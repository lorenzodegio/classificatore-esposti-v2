"""Test senza GPU: misure di confronto, divergenza e segnali deterministici del VLM."""
import pytest

from cerchio1.estrazione import config, vlm
from cerchio1.estrazione.divergenza import divergenza_pct
from cerchio1.estrazione.vlm import righe_ripetute
from tests.confronto import differenze_parole, levenshtein, misura, normalizza


def test_normalizza_ignora_spazi_e_a_capo():
    assert normalizza("  a\n\nb\t c ") == "a b c"


def test_levenshtein():
    assert levenshtein("gatto", "gatti") == 1
    assert levenshtein("", "abc") == 3
    assert levenshtein(["a", "b"], ["a", "c", "b"]) == 1


def test_misura_identici_e_diversi():
    assert misura("uno due\ntre", "uno  due tre")["errori_caratteri_pct"] == 0
    m = misura("il cane abbaia", "il gatto abbaia")
    assert m["errori_parole_pct"] == round(100 / 3, 1)


def test_differenze_parole():
    righe = differenze_parole("via dei Tigli 27", "via del Tigli")
    assert any("cambiato" in r for r in righe)
    assert any("mancante" in r and "27" in r for r in righe)


def test_righe_ripetute():
    assert righe_ripetute("a\nb\nb\n\nb\nb\nc", 4)
    assert not righe_ripetute("a\nb\na\nb", 2)


def test_divergenza():
    assert divergenza_pct("uno due\ntre", "uno due tre") == 0
    assert divergenza_pct("a b c d", "a b x d") == 25.0
    assert divergenza_pct("", "") == 0


def test_per_lettore_unisce_comuni_e_specifiche():
    cfg = config.carica()
    p = vlm.per_lettore(cfg, "principale")["vlm"]
    s = vlm.per_lettore(cfg, "secondo")["vlm"]
    assert p["modello"] != s["modello"]
    assert p["dpi"] == s["dpi"] == cfg["vlm"]["dpi"]
    assert "principale" not in p and "secondo" not in p
    assert p["ragionamento"] is False and "ragionamento" not in s
    with pytest.raises(ValueError):
        vlm.per_lettore(cfg, "terzo")


def test_verifica_modello_con_voci_doppie(monkeypatch):
    elenco = {"models": [
        {"name": "m:1", "model": "m:1", "digest": "bbbbbbbbbbbb" + "0" * 52},
        {"name": "m:1", "model": "m:1", "digest": "aaaaaaaaaaaa" + "0" * 52},
        {"name": "altro", "model": "altro", "digest": "cccccccccccc" + "0" * 52},
    ]}
    monkeypatch.setattr(vlm, "_richiesta", lambda *a, **k: elenco)
    cfg = {"vlm": {"url": "x", "modello": "m:1", "digest_attesi": ["bbbbbbbbbbbb", "aaaaaaaaaaaa"]}}
    assert vlm.digest_modello(cfg) == ["aaaaaaaaaaaa", "bbbbbbbbbbbb"]
    vlm.verifica_modello(cfg)
    cfg["vlm"]["digest_attesi"] = ["aaaaaaaaaaaa"]
    with pytest.raises(RuntimeError):
        vlm.verifica_modello(cfg)
    cfg["vlm"]["modello"] = "assente"
    with pytest.raises(RuntimeError):
        vlm.verifica_modello(cfg)
