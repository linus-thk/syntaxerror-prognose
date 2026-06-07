#!/usr/bin/env python3
"""Standalone reproduction of the operational pipeline in
``bart26k-lecture/14_team_4_submission.qmd`` (chapter 14, team_4 advanced submission),
adapted for team syntaxerror, runnable independently of Quarto.

It mirrors the chapter's *non-teaching* path --- download -> coverage guard ->
PACF lag selection -> ConfigEntsoe -> MultiTask(spotoptim) -> y_0 -> submission
CSV -> validate --- and optionally opens the leaderboard PR. The ~7 plotly
*teaching* visuals (endogenous / outliers / imputation / weather / rbf /
holidays / poly) and the prose availability tables are intentionally omitted;
five run-diagnostic figures (ACF, feature importance, SHAP, the forecast plot,
and team_4-vs-ENTSO-E) are saved as PNGs.

The reason this script exists: a render of chapter 14 aborted when ENTSO-E
returned transient HTTP 504/503 and ``download_new_data`` exhausted its shallow
5x/5s retry budget. This script wraps the download in an outer exponential-
backoff loop and an optional cached-data fallback so a transient outage no
longer kills the whole job.

Run it against the book's pinned venv (do NOT add a PEP-723 ``# /// script``
block --- that would build an isolated env and re-resolve spotforecast2*):

    cd /Users/bartz/bart26k-lecture
    export ENTSOE_API_KEY=...
    uv run python scripts/team4_submit.py            # full live run
    uv run python scripts/team4_submit.py --help     # all flags

SYNC NOTE --- this file duplicates chapter-14 logic. When ch14 changes any of:
the env homes (`team4-imports`), the date constants (`team4-constants`), the
coverage guards (`team4-interim`/`team4-cutoff`), the PACF rule (`fig-team4-acf`),
the ConfigEntsoe arguments (`team4-config`), the pipeline method order
(`team4-prepare`...`team4-train`), or the submission schema
(`team4-submission-write`), re-sync this script. The .qmd is the source of truth.
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# Headless backend MUST be selected before anything (incl. shap) imports pyplot.
import matplotlib

matplotlib.use("Agg")

import pandas as pd

# --- defaults pinned to the chapter-14 values (see SYNC NOTE) -----------------
COUNTRY = "DE"
DEFAULT_TEAM_ID = "syntaxerror"
START_DOWNLOAD = "202201010000"
DATA_SUBDIR = "syntaxerror_submission"      # under ~/spotforecast2_data/
CACHE_SUBDIR = "syntaxerror_submission"     # under ~/.spotforecast2_cache/
OUTLIER_IQR_K = 5
MAX_ACTUAL_LAG_HOURS = 72                # team4-interim guard (qmd line 252)
LAG_FALLBACK = [1, 2, 24, 168]
TRAIN_YEARS = 1
PREDICT_SIZE = 24
REFIT_SIZE = 7
NUMBER_FOLDS = 10
IMPUTATION_WINDOW_SIZE = 24
N_TRIALS_SPOTOPTIM = 50
N_INITIAL_SPOTOPTIM = 10
N_TRIALS_OPTUNA = 15

logger = logging.getLogger("syntaxerror_submit")


class Abort(Exception):
    """Raise to stop with a specific process exit code (see exit-code table)."""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class Dates:
    now: pd.Timestamp
    today: pd.Timestamp
    yesterday: pd.Timestamp
    tomorrow: pd.Timestamp
    last_target: pd.Timestamp
    start_dl: str
    end_dl: str


@dataclass
class Coverage:
    last_full_hour: pd.Timestamp
    first_pred: pd.Timestamp
    live_n_steps: int


# --- CLI + logging ------------------------------------------------------------
def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="teamsyntaxerror_submit",
        description="Standalone team_4 live forecast + submission (chapter 14).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--team-id", default=DEFAULT_TEAM_ID,
                   help="registry check + submission directory")
    p.add_argument("--skip-download", action="store_true",
                   help="reuse the cached interim CSV; no ENTSO-E API call")
    p.add_argument("--max-retries", type=int, default=5,
                   help="outer download attempts (each wraps the library's 5x loop)")
    p.add_argument("--backoff", type=float, default=5.0,
                   help="base seconds for exponential backoff between outer attempts")
    p.add_argument("--allow-stale", action="store_true",
                   help="permit cache fallback when the API is down "
                        "(still gated by the D-1 23:00 freshness check)")
    p.add_argument("--data-end", default=None,
                   help="override END_DOWNLOAD as YYYYMMDDHHMM (freezes the window)")
    p.add_argument("--no-validate", action="store_true",
                   help="skip the leaderboard validator subprocess")
    p.add_argument("--push", action="store_true",
                   help="branch + commit + open the auto-merging PR via gh")
    p.add_argument("--n-jobs", type=int, default=-1,
                   help="n_jobs_spotoptim (-1 = all cores; 0 = serial)")
    p.add_argument("--deterministic", action="store_true",
                   help="force serial SpotOptim (n_jobs=None) for bit-reproducible runs")
    p.add_argument("--n-trials", type=int, default=N_TRIALS_SPOTOPTIM,
                   help="n_trials_spotoptim (lower for a fast smoke run)")
    p.add_argument("--n-initial", type=int, default=N_INITIAL_SPOTOPTIM,
                   help="n_initial_spotoptim")
    p.add_argument("--train-years", type=int, default=TRAIN_YEARS,
                   help="training window length in years")
    p.add_argument("--figures-dir", default=None,
                   help="where to save diagnostic PNGs "
                        "(default: <data_home>/figures/<target-date>/)")
    p.add_argument("--no-figures", action="store_true",
                   help="skip all diagnostic figures")
    p.add_argument("--leaderboard-root",
                   default=str(Path.home() / "workspace" / "challenge-leaderboard"),
                   help="sibling challenge-leaderboard clone")
    p.add_argument("-v", "--verbose", action="count", default=0,
                   help="-v: show downloader INFO; -vv: DEBUG everywhere")
    return p.parse_args(argv)


def setup_logging(verbosity: int) -> None:
    # Keep the packages quiet by default (like the chapter's basicConfig WARNING)
    # but give our own logger a dedicated handler so its INFO always shows.
    logging.basicConfig(level=logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [team4_submit] %(levelname)s %(message)s",
                                           "%H:%M:%S"))
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if verbosity >= 2 else logging.INFO)
    logger.propagate = False
    if verbosity >= 1:
        logging.getLogger("spotforecast2_safe.downloader.entsoe").setLevel(logging.INFO)
    if verbosity >= 2:
        for name in ("spotforecast2", "spotforecast2_safe"):
            logging.getLogger(name).setLevel(logging.DEBUG)


# --- environment, registry, dates ---------------------------------------------
def configure_environment() -> None:
    """Mirror the qmd ``team4-imports`` cell: fork start method + isolated homes.

    Must run before any spotforecast2* import / MultiTask / download call;
    get_data_home()/get_cache_home() read these env vars at call time.
    """
    os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")
    import multiprocessing as mp

    try:
        mp.set_start_method("fork", force=True)
    except (RuntimeError, ValueError):
        logger.warning("could not set multiprocessing start method to 'fork'; "
                       "pass --n-jobs 0 for serial tuning if pool workers fail.")
    os.environ["SPOTFORECAST2_DATA"] = str(Path.home() / "spotforecast2_data" / DATA_SUBDIR)
    os.environ["SPOTFORECAST2_CACHE"] = str(Path.home() / ".spotforecast2_cache" / CACHE_SUBDIR)


def check_team_registry(team_id: str, lb_root: Path) -> None:
    """qmd ``team4-registry`` (lines 54-66): fail-loud if team_id is unknown."""
    import yaml

    teams_yml = lb_root / "teams.yml"
    if not teams_yml.exists():
        raise Abort(3, f"teams.yml not found at {teams_yml}; "
                       f"is challenge-leaderboard cloned at {lb_root}?")
    teams = yaml.safe_load(teams_yml.read_text())["teams"]
    team = next((t for t in teams if t["id"] == team_id), None)
    if team is None:
        raise Abort(3, f"{team_id} is not registered in {teams_yml}")
    logger.info("team %s : %s | github: %s", team_id,
                team.get("display_name", "?"),
                ", ".join(team.get("github_handles", [])))


def compute_dates(now: pd.Timestamp, data_end: str | None) -> Dates:
    """qmd ``team4-constants`` (lines 146-167). `now` is captured once upstream."""
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    else:
        now = now.tz_convert("UTC")
    today = now.normalize()
    yesterday = today - pd.Timedelta(days=1)
    tomorrow = today + pd.Timedelta(days=1)
    last_target = tomorrow + pd.Timedelta(hours=23)
    if data_end:
        try:
            pd.to_datetime(data_end, format="%Y%m%d%H%M", utc=True)
        except Exception as exc:  # noqa: BLE001
            raise Abort(1, f"--data-end {data_end!r} is not YYYYMMDDHHMM: {exc}")
        end_dl = data_end
    else:
        end_dl = (tomorrow + pd.Timedelta(days=1)).strftime("%Y%m%d%H%M")
    return Dates(now, today, yesterday, tomorrow, last_target, START_DOWNLOAD, end_dl)


# --- download (robust) + interim cache ----------------------------------------
def robust_download(api_key: str, dates: Dates, *, max_retries: int,
                    backoff: float, force: bool = True) -> bool:
    """qmd ``team4-download`` (lines 172-185), wrapped in an outer exponential-
    backoff loop. Returns True on success, False after exhausting attempts.

    The venv's download_new_data already retries 5x/5s internally and raises
    RuntimeError on persistent HTTP 504/503; this outer loop multiplies that
    resilience without editing shipped safety code.
    """
    from spotforecast2_safe.downloader.entsoe import download_new_data

    for attempt in range(1, max_retries + 1):
        try:
            download_new_data(
                api_key=api_key,
                country_code=COUNTRY,
                start=dates.start_dl,
                end=dates.end_dl,
                force=force,
                keep_forecast_future=True,
            )
            logger.info("ENTSO-E download succeeded on attempt %d/%d", attempt, max_retries)
            return True
        except Exception as exc:  # noqa: BLE001 -- download_new_data raises RuntimeError
            wait = backoff * (2 ** (attempt - 1))
            logger.warning("ENTSO-E download attempt %d/%d failed: %s",
                           attempt, max_retries, exc)
            if attempt < max_retries:
                logger.warning("retrying in %.0fs (exponential backoff) ...", wait)
                time.sleep(wait)
    logger.error("ENTSO-E download failed after %d outer attempts.", max_retries)
    return False


def load_interim() -> pd.DataFrame:
    """qmd ``team4-interim`` read (lines 236-238)."""
    from spotforecast2_safe.data.fetch_data import get_data_home

    interim_csv = get_data_home() / "interim" / "energy_load.csv"
    if not interim_csv.exists():
        raise Abort(2, f"no interim cache at {interim_csv}; cannot proceed "
                       f"without a successful download.")
    interim = pd.read_csv(interim_csv, index_col=0, parse_dates=True)
    interim.index = pd.to_datetime(interim.index, utc=True)
    logger.info("interim CSV: %s  (%d rows, %s -> %s)",
                interim_csv, len(interim), interim.index.min(), interim.index.max())
    return interim


def assert_coverage(interim: pd.DataFrame, dates: Dates, *, fallback: bool) -> Coverage:
    """qmd coverage guards (lines 240-262) + cutoff (lines 322-325).

    `fallback=True` (cache reused because the download was skipped/failed) adds a
    stricter gate: the published actuals must reach at least *yesterday 23:00 UTC*
    --- a full most-recent complete UTC day --- before we build a submission off
    cached data. (The plan's "D-1 23:00" phrasing resolves to yesterday 23:00 for
    a target day of *tomorrow*; today 23:00 is in the future and unpublishable.)
    """
    required_last = dates.today - pd.Timedelta(hours=1)
    if interim.index.max() < required_last:
        raise Abort(1, f"ENTSO-E coverage is stale: last interim row "
                       f"{interim.index.max()} < required {required_last}.")

    actual = interim["Actual Load"].dropna()
    if actual.empty:
        raise Abort(1, "interim CSV has no published Actual Load values.")
    last_actual = actual.index.max()
    if last_actual < dates.now - pd.Timedelta(hours=MAX_ACTUAL_LAG_HOURS):
        lag_h = int((dates.now - last_actual) / pd.Timedelta(hours=1))
        raise Abort(1, f"Actual Load is stale: last published {last_actual}, "
                       f"{lag_h} h before now; tolerance {MAX_ACTUAL_LAG_HOURS} h.")

    last_full_hour = last_actual.floor("h")
    if fallback:
        gate = dates.yesterday + pd.Timedelta(hours=23)  # yesterday 23:00 UTC
        if last_full_hour < gate:
            raise Abort(2, f"cached actuals end {last_full_hour} < {gate} "
                           f"(yesterday 23:00 UTC); refusing to submit a stale "
                           f"forecast. Re-run when ENTSO-E is reachable.")

    first_pred = last_full_hour + pd.Timedelta(hours=1)
    live_n_steps = int((dates.last_target - first_pred).total_seconds() // 3600) + 1
    logger.info("end_train=%s  first_pred=%s  last_target=%s  predict_size=%d",
                last_full_hour, first_pred, dates.last_target, live_n_steps)
    return Coverage(last_full_hour, first_pred, live_n_steps)


def entsoe_predictions(interim: pd.DataFrame) -> pd.Series:
    """qmd ``team4-entsoe-predictions`` (lines 283-284): ENTSO-E's own day-ahead
    forecast on the hourly grid (baseline only; never trained on)."""
    preds = interim["Forecasted Load"].resample("h", label="left", closed="left").mean().dropna()
    if preds.index.tz is None:
        preds.index = preds.index.tz_localize("UTC")
    else:
        preds.index = preds.index.tz_convert("UTC")
    preds.name = "Forecasted Load"
    return preds


# --- PACF lag selection (logic + optional plot) -------------------------------
def select_key_lags(interim: pd.DataFrame, last_full_hour: pd.Timestamp,
                    figdir: Path | None) -> list[int]:
    """qmd ``fig-team4-acf`` (lines 518-537), plot stripped out (optional save)."""
    import numpy as np
    from spotforecast2.stats.autocorrelation import calculate_lag_autocorrelation

    acf_series = interim.loc[:last_full_hour, "Actual Load"].resample("h").mean().dropna()
    acf = calculate_lag_autocorrelation(acf_series, n_lags=200)
    conf = 1.96 / np.sqrt(len(acf_series))
    significant = acf[acf["partial_autocorrelation_abs"] > conf]
    key_lags = sorted(significant.nlargest(8, "partial_autocorrelation_abs")["lag"].astype(int))
    if not key_lags:  # degenerate fallback (very short series)
        key_lags = list(LAG_FALLBACK)
    logger.info("PACF key_lags (top %d by |PACF|): %s  [N=%d, band=+/-%.4f]",
                len(key_lags), key_lags, len(acf_series), conf)
    if figdir is not None:
        _try(lambda: _plot_acf(acf, key_lags, conf, figdir), "acf")
    return key_lags


# --- config + pipeline --------------------------------------------------------
def build_config(key_lags, cov: Coverage, *, n_jobs, n_trials, n_initial, train_years):
    """qmd ``team4-config`` (lines 591-641)."""
    from spotforecast2_safe.data import Period
    from spotforecast2_safe.configurator.config_entsoe import ConfigEntsoe
    from spotforecast2.tasks.task_entsoe import (
        entsoe_data_loader,
        entsoe_test_data_loader,
        entsoe_lgbm_factory,
    )

    periods = [
        Period(name="daily",     n_periods=12, column="hour",      input_range=(1, 24)),
        Period(name="weekly",    n_periods=7,  column="dayofweek", input_range=(0, 6)),
        Period(name="monthly",   n_periods=12, column="month",     input_range=(1, 12)),
        Period(name="quarterly", n_periods=4,  column="quarter",   input_range=(1, 4)),
        Period(name="yearly",    n_periods=12, column="dayofyear", input_range=(1, 365)),
    ]
    cfg = ConfigEntsoe(
        country_code=COUNTRY,
        data_filename="interim/energy_load.csv",
        targets=["Actual Load"],
        agg_weights=[1.0],
        bounds=None,
        data_loader=entsoe_data_loader,
        test_data_loader=entsoe_test_data_loader,
        forecaster_factory=entsoe_lgbm_factory,
        periods=periods,
        lags_consider=key_lags,
        train_size=pd.Timedelta(days=365 * train_years),
        end_train_default=cov.last_full_hour.isoformat(),
        delta_val=pd.Timedelta(hours=PREDICT_SIZE * REFIT_SIZE * NUMBER_FOLDS),
        predict_size=cov.live_n_steps,
        cv_block_size=PREDICT_SIZE,
        refit_size=REFIT_SIZE,
        number_folds=NUMBER_FOLDS,
        imputation_window_size=IMPUTATION_WINDOW_SIZE,
        n_trials_optuna=N_TRIALS_OPTUNA,
        n_trials_spotoptim=n_trials,
        n_initial_spotoptim=n_initial,
        n_jobs_spotoptim=n_jobs,
        warm_start_lags=True,
        include_weather_windows=True,
        include_holiday_features=True,
        poly_features_degree=2,
        max_poly_features=10,
        state="NW",
        random_state=42,
        on_weather_failure="skip",
    )
    cfg.data_frame_name = "bart26k-live-team4"
    logger.info("config ready: predict_size=%s n_trials_spotoptim=%s n_jobs=%s "
                "number_folds=%s", cfg.predict_size, cfg.n_trials_spotoptim,
                cfg.n_jobs_spotoptim, cfg.number_folds)
    return cfg


def run_pipeline(cfg):
    """qmd ``team4-prepare``...``team4-train`` (lines 1139-1697), figures dropped."""
    from spotforecast2.multitask import MultiTask

    mt = MultiTask(cfg, task="spotoptim")
    logger.info("prepare_data() ...")
    mt.prepare_data()

    # Outlier bounds from the load history (qmd team4-outlier-bounds, lines 1216-1223).
    s = mt.df_pipeline["Actual Load"].dropna()
    med = s.median()
    iqr = s.quantile(0.75) - s.quantile(0.25)
    low = max(0.0, med - OUTLIER_IQR_K * iqr)
    high = med + OUTLIER_IQR_K * iqr
    mt.config.bounds = [(low, high)]
    logger.info("outlier bounds (K=%d): [%.0f, %.0f] MW  (median=%.0f, IQR=%.0f)",
                OUTLIER_IQR_K, low, high, med, iqr)

    mt.detect_outliers()
    mt.impute()
    nan_after = int(mt.df_pipeline["Actual Load"].isna().sum())
    if nan_after != 0:
        raise Abort(1, f"imputation left {nan_after} NaN in Actual Load (must be 0)")
    logger.info("imputation OK (0 NaN remaining)")

    mt.build_exogenous_features()

    logger.info("starting SpotOptim search (n_trials=%s, n_jobs=%s) -- the slow "
                "step (~5-10 min on a laptop) ...", cfg.n_trials_spotoptim,
                cfg.n_jobs_spotoptim)
    t0 = time.monotonic()
    mt.run(show=False)
    logger.info("SpotOptim done in %.1f s", time.monotonic() - t0)
    return mt


def extract_y0(mt, dates: Dates) -> pd.Series:
    """qmd (lines 1699-1705)."""
    future = mt.results["spotoptim"]["Actual Load"]["future_pred"]
    if future.index.tz is None:
        future.index = future.index.tz_localize("UTC")
    else:
        future.index = future.index.tz_convert("UTC")

    logger.info("raw forecast: %d steps  %s -> %s",
                len(future), future.index.min(), future.index.max())
    y0 = future.loc[dates.tomorrow:dates.last_target]
    logger.info("y_0 slice: %d steps  %s -> %s", len(y0),
                y0.index.min() if len(y0) else None,
                y0.index.max() if len(y0) else None)
    return y0


def assert_no_leakage(mt) -> None:
    """qmd ``team4-load-model`` leakage guard (lines 1739-1746). Always runs
    (even with --no-figures): ENTSO-E's own forecast must never reach the model."""
    try:
        fc = mt.results["spotoptim"]["Actual Load"]["forecaster"]
        feat_names = list(fc.estimator.feature_name_)
    except Exception as exc:  # noqa: BLE001
        logger.warning("leakage guard skipped (cannot read fitted features): %s", exc)
        return
    leak = {"Forecasted Load", "Actual"}
    dwe = getattr(mt, "data_with_exog", None)
    exog_names = getattr(mt, "exog_feature_names", None)
    targets = {
        "training frame": set(dwe.columns) if dwe is not None else set(),
        "selected exogenous features": set(exog_names) if exog_names is not None else set(),
        "fitted model features": set(feat_names),
    }
    for where, cols in targets.items():
        if leak & cols:
            raise Abort(1, f"ENTSO-E forecast leaked into the {where} -- "
                           f"refusing to submit (CR-3 data-governance invariant).")
    logger.info("leakage guard passed: ENTSO-E forecast absent from target, "
                "exog, and model (%d features).", len(feat_names))


