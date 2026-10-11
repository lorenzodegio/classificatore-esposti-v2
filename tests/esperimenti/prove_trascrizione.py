"""Prove di trascrizione sulle scansioni sintetiche (nessun documento reale).

Uso:
    python tests/esperimenti/prove_trascrizione.py trascrivi MODELLO [MODELLO...]
    python tests/esperimenti/prove_trascrizione.py tabella MODELLO [MODELLO...]
    python tests/esperimenti/prove_trascrizione.py fra_modelli MODELLO_A MODELLO_B

Per ogni modello si fanno due letture di ogni pagina (LETTURE): la pagina
intera e la pagina in fasce tagliate sulle righe bianche. Le trascrizioni si
salvano in /work/prove/<modello>/<lettura>/<scansione>.txt (pagine separate
da salto pagina). La tabella riporta gli errori della lettura principale
rispetto alla verità e la divergenza fra le due letture.
"""
import io
import json
import sys
import time
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image

from cerchio1.estrazione import config, vlm
from cerchio1.estrazione.divergenza import divergenza_pct as divergenza
from tests.confronto import misura

SCANSIONI = Path(__file__).resolve().parents[1] / "dati_sintetici" / "scansioni"
USCITE = Path("/work/prove")
SALTO = "\f"
CONTESTO = 16384

MODELLI = {
    "qwen3vl8b": {"modello": "qwen3-vl:8b-instruct"},
    # stessa pagina resa più grande, fino al tetto di pixel di Ollama 0.40.1 (circa 4 Mpx)
    "qwen3vl8b_lato3000": {"modello": "qwen3-vl:8b-instruct", "principale": "intera_300"},
    "gemma4_12b": {"modello": "gemma4:12b"},            # ragionamento attivo (predefinito)
    "gemma4_12b_noragion": {"modello": "gemma4:12b", "ragionamento": False},
    # uscite salvate con Ollama 0.23.1, solo per il confronto (non si ritrascrivono)
    "qwen3vl8b_ollama0231": {"modello": "qwen3-vl:8b-instruct"},
}
LETTURE = {
    "intera_200": {"dpi": 200, "lato_max": 2000, "fasce": 1},
    "intera_300": {"dpi": 300, "lato_max": 3000, "fasce": 1},
    "fasce3_300": {"dpi": 300, "lato_max": 4000, "fasce": 3},
}
LETTURA_PRINCIPALE, LETTURA_CONFRONTO = "intera_200", "fasce3_300"

FINESTRA_TAGLIO = 0.04         # il taglio si sposta sulla riga più bianca entro questa quota
SOGLIA_SCURO = 160             # livello di grigio sotto cui un pixel è inchiostro
INCHIOSTRO_MIN_FASCIA = 0.002  # fasce quasi bianche non si trascrivono


def _profilo_inchiostro(img: Image.Image) -> list[int]:
    g = img.convert("L").point(lambda p: 255 if p < SOGLIA_SCURO else 0)
    w, h = g.size
    dati = g.tobytes()
    return [dati[y * w:(y + 1) * w].count(255) for y in range(h)]


def _taglio_bianco(profilo, y, finestra):
    lo, hi = max(0, y - finestra), min(len(profilo) - 1, y + finestra)
    return min(range(lo, hi + 1), key=lambda r: (profilo[r], abs(r - y)))


def fasce(img: Image.Image, n: int) -> list[Image.Image]:
    """Fasce orizzontali non sovrapposte, tagliate sulle righe più bianche."""
    if n == 1:
        return [img]
    w, h = img.size
    profilo = _profilo_inchiostro(img)
    finestra = int(h * FINESTRA_TAGLIO)
    tagli = [0] + [_taglio_bianco(profilo, int(h * i / n), finestra) for i in range(1, n)] + [h]
    return [img.crop((0, a, w, b)) for a, b in zip(tagli, tagli[1:])
            if sum(profilo[a:b]) / (w * max(b - a, 1)) >= INCHIOSTRO_MIN_FASCIA]


