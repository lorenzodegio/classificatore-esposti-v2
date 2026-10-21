"""Test senza GPU della catena vera del servizio con i modelli simulati.

Estrazione (pypdfium2, LibreOffice), adattatore, protocollo e trasporto HTTP sono
quelli veri; solo le chiamate a Ollama sono sostituite: il "VLM" restituisce la
verità delle scansioni sintetiche (il secondo lettore la storpia sui fogli a mano,
così scatta la lettura incerta) e l'"LLM" risponde con valori plausibili nella
forma richiesta dallo schema. Si verificano le risposte contro gli schemi del
contratto su tutti i documenti sintetici: 4 scansioni, un PDF digitale, un Word.
"""
import hashlib
import json
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cerchio1.estrazione import vlm
from servizio import catena as modulo_catena
from servizio.app import carica_impostazioni, crea_app
from tests.verifica_contratto import verifica_stato

SINTETICI = Path(__file__).resolve().parent / "dati_sintetici"
DOCUMENTI = {  # file -> (nome dichiarato dall'applicazione, tipo MIME)
    "scansioni/email_inoltrata.pdf": ("Prot. 12345.08-04-2025.pdf", "application/pdf"),
    "scansioni/mano_1.pdf": ("mano_1.pdf", "application/pdf"),
    "scansioni/mano_2.pdf": ("12 Esposto 54400.20-07-2025.pdf", "application/pdf"),
    "scansioni/mano_3.pdf": ("esposto.pdf", "application/pdf"),
    "digitali/esposto_digitale.pdf": ("esposto_digitale.pdf", "application/pdf"),
    "digitali/riscontro_word.docx": ("riscontro_word.docx",
                                     "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
}


def _verita() -> dict:
    v = {}
    for pdf in (SINTETICI / "scansioni").glob("*.pdf"):
        pagine = pdf.with_suffix(".verita.txt").read_text(encoding="utf-8").split("\f")
        v[hashlib.sha256(pdf.read_bytes()).hexdigest()] = (pdf.stem, pagine)
    return v


VERITA = _verita()


def finto_rendi(percorso_pdf, indice, dpi, lato_max_px):
    return f"{hashlib.sha256(Path(percorso_pdf).read_bytes()).hexdigest()}|{indice}".encode()


def finto_trascrivi(png, cfg):
    sha, indice = png.decode().split("|")
    nome, pagine = VERITA[sha]
    testo = pagine[int(indice)] if int(indice) < len(pagine) else ""
    if cfg["vlm"]["modello"] != vlm.per_lettore(modulo_catena.config.carica(), "principale")["vlm"]["modello"] \
            and nome.startswith("mano"):
        testo = " ".join(p for i, p in enumerate(testo.split()) if i % 5)  # secondo lettore: 20% di parole perse
    return {"testo": testo, "errore": None, "troncato": False, "ripetizioni": False, "marcatori_illeggibile": 0,
            "secondi": 0.0}


def finto_chiedi_json(cfg_llm, sistema, utente, schema):
    props = schema["properties"]
    testo = utente.split("Testo del documento:\n", 1)[-1]
    righe = [r.strip() for r in testo.splitlines() if r.strip() and not r.startswith("[Pagina")]
    frase = max(righe, key=len) if righe else ""
    if "giustificazioni" in props:  # scheda
        campi = props["giustificazioni"]["required"]
        return {"tipo_documento": "esposto", "data_doc": "14/03/2025", "comune": "Borgoverde",
                "segnalante": "privato cittadino", "segnalante_rintracciabile": True, "destinatari": "", "luogo": "",
                "animali": "", "da_quando": "", "ambito": ["Medicina Veterinaria"], "ambito_altro": "",
                "problematica": ["Condizione di inidonea detenzione"], "prob_altro": "", "elementi": ["Foto/allegati"],
                "elementi_altro": "", "contenuto_presente": True, "contenuto_altrove": "",
                "giustificazioni": {c: frase for c in campi}}
    if "d1_competenza" in props:  # decisione
        return {"d1_competenza": {"risposta": "medicina veterinaria", "ente": "", "frase": frase},
                "d2_destinatario": {"risposta": False, "frase": ""},
                "d3_completezza": {"chi_segnala": True, "dove": True, "cosa": True, "secondari_mancanti": [],
                                   "frase": frase},
                "d4_urgenza": {"pericolo_attuale": False, "in_corso_o_ultime_24h": False, "condotta_lunga": False,
                               "altra_autorita_attivata": False, "frase": ""},
                "d5_valutabile": {"risposta": True, "frase": frase}}
    if "temi" in props:
        return {"temi": [{"valore": "Cani", "motivo": "Si parla di animali.", "frase": frase}]}
    if "inoltro" in props:
        return {"inoltro": False, "integrazione": False, "frase": "", "motivo": "Un privato segnala un problema."}
    return {c: [{"valore": v, "frase": frase} for v in props[c]["items"]["properties"]["valore"]["enum"] if v]
            for c in props}  # frasi per voce


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(vlm, "rendi_pagina", finto_rendi)
    monkeypatch.setattr(vlm, "trascrivi", finto_trascrivi)
    monkeypatch.setattr(vlm, "verifica_modello", lambda c: None)
    for modulo in ("cerchio1.scheda", "nucleo.decisione", "cerchio1.frasi_voci", "cerchio1.temi",
                   "cerchio2.tipo_documento"):
        monkeypatch.setattr(f"{modulo}.chiedi_json", finto_chiedi_json)
    imp = carica_impostazioni()
    imp["lavoro"] = {**imp["lavoro"], "cartella_temporanea": str(tmp_path / "lavoro")}
    return TestClient(crea_app(analizzatore=modulo_catena.Catena(imp["versione_motore"]), impostazioni=imp))


def _analizza(client, relativo):
    nome, mime = DOCUMENTI[relativo]
    contenuto = (SINTETICI / relativo).read_bytes()
    id_lavoro = str(uuid.uuid4())
    meta = {"versione_contratto": "1.1", "id_lavoro": id_lavoro,
            "documento": {"id": f"doc-{Path(relativo).stem}", "nome_file": nome, "tipo_mime": mime,
                          "sha256": hashlib.sha256(contenuto).hexdigest()}}
    r = client.post("/v1/analisi", files={"documento": (nome, contenuto, mime)}, data={"metadati": json.dumps(meta)})
    assert r.status_code == 202, r.text
    fine = time.monotonic() + 120
    while time.monotonic() < fine:
        s = client.get(f"/v1/analisi/{id_lavoro}").json()
        verifica_stato(s)
        if s["stato"] in ("completato", "errore"):
            assert client.delete(f"/v1/analisi/{id_lavoro}").status_code == 204
            return s
        time.sleep(0.05)
    raise AssertionError("lavoro non concluso")


@pytest.mark.parametrize("relativo", list(DOCUMENTI))
def test_catena_simulata_conforme_al_contratto(client, relativo):
    s = _analizza(client, relativo)
    assert s["stato"] == "completato", s.get("errore")
    r = s["risultato"]
    assert r["versione_motore"] == "2.1.0" and r["documento"]["id"] == f"doc-{Path(relativo).stem}"
    assert r["scheda"]["ambito"] and all(v["frase"] for v in r["scheda"]["ambito"])
    assert r["temi"] and r["temi"][0]["valore"] == "Cani"
    acquisizioni = {p["acquisizione"] for p in r["pagine"]}
    if relativo.startswith("scansioni"):
        assert acquisizioni == {"ocr"}
        assert r["lettura_incerta"] is Path(relativo).stem.startswith("mano")
    else:
        assert acquisizioni == {"testo_nativo"} and not r["lettura_incerta"]


def test_protocolli_dei_sintetici(client):
    # dal testo (timbro di protocollo nella scansione dell'email inoltrata e nel Word)
    assert _analizza(client, "scansioni/email_inoltrata.pdf")["risultato"]["protocollo"]["numero"] == "0004512/2025"
    p = _analizza(client, "digitali/riscontro_word.docx")["risultato"]["protocollo"]
    assert (p["numero"], p["data"], p["pagina"]) == ("0098317/2025", "2025-05-20", 1)
    # dal nome del file, in mancanza di protocollo nel testo
    p = _analizza(client, "scansioni/mano_2.pdf")["risultato"]["protocollo"]
    assert (p["numero"], p["data"]) == ("0054400/2025", "2025-07-20")
    assert _analizza(client, "scansioni/mano_3.pdf")["risultato"]["protocollo"] is None
