"""Frase e pagina per OGNI voce della scheda (ambito, problematica, elementi).

La scheda (cerchio1/scheda.py, invariata) dà una frase per campo. Questo passo,
successivo, chiede all'LLM per ciascuna voce già spuntata la frase del testo che
la giustifica, copiata alla lettera; la pagina si ricava ritrovando la frase nel
testo (cerchio1/ancora.py). Non aggiunge voci: se per una voce non arriva una
frase si usa quella del campo della scheda; se manca anche quella la voce si
omette, perché il contratto vuole una frase per ogni voce.
"""
from cerchio1.ancora import ancora
from cerchio1.llm import chiedi_json
from cerchio1.scheda import testo_per_llm

CAMPI = ["ambito", "problematica", "elementi"]

SISTEMA = """Sei un assistente del Servizio Veterinario di ATS Insubria. Ricevi il testo \
estratto da un documento (pagine numerate) e le voci di una scheda già compilata. Per OGNI voce \
riporta la frase del testo che la giustifica, copiata alla lettera (al massimo una o due righe, \
la parte più specifica). Non aggiungere voci e non toglierne. Se nessuna frase del testo \
giustifica una voce lascia la frase vuota. Ignora intestazioni email, firme e clausole."""


def voci_spuntate(sch: dict) -> dict[str, list[str]]:
    return {c: [v for v in (sch.get(c) or [])] for c in CAMPI}


def schema(spuntate: dict[str, list[str]]) -> dict:
    proprieta = {}
    for c, valori in spuntate.items():
        voce = {"type": "object", "properties": {"valore": {"enum": valori or [""]}, "frase": {"type": "string"}},
                "required": ["valore", "frase"]}
        proprieta[c] = {"type": "array", "items": voce}
    return {"type": "object", "properties": proprieta, "required": list(spuntate)}


def frasi(doc: dict, sch: dict, cfg: dict) -> dict[str, list[dict]]:
    """{campo: [{"valore", "frase", "pagina"}]} nello stesso ordine delle voci della scheda."""
    spuntate = voci_spuntate(sch)
    risposta = {}
    if any(spuntate.values()):
        elenco = "\n".join(f"- {c}: {v}" for c, v in spuntate.items() if v)
        utente = f"Voci della scheda:\n{elenco}\n\nTesto del documento:\n{testo_per_llm(doc)}"
        risposta = chiedi_json(cfg["llm"], SISTEMA, utente, schema(spuntate))
    giustificazioni = sch.get("giustificazioni") or {}
    uscita = {}
    for c in CAMPI:
        proposte = {}
        for r in risposta.get(c, []) or []:
            if r.get("valore") in spuntate[c] and (r.get("frase") or "").strip():
                proposte.setdefault(r["valore"], r["frase"])
        uscita[c] = []
        for v in spuntate[c]:
            posto = ancora(proposte.get(v) or giustificazioni.get(c, ""), doc["pagine"])
            if posto is not None:
                uscita[c].append({"valore": v, "frase": posto[0], "pagina": posto[1]})
    return uscita
