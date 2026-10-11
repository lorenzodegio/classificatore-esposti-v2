"""Prototipo della catena completa: estrazione -> scheda -> decisione -> consegna.

Uso:
    python prototipo.py sintetici                 # dal servizio `test`, solo dati sintetici
    python prototipo.py campione [N] [SEME]        # dal servizio `app`, documenti reali
    python prototipo.py rifai ESECUZIONE           # rifà scheda, decisione e consegna sul testo già estratto

A schermo escono solo conteggi, tempi e hash: mai contenuti né nomi di file.
Le uscite stanno in /work/prototipo/<esecuzione>/.
"""
import json
import random
import shutil
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import pypdfium2 as pdfium

from cerchio1 import scheda, voci
from cerchio1.estrazione import config, estrai, leggibilita
from cerchio2 import consegna
from nucleo import decisione

LAVORO = Path("/work")
N_CAMPIONE, SEME = 20, 42
MIN_SCANSIONATI, MIN_WORD = 4, 1
SINTETICI = Path(__file__).resolve().parent / "tests" / "dati_sintetici"

# Documenti sintetici digitali e Word generati con LibreOffice (contenuti inventati).
TESTI_SINTETICI = {
    "Riscontro Prot. 12345.20-04-2025.docx": """ATS Insubria - Dipartimento Veterinario
Distretto Veterinario di Varese

Oggetto: riscontro alla Vs. nota prot. n. 12345 dell'8 aprile 2025 - cani in via delle Robinie, Borgoverde

In riferimento alla segnalazione in oggetto, si comunica che in data 15 aprile 2025 personale
del Servizio Veterinario ha effettuato sopralluogo presso l'abitazione di via delle Robinie 18.
Sono stati rilevati cinque cani detenuti in un recinto privo di riparo. Al proprietario sono
state impartite prescrizioni per la realizzazione di una tettoia e la pulizia quotidiana.

Il Dirigente Veterinario""",
    "Prot. 67890.02-05-2025.txt": """Studio Legale Avv. Paolo Rinaldelli
Via Garibaldi 3 - 22100 Como

Spett.le ATS Insubria
Servizio Veterinario

Como, 2 maggio 2025

Oggetto: richiesta di accesso agli atti per conto del sig. Ottavio Brusadelli

Il sottoscritto avvocato, in nome e per conto del sig. Ottavio Brusadelli, chiede di prendere
visione ed estrarre copia di tutti gli atti relativi al sopralluogo effettuato presso
l'abitazione del proprio assistito in via delle Robinie 18 a Borgoverde.

Distinti saluti
Avv. Paolo Rinaldelli""",
}
NOMI_SCANSIONI = {
    "email_inoltrata.pdf": "Prot. 12345.08-04-2025.pdf",
    "mano_1.pdf": "Prot. 54321.14-03-2025.pdf",
    "mano_2.pdf": "12 Esposto 54400.20-07-2025.pdf",
    "mano_3.pdf": "esposto.pdf",
}


