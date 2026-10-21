"""Un lavoro del servizio: un documento, nel tmpfs, con avanzamento, scadenza e annullamento."""
import time
from dataclasses import dataclass, field
from pathlib import Path

from servizio.errori import ErroreContratto, LavoroAnnullato


@dataclass
class Lavoro:
    id_lavoro: str
    documento_id: str
    sha256: str
    nome_file: str          # solo per il protocollo di ripiego; mai nei log
    estensione: str
    cartella: Path          # tmpfs, nome neutro; cancellata a fine lavoro
    percorso: Path          # documento.<estensione> dentro `cartella`
    immagini: tuple = ()
    scadenza: float = 0.0
    annullato: bool = False
    avanzamento: dict = field(default_factory=lambda: {"pagine_lette": 0, "pagine_totali": 0})
    tempi: dict = field(default_factory=dict)
    conteggi: dict = field(default_factory=dict)

    def controlla(self) -> None:
        if self.annullato:
            raise LavoroAnnullato()
        if self.scadenza and time.monotonic() > self.scadenza:
            raise ErroreContratto("tempo_scaduto", "Analisi oltre il tempo massimo del motore.")
