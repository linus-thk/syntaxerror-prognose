#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Team Syntaxerror
"""Experimental LightGBM+XGBoost ensemble variant with a CONFIGURABLE blend
weight -- submitted as ``syntaxerror_ensemble_test``, never as ``syntaxerror``.

PROVENANCE / WHY THIS EXISTS -- ``syntaxerror_submit.py`` already ships an
LGBM+XGBoost ensemble (``team4_ensemble_factory``, gated by
``USE_XGBOOST_ENSEMBLE``), but it averages the two models with FIXED EQUAL
weights (``VotingRegressor([("lgbm", lgbm), ("xgb", xgb)])`` -> weights=None
-> plain mean). ``data/backtest/xgb_comparison.md`` found that equal-weight
ensemble beats single-LightGBM on all 3 backtested days (n=3, small sample).
This script asks the next question: is equal-weight optimal, or does shifting
the blend towards whichever model is locally more accurate do better? It
exposes the blend as one CLI knob (``--lgbm-weight``) instead of hardcoding
0.5, so that knob can later be set from real backtest error numbers.

WHY A SEPARATE SCRIPT, NOT A FLAG ON ``syntaxerror_spotoptim_submit.py`` --
that script is the deliberately-stock SINGLE-LightGBM baseline (see its
module docstring); bolting ensemble logic onto it would conflate two
different experiments. This file instead reuses the *operational* machinery
from ``syntaxerror_submit.py`` (download retry, date/coverage guards, leakage
guard, shape check, submission write/validate/push) the same way
``syntaxerror_spotoptim_submit.py`` does, and reuses ``team4_ensemble_factory``'s
proven hyperparameters/search space from ``syntaxerror_submit.py`` directly
-- the only new code is the weighted variant of the factory.

WEIGHT FORMULA -- inverse-error (Bates-Granger) combination, the standard
approach for combining diverse forecasts: given backtest errors e_lgbm,
e_xgb (e.g. MAE over comparable days from ``scripts/backtest_submissions.py``),

    w_lgbm = (1 / e_lgbm) / (1 / e_lgbm + 1 / e_xgb)
    w_xgb  = 1 - w_lgbm

A model with HALF the error of the other gets WEIGHTED TWICE as heavily.
Equal errors -> w_lgbm = 0.5 (identical to today's ``team4_ensemble_factory``
default). This script does not compute e_lgbm/e_xgb itself -- no backtest has
been run yet (deferred per explicit request) -- it only accepts the
resulting weight via ``--lgbm-weight`` so the formula can be applied by hand
once backtest numbers exist. ``--lgbm-weight 0.5`` (the default) reproduces
today's production ensemble's averaging behaviour exactly.

KNOWN HAZARD (carried over from ``team4_ensemble_factory``, see
``data/backtest/xgb_comparison.md``) -- running the VotingRegressor ensemble
under SpotOptim's parallel (fork-based) CV crashes reproducibly on macOS
(``RuntimeError: All initial design evaluations failed``, traced to an
OpenMP/pthread conflict). ``--n-jobs`` therefore defaults to ``0`` (serial)
here, unlike the ``-1`` default in the other two scripts -- override only on
a platform/setup known not to hit this.

NO TEAM-ID COLLISION -- unlike ``syntaxerror_spotoptim_submit.py`` (which
deliberately collides with ``syntaxerror_submit.py``'s output path),
``--team-id`` here defaults to ``syntaxerror_ensemble_test`` so an
experimental run can never silently overwrite a real submission.

NOT YET BACKTESTED -- this script has not itself been run through
``scripts/backtest_submissions.py``; that is explicitly a follow-up.

REPRODUCING A PAST DAY (re-running this later and getting SIMILAR numbers)
-- two independent things have to both hold; getting only one right is not
enough:

1. SAME INPUT DATA: pass ``--as-of <ISO-UTC timestamp from that day>``
   together with ``--skip-download`` (or a raw ENTSO-E snapshot CSV that
   matches that day, see ``data/backtest/xgb_comparison.md``'s methodology).
   Without ``--as-of``, "now" is wall-clock time and the training window
   shifts every run. This script includes no live weather/holiday exogenous
   features (deliberately, stock-style, see above), so unlike
   ``syntaxerror_submit.py`` there is no Open-Meteo live-fetch drift to
   worry about here.

2. SAME SEARCH BEHAVIOUR: SpotOptim's own search is seeded
   (``seed=cfg.random_state=42``) but the seed only produces a reproducible
   result when SpotOptim runs SEQUENTIALLY (``n_jobs == 1`` inside the
   ``spotoptim`` package, confirmed in ``spotoptim/SpotOptim.py`` --
   ``n_jobs > 1`` dispatches to ``optimize_steady_state``, an asynchronous
   parallel search whose outcome depends on worker completion timing and is
   NOT seed-reproducible even with a fixed seed). ``cfg.n_jobs_spotoptim``
   maps 1:1 onto that SpotOptim-internal ``n_jobs``. This script's default
   ``--n-jobs 0`` resolves to ``cfg.n_jobs_spotoptim=None``, which makes
   SpotOptim fall back to ITS OWN default of ``n_jobs=1`` -- i.e. already
   sequential and seed-reproducible, which is also why it dodges the macOS
   crash above. Pass ``--deterministic`` for the same effect spelled out
   explicitly (e.g. if you ever change the ``--n-jobs`` default). Avoid
   ``--n-jobs -1``/any value other than ``0``/``1`` for replay runs.

   LGBM (``num_threads=1``) and XGBoost (``n_jobs=1``) sub-estimators are
   single-threaded with fixed ``random_state=42`` regardless of this
   setting, so they do not add further variance on top of the SpotOptim
   search itself.

Residual, smaller risk: dependency version drift (numpy/lightgbm/xgboost/
sklearn upgrades between runs) can still shift results slightly even with
an identical seed -- fine for "similar", not for bit-exact reproduction;
see MODEL_CARD.md on the bit-exact-reproducibility goal of the pinned
environment ``syntaxerror_submit.py`` relies on.

Usage:

    export ENTSOE_API_KEY=...
    uv run python syntaxerror_ensemble_test.py --skip-download --no-validate --no-figures
    uv run python syntaxerror_ensemble_test.py --lgbm-weight 0.65 --skip-download
    uv run python syntaxerror_ensemble_test.py --help
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from functools import partial
from pathlib import Path

# Headless backend MUST be selected before anything (incl. shap) imports pyplot.
import matplotlib

matplotlib.use("Agg")

import pandas as pd

import syntaxerror_submit as se  # reuse the proven operational pipeline + ensemble search space

# --- weighted LGBM+XGBoost ensemble variant constants --------------------------
COUNTRY = se.COUNTRY
DEFAULT_TEAM_ID = "syntaxerror_ensemble_test"  # deliberately non-colliding, see module docstring
TRAIN_YEARS = 3
PREDICT_SIZE = 24
REFIT_SIZE = 7
NUMBER_FOLDS = 10
# Matches the data/backtest/xgb_comparison.md methodology (reduced trial
# budget for fast iteration while this is still an experiment).
N_TRIALS_SPOTOPTIM = 10
N_INITIAL_SPOTOPTIM = 5
LAGS_CONSIDER = [1, 2, 24]                # fixed, no PACF lag selection (stock-style, see spotoptim variant)
DEFAULT_LGBM_WEIGHT = 0.8                  # 0.5 = equal weight = today's team4_ensemble_factory behaviour

logger = logging.getLogger("syntaxerror_ensemble_test")


# --- CLI + logging --------------------------------------------------------------
def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="syntaxerror_ensemble_test",
        description="Experimental LightGBM+XGBoost VotingRegressor ensemble "
                    "with a configurable blend weight (vs. the fixed "
                    "equal-weight ensemble in syntaxerror_submit.py).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--team-id", default=DEFAULT_TEAM_ID,
                   help="registry check + submission directory (defaults to "
                        "a non-colliding test id, see module docstring)")
    p.add_argument("--skip-download", action="store_true",
                   help="reuse the cached interim CSV; no ENTSO-E API call")
    p.add_argument("--max-retries", type=int, default=5)
    p.add_argument("--timeout", type=float, default=60.0)
    p.add_argument("--backoff", type=float, default=5.0)
    p.add_argument("--allow-stale", action="store_true",
                   help="permit cache fallback when the API is down "
                        "(still gated by the D-1 23:00 freshness check)")
    p.add_argument("--data-end", default=None)
    p.add_argument("--as-of", default=None, metavar="ISO-UTC",
                   help="freeze 'now' for a historical replay (see "
                        "data/backtest/xgb_comparison.md for the methodology)")
    p.add_argument("--no-validate", action="store_true")
    p.add_argument("--push", action="store_true",
                   help="branch + commit + open the auto-merging PR via gh")
    p.add_argument("--n-jobs", type=int, default=0,
                   help="n_jobs_spotoptim (-1 = all cores; 0 = serial). "
                        "Defaults to serial: parallel VotingRegressor CV "
                        "crashes reproducibly on macOS, see module docstring")
    p.add_argument("--deterministic", action="store_true",
                   help="force serial SpotOptim (n_jobs=None) for bit-reproducible runs")
    p.add_argument("--n-trials", type=int, default=N_TRIALS_SPOTOPTIM)
    p.add_argument("--n-initial", type=int, default=N_INITIAL_SPOTOPTIM)
    p.add_argument("--train-years", type=int, default=TRAIN_YEARS)
    p.add_argument("--lgbm-weight", type=float, default=DEFAULT_LGBM_WEIGHT,
                   help="VotingRegressor weight for the LightGBM sub-model in "
                        "[0, 1]; XGBoost gets (1 - this). 0.5 = equal weight. "
                        "Set from backtest errors via w_lgbm = (1/mae_lgbm) / "
                        "(1/mae_lgbm + 1/mae_xgb), see module docstring")
    p.add_argument("--figures-dir", default=None)
    p.add_argument("--no-figures", action="store_true")
    p.add_argument("--leaderboard-root", default=str(se.PACKAGE_ROOT),
                   help="bundles teams.yml + scripts/validate_submission.py "
                        "(packaged-copy divergence, see syntaxerror_submit.py)")
    p.add_argument("-v", "--verbose", action="count", default=0)
    args = p.parse_args(argv)
    if not 0.0 <= args.lgbm_weight <= 1.0:
        p.error(f"--lgbm-weight must be in [0, 1], got {args.lgbm_weight}")
    return args


def setup_logging(verbosity: int) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [syntaxerror_ensemble_test] %(levelname)s %(message)s", "%H:%M:%S"))
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if verbosity >= 2 else logging.INFO)
    logger.propagate = False
    if verbosity >= 1:
        logging.getLogger("spotforecast2_safe.downloader.entsoe").setLevel(logging.INFO)
    if verbosity >= 2:
        for name in ("spotforecast2", "spotforecast2_safe"):
            logging.getLogger(name).setLevel(logging.DEBUG)


# --- the only genuinely new code: a weighted ensemble factory ------------------
def weighted_ensemble_factory(config, *, lgbm_weight: float, weight_func=None, target=None):
    """Same LightGBM+XGBoost VotingRegressor as ``se.team4_ensemble_factory``
    (identical sub-estimator hyperparameters, for apples-to-apples
    comparability), except the blend is ``[lgbm_weight, 1 - lgbm_weight]``
    instead of hardcoded equal weights.
    """
    from lightgbm import LGBMRegressor
    from xgboost import XGBRegressor
    from sklearn.ensemble import VotingRegressor
    from spotforecast2_safe.forecaster.recursive import ForecasterRecursive
    from spotforecast2_safe.preprocessing import RollingFeatures

    del target
    # num_threads=1 / n_jobs=1: see se.team4_ensemble_factory -- joblib
    # parallelises CV folds at the outer level (fork); letting LightGBM/
    # XGBoost spawn their own OpenMP threads inside forked workers causes
    # pthread_mutex_init failures and SIGSEGV on macOS (OMP Error #179).
    lgbm = LGBMRegressor(random_state=config.random_state, verbose=-1, num_threads=1)
    xgb = XGBRegressor(
        random_state=config.random_state,
        verbosity=0,
        tree_method="hist",
        n_estimators=1000,
        learning_rate=0.05,
        max_depth=6,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.1,
        reg_lambda=1.0,
        min_child_weight=5,
        n_jobs=1,
    )
    ensemble = VotingRegressor(
        [("lgbm", lgbm), ("xgb", xgb)],
        weights=[lgbm_weight, 1.0 - lgbm_weight],
    )
    # weight_func is not forwarded: VotingRegressor.fit() has no sample_weight
    # parameter and raises IgnoredArgumentWarning when one is passed.
    return ForecasterRecursive(
        estimator=ensemble,
        lags=config.lags_consider[-1],
        window_features=[
            RollingFeatures(stats="mean", window_sizes=config.window_size),
            RollingFeatures(stats="mean", window_sizes=24 * 7),
            RollingFeatures(stats="mean", window_sizes=24 * 30),
        ],
        weight_func=None,
    )


# --- config + pipeline ----------------------------------------------------------
def build_config(cov: "se.Coverage", *, n_trials: int, n_initial: int,
                 train_years: int, n_jobs, lgbm_weight: float):
    """Stock-style config (single daily Period, fixed lags, no PACF, no
    weather/holiday exogenous features) -- only the forecaster_factory
    differs from the spotoptim variant: weighted LGBM+XGBoost ensemble
    instead of a single LightGBM.
    """
    from spotforecast2_safe.data import Period
    from spotforecast2_safe.configurator.config_entsoe import ConfigEntsoe
    from spotforecast2.tasks.task_entsoe import (
        entsoe_data_loader,
        entsoe_test_data_loader,
    )

    cfg = ConfigEntsoe(
        country_code=COUNTRY,
        data_filename="interim/energy_load.csv",
        targets=["Actual Load"],
        agg_weights=[1.0],
        bounds=[(-1e9, 1e9)],            # essentially unbounded -- no real outlier clipping
        data_loader=entsoe_data_loader,
        test_data_loader=entsoe_test_data_loader,
        forecaster_factory=partial(weighted_ensemble_factory, lgbm_weight=lgbm_weight),
        periods=[Period(name="daily", n_periods=12, column="hour", input_range=(1, 24))],
        lags_consider=list(LAGS_CONSIDER),
        train_size=pd.Timedelta(days=365 * train_years),
        end_train_default=cov.last_full_hour.isoformat(),
        delta_val=pd.Timedelta(hours=PREDICT_SIZE * REFIT_SIZE * NUMBER_FOLDS),
        predict_size=cov.live_n_steps,
        cv_block_size=PREDICT_SIZE,
        refit_size=REFIT_SIZE,
        number_folds=NUMBER_FOLDS,
        n_trials_spotoptim=n_trials,
        n_initial_spotoptim=n_initial,
        n_jobs_spotoptim=n_jobs,
        random_state=42,
        on_weather_failure="skip",
        on_exog_provider_failure="skip",
        # Target-side QC: reuse the same thresholds/policy as syntaxerror_submit.py
        # so a corrupt frontier hour is handled identically.
        target_qc_range_mw=se.MAX_INTRAHOUR_RANGE_MW,
        target_qc_step_mw=se.MAX_ADJ_STEP_MW,
        target_qc_window_days=se.QC_WINDOW_DAYS,
        target_corruption_policy=se.TARGET_CORRUPTION_POLICY,
        target_max_heal_hours=se.TARGET_MAX_HEAL_HOURS,
        target_anchor_zone_hours=se.TARGET_ANCHOR_ZONE_HOURS,
        target_qc_deviation_mw=se.MAX_DEVIATION_MW,
        target_qc_deviation_ref=se.DEVIATION_REF,
        target_qc_deviation_slots=se.DEVIATION_SLOTS,
    )
    # Isolate the model cache from both syntaxerror_submit.py's ensemble cache
    # and syntaxerror_spotoptim_submit.py's cache, so none of the three runs
    # overwrite each other's tuned models / cached joblib files.
    cfg.data_frame_name = "bart26k-live-syntaxerror-ensemble-test"
    logger.info("config ready: predict_size=%s n_trials_spotoptim=%s n_jobs=%s "
                "number_folds=%s lgbm_weight=%.3f", cfg.predict_size,
                cfg.n_trials_spotoptim, cfg.n_jobs_spotoptim, cfg.number_folds,
                lgbm_weight)
    return cfg


def run_pipeline(cfg):
    """Stock MultiTask pipeline (mirrors the spotoptim variant), except the
    ensemble's nested VotingRegressor params (``estimator__lgbm__*``) need a
    custom search space -- ``mt.run()``'s generic dispatcher does not forward
    one, so this calls ``run_task_spotoptim`` directly (same reason
    syntaxerror_submit.py does, see its ``team4-train`` comment).
    """
    from spotforecast2.multitask import MultiTask

    mt = MultiTask(cfg, task="spotoptim")
    logger.info("prepare_data() ...")
    mt.prepare_data()
    mt.detect_outliers()
    mt.impute()
    nan_after = int(mt.df_pipeline["Actual Load"].isna().sum())
    if nan_after != 0:
        raise se.Abort(1, f"imputation left {nan_after} NaN in Actual Load (must be 0)")
    logger.info("imputation OK (0 NaN remaining)")

    mt.build_exogenous_features()

    search_space = se.build_ensemble_search_space(LAGS_CONSIDER)
    logger.info("starting SpotOptim search (n_trials=%s, n_jobs=%s) ...",
                cfg.n_trials_spotoptim, cfg.n_jobs_spotoptim)
    t0 = time.monotonic()
    mt.run_task_spotoptim(search_space=search_space, show=False)
    logger.info("SpotOptim done in %.1f s", time.monotonic() - t0)
    return mt


# --- orchestration ---------------------------------------------------------------
def _run(args: argparse.Namespace) -> int:
    se.configure_environment()
    lb_root = Path(args.leaderboard_root).expanduser()
    # Registry check intentionally skipped, matching syntaxerror_submit.py /
    # syntaxerror_spotoptim_submit.py: the bundled local teams.yml doesn't
    # list "syntaxerror"-derived ids.
    # se.check_team_registry(args.team_id, lb_root)

    if args.as_of:
        try:
            now = pd.to_datetime(args.as_of, utc=True)
        except Exception as exc:  # noqa: BLE001
            raise se.Abort(1, f"--as-of {args.as_of!r} is not an ISO-8601 UTC "
                              f"timestamp: {exc}")
        logger.warning(">> --as-of set: 'now' frozen to %s (historical replay)", now)
    else:
        now = pd.Timestamp.now(tz="UTC")
    dates = se.compute_dates(now, args.data_end)

    logger.info("=" * 72)
    logger.info("syntaxerror_ensemble_test -- weighted LightGBM+XGBoost ensemble variant")
    logger.info("now=%s  today=%s  tomorrow(target)=%s",
                dates.now, dates.today.date(), dates.tomorrow.date())
    logger.info("team=%s  leaderboard=%s", args.team_id, lb_root)
    logger.info("tuning: n_trials=%s n_initial=%s n_jobs=%s", args.n_trials,
                args.n_initial, args.n_jobs)
    logger.info("ensemble blend: lgbm_weight=%.3f  xgb_weight=%.3f",
                args.lgbm_weight, 1.0 - args.lgbm_weight)
    logger.info("=" * 72)

    api_key = se.os.environ.get("ENTSOE_API_KEY")
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
            raise se.Abort(3, "ENTSOE_API_KEY is not set. Export it, or pass "
                              "--skip-download / --allow-stale to use cached data.")
    else:
        timeout = args.timeout if args.timeout > 0 else None
        if not se.robust_download(api_key, dates, max_retries=args.max_retries,
                                  backoff=args.backoff, timeout=timeout):
            if args.allow_stale:
                used_cache = True
            else:
                raise se.Abort(2, "ENTSO-E download failed and --allow-stale not "
                                  "set; aborting (no stale submission).")
    if api_key and not args.skip_download:
        se.download_side_tables(api_key, dates,
                                timeout=args.timeout if args.timeout > 0 else None)

    interim = se.load_interim()
    cov = se.assert_coverage(interim, dates, fallback=used_cache)
    preds_entsoe = se.entsoe_predictions(interim)

    n_jobs = None if (args.deterministic or args.n_jobs == 0) else args.n_jobs
    if n_jobs in (None, 1):
        logger.info("SpotOptim search: sequential (n_jobs_spotoptim=%s) -> "
                    "seed-reproducible. Pair with --as-of + --skip-download "
                    "to replay a past day with similar values.", n_jobs)
    else:
        logger.warning("SpotOptim search: PARALLEL (n_jobs_spotoptim=%s) -> "
                       "spotoptim's steady-state async search is NOT "
                       "seed-reproducible (see module docstring); a replay "
                       "run will likely NOT reproduce similar values.", n_jobs)
    cfg = build_config(cov, n_trials=args.n_trials, n_initial=args.n_initial,
                       train_years=args.train_years, n_jobs=n_jobs,
                       lgbm_weight=args.lgbm_weight)
    mt = run_pipeline(cfg)
    y0 = se.extract_y0(mt, dates)
    se.warn_if_implausible_shape(y0, preds_entsoe, interim)
    se.assert_no_leakage(mt)

    if not args.no_figures:
        figdir = (args.figures_dir and Path(args.figures_dir).expanduser()) or (
            se.PACKAGE_ROOT / "data" / "figures_ensemble_test" / dates.tomorrow.date().isoformat())
        figdir.mkdir(parents=True, exist_ok=True)
        se.save_diagnostics(mt, y0, preds_entsoe, figdir)

    se.assert_contract(y0, dates)
    path = se.write_submission(y0, dates, args.team_id, lb_root)

    code = 0
    if not args.no_validate:
        if se.validate_submission(path, lb_root) != 0:
            logger.error("validator rejected the submission.")
            code = 4

    if args.push:
        if code != 0:
            logger.error("skipping --push because validation failed.")
        elif se.push_submission(path, dates, args.team_id, lb_root) != 0:
            logger.error("push failed.")
            code = code or 1
    else:
        se.print_push_instructions(path, dates, args.team_id, lb_root)

    if code == 0:
        logger.info("DONE: submission for %s written%s.",
                    dates.tomorrow.date().isoformat(),
                    " and validated" if not args.no_validate else "")
    return code


def main(argv=None) -> int:
    args = parse_args(argv)
    setup_logging(args.verbose)
    try:
        return _run(args)
    except se.Abort as abort:
        logger.error("%s", abort)
        return abort.code
    except Exception:  # noqa: BLE001
        logger.exception("unexpected failure")
        return 1


if __name__ == "__main__":
    sys.exit(main())
