"""Predisposizione: dal testo estratto alla scheda ATS (cerchio 1, passo 2).

L'LLM legge il testo per pagina e compila i campi della scheda con i valori
esatti del modulo ATS (config/scheda_ats.toml), ognuno con la frase del testo
che lo giustifica. Deve ignorare l'involucro (intestazioni email, inoltri,
firme, clausole). L'uscita non contiene nome del file né protocollo.
"""
from cerchio1.llm import chiedi_json

TIPI = ["esposto", "riscontro ATS", "lettera avvocato", "richiesta ente", "altro"]
CAMPI_GIUSTIFICATI = ["tipo_documento", "data_doc", "comune", "segnalante", "destinatari", "luogo",
                      "animali", "da_quando", "ambito", "problematica", "elementi"]
SEGNALANTI = ["privato cittadino", "associazione", "ente pubblico", "avvocato", "ATS", "anonimo"]

SISTEMA = """Sei un assistente del Servizio Veterinario di ATS Insubria. Ricevi il testo \
estratto da un documento (pagine numerate) e compili una scheda in JSON.
Regole:
- Considera solo il contenuto del messaggio. Ignora intestazioni email (Da, A, Cc, Oggetto, \
Inviato), righe di inoltro, "Messaggio originale", firme, recapiti, clausole di riservatezza, \
timbri e numeri di protocollo: non sono fatti segnalati.
- tipo_documento: "esposto" (segnalazione di un cittadino o associazione su fatti con animali), \
"riscontro ATS" (risposta o comunicazione scritta da ATS o dal Servizio Veterinario), \
"lettera avvocato" (scritta da un legale), "richiesta ente" (richiesta di Comune, Polizia \
Locale, Carabinieri, Procura, altro ente pubblico), "altro".
- segnalante: chi scrive (privato cittadino, associazione, ente pubblico, avvocato, ATS, \
anonimo); segnalante_rintracciabile: true se ci sono nome e un recapito (indirizzo, telefono, \
email, PEC). destinatari: a chi è indirizzato il documento e chi è solo in copia o "per \
conoscenza". luogo: dove si trovano gli animali o avviene il fatto (via, località). animali: \
quali animali e quanti. da_quando: da quando dura la situazione. Stringa vuota se non scritto.
- data_doc: data del documento (gg/mm/aaaa) o stringa vuota. comune: comune del luogo dei \
fatti, o stringa vuota.
- ambito, problematica, elementi: liste a scelta multipla con valori presi SOLO tra quelli \
ammessi. Spunta una voce di problematica o elementi SOLO se una frase del testo la afferma in \
modo esplicito; nel dubbio non spuntarla. "Foto/allegati" solo se il documento cita foto, video \
o allegati. "Maltrattamento animale" solo se il testo descrive violenze o crudeltà. Ambito "Medicina \
Veterinaria" indica la materia del Servizio Veterinario (benessere, salute e detenzione di \
animali, colonie feline, allevamenti); "ARPA" emissioni, reflui e ambiente. \
Per una voce non prevista usa "Altro" e descrivila in ambito_altro / prob_altro / elementi_altro.
- Per ogni campo in giustificazioni riporta la frase del testo, copiata alla lettera, che lo \
giustifica; stringa vuota se non c'è.
- contenuto_presente: false se il testo non descrive alcun fatto (pagina vuota, solo \
intestazioni, solo "vedi allegato"). contenuto_altrove: indica se i fatti sono in allegati, \
foto, link o documenti non presenti nel testo; stringa vuota altrimenti.
- Le pagine segnate [LETTURA INCERTA] sono trascrizioni automatiche poco affidabili: usale con \
cautela.
- Non inventare nulla che non sia nel testo."""


def schema(modulo: dict) -> dict:
    s = {"type": "string"}
    lista = lambda campo: {"type": "array", "items": {"enum": modulo[campo]["valori"]}}  # noqa: E731
    return {
        "type": "object",
        "properties": {
            "tipo_documento": {"enum": TIPI},
            "data_doc": s, "comune": s,
            "segnalante": {"enum": SEGNALANTI}, "segnalante_rintracciabile": {"type": "boolean"},
            "destinatari": s, "luogo": s, "animali": s, "da_quando": s,
            "ambito": lista("Ambito"), "ambito_altro": s,
            "problematica": lista("Problematica"), "prob_altro": s,
            "elementi": lista("Elementi"), "elementi_altro": s,
            "contenuto_presente": {"type": "boolean"}, "contenuto_altrove": s,
            "giustificazioni": {"type": "object",
                                "properties": {c: s for c in CAMPI_GIUSTIFICATI},
                                "required": CAMPI_GIUSTIFICATI},
        },
        "required": ["tipo_documento", "data_doc", "comune", "segnalante", "segnalante_rintracciabile",
                     "destinatari", "luogo", "animali", "da_quando", "ambito", "ambito_altro", "problematica",
                     "prob_altro", "elementi", "elementi_altro", "contenuto_presente",
                     "contenuto_altrove", "giustificazioni"],
    }


def testo_per_llm(doc: dict) -> str:
    parti = []
    for p in doc["pagine"]:
        etichetta = f"[Pagina {p['n']}{' - LETTURA INCERTA' if p['lettura_incerta'] else ''}]"
        parti.append(f"{etichetta}\n{p['testo'].strip()}")
    return "\n\n".join(parti)


def compila(doc: dict, cfg: dict, modulo: dict) -> dict:
    utente = (f"Valori ammessi:\n- ambito: {modulo['Ambito']['valori']}\n"
              f"- problematica: {modulo['Problematica']['valori']}\n"
              f"- elementi: {modulo['Elementi']['valori']}\n\nTesto del documento:\n{testo_per_llm(doc)}")
    return chiedi_json(cfg["llm"], SISTEMA, utente, schema(modulo))
