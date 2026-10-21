# classificatore-esposti-v2 (S.I.R.E.)

Pipeline locale e air-gapped per il Dipartimento di Prevenzione Veterinaria di
ATS Insubria. Legge i PDF degli esposti e delle segnalazioni (digitali e
scansionati), ne ricava il contenuto, li classifica in motivati / immotivati
secondo le procedure ufficiali ATS (Rev. 01.02.2024), collega esposto e
riscontro tramite protocollo, produce un JSON per documento e un report PDF.
Scopo: gli operatori leggono solo gli esposti motivati.

Questo progetto riparte da zero. Non esiste codice precedente da riusare e non
si danno per buoni etichette, partizioni o risultati di lavori passati. Si
costruisce e si verifica un pezzo alla volta, partendo dal preprocessing.

Questo file contiene solo istruzioni operative correnti. Piani e analisi vanno
in `docs/`. Non riscrivere questo file con materiale di pianificazione.

Stato (11/10/2026): prototipo end-to-end completo, a lotti; consegnato a Khalil
per il collegamento con l'applicazione (`applicazione-completa-esposti`, che
definisce il contratto in `docs/contratto_motore.md`). Vedi `docs/consegna.md`
(architettura, limiti, corrispondenza campo per campo con il contratto,
proposta di servizio) e `docs/stato.md` (misure). Repository GitHub
`lorenzodegio/classificatore-esposti-v2`, rami `master` (consegna) e `dev`.
Dal 21/10/2026 (ramo `dev`) anche servizio HTTP (`servizio/`, servizio `motore`) conforme
al contratto 1.2; decisioni in `docs/diario.md`.

## Pubblicazione (GitHub)

- Prima di ogni commit o push: `strumenti/controllo_pubblicazione.py` (container
  senza rete, documenti/merged.csv/`/work` in sola lettura) confronta il
  repository con nomi, protocolli, identificativi e valori liberi reali e stampa
  solo conteggi e percorsi del repository.
- Il `.gitignore` esclude PDF, Word, RTF, CSV e immagini fuori da
  `tests/dati_sintetici/`, uscite, cache, modelli, `.env` e `docs/procedure/`
  (documenti interni ATS: resta solo `docs/procedure/README.md`).

## Privacy (vincoli non negoziabili)

- I documenti sono reali e contengono dati di cittadini. PDF, testo estratto,
  nomi di file, nomi, email, indirizzi e numeri di protocollo restano SOLO su
  questa macchina.
- Non stampare mai in chat, nei log o nei report il contenuto dei documenti, i
  nomi dei file o i protocolli. Non usare `cat`, `head`, `Read` o simili su PDF,
  testi estratti o CSV con dati reali per "dare un'occhiata".
- Fuori dagli script escono solo conteggi, percentuali e hash. Celle sotto 5
  mostrate come "<5"; nascondi anche le celle ricavabili per differenza. La
  regola "<5" vale per i conteggi ricavati dai documenti, non per i conteggi
  dei giudizi di revisione di Lorenzo.
- Rete: internet si può usare per ciò che non riguarda i documenti (scaricare
  modelli, pacchetti, immagini Docker, consultare documentazione). I documenti
  e tutto ciò che ne deriva non escono mai dalla macchina: si elaborano solo
  con modelli locali serviti da Ollama.
- I container che leggono i documenti non hanno accesso a internet: parlano
  con Ollama solo tramite una rete Docker interna (`internal: true`). Download
  e installazioni si fanno in fase di build o in container separati, senza la
  cartella dei documenti montata.
- Nessun servizio esterno (API, OCR o LLM in cloud, telemetria) riceve mai
  testo, immagini o nomi di file dei documenti.
- Nessun commit e nessun push senza OK esplicito. Mostra sempre il diff prima.
- Sviluppo e test si fanno su dati sintetici che imitano i formati reali; i
  dati reali si toccano solo tramite script che emettono aggregati.

## Architettura: nucleo e cerchi

Regola di dipendenza: ogni cerchio conosce solo il contratto di quello più
interno. Il nucleo non conosce nulla di ciò che sta fuori. Ogni passaggio ha un
contratto di ingresso e uscita scritto, così si può sostituire un pezzo senza
toccare gli altri.

