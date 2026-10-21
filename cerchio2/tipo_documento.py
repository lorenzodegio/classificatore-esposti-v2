"""Tipo di documento nel vocabolario del contratto 1.2, con un motivo per l'operatore.

La scheda (cerchio1/scheda.py, invariata) distingue esposto, riscontro ATS,
lettera avvocato, richiesta ente, altro. Il contratto ha in più
`inoltro_per_competenza` e `integrazione`: un LLM risponde a due domande sul
testo (con la frase che le giustifica) e scrive il motivo; le regole qui sotto
decidono il codice. Riscontri ATS e lettere di avvocato restano come li ha
classificati la scheda.
"""
from cerchio1.ancora import ancora, tronca
from cerchio1.llm import chiedi_json
from cerchio1.scheda import testo_per_llm

DA_SCHEDA = {"esposto": "esposto", "riscontro ATS": "riscontro_ats", "lettera avvocato": "lettera_avvocato",
             "richiesta ente": "richiesta_ente", "altro": "altro"}
CODICI = ["esposto", "inoltro_per_competenza", "richiesta_ente", "riscontro_ats", "lettera_avvocato",
          "integrazione", "altro"]
NON_RIDEFINIBILI = {"riscontro_ats", "lettera_avvocato"}

SISTEMA = """Sei un assistente del Servizio Veterinario di ATS Insubria. Ricevi il testo \
estratto da un documento (pagine numerate) e il tipo che gli è stato attribuito. Rispondi in JSON:
- inoltro: true se il documento TRASMETTE ad ATS, per competenza, una segnalazione o un \
esposto ricevuto da altri (per esempio un Comune o la Polizia Locale che inoltra l'esposto di un \
cittadino: "si inoltra per competenza", "si trasmette"). false se chi scrive segnala fatti propri \
o chiede direttamente qualcosa.
- integrazione: true se il documento AGGIUNGE informazioni, foto o documenti a una segnalazione \
già inviata in precedenza dallo stesso mittente ("ad integrazione", "in aggiunta alla mia \
precedente segnalazione"). false altrimenti.
- frase: il tratto del testo, copiato alla lettera, che giustifica inoltro o integrazione \
(stringa vuota se entrambe false).
- motivo: una frase in italiano semplice per l'operatore che spiega perché il documento è del \
tipo attribuito (chi scrive e che cosa chiede), senza riportare nomi di persone.
Non inventare nulla che non sia nel testo."""


def schema() -> dict:
    s, b = {"type": "string"}, {"type": "boolean"}
    return {"type": "object", "properties": {"inoltro": b, "integrazione": b, "frase": s, "motivo": s},
            "required": ["inoltro", "integrazione", "frase", "motivo"]}


def decidi(da_scheda: str, risposta: dict, pagine: list[dict]) -> dict:
    """Regole: riscontri e lettere di avvocato restano; poi inoltro, poi integrazione, poi la scheda."""
    codice = DA_SCHEDA.get(da_scheda, "altro")
    motivo = (risposta.get("motivo") or "").strip()
    if codice not in NON_RIDEFINIBILI:
        posto = ancora(risposta.get("frase", ""), pagine)
        citazione = f" («{posto[0]}», pagina {posto[1]})" if posto else ""
        if risposta.get("inoltro"):
            return {"valore": "inoltro_per_competenza",
                    "motivo": f"Il documento trasmette ad ATS per competenza una segnalazione ricevuta da altri"
                              f"{citazione}."}
        if risposta.get("integrazione"):
            return {"valore": "integrazione",
                    "motivo": f"Il documento integra una segnalazione inviata in precedenza{citazione}."}
    return {"valore": codice, "motivo": tronca(motivo, 500) or f"Tipo attribuito dalla scheda: {codice}."}


def classifica(doc: dict, sch: dict, cfg: dict) -> dict:
    da_scheda = sch.get("tipo_documento", "altro")
    utente = f"Tipo attribuito: {da_scheda}\n\nTesto del documento:\n{testo_per_llm(doc)}"
    return decidi(da_scheda, chiedi_json(cfg["llm"], SISTEMA, utente, schema()), doc["pagine"])
