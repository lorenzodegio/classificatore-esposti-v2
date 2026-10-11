"""Confronto con la classificazione manuale ATS (merged.csv). Stampa solo aggregati.

Uso (container senza rete, con documenti, /work e merged.csv in sola lettura):
    python strumenti/confronto_merged.py protocolli   # verifica del parser sui nomi
    python strumenti/confronto_merged.py dividi       # associazione + metà taratura/verifica
    python strumenti/confronto_merged.py taratura     # accordo sulla sola metà di taratura

La metà di verifica non si usa per nessun confronto: `taratura` legge solo le
righe associate ai documenti della metà di taratura. Celle sotto 5 come "<5".
"""
import csv
import hashlib
import io
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from cerchio1.estrazione.estrai import sha256
from cerchio1.voci import carica_modulo, voci
from cerchio2.consegna import da_nome

CSV = Path("/dati/merged.csv")
DOCUMENTI = Path("/data/esposti")
ESTENSIONI = {".pdf", ".docx", ".doc", ".rtf"}
CONFRONTO = Path("/work/confronto")
DIVISIONE = CONFRONTO / "divisione.json"
ELABORATI = [Path("/work/prototipo/campione_20_seme42/documenti"),
             Path("/work/prototipo/taratura/documenti")]  # l'ultima vince
SEME = 42
MIN_CELLA = 5
CAMPI = {  # colonna merged.csv -> (sezione dell'uscita, chiave)
    "Ambito": ("scheda", "ambito"),
    "Problematica": ("scheda", "problematica"),
    "Elementi": ("scheda", "elementi"),
    "Esito": ("decisione", "esito"),
    "Urgenza": ("decisione", "urgenza"),
    "Azione": ("decisione", "azione"),
}
RISCONTRO_NEL_NOME = re.compile(r"riscontr|rispost|esito|nota\s*ats|comunicaz", re.I)


def cella(n: int) -> str:
    return "<5" if 0 < n < MIN_CELLA else str(n)


def norm_nome(nome: str) -> str:
    return " ".join(Path(nome).stem.lower().split())


def norm_prot(valore: str) -> str:
    m = re.search(r"(?<!\d)\d{5,7}(?!\d)", re.sub(r"(?<!\d)\d{1,2}[-./]\d{1,2}[-./]\d{4}(?!\d)", " ", valore or ""))
    return (m.group().lstrip("0") or "0") if m else ""


def norm_val(v) -> str:
    return " ".join(str(v or "").split()).casefold()


def righe_csv() -> list[dict]:
    testo = CSV.read_bytes().decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(testo)))


def file_documenti() -> list[Path]:
    return sorted(p for p in DOCUMENTI.rglob("*") if p.is_file() and p.suffix.lower() in ESTENSIONI)


def protocolli() -> None:
    file = file_documenti()
    prot = {f: da_nome(f.name)["protocollo"] for f in file}
    con = [f for f in file if prot[f]]
    gruppi = defaultdict(set)
    for f in con:
        gruppi[prot[f]].add(sha256(f))  # documenti distinti, non copie identiche
    multipli = {p: g for p, g in gruppi.items() if len(g) > 1}
    tipo_nome = {f: "riscontro" if RISCONTRO_NEL_NOME.search(f.stem) else "altro" for f in con}
    coppie = 0
    for p in multipli:
        tipi = Counter(tipo_nome[f] for f in con if prot[f] == p)
        coppie += min(tipi["riscontro"], tipi["altro"])
    print(f"file: {len(file)}; con protocollo dal nome: {len(con)}; senza: {cella(len(file) - len(con))}")
    print(f"protocolli distinti: {len(gruppi)}; presenti in più di un documento distinto: {len(multipli)}")
    print(f"documenti nei protocolli condivisi: {sum(len(g) for g in multipli.values())}")
    print(f"coppie esposto-riscontro (riscontro riconosciuto da parole nel nome): {cella(coppie)}")


def associa(righe: list[dict]):
    """Per ogni documento distinto: la riga di merged.csv (prima per nome, poi per protocollo)."""
    per_nome = defaultdict(list)
    per_prot = defaultdict(list)
    for i, r in enumerate(righe):
        per_nome[norm_nome(r.get("File", ""))].append(i)
        if norm_prot(r.get("Protocollo", "")):
            per_prot[norm_prot(r["Protocollo"])].append(i)
    documenti, metodo = {}, Counter()
    for f in file_documenti():
        d = sha256(f)[:16]
        if d in documenti and documenti[d]["riga"] is not None:
            continue
        prot = da_nome(f.name)["protocollo"]
        if per_nome.get(norm_nome(f.name)):
            riga, m = per_nome[norm_nome(f.name)][0], "nome"
        elif prot and per_prot.get(prot):
            riga, m = per_prot[prot][0], "protocollo"
        else:
            riga, m = None, "nessuna"
        documenti[d] = {"riga": riga, "protocollo": prot or (norm_prot(righe[riga].get("Protocollo", "")) if riga is not None else ""), "metodo": m}
    for d in documenti.values():
        metodo[d["metodo"]] += 1
    righe_usate = {d["riga"] for d in documenti.values() if d["riga"] is not None}
    return documenti, metodo, len(righe) - len(righe_usate)


