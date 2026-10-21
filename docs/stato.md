# Stato del progetto (10/10/2026; servizio HTTP 21/10/2026)

Solo aggregati: nessun contenuto, nome di file o protocollo. Celle sotto 5 come "<5".

## Cosa esiste

Prototipo end-to-end artigianale, tutto locale (Docker, rete interna, Ollama 0.40.1):

| Passo | Codice | Note |
|---|---|---|
| Estrazione | `cerchio1/estrazione/`, `estrai_tutti.py` | testo digitale se leggibile; altrimenti `gemma4:12b` (testo) + `qwen3-vl:8b-instruct` (solo divergenza); pagina "lettura incerta" se divergenza ≥ 5%; Word/RTF via LibreOffice; interrompibile e riprendibile |
| Scheda | `cerchio1/scheda.py` | `gemma4:12b`, valori del modulo ATS (`config/scheda_ats.toml`), frase giustificativa per campo |
| Decisione | `nucleo/decisione.py` | domande della direzione (`config/criteri_decisione.md`) applicate da regole in ordine; azione di partenza per esito da `config/azioni_per_esito.json` |
| Consegna | `cerchio2/consegna.py` | File e Protocollo dal nome, collegamento per protocollo, JSON per documento, report PDF, pagina HTML |
| Confronto | `strumenti/confronto_merged.py` | con merged.csv, per metà e per voce |

Esecuzione: `prototipo.py` (`sintetici`, `campione`, `rifai`, `taratura`, `verifica`, `tutti`).

## Dati

- 509 file, 457 documenti distinti (gli altri file sono copie identiche); 836 pagine, 434 trascritte con VLM.
- Documenti con almeno una pagina a lettura incerta: 113; senza contenuto utilizzabile: 8.
- merged.csv: 302 righe; 302 documenti associati (269 per nome, 33 per protocollo), 155 non associati.
- Divisione taratura / verifica: 151 + 151 documenti, seme 42, stesso protocollo nella stessa metà
  (`/work/confronto/divisione.json`, hash `f67f83c2e267f1f8`).
- Parser del protocollo: 393 file su 509 con protocollo; 33 protocolli in più di un documento.

## Configurazione congelata per la verifica

Impronta complessiva `133c0a34f6f86d6c` (`python strumenti/impronta_config.py`), calcolata dopo il giro
unico di correzioni sulla taratura e prima della misura sulla verifica.

## Misure (esposti e richieste di ente)

Esito in tre classi: Accolto / Invio Modulo / non si procede (Archiviato + Altro).

| | Taratura prima | Taratura dopo | Verifica (una volta) |
|---|---|---|---|
| Esito 3 classi, prototipo | 33% | 68% | 62% |
| Esito 3 classi, «sempre Accolto» | 68% | 69% | 64% |
| Esito 5 classi, prototipo | 28% | 61% | 48% |
| Esito 5 classi, «sempre Accolto» | 64% | 64% | 56% |
| Urgenza, prototipo | 34% | 38% | 49% |
| Urgenza, «sempre Normale» | 59% | 59% | 53% |
| Non accolti dal prototipo e nemmeno dagli operatori | 19 su 66 (29%) | 14 su 24 (58%) | 11 su 22 (50%) |

Riscontri, lettere e altro (esito 3 classi): taratura prima 42% (rif. 77%), dopo 43% (rif. 75%),
verifica 19% (rif. 65%): molti riscontri finiscono in "Da approfondire" (contenuto negli allegati).

Variabilità tra operatori (taratura, chi ha almeno 5 righe): quota di accolti dal 50% a oltre l'80%.

Lettura: il prototipo non supera ancora «sempre Accolto» sull'esito. È più utile come filtro dei
non accolti: quando non accoglie, gli operatori concordano in circa metà dei casi. Gli esiti degli
operatori precedono i criteri scritti della direzione: parte del disaccordo è un cambio di regole.

## Tutti i documenti (configurazione congelata)

457 documenti distinti (302 riusati da taratura e verifica, gli altri elaborati ex novo); circa 31 minuti.

- Formato: PDF 439, Word/RTF 18.
- Tipo: esposto 212, riscontro ATS 124, richiesta ente 88, lettera avvocato 11, altro 14, non determinato 8.
- Esito: Accolto 331, Altro (trasmissione ad altro ente) 41, Da approfondire 35, Archiviato 28,
  Invio Modulo 14, non elaborati (senza contenuto) 8.
- Con lettura incerta 113; con protocollo dal nome 350; con almeno un documento collegato 64.

## Punti fragili

