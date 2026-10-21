"""Test senza GPU del servizio HTTP: trasporto, uno alla volta, idempotenza, impronta, errori, DELETE.

La catena è simulata da un analizzatore finto (nessun modello): restituisce un
risultato conforme costruito con l'adattatore del contratto.
"""
import hashlib
import json
import threading
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from cerchio2 import contratto_v1
from servizio.app import carica_impostazioni, crea_app
from servizio.errori import ErroreContratto
from tests.verifica_contratto import verifica_stato

PDF_FINTO = b"%PDF-1.4\n% documento finto per i test del trasporto\n"


class Finto:
    """Analizzatore finto: aspetta il via (se richiesto), avanza per pagine, poi risponde."""

    def __init__(self, pagine=3, errore=None, attendi=False):
        self.pagine, self.errore, self.chiamate = pagine, errore, 0
        self.via = threading.Event()
        if not attendi:
            self.via.set()
        self.visti = []

    def __call__(self, lavoro):
        self.chiamate += 1
        self.visti.append(lavoro.percorso)
        assert lavoro.percorso.exists() and lavoro.percorso.name.startswith("documento")
        lavoro.avanzamento = {"pagine_lette": 0, "pagine_totali": self.pagine}
        for i in range(self.pagine):
            while not self.via.wait(0.01):
                lavoro.controlla()
            lavoro.controlla()
            lavoro.avanzamento = {"pagine_lette": i + 1, "pagine_totali": self.pagine}
        if isinstance(self.errore, Exception):
            raise self.errore
        doc = {"pagine": [{"n": i + 1, "modalita": "digitale", "testo": f"pagina {i + 1}", "lettura_incerta": False,
                           "divergenza_pct": None, "segnali": []} for i in range(self.pagine)]}
        return contratto_v1.risultato(
            doc=doc, documento_id=lavoro.documento_id, sha256=lavoro.sha256,
            sch={"data_doc": "", "comune": "", "ambito": [], "problematica": [], "elementi": [], "giustificazioni": {}},
            dec={"esito": "Accolto", "urgenza": "Normale", "azione": [], "determinante": "3",
                 "frase_determinante": "", "note": "Istanza completa."},
            frasi={}, temi=[], tipo={"valore": "esposto", "motivo": "m"}, prot=None, versione_motore="2.1.0")


@pytest.fixture
def imp(tmp_path):
    i = carica_impostazioni()
    i["lavoro"] = {**i["lavoro"], "cartella_temporanea": str(tmp_path / "lavoro"), "retry_after_s": 7}
    return i


def _client(finto, imp):
    return TestClient(crea_app(analizzatore=finto, impostazioni=imp))


def _invia(c, contenuto=PDF_FINTO, nome="esposto.pdf", id_lavoro=None, sha=None, mime="application/pdf", **meta):
    id_lavoro = id_lavoro or str(uuid.uuid4())
    metadati = {"versione_contratto": "1.1", "id_lavoro": id_lavoro,
                "documento": {"id": "doc-1", "nome_file": nome, "tipo_mime": mime,
                              "sha256": sha or hashlib.sha256(contenuto).hexdigest()}, **meta}
    r = c.post("/v1/analisi", files={"documento": (nome, contenuto, mime)},
               data={"metadati": json.dumps(metadati)})
    return id_lavoro, r


def _attendi(c, id_lavoro, finali=("completato", "errore"), limite=10):
    fine = time.monotonic() + limite
    while time.monotonic() < fine:
        s = c.get(f"/v1/analisi/{id_lavoro}").json()
        verifica_stato(s)
        if s["stato"] in finali:
            return s
        time.sleep(0.02)
    raise AssertionError("il lavoro non si è concluso")


def test_salute(imp):
    s = _client(Finto(), imp).get("/v1/salute").json()
    assert s == {"stato": "pronto", "versione_motore": "2.1.0", "versione_contratto": "1.1", "occupato": False}


def test_flusso_completo_e_delete(imp, tmp_path):
    f = Finto(attendi=True)
    c = _client(f, imp)
    id_lavoro, r = _invia(c)
    assert r.status_code == 202 and r.json() == {"id_lavoro": id_lavoro, "stato": "in_coda"}
    time.sleep(0.05)
    s = c.get(f"/v1/analisi/{id_lavoro}").json()
    verifica_stato(s)
    assert s["stato"] == "in_corso" and s["avanzamento"] == {"pagine_lette": 0, "pagine_totali": 3}
    assert c.get("/v1/salute").json()["occupato"] is True
    f.via.set()
    s = _attendi(c, id_lavoro)
    assert s["stato"] == "completato" and s["risultato"]["documento"] == {"id": "doc-1",
                                                                          "sha256": hashlib.sha256(PDF_FINTO).hexdigest()}
    assert not f.visti[0].exists(), "il documento deve sparire a fine analisi"
    assert list((tmp_path / "lavoro").iterdir()) == []
    # il risultato resta leggibile finché non arriva il DELETE
    assert c.get(f"/v1/analisi/{id_lavoro}").json()["stato"] == "completato"
    assert c.delete(f"/v1/analisi/{id_lavoro}").status_code == 204
    r = c.get(f"/v1/analisi/{id_lavoro}")
    assert r.status_code == 404 and r.json()["errore"]["codice"] == "errore_interno"
    assert c.delete(f"/v1/analisi/{id_lavoro}").status_code == 204  # idempotente


