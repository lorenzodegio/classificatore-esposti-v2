"""Trascrizione di una pagina con il VLM locale (Ollama).

Il VLM trascrive soltanto: riceve l'immagine di una pagina, restituisce testo.
I segnali di lettura incerta sono calcolati qui in modo deterministico, non
chiesti al modello. Nessun contenuto viene stampato o registrato.
"""
import base64
import io
import json
import time
import urllib.request

import pypdfium2 as pdfium

MARCATORE_ILLEGGIBILE = "[illeggibile]"


def rendi_pagina(percorso_pdf, indice: int, dpi: int, lato_max_px: int) -> bytes:
    """Rende la pagina come PNG, rispettando la rotazione del PDF."""
    doc = pdfium.PdfDocument(percorso_pdf)
    try:
        pagina = doc[indice]
        larghezza, altezza = pagina.get_size()
        scala = dpi / 72
        lato = max(larghezza, altezza) * scala
        if lato > lato_max_px:
            scala *= lato_max_px / lato
        immagine = pagina.render(scale=scala).to_pil().convert("RGB")
    finally:
        doc.close()
    buf = io.BytesIO()
    immagine.save(buf, format="PNG")
    return buf.getvalue()


def _richiesta(url: str, dati: dict | None, timeout: float) -> dict:
    corpo = None if dati is None else json.dumps(dati).encode()
    req = urllib.request.Request(url, data=corpo, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


LETTORI = ("principale", "secondo")


def per_lettore(cfg: dict, lettore: str) -> dict:
    """Configurazione con le impostazioni comuni del VLM più quelle del lettore."""
    if lettore not in LETTORI:
        raise ValueError(f"lettore sconosciuto: {lettore}")
    comuni = {k: v for k, v in cfg["vlm"].items() if k not in LETTORI}
    return {**cfg, "vlm": {**comuni, **cfg["vlm"][lettore]}}


def digest_modello(cfg: dict) -> list[str]:
    """Digest (12 caratteri) di tutte le voci di Ollama con il nome del modello.

    Ollama 0.40.1 può elencare lo stesso modello più volte (voce originale e
    voce convertita): si restituiscono tutte, ordinate; lista vuota se assente.
    """
    v = cfg["vlm"]
    modelli = _richiesta(f"{v['url']}/api/tags", None, 30).get("models", [])
    return sorted({m.get("digest", "")[:12] for m in modelli
                   if v["modello"] in (m.get("name"), m.get("model"))})


def verifica_modello(cfg: dict) -> None:
    """Interrompe se il modello manca o se i suoi digest non sono quelli attesi."""
    v = cfg["vlm"]
    trovati = digest_modello(cfg)
    if trovati != sorted(v["digest_attesi"]):
        raise RuntimeError(f"{v['modello']}: digest {trovati or 'assente'}, attesi {sorted(v['digest_attesi'])}")


def righe_ripetute(testo: str, minimo: int) -> bool:
    """Vero se una stessa riga non vuota compare di fila almeno `minimo` volte."""
    precedente, conta = None, 0
    for riga in testo.splitlines():
        riga = riga.strip()
        if not riga:
            continue
        conta = conta + 1 if riga == precedente else 1
        precedente = riga
        if conta >= minimo:
            return True
    return False


def trascrivi(png: bytes, cfg: dict) -> dict:
    """Trascrive un'immagine di pagina. Ritorna testo e segnali deterministici."""
    v = cfg["vlm"]
    richiesta = {
        "model": v["modello"],
        "stream": False,
        "messages": [{
            "role": "user",
            "content": v["prompt"],
            "images": [base64.b64encode(png).decode()],
        }],
        "options": {
            "temperature": v["temperatura"],
            "num_predict": v["max_token"],
            "num_ctx": v["contesto"],
        },
    }
    if "ragionamento" in v:  # solo per i modelli che "pensano" prima di rispondere
        richiesta["think"] = v["ragionamento"]
    inizio = time.monotonic()
    try:
        risposta = _richiesta(f"{v['url']}/api/chat", richiesta, v["timeout_s"])
    except Exception as e:  # il tipo di errore sì, il contenuto no
        return {"testo": "", "errore": type(e).__name__,
                "secondi": round(time.monotonic() - inizio, 1)}
    testo = risposta.get("message", {}).get("content", "")
    return {
        "testo": testo,
        "errore": None,
        "troncato": risposta.get("done_reason") == "length",
        "ripetizioni": righe_ripetute(testo, v["ripetizioni_riga_min"]),
        "marcatori_illeggibile": testo.count(MARCATORE_ILLEGGIBILE),
        "token_ingresso": risposta.get("prompt_eval_count"),
        "token_uscita": risposta.get("eval_count"),
        "secondi": round(time.monotonic() - inizio, 1),
    }
