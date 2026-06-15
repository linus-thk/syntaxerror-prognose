# Model/Method Card: syntaxerror-prognose

This card describes the day-ahead electricity load forecasting pipeline submitted by **team syntaxerror** to the Lastprognose-Challenge SoSe26 leaderboard. It documents the model's architecture, intended use, data requirements, and the conditions under which its results are valid. It follows the [Hugging Face Model Card Guidebook](https://huggingface.co/docs/hub/model-card-guidebook) taxonomy.

## 1. Model Details

| Field | Value |
| --- | --- |
| Name | syntaxerror-prognose |
| Version | 1.0.0 (frozen snapshot 2026-06-08) |
| Type | Deterministic recursive multi-step load forecasting system combining data preprocessing (spotforecast2-safe), hyperparameter tuning (SpotOptim), and LightGBM regression. |
| Developed by | Team syntaxerror (course project for Lastprognose-Challenge SoSe26) |
| Repository | <https://github.com/timhaeger/syntaxerror-prognose> |
| Reference | `MANIFEST.md`, `README.md` (this package); upstream lecture at <https://github.com/bartzbeielstein/bart26k-lecture> (chapter 14) |
| Language | Python 3.13+ |
| License | MIT (reproducibility package); underlying libraries carry their own licenses |
| Target | Day-ahead electricity load forecasting (Germany, 24-hour horizon, 1-hour resolution) |

**Key technical components:**

| Component | Version | Purpose |
| --- | --- | --- |
| spotforecast2-safe | 18.1.0 | Deterministic lag/feature engineering, guards against data leakage |
| spotforecast2 | 5.1.1 | Configuration and task orchestration (ConfigEntsoe, MultiTask) |
| SpotOptim | 0.12.8 | Sequential parameter optimization / hyperparameter tuning |
| LightGBM | 4.6.0 | Gradient boosting regressor (underlying learner) |
| pandas | 3.0.3 | Data I/O and tabular processing |
| scikit-learn | 1.9.0 | Model wrappers and metrics |
| entsoe-py | 0.8.0 | ENTSO-E Transparency Platform API client |

**Reproducibility:** This package bundles all dependencies at exact pinned versions (`pyproject.toml`, `uv.lock`). The forecasts are **bit-exactly reproducible** on arm64 macOS with the same random seed (`--deterministic` flag, `random_state=42`, serial SpotOptim). See `MANIFEST.md` for platform-specific details and the operational vs. reproducibility trade-off.

**Responsibilities:**

| Responsibility | Party |
| --- | --- |
| Model design, training, tuning | Team syntaxerror |
| Package assembly, reproducibility verification | Team syntaxerror |
| Integration into leaderboard submission | Challenge infrastructure (bartzbeielstein/challenge-leaderboard) |
| Real-world deployment, monitoring, retraining | Not applicable; this is a challenge entry, not a production system |

## 2. Intended Use and Scope

This pipeline forecasts the next 24 hours of electricity load for the German (DE) bidding zone, using only historical load data and publicly available ENTSO-E day-ahead price / renewable forecasts. The forecasts are produced once per day to support day-ahead market submissions or grid planning.

**Primary use cases:**
- Challenge participation and leaderboard ranking (current intended use)
- Reproducible pedagogical reference for time-series forecasting techniques
- Demonstration of bit-exact reproducibility in machine-learning pipelines
- Benchmark for comparing alternative forecasting methods

**Design constraints:**
- **No training inside this package.** The LightGBM hyperparameters are tuned offline via SpotOptim with a fixed random seed and then frozen into the pipeline.
- **Deterministic and stateless.** Given the same ENTSO-E data snapshot and tuning seed, the output is always identical on the same hardware.
- **24-hour ahead forecasting only.** The pipeline produces exactly one forecast per target day, not rolling or probabilistic forecasts.
- **Germany only.** The pipeline is hardcoded for the DE bidding zone; adaptation to other regions requires code changes.
- **Single-target regression.** Forecasts load only; price and renewable energy are exogenous inputs.

