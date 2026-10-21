"""Servizio HTTP del motore, contratto 1.2 (`docs/contratto_motore.md` dell'applicazione).

    GET    /v1/salute               stato, versioni, occupato, digest dei modelli
    POST   /v1/analisi              multipart `documento` + `metadati` → 202 {id_lavoro, stato}
    GET    /v1/analisi/{id_lavoro}  in_coda / in_corso (+ avanzamento) / completato (+ risultato) / errore
    DELETE /v1/analisi/{id_lavoro}  l'applicazione ha salvato: si cancella tutto ciò che resta

Un lavoro alla volta (un thread); 429 + Retry-After se occupato; idempotenza su
id_lavoro; 422 impronta_non_coincide se lo sha256 non coincide. Il documento sta
in una cartella dal nome neutro sul tmpfs e si cancella a fine analisi; il
risultato (che contiene il testo) resta in memoria fino al DELETE, al massimo
`conserva_risultato_s`. Log: solo identificativi, tempi e codici.

Avvio: uvicorn --factory servizio.app:crea_app_servizio --host 0.0.0.0 --port 8080
"""
import hashlib
import json
import logging
import re
import shutil
import threading
import time
import tomllib
import uuid
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, File, Form, Response, UploadFile
from fastapi.responses import JSONResponse

from servizio.errori import ErroreContratto, LavoroAnnullato
from servizio.formati import riconosci
from servizio.lavoro import Lavoro

from cerchio2.contratto_v1 import VERSIONE_CONTRATTO  # unica fonte della versione
FILE_IMPOSTAZIONI = Path(__file__).resolve().parents[1] / "config" / "servizio.toml"
ID_VALIDO = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
SHA256 = re.compile(r"[0-9a-f]{64}")

log = logging.getLogger("motore")


def carica_impostazioni(percorso: Path = FILE_IMPOSTAZIONI) -> dict:
    with open(percorso, "rb") as f:
        return tomllib.load(f)


class Stato:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.lavori: dict[str, dict] = {}   # id_lavoro -> {"lavoro", "stato", "esito", "fine"}
        self.attivo: str | None = None      # id del lavoro in elaborazione (anche se già cancellato)
        self.salute_cache: tuple[float, dict] | None = None

    def occupato(self) -> bool:
        return self.attivo is not None


def _errore(id_lavoro: str, e: ErroreContratto, http: int, headers: dict | None = None) -> JSONResponse:
    return JSONResponse({"id_lavoro": id_lavoro, "stato": "errore", "errore": e.corpo()},
                        status_code=http, headers=headers)


