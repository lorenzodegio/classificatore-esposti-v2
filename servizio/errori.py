"""Errori codificati del contratto (sezione 5). Il messaggio non contiene mai testo del documento."""

RITENTABILE = {"formato_non_supportato": False, "documento_illeggibile": False, "impronta_non_coincide": True,
               "tempo_scaduto": True, "occupato": True, "errore_interno": True,
               # non previsto dal contratto 1.1: metadati mancanti o malformati (errore dell'applicazione)
               "richiesta_non_valida": False}


class ErroreContratto(Exception):
    def __init__(self, codice: str, messaggio: str):
        super().__init__(codice)
        self.codice = codice
        self.messaggio = messaggio

    def corpo(self) -> dict:
        return {"codice": self.codice, "messaggio": self.messaggio, "ritentabile": RITENTABILE[self.codice]}


class LavoroAnnullato(Exception):
    """L'applicazione ha cancellato (DELETE) un lavoro ancora in corso."""