**What the pipeline does:**
1. Downloads or reads a frozen ENTSO-E data snapshot (load, renewables, price)
2. Validates data coverage and freshness against configured thresholds
3. Applies PACF-based lag selection to choose a subset of historical values
4. Constructs lag, cyclic (hour of day, day of week), and rolling-window features
5. Incorporates optional exogenous inputs (weather, day-of-week interactions)
6. Runs SpotOptim to tune the LightGBM hyperparameters
7. Trains a recursive LightGBM regressor on historical data
8. Forecasts the next 24 hours by recursive one-step-ahead prediction
9. Validates the output shape and schema; writes a CSV for leaderboard submission

**What it does NOT do:**
- Plot or visualize results (this package has no plotting dependencies)
- Automatically retrain or adapt to distribution shifts (retraining is manual)
- Quantify forecast uncertainty (produces point forecasts only)
- Handle missing values by automatic imputation (NaN/Inf raises an error)
- Support languages other than Python 3.13+

## 3. How to Get Started

### Installation & offline replay

Replay the exact 2026-06-08 forecast (deterministic mode, no API calls, uses bundled data):

```bash
# Install uv if not present: curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone or unzip the reproducibility package
git clone https://github.com/timhaeger/syntaxerror-prognose.git
cd syntaxerror-prognose

# Install dependencies (frozen exact versions)
uv sync --frozen

# Run offline replay (deterministic, bit-exact on arm64 macOS)
uv run python syntaxerror_submit.py \
    --skip-download \
    --as-of 2026-06-07T15:00:00Z \
    --deterministic \
    --n-trials 20 \
    --n-initial 10

# Verify bit-exactness
shasum -a 256 submissions/syntaxerror/2026-06-08.csv expected/2026-06-08_reference_deterministic.csv
```

If the checksums match, the reproduction is bit-identical. The run takes ~45 minutes (serial SpotOptim is the cost of determinism).

### Live forecasting (future dates)

Forecast tomorrow using live ENTSO-E data (requires API key):

```bash
export ENTSOE_API_KEY=your_token_here  # from https://transparency.entsoe.eu/

# Full operational run (~30 min, parallel SpotOptim, 100 trials)
uv run python syntaxerror_submit.py

# See all options
uv run python syntaxerror_submit.py --help
```

### Python API (programmatic use)

```python
from syntaxerror_submit import load_config_entsoe, prepare_pipeline, run_pipeline

# Load configuration
config = load_config_entsoe()

# Run the full pipeline (download → tune → forecast → validate → save)
result = run_pipeline(config, deterministic=False, n_trials=100)
print(f"Forecast shape: {result.forecast.shape}")
print(f"Output CSV: {result.submission_csv}")
```

See `syntaxerror_submit.py` docstring for full API and flag documentation.

## 4. Technical Specification

### Task definition

Univariate recursive 24-step-ahead forecasting of German electricity load (Germany, DE bidding zone) from ENTSO-E Transparency Platform data. Target frequency is one forecast per calendar day; production time is usually in the evening, because there is more data available. The target series is hourly observations of total German electricity load (MW).

### Mathematical formulation

Given a historical load series $\{x_1, x_2, \ldots, x_T\}$ (hourly), the pipeline constructs a feature matrix from:
- **Lags:** $x_{t-w}, \ldots, x_{t-1}$ (history window)
- **Cyclic features:** $\sin(2\pi h / 24)$, $\cos(2\pi h / 24)$ (hour of day)
- **Rolling stats:** mean/min/max over 24-h, 168-h (7-day) windows
- **PACF-selected lags:** automatic lag subset via partial autocorrelation function (data-driven)
- **Exogenous inputs:** renewable energy forecast, day-ahead price, day-of-week

Each row produces a single target $y_t = x_t$ (current load), never including $x_t$ on the feature side to prevent look-ahead leakage.

The predictor is a LightGBM gradient boosting regressor tuned via SpotOptim (Bayesian optimization). The hyperparameter search space includes:
- `num_leaves` (tree complexity)
- `learning_rate` (step size)
- `min_child_samples` (overfitting control)
- `subsample`, `colsample_bytree` (regularization)
- `max_depth` (tree structure)

Predictions are recursive: $\hat{y}_{T+h} = f(\hat{y}_{T+h-1}, \ldots, \hat{y}_{T+h-w}, \text{features}_{T+h})$ for $h = 1, \ldots, 24$.

### Architecture

**Five-layer design:**

