# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Team Syntaxerror
"""Post-hoc weight sweep: für jede LGBM-Gewichtung 0.0–1.0 den MAE berechnen,
ohne die Modelle neu zu trainieren.

Voraussetzung: scripts/se-weight-backtest-run.sh hat folgende Submissions erzeugt:
  submissions/backtest_lgbm_pure/<date>.csv  (lgbm-weight=1.0 aus ensemble_test)
  submissions/backtest_xgb_pure/<date>.csv   (lgbm-weight=0.0 aus ensemble_test)

Die Aktualwerte kommen aus dem neuesten ENTSO-E-Snapshot in data/raw/.
Vergleichs-Referenzen (optional, wenn vorhanden):
  submissions/backtest_ensemble_test/<date>.csv  (0.5/0.5 aus ensemble_test)
  submissions/backtest_spotoptim_test/<date>.csv (reines LightGBM spotoptim)

Usage:
    uv run python scripts/analyse_weight_sweep.py
    uv run python scripts/analyse_weight_sweep.py --dates 2026-06-18 2026-06-19 2026-06-20
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
SUB_DIR = REPO / "submissions"
RAW_DIR = REPO / "data" / "raw"
OUT_DIR = REPO / "data" / "backtest"

RAW_FILE_RE = re.compile(r"entsoe_load_(\d{12})_(\d{12})\.csv$")
WEIGHTS = np.round(np.arange(0.0, 1.01, 0.1), 2)
DATES_DEFAULT = ["2026-06-18", "2026-06-19", "2026-06-20"]


def find_actuals(dates: list[str]) -> dict[str, pd.Series]:
    """Find actual load for each date from the newest snapshot covering all dates."""
    raw_files = sorted(
        (p for p in RAW_DIR.glob("entsoe_load_*.csv") if RAW_FILE_RE.search(p.name)),
        key=lambda p: RAW_FILE_RE.search(p.name).group(2),
        reverse=True,
    )
    actuals: dict[str, pd.Series] = {}
    for date in dates:
        day_index = pd.date_range(f"{date}T00:00:00Z", periods=24, freq="h", tz="UTC")
        for path in raw_files:
            df = pd.read_csv(path)
            df["Time (UTC)"] = pd.to_datetime(df["Time (UTC)"], utc=True)
            df = df.set_index("Time (UTC)").sort_index()
            hourly = df[["Actual Load"]].resample("1h").mean()
            day = hourly.reindex(day_index)
            if day["Actual Load"].notna().all():
                actuals[date] = day["Actual Load"]
                break
        else:
            print(f"WARN: no full actuals found for {date}")
    return actuals


def load_submission(path: Path) -> pd.Series:
    df = pd.read_csv(path)
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)
    return df.set_index("timestamp_utc")["forecast_mw"]


def mae(pred: pd.Series, actual: pd.Series) -> float:
    aligned = pred.reindex(actual.index)
    return float((aligned - actual).abs().mean())


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dates", nargs="+", default=DATES_DEFAULT)
    args = p.parse_args()
    dates: list[str] = args.dates

    actuals = find_actuals(dates)
    if not actuals:
        raise SystemExit("No actuals found – check data/raw/ for recent snapshots.")

    # Load pure submissions
    lgbm_subs = {}
    xgb_subs = {}
    missing = []
    for date in dates:
        lp = SUB_DIR / "backtest_lgbm_pure" / f"{date}.csv"
        xp = SUB_DIR / "backtest_xgb_pure" / f"{date}.csv"
        if not lp.exists():
            missing.append(str(lp))
        else:
            lgbm_subs[date] = load_submission(lp)
        if not xp.exists():
            missing.append(str(xp))
        else:
            xgb_subs[date] = load_submission(xp)
    if missing:
        raise SystemExit(
            "Missing submissions (run /tmp/se-weight-backtest-run.sh first):\n"
            + "\n".join(f"  {m}" for m in missing)
        )

    # Load optional reference submissions
    ref_ensemble = {}
    ref_spotoptim = {}
    for date in dates:
        ep = SUB_DIR / "backtest_ensemble_test" / f"{date}.csv"
        sp = SUB_DIR / "backtest_spotoptim_test" / f"{date}.csv"
        if ep.exists():
            ref_ensemble[date] = load_submission(ep)
        if sp.exists():
            ref_spotoptim[date] = load_submission(sp)

    # --- Weight sweep ---
    rows = []
    for w in WEIGHTS:
        w_lgbm = float(w)
        w_xgb = 1.0 - w_lgbm
        day_maes = []
        for date in dates:
            if date not in actuals or date not in lgbm_subs or date not in xgb_subs:
                continue
            blend = w_lgbm * lgbm_subs[date] + w_xgb * xgb_subs[date]
            day_maes.append(mae(blend, actuals[date]))
        if day_maes:
            rows.append({"lgbm_weight": w_lgbm, "mae_mean": np.mean(day_maes),
                         **{f"mae_{d}": v for d, v in zip(dates, day_maes)}})

    df_sweep = pd.DataFrame(rows)
    best_row = df_sweep.loc[df_sweep["mae_mean"].idxmin()]
    best_w = float(best_row["lgbm_weight"])
    best_mae = float(best_row["mae_mean"])

    # Bates-Granger optimal weight (from per-day individual MAEs)
    lgbm_day_maes = [mae(lgbm_subs[d], actuals[d]) for d in dates if d in actuals]
    xgb_day_maes  = [mae(xgb_subs[d],  actuals[d]) for d in dates if d in actuals]
    mae_lgbm_avg = np.mean(lgbm_day_maes)
    mae_xgb_avg  = np.mean(xgb_day_maes)
    w_bg = (1 / mae_lgbm_avg) / (1 / mae_lgbm_avg + 1 / mae_xgb_avg)

    # Reference MAEs
    ref_ensemble_mae = None
    ref_spotoptim_mae = None
    if ref_ensemble:
        ref_ensemble_mae = np.mean([mae(ref_ensemble[d], actuals[d])
                                    for d in dates if d in ref_ensemble and d in actuals])
    if ref_spotoptim:
        ref_spotoptim_mae = np.mean([mae(ref_spotoptim[d], actuals[d])
                                     for d in dates if d in ref_spotoptim and d in actuals])

    # --- Print results ---
    print("\n=== Weight Sweep Results (Ø MAE across 3 days) ===")
    print(df_sweep[["lgbm_weight", "mae_mean"]].to_string(index=False,
          float_format=lambda v: f"{v:.1f}" if v > 1 else f"{v:.2f}"))
    print(f"\nBest weight:              lgbm={best_w:.1f} → Ø MAE {best_mae:.0f} MW")
    print(f"Bates-Granger weight:     lgbm={w_bg:.3f}  (from individual MAEs: "
          f"LGBM={mae_lgbm_avg:.0f}, XGB={mae_xgb_avg:.0f})")
    if ref_ensemble_mae is not None:
        print(f"Ref ensemble (0.5/0.5):   Ø MAE {ref_ensemble_mae:.0f} MW")
    if ref_spotoptim_mae is not None:
        print(f"Ref spotoptim (LGBM):     Ø MAE {ref_spotoptim_mae:.0f} MW")

    # --- Save CSV ---
    out_csv = OUT_DIR / "weight_sweep_results.csv"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df_sweep.to_csv(out_csv, index=False)
    print(f"\nSaved sweep table → {out_csv}")

    # --- Plot ---
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(df_sweep["lgbm_weight"], df_sweep["mae_mean"],
            color="#1F4E79", linewidth=2, marker="o", ms=5, label="post-hoc blend")
    ax.axvline(best_w, color="#1F4E79", linestyle="--", linewidth=1,
               label=f"best (w={best_w:.1f}, MAE {best_mae:.0f})")
    ax.axvline(w_bg, color="#2E8B57", linestyle=":", linewidth=1.5,
               label=f"Bates-Granger (w={w_bg:.3f})")
    if ref_ensemble_mae is not None:
        ax.axhline(ref_ensemble_mae, color="#E07B00", linestyle="-.", linewidth=1,
                   label=f"ref ensemble 0.5 (MAE {ref_ensemble_mae:.0f})")
    if ref_spotoptim_mae is not None:
        ax.axhline(ref_spotoptim_mae, color="#888888", linestyle="-.", linewidth=1,
                   label=f"ref spotoptim LGBM (MAE {ref_spotoptim_mae:.0f})")
    ax.set_xlabel("LGBM weight  (XGBoost weight = 1 − this)")
    ax.set_ylabel("Ø MAE [MW]")
    ax.set_title(f"Ensemble weight sweep — {', '.join(dates)}")
    ax.grid(True, color="#E5E5E5", linewidth=0.5)
    ax.legend(fontsize=8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    out_png = OUT_DIR / "weight_sweep.png"
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    print(f"Saved plot        → {out_png}")

    # --- Markdown summary ---
    md_lines = [
        "# Weight Sweep: LGBM vs XGBoost Blend",
        "",
        f"Backtested days: {', '.join(dates)}  |  n_trials=10, n_initial=5  |  "
        f"Pipeline: syntaxerror_ensemble_test.py",
        "",
        "## Ø MAE (MW) vs. LGBM-Gewichtung",
        "",
        "| LGBM weight | XGB weight | Ø MAE |",
        "|---|---|---|",
    ]
    for _, row in df_sweep.iterrows():
        w = row["lgbm_weight"]
        md_lines.append(f"| {w:.1f} | {1-w:.1f} | **{row['mae_mean']:.0f}** "
                        + ("← best" if abs(w - best_w) < 0.01 else "") + " |")
    md_lines += [
        "",
        f"**Bestes Gewicht (Sweep):** lgbm={best_w:.1f} → Ø MAE {best_mae:.0f} MW",
        f"**Bates-Granger-Gewicht:** lgbm={w_bg:.3f}  "
        f"(aus LGBM-MAE {mae_lgbm_avg:.0f} MW, XGB-MAE {mae_xgb_avg:.0f} MW)",
        "",
        "## Referenzwerte",
        "",
    ]
    if ref_ensemble_mae is not None:
        md_lines.append(f"- Ensemble 0.5/0.5 (backtest_ensemble_test): Ø MAE {ref_ensemble_mae:.0f} MW")
    if ref_spotoptim_mae is not None:
        md_lines.append(f"- Reines LightGBM (backtest_spotoptim_test):  Ø MAE {ref_spotoptim_mae:.0f} MW")
    md_lines += [
        "",
        "## Caveats",
        "",
        "- Post-hoc blend: die verwendeten LGBM- und XGB-Modelle wurden jeweils mit "
          "Gewichtung 1.0/0.0 optimiert (Hyperparameter für Einzelmodell, nicht für "
          "Ensemble). Ein echter Training-Run mit dem optimalen Gewicht würde "
          "Hyperparameter für die Blending-Gewichtung gemeinsam optimieren → "
          "die Kurve unterschätzt leicht das Potenzial des optimalen Gewichts.",
        "- n=3 Tage, kleine Stichprobe.",
        "- Seitentabellen nicht historisch nachgebildet (gleiches Restrisiko wie in "
          "ensemble_weight_test.md dokumentiert).",
    ]
    out_md = OUT_DIR / "weight_sweep.md"
    out_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    print(f"Saved Markdown    → {out_md}")


if __name__ == "__main__":
    main()