### Nucleo: classificatore
- Riceve SOLO l'uscita della predisposizione (cerchio 1, passo 2). Non vede il
  PDF, il nome del file, il protocollo, i metadati.
- Restituisce esito (motivato / immotivato), punteggio e motivazione leggibile
  dall'operatore.
- "Motivato" secondo le procedure: situazione di competenza del Servizio
  Veterinario, descritta con elementi sufficienti (circostanziata) per aprire
  un procedimento.
- Il tipo di modello è una decisione aperta (vedi sotto).
- Criteri scritti della direzione del servizio (10/10/2026), in
  `config/criteri_decisione.md`; l'LLM risponde alle domande, le regole in
  `nucleo/decisione.py` le applicano in ordine:
  1. Competenza: Medicina Veterinaria prosegue; altra autorità (Polizia
     Locale/Forze dell'Ordine, Comune, ARPA, Ordine dei veterinari, altro) →
     esito "Altro", azione "Trasmissione ad altro ente", ente nelle Note.
  2. Destinatario: indirizzato ad altra autorità per competenza e ad ATS per
     conoscenza → "Archiviato" (anche con urgenza alta), motivo nelle Note.
  3. Completezza: indispensabili solo chi segnala (identificabile), dove e
     cosa → "Accolto"; altrimenti "Invio Modulo" con l'elenco di cosa manca.
     "Da quando" o recapito mancanti si annotano nelle Note senza cambiare
     l'esito. Non si applica ai riscontri ATS.
  4. Urgenza: Normale; Alta/Immediata solo con segnali espliciti (ferite o
     sofferenza grave, veleno, animale in fin di vita, pericolo per le
     persone); sporcizia, odori, catena, magrezza generica restano Normale.
     −1 livello se la condotta dura da mesi/anni, −1 se un'altra autorità è
     già attivata o lo sarà in automatico.
  5. "Da approfondire" solo per testo assente o contenuto negli allegati. La
     lettura incerta non cambia la decisione: la marca "da verificare
     sull'originale".
  Azione di partenza per esito: dalla metà di taratura
  (`config/azioni_per_esito.json`). La scheda spunta Problematica/Elementi
  solo se una frase lo afferma esplicitamente; "Foto/allegati" solo se citati.
  Ogni decisione riporta la domanda determinante e la frase che la giustifica.
  Ambito del prototipo: Medicina Veterinaria, Igiene pubblica, Disturbo/rumori,
  ARPA, Altro; nel confronto con merged.csv "Veterinario", "Colonia felina" e
  "Allevamento/detenzione animali" corrispondono a Medicina Veterinaria.

### Cerchio 1: dal PDF al contenuto pronto per il nucleo
1. Estrazione del testo. Se il PDF è leggibile digitalmente, il testo si estrae
   senza IA. Se non lo è, si usa un VLM come trascrittore (anche scrittura a
   mano). "È leggibile digitalmente?" è un controllo deterministico, non un
   modello. Il VLM trascrive soltanto: non classifica e non giudica.
   L'estrazione è fedele: trascrive anche intestazioni, inoltri e firme, non
   toglie nulla.
   Configurazione (in `config/estrazione.toml`, Ollama fissato a 0.40.1):
   - lettore principale `gemma4:12b`, ragionamento disattivato, pagina intera a
     200 DPI (lato max 2000 px), temperatura 0: il suo testo è l'uscita;
   - secondo lettore `qwen3-vl:8b-instruct`, stesse impostazioni: serve solo a
     misurare la divergenza per pagina, mai come testo in uscita;
   - due passate separate (prima il principale su tutte le pagine, poi il
     secondo); digest attesi di entrambi i modelli verificati all'avvio.
   Regola: una pagina con divergenza fra i due lettori ≥ 5% (parole) è marcata
   "lettura incerta" e va all'operatore con l'indicazione di leggere
   l'originale; la sua trascrizione non si usa per decisioni automatiche (la
   decisione è marcata "da verificare sull'originale").
   File Word/RTF: convertiti in PDF con LibreOffice in `/work/convertiti`.
1b. Pulizia. Separa l'involucro (intestazioni email, inoltri, "Messaggio
   originale", firme, clausole, timbri, righe ripetute) dal corpo. Segna le
   parti, non cancella nulla. Prima regole; LLM solo per i casi anomali e solo
   per indicare le righe da tenere, mai per riscrivere.