def dividi() -> None:
    righe = righe_csv()
    documenti, metodo, righe_libere = associa(righe)
    associati = {d: v for d, v in documenti.items() if v["riga"] is not None}
    print(f"documenti distinti: {len(documenti)}; associati a una riga: {len(associati)} "
          f"(per nome {metodo['nome']}, per protocollo {metodo['protocollo']}); non associati {metodo['nessuna']}")
    print(f"righe di merged.csv: {len(righe)}; senza documento associato: {cella(righe_libere)}")
    gruppi = defaultdict(list)
    for d, v in associati.items():
        gruppi[v["protocollo"] or f"senza:{d}"].append(d)
    chiavi = sorted(gruppi)
    random.Random(SEME).shuffle(chiavi)
    meta = {"taratura": [], "verifica": []}
    for k in chiavi:  # stesso protocollo nella stessa metà; metà bilanciate per numero di documenti
        verso = "taratura" if len(meta["taratura"]) <= len(meta["verifica"]) else "verifica"
        meta[verso].extend(gruppi[k])
    divisione = {"seme": SEME, "taratura": sorted(meta["taratura"]), "verifica": sorted(meta["verifica"]),
                 "righe": {d: associati[d]["riga"] for d in associati}}
    CONFRONTO.mkdir(parents=True, exist_ok=True)
    testo = json.dumps(divisione, sort_keys=True)
    DIVISIONE.write_text(testo, encoding="utf-8")
    print(f"taratura: {len(meta['taratura'])} documenti; verifica: {len(meta['verifica'])} documenti; "
          f"gruppi per protocollo: {len(chiavi)}")
    print(f"hash della divisione (sha256): {hashlib.sha256(testo.encode()).hexdigest()[:16]}")


def tabella_incrociata(coppie: list[tuple[str, str]]) -> list[str]:
    op = sorted({a for a, _ in coppie})
    noi = sorted({b for _, b in coppie})
    conta = Counter(coppie)
    righe = ["| operatori \\ prototipo | " + " | ".join(noi) + " |", "|---" * (len(noi) + 1) + "|"]
    for a in op:
        righe.append(f"| {a} | " + " | ".join(cella(conta[(a, b)]) if conta[(a, b)] else "" for b in noi) + " |")
    return righe


def _prototipo(d: dict, sez: str, chiave: str, ammessi: list[str]) -> list[str]:
    sezione = d.get(sez) or {}
    if sez == "decisione" and not sezione.get("classificato"):
        return ["(non classificato)"]
    v = sezione.get(chiave)
    return voci("; ".join(v) if isinstance(v, list) else (v or ""), ammessi)


def voci_operatori(cella_csv: str, col: str, modulo: dict) -> list[str]:
    """Voci degli operatori; per l'Ambito si riportano ai valori usati dal prototipo."""
    if col != "Ambito":
        return voci(cella_csv, modulo[col]["valori"])
    csv_ = modulo["Ambito_csv"]
    mappate = [csv_["corrispondenza"].get(v, v) for v in voci(cella_csv, csv_["valori"])]
    return [v for v in modulo["Ambito"]["valori"] if v in mappate]


GRUPPI_TIPO = {"esposti e richieste di ente": {"esposto", "richiesta ente"}}
RIFERIMENTI = {"Esito": "Accolto", "Urgenza": "Normale"}  # "sempre X" come termine di paragone


def _gruppo(d: dict) -> str:
    tipo = (d.get("scheda") or {}).get("tipo_documento", "")
    for nome, tipi in GRUPPI_TIPO.items():
        if tipo in tipi:
            return nome
    return "riscontri, lettere e altro"


def _riporta(titolo: str, elaborati: dict, righe: list, divisione: dict, modulo: dict) -> None:
    print(f"\n## {titolo}: {len(elaborati)} documenti")
    if not elaborati:
        return
    for col, (sez, chiave) in CAMPI.items():
        ammessi = modulo[col]["valori"]
        coppie = []
        for d_id, d in elaborati.items():
            op = voci_operatori(righe[divisione["righe"][d_id]].get(col, ""), col, modulo)
            if op:
                coppie.append((op, _prototipo(d, sez, chiave, ammessi + ["(non classificato)"])))
        n = len(coppie)
        print(f"\n### {col} ({'scelta multipla' if modulo[col]['multipla'] else 'scelta singola'}): "
              f"{n} documenti con valore degli operatori")
        if not n:
            continue
        if not modulo[col]["multipla"]:
            accordo = sum(p[:1] == o[:1] for o, p in coppie)
            riga = f"accordo prototipo: {100 * accordo / n:.0f}%"
            if col in RIFERIMENTI:
                rif = sum(o[0] == RIFERIMENTI[col] for o, _ in coppie)
                riga += f"; riferimento «sempre {RIFERIMENTI[col]}»: {100 * rif / n:.0f}%"
            print(riga)
            print("\n".join(tabella_incrociata([(o[0], p[0] if p else "(vuoto)") for o, p in coppie])))
            continue
        print("| voce | entrambi | solo operatori | solo prototipo | accordo sulla voce |")
        print("|---|---|---|---|---|")
        for v in ammessi:
            ent = sum(v in o and v in p for o, p in coppie)
            so = sum(v in o and v not in p for o, p in coppie)
            sp = sum(v not in o and v in p for o, p in coppie)
            if ent or so or sp:
                print(f"| {v} | {cella(ent)} | {cella(so)} | {cella(sp)} | {100 * (n - so - sp) / n:.0f}% |")


