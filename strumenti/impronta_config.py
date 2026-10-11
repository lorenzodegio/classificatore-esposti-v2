"""Impronta della configurazione: sha256 dei file che determinano estrazione, scheda e decisione.

Uso: python strumenti/impronta_config.py   (stampa un elenco da incollare in docs/stato.md)
"""
import hashlib
from pathlib import Path

RADICE = Path(__file__).resolve().parents[1]
FILE = ["config/estrazione.toml", "config/scheda_ats.toml", "config/criteri_decisione.md",
        "config/azioni_per_esito.json", "cerchio1/estrazione/leggibilita.py",
        "cerchio1/estrazione/vlm.py", "cerchio1/estrazione/estrai.py", "cerchio1/estrazione/divergenza.py",
        "cerchio1/llm.py", "cerchio1/scheda.py", "cerchio1/voci.py", "nucleo/decisione.py",
        "docker-compose.yml"]


def main() -> None:
    complessiva = hashlib.sha256()
    for f in FILE:
        h = hashlib.sha256((RADICE / f).read_bytes()).hexdigest()
        complessiva.update(h.encode())
        print(f"{h[:16]}  {f}")
    print(f"{complessiva.hexdigest()[:16]}  (impronta complessiva)")


if __name__ == "__main__":
    main()
