# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Team Syntaxerror

"""
backtest_submissions.py

Vergleicht abgegebene Submissions (submissions/<team>/<date>.csv) gegen die
spaeter publizierte tatsaechliche Last UND die ENTSO-E-Day-Ahead-Prognose.
Beide Referenzwerte stecken bereits in den vorhandenen data/raw-Snapshots:
jeder neuere Snapshot traegt die "Actual Load" der Vortage nach, die zum
Prognosezeitpunkt noch leer war.

Schreibt MAE/RMSE je Tag nach data/backtest/results.csv (kumulativ, neue
Laeufe ueberschreiben nur die betroffenen Datumszeilen) und erzeugt je Tag
einen Vergleichsplot (data/backtest/plots/<date>.png) im Stil von
``_plot_vs_entsoe`` aus syntaxerror_submit.py.

Ein Tag wird uebersprungen, wenn noch kein Snapshot mit vollstaendiger
Actual-Load-Abdeckung fuer diesen Tag existiert (z.B. fuer den aktuellen
Zieltag, dessen Ist-Last noch nicht publiziert ist).
"""
from __future__ import annotations

import argparse
import functools
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

RAW_FILE_RE = re.compile(r"entsoe_load_(\d{12})_(\d{12})\.csv$")
SUBMISSION_COLUMNS = ["timestamp_utc", "forecast_mw"]


def find_raw_snapshots(raw_dir: Path) -> list[Path]:
    """Snapshot-Dateien aufsteigend nach dem im Dateinamen kodierten
    Abdeckungsende sortiert (nicht nach mtime -- die spiegelt nur den
    lokalen Checkout/Download-Zeitpunkt wider, nicht die Datenabdeckung)."""
    files = [p for p in raw_dir.glob("entsoe_load_*.csv") if RAW_FILE_RE.search(p.name)]
    return sorted(files, key=lambda p: RAW_FILE_RE.search(p.name).group(2))


@functools.lru_cache(maxsize=None)
def load_snapshot_hourly(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["Time (UTC)"] = pd.to_datetime(df["Time (UTC)"], utc=True)
    df = df.set_index("Time (UTC)").sort_index()
    return df[["Forecasted Load", "Actual Load"]].resample("1h").mean()


def find_actuals_for_date(raw_dir: Path, target_date: str) -> pd.DataFrame | None:
    """Aeltester Snapshot, in dem alle 24 Stunden des Zieltags bereits eine
    publizierte Actual Load tragen."""
    day_index = pd.date_range(f"{target_date}T00:00:00Z", periods=24, freq="h", tz="UTC")
    for path in find_raw_snapshots(raw_dir):
        hourly = load_snapshot_hourly(str(path))
        day = hourly.reindex(day_index)
        if day["Actual Load"].notna().all():
            return day.rename(columns={"Forecasted Load": "entsoe_forecast",
                                        "Actual Load": "actual_load"})
    return None


def load_submission(path: Path) -> pd.Series:
    df = pd.read_csv(path)
    if list(df.columns) != SUBMISSION_COLUMNS:
        raise ValueError(f"{path}: Spalten {list(df.columns)} != erwartete {SUBMISSION_COLUMNS}")
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)
    return df.set_index("timestamp_utc")["forecast_mw"]


def mae(a: pd.Series, b: pd.Series) -> float:
    return float((a - b).abs().mean())


def rmse(a: pd.Series, b: pd.Series) -> float:
    return float(((a - b) ** 2).mean() ** 0.5)