# --- diagnostic figures (best-effort; never block the submission) -------------
def family_of(col: str) -> str:
    """qmd helper (lines 1384-1396): map a feature name to its family."""
    c = col.lower()
    if "holiday" in c:
        return "holiday"
    if "poly" in c:
        return "polynomial"
    if "window" in c:
        return "weather_window"
    if any(k in c for k in ("sin", "cos", "rbf")):
        return "cyclical/RBF"
    if c.startswith("lag"):
        return "lag"
    return "weather/other"


def _try(fn, name: str) -> None:
    """Run a plot closure; log success/failure but never raise (CSV is critical)."""
    try:
        fn()
        logger.info("saved diagnostic: %s.png", name)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not save %s.png: %s", name, exc)


def _plot_acf(acf, key_lags, conf: float, figdir: Path) -> None:
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8.5, 3.0))
    ax.bar(acf["lag"], acf["autocorrelation"], width=0.9, color="#1F4E79")
    ax.axhline(conf, color="#999999", lw=0.8, ls="--")
    ax.axhline(-conf, color="#999999", lw=0.8, ls="--")
    for lag in key_lags:
        row = acf[acf["lag"] == lag]
        if not row.empty:
            val = float(row["autocorrelation"].iloc[0])
            ax.annotate(f"lag {lag}", xy=(lag, val), xytext=(lag, val + 0.08),
                        ha="center", fontsize=8, color="#E07B00",
                        arrowprops=dict(arrowstyle="->", color="#E07B00", lw=0.8))
    ax.set_xlabel("lag (hours)")
    ax.set_ylabel("autocorrelation")
    ax.set_title("ACF of Actual Load (annotated: data-selected key_lags)")
    ax.grid(True, color="#E5E5E5", linewidth=0.5)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(figdir / "acf.png", dpi=150)
    plt.close(fig)