def ingressi_sintetici() -> list[Path]:
    cartella = LAVORO / "sintetici_input"
    shutil.rmtree(cartella, ignore_errors=True)
    cartella.mkdir(parents=True)
    for orig, nome in NOMI_SCANSIONI.items():
        shutil.copyfile(SINTETICI / "scansioni" / orig, cartella / nome)
    for nome, testo in TESTI_SINTETICI.items():
        txt = cartella / (Path(nome).stem + ".txt")
        txt.write_text(testo, encoding="utf-8")
        formato = "docx" if nome.endswith(".docx") else "pdf"
        subprocess.run(["soffice", "--headless", "--norestore", f"-env:UserInstallation=file://{cartella}/.lo",
                        "--convert-to", formato, "--outdir", str(cartella), str(txt)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        txt.unlink()
    shutil.rmtree(cartella / ".lo", ignore_errors=True)
    return sorted(p for p in cartella.iterdir() if p.is_file())


def _scansionato(pdf: Path, soglie: dict) -> bool:
    try:
        doc = pdfium.PdfDocument(pdf)
        esito = any(leggibilita.smista(leggibilita.misure(doc[i]), soglie) == "vlm" for i in range(len(doc)))
        doc.close()
        return esito
    except pdfium.PdfiumError:
        return False


def ingressi_campione(cfg: dict, n: int, seme: int) -> list[Path]:
    radice = Path(cfg["percorsi"]["documenti"])
    tutti = sorted(p for p in radice.rglob("*") if p.is_file())
    word = [p for p in tutti if p.suffix.lower() in cfg["conversione"]["estensioni"]]
    pdf = [p for p in tutti if p.suffix.lower() == ".pdf"]
    rnd = random.Random(seme)
    rnd.shuffle(pdf)
    scansionati = [p for p in pdf if _scansionato(p, cfg["leggibilita"])]
    scelti = rnd.sample(word, min(MIN_WORD, len(word))) + scansionati[:MIN_SCANSIONATI]
    scelti += [p for p in pdf if p not in scelti][: n - len(scelti)]
    impronte = sorted(estrai.sha256(p) for p in scelti)
    (LAVORO / "campione_prototipo.txt").write_text(
        f"seme {seme}, n {n}\n" + "\n".join(impronte) + "\n", encoding="utf-8")
    print(f"campione: {len(scelti)} documenti (Word/RTF {min(MIN_WORD, len(word))}, "
          f"con pagine scansionate scelti apposta {min(MIN_SCANSIONATI, len(scansionati))}); "
          f"hash in /work/campione_prototipo.txt")
    return scelti


def ricarica(nome: str, cfg: dict) -> list[dict]:
    """Documenti di un'esecuzione precedente, con il percorso del PDF ritrovato."""
    documenti = []
    for f in sorted((LAVORO / "prototipo" / nome / "documenti").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        candidati = [LAVORO / "convertiti" / f"{d['doc_id']}.pdf", LAVORO / "sintetici_input" / d["file"],
                     *Path(cfg["percorsi"]["documenti"]).rglob(d["file"])]
        d["pdf"] = next((str(c) for c in candidati if c.exists() and c.suffix.lower() == ".pdf"), "")
        for k in ("scheda", "decisione", "blocco"):
            d.pop(k, None)
        documenti.append(d)
    return documenti


def carica_estratti(meta: str | None) -> list[dict]:
    """Testo già estratto (estrai_tutti.py): di una sola metà, oppure di tutti i documenti (None)."""
    indice = json.loads((LAVORO / "indice_locale.json").read_text(encoding="utf-8"))
    if meta:
        divisione = json.loads((LAVORO / "confronto" / "divisione.json").read_text(encoding="utf-8"))
        ids = divisione[meta]  # solo la metà richiesta
    else:
        ids = sorted(indice)
    documenti = []
    for d_id in ids:
        d = json.loads((LAVORO / "estrazione" / "documenti" / f"{d_id}.json").read_text(encoding="utf-8"))
        d["file"] = Path(indice[d_id][0]).name
        documenti.append(d)
    return documenti


def riusa(documenti: list[dict], esecuzioni: list[str]) -> int:
    """Scheda e decisione già calcolate con la stessa configurazione (per la modalità 'tutti')."""
    fatti = {}
    for nome in esecuzioni:
        for f in (LAVORO / "prototipo" / nome / "documenti").glob("*.json"):
            d = json.loads(f.read_text(encoding="utf-8"))
            fatti[d["doc_id"]] = d
    riusati = 0
    for d in documenti:
        prec = fatti.get(d["doc_id"])
        if prec and (prec.get("scheda") or prec.get("blocco")):
            for k in ("scheda", "decisione", "blocco"):
                if k in prec:
                    d[k] = prec[k]
            riusati += 1
    return riusati


def main() -> None:
    modo = sys.argv[1]
    cfg = config.carica()
    tempi = {}
    if modo == "rifai":
        nome = sys.argv[2]
        documenti = ricarica(nome, cfg)
    elif modo in ("taratura", "verifica"):
        nome = modo
        documenti = carica_estratti(modo)
    elif modo == "tutti":
        nome = "tutti"
        documenti = carica_estratti(None)
        print("riusati da taratura e verifica:", riusa(documenti, ["taratura", "verifica"]))
    else:
        if modo == "sintetici":
            ingressi, nome = ingressi_sintetici(), "sintetici"
        else:
            n = int(sys.argv[2]) if len(sys.argv) > 2 else N_CAMPIONE
            seme = int(sys.argv[3]) if len(sys.argv) > 3 else SEME
            ingressi, nome = ingressi_campione(cfg, n, seme), f"campione_{n}_seme{seme}"
        t = time.monotonic()
        documenti = estrai.estrai(ingressi, cfg)
        tempi["estrazione"] = time.monotonic() - t
    modulo = voci.carica_modulo()
    criteri = Path(cfg["percorsi"]["criteri"]).read_text(encoding="utf-8")
    uscita = LAVORO / "prototipo" / nome
    shutil.rmtree(uscita, ignore_errors=True)
    uscita.mkdir(parents=True)

    t = time.monotonic()
    for d in documenti:
        if d.get("scheda") or d.get("blocco"):
            continue
        if not d["pagine"]:
            d["blocco"] = "conversione fallita" if d.get("conversione") else "PDF non apribile"
            continue
        if d["documento"]["senza_contenuto"]:
            d["blocco"] = "senza contenuto utilizzabile"
            continue
        try:
            d["scheda"] = scheda.compila(d, cfg, modulo)
        except Exception as e:  # solo il tipo di errore, mai il contenuto
            d["blocco"] = f"scheda: {type(e).__name__}"
    tempi["scheda"] = time.monotonic() - t

    t = time.monotonic()
    for d in documenti:
        if d.get("scheda") and not d.get("decisione"):
            try:
                d["decisione"] = decisione.decidi(d["scheda"], d["documento"]["lettura_incerta"], cfg, criteri)
            except Exception as e:
                d["blocco"] = f"decisione: {type(e).__name__}"
    tempi["decisione"] = time.monotonic() - t

    t = time.monotonic()
    consegna.collega(documenti)
    consegna.scrivi_json(documenti, uscita / "documenti")
    intestazione = f"esecuzione {nome}, {time.strftime('%d/%m/%Y %H:%M')}"
    consegna.scrivi_report_pdf(documenti, uscita / "report.pdf", intestazione)
    consegna.scrivi_html(documenti, uscita / "revisione.html", intestazione)
    tempi["consegna"] = time.monotonic() - t

    pagine = Counter(p["modalita"] for d in documenti for p in d["pagine"])
    print(f"documenti: {len(documenti)}; pagine per modalità: {dict(pagine)}")
    print("formato origine:", dict(Counter(d["formato_origine"] for d in documenti)))
    print("per tipo:", dict(Counter((d.get("scheda") or {}).get("tipo_documento", "n/d") for d in documenti)))
    print("per esito:", dict(Counter(consegna.esito_breve(d) for d in documenti)))
    print("domanda determinante:", dict(Counter((d.get("decisione") or {}).get("determinante", "-")
                                                for d in documenti)))
    print("con lettura incerta:", sum(d.get("documento", {}).get("lettura_incerta", False) for d in documenti),
          "| con protocollo dal nome:", sum(bool(d.get("protocollo")) for d in documenti),
          "| con almeno un collegato:", sum(bool(d.get("collegati")) for d in documenti))
    print("tempi (s):", {k: round(v) for k, v in tempi.items()}, "totale", round(sum(tempi.values())))
    print(f"uscite: {uscita}")


if __name__ == "__main__":
    main()
