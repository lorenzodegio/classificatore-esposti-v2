# classificatore-esposti-v2 (S.I.R.E.) — motore

Motore locale e air-gapped per il Dipartimento di Prevenzione Veterinaria di ATS Insubria:
legge esposti e segnalazioni (PDF digitali, scansioni, scrittura a mano, Word/RTF), ricava
il testo per pagina, compila la scheda ATS con le frasi giustificative e **propone** esito,
urgenza e azione secondo i criteri della direzione del servizio.

**Stato (11/10/2026):** prototipo completo, eseguito a lotti (`prototipo.py`). Sull'esito non
è più affidabile di "accogli sempre" (62% contro 64% sulla metà di verifica): l'uscita è una
proposta per l'operatore, non una decisione. Non è ancora un servizio HTTP.

| Documento | Per chi |
|---|---|
| [docs/consegna.md](docs/consegna.md) | chi collega il motore all'applicazione: architettura, comandi, limiti, corrispondenza con il contratto |
| [docs/stato.md](docs/stato.md) | misure aggregate e punti fragili |
| [CLAUDE.md](CLAUDE.md) | istruzioni operative e vincoli di privacy |

## Privacy

I documenti reali non sono e non devono entrare in questo repository: restano sulla
workstation ATS. Sviluppo e test solo sui dati sintetici di `tests/dati_sintetici/`.
I container che leggono documenti non hanno accesso a internet; i modelli sono locali (Ollama).

## Avvio rapido (dati sintetici)

```bash
docker compose build app
MODELLO=gemma4:12b docker compose --profile scarica run --rm ollama-scarica
MODELLO=qwen3-vl:8b-instruct docker compose --profile scarica run --rm ollama-scarica
docker compose up -d ollama
docker compose run --rm test python -m pytest -q
docker compose run --rm test python prototipo.py sintetici
docker compose down
```

Requisiti: Docker Compose, GPU NVIDIA con 16 GB di VRAM. I percorsi delle cartelle in
`docker-compose.yml` sono quelli della workstation ATS.