1. **Data I/O layer** (`entsoe_*` from spotforecast2): Download and validate ENTSO-E load, price, renewables.
2. **Preprocessing layer** (`spotforecast2_safe`): PACF lag selection, cyclic encoding, rolling-window features, outlier detection, optional imputation.
3. **Tuning layer** (`SpotOptim`): Hyperparameter search (Bayesian optimization, fixed seed for reproducibility).
4. **Regression layer** (`LightGBM`, `sklearn` wrappers): Deterministic gradient boosting regressor, single-threaded mode for reproducibility.
5. **Forecasting layer** (`ForecasterRecursiveLGBM`): Recursive multi-step prediction, output validation, CSV schema compliance.

**Pipeline flow:**
```
ENTSO-E API / Snapshot
    ↓
Coverage & freshness validation
    ↓
PACF lag selection
    ↓
Feature engineering (lags, cyclic, rolling stats, exogenous)
    ↓
SpotOptim (Bayesian tuning, fixed seed=42)
    ↓
LightGBM training (single-threaded deterministic mode)
    ↓
Recursive 24-h forecast
    ↓
Output shape + schema validation
    ↓
CSV: [hour_0, hour_1, ..., hour_23] (MW)
```

### Design principles

1. **Determinism:** Same input, same seed → same output bit-for-bit (arm64 macOS).
2. **Fail-safe:** Invalid data (NaN, Inf, misaligned) raises explicit error; no silent repair.
3. **Leakage-free:** Future values never appear in current feature rows.
4. **Reproducibility:** All dependencies pinned; full environment in `pyproject.toml` + `uv.lock`.
5. **Offline capability:** Bundled data snapshot allows offline replay; live fetches are optional.

## 5. Interfaces and Runtime

### Inputs

| Input | Format | Source | Required? |
| --- | --- | --- | --- |
| Load history | pandas Series (hourly, MW) | ENTSO-E Transparency, `data/interim/energy_load.csv` | Yes |
| Renewable forecast | pandas DataFrame (wind%, solar%) | ENTSO-E Transparency, `data/interim/renewable_forecast.csv` | Optional (graceful skip if missing) |
| Day-ahead price | pandas Series (€/MWh) | ENTSO-E, `data/interim/day_ahead_price.csv` | Optional |
| Target date | ISO UTC string (e.g., `2026-06-08`) | Command-line `--as-of` or current date | Yes |

All time indices must be regular hourly grids aligned to UTC. Any gap or duplicate hour raises `ValueError`.

### Outputs

**Primary output: CSV submission**

```
hour,predicted_load
0,<MW_h0>
1,<MW_h1>
...
23,<MW_h23>
```

Decimal precision: float64 (saved as CSV, 2–6 significant digits typical). Strictly 24 rows required; any deviation is rejected by the leaderboard validator (`scripts/validate_submission.py`).

**Diagnostic outputs (optional, PNG format):**
- `*_acf_plot.png` — Autocorrelation function (PACF lag selection visualization)
- `*_importance_plot.png` — LightGBM feature importance
- `*_shap_summary.png` — SHAP force plot (feature attribution)
- `*_forecast_plot.png` — Historical load + 24-h forecast with uncertainty band
- `*_benchmark_plot.png` — syntaxerror vs. ENTSO-E baseline

### Runtime environment

| Property | Value |
| --- | --- |
| OS | macOS, Linux, Windows |
| Python | 3.13+ (tested 3.14.2) |
| CPU | Single-threaded deterministic mode (arm64 macOS reference); parallel mode runs on x86 / Linux / Windows but loses bit-exactness |
| GPU | Not used; no GPU support |
| Memory | Peak ~500 MB–1 GB typical (depends on history length and tuning complexity) |
| Duration | Deterministic: ~45 min (SpotOptim serial, 20 trials); Operational: ~30 min (parallel, 100 trials) |
| Network | Optional (ENTSO-E API calls); offline mode with bundled snapshot available (`--skip-download`) |

### Serialization

- **Model persistence:** LightGBM regressor saved as `.joblib` (compression level 3)
- **Forecast output:** Pandas DataFrame (in-memory) → CSV (leaderboard submission)
- **Figures:** PNG (optional diagnostic plots)
- **Reproducibility record:** Recorded in `MANIFEST.md` (provenance, environment pins, determinism statement)

