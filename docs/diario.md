# Diario delle decisioni

Decisioni prese in autonomia, con data e motivo. Solo aggregati e dati sintetici: nessun
contenuto, nome di file o protocollo reale.

## 21/10/2026 — servizio HTTP del motore (contratto 1.1)

Incarico di Lorenzo (tramite il coordinatore): servizio HTTP conforme al contratto 1.1
dell'applicazione, colmare le differenze di `docs/consegna.md`, servizio `motore` nel
compose, test, misure. OK esplicito a lavorare in autonomia e a fare commit su `dev` con i
test che passano (eccezione al "fermarsi a ogni fase" di `CLAUDE.md`); vincoli di privacy
invariati. Nessuna esecuzione su dati reali.

### Struttura

1. **Catena invariata, passi aggiunti a valle.** Estrazione, scheda, decisione e consegna
   non sono stati modificati (stessi file, stesso comportamento: `prototipo.py` produce le
   stesse uscite). Ciò che il contratto chiede in più sta in moduli nuovi:
   `cerchio1/ancora.py`, `cerchio1/frasi_voci.py`, `cerchio1/temi.py`,
   `cerchio2/protocollo.py`, `cerchio2/tipo_documento.py`, `cerchio2/contratto_v1.py`
   (adattatore). Motivo: richiesta esplicita di non cambiare il comportamento dei pezzi già
   misurati sulla metà di verifica.
2. **Orchestrazione per un documento in `servizio/catena.py`**, non in `estrai.py`: le due
   passate VLM sono riscritte lì con le stesse funzioni (`prepara`, `per_lettore`,
   `verifica_modello`, `rendi_pagina`, `trascrivi`, `completa`) e nello stesso ordine
   (prima il principale su tutte le pagine, poi il secondo), aggiungendo solo avanzamento
   per pagina, controllo del tempo massimo e annullamento. Motivo: `estrai.estrai` non ha un
   punto in cui riferire l'avanzamento o fermarsi, e cambiarlo avrebbe toccato un file
   misurato.
3. **Un thread, stato in memoria.** Un lavoro alla volta; `429` con `Retry-After` (30 s,
   `config/servizio.toml`) se occupato. Occupato = un lavoro in elaborazione; un lavoro
   concluso ma non ancora confermato con `DELETE` non blocca il successivo (come il finto
   motore). Idempotenza: stesso `id_lavoro` → `202` con lo stato attuale, nessun secondo
   lavoro, anche mentre lavora (niente `429` per un reinvio dello stesso lavoro).
4. **Documento sul tmpfs, nome neutro.** Il file ricevuto va in `/lavoro/<uuid casuale>/
   documento.<estensione>` (tmpfs); il nome dichiarato dall'applicazione non tocca mai il
   disco né i log (serve solo come ripiego per il protocollo, nella risposta). La cartella si
   cancella appena finita l'analisi; il risultato (che contiene il testo) resta in memoria
   fino al `DELETE`, e in ogni caso al massimo 24 ore (`conserva_risultato_s`), per non
   accumulare testi se l'applicazione non conferma. Anche `/tmp` (dove FastAPI parcheggia gli
   upload grandi) è tmpfs; file system del container in sola lettura.
5. **Ordine dei controlli in `POST`**: metadati → idempotenza → occupato (`429`) → impronta
   (`422 impronta_non_coincide`, nessun lavoro creato) → formato. Un formato non gestito
   crea un lavoro già concluso in errore (`202`, poi `GET` → `formato_non_supportato`),
   come il finto motore dell'applicazione e l'esempio 6.4 del contratto.
6. **Codice di errore in più: `richiesta_non_valida`** (`422`, non ritentabile) per
   metadati mancanti o malformati, `id_lavoro` con caratteri non ammessi (`[A-Za-z0-9._-]`,
   per non usarlo mai come percorso) o versione maggiore del contratto diversa da 1. Il
   contratto 1.1 non prevede un codice per questi casi, che sono errori dell'applicazione;
   `client.py` dell'applicazione lo tratta come rifiuto (`MotoreRifiuto`). Da proporre nel
   contratto (1.2). Il file oltre il limite (50 MB) è `formato_non_supportato`.
