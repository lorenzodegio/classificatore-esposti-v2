# Piano Fase 1 — Estrazione del testo su 10 documenti

Stato: proposta rivista (v2) dopo le risposte di Lorenzo. Nessun codice
scritto.

## 0. Punto di partenza (Fase 0, solo aggregati)

- Cartella documenti: 491 PDF; file Word/RTF da convertire: .docx 11, .doc
  <5, .rtf <5; .csv 10 (non aperti, ignorati).
- Pagine: 885 in totale; mediana 1, p90 3, massimo 12. Per documento:
  1 pagina 295, 2 pagine 122, 3-4 47, 5-8 22, 9-16 5. Nessun PDF non apribile.
- Dimensione: mediana 0,19 MB, p90 1,0 MB, massimo 9,1 MB, totale 229 MB.
- Strato di testo (solo presenza di caratteri, nessun contenuto letto): in
  tutte le pagine 387, solo in alcune 84, in nessuna 20.
  Attenzione: "ha caratteri" non vuol dire "leggibile digitalmente". Una
  scansione con OCR del fotocopiatore o un timbro digitale su un'immagine
  contano come "con testo". Per questo serve il controllo del punto 2.
- Sulla macchina gira già un Ollama di un altro progetto (`ats-ollama`), con
  `qwen3-vl:8b-instruct` (6,1 GB) e `qwen3-vl:30b-a3b-instruct` (19 GB). È su
  una rete Docker normale, con accesso a internet: la v2 non lo usa (vedi
  punto 3).

## 1. Struttura minima delle cartelle

Solo ciò che serve alla fase 1: il cerchio 1, passo 1 (estrazione). Nucleo,
predisposizione e cerchio 2 non si creano adesso.

```
classificatore-esposti-v2/            (codice; niente dati reali qui dentro)
  CLAUDE.md
  Dockerfile                          python:3.11-slim + pypdfium2, pdfplumber, Pillow,
                                      LibreOffice senza interfaccia e font compatibili Office
  docker-compose.yml                  servizi app, ollama, ollama-scarica (punto 3)
  config/
    estrazione.toml                   soglie, modello VLM, DPI, percorsi: tutte le costanti
  cerchio1/
    estrazione/
      converti.py                     Word/RTF -> PDF con LibreOffice, dentro /work
      leggibilita.py                  controllo deterministico per pagina (punto 2)
      digitale.py                     testo dallo strato digitale, senza IA
      vlm.py                          client Ollama, solo trascrizione (punto 3)
      estrai.py                       orchestra: PDF -> JSON del contratto
      contratto.schema.json           schema dell'uscita (punto 4)
  strumenti/
    scegli_campione.py                scelta dei 10 documenti (punto 5)
    revisione/                        generatore della pagina di revisione (punto 6)
    conteggi_giudizi.py               a Claude solo i conteggi
  tests/
    sintetici/genera.py               generatore di PDF finti
    test_*.py
  docs/
    piano_fase1.md                    questo file
    contratti/estrazione.md           contratto scritto, in prosa
    campioni/fase1.txt                hash dei 10 documenti scelti (nessun nome)
    errori_fase1.md                   tipi di errore segnalati, in astratto
```

Dati reali e uscite, fuori dal repository:

```
/home/lorenzo/vlm_pdf/documenti  ->  /data/esposti   (sola lettura; solo questa cartella)
/home/lorenzo/sire_lavoro/       ->  /work           (lettura/scrittura)
    indice_locale.json           doc_id -> percorso del file (resta qui, non esce)
    convertiti/<doc_id>.pdf      PDF ottenuti dai file Word/RTF
    estrazione/<doc_id>.json     uscite del contratto
    revisione/                   pagina di revisione e giudizi
```

`merged.csv` e la cartella superiore non vengono montati.

