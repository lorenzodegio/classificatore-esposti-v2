"""Controllo prima della pubblicazione: il repository contiene dati reali?

Confronta i file di testo del repository con: nomi dei documenti reali,
protocolli (dai nomi e da merged.csv), identificativi/hash dei documenti, e
valori liberi di merged.csv (colonne non del modulo). Stampa SOLO conteggi e
percorsi dei file del repository: mai le corrispondenze trovate.

Uso (container senza rete; documenti, merged.csv e /work in sola lettura):
    python strumenti/controllo_pubblicazione.py
"""
import csv
import io
import json
import re
from collections import defaultdict
from pathlib import Path

REPO = Path("/app")
DOCUMENTI = Path("/data/esposti")
CSV = Path("/dati/merged.csv")
INDICE = Path("/work/indice_locale.json")
TESTO = {".py", ".md", ".toml", ".json", ".txt", ".yml", ".yaml", ".ini", ".cfg", ""}
ESCLUSI = {".git", "__pycache__", ".pytest_cache"}
COLONNE_LIBERE = ["File", "Protocollo", "Operatore", "Note", "Ambito altro", "Prob altro", "Elementi altro"]
LUNGHEZZA_MIN = 6   # valori più corti producono solo falsi allarmi


def norm(s: str) -> str:
    return " ".join(s.casefold().split())


def file_repo() -> list[Path]:
    return [p for p in REPO.rglob("*") if p.is_file() and not ESCLUSI & set(p.parts)
            and (p.suffix.lower() in TESTO or p.name in {"Dockerfile", ".gitignore"})]


def main() -> None:
    nomi = [p for p in DOCUMENTI.rglob("*") if p.is_file()]
    steli = {norm(p.stem) for p in nomi if len(p.stem) >= LUNGHEZZA_MIN}
    protocolli = set()
    for p in nomi:
        protocolli |= {m.lstrip("0") for m in re.findall(r"(?<!\d)\d{5,7}(?!\d)", p.stem)}
    righe = list(csv.DictReader(io.StringIO(CSV.read_bytes().decode("utf-8-sig"))))
    valori_liberi, comuni = set(), set()
    for r in righe:
        for c in COLONNE_LIBERE:
            v = norm(r.get(c) or "")
            if len(v) >= LUNGHEZZA_MIN:
                valori_liberi.add(v)
        protocolli |= {m.lstrip("0") for m in re.findall(r"(?<!\d)\d{5,7}(?!\d)", r.get("Protocollo") or "")}
        if (r.get("Comune") or "").strip():
            comuni.add(norm(r["Comune"]))
    identificativi = set(json.loads(INDICE.read_text(encoding="utf-8"))) if INDICE.exists() else set()

    trovati = defaultdict(lambda: defaultdict(int))
    for f in file_repo():
        rel = str(f.relative_to(REPO))
        testo = f.read_text(encoding="utf-8", errors="ignore")
        basso = norm(testo)
        for s in steli:
            if s in basso:
                trovati["nomi di documenti reali"][rel] += 1
        for m in re.findall(r"(?<!\d)\d{5,7}(?!\d)", testo):
            if m.lstrip("0") in protocolli:
                trovati["protocolli reali"][rel] += 1
        for m in re.findall(r"(?<![0-9a-f])[0-9a-f]{16}(?![0-9a-f])", testo):
            if m in identificativi:
                trovati["identificativi di documenti reali"][rel] += 1
        for v in valori_liberi:
            if v in basso:
                trovati["valori liberi di merged.csv"][rel] += 1
        for c in comuni:
            if re.search(r"(?<!\w)" + re.escape(c) + r"(?!\w)", basso):
                trovati["nomi di comuni presenti in merged.csv (informativo)"][rel] += 1

    print(f"file di testo controllati: {len(file_repo())}")
    print(f"riferimenti: {len(steli)} nomi, {len(protocolli)} protocolli, {len(identificativi)} identificativi, "
          f"{len(valori_liberi)} valori liberi, {len(comuni)} comuni")
    for categoria in ["nomi di documenti reali", "protocolli reali", "identificativi di documenti reali",
                      "valori liberi di merged.csv", "nomi di comuni presenti in merged.csv (informativo)"]:
        per_file = trovati.get(categoria, {})
        print(f"\n{categoria}: {sum(per_file.values())} corrispondenze in {len(per_file)} file")
        for rel, n in sorted(per_file.items()):
            print(f"  {rel}: {n}")


if __name__ == "__main__":
    main()