def plot_comparison(date: str, df: pd.DataFrame, out_path: Path) -> None:
    """Stil an _plot_vs_entsoe (syntaxerror_submit.py) angelehnt, um zusaetzliche
    tatsaechliche Last erweitert."""
    fig, ax = plt.subplots(figsize=(8.5, 3.5))
    ax.plot(df.index, df["actual_load"] / 1000, color="#333333", linewidth=1.8,
            label="tatsaechliche Last")
    ax.plot(df.index, df["forecast_mw"] / 1000, marker="o", ms=3, color="#1F4E79",
            label="syntaxerror forecast")
    if df["entsoe_forecast"].notna().any():
        ax.plot(df.index, df["entsoe_forecast"] / 1000, marker="x", ms=4,
                color="#E07B00", label="ENTSO-E day-ahead forecast")
    ax.set_xlabel("Time (UTC)")
    ax.set_ylabel("Load [GW]")
    ax.set_title(f"syntaxerror vs. ENTSO-E vs. tatsaechliche Last -- {date}")
    ax.grid(True, color="#E5E5E5", linewidth=0.5)
    ax.legend(fontsize=8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def backtest_one(sub_path: Path, raw_dir: Path, plot_dir: Path) -> dict | None:
    date = sub_path.stem
    actuals = find_actuals_for_date(raw_dir, date)
    if actuals is None:
        print(f"SKIP {date}: noch keine vollstaendig publizierte Actual Load "
              f"fuer diesen Tag in {raw_dir}", file=sys.stderr)
        return None

    df = actuals.copy()
    df["forecast_mw"] = load_submission(sub_path).reindex(df.index)
    if df["forecast_mw"].isna().any():
        print(f"WARN {date}: {int(df['forecast_mw'].isna().sum())} Stunden "
              f"ohne passenden Submission-Wert", file=sys.stderr)

    plot_dir.mkdir(parents=True, exist_ok=True)
    plot_comparison(date, df, plot_dir / f"{date}.png")

    row = {
        "date": date,
        "mae_syntaxerror": mae(df["forecast_mw"], df["actual_load"]),
        "rmse_syntaxerror": rmse(df["forecast_mw"], df["actual_load"]),
    }
    if df["entsoe_forecast"].notna().any():
        row["mae_entsoe"] = mae(df["entsoe_forecast"], df["actual_load"])
        row["rmse_entsoe"] = rmse(df["entsoe_forecast"], df["actual_load"])
    else:
        row["mae_entsoe"] = float("nan")
        row["rmse_entsoe"] = float("nan")
    return row


def update_results(results_path: Path, rows: list[dict]) -> pd.DataFrame:
    new_df = pd.DataFrame(rows).set_index("date")
    if results_path.exists():
        old_df = pd.read_csv(results_path, index_col="date")
        combined = pd.concat([old_df, new_df])
        combined = combined[~combined.index.duplicated(keep="last")]
    else:
        combined = new_df
    combined = combined.sort_index()
    results_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(results_path)
    return combined


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--team", default="syntaxerror")
    parser.add_argument("--date", default=None,
                        help="einzelnes Zieldatum YYYY-MM-DD; ohne Angabe alle "
                             "vorhandenen Submissions des Teams")
    parser.add_argument("--submissions-dir", default="submissions")
    parser.add_argument("--raw-dir", default="data/raw")
    parser.add_argument("--out", default="data/backtest/results.csv")
    parser.add_argument("--plots", default="data/backtest/plots")
    args = parser.parse_args()

    sub_dir = Path(args.submissions_dir) / args.team
    if args.date:
        paths = [sub_dir / f"{args.date}.csv"]
    else:
        paths = sorted(sub_dir.glob("*.csv"))

    rows = []
    for p in paths:
        if not p.exists():
            print(f"SKIP {p}: nicht gefunden", file=sys.stderr)
            continue
        row = backtest_one(p, Path(args.raw_dir), Path(args.plots))
        if row is not None:
            rows.append(row)

    if not rows:
        print("Keine auswertbaren Tage gefunden.", file=sys.stderr)
        sys.exit(1)

    combined = update_results(Path(args.out), rows)
    evaluated_dates = {r["date"] for r in rows}
    print(combined.loc[combined.index.isin(evaluated_dates)].to_string(
        float_format=lambda v: f"{v:,.0f}"))


if __name__ == "__main__":
    main()