Docker: la v2 ha un suo Dockerfile, con dentro solo ciò che serve, e non usa
immagini di altri progetti (nemmeno `ats-pipeline-app`, usata solo come
ambiente Python per i conteggi della Fase 0). L'immagine si costruisce con
accesso a internet, senza documenti montati. I container che montano
`/data/esposti` stanno solo sulla rete interna `sire_interna`
(`internal: true`), senza uscita verso internet. I container girano con
l'utente 1000, così i file creati si possono cancellare da WSL senza
`find -delete`.

## 2. Controllo deterministico "leggibile digitalmente?" (per pagina)

I file Word/RTF arrivano qui già convertiti in PDF (vedi sotto) e passano
dallo stesso controllo.

Per ogni pagina, senza IA, si calcolano:

| Misura | Come |
|---|---|
| `caratteri` | caratteri non spaziali nello strato di testo (pypdfium2) |
| `quota_validi` | quota di caratteri "normali": lettere (anche accentate), cifre, punteggiatura comune. Esclude U+FFFD, uso privato, caratteri di controllo e glifi senza mappatura Unicode (font con codifica rotta) |
| `quota_parole` | quota di parole plausibili (lettere con almeno una vocale, lunghezza 1-25), senza dizionario |
| `copertura_immagini` | quota dell'area della pagina coperta da immagini (rettangoli delle immagini, pdfplumber) |
| `inchiostro` | quota di pixel scuri nella pagina resa a bassa risoluzione. Distingue una pagina bianca da una con contenuto |

Decisione per pagina (soglie di partenza, in `config/estrazione.toml`):

| Esito | Regola di partenza | Cosa si fa |
|---|---|---|
| `digitale` | caratteri ≥ 50, quota_validi ≥ 0,90, quota_parole ≥ 0,70, copertura_immagini < 0,15 | testo digitale |
| `digitale_con_immagini` | come sopra, ma copertura_immagini fra 0,15 e 0,70 | testo digitale + trascrizione VLM della pagina (es. screenshot o foto incollati) |
| `scansione_con_ocr` | caratteri ≥ 50 e copertura_immagini ≥ 0,70 | VLM; il testo OCR preesistente si conserva solo come confronto |
| `immagine` | caratteri < 50 oppure quota_validi < 0,90 oppure quota_parole < 0,70 | VLM |
| `vuota` | caratteri < 50 e inchiostro < 0,005 | nessuna trascrizione; segnalata come pagina vuota |

Queste soglie servono solo a smistare le pagine, non a decidere se
l'estrazione è accettabile. Se la revisione mostra pagine smistate male, le
soglie si correggono nel file di configurazione e si ripete il controllo.

### Conversione dei file Word/RTF

- `converti.py` copia il file originale in una cartella temporanea dentro
  `/work`, con un nome neutro (`<doc_id>.<est>`), così il nome reale non
  finisce nei messaggi di LibreOffice. Poi lancia
  `soffice --headless --convert-to pdf` con un profilo utente isolato in
  `/work`, macro disattivate e un tempo massimo per file. Il PDF risultante va
  in `/work/convertiti/<doc_id>.pdf`.
- Il `doc_id` è l'hash del file originale, non del PDF convertito: due
  conversioni dello stesso file possono dare PDF diversi a livello di byte.
- Dopo la conversione il file segue lo stesso percorso dei PDF. Di solito il
  testo risulta digitale; le immagini incollate nel documento (foto,
  screenshot) fanno scattare `digitale_con_immagini` e quindi la
  trascrizione VLM di quelle pagine.
- Se la conversione fallisce o va in tempo massimo, il documento esce con
  `senza_contenuto` e motivo `CONVERSIONE_FALLITA`.

## 3. VLM trascrittore in 16 GB di VRAM

**Scelta: `qwen3-vl:8b-instruct` su Ollama.** Occupa circa 6 GB e lascia
spazio al contesto di un'immagine ad alta risoluzione. Gestisce l'italiano e
la scrittura a mano. Si scarica una volta nell'Ollama della v2 (vedi sotto),
si controlla che il digest coincida con quello già visto in locale
(`0533d74300e4`) e lo si registra in ogni uscita.

