"""Test senza GPU: scomposizione delle celle multiple e sequenza di regole della decisione."""
from cerchio1.voci import carica_modulo, voci
from nucleo.decisione import AZIONI_PER_ESITO, applica_regole, urgenza

MODULO = carica_modulo()
AZIONI = MODULO["Azione"]["valori"]
AMBITI_CSV = MODULO["Ambito_csv"]["valori"]


def test_voci_separatori_diversi():
    assert voci("Veterinario; Colonia felina", AMBITI_CSV) == ["Veterinario", "Colonia felina"]
    assert voci("Veterinario,Igiene pubblica", AMBITI_CSV) == ["Veterinario", "Igiene pubblica"]
    assert voci("Allevamento / detenzione animali", AMBITI_CSV) == ["Allevamento/detenzione animali"]


def test_voci_la_piu_lunga_vince():
    assert voci("Sopralluogo congiunto", AZIONI) == ["Sopralluogo congiunto"]
    assert voci("Sopralluogo, Sopralluogo congiunto", AZIONI) == ["Sopralluogo", "Sopralluogo congiunto"]


def test_voci_testo_libero_diventa_altro():
    assert voci("Veterinario; cani pericolosi", AMBITI_CSV) == ["Veterinario", "Altro"]
    assert voci("", AMBITI_CSV) == []


def _u(p=False, h24=False, lunga=False, attivata=False):
    return {"pericolo_attuale": p, "in_corso_o_ultime_24h": h24, "condotta_lunga": lunga,
            "altra_autorita_attivata": attivata, "frase": ""}


def _r(comp="medicina veterinaria", ente="", conoscenza=False, chi=True, dove=True, cosa=True,
       secondari=(), valutabile=True, **u):
    return {"d1_competenza": {"risposta": comp, "ente": ente, "frase": "f1"},
            "d2_destinatario": {"risposta": conoscenza, "frase": "f2"},
            "d3_completezza": {"chi_segnala": chi, "dove": dove, "cosa": cosa,
                               "secondari_mancanti": list(secondari), "frase": "f3"},
            "d4_urgenza": _u(**u),
            "d5_valutabile": {"risposta": valutabile, "frase": "f5"}}


def test_urgenza():
    assert urgenza(_u()) == "Normale"
    assert urgenza(_u(p=True)) == "Alta"
    assert urgenza(_u(p=True, h24=True)) == "Immediata"
    assert urgenza(_u(lunga=True)) == "Bassa"
    assert urgenza(_u(p=True, h24=True, lunga=True, attivata=True)) == "Normale"


def test_regole_in_ordine():
    x = applica_regole(_r(comp="altra autorità", ente="Polizia Locale"))
    assert (x["determinante"], x["esito"], x["azione"]) == ("1", "Altro", ["Trasmissione ad altro ente"])
    assert "Polizia Locale" in x["note_regola"] and x["frase_determinante"] == "f1"
    x = applica_regole(_r(conoscenza=True, p=True))
    assert (x["determinante"], x["esito"], x["urgenza"]) == ("2", "Archiviato", "Alta")
    x = applica_regole(_r(dove=False))
    assert (x["esito"], x["note_regola"]) == ("Invio Modulo", "Manca: dove.")
    x = applica_regole(_r(secondari=["da quando", "recapito"]))
    assert x["esito"] == "Accolto" and "da quando" in x["note_regola"]
    assert applica_regole(_r())["azione"] == AZIONI_PER_ESITO["Accolto"]
    assert applica_regole(_r(valutabile=False, comp="altra autorità"))["esito"] == "Da approfondire"


def test_riscontro_ats_non_soggetto_a_completezza():
    assert applica_regole(_r(chi=False), tipo="riscontro ATS")["esito"] == "Accolto"
    assert applica_regole(_r(chi=False), tipo="esposto")["esito"] == "Invio Modulo"
