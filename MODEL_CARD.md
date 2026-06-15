# Model/Method Card: spotforecast2-safe

This card describes what spotforecast2-safe is, how to use it safely, the conditions under which its results are valid, and the responsibilities it places on anyone who deploys it. It follows the [Hugging Face Model Card Guidebook](https://huggingface.co/docs/hub/model-card-guidebook) taxonomy.

## 1. Model Details

| Field | Value |
| --- | --- |
| Name | spotforecast2-safe |
| Version | 22.9.0 |
| Type | Deterministic Python library for time series feature engineering and recursive multi-step forecasting. It performs no training of its own. |
| Developed by | Thomas Bartz-Beielstein, ORCID [0000-0002-5938-5158](https://orcid.org/0000-0002-5938-5158) |
| Distributed by | the `sequential-parameter-optimization` GitHub organization |
| Language | Python 3.13 or newer |
| License | AGPL-3.0-or-later (Affero General Public License) |
| Repository | <https://github.com/sequential-parameter-optimization/spotforecast2-safe> |
| Technical report | `bart26h/index.qmd`, shipped in the source tree |

The library depends only on numpy, pandas, scikit-learn, lightgbm, numba, pyarrow, requests, feature-engine, holidays, astral, and tqdm. It deliberately excludes plotly, matplotlib, spotoptim, optuna, torch, and tensorflow, so no plotting or automated-tuning code ships in this package.

Two Common Platform Enumeration (CPE) identifiers let vulnerability-tracking and software bill of materials (SBOM) tools recognize the package. The wildcard identifier `cpe:2.3:a:sequential_parameter_optimization:spotforecast2_safe:*:*:*:*:*:*:*:*` matches any release; the current release is `cpe:2.3:a:sequential_parameter_optimization:spotforecast2_safe:22.9.0:*:*:*:*:*:*:*`.

The library itself is a low-risk component: it is deterministic, its source is fully inspectable, and it fails safe on invalid input. It is built to support high-risk AI systems in the sense of the EU AI Act, but it is not itself such a system. When it is embedded in a high-risk deployment, the duties that attach to that system fall on the integrator, not on the library.

Responsibilities are divided as follows.

| Responsibility | Party | Contact |
| --- | --- | --- |
| Library development and maintenance | Thomas Bartz-Beielstein | `bartzbeielstein@gmail.com` |
| Distribution | sequential-parameter-optimization on GitHub | repository issue tracker |
| Deployment, operation, and audit | the system integrator | defined per deployment |

The current release is 22.9.0, with a stable public interface pinned in `spotforecast2_safe.__init__.__all__`. The full version history, including release dates, is recorded in `CHANGELOG.md` and on the GitHub Releases page; it is maintained automatically by the release pipeline and is not repeated here.

## 2. Intended Use and Scope

spotforecast2-safe prepares time series data for regression models in auditable settings such as energy supply, finance, and industrial monitoring. It runs in resource-constrained or embedded environments where heavier machine-learning frameworks are unavailable, and it produces bit-for-bit reproducible lag transformations with no hidden randomness.

The feature matrices it builds feed directly into scikit-learn regressors, LightGBM, or XGBoost, either through the bundled `ForecasterRecursiveLGBM` and `ForecasterRecursiveXGB` wrappers or through custom forecasters built on the `ForecasterRecursiveModel` base class.

The package has clear limits. It does not visualize data, since no plotting backend ships with it. It does not tune hyperparameters; tuning belongs in a separate workflow outside the safety-critical environment. It does not clean data silently: missing (NaN) or infinite (Inf) values raise an error rather than being imputed without the caller's consent.

## 3. How to Get Started

```bash
pip install spotforecast2-safe
```

```python
import numpy as np
import pandas as pd
from spotforecast2_safe import ForecasterRecursiveLGBM

# A short hourly demonstration series
idx = pd.date_range("2023-01-01", periods=50, freq="h")
y = pd.Series(100 + 10 * np.sin(np.linspace(0, 4 * np.pi, 50)), index=idx)

forecaster = ForecasterRecursiveLGBM(iteration=0, lags=3)
forecaster.fit(y=y)
predictions = forecaster.forecaster.predict(steps=2)
```

A complete reference workflow, which compares a seasonal baseline, a covariate model, and a tuned LightGBM forecaster against ground truth, is registered as a console script:

```bash
uv run spotforecast-safe-demo
```

Its source is in `src/spotforecast2_safe/tasks/task_safe_demo.py`.

## 4. Technical Specification

### Task and model family

The library addresses recursive multi-step forecasting of a univariate time series from its own past values (lags), rolling-window features, and exogenous regressors. The forecasters are scikit-learn-compatible wrappers around a regressor that the caller supplies, such as LightGBM or XGBoost. The wrapper handles feature construction, the recursive prediction loop, and persistence, while the supplied regressor handles learning. The library fixes no model size, because size is a property of the chosen regressor and its configuration.

### Mathematical description

For a univariate series $X = \{x_1, x_2, \ldots, x_T\}$ and a window of $w$ lags, the transformation builds one feature row per target value:

$$X_{row, t} = [x_{t-w}, x_{t-w+1}, \ldots, x_{t-1}] \rightarrow y_t = x_t.$$

The target $y_t$ never appears in its own feature row, which prevents look-ahead leakage by construction.

### Architecture

The package is layered. The `forecaster` layer holds the low-level estimator wrappers. The `preprocessing` layer holds deterministic transformers such as `ExogBuilder`, `RepeatingBasisFunction`, `QuantileBinner`, and `TimeSeriesDifferentiator`. The `model_selection` layer holds time-aware cross-validation (`TimeSeriesFold`, `OneStepAheadFold`, and `backtesting_forecaster`), which avoids the future-data leakage that ordinary random splits cause. The `manager` layer orchestrates these into `ForecasterRecursiveLGBM`, `ForecasterRecursiveXGB`, and the `ConfigEntsoe` configuration object. The `processing` and `tasks` layers compose these into end-to-end pipelines and console entry points.

### Training

The library trains nothing on its own. Training happens in the downstream regressor and is the integrator's responsibility, so the training data, hyperparameters, and learning schedule belong to each deployment rather than to the library. The bundled demo is a concrete, reproducible example of such a deployment.

Running `uv run spotforecast-safe-demo` forecasts an aggregated hourly energy series from a bundled CSV fixture. The demo uses a 24-hour forecast horizon, 24 lags, a 72-hour rolling window, an outlier-contamination fraction of 0.01, and an 80/20 train and test split, with a fixed random seed of 42. It builds calendar, cyclic, day-and-night (from sunrise and sunset), weather, and holiday features for the Dortmund location (51.5136, 7.4653). One of the three models it compares is a LightGBM regressor with the following configuration:

| Hyperparameter | Value |
| --- | --- |
| n_estimators | 1059 |
| learning_rate | 0.0419 |
| num_leaves | 212 |
| min_child_samples | 54 |
| subsample | 0.501 |
| colsample_bytree | 0.608 |
| random_state | 42 |
| verbose | -1 |

These are the demo's chosen values, shown to illustrate a deployment, not a recommended default.

### Design objectives

Three properties hold by design. The library is deterministic, so the same input produces the same output bit for bit. Its construction is leakage-free, so a target value is never part of its own feature row. Its behavior is fail-safe, so invalid input raises an explicit exception instead of being silently repaired.

## 5. Interfaces and Runtime

The target is a numeric univariate series (a pandas Series or NumPy array) carrying a regular, monotonic date-time index. Exogenous features are a numeric pandas DataFrame aligned to that index and complete; any missing entry in the exogenous features raises a `ValueError` before a prediction is made. Inside the pipeline the data passes through lag-matrix construction, cyclic encoding of calendar features, optional outlier handling and imputation that the caller enables explicitly, and a cast of the feature matrix to 32-bit floating point for memory efficiency. The forecaster returns predictions as a series whose length equals the requested horizon (24 steps in the demo), in the same units as the target. A fitted forecaster is serialized with joblib at compression level 3 using the `.joblib` extension, and is reloaded through the same persistence helpers.

The library runs on Python 3.13 or newer on a central processing unit (CPU). It needs no graphics processing unit (GPU) and ships no GPU code. Building the lag matrix duplicates the input, so peak memory grows in proportion to the series length times the window size. Bit-for-bit reproducibility assumes deterministic regressor settings: the bundled LightGBM wrapper enables LightGBM's deterministic and column-wise flags, and single-threaded execution removes any remaining floating-point reordering.

All runtime dependencies carry permissive licenses, which keeps the combined distribution simple for integrators. The library itself is distributed under the copyleft AGPL-3.0-or-later license.

| Dependency | License |
| --- | --- |
| numpy | BSD-3-Clause |
| pandas | BSD-3-Clause |
| scikit-learn | BSD-3-Clause |
| feature-engine | BSD-3-Clause |
| numba | BSD |
| lightgbm | MIT |
| holidays | MIT |
| pyarrow | Apache-2.0 |
| requests | Apache-2.0 |
| astral | Apache-2.0 |
| tqdm | MPL-2.0 and MIT |

Because the library performs no training and uses no GPU, its own energy cost is small. Runtime cost is dominated by vector operations during feature engineering and by whatever regressor the caller trains. A typical LightGBM fit on an hourly series of about 100,000 rows completes in seconds on one commodity CPU core. No pretrained weights ship with the package, so there are no embedded training emissions to report.

## 6. Data and Operational Design Domain

The fixtures under `src/spotforecast2_safe/datasets/csv/` and the demo dataset support reproducible documentation and tests; production data is supplied by the integrator. Docstring examples in the source are executed as tests, and time-aware cross-validation is used during validation so that no future observation can influence a past prediction.

The Operational Design Domain (ODD) is the set of conditions under which the library's results are valid. Outside these conditions the library is designed to raise an error rather than return an unreliable result.

| Condition | Valid range | Outside the range |
| --- | --- | --- |
| Target series | numeric, univariate, with a regular and monotonic date-time index | error |
| Exogenous features | numeric, complete, aligned to the target index | `ValueError` on any missing entry |
| Sampling interval | uniform; hourly in the demo | unreliable result |
| Minimum history | longer than the window size plus the number of lags, about 96 hourly points for the demo defaults | the model cannot be called |
| Missing target values | rejected unless the caller explicitly enables imputation | error |
| Series length | validated to about one million rows; beyond about ten million the caller must process the series in chunks | memory exhaustion |
| Numeric precision | feature matrices computed in 32-bit floating point | values needing higher precision fall outside the domain |
| Any invalid input | not applicable | explicit `ValueError` or `TypeError`, never silent repair |

Forecast accuracy is bounded by the downstream regressor and its training data, so concept drift, seasonal shifts, or regime changes degrade forecasts even when the feature engineering stays correct. Users who build lag or calendar features outside the provided builders risk leaking a target value into its own feature row; the bundled `ExogBuilder` and task paths are leakage-free, hand-rolled pipelines are not. Operating states that are scarce in the training data are forecast less reliably than common ones.

To stay inside the valid domain, validate every new deployment against historical ground truth before it carries live traffic, build features only through `ExogBuilder` or the bundled tasks, keep the regressor deterministic when reproducibility is required, and process very long series in windowed chunks.

## 7. Evaluation

Because no training runs inside the library, classical accuracy metrics do not describe the library itself. The library is evaluated on software-quality properties, while forecast accuracy is a property of each deployment.

DataFrames that contain missing or infinite values raise a `ValueError`. The public loaders `load_timeseries`, `load_timeseries_forecast`, and `WeatherService.get_dataframe` refuse to return silently imputed values unless the caller opts in. Input types are checked at runtime, identical input yields identical output bytes, and new code carries at least 80 percent line coverage. CPE identifier generation is tested directly. Excluding heavy dependencies keeps the Common Vulnerabilities and Exposures (CVE) attack surface small: there is no web server, no deep-learning runtime, and no plotting backend.

For deployments, the demo computes mean absolute error (MAE) and mean squared error (MSE) when it compares each model against ground truth. These metrics are deterministic and can be reproduced by running the demo. Their numerical values depend on the data vintage and are therefore not fixed in this card.

## 8. Model Transparency

The library produces point forecasts. It does not natively quantify or calibrate predictive uncertainty, so a deployment that needs prediction intervals or calibrated probabilities must add them in the downstream regressor or a wrapper around it.

The code is white-box: there are no compiled inference kernels and no opaque weights, so every transformation can be read and audited in source. Feature attributions are available through the downstream regressor's own importance measures, for example LightGBM's split and gain importances. The package ships no separate explainability backend such as SHAP or LIME, consistent with its minimal-dependency policy.

## 9. Operation: Monitoring and Response

A deployment should watch the quality of incoming data (missing or out-of-range values and gaps in the timestamps), the drift of the input and target distributions away from the training period, and the forecast error measured against a simple baseline. The production configuration carries a refit cadence, with a default of seven days, and a maximum-model-age policy that signals when retraining is due.

When monitoring crosses a deployment-defined threshold, the usual responses are to refit or retrain the model, to fall back to the seasonal baseline forecaster or the last known-good model, and to alert the responsible team. A dual-handler logger writes timestamped records to the console and to files under `~/spotforecast2_safe_models/logs/`, which supports audit retention. The thresholds and escalation steps are owned by the integrator.

## 10. Compliance Support

The package is built to support the development of high-risk AI systems under the EU AI Act. The package itself is not certified; full-system certification is the integrator's responsibility.

It rejects missing or infinite data by default, which supports the data-governance duty of Article 10. This card together with the technical report forms a technical-documentation baseline for Article 11, and the CPE identifiers in Section 1 feed SBOM and vulnerability-tracking pipelines. The logging facility supports the record-keeping duty of Article 12. The white-box code supports the transparency duty of Article 13. The deterministic, reproducible transformations support the accuracy-and-robustness duty of Article 15, while formal system-level verification remains the integrator's responsibility.

The authoritative mapping to IEC 61508, ISO 26262, ISA/IEC 62443, and the individual EU AI Act articles is maintained in the technical report (`bart26h/index.qmd`, section Compliance Mapping). These references reflect the standards as of 2026-04-19; users must track later amendments themselves.

## 11. Glossary

| Term | Meaning |
| --- | --- |
| EU AI Act | Regulation (EU) 2024/1689 on artificial intelligence, in force since 2024-08-01. |
| IEC 61508 | International standard for the functional safety of electrical, electronic, and programmable electronic safety-related systems. |
| ISA/IEC 62443 | Standard series for the security of industrial automation and control systems. |
| ISO 26262 | International standard for the functional safety of road vehicles. |

## 12. How to Audit

An auditor can validate this package as follows.

1. Inspect `pyproject.toml` to confirm that none of the prohibited libraries (plotly, matplotlib, spotoptim, optuna, torch, tensorflow) are present.
2. Run `uv run pytest tests/` to confirm functional correctness and the full test suite.
3. Run `uv run pytest tests/test_cpe.py` to confirm CPE identifier generation.
4. Record the CPE identifiers from Section 1 in vulnerability-tracking systems and supply-chain disclosures.
5. Read `get_cpe_identifier` in `src/spotforecast2_safe/utils/cpe.py` for use in automated workflows.
6. Run `uv run reuse lint` to confirm license and copyright-header compliance.

## 13. Citation, Authors, and Contact

Maintainer: Thomas Bartz-Beielstein, ORCID [0000-0002-5938-5158](https://orcid.org/0000-0002-5938-5158), `bartzbeielstein@gmail.com`.

```bibtex
@misc{spotforecast2safe,
  author       = {Bartz-Beielstein, Thomas},
  title        = {{spotforecast2-safe}: Safety-critical Subset of {spotforecast2}},
  year         = {2026},
  howpublished = {\url{https://github.com/sequential-parameter-optimization/spotforecast2-safe}},
  note         = {AGPL-3.0-or-later}
}
```

Or as a formatted reference: Bartz-Beielstein, T. (2026). *spotforecast2-safe: Safety-critical subset of spotforecast2* (Version 22.9.0) [Computer software]. https://github.com/sequential-parameter-optimization/spotforecast2-safe

The technical report (`bart26h/index.qmd`) is the long-form reference for design rationale, compliance mapping, and evaluation protocol.

## 14. Disclaimer and Liability

**Limitation of liability.** This library is designed with safety principles and deterministic logic, but it is provided as is, without warranty of any kind. The authors and contributors accept no liability for any direct or indirect damage, system failure, or financial loss arising from its use.

It is the sole responsibility of the system integrator to perform full system-level safety validation, for example under ISO 26262, IEC 61508, or the EU AI Act, before deploying this software in a production or safety-critical environment.