Alternative, da valutare solo se la revisione mostra limiti:

| Modello | Pro | Contro |
|---|---|---|
| `qwen3-vl:30b-a3b-instruct` | più accurato | 19 GB: non sta in 16 GB di VRAM, quindi viola il vincolo. Escluso |
| `qwen2.5vl:7b` (Ollama) | maturo, stessa famiglia | da scaricare; in genere inferiore al successore |
| `gemma3:12b` (Ollama) | buona resa del testo stampato | da scaricare; meno affidabile sulla grafia a mano |
| Modelli specifici per OCR (olmOCR-2, dots.ocr, PaddleOCR-VL) | addestrati a trascrivere pagine | servono tramite vLLM, non Ollama (in locale c'è un'immagine vLLM); cambierebbe lo stack |

Come si usa:
- Una pagina per chiamata, resa con pypdfium2 a 200 DPI rispettando la
  rotazione del PDF, lato lungo al massimo 2000 px.
- Prompt fisso di sola trascrizione: trascrivi fedelmente, in ordine di
  lettura, mantieni gli a capo. Scrivi `[illeggibile]` dove non si legge.
  Niente riassunti, correzioni, traduzioni o commenti. Temperatura 0, limite
  massimo di token in uscita.
- Il VLM non decide nulla sul documento: riceve un'immagine e restituisce testo.

Documenti misti: la decisione si prende per pagina, quindi nello stesso
documento possono convivere pagine digitali e pagine trascritte dal VLM. Le
pagine si riassemblano nell'ordine originale e ognuna porta la sua modalità.

Documenti lunghi: il massimo trovato è 12 pagine. Con una chiamata per pagina
la lunghezza non pesa sul contesto del VLM. I documenti lunghi contano solo
sui tempi, e il testo di ogni pagina resta separato.

Ollama e rete (approvato):
- Nel compose della v2 c'è un servizio `ollama` (immagine ufficiale
  `ollama/ollama` con la versione fissata), collegato solo alla rete interna
  `sire_interna`. Riceve le immagini delle pagine, quindi conta come
  container che tocca i documenti e non ha uscita verso internet. Niente
  `OLLAMA_DEBUG`, quindi i prompt non finiscono nei log.
- I modelli si scaricano con un servizio separato `ollama-scarica`. Questo
  usa la rete normale, non monta né `/data/esposti` né `/work`, e scrive
  nella cartella dei modelli `/home/lorenzo/sire_modelli`. Il servizio
  `ollama` legge poi la stessa cartella.
- `ats-ollama` non si usa: appartiene a un altro progetto ed è collegato a
  internet. Va fermato mentre gira la v2, perché i due non stanno insieme nei
  16 GB di VRAM.

## 4. Contratto di uscita dell'estrazione

Un JSON per documento in `/work/estrazione/<doc_id>.json`, validato contro
`contratto.schema.json`:

```json
{
  "schema": "estrazione/1",
  "doc_id": "primi 16 caratteri esadecimali dello sha256 del file originale",
  "sha256": "...",
  "formato_origine": "pdf | docx | doc | rtf",
  "conversione": {"strumento": "libreoffice", "versione": "...", "esito": "ok"},
  "n_pagine": 3,
  "pagine": [
    {
      "n": 1,
      "modalita": "digitale | vlm | digitale+vlm | vuota",
      "smistamento": "digitale | digitale_con_immagini | scansione_con_ocr | immagine | vuota",
      "testo": "testo della pagina",
      "testo_vlm_immagini": "solo per digitale+vlm",
      "lettura_incerta": false,
      "motivi_incertezza": [],
      "misure": {"caratteri": 0, "quota_validi": 0.0, "quota_parole": 0.0,
                 "copertura_immagini": 0.0, "inchiostro": 0.0},
      "vlm": {"modello": "qwen3-vl:8b-instruct", "digest": "0533d74300e4",
              "dpi": 200, "troncato": false, "marcatori_illeggibile": 0,
              "ripetizioni": false, "secondi": 0.0}
    }
  ],
  "documento": {
    "acquisizione": "digitale | vlm | misto",
    "lettura_incerta": false,
    "pagine_incerte": [],
    "senza_contenuto": false
  },
  "esecuzione": {"versione_codice": "...", "hash_config": "...", "data": "..."}
}
```

