"""Prova con Ollama vero: catena completa via HTTP sul servizio `motore`, solo dati sintetici.

Uso (servizio `motore` e Ollama accesi; UNA prova alla volta sulla GPU):
    docker compose up -d motore
    docker compose run --rm prova python tests/prova_motore_vero.py [--url http://motore:8080] [file ...]

Invia i documenti sintetici uno alla volta (come l'applicazione), segue lo stato,
verifica ogni risposta contro gli schemi del contratto 1.2, conferma con DELETE e
misura il tempo per documento. Stampa un riepilogo per documento (i contenuti sono
inventati) e una tabella dei tempi per tipo. Esce con codice 1 se una risposta non
è conforme o un lavoro non si completa.
"""
import argparse
import hashlib
import json
import sys
import time
import urllib.request
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.verifica_contratto import verifica_stato  # noqa: E402

SINTETICI = Path(__file__).resolve().parent / "dati_sintetici"
DOCUMENTI = [  # (file, nome dichiarato, tipo MIME, tipo per la misura dei tempi)
    ("digitali/esposto_digitale.pdf", "esposto_digitale.pdf", "application/pdf", "digitale"),
    ("digitali/riscontro_word.docx", "riscontro_word.docx",
     "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "Word"),
    ("scansioni/email_inoltrata.pdf", "Prot. 12345.08-04-2025.pdf", "application/pdf", "scansione"),
    ("scansioni/mano_1.pdf", "mano_1.pdf", "application/pdf", "manoscritto"),
    ("scansioni/mano_2.pdf", "12 Esposto 54400.20-07-2025.pdf", "application/pdf", "manoscritto"),
    ("scansioni/mano_3.pdf", "esposto.pdf", "application/pdf", "manoscritto"),
]
OLLAMA = "http://ollama:11434"


def modelli_caricati() -> str:
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/ps", timeout=5) as r:
            ps = json.loads(r.read())["models"]
        return ", ".join(f"{m['name']} {m.get('size', 0) / 2**30:.1f} GB (in VRAM {m.get('size_vram', 0) / 2**30:.1f} GB)" for m in ps) or "nessuno"
    except Exception as e:
        return f"non leggibile ({type(e).__name__})"


def analizza(c: httpx.Client, relativo: str, nome: str, mime: str) -> tuple[dict, float, list]:
    contenuto = (SINTETICI / relativo).read_bytes()
    id_lavoro = str(uuid.uuid4())
    meta = {"versione_contratto": "1.2", "id_lavoro": id_lavoro,
            "documento": {"id": f"doc-{Path(relativo).stem}", "nome_file": nome, "tipo_mime": mime,
                          "sha256": hashlib.sha256(contenuto).hexdigest()}}
    inizio = time.monotonic()
    while True:
        r = c.post("/v1/analisi", files={"documento": (nome, contenuto, mime)}, data={"metadati": json.dumps(meta)})
        if r.status_code != 429:
            break
        time.sleep(float(r.headers.get("Retry-After", "5")))
    assert r.status_code == 202, (r.status_code, r.text[:300])
    avanzamenti = []
    while True:
        s = c.get(f"/v1/analisi/{id_lavoro}").json()
        verifica_stato(s)
        if s.get("avanzamento") and (not avanzamenti or avanzamenti[-1] != s["avanzamento"]):
            avanzamenti.append(s["avanzamento"])
        if s["stato"] in ("completato", "errore"):
            secondi = time.monotonic() - inizio
            assert c.delete(f"/v1/analisi/{id_lavoro}").status_code == 204
            assert c.get(f"/v1/analisi/{id_lavoro}").status_code == 404
            return s, secondi, avanzamenti
        time.sleep(2)


def riepilogo(r: dict) -> dict:
    sch = r["scheda"]
    return {"tipo": r["tipo_documento"], "protocollo": r["protocollo"],
            "acquisizione": [p["acquisizione"] for p in r["pagine"]],
            "incerte": [p["numero"] for p in r["pagine"] if p["lettura_incerta"]],
            "data_doc": sch["data_doc"], "comune": sch["comune"],
            **{c: [(v["valore"], v["pagina"], v["frase"]) for v in sch[c]] for c in ("ambito", "problematica", "elementi")},
            "proposta": r["proposta"], "temi": r["temi"]}


def main() -> int:
    a = argparse.ArgumentParser()
    a.add_argument("--url", default="http://motore:8080")
    a.add_argument("file", nargs="*", help="sottoinsieme di file (percorsi relativi a tests/dati_sintetici)")
    args = a.parse_args()
    scelti = [d for d in DOCUMENTI if not args.file or d[0] in args.file]
    c = httpx.Client(base_url=args.url, timeout=60)
    salute = c.get("/v1/salute").json()
    print("salute:", json.dumps(salute, ensure_ascii=False))
    if salute["stato"] != "pronto":
        print("motore non pronto")
        return 1
    tempi, falliti = [], 0
    for relativo, nome, mime, tipo in scelti:
        try:
            s, secondi, avanzamenti = analizza(c, relativo, nome, mime)
        except AssertionError as e:
            print(f"\n## {relativo}: NON CONFORME {str(e)[:500]}")
            falliti += 1
            continue
        print(f"\n## {relativo} ({tipo}): {s['stato']} in {secondi:.0f} s; avanzamento {avanzamenti}")
        print("modelli in memoria:", modelli_caricati())
        if s["stato"] == "completato":
            print(json.dumps(riepilogo(s["risultato"]), ensure_ascii=False, indent=1))
            tempi.append((tipo, relativo, len(s["risultato"]["pagine"]), secondi))
        else:
            print("errore:", s["errore"])
            falliti += 1
    print("\n| Tipo | Documento | Pagine | Secondi |\n|---|---|---|---|")
    for tipo, relativo, pagine, secondi in tempi:
        print(f"| {tipo} | {relativo} | {pagine} | {secondi:.0f} |")
    print(f"\nconformi e completati: {len(tempi)} su {len(scelti)}")
    return 1 if falliti else 0


if __name__ == "__main__":
    sys.exit(main())