def test_occupato_429_con_retry_after(imp):
    f = Finto(attendi=True)
    c = _client(f, imp)
    primo, _ = _invia(c)
    _, r = _invia(c)
    assert r.status_code == 429 and r.headers["Retry-After"] == "7"
    corpo = r.json()
    verifica_stato(corpo)
    assert corpo["errore"] == {"codice": "occupato", "messaggio": "Un altro lavoro è in corso.", "ritentabile": True}
    f.via.set()
    _attendi(c, primo)
    _, r = _invia(c)  # concluso il primo, il motore accetta di nuovo (anche senza DELETE)
    assert r.status_code == 202


def test_idempotenza_stesso_id_nessun_secondo_lavoro(imp):
    f = Finto()
    c = _client(f, imp)
    id_lavoro, r1 = _invia(c)
    _attendi(c, id_lavoro)
    _, r2 = _invia(c, id_lavoro=id_lavoro)
    assert r1.status_code == r2.status_code == 202
    assert r2.json() == {"id_lavoro": id_lavoro, "stato": "completato"}
    assert f.chiamate == 1


def test_idempotenza_mentre_lavora_non_da_429(imp):
    f = Finto(attendi=True)
    c = _client(f, imp)
    id_lavoro, _ = _invia(c)
    _, r = _invia(c, id_lavoro=id_lavoro)
    assert r.status_code == 202 and r.json()["stato"] in ("in_coda", "in_corso")
    f.via.set()
    _attendi(c, id_lavoro)
    assert f.chiamate == 1


def test_impronta_non_coincide_422(imp):
    f = Finto()
    c = _client(f, imp)
    id_lavoro, r = _invia(c, sha="0" * 64)
    assert r.status_code == 422
    corpo = r.json()
    verifica_stato(corpo)
    assert corpo["errore"]["codice"] == "impronta_non_coincide" and corpo["errore"]["ritentabile"] is True
    assert f.chiamate == 0 and c.get(f"/v1/analisi/{id_lavoro}").status_code == 404


def test_formato_non_supportato(imp):
    c = _client(Finto(), imp)
    id_lavoro, r = _invia(c, contenuto=b"PK\x03\x04 non un formato gestito", nome="nota_segreta.pages",
                          mime="application/octet-stream")
    assert r.status_code == 202
    s = _attendi(c, id_lavoro)
    assert s["errore"]["codice"] == "formato_non_supportato" and s["errore"]["ritentabile"] is False
    assert "nota_segreta" not in s["errore"]["messaggio"] and ".pages" in s["errore"]["messaggio"]


def test_formato_dalla_firma_se_manca_l_estensione(imp):
    f = Finto()
    c = _client(f, imp)
    id_lavoro, _ = _invia(c, nome="senza_estensione", mime="application/octet-stream")
    assert _attendi(c, id_lavoro)["stato"] == "completato"
    assert f.visti[0].suffix == ".pdf"


@pytest.mark.parametrize("errore, codice, ritentabile", [
    (ErroreContratto("documento_illeggibile", "Nessuna pagina contiene testo riconoscibile."), "documento_illeggibile",
     False),
    (RuntimeError("testo riservato del documento"), "errore_interno", True),
])
def test_errori_della_catena(imp, errore, codice, ritentabile):
    c = _client(Finto(errore=errore), imp)
    id_lavoro, _ = _invia(c)
    s = _attendi(c, id_lavoro)
    assert (s["errore"]["codice"], s["errore"]["ritentabile"]) == (codice, ritentabile)
    assert "riservato" not in s["errore"]["messaggio"]


def test_tempo_scaduto(imp):
    imp["lavoro"]["tempo_max_s"] = 0.1
    c = _client(Finto(attendi=True), imp)
    id_lavoro, _ = _invia(c)
    s = _attendi(c, id_lavoro)
    assert s["errore"]["codice"] == "tempo_scaduto" and s["errore"]["ritentabile"] is True


def test_delete_durante_il_lavoro_lo_ferma(imp, tmp_path):
    f = Finto(attendi=True)
    c = _client(f, imp)
    id_lavoro, _ = _invia(c)
    time.sleep(0.05)
    assert c.delete(f"/v1/analisi/{id_lavoro}").status_code == 204
    assert c.get(f"/v1/analisi/{id_lavoro}").status_code == 404
    fine = time.monotonic() + 5
    while c.get("/v1/salute").json()["occupato"] and time.monotonic() < fine:
        time.sleep(0.02)
    assert not c.get("/v1/salute").json()["occupato"]
    assert list((tmp_path / "lavoro").iterdir()) == []
    _, r = _invia(c)
    assert r.status_code == 202


def test_richieste_non_valide(imp):
    c = _client(Finto(), imp)
    r = c.post("/v1/analisi", files={"documento": ("a.pdf", PDF_FINTO, "application/pdf")}, data={"metadati": "{"})
    assert r.status_code == 422 and r.json()["errore"]["codice"] == "richiesta_non_valida"
    _, r = _invia(c, id_lavoro="../../etc")
    assert r.status_code == 422
    _, r = _invia(c, versione_contratto="2.0")
    assert r.status_code == 422


def test_risultato_non_confermato_scade(imp):
    imp["lavoro"]["conserva_risultato_s"] = 0.05
    c = _client(Finto(), imp)
    id_lavoro, _ = _invia(c)
    _attendi(c, id_lavoro)
    time.sleep(0.1)
    assert c.get(f"/v1/analisi/{id_lavoro}").status_code == 404