- Niente nome del file né percorso. L'abbinamento `doc_id` -> file sta solo in
  `/work/indice_locale.json`. Servirà al cerchio 2 per il protocollo; il
  nucleo non lo vedrà mai.
- Il segnale di lettura incerta è deterministico, calcolato dal codice e non
  chiesto al modello. Motivi possibili:
  `DIGITALE_CARATTERI_ANOMALI` (codifica sospetta), `VLM_TRONCATO` (limite di
  token raggiunto), `VLM_RIPETIZIONI` (righe o frammenti ripetuti in ciclo),
  `VLM_ILLEGGIBILE` (il modello ha messo marcatori `[illeggibile]`),
  `VLM_TESTO_SCARSO` (poco testo a fronte di molto inchiostro sulla pagina),
  `VLM_DISACCORDO_OCR` (forte differenza dall'OCR preesistente, quando c'è),
  `VLM_ERRORE` (chiamata fallita).
- `conversione` è presente solo per i file Word/RTF; `n_pagine` e le pagine
  si riferiscono al PDF convertito.
- `senza_contenuto` vale true se tutte le pagine sono vuote o in errore, o se
  la conversione è fallita (`CONVERSIONE_FALLITA`). Il documento andrà poi
  all'operatore con questa etichetta.

## 5. Scelta dei 10 documenti senza vederne il contenuto

`strumenti/scegli_campione.py` gira su tutti i 491 PDF e sui circa 15 file
Word/RTF convertiti, e calcola solo le misure del punto 2 per pagina. Assegna
ogni documento a uno strato e ne estrae a caso, con seme fisso:

| Strato | Criterio (misure, non contenuto) | Quanti |
|---|---|---|
| Word/RTF | file convertito da .docx/.doc/.rtf | 1 |
| digitale breve | tutte le pagine `digitale`, 1-2 pagine | 1 |
| digitale lungo | tutte `digitale`, ≥ 5 pagine | 1 |
| catena di email | digitale, con ≥ 3 righe d'intestazione email (Da:/A:/Oggetto:/Inviato:/From:...) contate dallo script, mai stampate | 1 |
| scansione | tutte le pagine `immagine` o `scansione_con_ocr` | 2 |
| misto | pagine digitali e pagine VLM nello stesso documento | 2 |
| digitale con immagini | almeno una pagina `digitale_con_immagini` | 1 |
| scrittura a mano | vedi sotto | 1 |

La scrittura a mano non si riconosce con una regola affidabile. Proposta: lo
script produce una pagina locale con le miniature delle prime pagine dei
documenti scansionati candidati, in ordine casuale. La pagina sta in `/work`. Tu spunti quelli scritti a
mano e lo script ne sceglie uno a caso con seme fisso. Io vedo solo quanti ne
hai spuntati.

In chat escono solo i conteggi per strato e gli hash dei 10 documenti, che si
registrano in `docs/campioni/fase1.txt` insieme al seme. Se uno strato ha meno
documenti di quanti ne servono, lo script lo dice e prende dallo strato più
vicino.

## 6. Strumento di revisione locale

Approvato: una pagina HTML autonoma, generata dal container in
`/work/revisione/fase1.html`, da aprire in Edge da Windows
(`\\wsl.localhost\Ubuntu\home\lorenzo\sire_lavoro\revisione\fase1.html`).
Funziona senza server e senza rete: i PDF sono incorporati nella pagina (i
10 documenti pesano pochi MB).

- A sinistra il PDF, a destra il testo estratto della stessa pagina. Il
  cambio di pagina è sincronizzato.
