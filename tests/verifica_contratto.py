"""Verifica delle risposte contro il contratto 1.2 (schemi JSON copiati dall'applicazione).

Gli schemi in tests/contratto/ sono copie di
applicazione-completa-esposti/backend/motore/contratto/schema_*.json (vedi docs/diario.md
per le impronte); in più si controllano le regole di coerenza di contratto/modelli.py
(pagine in ordine e senza doppioni, lettura_incerta coerente con le pagine).
"""
import json
from pathlib import Path

import jsonschema

CARTELLA = Path(__file__).resolve().parent / "contratto"
SCHEMA_RISULTATO = json.loads((CARTELLA / "schema_risultato.json").read_text(encoding="utf-8"))
SCHEMA_STATO = json.loads((CARTELLA / "schema_stato_lavoro.json").read_text(encoding="utf-8"))
_FORMATI = jsonschema.FormatChecker()


def errori(schema: dict, dato: dict) -> list[str]:
    v = jsonschema.Draft202012Validator(schema, format_checker=_FORMATI)
    return sorted(f"{'/'.join(map(str, e.absolute_path))}: {e.message[:120]}" for e in v.iter_errors(dato))


def verifica_risultato(r: dict) -> None:
    e = errori(SCHEMA_RISULTATO, r)
    assert not e, e
    numeri = [p["numero"] for p in r["pagine"]]
    assert numeri == sorted(numeri) and len(set(numeri)) == len(numeri), "pagine non in ordine o duplicate"
    assert r["lettura_incerta"] == any(p["lettura_incerta"] for p in r["pagine"]), "lettura_incerta incoerente"
    assert r["versione_contratto"] == "1.2"


def verifica_stato(s: dict) -> None:
    e = errori(SCHEMA_STATO, s)
    assert not e, e
    if s["stato"] == "completato":
        assert s.get("risultato") is not None
        verifica_risultato(s["risultato"])
    if s["stato"] == "errore":
        assert s.get("errore") is not None
