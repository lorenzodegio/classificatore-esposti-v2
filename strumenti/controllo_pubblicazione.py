"""Controllo prima della pubblicazione: il repository contiene dati reali?

Confronta i file di testo del repository con: nomi dei documenti reali,
protocolli (dai nomi e da merged.csv), identificativi/hash dei documenti, e
valori liberi di merged.csv (colonne non del modulo). Stampa SOLO conteggi e
percorsi dei file del repository: mai le corrispondenze trovate.

Uso (container senza rete; documenti, merged.csv e /work in sola lettura):
    python strumenti/controllo_pubblicazione.py

Non si segnalano: le parole comuni di PAROLE_COMUNI_IGNORATE (verificate da
Lorenzo) e le occorrenze dentro un digest o un hash esadecimale. Per nomi e
valori liberi stampa anche quante corrispondenze non sono spiegate dal
vocabolario del modulo; alla fine "esito: pulito" se non ci sono protocolli o
identificativi reali né corrispondenze non spiegate.

Opzione --dettaglio [FILE] (default /work/corrispondenze.txt, cioè
/home/lorenzo/sire_lavoro/corrispondenze.txt sulla workstation): per ogni
corrispondenza con i valori liberi di merged.csv o con i nomi dei documenti (una
per file e valore, come il conteggio) scrive nel file, una per riga separata da
tabulazioni: file del repository, numero di riga, testo che coincide, colonne di
merged.csv in cui compare (o "nome di un documento"), e se è spiegata dal
vocabolario (voci del modulo ATS, temi, tipi di
documento, poche parole generiche); prima le non spiegate. Il file contiene
dati reali: resta sulla workstation e non si stampa. Sullo schermo escono solo
il percorso del file e il numero di righe scritte. Va montato in scrittura solo
quel file (creato prima, permessi 600); /work resta in sola lettura:
    -v /home/lorenzo/sire_lavoro/corrispondenze.txt:/work/corrispondenze.txt
"""
import argparse
import csv
import io
import json
import re
import tomllib
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
DETTAGLIO_PREDEFINITO = "/work/corrispondenze.txt"
# Vocabolario che "spiega" una corrispondenza: un'occorrenza interamente dentro una di queste voci
# non è un dato reale ma un'etichetta del modulo (le definizioni dei temi sono testo libero: escluse).
VOCABOLARIO_TOML = [REPO / "config" / "scheda_ats.toml", REPO / "config" / "temi.toml"]
TIPI_DOCUMENTO = ["esposto", "inoltro_per_competenza", "richiesta_ente", "riscontro_ats", "lettera_avvocato",
                  "integrazione", "altro", "inoltro per competenza", "richiesta ente", "riscontro ATS",
                  "lettera avvocato"]
PAROLE_GENERICHE = ["esposto", "esposti", "riscontro", "segnalazione", "segnalante", "sopralluogo",
                    "documento", "protocollo", "competenza", "richiesta"]
# Valori di merged.csv che sono parole comuni, non dati personali: verificati da Lorenzo il 22/10/2026
# (con --dettaglio). Non si cercano affatto.
PAROLE_COMUNI_IGNORATE = ["veterinario", "veterinari", "privato", "non di competenza", "avvelenamento",
                          "uccisione", "varese", "richiesta intervento"]
# Un'occorrenza dentro un digest o un hash (sequenza esadecimale di almeno 8 caratteri con lettere e
# cifre, per esempio i digest dei modelli in config/estrazione.toml) è una coincidenza: non si segnala.
HASH_LUNGHEZZA_MIN = 8


def norm(s: str) -> str:
    return " ".join(s.casefold().split())


def vocabolario() -> list[str]:
    voci = set(TIPI_DOCUMENTO) | set(PAROLE_GENERICHE)
    for percorso in VOCABOLARIO_TOML:
        if not percorso.exists():
            continue
        dati = tomllib.loads(percorso.read_text(encoding="utf-8"))
        for sezione in dati.values():
            for elemento in (sezione if isinstance(sezione, list) else [sezione]):
                if not isinstance(elemento, dict):
                    continue
                voci |= {v for v in elemento.get("valori", []) if isinstance(v, str)}
                if isinstance(elemento.get("valore"), str):
                    voci.add(elemento["valore"])
                for k, v in (elemento.get("corrispondenza") or {}).items():
                    voci |= {k, v}
    return sorted({norm(v) for v in voci if v.strip()}, key=len, reverse=True)


