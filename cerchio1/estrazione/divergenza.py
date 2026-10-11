"""Divergenza fra due letture della stessa pagina (segnale di lettura incerta).

Il confronto è a livello di parole e ignora spaziatura e a capo. Nessun
contenuto viene stampato o registrato: esce solo la percentuale.
"""
import re
import unicodedata


def normalizza(testo: str) -> str:
    testo = unicodedata.normalize("NFC", testo)
    testo = testo.replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", testo).strip()


def levenshtein(a, b) -> int:
    if len(a) < len(b):
        a, b = b, a
    precedente = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        corrente = [i]
        for j, cb in enumerate(b, 1):
            corrente.append(min(precedente[j] + 1, corrente[j - 1] + 1,
                                precedente[j - 1] + (ca != cb)))
        precedente = corrente
    return precedente[-1]


def divergenza_pct(a: str, b: str) -> float:
    """Parole da cambiare per passare da una lettura all'altra, in % della lunghezza media."""
    pa, pb = normalizza(a).split(), normalizza(b).split()
    return round(100 * levenshtein(pa, pb) / max((len(pa) + len(pb)) / 2, 1), 1)