**Reproducibility trade-off:**
- **Deterministic mode** (`--deterministic`, serial SpotOptim): bit-identical on arm64 macOS; reference CSV in `expected/`
- **Operational mode** (parallel SpotOptim): faster (~5–10 min vs. ~45 min), but NOT bit-reproducible across runs (parallel scheduling variance)

## 6. Data and Operational Design Domain

### Data sources and provenance

| Source | Data | Frequency | Retention | License |
| --- | --- | --- | --- | --- |
| ENTSO-E Transparency | Actual Total Load (ATL), Forecasted Load (day-ahead), renewable generation forecast | 15-min (aggregated to hourly) | 2022-01-01 → present | CC0 (public domain); see MANIFEST.md attribution |
| Open-Meteo (optional) | Temperature, humidity, cloud cover, wind speed | hourly | Cached during run; external call if fresh data needed | CC-BY 4.0 (free for non-commercial research) |
| Holiday calendar | DE national holidays, weekends | daily | Fixed via `holidays` package | Package license |

**Bundled snapshot** (this package, `data/interim/`):
- Frozen 2026-06-07 ~15:04 UTC
- Covers 2022-01-01 → 2026-06-08 21:45 UTC
- Enables offline reproduction and time-travel replay

### Operational Design Domain (ODD)

The conditions under which the forecasts are valid:

| Condition | Valid range | Outside the range |
| --- | --- | --- |
| **Target bidding zone** | Germany (DE) only | error; code change required for other zones |
| **Forecast horizon** | 1–24 hours ahead, produced once per day | unreliable; not tested for longer horizons |
| **Load data** | Regular hourly, no gaps, no duplicates, aligned to UTC | `ValueError` on any irregularity |
| **Load values** | 10,000–80,000 MW typical; physically plausible | large outliers (>100k MW or negative) trigger optional outlier detection |
| **Minimum history** | ≥96 hours (4 days) to compute lags; ≥730 days recommended for seasonal patterns | model cannot be fitted |
| **Training data freshness** | Data up to T-1 (yesterday); training window ≥2 years typical | forecast accuracy degrades |
| **Exogenous data** | Complete and aligned to load index; optional but gracefully skip if missing | error on misaligned rows; missing columns → feature skipped |
| **Concept drift** | Stable seasonal patterns, no regime change in infrastructure | accuracy drops; retraining recommended |
| **Extreme events** | Load behavior similar to recent history | blackouts, heatwaves, or COVID-like events degrade forecasts |

### Coverage validation (pipeline guards)

The pipeline enforces three checks before forecasting:

1. **Temporal frontier:** Last obs in data must be ≥ T-1 midnight UTC (ensures we can build features for day T).
2. **Temporal continuity:** No gaps >1 hour in the load series; if gaps are found, imputation is offered.
3. **Value sanity:** Load values in [5,000, 100,000] MW; outliers beyond this trigger detection.

If any check fails, the pipeline raises an explicit error with remediation instructions rather than proceeding with unreliable input.

### Training / test split (how models were built)

- **Training window:** 2024-01-01 → 2026-06-05 (18 months of historical data)
- **Validation window:** 2026-06-06 → 2026-06-07 (2 days for hyperparameter tuning)
- **Test window:** 2026-06-08 (1 day, the submission target)
- **No data leakage:** Tuning and testing never see the same days

### Known limitations and drift risk

1. **Seasonal resets:** Each summer and winter, load patterns shift due to heating/cooling changes; forecast error increases for 1–2 weeks after seasonal transitions.
2. **Holiday effects:** Public holidays and school vacations are encoded explicitly, but localized regional events (e.g., plant shutdowns) are unknown to the model.
3. **Infrastructure changes:** Grid modernization (e.g., rooftop solar adoption) alters the load profile; the model trains on recent data but cannot anticipate future structural shifts.
4. **Extreme weather:** Unusually hot/cold days cause load spikes not always proportional to temperature; the model captures only typical correlations.
5. **System disturbances:** Unplanned outages or emergency events (blackouts, cyberattacks) are outside the training domain.

To maintain forecast quality, **retraining is recommended weekly or monthly** with the latest data and a fresh tuning run.

## 7. Evaluation

### Accuracy metrics

