"""Estrazione del testo per pagina, con due passate VLM separate.

Passo 0: conversione Word/RTF, smistamento delle pagine, testo digitale.
Passo 1: lettore principale su tutte le pagine 'vlm' di tutti i documenti.
Passo 2: secondo lettore sulle stesse pagine; divergenza; lettura incerta.
Il testo in uscita è sempre quello digitale o del lettore principale.
Nessun contenuto o nome di file viene stampato: solo conteggi.
"""
import hashlib
from pathlib import Path

import pypdfium2 as pdfium

from cerchio1.estrazione import converti, leggibilita, vlm
from cerchio1.estrazione.divergenza import divergenza_pct

AVVISO_INCERTA = "Lettura incerta: leggere l'originale."


def sha256(percorso: Path) -> str:
    h = hashlib.sha256()
    with open(percorso, "rb") as f:
        for blocco in iter(lambda: f.read(1 << 20), b""):
            h.update(blocco)
    return h.hexdigest()


def prepara(originale: Path, cfg: dict) -> dict:
    """Passo 0 per un documento: identificativo, PDF da leggere, pagine smistate."""
    impronta = sha256(originale)
    doc = {"doc_id": impronta[:16], "sha256": impronta, "file": originale.name,
           "formato_origine": originale.suffix.lower().lstrip("."), "conversione": None,
           "pdf": str(originale), "pagine": []}
    if originale.suffix.lower() in cfg["conversione"]["estensioni"]:
        pdf = converti.converti(originale, doc["doc_id"], Path(cfg["percorsi"]["lavoro"]) / "convertiti",
                                cfg["conversione"]["timeout_s"])
        doc["conversione"] = {"strumento": "libreoffice", "esito": "ok" if pdf else "fallita"}
        if pdf is None:
            return doc
        doc["pdf"] = str(pdf)
    try:
        pdf = pdfium.PdfDocument(doc["pdf"])
    except pdfium.PdfiumError:
        doc["errore_apertura"] = True
        return doc
    for i in range(len(pdf)):
        m = leggibilita.misure(pdf[i])
        modo = leggibilita.smista(m, cfg["leggibilita"])
        doc["pagine"].append({
            "n": i + 1, "modalita": modo,
            "testo": m.pop("testo") if modo == "digitale" else "",
            "misure": {k: v for k, v in m.items() if k != "testo"},
            "lettura_incerta": False, "divergenza_pct": None, "segnali": [],
        })
    pdf.close()
    return doc


def _passata(documenti: list[dict], cfg: dict, lettore: str) -> dict:
    c = vlm.per_lettore(cfg, lettore)
    vlm.verifica_modello(c)
    v = c["vlm"]
    uscite = {}
    for doc in documenti:
        for p in doc["pagine"]:
            if p["modalita"] == "vlm":
                png = vlm.rendi_pagina(doc["pdf"], p["n"] - 1, v["dpi"], v["lato_max_px"])
                uscite[(doc["doc_id"], p["n"])] = vlm.trascrivi(png, c)
    return uscite


def estrai(originali: list[Path], cfg: dict, avanzamento=print) -> list[dict]:
    documenti = [prepara(o, cfg) for o in originali]
    n_vlm = sum(p["modalita"] == "vlm" for d in documenti for p in d["pagine"])
    avanzamento(f"estrazione: {len(documenti)} documenti, "
                f"{sum(len(d['pagine']) for d in documenti)} pagine, di cui {n_vlm} da trascrivere")
    principale = _passata(documenti, cfg, "principale") if n_vlm else {}
    avanzamento("estrazione: passata del lettore principale conclusa")
    secondo = _passata(documenti, cfg, "secondo") if n_vlm else {}
    avanzamento("estrazione: passata del secondo lettore conclusa")
    soglia = cfg["vlm"]["divergenza_incerta_pct"]
    for doc in documenti:
        completa(doc, {n: r for (d, n), r in principale.items() if d == doc["doc_id"]},
                 {n: r for (d, n), r in secondo.items() if d == doc["doc_id"]}, soglia)
    return documenti


def completa(doc: dict, principale: dict, secondo: dict, soglia: float) -> dict:
    """Unisce le letture (per numero di pagina) e calcola i segnali di lettura incerta."""
    for p in doc["pagine"]:
        if p["modalita"] != "vlm":
            continue
        r1, r2 = principale[p["n"]], secondo[p["n"]]
        p["testo"] = r1["testo"]
        p["divergenza_pct"] = divergenza_pct(r1["testo"], r2["testo"])
        p["segnali"] = [k for k in ("troncato", "ripetizioni") if r1.get(k)]
        if r1.get("marcatori_illeggibile"):
            p["segnali"].append("illeggibile")
        if r1.get("errore"):
            p["segnali"].append("errore_vlm")
        p["lettura_incerta"] = p["divergenza_pct"] >= soglia or bool(p["segnali"])
        if p["lettura_incerta"]:
            p["avviso"] = AVVISO_INCERTA
    modi = {p["modalita"] for p in doc["pagine"]} - {"vuota"}
    doc["documento"] = {
        "acquisizione": "misto" if len(modi) > 1 else (modi.pop() if modi else "nessuna"),
        "pagine_incerte": [p["n"] for p in doc["pagine"] if p["lettura_incerta"]],
        "senza_contenuto": not any(p["testo"].strip() for p in doc["pagine"]),
    }
    doc["documento"]["lettura_incerta"] = bool(doc["documento"]["pagine_incerte"])
    return doc
