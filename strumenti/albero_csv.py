"""Albero di decisione piccolo sul solo CSV, metà di taratura (nessun testo, nessuna GPU).

Prevede Esito e Urgenza degli operatori dai loro stessi campi Ambito,
Problematica ed Elementi (una variabile sì/no per voce). Convalida incrociata
a gruppi di protocollo. Stampa solo aggregati; celle sotto 5 come "<5".
La metà di verifica non si legge.

Uso: python strumenti/albero_csv.py
"""
import json
import random
from collections import Counter, defaultdict

from cerchio1.voci import carica_modulo, voci
from strumenti.confronto_merged import DIVISIONE, cella, norm_prot, righe_csv, tabella_incrociata

PROFONDITA = 3
FOGLIA_MIN = 5      # anche per non creare regole su meno di 5 casi
PIEGHE = 5
SEME = 42
INGRESSI = ["Ambito", "Problematica", "Elementi"]
OBIETTIVI = ["Esito", "Urgenza"]


def gini(etichette) -> float:
    n = len(etichette)
    return 1 - sum((c / n) ** 2 for c in Counter(etichette).values()) if n else 0


def costruisci(X, y, profondita):
    maggioranza = Counter(y).most_common(1)[0][0]
    nodo = {"classe": maggioranza, "n": len(y), "conta": Counter(y)}
    if profondita == 0 or len(set(y)) == 1:
        return nodo
    migliore = None
    for f in X[0]:
        si = [i for i, x in enumerate(X) if x[f]]
        no = [i for i, x in enumerate(X) if not x[f]]
        if len(si) < FOGLIA_MIN or len(no) < FOGLIA_MIN:
            continue
        impurita = (len(si) * gini([y[i] for i in si]) + len(no) * gini([y[i] for i in no])) / len(y)
        if migliore is None or impurita < migliore[0]:
            migliore = (impurita, f, si, no)
    if migliore is None or migliore[0] >= gini(y):
        return nodo
    _, f, si, no = migliore
    nodo["variabile"] = f
    nodo["si"] = costruisci([X[i] for i in si], [y[i] for i in si], profondita - 1)
    nodo["no"] = costruisci([X[i] for i in no], [y[i] for i in no], profondita - 1)
    return nodo


def prevedi(nodo, x):
    while "variabile" in nodo:
        nodo = nodo["si"] if x[nodo["variabile"]] else nodo["no"]
    return nodo["classe"]


def regole(nodo, condizioni=()) -> list[str]:
    if "variabile" not in nodo:
        se = " e ".join(condizioni) or "sempre"
        dettaglio = ", ".join(f"{k} {cella(v)}" for k, v in nodo["conta"].most_common())
        return [f"- se {se} → {nodo['classe']} (casi: {dettaglio})"]
    f = nodo["variabile"]
    return (regole(nodo["si"], (*condizioni, f"c'è «{f}»"))
            + regole(nodo["no"], (*condizioni, f"non c'è «{f}»")))


def main() -> None:
    modulo = carica_modulo()
    divisione = json.loads(DIVISIONE.read_text(encoding="utf-8"))
    righe = righe_csv()
    indici = sorted({divisione["righe"][d] for d in divisione["taratura"]})  # righe distinte
    print(f"righe di merged.csv nella metà di taratura: {len(indici)}")

    variabili = [f"{c}: {v}" for c in INGRESSI for v in modulo["Ambito_csv" if c == "Ambito" else c]["valori"]]
    dati = []
    for i in indici:
        r = righe[i]
        presenti = {f"{c}: {v}" for c in INGRESSI for v in voci(r.get(c, ""), modulo["Ambito_csv" if c == "Ambito" else c]["valori"])}
        obiettivi = {o: (voci(r.get(o, ""), modulo[o]["valori"]) or [""])[0] for o in OBIETTIVI}
        gruppo = norm_prot(r.get("Protocollo", "")) or f"riga{i}"
        dati.append(({v: v in presenti for v in variabili}, obiettivi, gruppo, r.get("Operatore", "")))

    gruppi = sorted({g for _, _, g, _ in dati})
    random.Random(SEME).shuffle(gruppi)
    piega = {g: k % PIEGHE for k, g in enumerate(gruppi)}

    for o in OBIETTIVI:
        validi = [(x, t[o], g) for x, t, g, _ in dati if t[o]]
        classi = Counter(t for _, t, _ in validi)
        base = classi.most_common(1)[0]
        print(f"\n## {o}: {len(validi)} righe con valore")
        print(f"riferimento «sempre {base[0]}»: accordo {100 * base[1] / len(validi):.0f}%")
        coppie = []
        for k in range(PIEGHE):
            allena = [(x, t) for x, t, g in validi if piega[g] != k]
            prova = [(x, t) for x, t, g in validi if piega[g] == k]
            albero = costruisci([x for x, _ in allena], [t for _, t in allena], PROFONDITA)
            coppie += [(t, prevedi(albero, x)) for x, t in prova]
        print(f"albero (profondità ≤ {PROFONDITA}, convalida a {PIEGHE} pieghe per protocollo): "
              f"accordo {100 * sum(a == b for a, b in coppie) / len(coppie):.0f}%")
        print("\n".join(tabella_incrociata(coppie)))
        albero = costruisci([x for x, _, _ in validi], [t for _, t, _ in validi], PROFONDITA)
        print("Regole (albero allenato su tutta la taratura):")
        print("\n".join(regole(albero)))

    # Variabilità tra operatori: senza nomi, solo chi ha almeno 5 righe.
    per_op = defaultdict(Counter)
    for _, t, _, op in dati:
        per_op[op.strip() or "(vuoto)"][t["Esito"] or "(vuoto)"] += 1
    ordinati = sorted(per_op.items(), key=lambda kv: -sum(kv[1].values()))
    esiti = modulo["Esito"]["valori"] + ["(vuoto)"]
    print("\n## Esito per operatore (anonimo; solo chi ha almeno 5 righe)")
    print("| operatore | righe | " + " | ".join(esiti) + " | % Accolto |")
    print("|---" * (len(esiti) + 3) + "|")
    piccoli = 0
    for k, (op, c) in enumerate(ordinati, 1):
        n = sum(c.values())
        if n < FOGLIA_MIN:
            piccoli += n
            continue
        print(f"| operatore {k} | {n} | " + " | ".join(cella(c[e]) for e in esiti)
              + f" | {100 * c['Accolto'] / n:.0f}% |")
    print(f"righe di operatori con meno di 5 righe: {cella(piccoli)}")


if __name__ == "__main__":
    main()