7. **`GET` di un lavoro sconosciuto o cancellato: `404`** con `errore_interno` "Lavoro
   sconosciuto.", identico al finto motore.
8. **`DELETE` durante l'elaborazione** ferma il lavoro alla pagina o al passo successivo
   (la chiamata in corso a Ollama finisce); il motore resta occupato finché il thread non si
   ferma davvero, perché la GPU è ancora impegnata.
9. **`tempo_scaduto`** dopo 30 minuti (`tempo_max_s`), controllato fra una pagina e l'altra
   e fra un passo e l'altro (ogni chiamata a Ollama ha già il suo limite di 600 s).
10. **Avanzamento**: `pagine_totali` = pagine del documento; `pagine_lette` = pagine digitali
    + metà delle letture VLM fatte (ogni pagina scansionata la leggono due lettori in due
    passate). Durante scheda e decisione vale `pagine_totali`.
11. **`GET /v1/salute`**: oltre ai campi del contratto riporta i digest dei due modelli in
    Ollama e se coincidono con quelli attesi (`config/estrazione.toml`), con cache di 30 s;
    `stato` è `non_pronto` se Ollama non risponde o i digest non coincidono.

### Contenuto del risultato

12. **Frase e pagina per ogni voce** (`cerchio1/frasi_voci.py`): una chiamata LLM in più,
    dopo la scheda, chiede per ciascuna voce già spuntata la frase che la giustifica. Le voci
    non cambiano (la scheda resta l'unica a sceglierle). Se per una voce non arriva una frase
    si usa quella del campo; se manca anche quella la voce si omette (il contratto vuole una
    frase per voce).
13. **Ancoraggio deterministico** (`cerchio1/ancora.py`): la pagina non si chiede all'LLM, si
    ricava ritrovando la frase nel testo (uguale a meno di spazi e maiuscole, altrimenti la
    finestra di parole più simile, soglia 0,75); la frase restituita è il tratto letterale del
    documento, con spazi uniformati (gli a capo diventano spazi) e al massimo 300 caratteri,
    tagliata a fine parola. Se l'LLM accorcia con "…", si ancora il tratto più lungo. Se la
    frase non si ritrova si tiene quella dell'LLM sulla pagina più simile.
14. **Temi** (`cerchio1/temi.py`, vocabolario e definizioni in `config/temi.toml`): una
    chiamata LLM sul testo; zero o più temi, ognuno con motivo, frase e pagina. Un tema senza
    frase si scarta. Zero temi è ammesso (lo schema lo permette) per documenti che non
    riguardano nessuno dei quattro temi (rumori, ARPA, accesso agli atti senza animali…).
    Dopo la prima prova vera il prompt chiede che "una menzione di passaggio non basta"
    (sul PDF digitale sintetico proponeva "Cani" per cani citati solo come passanti).
15. **Tipo di documento** (`cerchio2/tipo_documento.py`): la scheda resta la fonte; una
    chiamata LLM risponde a due domande (inoltro per competenza? integrazione di una
    segnalazione precedente?) e scrive il motivo. Regole: riscontro ATS e lettera di avvocato
    restano; poi inoltro → `inoltro_per_competenza`; poi integrazione → `integrazione`;
    altrimenti la conversione diretta (`riscontro ATS`→`riscontro_ats`, `lettera
    avvocato`→`lettera_avvocato`, `richiesta ente`→`richiesta_ente`). La decisione del nucleo
    continua a usare il tipo della scheda (invariata).
16. **Protocollo dal testo** (`cerchio2/protocollo.py`, regole senza modello): prima
    indicazione "Prot./Protocollo [n./n°] NNNN[/AAAA] [del gg/mm/aaaa | dell'8 aprile 2025]"
    nell'ordine delle pagine (in un riscontro è il riferimento all'esposto, che serve al
    collegamento); numero a 7 cifre con l'anno (`0005120/2025`); per l'anno vedi il punto 33.
    Ripiego: il nome del file con le regole di `cerchio2/consegna.py`; in quel caso `frase`
    è "(nome del file) <nome>" e `pagina` è 1 per convenzione (lo schema le richiede).
    `contesto.protocollo_noto` non si usa: il motore restituisce ciò che legge.
