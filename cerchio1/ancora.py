"""Ancoraggio di una frase al testo per pagina: dove si trova, e com'è scritta alla lettera.

Le frasi che l'LLM riporta come giustificazione possono differire dal testo per
spazi, a capo o qualche carattere. Qui si cerca la frase nelle pagine (prima
uguale a meno di spazi e maiuscole, poi la finestra di parole più simile) e si
restituisce il tratto LETTERALE del documento con il numero di pagina.
Deterministico, nessun modello. Nessun contenuto viene stampato.
"""
import re
import unicodedata
from difflib import SequenceMatcher

FRASE_MAX = 300          # limite del contratto (caratteri)
SOMIGLIANZA_MIN = 0.75   # sotto, la frase non si considera ritrovata nel testo


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s).replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", s).strip().casefold()


def tronca(frase: str, massimo: int = FRASE_MAX) -> str:
    """Spazi uniformi e al massimo `massimo` caratteri, tagliando a fine parola."""
    f = re.sub(r"\s+", " ", frase or "").strip()
    if len(f) <= massimo:
        return f
    taglio = f[:massimo]
    spazio = taglio.rfind(" ")
    return (taglio[:spazio] if spazio > massimo // 2 else taglio).rstrip(" ,;:")


def _parole(testo: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in re.finditer(r"\S+", testo)]


ELLISSI = re.compile(r"\s*(?:\.\.\.+|…)\s*")


def ancora(frase: str, pagine: list[dict]) -> tuple[str, int] | None:
    """(frase letterale del documento, pagina) oppure None se la frase è vuota.

    `pagine`: [{"n": int, "testo": str}]. Se la frase contiene puntini ("…",
    che l'LLM usa per accorciare) si prova prima il tratto più lungo fra quelli
    separati dai puntini. Se la frase non si ritrova con somiglianza sufficiente
    si tiene così com'è, sulla pagina più simile.
    """
    if ELLISSI.search(frase or ""):
        parti = sorted((p for p in ELLISSI.split(frase) if len(p.split()) >= 3), key=len, reverse=True)
        if parti:
            posto, ritrovata = _cerca(parti[0], pagine)
            if ritrovata:
                return posto
    return _cerca(frase, pagine)[0]


def _cerca(frase: str, pagine: list[dict]) -> tuple[tuple[str, int] | None, bool]:
    """(posto, ritrovata nel testo)."""
    cercata = _norm(frase)
    if not cercata:
        return None, False
    migliore = (0.0, None, pagine[0]["n"] if pagine else 1)
    n_cercata = len(cercata.split())
    confronto = SequenceMatcher(None, autojunk=False)
    confronto.set_seq2(cercata)  # la sequenza fissa è quella che SequenceMatcher indicizza
    for p in pagine:
        testo = p.get("testo") or ""
        parole = _parole(testo)
        if not parole:
            continue
        piatto = " ".join(testo[a:b] for a, b in parole)
        if cercata in _norm(piatto):
            # Ricostruisce il tratto letterale: finestra di parole che normalizzata coincide.
            # Si sceglie la finestra più corta che la contiene.
            candidati = []
            for i in range(len(parole)):
                for j in range(max(i, i + n_cercata - 2), min(len(parole), i + n_cercata + 2)):
                    tratto = testo[parole[i][0]:parole[j][1]]
                    if cercata in _norm(tratto):
                        candidati.append(tratto)
                        break
            if candidati:
                return (tronca(min(candidati, key=len)), p["n"]), True
            return (tronca(frase), p["n"]), True
        # Finestra di parole più simile (stessa lunghezza della frase cercata).
        for i in range(0, max(1, len(parole) - n_cercata + 1)):
            j = min(len(parole), i + n_cercata) - 1
            tratto = testo[parole[i][0]:parole[j][1]]
            confronto.set_seq1(_norm(tratto))
            if confronto.quick_ratio() <= migliore[0]:
                continue
            r = confronto.ratio()
            if r > migliore[0]:
                migliore = (r, tratto, p["n"])
    r, tratto, n = migliore
    if tratto is not None and r >= SOMIGLIANZA_MIN:
        return (tronca(tratto), n), True
    return (tronca(frase), n), False
