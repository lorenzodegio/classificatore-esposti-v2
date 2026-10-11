"""Forma dei nomi dei file, solo aggregata (per progettare il parser del protocollo).

Ogni nome diventa una sagoma: le lettere diventano "a", i gruppi di cifre
"9{n}" con la loro lunghezza, la punteggiatura resta. Si stampano solo le
sagome che compaiono almeno MIN volte, con il conteggio. Nessun nome esce.
"""
import os
import re
from collections import Counter

CARTELLA = "/data/esposti"
MIN = 5


def sagoma(nome: str) -> str:
    base, ext = os.path.splitext(nome)
    s = re.sub(r"[^\W\d_]+", "a", base)          # parole -> a
    s = re.sub(r"\d+", lambda m: f"9{{{len(m.group())}}}", s)
    s = re.sub(r"\s+", " ", s)
    return s + ext.lower()


def main():
    nomi = [f for _, _, fs in os.walk(CARTELLA) for f in fs if not f.lower().endswith(".csv")]
    forme = Counter(sagoma(n) for n in nomi)
    lunghezze = Counter(len(m) for n in nomi for m in re.findall(r"\d+", os.path.splitext(n)[0]))
    print(f"file: {len(nomi)}; sagome distinte: {len(forme)}")
    coperti = 0
    for f, n in forme.most_common():
        if n >= MIN:
            coperti += n
            print(f"{n:5d}  {f}")
    print(f"coperti dalle sagome mostrate: {coperti}")
    print("lunghezze dei gruppi di cifre (>= 5 occorrenze):",
          {k: v for k, v in sorted(lunghezze.items()) if v >= MIN})


if __name__ == "__main__":
    main()