TRE_CLASSI = {"Accolto": "Accolto", "Invio Modulo": "Invio Modulo",
              "Archiviato": "non si procede", "Altro": "non si procede"}


def _tre_classi(titolo: str, docs: dict, righe: list, divisione: dict, modulo: dict) -> None:
    """Esito in tre classi (Accolto / Invio Modulo / non si procede) e concordanza sui non accolti."""
    ammessi = modulo["Esito"]["valori"]
    coppie = []
    for d_id, d in docs.items():
        op = (voci(righe[divisione["righe"][d_id]].get("Esito", ""), ammessi) or [""])[0]
        pr = (_prototipo(d, "decisione", "esito", ammessi) or [""])[0]
        coppie.append((op, pr))
    in_tre = [(TRE_CLASSI[o], TRE_CLASSI.get(p, p or "(vuoto)")) for o, p in coppie if o in TRE_CLASSI]
    n = len(in_tre)
    print(f"\n### {titolo}: esito in tre classi ({n} documenti con esito operatori in una delle tre)")
    if n:
        acc = sum(o == p for o, p in in_tre)
        rif = sum(o == "Accolto" for o, _ in in_tre)
        print(f"accordo prototipo: {100 * acc / n:.0f}%; riferimento «sempre Accolto»: {100 * rif / n:.0f}%")
        print("\n".join(tabella_incrociata(in_tre)))
    non_acc = [(o, p) for o, p in coppie if p and p != "Accolto" and o]
    concordi = sum(o != "Accolto" for o, _ in non_acc)
    print(f"documenti NON accolti dal prototipo (con esito operatori): {len(non_acc)}; "
          f"di questi non accolti nemmeno dagli operatori: {concordi}"
          + (f" ({100 * concordi / len(non_acc):.0f}%)" if non_acc else ""))


def misura(meta: str, cartella: Path) -> None:
    """Confronto completo sui documenti di UNA metà, letti da UNA cartella di uscite."""
    divisione = json.loads(DIVISIONE.read_text(encoding="utf-8"))
    ids = set(divisione[meta])
    righe = righe_csv()
    modulo = carica_modulo()
    elaborati = {}
    for f in cartella.glob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        if d["doc_id"] in ids:  # solo la metà richiesta
            elaborati[d["doc_id"]] = d
    print(f"metà {meta}: {len(ids)} documenti; elaborati dal prototipo: {len(elaborati)} ({cartella})")

    ammessi_esito = modulo["Esito"]["valori"]
    gruppi = defaultdict(dict)
    for d_id, d in elaborati.items():
        gruppi[_gruppo(d)][d_id] = d
    print("\n### Distribuzione degli esiti (documenti elaborati)")
    print("| gruppo | esito | operatori | prototipo |")
    print("|---|---|---|---|")
    for g, docs in gruppi.items():
        op = Counter((voci(righe[divisione["righe"][d]].get("Esito", ""), ammessi_esito) or ["(vuoto)"])[0]
                     for d in docs)
        pr = Counter((_prototipo(d, "decisione", "esito", ammessi_esito + ["(non classificato)"])
                      or ["(vuoto)"])[0] for d in docs.values())
        for e in [*ammessi_esito, "(non classificato)", "(vuoto)"]:
            if op[e] or pr[e]:
                print(f"| {g} | {e} | {cella(op[e])} | {cella(pr[e])} |")
    for g in [*GRUPPI_TIPO, "riscontri, lettere e altro"]:
        _tre_classi(g, gruppi.get(g, {}), righe, divisione, modulo)
    for g in [*GRUPPI_TIPO, "riscontri, lettere e altro"]:
        _riporta(g, gruppi.get(g, {}), righe, divisione, modulo)
    determinanti = Counter((d.get("decisione") or {}).get("determinante", "-") for d in elaborati.values())
    print("\ndomanda determinante (tutti gli elaborati):",
          ", ".join(f"{k} {cella(v)}" for k, v in sorted(determinanti.items())))


if __name__ == "__main__":
    if sys.argv[1] == "misura":  # misura META CARTELLA_USCITE
        misura(sys.argv[2], Path(sys.argv[3]))
    else:
        {"protocolli": protocolli, "dividi": dividi}[sys.argv[1]]()