- Per ogni documento: giudizio `ok / errore lieve / errore grave` e un campo
  nota libero. Facoltativi: le pagine con problemi e caselle di tipo di
  errore (parole sbagliate, righe mancanti, ordine di lettura sbagliato,
  testo inventato, timbri o intestazioni persi, tabelle rovinate, pagina
  smistata male), così poi si possono descrivere in astratto in
  `docs/errori_fase1.md`.
- Salvataggio: con il pulsante "Salva" il browser scrive
  `giudizi_fase1.json` in una cartella scelta da te, una volta sola
  (`/work/revisione/`).
- `strumenti/conteggi_giudizi.py` legge solo i campi giudizio e tipo di
  errore e stampa i conteggi completi: la regola "<5" non si applica ai
  giudizi. Non legge le note.

## 7. Cosa vedrai per ogni documento

- Il PDF e, accanto, il testo della stessa pagina, con gli a capo come
  estratti.
- Per ogni pagina, un'etichetta con la modalità (digitale, VLM, digitale+VLM,
  vuota) e lo smistamento. Così vedi subito se una pagina è stata smistata
  male, per esempio una scansione trattata come digitale.
- Per le pagine VLM, l'immagine esatta inviata al modello (risoluzione e
  rotazione comprese). Così si capisce se un errore viene dal modello o
  dall'immagine.
