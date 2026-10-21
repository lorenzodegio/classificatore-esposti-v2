# Consegna del motore (classificatore-esposti-v2) — 11/10/2026, aggiornata il 21/10/2026

Per chi collega il motore all'applicazione (`applicazione-completa-esposti`). Stato al
momento della consegna: prototipo funzionante dall'inizio alla fine, provato sui ~500
documenti reali di ATS. Le misure qui sotto sono aggregate; dettagli in `docs/stato.md`.

**In una frase:** il motore legge un documento (PDF, Word, scansione, anche a mano), ne
ricava il testo per pagina, compila la scheda ATS con le frasi che la giustificano e
propone esito, urgenza e azione, più i temi del fascicolo. Dal 21/10/2026 è anche un
servizio HTTP conforme al contratto 1.2 (sezione 4); la sua decisione non è più affidabile
di "accogli sempre": va usata come **proposta** da confermare, mai come decisione.

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
| Cerchio 1, frasi per voce | `cerchio1/frasi_voci.py`, `cerchio1/ancora.py` | per ogni voce spuntata la frase che la giustifica (LLM) e la pagina dove si trova (ritrovata nel testo, senza modello) |
| Cerchio 1, temi | `cerchio1/temi.py`, `config/temi.toml` | temi del fascicolo con motivo, frase e pagina (LLM) |
| Cerchio 2, contratto | `cerchio2/tipo_documento.py`, `cerchio2/protocollo.py`, `cerchio2/contratto_v1.py` | tipo nel vocabolario del contratto (inoltro, integrazione), protocollo dal testo, adattatore al risultato 1.2 |
| Servizio | `servizio/` | HTTP (FastAPI), un documento alla volta, contratto 1.2 |
| Orchestrazione | `prototipo.py`, `estrai_tutti.py` | esecuzione a lotti |
| Strumenti | `strumenti/` | confronto con merged.csv, impronta della configurazione, controllo prima della pubblicazione |

Configurazione: `config/estrazione.toml` (modelli, digest attesi, soglie), Ollama fissato a
0.40.1 in `docker-compose.yml`. La configurazione misurata sulla metà di verifica ha
impronta `133c0a34f6f86d6c` (`python strumenti/impronta_config.py`); con il servizio HTTP (21/10/2026)
l'impronta è `5ffcd75227630b09` (motivo in `docs/stato.md`).

### Provarlo sui dati sintetici

