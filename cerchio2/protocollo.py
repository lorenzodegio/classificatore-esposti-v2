"""Protocollo letto dal testo del documento (e, in mancanza, dal nome del file).

Deterministico, nessun modello. Formato del contratto: numero a 7 cifre e anno
("0005120/2025"), data ISO, frase letterale (al massimo 300 caratteri) e pagina.
L'anno non si inventa: si aggiunge solo se è scritto accanto al numero ("/2025")
o nella data che segue il numero ("Prot. n. 12345 del 08/04/2025", che è la data
del protocollo). Altrimenti il numero resta senza anno ("0012345") e la data è null.
Si prende la prima indicazione di protocollo nell'ordine delle pagine: in un
riscontro è di solito il riferimento all'esposto ("Rif. Prot. …"), che è proprio
quello che serve per il collegamento.
"""
import datetime as dt
import re

from cerchio1.ancora import tronca
from cerchio2.consegna import da_nome

CIFRE = 7
MESI = {m: i for i, m in enumerate(["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
                                    "agosto", "settembre", "ottobre", "novembre", "dicembre"], 1)}

PROTOCOLLO = re.compile(
    r"(?<![\w])prot(?:ocollo)?\b\.?\s*"
    r"(?:(?:n|nr|num|no)\b\.?\s*|n°\s*|nº\s*)?[:.]?\s*"
    r"(?P<numero>\d{3,7})(?:\s*/\s*(?P<anno>(?:19|20)\d{2}))?(?!\d)",
    re.IGNORECASE)
DATA_NUMERICA = r"(?P<g>\d{1,2})\s*[/.\-]\s*(?P<m>\d{1,2})\s*[/.\-]\s*(?P<a>(?:19|20)\d{2})"
DATA_ESTESA = r"(?P<g2>\d{1,2})\s*[°º]?\s+(?P<mese>" + "|".join(MESI) + r")\s+(?P<a2>(?:19|20)\d{2})"
DATA_DOPO = re.compile(r"\s*,?\s*(?:del\s+|dell['’]\s*|in\s+data\s+|data\s+)(?:" + DATA_NUMERICA + "|" + DATA_ESTESA + ")",
                       re.IGNORECASE)


def _data(g: str, m: str, a: str) -> dt.date | None:
    try:
        return dt.date(int(a), int(m), int(g))
    except ValueError:
        return None


def data_iso(testo: str) -> str | None:
    """"gg/mm/aaaa" (o con - e .) oppure "8 aprile 2025" -> "AAAA-MM-GG"; None se non è una data."""
    t = (testo or "").strip()
    m = re.fullmatch(DATA_NUMERICA, t) or re.fullmatch(DATA_ESTESA, t, re.IGNORECASE)
    if not m:
        return None
    d = m.groupdict()
    if d.get("g"):
        data = _data(d["g"], d["m"], d["a"])
    else:
        data = _data(d["g2"], str(MESI[d["mese"].lower()]), d["a2"])
    return data.isoformat() if data else None


def numero(cifre: str, anno: str | int | None) -> str:
    """7 cifre, più "/AAAA" solo se l'anno è noto con certezza."""
    n = cifre.lstrip("0").zfill(CIFRE)
    return f"{n}/{anno}" if anno else n


def dal_testo(pagine: list[dict]) -> dict | None:
    """{"numero", "data", "frase", "pagina"} della prima indicazione di protocollo, oppure None."""
    for p in pagine:
        testo = p.get("testo") or ""
        for m in PROTOCOLLO.finditer(testo):
            fine, data = m.end(), None
            dopo = DATA_DOPO.match(testo, m.end())
            if dopo:
                d = dopo.groupdict()
                data = (_data(d["g"], d["m"], d["a"]) if d.get("g")
                        else _data(d["g2"], str(MESI[d["mese"].lower()]), d["a2"]))
                fine = dopo.end()
            anno = m["anno"] or (data.year if data else None)
            return {"numero": numero(m["numero"], anno), "data": data.isoformat() if data else None,
                    "frase": tronca(testo[m.start():fine]), "pagina": p["n"]}
    return None


def dal_nome(nome_file: str) -> dict | None:
    """Ripiego: numero di protocollo dal nome del file (regole di cerchio2/consegna.py).

    Il nome dà il numero senza anno, e la data che vi compare non è con certezza
    quella del protocollo: il numero resta quindi SENZA anno ("0054321") e la data
    è null. La frase è il nome del file preceduto da "(nome del file)": non è testo
    del documento, e la pagina è convenzionalmente 1.
    """
    letti = da_nome(nome_file or "")
    if not letti["protocollo"]:
        return None
    return {"numero": numero(letti["protocollo"], None), "data": None,
            "frase": tronca(f"(nome del file) {nome_file}"), "pagina": 1}


def protocollo(pagine: list[dict], nome_file: str) -> dict | None:
    return dal_testo(pagine) or dal_nome(nome_file)