2. Predisposizione con LLM. I documenti sono molto variabili e possono superare
   le 8 pagine. Un LLM locale legge il testo estratto e lo prepara per il
   nucleo: riduce il testo, segnala se mancano dati, segnala se il contenuto
   sta altrove (allegati, link, foto). La forma dell'uscita è una decisione
   aperta (vedi sotto).
3. Segnali di qualità che accompagnano ogni documento: come è stato acquisito
   (digitale / VLM), se la lettura è incerta, se mancano dati. Un documento
   senza contenuto utilizzabile non entra nel nucleo: va all'operatore con
   un'etichetta che dice perché.

### Cerchio 2: contesto e consegna
- Tipo di documento: esposto, riscontro ATS, lettera di avvocato, richiesta di
  ente.
- Collegamento esposto–riscontro tramite numero di protocollo nel nome del file.
- JSON per documento e report PDF riepilogativo.
- Consuma le uscite del cerchio 1 e del nucleo; non le modifica.

## Dati

- Circa 500 documenti reali in `/home/lorenzo/vlm_pdf/documenti`, montata nel
  container in sola lettura come `/data/esposti`. Si monta SOLO questa
  cartella, mai la cartella superiore.
- Si lavora sui PDF (491) e sui file Word/RTF (.docx, .doc, .rtf, circa 15):
  anche questi possono essere esposti. Si convertono in PDF in locale con
  LibreOffice senza interfaccia, in una cartella di lavoro, e poi seguono lo
  stesso percorso dei PDF. I CSV presenti nella cartella non si aprono.
- Cartella di lavoro per uscite e revisione: `/home/lorenzo/sire_lavoro`,
  montata come `/work`. Sta fuori dal progetto e non va mai in un commit.
- `/home/lorenzo/vlm_pdf/merged.csv` è la classificazione manuale fatta da
  ATS. Autorizzato (10/10/2026) SOLO dentro script che stampano aggregati:
  valori distinti delle colonne del modulo (`strumenti/valori_ammessi.py`),
  associazione ai documenti, divisione taratura/verifica e confronto
  (`strumenti/confronto_merged.py`, `albero_csv.py`, `azioni_per_esito.py`).
  Nessun valore libero (Note, campi "altro", Operatore) esce dagli script.
- Nelle fasi di preprocessing non si usano etichette: la verifica di ogni
  passaggio la fa Lorenzo guardando i risultati.

## Fasi (una alla volta, ognuna con verifica umana prima della successiva)

1. Estrazione su 10 documenti, scelti per coprire i tipi diversi (digitale,
   scansione, scrittura a mano, lungo, catena di email). Lorenzo confronta PDF
   e testo estratto e decide se funziona.
2. Estrazione su tutti i ~500, poi controllo su un campione casuale.
3. Pulizia: molti documenti sono scansioni di stampe di email. Si separa
   l'involucro dal corpo (vedi Cerchio 1, passo 1b); il testo estratto resta
   intatto. Prima su 10 documenti con verifica di Lorenzo, poi tutti e
   campione casuale.
4. Predisposizione con LLM su 10 documenti: estrae davvero le informazioni
   corrette? Stessa verifica, poi tutti e campione casuale.
5. Prima scrematura senza classificatore: tipo di documento, e imputazione di
   "archiviato perché non di competenza" secondo le procedure. Si imputa solo
   quando il caso è chiaro e con la frase del documento che lo giustifica; nel
   dubbio il documento prosegue.
6. Restano esposti e richieste di competenza: solo quelli vanno al nucleo.

Prototipo end-to-end (`prototipo.py`, richiesto da Lorenzo il 10/10/2026):
catena artigianale estrazione → scheda (gemma4:12b, campi della scheda ATS con
frase giustificativa) → decisione (gemma4:12b con `config/criteri_decisione.md`)
→ consegna (JSON per documento, report PDF, pagina HTML di revisione in
`/work/prototipo/<esecuzione>/`). Serve a vedere la catena intera; le fasi
sopra restano il percorso per arrivare alla qualità da produzione.

Regole per le verifiche:
- Non esiste una soglia numerica di errori: i documenti dei cittadini non
  seguono uno schema e possono essere di qualsiasi tipo. Se una fase funziona
  lo decide Lorenzo a occhio. Non proporre soglie o metriche di accettazione.
