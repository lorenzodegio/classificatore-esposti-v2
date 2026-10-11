# Consegna del motore (classificatore-esposti-v2) — 11/10/2026

Per chi collega il motore all'applicazione (`applicazione-completa-esposti`). Stato al
momento della consegna: prototipo funzionante dall'inizio alla fine, provato sui ~500
documenti reali di ATS. Le misure qui sotto sono aggregate; dettagli in `docs/stato.md`.

**In una frase:** il motore legge un documento (PDF, Word, scansione, anche a mano), ne
ricava il testo per pagina, compila la scheda ATS con le frasi che la giustificano e
propone esito, urgenza e azione. Oggi è uno script a lotti, non ancora un servizio, e la
sua decisione non è più affidabile di "accogli sempre": va usata come **proposta** da
confermare, mai come decisione.

---

## 1. Regole che valgono anche per te (non negoziabili)

- I documenti reali contengono dati di cittadini. Restano **solo sulla workstation ATS**
  (`/home/lorenzo/vlm_pdf/documenti`, `/home/lorenzo/sire_lavoro`). Non vanno copiati,
  allegati a issue, incollati in chat o in log, né inviati a servizi esterni (LLM o OCR in
  cloud, telemetria). Lo stesso vale per testi estratti, nomi dei file e protocolli.
- Si sviluppa e si prova **solo su dati sintetici** (`tests/dati_sintetici/`, contenuti
  inventati). Sui dati reali si lavora soltanto con script che stampano aggregati
  (conteggi, percentuali; celle sotto 5 mostrate come "<5").
- Rete: i container che vedono i documenti stanno **solo** sulla rete Docker interna
  (`internal: true`), senza internet, e parlano solo con Ollama. Internet serve solo per
  build e download dei modelli, in container senza documenti (`ollama-scarica`).
- Modelli solo locali, serviti da Ollama, uno alla volta in 16 GB di VRAM.
- `merged.csv` (valutazioni manuali ATS) non si legge senza OK di Lorenzo; finora sono
  stati usati solo aggregati.
- `docs/procedure/` contiene documenti interni ATS: non sono nel repository (vedi il
  README lì dentro). Il `.gitignore` esclude PDF, Word, CSV e immagini fuori da
  `tests/dati_sintetici/`.
- Prima di ogni push: `strumenti/controllo_pubblicazione.py` (sulla workstation)
  confronta il repository con i dati reali e stampa solo conteggi.
- Commit e push solo con OK di Lorenzo; `CLAUDE.md` contiene le istruzioni operative.

## 2. Com'è fatto: nucleo e cerchi

Ogni cerchio conosce solo il contratto di quello più interno; il nucleo non vede PDF,
nome del file, protocollo né metadati.

| Parte | Codice | Cosa fa |
|---|---|---|
| Cerchio 1, estrazione | `cerchio1/estrazione/` | controllo deterministico "leggibile digitalmente?" per pagina (`leggibilita.py`); testo nativo se leggibile; altrimenti due lettori VLM: `gemma4:12b` (testo in uscita) e `qwen3-vl:8b-instruct` (solo per misurare la divergenza); pagina "lettura incerta" se divergono ≥ 5% delle parole; Word/RTF convertiti con LibreOffice (`converti.py`) |
| Cerchio 1, scheda | `cerchio1/scheda.py` | `gemma4:12b` compila la scheda (tipo documento, data, comune, segnalante, destinatari, luogo, animali, da quando, ambito, problematica, elementi) con valori del modulo ATS (`config/scheda_ats.toml`) e frase giustificativa per campo |
| Nucleo, decisione | `nucleo/decisione.py` | l'LLM risponde alle domande della direzione (`config/criteri_decisione.md`: competenza, destinatario, completezza, urgenza, valutabilità), regole Python le applicano in ordine; esito, urgenza, azione, domanda determinante e frase |
| Cerchio 2, consegna | `cerchio2/consegna.py` | protocollo e data dal nome del file, collegamento esposto–riscontro per protocollo, JSON per documento, report PDF, pagina HTML di revisione |
| Orchestrazione | `prototipo.py`, `estrai_tutti.py` | esecuzione a lotti |
| Strumenti | `strumenti/` | confronto con merged.csv, impronta della configurazione, controllo prima della pubblicazione |

Configurazione: `config/estrazione.toml` (modelli, digest attesi, soglie), Ollama fissato a
0.40.1 in `docker-compose.yml`. La configurazione misurata sulla metà di verifica ha
impronta `133c0a34f6f86d6c` (`python strumenti/impronta_config.py`).

### Provarlo sui dati sintetici

```bash
docker compose build app                                   # con internet, senza documenti
MODELLO=gemma4:12b docker compose --profile scarica run --rm ollama-scarica
MODELLO=qwen3-vl:8b-instruct docker compose --profile scarica run --rm ollama-scarica
docker compose up -d ollama                                # solo rete interna
docker compose run --rm test python -m pytest -q           # 14 test, senza GPU
docker compose run --rm test python tests/vlm_contro_verita.py   # due lettori contro la verità
docker compose run --rm test python prototipo.py sintetici       # catena completa
```

