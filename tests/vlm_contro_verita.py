"""Configurazione finale dell'estrazione sulle scansioni sintetiche.

Uso (dal container `test`, senza documenti reali montati):
    python tests/vlm_contro_verita.py

Due passate separate, come nell'estrazione: prima il lettore principale su
tutte le pagine, poi il secondo lettore. Per ogni pagina riporta gli errori
del lettore principale rispetto alla verità (<nome>.verita.txt, pagine
separate da salto pagina), la divergenza fra i due lettori e se la pagina
risulterebbe "lettura incerta". Non ci sono soglie di accettazione: è un
rapporto. Le uscite si salvano in /work/vlm_contro_verita/<lettore>/.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pypdfium2 as pdfium  # noqa: E402

from cerchio1.estrazione import config, vlm  # noqa: E402
from cerchio1.estrazione.divergenza import divergenza_pct  # noqa: E402
from tests.confronto import differenze_parole, misura  # noqa: E402

CARTELLA_SCANSIONI = Path(__file__).resolve().parent / "dati_sintetici" / "scansioni"
CARTELLA_USCITE = Path("/work/vlm_contro_verita")
SALTO_PAGINA = "\f"


def passata(cfg: dict, lettore: str, pdfs: list[Path]) -> dict:
    """Trascrive tutte le pagine con un lettore. Ritorna {stem: [risultato per pagina]}."""
    c = vlm.per_lettore(cfg, lettore)
    vlm.verifica_modello(c)
    v = c["vlm"]
    print(f"Lettore {lettore}: {v['modello']} (digest verificati), "
          f"{v['dpi']} DPI, lato max {v['lato_max_px']} px", flush=True)
    risultati = {}
    for pdf in pdfs:
        pagine = []
        for i in range(len(pdfium.PdfDocument(pdf))):
            pagine.append(vlm.trascrivi(vlm.rendi_pagina(pdf, i, v["dpi"], v["lato_max_px"]), c))
        risultati[pdf.stem] = pagine
        cartella = CARTELLA_USCITE / lettore
        cartella.mkdir(parents=True, exist_ok=True)
        (cartella / f"{pdf.stem}.txt").write_text(SALTO_PAGINA.join(p["testo"] for p in pagine), encoding="utf-8")
    return risultati


def main() -> None:
    cfg = config.carica()
    soglia = cfg["vlm"]["divergenza_incerta_pct"]
    pdfs = [p for p in sorted(CARTELLA_SCANSIONI.glob("*.pdf")) if p.with_suffix(".verita.txt").exists()]
    principale = passata(cfg, "principale", pdfs)
    secondo = passata(cfg, "secondo", pdfs)

    print(f"\n| Pagina | Errori parole (principale) | Divergenza fra i lettori | Lettura incerta (≥ {soglia}%) "
          "| s principale / secondo | Altri segnali |")
    print("|---|---|---|---|---|---|")
    dettagli = []
    for pdf in pdfs:
        verita = pdf.with_suffix(".verita.txt").read_text(encoding="utf-8").split(SALTO_PAGINA)
        for i, (p, s) in enumerate(zip(principale[pdf.stem], secondo[pdf.stem])):
            m = misura(verita[i] if i < len(verita) else "", p["testo"])
            div = divergenza_pct(p["testo"], s["testo"])
            segnali = [k for k in ("troncato", "ripetizioni") if p.get(k)]
            if p.get("marcatori_illeggibile"):
                segnali.append(f"illeggibile x{p['marcatori_illeggibile']}")
            if p.get("errore") or s.get("errore"):
                segnali.append(f"errore {p.get('errore') or s.get('errore')}")
            print(f"| {pdf.stem} p.{i + 1} | {m['errori_parole_pct']}% | {div}% | "
                  f"{'sì' if div >= soglia else 'no'} | {p['secondi']} / {s['secondi']} | {', '.join(segnali) or '-'} |")
            dettagli.append((f"{pdf.stem} p.{i + 1}", differenze_parole(verita[i] if i < len(verita) else "", p["testo"])))
    print("\nDifferenze del lettore principale rispetto alla verità:")
    for nome, righe in dettagli:
        print(nome)
        print("\n".join(righe) or "  nessuna")


if __name__ == "__main__":
    main()