def spiegata(basso: str, inizio: int, fine: int, voci: list[str]) -> bool:
    """L'occorrenza basso[inizio:fine] cade interamente dentro un'occorrenza di una voce del vocabolario?"""
    for voce in voci:
        if len(voce) < fine - inizio:
            continue
        da = max(0, fine - len(voce))
        i = basso.find(voce, da)
        while i != -1 and i <= inizio:
            if i + len(voce) >= fine:
                return True
            i = basso.find(voce, i + 1)
    return False


def dentro_hash(s: str, inizio: int, fine: int) -> bool:
    """s[inizio:fine] sta dentro una sola parola che è un digest o un hash esadecimale?"""
    a, b = inizio, fine
    while a > 0 and s[a - 1].isalnum():
        a -= 1
    while b < len(s) and s[b].isalnum():
        b += 1
    parola = s[a:b].lower()
    return (len(parola) >= HASH_LUNGHEZZA_MIN and re.fullmatch(r"[0-9a-f]+", parola) is not None
            and re.search(r"[a-f]", parola) is not None and re.search(r"[0-9]", parola) is not None)


def occorrenze(basso: str, v: str):
    i = basso.find(v)
    while i != -1:
        yield i
        i = basso.find(v, i + 1)


def riga_di(testo: str, basso: str, posizione: int) -> int:
    """Numero di riga (da 1) nel testo originale della parola che contiene la posizione nel testo normalizzato."""
    parola = basso.count(" ", 0, posizione)
    for n, riga in enumerate(testo.splitlines(), start=1):
        k = len(riga.split())
        if parola < k:
            return n
        parola -= k
    return len(testo.splitlines())