Uscite in `/home/lorenzo/sire_lavoro/sintetici/prototipo/sintetici/` (`revisione.html`,
`report.pdf`, `documenti/*.json`). I percorsi in `docker-compose.yml` sono quelli della
workstation ATS: su un'altra macchina vanno adattati (cambia l'impronta della
configurazione, va bene per lo sviluppo).

## 3. Cosa funziona e cosa no

Misure sui documenti reali, confrontate con le valutazioni degli operatori (merged.csv),
divise in metà di taratura e di verifica (151 + 151 documenti). La metà di verifica è stata
misurata **una sola volta**, a configurazione congelata.

| Esposti e richieste di ente | Verifica |
|---|---|
| Esito (Accolto / Invio Modulo / non si procede): motore | **62%** |
| stesso, scrivendo sempre "Accolto" | **64%** |
| Urgenza: motore / sempre "Normale" | 49% / 53% |
| Quando il motore non accoglie, anche gli operatori non accolgono | 50% (11 su 22) |

Quindi: **sull'esito il motore non batte "sempre Accolto"**. La sua uscita è una proposta che
l'operatore conferma o corregge, e il valore pratico oggi è nella scheda con le frasi
giustificative e nel segnalare i casi dubbi, non nella decisione.

Funziona bene:
- estrazione: 457 documenti distinti, 836 pagine, nessun PDF non apribile; Word/RTF convertiti;
- segnale di lettura incerta: separa nettamente stampa (0–1% di divergenza) e scrittura a
  mano (12–19%) sui sintetici; sui reali marca un documento su quattro;
- Ambito "Medicina Veterinaria" in accordo con gli operatori nel 90% dei casi.

