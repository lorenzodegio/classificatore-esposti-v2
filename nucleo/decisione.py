"""Nucleo: decisione a partire SOLO dalla scheda (criteri della direzione, 10/10/2026).

Non vede PDF, nome del file, protocollo né metadati. L'LLM risponde alle
domande (ognuna con risposta e frase giustificativa); le regole qui sotto le
applicano in ordine: 5 (testo assente o negli allegati) come condizione
preliminare, poi 1 competenza, 2 destinatario, 3 completezza. L'urgenza (4) si
calcola a parte. L'azione di partenza per ciascun esito viene dalla metà di
taratura (config/azioni_per_esito.json). La lettura incerta non cambia la
decisione: la marca "da verificare sull'originale".
"""
import json
from pathlib import Path

from cerchio1.llm import chiedi_json

NOTA_INCERTA = "Da verificare sull'originale: alcune pagine hanno lettura incerta."
LIVELLI = ["Bassa", "Normale", "Alta", "Immediata"]
AZIONI_PER_ESITO = json.loads(
    (Path(__file__).resolve().parents[1] / "config" / "azioni_per_esito.json").read_text(encoding="utf-8"))

DOMANDE = {
    "d1_competenza": "Competenza: a chi spetta la questione? 'medicina veterinaria' (benessere e "
                     "detenzione di animali, maltrattamento, abbandono, igiene di allevamenti e "
                     "ricoveri, zoonosi, animali morti) oppure 'altra autorità' (Polizia Locale o "
                     "Forze dell'Ordine per disturbo, rumori, cani liberi incustoditi; Comune; ARPA "
                     "per emissioni, reflui, ambiente; Ordine dei veterinari per la condotta di un "
                     "libero professionista; altro). Se altra autorità indica quale in ente.",
    "d2_destinatario": "Destinatario: il documento è indirizzato a un'altra autorità per competenza "
                       "e ad ATS solo per conoscenza (ATS in copia, 'per conoscenza', 'p.c.')?",
    "d3_completezza": "Completezza: sono indispensabili solo tre cose. chi_segnala: il segnalante è "
                      "identificabile (nome, ente o studio legale; non anonimo). dove: si capisce "
                      "dove si trovano gli animali o avviene il fatto. cosa: si capisce quale "
                      "situazione viene segnalata. Elenca in secondari_mancanti ciò che manca tra "
                      "'da quando' e 'recapito': non rende l'istanza incompleta.",
    "d4_urgenza": "Urgenza: pericolo_attuale è true SOLO con segnali espliciti nel testo: ferite "
                  "o sofferenza grave, veleno o avvelenamento, animale in fin di vita, pericolo "
                  "per le persone. Sporcizia, odori, catena, magrezza generica, mancanza di "
                  "riparo NON bastano: false. in_corso_o_ultime_24h se il testo dice che avviene "
                  "ora o nelle ultime 24 ore; condotta_lunga se dura da mesi o anni; "
                  "altra_autorita_attivata se un'altra autorità è già stata attivata o lo sarà in "
                  "automatico (per esempio segnalazione registrata su un portale che avvisa "
                  "Polizia Locale e Sindaco).",
    "d5_valutabile": "C'è testo su cui decidere? false SOLO se il contenuto è assente o si trova "
                     "negli allegati non trascritti (per esempio 'vedi allegato' senza altro).",
}

SISTEMA = """Sei un dirigente veterinario di ATS Insubria. Ricevi la scheda di un documento \
(con le frasi del documento che giustificano ogni campo) e rispondi in JSON alle domande \
seguenti applicando i criteri della direzione. Rispondi in modo rigoroso, senza presumere fatti \
non scritti. Per ogni risposta riporta la frase della scheda o del documento che la giustifica, \
copiata alla lettera (stringa vuota se non c'è).

Domande:
{domande}

Criteri della direzione:
{criteri}"""