This pipeline is evaluated on the leaderboard using **Mean Absolute Error (MAE)** measured against the actual (realized) German load on the day of submission:

$$\text{MAE} = \frac{1}{24} \sum_{h=0}^{23} \left| y_h - \hat{y}_h \right|$$

where $y_h$ is the actual load in hour $h$ and $\hat{y}_h$ is the forecast.

Performance depends on the target date, data quality, and tuning budget. Concrete accuracy numbers for a specific submission are recorded alongside that submission in the `expected/` directory and in the run logs; auditors should consult those artifacts for exact figures.

### Reproducibility evaluation

**Deterministic mode verification:**
```bash
shasum -a 256 submissions/syntaxerror/2026-06-08.csv
shasum -a 256 expected/2026-06-08_reference_deterministic.csv
```

On arm64 macOS with `--deterministic --n-trials 20 --n-initial 10`, the two checksums must match exactly. Any difference indicates:
- Platform/architecture mismatch (see MANIFEST.md)
- Different dependency versions (regenerate via `uv sync --frozen`)
- Altered source code or data

**Software quality checks:**
- All ENTSO-E data download paths validated (no silent failures)
- CSV schema enforced: exactly 24 rows, correct column names, numeric values
- Lag matrix construction leakage-free (guaranteed by spotforecast2-safe)
- SpotOptim seed set to `random_state=42` for reproducibility
- LightGBM trained with `deterministic=True`, `single_thread=True` (arm64 mode only)

## 8. Model Transparency

### Point vs. probabilistic forecasts

This pipeline produces **point forecasts only** (single value per hour). It does not natively quantify uncertainty or produce prediction intervals. If uncertainty estimates are needed, post-hoc methods (e.g., SHAP confidence intervals, ensemble bootstrapping) can be applied externally.

### White-box architecture

The entire pipeline is inspectable source code with no compiled inference kernels or opaque weights:

1. **Feature engineering:** Explicitly listed in `data/interim/` and logs (lag indices, cyclic transforms, rolling-window parameters)
2. **LightGBM model:** Feature importances available via `lgb_model.feature_importance()` (split importance, gain importance)
3. **SHAP values:** Optional diagnostic output (`*_shap_summary.png`) shows feature-by-feature attribution
4. **Hyperparameters:** All tuned values recorded in logs and diagnostic CSVs; SpotOptim optimization history can be replayed

### Feature importance

Post-hoc explainability is supported through:
- **LightGBM split importance:** Which features are used most frequently in tree splits
- **SHAP:** Force plots and summary plots showing how each feature contributed to the forecast for a specific hour
- **Partial Dependence:** How forecasts change as each feature varies (in diagnostic mode)

Example extraction:
```python
from syntaxerror_submit import load_trained_model
model = load_trained_model("path/to/model.joblib")
importances = model.lgb_model.feature_importance()
# Inspect to understand which lags and exogenous features matter most
```

### Audit trail

Every run produces timestamped logs recording:
- Data download sources and URLs
- PACF lag selection output
- Hyperparameter tuning progress (SpotOptim iterations)
- Training metrics (MAE, RMSE on hold-out validation)
- Forecast values and their components
- Reproducibility metadata (seed, architecture, Python version)

## 9. Operation: Monitoring and Response

### Monitoring checklist for production deployment

If this pipeline were deployed operationally (beyond the challenge), the operator should monitor:

1. **Data quality**
   - ENTSO-E API uptime and response time
   - Gaps or duplicates in hourly load grid
   - Out-of-range load values (e.g., <5k, >100k MW)
   - Misalignment between renewable forecast and load index

2. **Forecast quality**
   - MAE vs. a simple baseline (e.g., same-day-last-year, 7-day moving average)
   - Systematic bias (mean forecast error) — if forecast is consistently too high/low, retrain
   - Spike detection: if |error| > 2× typical, investigate data/events
   - Seasonal drift: after summer/winter transition, expect transient error increase

3. **Computational health**
   - Tuning time stability (should be ~5–10 min in operational mode)
   - Memory usage during training
   - Log file rotation (logs grow with each run)

### Response protocols