def trascrivi_modello(chiave: str) -> None:
    m = MODELLI[chiave]
    cfg = vlm.per_lettore(config.carica(), "principale")
    cfg["vlm"].pop("ragionamento", None)
    cfg["vlm"].update(temperatura=0, contesto=CONTESTO, modello=m["modello"])
    if "ragionamento" in m:
        cfg["vlm"]["ragionamento"] = m["ragionamento"]
    for nome in (m.get("principale", LETTURA_PRINCIPALE), LETTURA_CONFRONTO):
        lettura = LETTURE[nome]
        cartella = USCITE / chiave / nome
        cartella.mkdir(parents=True, exist_ok=True)
        tempi, token = {}, {}
        for pdf in sorted(SCANSIONI.glob("*.pdf")):
            pagine, secondi, tok = [], [], []
            for i in range(len(pdfium.PdfDocument(pdf))):
                img = Image.open(io.BytesIO(vlm.rendi_pagina(pdf, i, lettura["dpi"], lettura["lato_max"])))
                inizio = time.monotonic()
                testi = []
                for f in fasce(img, lettura["fasce"]):
                    buf = io.BytesIO()
                    f.save(buf, format="PNG")
                    r = vlm.trascrivi(buf.getvalue(), cfg)
                    if r.get("errore"):
                        sys.exit(f"{chiave}: errore {r['errore']}")
                    testi.append(r["testo"])
                    tok.append(r["token_ingresso"])
                secondi.append(round(time.monotonic() - inizio, 1))
                pagine.append("\n".join(testi))
            (cartella / f"{pdf.stem}.txt").write_text(SALTO.join(pagine), encoding="utf-8")
            tempi[pdf.stem], token[pdf.stem] = secondi, tok
            print(chiave, nome, pdf.stem, secondi, "token ingresso", tok, flush=True)
        (cartella / "tempi.json").write_text(json.dumps(tempi))


def _leggi(chiave, lettura, stem) -> list[str]:
    return (USCITE / chiave / lettura / f"{stem}.txt").read_text(encoding="utf-8").split(SALTO)


def tabella(chiavi: list[str]) -> None:
    stems = [p.stem for p in sorted(SCANSIONI.glob("*.pdf"))]
    verita = {s: (SCANSIONI / f"{s}.verita.txt").read_text(encoding="utf-8").split(SALTO) for s in stems}
    print(f"| Modello | errori parole {LETTURA_PRINCIPALE}: " + " / ".join(stems) +
          " | s/pagina (stampa / mano) | divergenza " + f"{LETTURA_PRINCIPALE}:{LETTURA_CONFRONTO}: " +
          " / ".join(stems) + " |")
    print("|---|---|---|---|")
    for k in chiavi:
        principale = MODELLI[k].get("principale", LETTURA_PRINCIPALE)
        tempi = json.loads((USCITE / k / principale / "tempi.json").read_text())
        errori = [f"{misura(SALTO.join(verita[s]), SALTO.join(_leggi(k, principale, s)))['errori_parole_pct']}"
                  for s in stems]
        stampa = [t for s in stems if not s.startswith("mano") for t in tempi[s]]
        mano = [t for s in stems if s.startswith("mano") for t in tempi[s]]
        div = [", ".join(str(divergenza(x, y)) for x, y in
                         zip(_leggi(k, principale, s), _leggi(k, LETTURA_CONFRONTO, s)))
               for s in stems]
        print(f"| {k} ({MODELLI[k]['modello']}, {principale}) | " + " / ".join(errori) +
              f" % | {sum(stampa) / len(stampa):.1f} / {sum(mano) / len(mano):.1f} | " + " / ".join(div) + " % |")


def fra_modelli(a: str, b: str) -> None:
    """Divergenza fra le letture principali di due modelli diversi, per pagina."""
    stems = [p.stem for p in sorted(SCANSIONI.glob("*.pdf"))]
    pa, pb = MODELLI[a].get("principale", LETTURA_PRINCIPALE), MODELLI[b].get("principale", LETTURA_PRINCIPALE)
    div = [", ".join(str(divergenza(x, y)) for x, y in zip(_leggi(a, pa, s), _leggi(b, pb, s))) for s in stems]
    print(f"| {a}:{b} | " + " / ".join(div) + " % |")


if __name__ == "__main__":
    comando, *argomenti = sys.argv[1:]
    if comando == "fra_modelli":
        fra_modelli(*argomenti)
    for chiave in argomenti:
        if comando == "trascrivi":
            trascrivi_modello(chiave)
    if comando == "tabella":
        tabella(argomenti)
