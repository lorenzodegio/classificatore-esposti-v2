"""Valori del modulo ATS e scomposizione delle celle a scelta multipla in voci singole."""
import re
import tomllib
from pathlib import Path

FILE_MODULO = Path(__file__).resolve().parents[1] / "config" / "scheda_ats.toml"


def carica_modulo() -> dict:
    with open(FILE_MODULO, "rb") as f:
        return tomllib.load(f)


def chiave(testo: str) -> str:
    """Forma di confronto: minuscole, spazi uniformi, nessuno spazio attorno a '/'."""
    t = " ".join(str(testo or "").split()).casefold()
    return re.sub(r"\s*/\s*", "/", t)


def voci(cella: str, ammessi: list[str]) -> list[str]:
    """Voci ammesse contenute in una cella, qualunque sia il separatore usato.

    Si cercano i valori ammessi come sottostringhe, dal più lungo al più corto
    (così "Sopralluogo congiunto" non conta anche come "Sopralluogo"). Il testo
    che resta, se non è solo punteggiatura, conta come "Altro" quando ammesso.
    """
    resto = chiave(cella)
    trovate = []
    for v in sorted(ammessi, key=len, reverse=True):
        k = chiave(v)
        schema = re.compile(r"(?<![\w])" + re.escape(k) + r"(?![\w])")
        if schema.search(resto):
            trovate.append(v)
            resto = schema.sub(" ", resto)
    if re.sub(r"[\W_]+", "", resto) and "Altro" in ammessi and "Altro" not in trovate:
        trovate.append("Altro")
    return [v for v in ammessi if v in trovate]