17. **Acquisizione**: `digitale`→`testo_nativo`, `vuota`→`nessuna`, `vlm`→`ocr` sempre: il
    motore non distingue lo stampato dal manoscritto (vedi `docs/consegna.md`, cosa resta).
    `motivo_incertezza` spiega la divergenza fra i due lettori e i segnali.
18. **Proposta**: `motivo` = note della decisione più la frase determinante; `domanda_decisiva`
    = una domanda breve per ciascuna regola (1, 2, 3, 5) in `cerchio2/contratto_v1.py`,
    invece del testo lungo di `DOMANDE` pensato per l'LLM; `da_verificare_sull_originale` =
    "Pagina N: lettura incerta, leggere l'originale." per ogni pagina incerta.
19. **Immagini** (PNG, JPEG, TIFF anche a più pagine) accettate: convertite in PDF con Pillow
    (rotazione EXIF rispettata) e poi lette come scansioni. Costava poche righe e non tocca la
    catena. `.eml` non ancora: `formato_non_supportato`.
20. **Versioni**: `versione_contratto` "1.1", `versione_motore` "2.1.0" (`config/servizio.toml`).

### Compose, immagine, test

21. **Servizio `motore`**: reti `sire_interna` (verso Ollama) ed `esposti_interna` (esterna,
    creata dal coordinatore, interna), in ascolto su 0.0.0.0:8080, nessuna porta sull'host;
    montato solo il codice che serve (`cerchio1`, `cerchio2`, `nucleo`, `config`, `servizio`)
    in sola lettura, non l'intero repository (che contiene anche `docs/procedure/`); nessuna
    cartella di documenti o di lavoro.
22. **Profilo `lotti` per `app` e `test`**: così un `docker compose up` generico non avvia
    mai il servizio che monta i documenti reali. `docker compose run --rm app|test …` funziona
    come prima (un servizio nominato esplicitamente attiva il suo profilo).
23. **Servizio `prova`** (profilo `prova`) per i test nuovi: nessun documento reale e nessuna
    cartella di lavoro montati (`/work`, `/lavoro`, `/tmp` in tmpfs). Il servizio `test`
    esistente monta `/home/lorenzo/sire_lavoro/sintetici`; per rispettare il divieto di
    montare `sire_lavoro` in questo incarico non l'ho più usato dopo un primo avvio (solo per
    leggere l'elenco dei modelli di Ollama).
24. **Dipendenze nell'immagine** (in build, con internet, senza documenti): fastapi 0.115.6,
    uvicorn 0.32.1, python-multipart 0.0.20, httpx 0.27.2 (TestClient), jsonschema 4.23.0.
25. **Schemi del contratto copiati** in `tests/contratto/` dall'applicazione (contratto 1.1):
    `schema_risultato.json` sha256 `848864a1a89e…`, `schema_stato_lavoro.json` sha256
    `ad44c9cfed08…`. I test verificano anche le regole di coerenza di `contratto/modelli.py`
    (pagine in ordine, `lettura_incerta` coerente). Se il contratto cambia, vanno ricopiati.
26. **Documenti sintetici nuovi** generati con LibreOffice da `tests/genera_sintetici.py`
    (contenuti inventati): `tests/dati_sintetici/digitali/esposto_digitale.pdf` (email di una
    cittadina inventata: veleno e gatti) e `riscontro_word.docx` (riscontro ATS con
    protocollo nel testo).
