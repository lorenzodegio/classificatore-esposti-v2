# Procedure ATS (non incluse nel repository)

Questa cartella contiene documenti interni di ATS Insubria che restano solo sulla
workstation e non vanno pubblicati. Per lavorare servono questi quattro file, da
chiedere a Lorenzo e copiare qui:

| File | Contenuto |
|---|---|
| `Procedura esp segn. animali aff. Rev distretti.docx` | PRO Esposti/segnalazioni SPV, animali d'affezione, emissione 01.02.2024, rev. 3 |
| `Procedura esp. segn. animali redd.Rev distretti.docx` | PRO Esposti/segnalazioni SPV, animali da reddito, emissione 01.02.2024, rev. 2 |
| `Procedura S.I.R.E 2026 U.C.docx` | bozza di progetto S.I.R.E. (classi critico / ordinario / banale) |
| `procedura esposti.docx` | proposta dell'Università dell'Insubria sul macro-flusso (bozza 13.04.2026) |

Il motore non legge questi file a runtime: i criteri che usa sono in
`config/criteri_decisione.md` (criteri scritti della direzione del servizio, che
prevalgono sulle procedure). Il `.gitignore` esclude tutto il resto di questa cartella.
