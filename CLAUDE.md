# CLAUDE.md — Team syntaxerror Prognose-Repo

Dieses Repo enthält die tägliche Lastprognose-Submission für das ENTSO-E-Leaderboard
(Mirror von `bart26k-lecture` Kapitel 14).

## Wichtige Konventionen

### Die vier Code-Regeln (CR-1 bis CR-4)
Alle Änderungen müssen diese befolgen:
- **CR-1** (No dead code): Jede Funktion/Branch muss getestet sein
- **CR-2** (Determinism): Gleicher Input → Byte-identischer Output (fixes Seeds, Iteration order)
- **CR-3** (Fail-safe): Ungültige Eingaben (NaN, falsch dtype) werfen explizite Errors, nie still imputation
- **CR-4** (Minimal CVE surface): Kurze, versionierte Dependency-Liste (in `pyproject.toml` gepinnt)

### Dates & Determinism (CR-2)
- Alle Daten werden from `pd.Timestamp.now(tz="UTC")` abgeleitet
- **Nie hard-code Kalender-Daten** in Scripts!
- Für Reproduzierbarkeit: `--deterministic` flag oder `--data-end YYYYMMDDHHMM`

### Dependencies
- **spotforecast2-safe >=15.7.0** (für provider-Exogene: ENTSO-E Prognose, COVID, etc.)
- **spotforecast2 >=3.4.0** (MultiTask, ConfigEntsoe, entsoe task hooks)
- Locked via `uv.lock` — never `pip install`
- `uv sync` zum Setup

### Environment
```bash
export ENTSOE_API_KEY=...                    # Required
export SPOTFORECAST2_DATA=~/.spotforecast2_data/syntaxerror_submission  # Optional (auto-set by script)
export SPOTFORECAST2_CACHE=~/.spotforecast2_cache/syntaxerror_submission  # Optional
```

## Submission Pipeline (`scripts/submit.py`)

Synced von `bart26k-lecture/scripts/team4_submit.py`. Wenn ich ändere:
- date constants (NOW_UTC, TODAY_UTC, etc.)
- ConfigEntsoe arguments (periods, poly_features_degree, include_entsoe_*, etc.)
- Method order (download → coverage → PACF → fit → predict)
- CSV schema (timestamp, forecast_mw columns)

**Dann muss das auch hier aktualisiert werden!**

### Häufige Commands

```bash
# Full live run
uv run python scripts/submit.py

# Quick test (50 trials statt 500)
uv run python scripts/submit.py --n-trials 50

# Bit-reproducible (serial SpotOptim)
uv run python scripts/submit.py --deterministic

# Reuse cached data
uv run python scripts/submit.py --skip-download

# Freeze the window (für Debugging)
uv run python scripts/submit.py --data-end 202606030000

# Commit + push to leaderboard (needs gh + team auth)
uv run python scripts/submit.py --push
```

## Leaderboard

- **Repo:** `github.com/bartzbeielstein/challenge-leaderboard`
- **Teams:** vordefiniert in `challenge-leaderboard/teams.yml`
- **Team ID:** `syntaxerror` (hardcoded)
- **CSV Schema:** 24 rows (Stunden 00:00–23:00 UTC), Spalten `timestamp` + `forecast_mw` (MW, positive)
- **Validation:** `challenge-leaderboard/scripts/validate_submission.py` prüft Autor, Schema, Positivität

## Git Discipline

- **Keine hardcoded Secrets** (ENTSOE_API_KEY, GitHub tokens) — use `.env` (in `.gitignore`)
- **Keine venv commits** — `.venv` ist in `.gitignore`
- **Keine Jupyter Notebooks** — nur `.qmd` Source of Truth
- **CSV-Output** (`prognosen/`) ist ignoriert (außer wenn du committing) — täglich neu generiert

## Debugging & Logs

- `--verbose (-v)`: INFO level
- `--verbose -v (-vv)`: DEBUG level
- Figures saved to `~/.spotforecast2_cache/syntaxerror_submission/figures/` (or `--figures-dir`)
- Script logs go to stdout (kein separate log file by default)

---

**Last synced from:** `bart26k-lecture/scripts/team4_submit.py` at commit 0982863

Wenn du diese Datei änderst, dokumentiere die Sync-Note oben!
