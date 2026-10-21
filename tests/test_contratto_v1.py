"""Test senza GPU: ancoraggio delle frasi, protocollo dal testo, tipo di documento, adattatore 1.2."""
from cerchio1.ancora import FRASE_MAX, ancora, tronca
from cerchio1.voci import carica_modulo
from cerchio2 import contratto_v1, protocollo, tipo_documento
from cerchio1.temi import carica_vocabolario
from tests.verifica_contratto import verifica_risultato

PAGINE = [{"n": 1, "testo": "Oggetto: prova\nProt. n. 0004512/2025 del 08/04/2025\n"},
          {"n": 2, "testo": "Testo di prova: nel cortile di prova ci sono sette cani di esempio,\nquattro grandi e tre piccoli, dentro un recinto di prova."}]


def test_ancora_esatta_con_a_capo_e_maiuscole():
    frase, pagina = ancora("sette cani di esempio, quattro grandi", PAGINE)
    assert pagina == 2 and frase == "sette cani di esempio, quattro grandi"  # spazi uniformati da tronca


def test_ancora_restituisce_il_testo_letterale_del_documento():
    frase, pagina = ancora("SETTE  cani DI esempio, QUATTRO grandi", PAGINE)
    assert pagina == 2 and "sette cani" in frase and "SETTE" not in frase


def test_ancora_approssimata_e_vuota():
    frase, pagina = ancora("sette cani di esempo, quattro grandi e tre picoli", PAGINE)
    assert pagina == 2 and "piccoli" in frase
    assert ancora("", PAGINE) is None
    frase, _ = ancora("frase che non esiste da nessuna parte", PAGINE)
    assert frase == "frase che non esiste da nessuna parte"


def test_ancora_con_puntini_prende_il_tratto_piu_lungo():
    frase, pagina = ancora("sette cani di esempio, quattro grandi ... dentro un", PAGINE)
    assert (frase, pagina) == ("sette cani di esempio, quattro grandi", 2)


def test_tronca():
    assert len(tronca("parola " * 100)) <= FRASE_MAX
    assert tronca("  a \n b  ") == "a b"


def test_protocollo_dal_testo_forme_diverse():
    p = protocollo.dal_testo(PAGINE)
    assert p == {"numero": "0004512/2025", "data": "2025-04-08", "frase": "Prot. n. 0004512/2025 del 08/04/2025",
                 "pagina": 1}
    p = protocollo.dal_testo([{"n": 1, "testo": "nota di prova prot. n. 12345 dell'8 aprile 2025 - prova"}])
    assert (p["numero"], p["data"]) == ("0012345/2025", "2025-04-08")
    p = protocollo.dal_testo([{"n": 3, "testo": "x\nRif. Prot. 0003177/2025\ny"}])
    assert (p["numero"], p["data"], p["pagina"], p["frase"]) == ("0003177/2025", None, 3, "Prot. 0003177/2025")
    p = protocollo.dal_testo([{"n": 1, "testo": "Protocollo N° 5120 / 2025, del 11-04-2025"}])
    assert (p["numero"], p["data"]) == ("0005120/2025", "2025-04-11")
    assert protocollo.dal_testo([{"n": 1, "testo": "Protocollo ATS <protocollo@ats.example>"}]) is None
    p = protocollo.dal_testo([{"n": 1, "testo": "prot. 4512 senza data"}])
    assert (p["numero"], p["data"]) == ("0004512", None)


def test_protocollo_dal_nome_come_ripiego():
    p = protocollo.protocollo([{"n": 1, "testo": "nessun numero"}], "Prot. 54321.14-03-2025.pdf")
    assert (p["numero"], p["data"], p["pagina"]) == ("0054321", None, 1)  # l'anno non si inventa
    assert p["frase"].startswith("(nome del file)")
    assert protocollo.protocollo([{"n": 1, "testo": ""}], "esposto.pdf") is None


def test_data_iso():
    assert protocollo.data_iso("09/04/2025") == "2025-04-09"
    assert protocollo.data_iso("9 aprile 2025") == "2025-04-09"
    assert protocollo.data_iso("31/02/2025") is None
    assert protocollo.data_iso("") is None


def test_tipo_documento_regole():
    r = {"inoltro": True, "integrazione": False, "frase": "frase di prova", "motivo": "m"}
    pag = [{"n": 1, "testo": "Frase di prova numero uno"}]
    assert tipo_documento.decidi("richiesta ente", r, pag)["valore"] == "inoltro_per_competenza"
    assert tipo_documento.decidi("riscontro ATS", r, pag)["valore"] == "riscontro_ats"
    assert tipo_documento.decidi("lettera avvocato", r, pag)["valore"] == "lettera_avvocato"
    r = {"inoltro": False, "integrazione": True, "frase": "", "motivo": "m"}
    assert tipo_documento.decidi("esposto", r, pag)["valore"] == "integrazione"
    r = {"inoltro": False, "integrazione": False, "frase": "", "motivo": "Motivo di prova."}
    assert tipo_documento.decidi("esposto", r, pag) == {"valore": "esposto", "motivo": "Motivo di prova."}
    assert set(tipo_documento.DA_SCHEDA.values()) <= set(tipo_documento.CODICI)