```bash
docker compose build app                                   # con internet, senza documenti
MODELLO=gemma4:12b docker compose --profile scarica run --rm ollama-scarica
MODELLO=qwen3-vl:8b-instruct docker compose --profile scarica run --rm ollama-scarica
docker compose up -d ollama                                # solo rete interna
docker compose run --rm prova python -m pytest -q          # test senza GPU (anche il servizio)
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

## 4. Collegamento con l'applicazione (`docs/contratto_motore.md`, versione 1.2)

**Aggiornato il 21/10/2026: il servizio HTTP esiste** (`servizio/`, servizio `motore` nel
`docker-compose.yml`). Le scelte fatte sono nel [diario](diario.md); misure in
[stato](stato.md#servizio-http-21102026).

### 4.0 Avvio e prova

```bash
docker compose build motore                     # con internet, senza documenti
docker compose up -d motore                     # avvia anche ollama; http://motore:8080 su esposti_interna
docker compose run --rm prova python -m pytest -q                 # test senza GPU
docker compose run --rm prova python tests/prova_motore_vero.py   # catena vera via HTTP, Ollama, sintetici
```

Il servizio `motore` sta sulle reti `sire_interna` (con Ollama) ed `esposti_interna`
(esterna, condivisa con l'applicazione), entrambe interne; nessuna porta sull'host; nessuna
cartella di documenti o di lavoro montata (il documento arriva nella richiesta, sta in un
tmpfs e si cancella a fine analisi; il risultato resta in memoria fino al `DELETE`).
Log: identificativo del lavoro, tempi, conteggi e codici di errore.

### 4.1 Risultato: corrispondenza campo per campo

| Campo del contratto | Da dove viene | Stato |
|---|---|---|
| `versione_contratto`, `versione_motore` | `"1.2"` (accetta metadati con qualunque `1.x`), `config/servizio.toml` (`2.2.0`) | colmato |
| `documento.id`, `sha256` | eco dei metadati; sha256 verificato (`422 impronta_non_coincide`) | colmato |
| `tipo_documento.valore` | scheda + `cerchio2/tipo_documento.py` (inoltro / integrazione) | colmato: tutti e 7 i codici |
| `tipo_documento.motivo` | LLM, una frase per l'operatore | colmato |
| `protocollo` | `cerchio2/protocollo.py`: dal testo (numero `0005120/2025`, data ISO, frase, pagina); ripiego dal nome del file | colmato; anno solo se scritto nel documento, altrimenti numero senza "/AAAA" e data null; ripiego dal nome: numero senza anno, data null, frase "(nome del file) …", pagina 1 |
| `pagine[].numero`, `testo` | estrazione | colmato |
| `pagine[].acquisizione` | `digitale`→`testo_nativo`, `vlm`→`ocr`, `vuota`→`nessuna` | **`ocr_manoscritto` mai prodotto** |
| `pagine[].lettura_incerta`, `motivo_incertezza` | divergenza fra i lettori e segnali, frase per l'operatore | colmato |
| `lettura_incerta` | almeno una pagina incerta | colmato |
| `scheda.data_doc`, `comune` | scheda + giustificazione, data ISO, pagina ritrovata nel testo | colmato |
| `scheda.ambito[]`, `problematica[]`, `elementi[]` | voci della scheda; frase per voce da `cerchio1/frasi_voci.py`; pagina e frase letterale da `cerchio1/ancora.py`; ≤ 300 caratteri | colmato |
| `scheda.*_altro` | `ambito_altro`, `prob_altro`→`problematica_altro`, `elementi_altro` | colmato |
| `proposta.esito`, `urgenza`, `azione` | decisione (stessi vocabolari) | colmato |
| `proposta.motivo` | note della decisione + frase determinante | colmato |
| `proposta.domanda_decisiva` | domanda breve per regola (1, 2, 3, 5) | colmato |
| `proposta.da_verificare_sull_originale` | "Pagina N: lettura incerta, leggere l'originale." | colmato (solo pagine incerte) |
| `temi[]` | `cerchio1/temi.py`, vocabolario `config/temi.toml`, motivo, frase, pagina | colmato |
| — | `segnalante`, `destinatari`, `luogo`, `animali`, `da_quando` della scheda | non inviati (dati personali, il contratto non li prevede) |

Vocabolari: `ambito` è l'elenco attuale (Medicina Veterinaria, Igiene pubblica,
Disturbo/rumori, ARPA, Altro); `problematica`, `elementi`, `esito`, `urgenza`, `azione`
coincidono con il modulo ATS; `tema`: Cani, Gatti e colonie feline, Animali da reddito,
Avvelenamenti; `tipo_documento`: i 7 codici del contratto.

### 4.2 Trasporto ed errori

| Contratto | Il motore |
|---|---|
| `GET /v1/salute`, `POST/GET/DELETE /v1/analisi` | sì; `salute` riporta anche i digest dei modelli (`stato: non_pronto` se Ollama manca o i digest non coincidono) |
| un lavoro alla volta, `429` + `Retry-After`, idempotenza su `id_lavoro` | sì (`Retry-After: 30`) |
| formati | PDF, `.docx`, `.doc`, `.rtf`, immagini (PNG, JPEG, TIFF); **manca `.eml`** |
| non conservare documento e testo dopo `DELETE` | documento cancellato a fine analisi; risultato in memoria fino al `DELETE` (al massimo 24 ore) |
| errori codificati | `formato_non_supportato`, `documento_illeggibile`, `impronta_non_coincide`, `tempo_scaduto` (30 min), `occupato`, `errore_interno`; `richiesta_non_valida` (`422`, metadati malformati: nel contratto dalla 1.2) |
| avanzamento (`pagine_lette`, `pagine_totali`) | sì, per pagina |

## 5. Cosa resta

1. **`.eml`**: non gestito (`formato_non_supportato`). Serve un passo che estragga corpo e
   allegati (gli allegati sono a loro volta documenti).
2. **`ocr` / `ocr_manoscritto`**: il motore non distingue lo stampato scansionato dal
   manoscritto; ogni pagina trascritta è `ocr`. La divergenza fra i lettori separa bene i
   due casi sui sintetici (0–1% contro 12–19%) ma non è stata verificata come criterio sui
   reali: va deciso con Lorenzo.
3. **Protocollo**: regole sulle forme viste nei sintetici; da verificare sui reali (solo
   conteggi) quante volte si legge dal testo e quante si ripiega sul nome del file.
4. **Frasi e temi**: due chiamate LLM in più per documento (più quella del tipo). Qualità da
   rivedere da Lorenzo sui reali con lo strumento di revisione; per ora provata solo sui
   sintetici.
5. **Pulizia dell'involucro email** (fase prevista in `CLAUDE.md`): non ancora fatta.
6. **Qualità della decisione**: vedi sezione 3; non tarare di nuovo sulla metà di verifica.
7. **Contratto 1.2** (21/10/2026): `richiesta_non_valida`, `acquisizione` sempre `ocr`, frase
   convenzionale del protocollo dal nome del file e `.eml` non supportato sono ora scritti nel
   contratto; un numero di protocollo senza "/AAAA" vale come anno non noto.
8. **Stato in memoria**: un riavvio del servizio perde i lavori in corso e i risultati non
   ancora confermati; l'applicazione li vede come `404` (`errore_interno`, ritentabile) e ripete il lavoro.
