"""Conversione Word/RTF -> PDF con LibreOffice senza interfaccia, dentro /work.

Il file si copia con un nome neutro (doc_id), così il nome reale non finisce
nei messaggi di LibreOffice. Profilo utente isolato e macro disattivate di
default in modalità headless; nessuna rete nel container.
"""
import shutil
import subprocess
from pathlib import Path


def converti(originale: Path, doc_id: str, cartella: Path, timeout_s: int) -> Path | None:
    cartella.mkdir(parents=True, exist_ok=True)
    neutro = cartella / f"{doc_id}{originale.suffix.lower()}"
    shutil.copyfile(originale, neutro)
    profilo = cartella / ".profilo_lo"
    try:
        subprocess.run(
            ["soffice", "--headless", "--norestore", "--nolockcheck",
             f"-env:UserInstallation=file://{profilo}",
             "--convert-to", "pdf", "--outdir", str(cartella), str(neutro)],
            check=True, timeout=timeout_s, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (subprocess.SubprocessError, OSError):
        return None
    finally:
        neutro.unlink(missing_ok=True)
    pdf = cartella / f"{doc_id}.pdf"
    return pdf if pdf.exists() else None
