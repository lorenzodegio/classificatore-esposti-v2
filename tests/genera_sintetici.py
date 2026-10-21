"""Genera i documenti sintetici digitali dei test del servizio (contenuti inventati).

- digitali/esposto_digitale.pdf: email stampata in PDF (testo nativo), veleno e gatti;
- digitali/riscontro_word.docx: riscontro ATS in Word, con protocollo nel testo.

Uso (servizio `prova`, con la cartella di uscita montata in scrittura):
    docker compose run --rm -v ./tests/dati_sintetici:/uscita prova python tests/genera_sintetici.py /uscita
Persone, indirizzi, comuni e protocolli sono inventati.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TESTI = {
    "esposto_digitale.pdf": """Da: Anna Esempio <anna.esempio@posta.example>
Inviato: lunedì 12 maggio 2025 08:30
A: Servizio Veterinario <veterinario@ats.example>
Oggetto: Veleno per gatti in via delle Prove - Borgoverde

Buongiorno,
mi chiamo Anna Esempio, abito in via delle Prove 9 a Borgoverde e do da mangiare ai gatti
che vivono nel cortile di prova dietro casa.

Da sabato 10 maggio 2025 ho trovato due gatti morti vicino al muro e un terzo gatto che
vomitava e non stava in piedi; la veterinaria pensa a un veleno. Ieri sera vicino al muro
ho visto dei pezzi di carne con dentro dei granuli blu: li ho lasciati dove erano e li ho
fotografati.

Chiedo un vostro intervento urgente. Allego le foto.

Saluti
Anna Esempio
tel. 000 000 0000""",
    "riscontro_word.docx": """ATS di prova - Servizio Veterinario
Distretto di Borgoverde

Prot. n. 0098317/2025 del 20/05/2025

Alla sig.ra Anna Esempio
via delle Prove 9 - Borgoverde

Oggetto: riscontro alla Vs. segnalazione del 12 maggio 2025 - veleno per gatti in via delle Prove

In riferimento alla segnalazione in oggetto, si comunica che in data 13 maggio 2025 il
Servizio Veterinario ha fatto un sopralluogo nel cortile di via delle Prove insieme alla
Polizia Locale. I pezzi di carne trovati vicino al muro e uno dei gatti morti sono stati
inviati al laboratorio per le analisi. Il Comune ha disposto la pulizia del cortile.

Si resta a disposizione per ogni ulteriore informazione.

Il Dirigente Veterinario""",
}


def main() -> None:
    uscita = Path(sys.argv[1]) / "digitali"
    uscita.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for nome, testo in TESTI.items():
            sorgente = Path(tmp) / (Path(nome).stem + ".txt")
            sorgente.write_text(testo, encoding="utf-8")
            formato = Path(nome).suffix.lstrip(".")
            subprocess.run(["soffice", "--headless", "--norestore", f"-env:UserInstallation=file://{tmp}/.lo",
                            "--infilter=Text (encoded):UTF8,LF,,", "--convert-to", formato,
                            "--outdir", tmp, str(sorgente)],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
            shutil.copyfile(Path(tmp) / nome, uscita / nome)
            print(f"scritto {uscita / nome}")


if __name__ == "__main__":
    main()