1. Archiviazioni: gli operatori archiviano circa un quinto degli esposti; il prototipo quasi mai
   (la domanda 2 scatta raramente). I motivi di archiviazione degli operatori non sono nei criteri scritti.
2. Urgenza: il prototipo resta sotto «sempre Normale».
3. Scheda: spunta troppo spesso "Foto/allegati", "Maltrattamento animale", "Condizione di inidonea detenzione".
4. Riscontri: con allegati non trascritti finiscono in "Da approfondire".
5. Azione: "Sopralluogo congiunto" come partenza per "Accolto" viene dalla prassi degli operatori.
6. Lettura incerta: soglia del 5% tarata solo su pagine sintetiche; un documento su quattro è marcato.

## Uscite (in /work, mai nel repository)

- `/work/estrazione/`: testo per pagina e segnali (JSON per documento); `/work/indice_locale.json`.
- `/work/prototipo/{taratura,verifica,tutti}/`: JSON per documento, `report.pdf`, `revisione.html`.
- `/work/confronto/`: divisione e misure aggregate (prima, dopo, verifica).

## Servizio HTTP (21/10/2026)

Servizio `motore` (contratto 1.1 dell'applicazione), solo dati sintetici. Decisioni in
`docs/diario.md`.

### Test

- Senza GPU (`docker compose run --rm prova python -m pytest -q`): 47 test superati (14 già
  esistenti, 33 nuovi: adattatore, protocollo, ancoraggio delle frasi, tipo di documento,
  trasporto HTTP con 429, idempotenza, impronta, errori, tempo scaduto, DELETE, e catena vera
  con Ollama simulato su 6 documenti sintetici, risposte verificate contro gli schemi).
- Con Ollama vero (`docker compose run --rm prova python tests/prova_motore_vero.py`, via
  HTTP sul servizio `motore`): 6 documenti sintetici su 6 completati e conformi agli schemi
  `schema_risultato.json` e `schema_stato_lavoro.json`. Tipo: 3 esposti, 1 riscontro ATS,
  1 inoltro per competenza; protocollo letto dal testo in 2 documenti, dal nome del file in
  1; lettura incerta sui 3 fogli a mano, nessuna sulle stampe.

### Tempo per documento (catena completa via HTTP, Ollama 0.40.1, RTX 5060 Ti 16 GB)

Dall'invio al risultato, modelli già scaricati su disco, un documento alla volta.

| Tipo | Documento sintetico | Pagine | Secondi |
|---|---|---|---|
| digitale | `digitali/esposto_digitale.pdf` | 1 | 24 |
| Word | `digitali/riscontro_word.docx` | 1 | 20 |
| scansione (stampa) | `scansioni/email_inoltrata.pdf` | 2 | 94 |
| manoscritto | `scansioni/mano_1.pdf`, `mano_2.pdf`, `mano_3.pdf` | 1 | 46, 44, 44 |

Ripartizione tipica per un foglio a mano (log del servizio): estrazione con i due lettori
circa 20 s, scheda 12 s, decisione 6 s, frasi per voce 3–4 s, temi 2 s, tipo 1,5 s. Il primo
documento dopo l'avvio di Ollama costa in più il caricamento da disco (prima prova: 84 s per
il PDF digitale contro 24 s; un foglio a mano subito dopo un riavvio di Ollama: 116 s contro
46 s). Con gemma4:12b in memoria la GPU occupa circa 9,6 GB su 16: i due lettori non stanno
insieme in VRAM (`OLLAMA_MAX_LOADED_MODELS=1`, diario n. 28).

### Impronta della configurazione

Nuova impronta complessiva `0500aac69b2a5ed0` (`python strumenti/impronta_config.py`), al posto di
`133c0a34f6f86d6c`. Perché è cambiata:
- `docker-compose.yml`: servizi `motore` e `prova`, profilo `lotti` per `app` e `test`,
  `OLLAMA_MAX_LOADED_MODELS=1`;
- l'elenco dei file include ora i passi nuovi del servizio (`config/temi.toml`,
  `config/servizio.toml`, `cerchio1/ancora.py`, `frasi_voci.py`, `temi.py`,
  `cerchio2/consegna.py`, `protocollo.py`, `tipo_documento.py`, `contratto_v1.py`,
  `servizio/catena.py`).
Gli altri file della configurazione congelata (estrazione, scheda, decisione, criteri,
modulo, azioni) non sono cambiati: la catena a lotti dà le stesse uscite di prima. La misura
sulla metà di verifica resta quella del 10/10/2026 e non vale per i passi nuovi (temi, frasi
per voce, tipo, protocollo), che non sono ancora stati misurati sui reali.
