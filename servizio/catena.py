"""Catena completa su UN documento, per il servizio: stessi passi di prototipo.py.

estrazione (cerchio1/estrazione: passo 0, poi le due passate VLM separate sulle
pagine da trascrivere, poi `completa`) → scheda → decisione → frasi per voce →
temi → tipo di documento → protocollo → adattatore del contratto 1.1.
Le funzioni dei cerchi e del nucleo si usano così come sono; qui si aggiungono
solo l'avanzamento per pagina, il tempo massimo e la cancellazione.
Nessun contenuto né nome di file nei log: solo identificativi, tempi e codici.
"""
import copy
import json
import time
import urllib.request
from pathlib import Path

from cerchio1 import frasi_voci, scheda, temi, voci
from cerchio1.estrazione import config, estrai, vlm
from cerchio2 import contratto_v1, protocollo, tipo_documento
from nucleo import decisione
from servizio.errori import ErroreContratto
from servizio.formati import immagine_in_pdf
from servizio.lavoro import Lavoro

RADICE = Path(__file__).resolve().parents[1]


class Catena:
    """Analizzatore vero: chiamabile con un Lavoro, restituisce il risultato del contratto."""

    def __init__(self, versione_motore: str, cfg: dict | None = None):
        self.versione_motore = versione_motore
        self.cfg = cfg or config.carica()
        self.modulo = voci.carica_modulo()
        self.criteri = (RADICE / self.cfg["percorsi"]["criteri"]).read_text(encoding="utf-8")
        self.vocabolario_temi = temi.carica_vocabolario()

    # --- salute -------------------------------------------------------------------------
    def modelli(self, timeout_s: float) -> dict:
        """Digest dei modelli in Ollama e se coincidono con quelli attesi (config/estrazione.toml)."""
        url = self.cfg["vlm"]["url"]
        with urllib.request.urlopen(f"{url}/api/tags", timeout=timeout_s) as r:
            elenco = json.loads(r.read()).get("models", [])
        uscita = {}
        for lettore in vlm.LETTORI:
            v = vlm.per_lettore(self.cfg, lettore)["vlm"]
            trovati = sorted({m.get("digest", "")[:12] for m in elenco
                              if v["modello"] in (m.get("name"), m.get("model"))})
            uscita[v["modello"]] = {"digest": trovati, "atteso": trovati == sorted(v["digest_attesi"])}
        return uscita

    # --- analisi ------------------------------------------------------------------------
    def _tempo(self, lavoro: Lavoro, nome: str, inizio: float) -> None:
        lavoro.tempi[nome] = round(time.monotonic() - inizio, 1)

    def __call__(self, lavoro: Lavoro) -> dict:
        cfg = copy.deepcopy(self.cfg)
        cfg["percorsi"]["lavoro"] = str(lavoro.cartella)  # conversioni Word/RTF nel tmpfs del lavoro
        t = time.monotonic()
        percorso = lavoro.percorso
        if lavoro.estensione in lavoro.immagini:
            percorso = lavoro.cartella / "documento_immagine.pdf"
            try:
                immagine_in_pdf(lavoro.percorso, percorso, cfg["vlm"]["dpi"])
            except Exception:
                raise ErroreContratto("documento_illeggibile", "L'immagine non si apre.") from None
        doc = estrai.prepara(percorso, cfg)
        if (doc.get("conversione") or {}).get("esito") == "fallita":
            raise ErroreContratto("documento_illeggibile", "Il file non si è potuto convertire in PDF.")
        if doc.get("errore_apertura"):
            raise ErroreContratto("documento_illeggibile", "Il file non si apre come PDF.")
        if not doc["pagine"]:
            raise ErroreContratto("documento_illeggibile", "Il documento non ha pagine.")

        da_trascrivere = [p for p in doc["pagine"] if p["modalita"] == "vlm"]
        totali = len(doc["pagine"])
        digitali = totali - len(da_trascrivere)
        letture = 0
        lavoro.avanzamento = {"pagine_lette": digitali, "pagine_totali": totali}
        letture_per_lettore = {}
        for lettore in vlm.LETTORI if da_trascrivere else ():
            # Due passate separate, come estrai.estrai: prima il principale, poi il secondo.
            c = vlm.per_lettore(cfg, lettore)
            vlm.verifica_modello(c)
            v = c["vlm"]
            letture_per_lettore[lettore] = {}
            for p in da_trascrivere:
                lavoro.controlla()
                png = vlm.rendi_pagina(doc["pdf"], p["n"] - 1, v["dpi"], v["lato_max_px"])
                letture_per_lettore[lettore][p["n"]] = vlm.trascrivi(png, c)
                letture += 1
                # una pagina è letta quando l'hanno letta entrambi i lettori: metà per passata
                lavoro.avanzamento = {"pagine_lette": digitali + letture // 2, "pagine_totali": totali}
        estrai.completa(doc, letture_per_lettore.get("principale", {}), letture_per_lettore.get("secondo", {}),
                        cfg["vlm"]["divergenza_incerta_pct"])
        lavoro.avanzamento = {"pagine_lette": totali, "pagine_totali": totali}
        lavoro.conteggi = {"pagine": totali, "trascritte": len(da_trascrivere),
                           "incerte": len(doc["documento"]["pagine_incerte"])}
        self._tempo(lavoro, "estrazione", t)
        if doc["documento"]["senza_contenuto"]:
            raise ErroreContratto("documento_illeggibile", "Nessuna pagina contiene testo riconoscibile.")

        lavoro.controlla()
        t = time.monotonic()
        sch = scheda.compila(doc, cfg, self.modulo)
        self._tempo(lavoro, "scheda", t)
        lavoro.controlla()
        t = time.monotonic()
        dec = decisione.decidi(sch, doc["documento"]["lettura_incerta"], cfg, self.criteri)
        self._tempo(lavoro, "decisione", t)
        lavoro.controlla()
        t = time.monotonic()
        frasi = frasi_voci.frasi(doc, sch, cfg)
        self._tempo(lavoro, "frasi", t)
        lavoro.controlla()
        t = time.monotonic()
        proposti = temi.proponi(doc, cfg, self.vocabolario_temi)
        self._tempo(lavoro, "temi", t)
        lavoro.controlla()
        t = time.monotonic()
        tipo = tipo_documento.classifica(doc, sch, cfg)
        self._tempo(lavoro, "tipo", t)
        prot = protocollo.protocollo(doc["pagine"], lavoro.nome_file)
        return contratto_v1.risultato(doc=doc, documento_id=lavoro.documento_id, sha256=lavoro.sha256, sch=sch,
                                      dec=dec, frasi=frasi, temi=proposti, tipo=tipo, prot=prot,
                                      versione_motore=self.versione_motore)
