"""Adattatore: dalle uscite della catena al risultato del contratto 1.2.

Traduce soltanto (nomi, vocabolari, formati, frasi ancorate alle pagine): non
cambia estrazione, scheda né decisione. Il contratto sta nel repository
dell'applicazione (`docs/contratto_motore.md`, schemi in
`backend/motore/contratto/`); qui se ne usa una copia degli schemi per i test
(`tests/contratto/`).
"""
from cerchio1.ancora import ancora, tronca
from cerchio2.protocollo import data_iso

VERSIONE_CONTRATTO = "1.2"

ACQUISIZIONE = {"digitale": "testo_nativo", "vlm": "ocr", "vuota": "nessuna"}
SEGNALI = {"troncato": "la trascrizione si è interrotta",
           "ripetizioni": "righe ripetute (possibile errore del lettore)",
           "illeggibile": "parti segnate come illeggibili",
           "errore_vlm": "errore del lettore automatico"}
DOMANDE_BREVI = {
    "1": "La questione è di competenza della Medicina Veterinaria o di un'altra autorità?",
    "2": "Il documento è indirizzato a un'altra autorità per competenza e ad ATS solo per conoscenza?",
    "3": "Il documento indica chi segnala, dove e qual è il problema?",
    "5": "C'è un contenuto su cui decidere, o i fatti sono solo negli allegati?",
}
CAMPI_MULTIPLI = {"ambito": "ambito_altro", "problematica": "prob_altro", "elementi": "elementi_altro"}


def motivo_incertezza(p: dict) -> str | None:
    if not p.get("lettura_incerta"):
        return None
    parti = []
    if p.get("divergenza_pct") is not None:
        parti.append(f"i due lettori automatici divergono del {p['divergenza_pct']:g}% delle parole")
    parti += [SEGNALI[s] for s in p.get("segnali", []) if s in SEGNALI]
    return ("Trascrizione automatica poco affidabile: " + "; ".join(parti or ["segnali di incertezza"])
            + ". Nomi, date e numeri vanno controllati sull'originale.")


def pagine(doc: dict) -> list[dict]:
    return [{"numero": p["n"], "acquisizione": ACQUISIZIONE.get(p["modalita"], "nessuna"),
             "testo": p.get("testo") or "", "lettura_incerta": bool(p.get("lettura_incerta")),
             "motivo_incertezza": motivo_incertezza(p)} for p in doc["pagine"]]


def _voce(valore, frase: str, pag: list[dict]) -> dict | None:
    if not valore:
        return None
    posto = ancora(frase or str(valore), pag)
    return {"valore": valore, "frase": posto[0], "pagina": posto[1]} if posto else None


def _altro(testo: str) -> str | None:
    t = (testo or "").strip()
    return t or None


def scheda(sch: dict, frasi: dict, doc: dict) -> dict:
    g = sch.get("giustificazioni") or {}
    pag = doc["pagine"]
    uscita = {"data_doc": _voce(data_iso(sch.get("data_doc", "")), g.get("data_doc") or sch.get("data_doc"), pag),
              "comune": _voce((sch.get("comune") or "").strip(), g.get("comune"), pag)}
    for campo, altro in CAMPI_MULTIPLI.items():
        uscita[campo] = [{"valore": v["valore"], "frase": tronca(v["frase"]), "pagina": v["pagina"]}
                         for v in frasi.get(campo, [])]
        uscita[f"{campo}_altro"] = _altro(sch.get(altro))
    return uscita


def proposta(dec: dict, doc: dict) -> dict:
    motivo = (dec.get("note") or "").strip()
    frase = tronca(dec.get("frase_determinante") or "")
    if frase:
        motivo += f" Frase del documento: «{frase}»."
    return {"esito": dec["esito"], "urgenza": dec["urgenza"], "azione": list(dec.get("azione") or []),
            "motivo": motivo.strip(),
            "domanda_decisiva": DOMANDE_BREVI.get(str(dec.get("determinante")), "Valutazione complessiva del documento."),
            "da_verificare_sull_originale": [f"Pagina {p['n']}: lettura incerta, leggere l'originale."
                                             for p in doc["pagine"] if p.get("lettura_incerta")]}


def risultato(*, doc: dict, documento_id: str, sha256: str, sch: dict, dec: dict, frasi: dict, temi: list[dict],
              tipo: dict, prot: dict | None, versione_motore: str) -> dict:
    p = pagine(doc)
    return {
        "versione_contratto": VERSIONE_CONTRATTO,
        "versione_motore": versione_motore,
        "documento": {"id": documento_id, "sha256": sha256},
        "tipo_documento": {"valore": tipo["valore"], "motivo": tipo["motivo"]},
        "protocollo": prot,
        "pagine": p,
        "lettura_incerta": any(x["lettura_incerta"] for x in p),
        "scheda": scheda(sch, frasi, doc),
        "proposta": proposta(dec, doc),
        "temi": [{"valore": t["valore"], "motivo": t["motivo"], "frase": tronca(t["frase"]), "pagina": t["pagina"]}
                 for t in temi],
    }