def test_vocabolari_del_contratto():
    modulo = carica_modulo()
    assert modulo["Ambito"]["valori"] == ["Medicina Veterinaria", "Igiene pubblica", "Disturbo/rumori", "ARPA", "Altro"]
    assert [t["valore"] for t in carica_vocabolario()] == ["Cani", "Gatti e colonie feline", "Animali da reddito",
                                                          "Avvelenamenti"]
    assert tipo_documento.CODICI == ["esposto", "inoltro_per_competenza", "richiesta_ente", "riscontro_ats",
                                     "lettera_avvocato", "integrazione", "altro"]


def _doc(incerta=False):
    return {"pagine": [{"n": 1, "modalita": "digitale", "testo": PAGINE[0]["testo"], "lettura_incerta": False,
                        "divergenza_pct": None, "segnali": []},
                       {"n": 2, "modalita": "vlm", "testo": PAGINE[1]["testo"], "lettura_incerta": incerta,
                        "divergenza_pct": 12.5 if incerta else 0.0, "segnali": ["illeggibile"] if incerta else []},
                       {"n": 3, "modalita": "vuota", "testo": "", "lettura_incerta": False,
                        "divergenza_pct": None, "segnali": []}]}


SCHEDA = {"tipo_documento": "esposto", "data_doc": "08/04/2025", "comune": "Borgoverde",
          "ambito": ["Medicina Veterinaria"], "ambito_altro": "", "problematica": ["Condizione di inidonea detenzione"],
          "prob_altro": "", "elementi": ["Altro"], "elementi_altro": "valore di prova",
          "giustificazioni": {"data_doc": "del 08/04/2025", "comune": "", "ambito": "sette cani"}}
DECISIONE = {"esito": "Accolto", "urgenza": "Normale", "azione": ["Sopralluogo congiunto"], "determinante": "3",
             "frase_determinante": "dentro un recinto di prova", "note": "Istanza completa."}


def test_adattatore_produce_un_risultato_conforme():
    doc = _doc(incerta=True)
    frasi = {"ambito": [{"valore": "Medicina Veterinaria", "frase": "sette cani", "pagina": 2}],
             "problematica": [{"valore": "Condizione di inidonea detenzione", "frase": "x" * 400, "pagina": 2}],
             "elementi": [{"valore": "Altro", "frase": "tre piccoli", "pagina": 2}]}
    temi = [{"valore": "Cani", "motivo": "Motivo di prova.", "frase": "sette cani", "pagina": 2}]
    r = contratto_v1.risultato(doc=doc, documento_id="d1", sha256="a" * 64, sch=SCHEDA, dec=DECISIONE, frasi=frasi,
                               temi=temi, tipo={"valore": "esposto", "motivo": "m"},
                               prot=protocollo.dal_testo(doc["pagine"]), versione_motore="2.2.0")
    verifica_risultato(r)
    assert [p["acquisizione"] for p in r["pagine"]] == ["testo_nativo", "ocr", "nessuna"]
    assert r["lettura_incerta"] and "12.5%" in r["pagine"][1]["motivo_incertezza"]
    assert r["scheda"]["data_doc"] == {"valore": "2025-04-08", "frase": "del 08/04/2025", "pagina": 1}
    assert r["scheda"]["comune"]["valore"] == "Borgoverde"
    assert len(r["scheda"]["problematica"][0]["frase"]) <= FRASE_MAX
    assert r["scheda"]["elementi_altro"] == "valore di prova" and r["scheda"]["ambito_altro"] is None
    assert r["proposta"]["domanda_decisiva"] == contratto_v1.DOMANDE_BREVI["3"]
    assert r["proposta"]["da_verificare_sull_originale"] == ["Pagina 2: lettura incerta, leggere l'originale."]
    assert r["protocollo"]["numero"] == "0004512/2025"


def test_adattatore_scheda_vuota():
    sch = {"tipo_documento": "altro", "data_doc": "", "comune": "", "ambito": [], "problematica": [], "elementi": [],
           "giustificazioni": {}}
    r = contratto_v1.risultato(doc=_doc(), documento_id="d1", sha256="b" * 64, sch=sch,
                               dec={**DECISIONE, "determinante": "5", "frase_determinante": ""},
                               frasi={"ambito": [], "problematica": [], "elementi": []}, temi=[],
                               tipo={"valore": "altro", "motivo": "m"}, prot=None, versione_motore="2.2.0")
    verifica_risultato(r)
    assert r["scheda"]["data_doc"] is None and r["scheda"]["comune"] is None and r["protocollo"] is None
    assert not r["lettura_incerta"] and r["proposta"]["da_verificare_sull_originale"] == []