def crea_app(analizzatore: Callable | None = None, impostazioni: dict | None = None) -> FastAPI:
    imp = impostazioni or carica_impostazioni()
    if analizzatore is None:
        from servizio.catena import Catena
        analizzatore = Catena(imp["versione_motore"])
    lav = imp["lavoro"]
    radice = Path(lav["cartella_temporanea"])
    limite = int(lav["dimensione_max_mb"]) * 1024 * 1024
    stato = Stato()
    app = FastAPI(title="Motore S.I.R.E. (contratto 1.2)", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.motore = stato

    def pulisci_scaduti() -> None:
        limite_s = time.monotonic() - lav["conserva_risultato_s"]
        for k in [k for k, j in stato.lavori.items() if j["fine"] and j["fine"] < limite_s]:
            stato.lavori.pop(k, None)
            log.info("lavoro=%s evento=scaduto_senza_conferma", k)

    def esegui(id_lavoro: str, job: dict) -> None:
        lavoro = job["lavoro"]
        job["stato"] = "in_corso"
        inizio = time.monotonic()
        log.info("lavoro=%s evento=avviato", id_lavoro)
        try:
            risultato = analizzatore(lavoro)
            esito = {"id_lavoro": id_lavoro, "stato": "completato", "risultato": risultato}
            log.info("lavoro=%s evento=completato secondi=%.1f conteggi=%s tempi=%s", id_lavoro,
                     time.monotonic() - inizio, json.dumps(lavoro.conteggi), json.dumps(lavoro.tempi))
        except LavoroAnnullato:
            esito = None
            log.info("lavoro=%s evento=annullato secondi=%.1f", id_lavoro, time.monotonic() - inizio)
        except ErroreContratto as e:
            esito = {"id_lavoro": id_lavoro, "stato": "errore", "errore": e.corpo()}
            log.info("lavoro=%s evento=errore codice=%s secondi=%.1f", id_lavoro, e.codice,
                     time.monotonic() - inizio)
        except Exception as e:  # solo il tipo di errore, mai il messaggio (potrebbe contenere testo)
            esito = {"id_lavoro": id_lavoro, "stato": "errore",
                     "errore": ErroreContratto("errore_interno", "Errore interno del motore.").corpo()}
            log.warning("lavoro=%s evento=errore codice=errore_interno tipo=%s secondi=%.1f", id_lavoro,
                        type(e).__name__, time.monotonic() - inizio)
        finally:
            shutil.rmtree(lavoro.cartella, ignore_errors=True)
        with stato.lock:
            if esito is not None and stato.lavori.get(id_lavoro) is job:
                job["stato"], job["esito"], job["fine"] = esito["stato"], esito, time.monotonic()
            stato.attivo = None

    @app.get("/v1/salute")
    def salute() -> dict:
        corpo = {"stato": "pronto", "versione_motore": imp["versione_motore"],
                 "versione_contratto": VERSIONE_CONTRATTO, "occupato": stato.occupato()}
        modelli = getattr(analizzatore, "modelli", None)
        if modelli is None:
            return corpo
        adesso = time.monotonic()
        if stato.salute_cache is None or adesso - stato.salute_cache[0] > imp["salute"]["cache_s"]:
            try:
                stato.salute_cache = (adesso, {"modelli": modelli(imp["salute"]["timeout_ollama_s"])})
            except Exception as e:
                stato.salute_cache = (adesso, {"modelli": {}, "ollama": type(e).__name__})
        extra = stato.salute_cache[1]
        corpo.update(extra)
        if not extra["modelli"] or not all(m["atteso"] for m in extra["modelli"].values()):
            corpo["stato"] = "non_pronto"
        return corpo

    @app.post("/v1/analisi", status_code=202)
    async def consegna(documento: UploadFile | None = File(None), metadati: str | None = Form(None)):
        try:
            meta = json.loads(metadati or "")
            id_lavoro = str(meta["id_lavoro"])
            d = meta["documento"]
            documento_id, sha, nome_file = str(d["id"]), str(d["sha256"]).lower(), str(d.get("nome_file") or "")
            tipo_mime = d.get("tipo_mime")
            versione = str(meta.get("versione_contratto", VERSIONE_CONTRATTO))
        except (ValueError, KeyError, TypeError):
            return _errore("", ErroreContratto("richiesta_non_valida", "Metadati mancanti o non validi."), 422)
        if documento is None or not ID_VALIDO.fullmatch(id_lavoro) or not SHA256.fullmatch(sha):
            return _errore(id_lavoro if ID_VALIDO.fullmatch(id_lavoro) else "",
                           ErroreContratto("richiesta_non_valida", "Documento, id_lavoro o sha256 non validi."), 422)
        if versione.split(".")[0] != VERSIONE_CONTRATTO.split(".")[0]:
            return _errore(id_lavoro, ErroreContratto("richiesta_non_valida",
                                                      f"Versione del contratto non gestita: {versione[:10]}."), 422)
        contenuto = await documento.read(limite + 1)
        await documento.close()
        with stato.lock:
            pulisci_scaduti()
            if id_lavoro in stato.lavori:  # idempotenza: stesso id, nessun secondo lavoro
                return {"id_lavoro": id_lavoro, "stato": stato.lavori[id_lavoro]["stato"]}
            if stato.occupato():
                return _errore(id_lavoro, ErroreContratto("occupato", "Un altro lavoro è in corso."), 429,
                               {"Retry-After": str(lav["retry_after_s"])})
            if hashlib.sha256(contenuto).hexdigest() != sha:
                log.info("lavoro=%s evento=rifiutato codice=impronta_non_coincide", id_lavoro)
                return _errore(id_lavoro, ErroreContratto("impronta_non_coincide", "Il file è arrivato danneggiato."),
                               422)
            try:
                if len(contenuto) > limite:
                    raise ErroreContratto("formato_non_supportato",
                                          f"File oltre il limite di {lav['dimensione_max_mb']} MB.")
                estensione = riconosci(nome_file, tipo_mime, contenuto, imp["formati"])
            except ErroreContratto as e:  # lavoro creato già concluso in errore, come nel finto motore
                stato.lavori[id_lavoro] = {"lavoro": None, "stato": "errore", "fine": time.monotonic(),
                                           "esito": {"id_lavoro": id_lavoro, "stato": "errore", "errore": e.corpo()}}
                log.info("lavoro=%s evento=errore codice=%s", id_lavoro, e.codice)
                return {"id_lavoro": id_lavoro, "stato": "in_coda"}
            cartella = radice / uuid.uuid4().hex
            cartella.mkdir(parents=True, mode=0o700)
            percorso = cartella / f"documento{estensione}"
            percorso.write_bytes(contenuto)
            lavoro = Lavoro(id_lavoro=id_lavoro, documento_id=documento_id, sha256=sha, nome_file=nome_file,
                            estensione=estensione, cartella=cartella, percorso=percorso,
                            immagini=tuple(imp["formati"]["immagini"]),
                            scadenza=time.monotonic() + lav["tempo_max_s"])
            job = {"lavoro": lavoro, "stato": "in_coda", "esito": None, "fine": None}
            stato.lavori[id_lavoro] = job
            stato.attivo = id_lavoro
            log.info("lavoro=%s evento=ricevuto byte=%d formato=%s", id_lavoro, len(contenuto), estensione)
            threading.Thread(target=esegui, args=(id_lavoro, job), daemon=True, name=f"lavoro-{id_lavoro}").start()
        return {"id_lavoro": id_lavoro, "stato": "in_coda"}

    @app.get("/v1/analisi/{id_lavoro}")
    def leggi(id_lavoro: str):
        with stato.lock:
            pulisci_scaduti()
            job = stato.lavori.get(id_lavoro)
            if job is None:
                return _errore(id_lavoro, ErroreContratto("errore_interno", "Lavoro sconosciuto."), 404)
            if job["esito"] is not None:
                return job["esito"]
            corpo = {"id_lavoro": id_lavoro, "stato": job["stato"]}
            if job["lavoro"] is not None and job["lavoro"].avanzamento["pagine_totali"]:
                corpo["avanzamento"] = dict(job["lavoro"].avanzamento)
            return corpo

    @app.delete("/v1/analisi/{id_lavoro}", status_code=204)
    def conferma(id_lavoro: str) -> Response:
        with stato.lock:
            job = stato.lavori.pop(id_lavoro, None)
        if job is not None:
            if job["lavoro"] is not None and job["esito"] is None:
                job["lavoro"].annullato = True  # il thread si ferma alla prossima pagina o passo
            log.info("lavoro=%s evento=cancellato", id_lavoro)
        return Response(status_code=204)

    return app


def crea_app_servizio() -> FastAPI:
    """Fabbrica per uvicorn (--factory): catena vera e log solo con identificativi, tempi e codici."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    return crea_app()