Non funziona ancora:
- archiviazioni: gli operatori archiviano circa un quinto degli esposti, il motore quasi mai;
- urgenza sotto il riferimento "sempre Normale";
- la scheda spunta troppo spesso alcune voci (Foto/allegati, Maltrattamento, Inidonea detenzione);
- riscontri con contenuto negli allegati finiscono in "Da approfondire";
- gli operatori stessi variano molto (quota di accolti dal 50% a oltre l'80%): parte del
  disaccordo è rumore, parte è che le loro valutazioni precedono i criteri scritti attuali.

## 4. Collegamento con l'applicazione (`docs/contratto_motore.md`, versione 1.0)

Il contratto prevede un servizio HTTP asincrono (`/v1/salute`, `/v1/analisi`) che riceve un
documento e restituisce un risultato. Il motore oggi produce un JSON per documento (in
`/work/prototipo/<esecuzione>/documenti/<doc_id>.json`) con nomi diversi. Corrispondenza:

### 4.1 Risultato

| Campo del contratto | Il motore oggi | Nome attuale | Cosa manca |
|---|---|---|---|
| `versione_contratto`, `versione_motore` | no | — | da aggiungere |
| `documento.id` | no | — | eco dell'id ricevuto nei metadati |
| `documento.sha256` | sì | `sha256` | verifica contro l'impronta inviata (`422 impronta_non_coincide`) |
| `tipo_documento.valore` | sì, vocabolario diverso | `scheda.tipo_documento` (`esposto`, `riscontro ATS`, `lettera avvocato`, `richiesta ente`, `altro`) | conversione a `esposto`, `richiesta_ente`, `riscontro_ats`, `altro`; il motore non distingue `inoltro_per_competenza` e `integrazione`; il contratto non ha `lettera avvocato` |
| `tipo_documento.motivo` | in parte | `scheda.giustificazioni.tipo_documento` (frase, non motivo) | motivo in italiano semplice |
| `protocollo.numero`, `data` | in parte | `protocollo`, `data_nome` (dal **nome del file**, numero senza zeri iniziali né anno) | lettura dal testo del documento, formato `0005120/2025`, data ISO |
| `protocollo.frase`, `pagina` | no | — | da aggiungere con la lettura dal testo |
| `pagine[].numero`, `testo` | sì | `pagine[].n`, `pagine[].testo` | rinomina |
| `pagine[].acquisizione` | in parte | `pagine[].modalita`: `digitale` / `vlm` / `vuota` | `digitale`→`testo_nativo`, `vuota`→`nessuna`; per `vlm` il motore non distingue `ocr` da `ocr_manoscritto` |
| `pagine[].lettura_incerta` | sì | `pagine[].lettura_incerta` | — |
| `pagine[].motivo_incertezza` | in parte | `pagine[].avviso`, `segnali`, `divergenza_pct` | frase per l'operatore |
| `lettura_incerta` | sì | `documento.lettura_incerta` | — |
| `scheda.data_doc` | in parte | `scheda.data_doc` (gg/mm/aaaa) + `giustificazioni.data_doc` | formato ISO, `pagina` |
| `scheda.comune` | in parte | `scheda.comune` + `giustificazioni.comune` | `pagina` |
| `scheda.ambito[]`, `problematica[]`, `elementi[]` | in parte | liste di valori + **una** frase per campo in `giustificazioni` | frase e pagina **per ogni voce**; limite di 300 caratteri |
| `scheda.ambito_altro`, `elementi_altro` | sì | stessi nomi | — |
| `scheda.problematica_altro` | sì | `scheda.prob_altro` | rinomina |
| `proposta.esito`, `urgenza`, `azione` | sì | `decisione.esito`, `urgenza`, `azione` | — (stessi vocabolari) |
| `proposta.motivo` | in parte | `decisione.note` | motivo più discorsivo |
| `proposta.domanda_decisiva` | in parte | `decisione.determinante` (codice 1–5) + `frase_determinante` | testo della domanda (disponibile in `nucleo/decisione.py`, `DOMANDE`) |
| `proposta.da_verificare_sull_originale` | in parte | `decisione.da_verificare_sull_originale` (vero/falso) | elenco delle cose da controllare (oggi si può dare almeno "pagina N: lettura incerta") |
| `temi[]` | **no** | — | passo nuovo: tema per il fascicolo (vocabolario `tema`) con motivo, frase e pagina |
| — | sì, non previsto | `scheda.segnalante`, `destinatari`, `luogo`, `animali`, `da_quando`, `collegati`, `doc_id`, `formato_origine` | il contratto li ignora; attenzione: contengono dati personali |

Vocabolari: `esito`, `urgenza`, `azione` coincidono. Per `ambito`, `problematica`,
`elementi` (nel contratto "da fissare") il motore usa `config/scheda_ats.toml`: Ambito
Medicina Veterinaria, Igiene pubblica, Disturbo/rumori, ARPA, Altro; le altre voci sono
quelle del modulo ATS. L'esempio 6.1 del contratto usa "Benessere animale", che non è tra
le voci del modulo.

### 4.2 Trasporto ed errori

| Contratto | Il motore oggi |
|---|---|
| `GET /v1/salute`, `POST/GET/DELETE /v1/analisi` | no: script a lotti su una cartella |
| un lavoro alla volta, `429` se occupato, idempotenza su `id_lavoro` | no |
| formati: PDF, immagine, `.eml`, `.docx` | PDF, `.docx`, `.doc`, `.rtf`; **mancano** immagini ed `.eml` |
| non conservare documento e testo dopo `DELETE` | no: oggi scrive tutto in `/work` |
| errori codificati (`formato_non_supportato`, `documento_illeggibile`, …) | in parte: campo `blocco` testuale (conversione fallita, senza contenuto, errore di scheda/decisione) |
| avanzamento (`pagine_lette`, `pagine_totali`) | no (solo log aggregato in `estrai_tutti.py`) |

## 5. Cosa manca di sicuro e proposta per il servizio (non implementata)

1. **Servizio invece di lotti.** Proposta:
   - nuovo servizio `motore` nel `docker-compose.yml` del motore, stessa immagine più un
     piccolo server HTTP (per esempio FastAPI + uvicorn, aggiunti al `Dockerfile` in build);
   - reti: `sire_interna` (verso Ollama) e una seconda rete interna condivisa con il worker
     dell'applicazione, entrambe `internal: true`; nessuna porta pubblicata sull'host;
   - un solo lavoro alla volta (un worker in un thread, stato in memoria); `429` con
     `Retry-After` se occupato; `id_lavoro` come chiave di idempotenza;
   - il documento ricevuto va in una cartella temporanea su `tmpfs` (memoria, non disco),
     si verifica lo `sha256`, si esegue la stessa catena di `prototipo.py` su un documento
     (estrazione con le due passate sulle sue pagine, scheda, decisione, temi), si traduce
     l'uscita nel formato del contratto con un modulo adattatore in `cerchio2/`
     (per esempio `contratto_v1.py`), si conserva il risultato in memoria fino al `DELETE`,
     poi si cancella tutto;
   - con un documento alla volta le due passate alternano i due modelli: o si tengono
     entrambi in memoria (`OLLAMA_MAX_LOADED_MODELS=2`, circa 14 GB, da verificare con il
     contesto) o si accetta il tempo di ricaricamento;
   - log solo con identificativi, tempi e codici di errore, mai testo o nomi di file;
   - `GET /v1/salute` riporta versione del motore, del contratto e digest dei modelli.
2. **Temi del fascicolo** (`temi[]`): non esistono; serve un passo LLM sulla scheda con il
   vocabolario `tema` del contratto.
3. **Protocollo dal testo**: oggi viene solo dal nome del file.
4. **Frase e pagina per ogni voce della scheda**: oggi una frase per campo, senza pagina.
5. **Formati**: immagini (si possono trattare come PDF di una pagina) ed `.eml`.
6. **Pulizia dell'involucro email** (fase prevista in `CLAUDE.md`): non ancora fatta;
   oggi la scheda la ignora solo su istruzione del prompt.
7. **Qualità della decisione**: vedi sezione 3; non tarare di nuovo sulla metà di verifica.