- I punti `[illeggibile]` evidenziati nel testo.
- Se la lettura è incerta, il motivo in parole semplici ("il modello si è
  ripetuto", "uscita troncata", "poco testo per tanta scrittura sulla
  pagina").
- Per le scansioni con OCR preesistente, il confronto affiancato fra OCR
  preesistente e trascrizione VLM, con le differenze evidenziate.
- Per i file Word/RTF, a sinistra c'è il PDF convertito con un'etichetta
  "convertito da .docx/.doc/.rtf". L'originale si può aprire a parte in Word
  per controllare che la conversione non abbia perso nulla.
- Le misure numeriche del punto 2 in un pannello "dettagli", chiuso di
  default, solo come contesto. Nessun verdetto automatico: il giudizio è tuo.

## 8. Test sintetici, tempi, rischi

### Test su dati sintetici (prima di toccare i reali)

`tests/sintetici/genera.py` crea PDF finti, con nomi, indirizzi e protocolli
inventati, che imitano i formati reali:
- lettera digitale di 1-2 pagine; documento digitale di 12 pagine;
- catena di email con intestazioni annidate;
- scansione senza testo (lettera digitale resa come immagine, con rumore,
  leggera rotazione e sfocatura);
- scansione con OCR preesistente (immagine + strato di testo invisibile);
- documento misto (pagine digitali + pagine immagine);
- pagina digitale con screenshot incollato;
- pagina con codifica rotta (caratteri di uso privato);
- file .docx, .doc e .rtf finti, generati con LibreOffice da testo
  sintetico: anche con immagine incollata, tabella, intestazione e piè di
  pagina, commenti e revisioni tracciate; più un file danneggiato;
- pagina bianca; pagina ruotata di 90°;
- scrittura a mano: 2-3 pagine con contenuto inventato, scritte a mano e
  scansionate da Lorenzo (approvato).

Test:
- conversione: i file Word/RTF sintetici diventano PDF con il testo atteso;
  il file danneggiato dà `CONVERSIONE_FALLITA` senza bloccare gli altri;
- rete: dal container dell'app la rete interna raggiunge Ollama, mentre un
  indirizzo esterno non risponde;
- smistamento: ogni pagina sintetica finisce nella categoria attesa;
- contratto: ogni uscita rispetta lo schema; il `doc_id` non dipende dal nome
  del file;
- privacy: una stringa-sentinella nel nome e nel contenuto dei sintetici non
  deve comparire in stdout, nei log o nei conteggi;
- VLM finto (senza GPU): rilevamento di troncamento, ripetizioni e marcatori;
- VLM vero sui sintetici: per conoscere i tempi e controllare a vista che
  trascriva senza riassumere. Sui sintetici il testo vero è noto: la
  differenza misurata serve solo come diagnostica durante lo sviluppo, non
  come criterio di accettazione.

### Tempi (stime)

- Sviluppo: Dockerfile/compose (reti, Ollama, download del modello) e
  generatore sintetico; poi conversione Word/RTF, smistamento ed estrazione
  digitale; poi VLM e contratto; poi scelta del campione; infine la pagina di
  revisione. Circa 5 sessioni di lavoro, ognuna chiusa con un controllo sui
  sintetici.
- Una tantum: build dell'immagine (LibreOffice aggiunge circa 0,5-1 GB) e
  download del modello (circa 6 GB).
- Conversione Word/RTF: pochi secondi per file, quindi circa 15 file in
  qualche minuto.
- Esecuzione sui 10 documenti: con qwen3-vl 8B sulla 5060 Ti stimo 15-40
  secondi per pagina VLM. Su circa 20-30 pagine, di cui meno della metà VLM,
  sono pochi minuti. Il tempo vero si misura sui sintetici.
- Per la fase 2 (885 pagine; VLM su una parte stimata fra 150 e 400 pagine)
  l'ordine di grandezza è 1-4 ore. Da rimisurare dopo la fase 1.

### Rischi

- Testo inventato dal VLM: dove la grafia è difficile, il modello può
  scrivere parole plausibili invece di `[illeggibile]`, oppure "correggere" o
  riassumere. Si mitiga con prompt di sola trascrizione, temperatura 0 e
  immagine visibile in revisione. Resta il rischio principale e lo vedrai
  solo confrontando a occhio.
- Smistamento sbagliato: OCR del fotocopiatore scambiato per testo digitale,
  firme o timbri digitali su un'immagine, codifiche rotte non riconosciute.
- Cicli di ripetizione e troncamenti del VLM, soprattutto su tabelle e
  moduli.
- Pagine ruotate o scansioni storte, che il VLM può leggere male.
- Riproducibilità: un aggiornamento di Ollama o del modello cambia i
  risultati. Per questo si registra il digest; aggiornamenti solo con il tuo
  OK.
- Privacy della pagina di revisione: contiene PDF e testi reali, quindi resta
  in `/work`, mai nel repository.
- Conversione Word/RTF: LibreOffice può impaginare in modo diverso da Word.
  Può anche perdere o mostrare in modo diverso caselle di testo, commenti,
  revisioni tracciate, oggetti incorporati e font mancanti. I .doc molto
  vecchi possono non aprirsi. Si mitiga con i test sintetici dedicati, con i
  font compatibili Office nell'immagine e con l'etichetta "convertito" in
  revisione.
- File Word/RTF come vettore: possono contenere macro o collegamenti
  esterni. Si mitiga con macro disattivate, profilo isolato e nessuna rete
  nel container.

## Decisioni prese (risposte di Lorenzo)

1. Rete Docker interna `internal: true` fra container e Ollama. Internet
   solo per build e download dei modelli, mai dai container con i documenti.
2. Cartella di lavoro `/home/lorenzo/sire_lavoro` montata come `/work`.
3. Revisione con una pagina HTML autonoma, senza server.
4. Regola "<5" solo sui conteggi ricavati dai documenti, non sui giudizi.
5. Scrittura a mano per i test: 2-3 pagine inventate preparate da Lorenzo.
6. I file Word/RTF entrano nella fase 1 (conversione con LibreOffice in
   `/work`); almeno uno fra i 10 documenti di prova.
7. Dockerfile proprio della v2; nessuna immagine di altri progetti.

## Dettagli nuovi da guardare insieme all'OK

- Ollama: servizio proprio della v2 sulla sola rete interna, modelli in
  `/home/lorenzo/sire_modelli`, scaricati con un servizio separato collegato
  a internet. `ats-ollama` va fermato mentre gira la v2.
