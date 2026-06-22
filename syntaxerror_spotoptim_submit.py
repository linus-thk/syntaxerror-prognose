#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Team Syntaxerror
"""Stock single-LightGBM SpotOptim variant, submitted as ``syntaxerror``.

PROVENANCE -- this file started as a copy of a course script
(``bart26l-vorlesung/scripts/team4_spotoptim_submit.py``, the "team_4" stock
baseline) that targets a much newer, unpinned environment
(``spotforecast2-safe >= 22.10.0``; this package pins 18.1.0 -- see
``MODEL_CARD.md``) and an external ``challenge_leaderboard`` Python package
that is not a dependency here. It has since been rebranded onto this team's
identity: every ``team4``/``team_4`` reference was renamed to
``syntaxerror`` (including ``--team-id``'s default), per an explicit choice
to use the same team_id as ``syntaxerror_submit.py``.

IMPORTANT -- TEAM-ID COLLISION, BY DESIGN: this script writes to
``submissions/syntaxerror/<date>.csv``, the SAME path ``syntaxerror_submit.py``
writes to. Running both for the same target day means whichever runs last
wins; the simple single-LightGBM forecast from THIS script will silently
overwrite the ensemble forecast (or vice versa). This was a deliberate
choice (see conversation), not an oversight -- do not run both for the same
day unless you intend to replace one submission with the other. Use
``--team-id`` to override and write elsewhere if you want to compare them
side by side instead.

REWRITE STRATEGY -- rather than upgrading the pinned environment (would risk
the bit-exact reproducibility ``syntaxerror_submit.py`` documents in
MANIFEST.md/MODEL_CARD.md), this script imports the already-working
operational machinery from ``syntaxerror_submit.py`` (download retry,
date/coverage guards, leakage guard, shape check, submission write/validate/
push -- all proven against the installed 18.1.0 API) and only swaps in what
makes this a *different model*: a single stock LightGBM
(``default_lgbm_forecaster_factory``, available unchanged in 18.1.0), fixed
``lags_consider=[1, 2, 24]``, one daily ``Period`` only, no PACF lag
selection, no custom SpotOptim search space (``mt.run(show=False)`` -> the
package's ``_default_spotoptim_search_space``), and no weather/holiday/
ENTSO-E-provider exogenous features.

NO EXTRA DATA DOWNLOAD NEEDED -- the ``TRAIN_YEARS = 3`` window fits entirely
inside the already-cached ``data/interim/energy_load.csv`` (2022-01-01 ->
present, the same ENTSO-E history ``syntaxerror_submit.py`` downloads daily);
this script reuses that same cache/data home (``PACKAGE_ROOT/data``,
``PACKAGE_ROOT/.cache``) instead of the course script's separate
``~/spotforecast2_data/ddmo_ch13_live``. Weather is fetched live via
Open-Meteo on every run (same mechanism ``syntaxerror_submit.py`` already
uses) -- nothing to pre-download there.

Usage:

    export ENTSOE_API_KEY=...
    uv run python syntaxerror_spotoptim_submit.py --skip-download --no-validate --no-figures
    uv run python syntaxerror_spotoptim_submit.py --help
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

# Headless backend MUST be selected before anything (incl. shap) imports pyplot.
import matplotlib

matplotlib.use("Agg")

import pandas as pd

import syntaxerror_submit as se  # reuse the proven operational pipeline

# --- single-LightGBM SpotOptim variant constants (deliberately simple) --------
COUNTRY = se.COUNTRY
DEFAULT_TEAM_ID = "syntaxerror"          # NOTE: collides with syntaxerror_submit.py's
                                         #   output path -- see module docstring
TRAIN_YEARS = 3
PREDICT_SIZE = 24
REFIT_SIZE = 7
NUMBER_FOLDS = 10
N_TRIALS_SPOTOPTIM = 100                 # matched to the course Optuna baseline
N_INITIAL_SPOTOPTIM = 12
LAGS_CONSIDER = [1, 2, 24]                # fixed, no PACF lag selection

logger = logging.getLogger("syntaxerror_spotoptim_submit")


# --- CLI + logging --------------------------------------------------------------
def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="syntaxerror_spotoptim_submit",
        description="Stock single-LightGBM SpotOptim variant of the "
                    "syntaxerror submission (vs. the ensemble in "
                    "syntaxerror_submit.py).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--team-id", default=DEFAULT_TEAM_ID,
                   help="registry check + submission directory (default "
                        "collides with syntaxerror_submit.py's output -- "
                        "see module docstring)")
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
    p.add_argument("--n-jobs", type=int, default=-1)
    p.add_argument("--deterministic", action="store_true")
    p.add_argument("--n-trials", type=int, default=N_TRIALS_SPOTOPTIM)
    p.add_argument("--n-initial", type=int, default=N_INITIAL_SPOTOPTIM)
    p.add_argument("--train-years", type=int, default=TRAIN_YEARS)
    p.add_argument("--figures-dir", default=None)
    p.add_argument("--no-figures", action="store_true")
    p.add_argument("--leaderboard-root", default=str(se.PACKAGE_ROOT),
                   help="bundles teams.yml + scripts/validate_submission.py "
                        "(packaged-copy divergence, see syntaxerror_submit.py)")
    p.add_argument("-v", "--verbose", action="count", default=0)
    return p.parse_args(argv)


def setup_logging(verbosity: int) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [syntaxerror_spotoptim_submit] %(levelname)s %(message)s", "%H:%M:%S"))
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if verbosity >= 2 else logging.INFO)
    logger.propagate = False
    if verbosity >= 1:
        logging.getLogger("spotforecast2_safe.downloader.entsoe").setLevel(logging.INFO)
    if verbosity >= 2:
        for name in ("spotforecast2", "spotforecast2_safe"):
            logging.getLogger(name).setLevel(logging.DEBUG)


# --- config + pipeline (the only genuinely model-specific code) ---------------
def build_config(cov: "se.Coverage", *, n_trials: int, n_initial: int, train_years: int):
    """Stock variant: single LightGBM, fixed lags, one daily Period, no
    exogenous-feature flags, no custom SpotOptim search space."""
    from spotforecast2_safe.data import Period
    from spotforecast2_safe.configurator.config_entsoe import ConfigEntsoe
    from spotforecast2.tasks.task_entsoe import (
        entsoe_data_loader,
        entsoe_test_data_loader,
    )
    from spotforecast2_safe.multitask.factories import default_lgbm_forecaster_factory

    cfg = ConfigEntsoe(
        country_code=COUNTRY,
        data_filename="interim/energy_load.csv",
        targets=["Actual Load"],
        agg_weights=[1.0],
        bounds=[(-1e9, 1e9)],            # essentially unbounded -- no real outlier clipping
        data_loader=entsoe_data_loader,
        test_data_loader=entsoe_test_data_loader,
        forecaster_factory=default_lgbm_forecaster_factory,
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
        random_state=42,
        on_weather_failure="skip",
        # No include_weather_windows / include_holiday_* / include_entsoe_* /
        # warm_start_lags -- deliberately the package defaults (all False),
        # matching the stock variant's minimal feature set.
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
    # Isolate the model cache from syntaxerror_submit.py's own ensemble cache
    # ("bart26k-live-team4") so neither run overwrites the other's tuned models
    # -- even though both now submit under the same team_id (see module
    # docstring), the cached joblib/tuning-result files stay independent.
    cfg.data_frame_name = "bart26k-live-syntaxerror-spotoptim"
    logger.info("config ready: predict_size=%s n_trials_spotoptim=%s n_jobs=%s "
                "number_folds=%s", cfg.predict_size, cfg.n_trials_spotoptim,
                cfg.n_jobs_spotoptim, cfg.number_folds)
    return cfg


def run_pipeline(cfg):
    """Stock MultiTask pipeline: no PACF, no outlier-IQR bounds, no degree-day
    injection -- just prepare/detect/impute/build-exog/tune."""
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

    logger.info("starting SpotOptim search (n_trials=%s, n_jobs=%s) ...",
                cfg.n_trials_spotoptim, cfg.n_jobs_spotoptim)
    t0 = time.monotonic()
    # No custom search space -> mt.run() dispatches to run_task_spotoptim with
    # the package's _default_spotoptim_search_space (unlike syntaxerror_submit.py,
    # which needs run_task_spotoptim directly because it DOES pass a custom space).
    mt.run(task="spotoptim", show=False)
    logger.info("SpotOptim done in %.1f s", time.monotonic() - t0)
    return mt


# --- orchestration ---------------------------------------------------------------
def _run(args: argparse.Namespace) -> int:
    se.configure_environment()
    lb_root = Path(args.leaderboard_root).expanduser()
    # Registry check intentionally skipped, matching syntaxerror_submit.py:
    # the bundled local teams.yml only lists team_4/team_4_entsoe (the course's
    # own baseline ids), not "syntaxerror" -- the real registration lives in
    # the upstream bartzbeielstein/challenge-leaderboard teams.yml.
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
    logger.info("syntaxerror_spotoptim_submit -- stock single-LightGBM variant")
    logger.info("now=%s  today=%s  tomorrow(target)=%s",
                dates.now, dates.today.date(), dates.tomorrow.date())
    logger.info("team=%s  leaderboard=%s", args.team_id, lb_root)
    logger.info("tuning: n_trials=%s n_initial=%s n_jobs=%s", args.n_trials,
                args.n_initial, args.n_jobs)
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

    cfg = build_config(cov, n_trials=args.n_trials, n_initial=args.n_initial,
                       train_years=args.train_years)
    mt = run_pipeline(cfg)
    y0 = se.extract_y0(mt, dates)
    se.warn_if_implausible_shape(y0, preds_entsoe, interim)
    se.assert_no_leakage(mt)

    if not args.no_figures:
        figdir = (args.figures_dir and Path(args.figures_dir).expanduser()) or (
            se.PACKAGE_ROOT / "data" / "figures_spotoptim" / dates.tomorrow.date().isoformat())
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