| Trigger | Action |
| --- | --- |
| Data gap >1 hour | Skip forecast; raise alert; check ENTSO-E status |
| MAE >10% above baseline | Trigger immediate retraining with fresh data |
| API timeout on ENTSO-E | Fall back to cached snapshot + `--skip-download`; alert ops |
| Feature value NaN/Inf | Fail fast; inspect logs for feature engineering failure |
| Seasonal transition (spring/autumn) | Expected 15–20% error spike for 1–2 weeks; monitor recovery |
| Forecast inconsistent with human judgment | Retrain with updated data; validate against domain expertise |

### Retraining schedule

**Recommended cadence:**
- **Weekly:** Full rerun with fresh SpotOptim tuning (to track recent trends)
- **Monthly:** Full re-fetch from ENTSO-E (archive cleanup, historical validation)
- **After any infrastructure change:** Immediate rerun (plant shutdown, grid upgrade, etc.)
- **Seasonal transitions:** Extra retrains in late March, late September

### Offline fallback

If ENTSO-E API is unavailable, the pipeline can operate in `--skip-download` mode using bundled snapshot data, with graceful accuracy degradation:
- Renewable forecast and price features skipped
- Load history frozen at last snapshot update
- Forecast quality reduced but still valid

## 10. Compliance and Leaderboard Submission

### Leaderboard submission requirements

This package is designed to produce valid leaderboard submissions. Every forecast is validated offline before upload:

| Check | Details |
| --- | --- |
| **CSV schema** | Columns: `hour`, `predicted_load`; types: int, float |
| **Row count** | Exactly 24 rows (one per hour 0–23) |
| **Hour index** | 0, 1, 2, …, 23 (no duplicates, no gaps) |
| **Values** | Numeric, finite (no NaN, Inf, or string values); range ~10k–80k MW typical |
| **Filename** | `YYYY-MM-DD.csv` (target date in ISO format) |

Validation script: `scripts/validate_submission.py` (runs post-forecast, prevents invalid submissions).

### Reproducibility record

Every submission is accompanied by:
- **MANIFEST.md:** Execution environment, data provenance, determinism statement
- **Logs:** Timestamped records of download, tuning, training, forecast
- **Diagnostic plots:** ACF, importance, SHAP, forecast plot, benchmark comparison
- **Checksums:** SHA-256 hashes in `expected/SHA256SUMS` for integrity verification

### Licensing and attribution

| Component | License | Attribution |
| --- | --- | --- |
| Reproducibility package | MIT | Team syntaxerror (course project SoSe26) |
| spotforecast2-safe | AGPL-3.0-or-later | Bartz-Beielstein et al., sequential-parameter-optimization |
| spotforecast2 | AGPL-3.0-or-later | Bartz-Beielstein et al. |
| SpotOptim | AGPL-3.0-or-later | Bartz-Beielstein et al. |
| LightGBM | MIT | Microsoft; see https://github.com/microsoft/LightGBM |
| ENTSO-E data | CC0 (Public Domain) | ENTSO-E Transparency Platform; see MANIFEST.md |

All dependencies are disclosed in `pyproject.toml` and locked in `uv.lock`.

## 11. Glossary

| Term | Meaning |
| --- | --- |
| **Bidding zone** | Geographic region for electricity market trading; Germany's is "DE". |
| **ENTSO-E** | European Network of Transmission System Operators for Electricity. |
| **PACF** | Partial Autocorrelation Function; used here to select which past hours are most predictive. |
| **Recursive forecasting** | Multi-step prediction where each forecast step uses previously predicted values as inputs for the next step. |
| **SpotOptim** | Sequential Parameter Optimization framework for Bayesian hyperparameter tuning. |
| **Leaderboard** | Live ranking of all challenge submissions (see bartzbeielstein/challenge-leaderboard). |
| **Bit-exact / bit-reproducible** | Output is identical byte-for-byte across identical runs (same hardware, seed, environment). |
| **Deterministic mode** | Serial (non-parallel) tuning with fixed seed → bit-exact on arm64 macOS. |
| **Operational mode** | Parallel tuning (faster) → not bit-exact (scheduling variance). |

## 12. How to Audit

An auditor or reviewer can validate this package as follows:

1. **Verify package integrity:**
   ```bash
   shasum -a 256 -c expected/SHA256SUMS
   ```
   All files must match; any mismatch indicates corruption or tampering.