- Dopo ogni revisione Lorenzo decide: si prosegue, oppure si corregge e si
  ripete il controllo. I tipi di errore che segnala si annotano in `docs/`
  (descritti in astratto, senza contenuti) per guidare le correzioni.
- Il campione casuale si estrae con seme fisso e si registra tramite hash.
- Ogni fase fornisce a Lorenzo uno strumento di revisione locale: PDF e uscita
  affiancati, giudizio per documento (ok / errore lieve / errore grave / nota)
  salvato in un file locale. Claude Code vede solo i conteggi dei giudizi, mai
  i documenti né le note.

## Decisioni aperte (da risolvere fase per fase, non date per prese)

- Forma dell'uscita della predisposizione: riassunto libero, scheda a campi
  fissi ricavati dalle procedure (ambito, luogo, problema, circostanziato,
  dati mancanti, con la frase del documento che giustifica ogni campo), o
  entrambi.
- Tipo di classificatore del nucleo. Senza etichette non si può addestrare un
  modello: si parte da LLM con i criteri delle procedure o regole sui campi
  estratti. I giudizi di revisione raccolti nelle fasi possono diventare in
  seguito la base per un modello addestrato.
- Uso del risultato: nascondere gli immotivati o ordinarli per priorità.

## Ambiente

- Workstation locale ATS: Windows 11, WSL2 Ubuntu, Docker Compose, GPU NVIDIA
  RTX 5060 Ti 16 GB.
- Python 3.11, Ollama locale, Docker per tutto: niente venv, niente
  installazioni sull'host.
- I modelli (LLM, VLM) devono stare in 16 GB di VRAM e si usano uno alla volta.
- File creati dentro i container non si cancellano da WSL con `rm`: usare
  `docker compose run --rm app find ... -delete`.
- Deriva dell'orologio WSL2: `sudo hwclock -s`.

## Modo di lavorare

- Si procede per piccoli passi. Prima un piano in `docs/`, poi ci si ferma e si
  aspetta l'OK; conferma a ogni confine di fase prima di proseguire.
- Eccezione: quando Lorenzo chiede un prototipo con libertà sulle scelte
  tecniche, si va avanti senza fermarsi a ogni passo e ci si ferma solo per un
  blocco vero. I vincoli di Privacy e il divieto di commit senza OK restano.
- Se qualcosa è ambiguo, una sola domanda, poi fermo.
- CLAUDE.md lo modifica Claude su richiesta di Lorenzo, mostrando il diff
  prima di salvare, salvo quando Lorenzo dice esplicitamente di non mostrarlo.
- Costanti di configurazione (cartelle, soglie, nomi dei modelli) in cima agli
  script o in un file di configurazione, mai sparse nel codice.
- Ogni script si prova su dati sintetici prima di girare sui dati reali.

## Riferimenti

- `docs/procedure/` (letti il 10/10/2026; nessuna revisione doppia; non nel
  repository, da chiedere a Lorenzo):
  - PRO Esposti/segnalazioni SPV: animali d'affezione, emissione 01.02.2024,
    rev. 3 (procedura ufficiale);
  - PRO Esposti/segnalazioni SPV: animali da reddito, emissione 01.02.2024,
    rev. 2 (procedura ufficiale);
  - "Procedura S.I.R.E 2026": bozza di progetto (classi critico / ordinario /
    banale, triage), non procedura approvata;
  - "procedura esposti": proposta Università dell'Insubria, bozza 13.04.2026,
    sul macro-flusso; non contiene criteri.
- `config/criteri_decisione.md`: criteri scritti della direzione del servizio
  (10/10/2026); prevalgono sulle procedure, usate come contesto.
- `config/scheda_ats.toml`: valori del modulo degli operatori e dell'Ambito
  del prototipo.
- `/work/confronto/divisione.json`: metà di taratura e di verifica (seme 42,
  stesso protocollo nella stessa metà). La metà di verifica è stata misurata
  UNA volta il 10/10/2026 con la configurazione congelata (impronta
  `133c0a34f6f86d6c`, `strumenti/impronta_config.py`): non si usa più per
  tarare. Una nuova verifica richiede un nuovo campione o l'OK di Lorenzo.
- `docs/stato.md`: stato del prototipo, misure prima/dopo/verifica, punti fragili.