def schema() -> dict:
    s = {"type": "string"}
    b = {"type": "boolean"}
    risposta = lambda extra: {"type": "object", "properties": {**extra, "frase": s},  # noqa: E731
                              "required": [*extra, "frase"]}
    return {
        "type": "object",
        "properties": {
            "d1_competenza": risposta({"risposta": {"enum": ["medicina veterinaria", "altra autorità"]},
                                       "ente": s}),
            "d2_destinatario": risposta({"risposta": b}),
            "d3_completezza": risposta({"chi_segnala": b, "dove": b, "cosa": b,
                                        "secondari_mancanti": {"type": "array",
                                                               "items": {"enum": ["da quando", "recapito"]}}}),
            "d4_urgenza": risposta({"pericolo_attuale": b, "in_corso_o_ultime_24h": b,
                                    "condotta_lunga": b, "altra_autorita_attivata": b}),
            "d5_valutabile": risposta({"risposta": b}),
        },
        "required": list(DOMANDE),
    }


def urgenza(u: dict) -> str:
    """Normale di partenza; Alta/Immediata solo con pericolo esplicito; -1 livello per condizione."""
    livello = LIVELLI.index("Normale")
    if u["pericolo_attuale"]:
        livello = LIVELLI.index("Immediata" if u["in_corso_o_ultime_24h"] else "Alta")
    livello -= int(bool(u["condotta_lunga"])) + int(bool(u["altra_autorita_attivata"]))
    return LIVELLI[max(livello, 0)]


def _esito(determinante: str, frase: str, esito: str, u: str, nota: str, azione=None) -> dict:
    return {"determinante": determinante, "frase_determinante": frase, "esito": esito, "urgenza": u,
            "azione": list(AZIONI_PER_ESITO.get(esito, [])) if azione is None else azione,
            "note_regola": nota}


def applica_regole(r: dict, tipo: str = "esposto") -> dict:
    """Sequenza 5 → 1 → 2 → 3; la prima che scatta decide Esito e Note.

    Un riscontro ATS è un documento di ATS stessa: la completezza (3) non si applica.
    """
    u = urgenza(r["d4_urgenza"])
    d1, d2, d3, d5 = r["d1_competenza"], r["d2_destinatario"], r["d3_completezza"], r["d5_valutabile"]
    if not d5["risposta"]:
        return _esito("5", d5["frase"], "Da approfondire", u,
                      "Da approfondire: contenuto assente o negli allegati.", ["Richiesta integrazione"])
    if d1["risposta"] == "altra autorità":
        ente = d1.get("ente", "").strip() or "ente da individuare"
        return _esito("1", d1["frase"], "Altro", u, f"Competenza di: {ente}.", ["Trasmissione ad altro ente"])
    if d2["risposta"]:
        return _esito("2", d2["frase"], "Archiviato", u,
                      "Indirizzato ad altra autorità per competenza, ad ATS per conoscenza.")
    secondari = d3.get("secondari_mancanti") or []
    annotazione = f" Manca anche: {', '.join(secondari)}." if secondari else ""
    indispensabili = {"chi segnala": d3["chi_segnala"], "dove": d3["dove"], "cosa": d3["cosa"]}
    mancanti = [k for k, v in indispensabili.items() if not v]
    if mancanti and tipo != "riscontro ATS":
        return _esito("3", d3["frase"], "Invio Modulo", u, f"Manca: {', '.join(mancanti)}.{annotazione}")
    return _esito("3", d3["frase"], "Accolto", u, f"Istanza completa.{annotazione}")


def decidi(scheda: dict, lettura_incerta: bool, cfg: dict, criteri: str) -> dict:
    if not scheda.get("contenuto_presente", True):
        d = _esito("5", "", "Da approfondire", "Normale", "Contenuto assente nel testo"
                   + (f" ({scheda['contenuto_altrove']})." if scheda.get("contenuto_altrove") else "."),
                   ["Richiesta integrazione"])
    else:
        domande = "\n".join(f"{k}: {v}" for k, v in DOMANDE.items())
        risposte = chiedi_json(cfg["llm"], SISTEMA.format(domande=domande, criteri=criteri),
                               "Scheda:\n" + json.dumps(scheda, ensure_ascii=False, indent=1), schema())
        d = {"domande": {k: risposte[k] for k in DOMANDE},
             **applica_regole(risposte, scheda.get("tipo_documento", ""))}
    d["classificato"] = True
    d["note"] = d.pop("note_regola")
    d["da_verificare_sull_originale"] = lettura_incerta
    if lettura_incerta:
        d["note"] = f"{NOTA_INCERTA} {d['note']}"
    return d
