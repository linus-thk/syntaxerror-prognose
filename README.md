# Team syntaxerror — ENTSO-E Load Forecasting Submission

Das ist euer privates Team-Repo für die tägliche Lastprognose-Submission zum Leaderboard.

## Setup

```bash
# Install dependencies (requires Python 3.13+)
uv sync

# Export your ENTSO-E API key
export ENTSOE_API_KEY=<your-key>

# Run the submission pipeline
uv run python scripts/submit.py

# Or submit to leaderboard (requires gh CLI auth + challenge-leaderboard fork)
uv run python scripts/submit.py --push
```

## Struktur

- **scripts/submit.py** — Die Submission-Pipeline (Mirror von bart26k-lecture ch. 14)
- **pyproject.toml** — Dependencies (spotforecast2-safe ≥15.7.0, spotforecast2 ≥3.4.0)
- **prognosen/** — Ausgabeverzeichnis für tägliche Vorhersagen (CSV)
- **docs/** — Dokumentation und Team-Notes

## Pipeline

1. **Download** — ENTSO-E Aktuelle Lasten + Day-Ahead Prognose/Wind/Solar/Preis
2. **PACF Lag-Selection** — Dynamische Lag-Wahl aus Autokorrelation
3. **ConfigEntsoe Setup** — Advanced Features:
   - 5 Seasonal Periods (täglich bis jährlich mit RBF)
   - Weather Windows + Holiday Features
   - Poly Features (degree=2, max=10)
   - Provider-basierte Exogene (ENTSO-E, COVID-Inzidenz)
4. **MultiTask(SpotOptim)** — 500 Trials / 50 Initial über 10 Folds
5. **Vorhersage & Validierung** — 24h für morgen, CSV mit 24 positiven Werten
6. **Leaderboard PR** — Submission ins leaderboard Repo

## Vier Code-Regeln (CR-1 bis CR-4)

Diese Pipeline implementiert die vier Safety-Critical Regeln der Vorlesung:

- **CR-1**: No dead code (alle Branches getestet)
- **CR-2**: Determinism (same input = byte-identisch)
- **CR-3**: Fail-safe (ungültige Eingaben werfen explizite Errors)
- **CR-4**: Minimal CVE surface (versionierte Dependencies)

## Wichtig: Determinism (CR-2)

Die Pipeline nutzt `pd.Timestamp.now(tz="UTC")` für "live" Daten, aber innerhalb desselben Datenfensters ist das Ergebnis reproduzierbar:

- Gleiche Trainings-Daten + Gleiche Config → Gleiche Model-Gewichte
- Mit `--deterministic` erzwingt man serielle SpotOptim für Bit-Reproduzierbarkeit

## Testing

```bash
# Schneller Test (50 Trials statt 500)
uv run python scripts/submit.py --n-trials 50

# Reproducible/deterministic run
uv run python scripts/submit.py --deterministic

# Reuse cached data (no ENTSO-E API call)
uv run python scripts/submit.py --skip-download

# Freeze the window (für Tests)
uv run python scripts/submit.py --data-end 202606030000
```

## EU KI-VO Anforderungen

Der Forecaster behandelt folgende Anforderungen:

- **Art. 10** (Datenqualität): Explizite Fehler bei NaN/Anomalien (CR-3), Coverage Guards
- **Art. 12** (Record-keeping): Logging & Audit Trail
- **Art. 13** (Transparenz): Feature Importance, SHAP-Plots
- **Art. 15** (Robustheit): PACF-Lag-Selection, Backtest mit Rolling Origin

---

**Source of Truth:** `../../bart26k-lecture/14_team_4_submission.qmd` (mit Anpassungen für syntaxerror)

**Leaderboard:** github.com/bartzbeielstein/challenge-leaderboard
