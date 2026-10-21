"""Temi per il fascicolo (cerchio 1, dopo la scheda): proposta, decide l'operatore.

L'LLM legge il testo per pagina e sceglie zero o più temi dal vocabolario di
config/temi.toml, ognuno con un motivo in italiano semplice e la frase del
testo che lo giustifica (copiata alla lettera). La pagina si ricava in modo
deterministico ritrovando la frase nel testo (cerchio1/ancora.py).
Non vede nome del file, protocollo né metadati.
"""
import tomllib
from pathlib import Path

from cerchio1.ancora import ancora
from cerchio1.llm import chiedi_json
from cerchio1.scheda import testo_per_llm

FILE_TEMI = Path(__file__).resolve().parents[1] / "config" / "temi.toml"

SISTEMA = """Sei un assistente del Servizio Veterinario di ATS Insubria. Ricevi il testo \
estratto da un documento (pagine numerate) e proponi i TEMI del fascicolo a cui appartiene, \
scegliendo SOLO tra quelli elencati. Regole:
- Un tema si propone solo se i fatti segnalati riguardano esplicitamente quegli animali o \
quel fatto; una menzione di passaggio non basta; nel dubbio non proporlo. Più temi sono ammessi; nessun tema se nessuno si applica.
- Ignora intestazioni email, inoltri, firme e clausole: contano i fatti descritti.
- motivo: una frase breve in italiano semplice per l'operatore, che dica quali animali o \
quale fatto del testo giustificano il tema.
- frase: il tratto del testo, copiato alla lettera, che giustifica il tema (al massimo una \
riga).
- Non inventare nulla che non sia nel testo."""


def carica_vocabolario(percorso: Path = FILE_TEMI) -> list[dict]:
    with open(percorso, "rb") as f:
        return tomllib.load(f)["tema"]


def schema(vocabolario: list[dict]) -> dict:
    s = {"type": "string"}
    voce = {"type": "object",
            "properties": {"valore": {"enum": [t["valore"] for t in vocabolario]}, "motivo": s, "frase": s},
            "required": ["valore", "motivo", "frase"]}
    return {"type": "object", "properties": {"temi": {"type": "array", "items": voce}}, "required": ["temi"]}


def proponi(doc: dict, cfg: dict, vocabolario: list[dict]) -> list[dict]:
    """[{"valore", "motivo", "frase", "pagina"}], un tema al massimo una volta."""
    elenco = "\n".join(f"- {t['valore']}: {t['definizione']}" for t in vocabolario)
    utente = f"Temi ammessi:\n{elenco}\n\nTesto del documento:\n{testo_per_llm(doc)}"
    risposta = chiedi_json(cfg["llm"], SISTEMA, utente, schema(vocabolario))
    ammessi = {t["valore"] for t in vocabolario}
    temi, visti = [], set()
    for t in risposta.get("temi", []):
        valore = t.get("valore")
        if valore not in ammessi or valore in visti:
            continue
        posto = ancora(t.get("frase", ""), doc["pagine"])
        if posto is None:  # senza una frase del documento il tema non è giustificato
            continue
        visti.add(valore)
        temi.append({"valore": valore, "motivo": (t.get("motivo") or "").strip() or f"Tema: {valore}.",
                     "frase": posto[0], "pagina": posto[1]})
    return temi
