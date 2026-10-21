"""Riconoscimento del formato del file ricevuto e conversione delle immagini in PDF."""
from pathlib import Path

from servizio.errori import ErroreContratto

FIRME = [(b"%PDF", ".pdf"), (b"\x89PNG\r\n\x1a\n", ".png"), (b"\xff\xd8\xff", ".jpg"),
         (b"II*\x00", ".tif"), (b"MM\x00*", ".tif"), (b"{\\rtf", ".rtf"),
         (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", ".doc")]
MIME = {"application/pdf": ".pdf", "image/png": ".png", "image/jpeg": ".jpg", "image/tiff": ".tif",
        "application/rtf": ".rtf", "text/rtf": ".rtf", "application/msword": ".doc",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx"}


def ammessi(formati: dict) -> set[str]:
    return {e for elenco in formati.values() for e in elenco}


def riconosci(nome_file: str, tipo_mime: str | None, contenuto: bytes, formati: dict) -> str:
    """Estensione con cui trattare il file (".pdf", ".docx", ...), oppure formato_non_supportato.

    Prima l'estensione del nome, poi il tipo MIME dichiarato, poi la firma dei primi byte.
    Nel messaggio d'errore compare solo l'estensione, mai il nome del file.
    """
    ok = ammessi(formati)
    est = Path(nome_file or "").suffix.lower()
    if est in ok:
        return est
    da_mime = MIME.get((tipo_mime or "").split(";")[0].strip().lower())
    if da_mime in ok:
        return da_mime
    for firma, e in FIRME:
        if contenuto.startswith(firma) and e in ok:
            return e
    raise ErroreContratto("formato_non_supportato",
                          f"Tipo di file {est[:12] if est else 'senza estensione'} non gestito.")


def immagine_in_pdf(origine: Path, destinazione: Path, dpi: int = 200) -> None:
    """Un'immagine (anche TIFF a più pagine) diventa un PDF con una pagina per immagine."""
    from PIL import Image, ImageOps, ImageSequence

    with Image.open(origine) as im:
        pagine = [ImageOps.exif_transpose(f.copy()).convert("RGB") for f in ImageSequence.Iterator(im)]
    pagine[0].save(destinazione, "PDF", resolution=float(dpi), save_all=True, append_images=pagine[1:])
