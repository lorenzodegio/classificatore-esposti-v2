"""Estrazione su tutti i documenti, interrompibile e riprendibile.

Ogni risultato si salva appena pronto in /work/estrazione/; al riavvio si
salta ciò che esiste già. Ordine: passo 0 (conversione, smistamento, testo
digitale) per tutti; passata del lettore principale su tutte le pagine VLM;
passata del secondo lettore; assemblaggio di un JSON per documento.
A schermo e nel log escono solo conteggi.

Uso (servizio `app`):  python estrai_tutti.py
"""
import json
import time
from pathlib import Path

from cerchio1.estrazione import config, estrai, vlm

STATO = Path("/work/estrazione")
LOG = STATO / "avanzamento.log"
OGNI = 25  # pagine VLM fra un messaggio di avanzamento e l'altro


def log(msg: str) -> None:
    riga = f"{time.strftime('%H:%M:%S')} {msg}"
    print(riga, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(riga + "\n")


def scrivi(percorso: Path, dati) -> None:
    tmp = percorso.with_suffix(".tmp")
    tmp.write_text(json.dumps(dati, ensure_ascii=False), encoding="utf-8")
    tmp.replace(percorso)  # scrittura atomica: un'interruzione non lascia file a metà


def main() -> None:
    cfg = config.carica()
    radice = Path(cfg["percorsi"]["documenti"])
    estensioni = {".pdf", *cfg["conversione"]["estensioni"]}
    file = sorted(p for p in radice.rglob("*") if p.is_file() and p.suffix.lower() in estensioni)
    for sotto in ("prep", "principale", "secondo", "documenti"):
        (STATO / sotto).mkdir(parents=True, exist_ok=True)

    # Passo 0
    indice, docs = {}, {}
    for f in file:
        doc_id = estrai.sha256(f)[:16]
        indice.setdefault(doc_id, []).append(str(f.relative_to(radice)))
        prep = STATO / "prep" / f"{doc_id}.json"
        if doc_id in docs:
            continue
        if prep.exists():
            docs[doc_id] = json.loads(prep.read_text(encoding="utf-8"))
        else:
            docs[doc_id] = estrai.prepara(f, cfg)
            scrivi(prep, docs[doc_id])
    scrivi(Path("/work/indice_locale.json"), indice)
    pagine_vlm = [(d, p["n"]) for d, doc in docs.items() for p in doc["pagine"] if p["modalita"] == "vlm"]
    log(f"passo 0: {len(file)} file, {len(docs)} documenti distinti, "
        f"{sum(len(d['pagine']) for d in docs.values())} pagine, {len(pagine_vlm)} da trascrivere")

    # Passate VLM
    for lettore in vlm.LETTORI:
        c = vlm.per_lettore(cfg, lettore)
        vlm.verifica_modello(c)
        v = c["vlm"]
        da_fare = [(d, n) for d, n in pagine_vlm if not (STATO / lettore / f"{d}_{n}.json").exists()]
        log(f"lettore {lettore}: {len(pagine_vlm) - len(da_fare)} pagine già fatte, {len(da_fare)} da fare")
        inizio = time.monotonic()
        for i, (d, n) in enumerate(da_fare, 1):
            png = vlm.rendi_pagina(docs[d]["pdf"], n - 1, v["dpi"], v["lato_max_px"])
            scrivi(STATO / lettore / f"{d}_{n}.json", vlm.trascrivi(png, c))
            if i % OGNI == 0 or i == len(da_fare):
                s = (time.monotonic() - inizio) / i
                log(f"lettore {lettore}: {i}/{len(da_fare)} pagine, {s:.1f} s/pagina, "
                    f"mancano circa {s * (len(da_fare) - i) / 60:.0f} min")

    # Assemblaggio
    soglia = cfg["vlm"]["divergenza_incerta_pct"]
    for d, doc in docs.items():
        vlm_n = [p["n"] for p in doc["pagine"] if p["modalita"] == "vlm"]
        letture = {lett: {n: json.loads((STATO / lett / f"{d}_{n}.json").read_text(encoding="utf-8"))
                          for n in vlm_n} for lett in vlm.LETTORI}
        if doc["pagine"]:
            estrai.completa(doc, letture["principale"], letture["secondo"], soglia)
        doc["file"] = None  # il nome resta solo in indice_locale.json
        scrivi(STATO / "documenti" / f"{d}.json", doc)
    incerti = sum(doc.get("documento", {}).get("lettura_incerta", False) for doc in docs.values())
    vuoti = sum(doc.get("documento", {}).get("senza_contenuto", True) for doc in docs.values())
    log(f"fine: {len(docs)} documenti assemblati; con lettura incerta {incerti}; senza contenuto {vuoti}")


if __name__ == "__main__":
    main()
