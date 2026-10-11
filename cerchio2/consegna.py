"""Cerchio 2: contesto e consegna. Consuma le uscite del cerchio 1 e del nucleo.

- File e Protocollo dal nome del file; collegamento esposto-riscontro per protocollo.
- Un JSON per documento, un report PDF riepilogativo, una pagina HTML locale.
Tutto resta in /work; a schermo escono solo conteggi.
"""
import base64
import html
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import quote

DATA_NOME = re.compile(r"(?<!\d)(\d{1,2})[-._](\d{1,2})[-._](\d{4})(?!\d)")
PROTOCOLLO = re.compile(r"(?<!\d)\d{5,7}(?!\d)")


def da_nome(nome: str) -> dict:
    """Protocollo: primo gruppo di 5-7 cifre fuori dalle date. Data: prima gg-mm-aaaa."""
    base = Path(nome).stem
    data = DATA_NOME.search(base)
    resto = DATA_NOME.sub(" ", base)
    prot = PROTOCOLLO.search(resto)
    return {"protocollo": (prot.group().lstrip("0") or "0") if prot else "",
            "data_nome": f"{int(data[1]):02d}/{int(data[2]):02d}/{data[3]}" if data else ""}


def collega(documenti: list[dict]) -> None:
    per_prot = defaultdict(list)
    for d in documenti:
        d.update(da_nome(d["file"]))
        if d["protocollo"]:
            per_prot[d["protocollo"]].append(d)
    for d in documenti:
        d["collegati"] = [{"doc_id": a["doc_id"], "tipo": (a.get("scheda") or {}).get("tipo_documento", "")}
                          for a in per_prot.get(d["protocollo"], []) if a is not d]


def esito_breve(d: dict) -> str:
    dec = d.get("decisione") or {}
    if d.get("blocco"):
        return f"non elaborato ({d['blocco']})"
    if not dec.get("classificato"):
        return "non classificato"
    return dec.get("esito", "")


def scrivi_json(documenti: list[dict], cartella: Path) -> None:
    cartella.mkdir(parents=True, exist_ok=True)
    for d in documenti:
        (cartella / f"{d['doc_id']}.json").write_text(
            json.dumps({k: v for k, v in d.items() if k != "pdf"}, ensure_ascii=False, indent=1),
            encoding="utf-8")


def scrivi_report_pdf(documenti: list[dict], percorso: Path, intestazione: str) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    st = getSampleStyleSheet()
    piccolo = st["BodyText"].clone("piccolo", fontSize=7, leading=8.5)
    tipi = Counter((d.get("scheda") or {}).get("tipo_documento", "n/d") for d in documenti)
    esiti = Counter(esito_breve(d) for d in documenti)
    incerti = sum(bool(d.get("documento", {}).get("lettura_incerta")) for d in documenti)
    storia = [Paragraph("S.I.R.E. - Report riepilogativo (prototipo)", st["Title"]),
              Paragraph(intestazione, st["BodyText"]),
              Paragraph(f"Documenti: {len(documenti)}; con pagine a lettura incerta: {incerti}", st["BodyText"]),
              Paragraph("Per tipo: " + ", ".join(f"{k} {v}" for k, v in tipi.most_common()), st["BodyText"]),
              Paragraph("Per esito: " + ", ".join(f"{k} {v}" for k, v in esiti.most_common()), st["BodyText"]),
              Spacer(1, 8)]
    righe = [["File", "Protocollo", "Tipo", "Esito", "Urgenza", "Azione", "Incerta", "Collegati", "Note"]]
    # Note: domanda determinante (a-e) e motivazione breve
    for d in sorted(documenti, key=lambda x: (x.get("protocollo", ""), x["file"])):
        dec, sch = d.get("decisione") or {}, d.get("scheda") or {}
        righe.append([Paragraph(html.escape(d["file"]), piccolo), d.get("protocollo", ""),
                      sch.get("tipo_documento", ""), esito_breve(d), dec.get("urgenza", ""),
                      ", ".join(dec.get("azione") or []),
                      "sì" if d.get("documento", {}).get("lettura_incerta") else "",
                      str(len(d.get("collegati", []))),
                      Paragraph(html.escape((f"[{dec['determinante']}] " if dec.get("determinante") else "")
                                          + (dec.get("note", "") or dec.get("motivo", ""))), piccolo)])
    t = Table(righe, colWidths=[150, 50, 60, 70, 45, 85, 35, 40, 260], repeatRows=1)
    t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 7), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                           ("GRID", (0, 0), (-1, -1), 0.3, colors.grey)]))
    storia.append(t)
    SimpleDocTemplate(str(percorso), pagesize=landscape(A4), leftMargin=20, rightMargin=20,
                      topMargin=20, bottomMargin=20).build(storia)


