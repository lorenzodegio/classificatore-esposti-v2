# classificatore-esposti-v2 (S.I.R.E.) — motore

Motore locale e air-gapped per il Dipartimento di Prevenzione Veterinaria di ATS Insubria:
legge esposti e segnalazioni (PDF digitali, scansioni, scrittura a mano, Word/RTF), ricava
il testo per pagina, compila la scheda ATS con le frasi giustificative e **propone** esito,
urgenza e azione secondo i criteri della direzione del servizio.

**Stato (11/10/2026):** prototipo completo, eseguito a lotti (`prototipo.py`). Sull'esito non
è più affidabile di "accogli sempre" (62% contro 64% sulla metà di verifica): l'uscita è una
proposta per l'operatore, non una decisione. Dal 21/10/2026 è anche un servizio HTTP
(`servizio/`, servizio `motore` nel compose) conforme al contratto 1.2 dell'applicazione.

| Documento | Per chi |
|---|---|
| [docs/consegna.md](docs/consegna.md) | chi collega il motore all'applicazione: architettura, comandi, limiti, corrispondenza con il contratto |
| [docs/stato.md](docs/stato.md) | misure aggregate e punti fragili |
| [docs/diario.md](docs/diario.md) | decisioni prese in autonomia, con data e motivo |
| [CLAUDE.md](CLAUDE.md) | istruzioni operative e vincoli di privacy |

## Privacy

I documenti reali non sono e non devono entrare in questo repository: restano sulla
workstation ATS. Sviluppo e test solo sui dati sintetici di `tests/dati_sintetici/`.
I container che leggono documenti non hanno accesso a internet; i modelli sono locali (Ollama).

## Avvio rapido (dati sintetici)

```bash
docker compose build motore
MODELLO=gemma4:12b docker compose --profile scarica run --rm ollama-scarica
MODELLO=qwen3-vl:8b-instruct docker compose --profile scarica run --rm ollama-scarica
docker compose run --rm prova python -m pytest -q                 # test senza GPU
docker compose up -d motore                                       # servizio HTTP (+ ollama)
docker compose run --rm prova python tests/prova_motore_vero.py   # catena vera via HTTP
docker compose run --rm test python prototipo.py sintetici        # catena a lotti
docker compose down
```

La rete `esposti_interna` (condivisa con l'applicazione) è esterna: se non esiste,
`docker network create --internal esposti_interna`.

Requisiti: Docker Compose, GPU NVIDIA con 16 GB di VRAM. I percorsi delle cartelle in
`docker-compose.yml` sono quelli della workstation ATS.
