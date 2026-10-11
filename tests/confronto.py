"""Misure di scostamento fra una trascrizione e la sua verità (solo dati sintetici).

Servono come diagnostica durante lo sviluppo, non come criterio di
accettazione. Il confronto ignora le differenze di spaziatura e di a capo.
"""
import difflib

from cerchio1.estrazione.divergenza import levenshtein, normalizza  # noqa: F401


def misura(verita: str, uscita: str) -> dict:
    """Scostamento a livello di caratteri e di parole, in percentuale della verità."""
    v, u = normalizza(verita), normalizza(uscita)
    pv, pu = v.split(), u.split()
    return {
        "car_verita": len(v),
        "car_uscita": len(u),
        "errori_caratteri_pct": round(100 * levenshtein(v, u) / max(len(v), 1), 1),
        "errori_parole_pct": round(100 * levenshtein(pv, pu) / max(len(pv), 1), 1),
    }


def differenze_parole(verita: str, uscita: str) -> list[str]:
    """Elenco leggibile delle parole cambiate, mancanti o aggiunte."""
    pv, pu = normalizza(verita).split(), normalizza(uscita).split()
    righe = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=pv, b=pu, autojunk=False).get_opcodes():
        if op == "replace":
            righe.append(f"  cambiato: {' '.join(pv[i1:i2])!r} -> {' '.join(pu[j1:j2])!r}")
        elif op == "delete":
            righe.append(f"  mancante: {' '.join(pv[i1:i2])!r}")
        elif op == "insert":
            righe.append(f"  aggiunto: {' '.join(pu[j1:j2])!r}")
    return righe