PAGINA = """<!doctype html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>S.I.R.E. revisione</title>
<style>
:root{{--bg:#fafafa;--fg:#1a1a1a;--card:#fff;--line:#ddd;--warn:#fff3cd;--warnfg:#7a5300;--accent:#2457a6}}
@media (prefers-color-scheme:dark){{:root{{--bg:#16181c;--fg:#e8e8e8;--card:#1f2228;--line:#3a3d44;--warn:#4a3b10;--warnfg:#ffd97a;--accent:#7aa7ff}}}}
body{{margin:0;font:14px system-ui,sans-serif;background:var(--bg);color:var(--fg)}}
header{{padding:10px 16px;border-bottom:1px solid var(--line)}}
#lista{{width:290px;position:fixed;top:52px;bottom:0;overflow:auto;border-right:1px solid var(--line)}}
#lista div{{padding:6px 10px;cursor:pointer;border-bottom:1px solid var(--line);font-size:12px}}
#lista div.sel{{background:var(--card);border-left:3px solid var(--accent)}}
#vista{{margin-left:290px;display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;padding:10px;height:calc(100vh - 72px)}}
.col{{background:var(--card);border:1px solid var(--line);border-radius:6px;overflow:auto;padding:8px}}
iframe{{width:100%;height:100%;border:0}} pre{{white-space:pre-wrap;font-size:12px}}
.inc{{background:var(--warn);color:var(--warnfg);padding:4px 6px;border-radius:4px;font-weight:600}}
table{{border-collapse:collapse;font-size:12px;width:100%}} td{{border-bottom:1px solid var(--line);padding:3px;vertical-align:top}}
td.g{{color:#888;font-style:italic}} h3{{margin:6px 0}}
</style></head><body><header><b>S.I.R.E. - revisione prototipo</b> · {n} documenti · {intestazione}</header>
<div id="lista"></div><div id="vista"><div class="col"><iframe id="pdf"></iframe></div>
<div class="col" id="testo"></div><div class="col" id="dec"></div></div>
<script>
const D={dati};
const e=s=>String(s??'').replace(/[&<>"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c]));
let url=null;
function mostra(i){{
 document.querySelectorAll('#lista div').forEach((x,j)=>x.className=j==i?'sel':'');
 const d=D[i];
 if(url)URL.revokeObjectURL(url);
 if(d.pdf_b64){{const b=Uint8Array.from(atob(d.pdf_b64),c=>c.charCodeAt(0));
  url=URL.createObjectURL(new Blob([b],{{type:'application/pdf'}}));document.getElementById('pdf').src=url;}}
 else if(d.pdf_url)document.getElementById('pdf').src=d.pdf_url;
 else document.getElementById('pdf').removeAttribute('src');
 document.getElementById('testo').innerHTML='<h3>Testo estratto</h3>'+(d.pagine||[]).map(p=>
  `<div><b>Pagina ${{p.n}}</b> · ${{e(p.modalita)}}${{p.divergenza_pct!=null?' · divergenza '+p.divergenza_pct+'%':''}}
  ${{p.lettura_incerta?'<div class="inc">'+e(p.avviso||'Lettura incerta')+'</div>':''}}<pre>${{e(p.testo)}}</pre></div>`).join('');
 const s=d.scheda||{{}},g=s.giustificazioni||{{}},c=d.decisione||{{}};
 const riga=(k,v,gi)=>`<tr><td><b>${{k}}</b></td><td>${{e(Array.isArray(v)?v.join(', '):v)}}</td><td class="g">${{e(gi||'')}}</td></tr>`;
 document.getElementById('dec').innerHTML=`${{d.pdf_url?'<a href="'+e(d.pdf_url)+'" target="_blank">Apri il PDF in una nuova scheda</a>':''}}
 <h3>File</h3><table>${{riga('File',d.file)}}${{riga('Protocollo',d.protocollo)}}
 ${{riga('Collegati',(d.collegati||[]).map(x=>x.tipo+' '+x.doc_id).join('; '))}}</table>
 <h3>Scheda</h3><table>${{riga('Tipo',s.tipo_documento,g.tipo_documento)}}${{riga('Data doc',s.data_doc,g.data_doc)}}
 ${{riga('Comune',s.comune,g.comune)}}${{riga('Ambito',s.ambito,g.ambito)}}${{riga('Ambito altro',s.ambito_altro)}}
 ${{riga('Problematica',s.problematica,g.problematica)}}${{riga('Prob altro',s.prob_altro)}}
 ${{riga('Elementi',s.elementi,g.elementi)}}${{riga('Elementi altro',s.elementi_altro)}}
 ${{riga('Contenuto presente',s.contenuto_presente)}}${{riga('Contenuto altrove',s.contenuto_altrove)}}</table>
 <h3>Decisione</h3>${{c.da_verificare_sull_originale?'<div class="inc">Da verificare sull\\'originale</div>':''}}
 <table>${{c.classificato?riga('Esito',c.esito)+riga('Urgenza',c.urgenza)+riga('Azione',c.azione)+
 riga('Domanda determinante',c.determinante,c.frase_determinante)+riga('Note',c.note)+
 Object.entries(c.domande||{{}}).map(([k,v])=>riga(k,Object.entries(v).filter(([x])=>x!='frase').map(([x,y])=>x+': '+y).join('; '),v.frase)).join('')
 :riga('Non classificato',c.motivo||d.blocco)}}</table>`;
}}
document.getElementById('lista').innerHTML=D.map((d,i)=>`<div onclick="mostra(${{i}})">${{e(d.file)}}<br>
<small>${{e((d.scheda||{{}}).tipo_documento||'')}} · ${{e(d.esito_breve)}}${{(d.documento||{{}}).lettura_incerta?' · ⚠ incerta':''}}</small></div>`).join('');
if(D.length)mostra(0);
</script></body></html>"""