2. **Reproduce the reference forecast (deterministic mode):**
   ```bash
   uv sync --frozen
   uv run python syntaxerror_submit.py \
       --skip-download \
       --as-of 2026-06-07T15:00:00Z \
       --deterministic \
       --n-trials 20 \
       --n-initial 10
   shasum -a 256 submissions/syntaxerror/2026-06-08.csv | \
       diff - expected/2026-06-08_reference_deterministic.csv
   ```
   Zero diff = reproducibility verified on arm64 macOS.

3. **Inspect source code and configuration:**
   - Read `syntaxerror_submit.py` for the full pipeline logic
   - Check `teams.yml` for submission metadata
   - Review `MANIFEST.md` for provenance and environment pins

4. **Validate dependency versions:**
   ```bash
   uv tree  # Show all transitive dependencies
   diff <(grep dependencies pyproject.toml) expected_dependencies.txt
   ```
   Verify no unexpected packages are included.

5. **Check data sources and attribution:**
   - Inspect `data/interim/*.csv` for ENTSO-E metadata
   - Verify licenses: `README.md`, `MANIFEST.md`
   - Confirm no proprietary or restricted data is bundled

6. **Test leaderboard submission validation:**
   ```bash
   uv run python scripts/validate_submission.py submissions/syntaxerror/2026-06-08.csv
   ```
   Should complete without errors if output is schema-compliant.

## 13. Citation and Contact

### How to cite this work

For the reproducibility package:
```bibtex
@misc{syntaxerror2026,
  author       = {Team Syntaxerror},
  title        = {{syntaxerror} Forecast Pipeline: Reproducibility Package},
  year         = {2026},
  howpublished = {\url{https://github.com/timhaeger/syntaxerror-prognose}},
  note         = {Lastprognose-Challenge SoSe26 submission}
}
```

### Upstream references

This work builds on:

- **spotforecast2-safe** and **spotforecast2**: Bartz-Beielstein, T. (2026). Sequential Parameter Optimization. Available at https://github.com/sequential-parameter-optimization/
- **Lecture:** Bartz-Beielstein, T. (2026). *Safety-Critical Time-Series Forecasting with spotforecast2-safe*. Available at https://github.com/bartzbeielstein/bart26k-lecture
- **Leaderboard:** Challenge infrastructure at https://github.com/bartzbeielstein/challenge-leaderboard

### Contact and support

- **Package issues:** GitHub Issues at https://github.com/timhaeger/syntaxerror-prognose/issues
- **Challenge questions:** See https://bartzbeielstein.github.io/challenge-leaderboard/ for leaderboard rules and FAQ
- **Upstream library:** For spotforecast2-safe issues, open an issue at https://github.com/sequential-parameter-optimization/spotforecast2-safe

## 14. Disclaimer and Liability

**Limitation of liability.** This reproducibility package and forecasting pipeline are provided as is, without warranty of any kind. The authors and contributors accept no liability for any direct or indirect damage, forecast error, system failure, or financial loss arising from their use.

### Specific disclaimers

- **Forecast accuracy is not guaranteed.** Electricity load is influenced by unpredictable factors (weather, events, infrastructure changes) that are outside the model's knowledge. Forecasts may be significantly wrong.
- **For research and education only.** This is a course project and challenge entry, not a production forecasting system. Do not use it for critical operational decisions without independent validation.
- **Data quality is as-is.** ENTSO-E data is used under its public data terms; errors in upstream data are propagated without correction.
- **Not a replacement for domain expertise.** Grid operators, traders, and planners must always apply human judgment and domain knowledge alongside automated forecasts.
- **Reproducibility on non-reference platforms.** Bit-exactness is only claimed for arm64 macOS. Runs on Linux, Windows, or Intel macOS may produce slightly different results due to floating-point rounding.

### Challenge-specific disclaimers

- **Leaderboard rankings are provisional.** This package represents one team's approach; the leaderboard is for educational comparison, not operational deployment.
- **APIs may be unavailable.** ENTSO-E Transparency may experience downtime; bundled snapshot fallback has limited freshness.
- **No guarantee of continued maintenance.** This is a course project. The repository may be archived or deleted after the course ends.

It is the sole responsibility of anyone using this code to validate it against their requirements and to ensure its safe operation in their context.
