"""Lettura delle costanti da config/estrazione.toml."""
import tomllib
from pathlib import Path

FILE_CONFIG = Path(__file__).resolve().parents[2] / "config" / "estrazione.toml"


def carica(percorso: Path = FILE_CONFIG) -> dict:
    with open(percorso, "rb") as f:
        return tomllib.load(f)
