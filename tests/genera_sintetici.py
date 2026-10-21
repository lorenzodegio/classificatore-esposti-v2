"""Genera i documenti sintetici digitali dei test del servizio (contenuti inventati).

- digitali/esposto_digitale.pdf: email stampata in PDF (testo nativo), esche avvelenate
  e colonia felina;
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
    "esposto_digitale.pdf": """Da: Ernesta Valtorta <ernesta.valtorta@posta-esempio.example>
Inviato: lunedì 12 maggio 2025 08:30
A: Servizio Veterinario ATS <veterinario@ats-esempio.example>
Oggetto: Esche avvelenate in via dei Castagni - Prato Lungo

Buongiorno,
mi chiamo Ernesta Valtorta, abito in via dei Castagni 9 a Prato Lungo e da anni mi occupo
della colonia felina che vive nel parco dietro il condominio.

Da sabato 10 maggio 2025 ho trovato due gatti della colonia morti vicino alla siepe e un terzo
gatto che vomitava e non riusciva a stare in piedi; l'ho portato dalla veterinaria, che sospetta
un avvelenamento. Ieri sera, lungo la recinzione del parco, ho visto dei bocconi di carne con
dentro dei granuli azzurri: li ho lasciati dove erano e li ho fotografati.

Nel parco giocano ogni giorno dei bambini e passano molti cani al guinzaglio: temo che altri
animali possano mangiarli.

Chiedo un vostro intervento urgente. Allego le fotografie dei bocconi.

Cordiali saluti
Ernesta Valtorta
tel. 0331 000 777""",
    "riscontro_word.docx": """ATS Insubria - Dipartimento Veterinario
Distretto Veterinario di Prato Lungo

Prot. n. 0098317/2025 del 20/05/2025

Alla sig.ra Ernesta Valtorta
via dei Castagni 9 - Prato Lungo

Oggetto: riscontro alla Vs. segnalazione del 12 maggio 2025 - esche avvelenate in via dei Castagni

In riferimento alla segnalazione in oggetto, si comunica che in data 13 maggio 2025 personale
del Servizio Veterinario ha effettuato un sopralluogo nel parco di via dei Castagni insieme alla
Polizia Locale. Sono stati raccolti e inviati all'Istituto Zooprofilattico i bocconi rinvenuti
lungo la recinzione e la carcassa di uno dei gatti della colonia. Il Comune ha disposto la
chiusura temporanea del parco e la bonifica dell'area.

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