MAX_INCORPORATI = 40  # oltre, i PDF si collegano invece di incorporarli nella pagina
# Percorsi del container -> percorsi visti da Windows (la pagina si apre in Edge).
SU_WINDOWS = {"/data/esposti/": "file://wsl.localhost/Ubuntu/home/lorenzo/vlm_pdf/documenti/",
              "/work/": "file://wsl.localhost/Ubuntu/home/lorenzo/sire_lavoro/"}


def url_windows(percorso: str) -> str:
    for interno, esterno in SU_WINDOWS.items():
        if percorso.startswith(interno):
            return esterno + "/".join(quote(p) for p in percorso[len(interno):].split("/"))
    return ""


def scrivi_html(documenti: list[dict], percorso: Path, intestazione: str) -> None:
    dati = []
    incorpora = len(documenti) <= MAX_INCORPORATI
    for d in documenti:
        voce = {k: v for k, v in d.items() if k != "pdf"}
        voce["esito_breve"] = esito_breve(d)
        voce["pdf_b64"], voce["pdf_url"] = "", url_windows(d.get("pdf", ""))
        if incorpora:
            try:
                voce["pdf_b64"] = base64.b64encode(Path(d["pdf"]).read_bytes()).decode()
            except (OSError, KeyError):
                pass
        dati.append(voce)
    js = json.dumps(dati, ensure_ascii=False).replace("</", "<\\/")
    percorso.write_text(PAGINA.format(n=len(dati), intestazione=html.escape(intestazione), dati=js),
                        encoding="utf-8")
