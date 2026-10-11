"""Chiamata a un LLM locale (Ollama) con uscita JSON vincolata da uno schema."""
import json
import urllib.request


def chiedi_json(cfg_llm: dict, sistema: str, utente: str, schema: dict) -> dict:
    richiesta = {
        "model": cfg_llm["modello"],
        "stream": False,
        "think": cfg_llm.get("ragionamento", False),
        "format": schema,
        "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": utente}],
        "options": {"temperature": cfg_llm["temperatura"], "num_ctx": cfg_llm["contesto"],
                    "num_predict": cfg_llm["max_token"]},
    }
    req = urllib.request.Request(f"{cfg_llm['url']}/api/chat", data=json.dumps(richiesta).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=cfg_llm["timeout_s"]) as r:
        risposta = json.loads(r.read())
    return json.loads(risposta["message"]["content"])
