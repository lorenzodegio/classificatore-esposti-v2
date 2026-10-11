"""Controllo deterministico "leggibile digitalmente?" per pagina (nessun modello)."""
import unicodedata

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c


def _carattere_valido(c: str) -> bool:
    if c == "�" or 0xE000 <= ord(c) <= 0xF8FF:
        return False
    cat = unicodedata.category(c)
    return cat[0] in "LNPZS" or c in "\n\r\t"


def misure(pagina: pdfium.PdfPage) -> dict:
    tp = pagina.get_textpage()
    testo = tp.get_text_bounded()
    tp.close()
    pieni = [c for c in testo if not c.isspace()]
    validi = sum(_carattere_valido(c) for c in pieni)
    larghezza, altezza = pagina.get_size()
    area = 0.0
    for obj in pagina.get_objects(filter=(pdfium_c.FPDF_PAGEOBJ_IMAGE,), max_depth=3):
        sx, basso, dx, alto = obj.get_pos()
        area += max(0, min(dx, larghezza) - max(sx, 0)) * max(0, min(alto, altezza) - max(basso, 0))
    return {
        "caratteri": len(pieni),
        "quota_validi": round(validi / len(pieni), 3) if pieni else 0.0,
        "copertura_immagini": round(min(area / (larghezza * altezza), 1.0), 3),
        "testo": testo,
    }


def smista(m: dict, soglie: dict) -> str:
    """'digitale' se lo strato di testo è usabile, 'vuota' se non c'è nulla, altrimenti 'vlm'."""
    if (m["caratteri"] >= soglie["caratteri_min"]
            and m["quota_validi"] >= soglie["quota_validi_min"]
            and m["copertura_immagini"] <= soglie["copertura_immagini_max"]):
        return "digitale"
    if m["caratteri"] == 0 and m["copertura_immagini"] == 0:
        return "vuota"
    return "vlm"