def _plot_importance(fc, feat_names, figdir: Path) -> None:
    import matplotlib.pyplot as plt

    importances = fc.estimator.feature_importances_
    ranking = sorted(zip(feat_names, importances), key=lambda kv: kv[1], reverse=True)[:20]
    family_color = {
        "lag": "#B22222", "weather/other": "#E07B00", "weather_window": "#F0A33C",
        "cyclical/RBF": "#1F4E79", "holiday": "#2E8B57", "polynomial": "#7B5EA7",
    }
    labels = [n for n, _ in ranking][::-1]
    values = [v for _, v in ranking][::-1]
    colors = [family_color.get(family_of(n), "#888888") for n in labels]
    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    ax.barh(labels, values, color=colors)
    ax.set_xlabel("split count (feature importance)")
    ax.set_title("Top-20 feature importances (coloured by family; lags in red)")
    ax.grid(True, axis="x", color="#E5E5E5", linewidth=0.5)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in family_color.values()]
    ax.legend(handles, family_color.keys(), fontsize=7, loc="lower right")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(figdir / "feature_importance.png", dpi=150)
    plt.close(fig)


def _plot_shap(fc, X_tr, figdir: Path) -> None:
    import shap
    import matplotlib.pyplot as plt

    step = max(1, len(X_tr) // 2000)
    X_sample = X_tr.iloc[::step]
    explainer = shap.TreeExplainer(fc.estimator)
    sv = explainer.shap_values(X_sample)
    shap.summary_plot(sv, X_sample, plot_type="bar", show=False)
    fig = plt.gcf()
    fig.tight_layout()
    fig.savefig(figdir / "shap.png", dpi=150)
    plt.close(fig)


def _plot_forecast(mt, preds_entsoe, figdir: Path) -> None:
    from spotforecast2.plots.plotter import make_plot

    pkg = mt.results["spotoptim"]["Actual Load"]
    pkg["future_forecast"] = preds_entsoe.reindex(pkg["future_pred"].index)
    fig = make_plot(pkg)
    fig.write_image(str(figdir / "forecast.png"), scale=2)  # plotly + kaleido


def _plot_vs_entsoe(y0, preds_entsoe, figdir: Path) -> None:
    import matplotlib.pyplot as plt

    entsoe_fc = preds_entsoe.reindex(y0.index)
    overlap = entsoe_fc.dropna().index
    fig, ax = plt.subplots(figsize=(8.5, 3.5))
    ax.plot(y0.index, y0.values / 1000, marker="o", ms=3, color="#1F4E79",
            label="team_4 forecast (y_0)")
    if len(overlap) > 0:
        ax.plot(entsoe_fc.index, entsoe_fc.values / 1000, marker="x", ms=4,
                color="#E07B00", label="ENTSO-E day-ahead forecast")
        mad = float((y0.loc[overlap] - entsoe_fc.loc[overlap]).abs().mean())
        logger.info("mean |team_4 - ENTSO-E| over %d overlap hours: %.0f MW",
                    len(overlap), mad)
    else:
        logger.info("ENTSO-E day-ahead forecast not yet published for the target "
                    "day; plotting team_4 only.")
    ax.set_xlabel("Time (UTC)")
    ax.set_ylabel("Load [GW]")
    ax.set_title("team_4 vs. ENTSO-E day-ahead forecast -- target day")
    ax.grid(True, color="#E5E5E5", linewidth=0.5)
    ax.legend(fontsize=8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(figdir / "team4_vs_entsoe.png", dpi=150)
    plt.close(fig)


def save_diagnostics(mt, y0, preds_entsoe, figdir: Path) -> None:
    """qmd figures fig-team4-importance / -shap / -predict / -vs-entsoe."""
    figdir.mkdir(parents=True, exist_ok=True)
    fc = mt.results["spotoptim"]["Actual Load"]["forecaster"]

    X_tr = feat_names = None
    try:
        X_tr, _ = fc.create_train_X_y(
            y=mt.data_with_exog["Actual Load"],
            exog=mt.data_with_exog[mt.exog_feature_names],
        )
        feat_names = list(fc.estimator.feature_name_)
    except Exception as exc:  # noqa: BLE001
        logger.warning("design-matrix reconstruction failed; skipping "
                       "importance/SHAP: %s", exc)

    if feat_names is not None:
        _try(lambda: _plot_importance(fc, feat_names, figdir), "feature_importance")
    if X_tr is not None:
        _try(lambda: _plot_shap(fc, X_tr, figdir), "shap")
    _try(lambda: _plot_forecast(mt, preds_entsoe, figdir), "forecast")
    _try(lambda: _plot_vs_entsoe(y0, preds_entsoe, figdir), "team4_vs_entsoe")


# --- submission write + validate + push ---------------------------------------
def assert_contract(y0: pd.Series, dates: Dates) -> None:
    """qmd ``team4-submission-write`` contract (lines 1919-1924)."""
    assert len(y0) == 24, f"expected 24 hourly steps for y_0, got {len(y0)}"
    assert y0.index.min() == dates.tomorrow, (
        f"first step {y0.index.min()} != TOMORROW {dates.tomorrow}")
    assert (y0 > 0).all(), "non-positive forecast value -- spec requires > 0"
    assert y0.notna().all(), "NaN in forecast -- spec forbids"


def write_submission(y0: pd.Series, dates: Dates, repo_root: Path) -> Path:
    """Write submission CSV to prognosen/YYYY-MM-DD/HHmm-forecast.csv (local repo)."""
    date = dates.tomorrow.date()
    now = dates.now
    sub_dir = repo_root / "prognosen" / date.isoformat()
    sub_dir.mkdir(parents=True, exist_ok=True)
    path = sub_dir / f"{now.strftime('%H%M')}-forecast.csv"
    idx = y0.index
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    else:
        idx = idx.tz_convert("UTC")
    df = pd.DataFrame({
        "timestamp_utc": idx.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "forecast_mw": y0.round(2).values,
    })
    df.to_csv(path, index=False)
    logger.info("wrote %s  (%d rows, %.1f-%.1f MW)",
                path, len(df), df.forecast_mw.min(), df.forecast_mw.max())
    return path


def validate_submission(path: Path, lb_root: Path) -> int:
    """qmd ``team4-validate`` (lines 1947-1962): run the leaderboard's validator."""
    rel = path.relative_to(lb_root)
    cmd = ["uv", "run", "python", "scripts/validate_submission.py",
           "--path", str(rel), "--skip-deadline"]
    logger.info("validating: %s  (cwd=%s)", " ".join(cmd), lb_root)
    res = subprocess.run(cmd, cwd=lb_root, capture_output=True, text=True)
    if res.stdout.strip():
        logger.info("validator stdout: %s", res.stdout.strip())
    if res.stderr.strip():
        logger.warning("validator stderr: %s", res.stderr.strip())
    logger.info("validator exit code: %d", res.returncode)
    return res.returncode


def _push_steps_local(path: Path, repo_root: Path, dates: Dates):
    """Push to local repo (syntaxerror-prognose), not challenge-leaderboard."""
    date = dates.tomorrow.date()
    branch = f"forecast/{date}-{dates.now.strftime('%H%M%S')}"
    rel = path.relative_to(repo_root)
    title = f"forecast: {date}"
    return branch, date.isoformat(), [
        ["git", "switch", "-c", branch, "main"],
        ["git", "add", str(rel)],
        ["git", "commit", "-m", title],
        ["git", "push", "-u", "origin", branch],
    ]


def push_submission(path: Path, repo_root: Path, dates: Dates) -> int:
    """Commit and push CSV to local repo."""
    branch, target, steps = _push_steps_local(path, repo_root, dates)
    for cmd in steps:
        logger.info("$ %s", " ".join(cmd))
        res = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True)
        if res.stdout.strip():
            logger.info("%s", res.stdout.strip())
        if res.returncode != 0:
            logger.error("push step failed: %s\n%s", " ".join(cmd), res.stderr.strip())
            return res.returncode
    logger.info("forecast pushed for %s on branch %s", target, branch)
    return 0


def print_push_instructions(path: Path, repo_root: Path, dates: Dates) -> None:
    _, target, steps = _push_steps_local(path, repo_root, dates)
    logger.info("CSV written but NOT pushed. To submit, run (or pass --push):")
    logger.info("  cd %s", repo_root)
    for cmd in steps:
        logger.info("  %s", " ".join(cmd))


def _figures_dir(args: argparse.Namespace, dates: Dates) -> Path:
    if args.figures_dir:
        figdir = Path(args.figures_dir).expanduser()
    else:
        figdir = (Path.home() / "spotforecast2_data" / DATA_SUBDIR / "figures"
                  / dates.tomorrow.date().isoformat())
    figdir.mkdir(parents=True, exist_ok=True)
    logger.info("diagnostics -> %s", figdir)
    return figdir


def _log_banner(dates: Dates, args: argparse.Namespace, lb_root: Path) -> None:
    logger.info("=" * 72)
    logger.info("team4_submit -- standalone chapter-14 pipeline")
    logger.info("now=%s  today=%s  tomorrow(target)=%s",
                dates.now, dates.today.date(), dates.tomorrow.date())
    logger.info("download window: %s -> %s", dates.start_dl, dates.end_dl)
    logger.info("data_home=%s", os.environ.get("SPOTFORECAST2_DATA"))
    logger.info("cache_home=%s", os.environ.get("SPOTFORECAST2_CACHE"))
    logger.info("team=%s  leaderboard=%s", args.team_id, lb_root)
    logger.info("tuning: n_trials=%s n_initial=%s n_jobs=%s%s",
                args.n_trials, args.n_initial, args.n_jobs,
                " (deterministic -> serial)" if args.deterministic else "")
    logger.info("=" * 72)


# --- orchestration ------------------------------------------------------------
def _run(args: argparse.Namespace) -> int:
    configure_environment()
    repo_root = Path.cwd()
    lb_root = Path(args.leaderboard_root).expanduser()

    now = pd.Timestamp.now(tz="UTC")
    dates = compute_dates(now, args.data_end)
    _log_banner(dates, args, lb_root)

    # ---- download / cache decision ----
    api_key = os.environ.get("ENTSOE_API_KEY")
    used_cache = False
    if args.skip_download:
        logger.warning(">> --skip-download set: reusing cached interim, NO live "
                       "ENTSO-E call.")
        used_cache = True
    elif not api_key:
        if args.allow_stale:
            logger.error(">> ENTSOE_API_KEY missing and --allow-stale set: "
                         "falling back to cached interim.")
            used_cache = True
        else:
            raise Abort(3, "ENTSOE_API_KEY is not set. Export it, or pass "
                           "--skip-download / --allow-stale to use cached data.")
    else:
        if not robust_download(api_key, dates, max_retries=args.max_retries,
                               backoff=args.backoff):
            if args.allow_stale:
                logger.error("=" * 72)
                logger.error("ENTSO-E DOWNLOAD FAILED -- --allow-stale set: reusing "
                             "cached interim data.")
                logger.error("The submission will be built from possibly-stale "
                             "cached actuals (gated by the yesterday-23:00 check).")
                logger.error("=" * 72)
                used_cache = True
            else:
                raise Abort(2, "ENTSO-E download failed and --allow-stale not set; "
                               "aborting (no stale submission).")

    interim = load_interim()
    cov = assert_coverage(interim, dates, fallback=used_cache)
    preds_entsoe = entsoe_predictions(interim)

    figdir = None if args.no_figures else _figures_dir(args, dates)
    key_lags = select_key_lags(interim, cov.last_full_hour, figdir)

    n_jobs = None if (args.deterministic or args.n_jobs == 0) else args.n_jobs
    cfg = build_config(key_lags, cov, n_jobs=n_jobs, n_trials=args.n_trials,
                       n_initial=args.n_initial, train_years=args.train_years)
    mt = run_pipeline(cfg)
    y0 = extract_y0(mt, dates)

    assert_no_leakage(mt)
    if figdir is not None:
        save_diagnostics(mt, y0, preds_entsoe, figdir)

    assert_contract(y0, dates)
    path = write_submission(y0, dates, repo_root)

    code = 0
    if not args.no_validate:
        if validate_submission(path, lb_root) != 0:
            logger.error("validator rejected the submission.")
            code = 4

    if args.push:
        if code != 0:
            logger.error("skipping --push because validation failed.")
        elif push_submission(path, repo_root, dates) != 0:
            logger.error("push failed.")
            code = code or 1
    else:
        print_push_instructions(path, repo_root, dates)

    if code == 0:
        logger.info("DONE: forecast for %s written%s.",
                    dates.tomorrow.date().isoformat(),
                    " and validated" if not args.no_validate else "")
    return code


def main(argv=None) -> int:
    args = parse_args(argv)
    setup_logging(args.verbose)
    try:
        return _run(args)
    except Abort as abort:
        logger.error("%s", abort)
        return abort.code
    except Exception:  # noqa: BLE001
        logger.exception("unexpected failure")
        return 1


if __name__ == "__main__":
    sys.exit(main())