27. **Test senza GPU con la catena simulata**: catena vera (pypdfium2, LibreOffice,
    adattatore, HTTP) con Ollama sostituito: il "VLM" restituisce la verità delle scansioni
    sintetiche (il secondo lettore perde una parola su cinque sui fogli a mano) e l'"LLM"
    risponde con valori plausibili nella forma dello schema.

### Ollama

28. **`OLLAMA_MAX_LOADED_MODELS=1`** sul servizio `ollama`. Misura (prova vera, 21/10/2026):
    con gemma4:12b caricato la GPU occupa circa 9,6 GB su 16; qwen3-vl:8b-instruct (circa 6 GB
    più il contesto) non ci sta insieme, e infatti a fine documento in memoria resta solo
    gemma: Ollama scarica comunque un modello per caricare l'altro. Tenerne due
    (`=2`, proposta di `consegna.md`) non dà vantaggi e rischia lo scarico parziale su CPU;
    `=1` rende esplicita la regola di `CLAUDE.md` ("uno alla volta"). Ordine dei passi per
    documento: principale (gemma4, contesto 16k) → secondo (qwen3-vl) → scheda, decisione,
    frasi, temi, tipo (gemma4, contesto 32k): per una scansione sono tre caricamenti, già
    compresi nei tempi misurati in `docs/stato.md`.

### Documentazione

29. `CLAUDE.md`: aggiornata solo la riga di stato (in modo minimo: servizio HTTP presente,
    rimando a questo diario); nessun materiale di pianificazione.

### Controllo prima del commit

30. `strumenti/controllo_pubblicazione.py` (container senza rete, sola lettura), solo conteggi:
    protocolli reali 0, identificativi di documenti reali 0. "Nomi di documenti reali" e
    "valori liberi di merged.csv": 1 corrispondenza per file (1–3 per i valori) nei file
    nuovi, con lo stesso andamento del ramo già pubblicato (stesso controllo sull'albero
    di `HEAD`: 12 e 28 corrispondenze, una per ogni file che usa il vocabolario del modulo,
    per esempio `cerchio1/scheda.py`, `nucleo/decisione.py`, `config/scheda_ats.toml`); i file
    modificati hanno gli stessi conteggi di prima. Le ho lette come parole generiche del
    vocabolario (lo strumento non mostra le corrispondenze, per scelta); i nomi, i comuni e i
    numeri dei sintetici nuovi non aggiungono categorie. Da guardare con Lorenzo se serve.

## 21/10/2026 — correzioni dopo la revisione del commit 2c9ff7c

31. **Pulizia preventiva dei testi d'esempio** (richiesta del revisore: corrispondenze con i
    valori liberi di merged.csv non spiegate dal vocabolario in 5 file nuovi). Senza cercare
    quali parole coincidessero: in `cerchio1/temi.py` tolto l'esempio di motivo; in
    `config/temi.toml` definizioni ridotte a etichette del contratto e parole generiche; in
    `tests/genera_sintetici.py` persone, vie e comuni sostituiti con valori palesemente
    inventati ("Anna Esempio", "via delle Prove", "Borgoverde") e testo semplificato, con i
    due documenti sintetici rigenerati; in `tests/test_catena_simulata.py` e
    `tests/test_contratto_v1.py` frasi d'esempio sostituite con testi "di prova".
    `controllo_pubblicazione.py` rilanciato una sola volta, come controllo prima del commit.
32. **`CLAUDE.md`**: ripristinate le fini riga CRLF originali; rispetto a `origin/dev` il
    file differisce solo per le 2 righe di stato.
33. **Protocollo: l'anno non si inventa** (sostituisce in parte il punto 16). Si aggiunge
    "/AAAA" solo se l'anno è scritto accanto al numero o nella data che segue il numero nel
    testo ("Prot. n. 12345 del 08/04/2025": è la data del protocollo). Altrimenti il numero
    resta a 7 cifre senza anno ("0012345") e `data` è null. Dal nome del file il numero è
    sempre senza anno e `data` è null: la data nel nome non è con certezza quella del
    protocollo. Scelto invece di `protocollo: null` per non perdere il numero, che
    l'applicazione può confrontare con il protocollo noto all'arrivo; un numero senza
    "/AAAA" significa "anno non noto" (da documentare nel contratto 1.2).
