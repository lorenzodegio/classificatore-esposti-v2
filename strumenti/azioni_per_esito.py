"""Azione più frequente degli operatori per ciascun esito, sulla sola metà di taratura.

Scrive config/azioni_per_esito.json (usato dalla decisione come valore di
partenza dell'Azione) e stampa solo conteggi aggregati. La metà di verifica
non si legge.

Uso: python strumenti/azioni_per_esito.py   (scrive in /work; si copia poi in config/)
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

from cerchio1.voci import carica_modulo, voci
from strumenti.confronto_merged import DIVISIONE, cella, righe_csv

USCITA = Path("/work/azioni_per_esito.json")


def main() -> None:
    modulo = carica_modulo()
    divisione = json.loads(DIVISIONE.read_text(encoding="utf-8"))
    righe = righe_csv()
    indici = sorted({divisione["righe"][d] for d in divisione["taratura"]})
    per_esito = defaultdict(Counter)
    for i in indici:
        esito = (voci(righe[i].get("Esito", ""), modulo["Esito"]["valori"]) or [""])[0]
        azioni = voci(righe[i].get("Azione", ""), modulo["Azione"]["valori"])
        if esito:
            per_esito[esito][" + ".join(azioni) or "(nessuna)"] += 1
    scelta = {}
    for esito, c in per_esito.items():
        prima, n = c.most_common(1)[0]
        scelta[esito] = [] if prima == "(nessuna)" else prima.split(" + ")
        print(f"{esito}: {cella(sum(c.values()))} righe; azione più frequente «{prima}» ({cella(n)})")
    USCITA.write_text(json.dumps(scelta, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
