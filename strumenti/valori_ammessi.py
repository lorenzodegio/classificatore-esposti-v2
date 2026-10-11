"""Valori ammessi dei campi della scheda, ricavati da merged.csv.

Legge SOLO le colonne autorizzate e tiene SOLO i valori che compaiono almeno
MIN_OCCORRENZE volte. Non stampa righe né altre colonne: scrive l'elenco dei
valori in /work/valori_ammessi.json e stampa solo quanti valori per colonna.
Le celle con più valori separati da VIRGOLA_MULTI si contano separatamente.
"""
import csv
import io
import json
import sys
from collections import Counter

CSV = "/dati/merged.csv"
USCITA = "/work/valori_ammessi.json"
COLONNE = ["Ambito", "Problematica", "Esito", "Urgenza", "Azione", "Elementi"]
MIN_OCCORRENZE = 5
SEPARATORI_MULTI = (";", "|")


def apri():
    grezzo = open(CSV, "rb").read()
    for cod in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            testo = grezzo.decode(cod)
            break
        except UnicodeDecodeError:
            continue
    dialetto = csv.Sniffer().sniff(testo[:20000], delimiters=",;\t|")
    return csv.DictReader(io.StringIO(testo), dialect=dialetto)


def main():
    lettore = apri()
    intestazione = {c.strip().lower(): c for c in lettore.fieldnames or []}
    mancanti = [c for c in COLONNE if c.lower() not in intestazione]
    if mancanti:
        # solo i nomi delle colonne, mai i valori
        sys.exit(f"Colonne non trovate: {mancanti}. Intestazioni presenti: {list(intestazione.values())}")
    conteggi = {c: Counter() for c in COLONNE}
    for riga in lettore:
        for c in COLONNE:
            cella = (riga.get(intestazione[c.lower()]) or "").strip()
            if not cella:
                continue
            parti = [cella]
            for sep in SEPARATORI_MULTI:
                parti = [p for x in parti for p in x.split(sep)]
            for p in parti:
                p = " ".join(p.split())
                if p:
                    conteggi[c][p] += 1
    valori = {c: sorted(v for v, n in conteggi[c].items() if n >= MIN_OCCORRENZE) for c in COLONNE}
    with open(USCITA, "w", encoding="utf-8") as f:
        json.dump(valori, f, ensure_ascii=False, indent=1)
    for c in COLONNE:
        print(f"{c}: {len(valori[c])} valori con almeno {MIN_OCCORRENZE} occorrenze")


if __name__ == "__main__":
    main()