34. **Esito del controllo** dopo la pulizia (una sola esecuzione): protocolli reali 0,
    identificativi 0; nomi di documenti reali 20 in 19 file (invariato, vocabolario); valori
    liberi di merged.csv 40 in 21 file (prima 44 in 22). Nei 5 file segnalati: `cerchio1/temi.py`
    2 (prima 3), `config/temi.toml` 0 (prima 1), `tests/genera_sintetici.py` 2 (prima 3),
    `tests/test_catena_simulata.py` 2 (prima 2), `tests/test_contratto_v1.py` 1 (prima 2).
    Restano corrispondenze: come indicato dal coordinatore mi fermo su questo punto (nessuna
    ricerca delle parole coincidenti); il push resta bloccato finché non le guarda Lorenzo.
35. Nuova impronta della configurazione `98c254f94decd91c` (temi e protocollo cambiati).
    I tempi in `docs/stato.md` sono della prova del 21/10/2026 prima di queste correzioni;
    nessuna nuova prova con Ollama finché il coordinatore non la autorizza.

## 21/10/2026 — contratto 1.2

36. **Contratto 1.2** (chiuso dall'Agente A nell'applicazione): il servizio risponde con
    `versione_contratto` "1.2" (unica fonte in `cerchio2/contratto_v1.py`, che `servizio/app.py`
    importa) e accetta metadati con qualunque `1.x`. `versione_motore` portata a "2.2.0" perché
    cambia la versione del contratto prodotta. Nessun cambiamento di comportamento: la 1.2
    scrive nel contratto ciò che il motore già faceva (`richiesta_non_valida`, `ocr` sempre,
    frase convenzionale dal nome del file, `.eml` non supportato).
37. **Schemi ricopiati** in `tests/contratto/` (ora con `pattern` `^1\.[0-9]+$` su
    `versione_contratto`): `schema_risultato.json` sha256 `2dc6f059a91d…`,
    `schema_stato_lavoro.json` sha256 `0def84bdfbff…`; contratto `docs/contratto_motore.md`
    sha256 `79a21dafc4da…`. Gli esempi e `modelli.py` dell'applicazione non si copiano: i test
    del motore usano gli schemi e ripetono le regole di coerenza di `modelli.py`
    (`tests/verifica_contratto.py`).
38. Una sola prova con Ollama vero, autorizzata dal coordinatore: 6 su 6 conformi; tempi in
    `docs/stato.md`. `CLAUDE.md`: nella riga di stato "1.1" → "1.2", fini riga CRLF mantenute.
39. Nuova impronta della configurazione `5ffcd75227630b09` (solo versioni e commenti del contratto 1.2).
40. (22/10/2026, coordinatore) `strumenti/controllo_pubblicazione.py --dettaglio`: scrive in
    `/home/lorenzo/sire_lavoro/corrispondenze.txt` (solo sulla workstation, permessi 600) file, riga,
    testo e colonna di merged.csv di ogni corrispondenza con i valori liberi; sullo schermo solo
    percorso e conteggi. Lorenzo ha verificato le corrispondenze: parole comuni e una coincidenza
    dentro un digest; il file è stato cancellato.
41. (22/10/2026, coordinatore) Il controllo ignora le parole comuni verificate da Lorenzo
    (`PAROLE_COMUNI_IGNORATE`) e le occorrenze dentro un digest o un hash esadecimale (almeno 8
    caratteri, lettere e cifre); per nomi e valori liberi conta anche le corrispondenze non spiegate
    dal vocabolario e chiude con "esito: pulito" o "da verificare". `--dettaglio` copre anche i nomi
    dei documenti. Una seconda verifica di Lorenzo ha aggiunto all'elenco un'altra parola comune
    (coincidenza con il nome di un documento); file di dettaglio cancellato. Esito: pulito.