def file_repo() -> list[Path]:
    return [p for p in REPO.rglob("*") if p.is_file() and not ESCLUSI & set(p.parts)
            and (p.suffix.lower() in TESTO or p.name in {"Dockerfile", ".gitignore"})]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dettaglio", nargs="?", const=DETTAGLIO_PREDEFINITO, default=None, metavar="FILE",
                    help="scrive le corrispondenze non spiegate dal vocabolario in FILE (mai sullo schermo)")
    args = ap.parse_args()
    ignorate = {norm(p) for p in PAROLE_COMUNI_IGNORATE}
    nomi = [p for p in DOCUMENTI.rglob("*") if p.is_file()]
    steli = {norm(p.stem) for p in nomi if len(p.stem) >= LUNGHEZZA_MIN} - ignorate
    protocolli = set()
    for p in nomi:
        protocolli |= {m.lstrip("0") for m in re.findall(r"(?<!\d)\d{5,7}(?!\d)", p.stem)}
    righe = list(csv.DictReader(io.StringIO(CSV.read_bytes().decode("utf-8-sig"))))
    valori_liberi, comuni = set(), set()
    colonne_di = defaultdict(set)   # valore libero -> colonne di merged.csv in cui compare
    for r in righe:
        for c in COLONNE_LIBERE:
            v = norm(r.get(c) or "")
            if len(v) >= LUNGHEZZA_MIN and v not in ignorate:
                valori_liberi.add(v)
                colonne_di[v].add(c)
        protocolli |= {m.lstrip("0") for m in re.findall(r"(?<!\d)\d{5,7}(?!\d)", r.get("Protocollo") or "")}
        if (r.get("Comune") or "").strip() and norm(r["Comune"]) not in ignorate:
            comuni.add(norm(r["Comune"]))
    identificativi = set(json.loads(INDICE.read_text(encoding="utf-8"))) if INDICE.exists() else set()

    trovati = defaultdict(lambda: defaultdict(int))
    non_spiegati = defaultdict(int)   # categoria -> corrispondenze non spiegate dal vocabolario
    voci = vocabolario()
    dettaglio = []   # (file, riga, testo, colonne, spiegata): dati reali, solo nel file di dettaglio
    for f in file_repo():
        rel = str(f.relative_to(REPO))
        testo = f.read_text(encoding="utf-8", errors="ignore")
        basso = norm(testo)
        for categoria, insieme in (("nomi di documenti reali", steli), ("valori liberi di merged.csv", valori_liberi)):
            for v in insieme:
                if v not in basso:
                    continue
                # occorrenze valide: fuori da digest/hash; la scelta è la prima non spiegata dal vocabolario
                valide = [i for i in occorrenze(basso, v) if not dentro_hash(basso, i, i + len(v))]
                if not valide:
                    continue
                trovati[categoria][rel] += 1
                scelta = next((i for i in valide if not spiegata(basso, i, i + len(v), voci)), None)
                if scelta is not None:
                    non_spiegati[categoria] += 1
                if args.dettaglio:
                    origine = (", ".join(sorted(colonne_di[v])) if categoria == "valori liberi di merged.csv"
                               else "nome di un documento")
                    dettaglio.append((rel, riga_di(testo, basso, valide[0] if scelta is None else scelta), v,
                                      origine, "sì" if scelta is None else "no"))
        for m in re.finditer(r"(?<!\d)\d{5,7}(?!\d)", testo):
            if m.group().lstrip("0") in protocolli and not dentro_hash(testo, m.start(), m.end()):
                trovati["protocolli reali"][rel] += 1
        for m in re.findall(r"(?<![0-9a-f])[0-9a-f]{16}(?![0-9a-f])", testo):
            if m in identificativi:
                trovati["identificativi di documenti reali"][rel] += 1
        for c in comuni:
            if re.search(r"(?<!\w)" + re.escape(c) + r"(?!\w)", basso):
                trovati["nomi di comuni presenti in merged.csv (informativo)"][rel] += 1

    if args.dettaglio:
        uscita = Path(args.dettaglio)
        with uscita.open("w", encoding="utf-8") as fh:
            fh.write("file\triga\ttesto che coincide\tcolonne di merged.csv o nome di un documento\t"
                     "spiegata dal vocabolario\n")
            for rel, n, v, colonne, sp in sorted(dettaglio, key=lambda d: (d[4] == "sì", d[0], d[1])):
                fh.write(f"{rel}\t{n}\t{v}\t{colonne}\t{sp}\n")
        non_spiegate = sum(d[4] == "no" for d in dettaglio)
        print(f"dettaglio scritto in {uscita} ({len(dettaglio)} corrispondenze, {non_spiegate} non spiegate dal vocabolario)")
        return

    print(f"file di testo controllati: {len(file_repo())}")
    print(f"riferimenti: {len(steli)} nomi, {len(protocolli)} protocolli, {len(identificativi)} identificativi, "
          f"{len(valori_liberi)} valori liberi, {len(comuni)} comuni")
    for categoria in ["nomi di documenti reali", "protocolli reali", "identificativi di documenti reali",
                      "valori liberi di merged.csv", "nomi di comuni presenti in merged.csv (informativo)"]:
        per_file = trovati.get(categoria, {})
        print(f"\n{categoria}: {sum(per_file.values())} corrispondenze in {len(per_file)} file")
        if categoria in ("nomi di documenti reali", "valori liberi di merged.csv"):
            print(f"  di cui non spiegate dal vocabolario: {non_spiegati[categoria]}")
        for rel, n in sorted(per_file.items()):
            print(f"  {rel}: {n}")

    # Pulito = nessun protocollo o identificativo reale e nessuna corrispondenza fuori dal vocabolario.
    pulito = (not trovati.get("protocolli reali") and not trovati.get("identificativi di documenti reali")
              and not any(non_spiegati.values()))
    print(f"\nesito: {'pulito' if pulito else 'da verificare (python strumenti/controllo_pubblicazione.py --dettaglio)'}")


if __name__ == "__main__":
    main()
