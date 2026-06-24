# syntaxerror_ensemble_test.py -- erster kontrollierter Backtest (Equal-Weight)

Frage: Lohnt sich `syntaxerror_ensemble_test.py` (LightGBM+XGBoost-Ensemble
mit konfigurierbarer Blend-Gewichtung via `--lgbm-weight`) gegenueber dem
Single-LightGBM-Stockmodell aus `syntaxerror_spotoptim_submit.py`? Dieser
erste Lauf testet nur den Equal-Weight-Fall (`--lgbm-weight 0.5`, Default --
identisch zum Verhalten von `team4_ensemble_factory` in
`syntaxerror_submit.py`). Die eigentliche Gewichtungsfrage (lohnt eine
*andere* Gewichtung als 0.5?) ist damit noch NICHT beantwortet -- dafuer
braucht es die Einzel-MAE von LightGBM und XGBoost getrennt auf denselben
Tagen, um die Inverse-Error-Formel (siehe Docstring von
`syntaxerror_ensemble_test.py`) anzuwenden.

## Methode

Historischer Replay (`--as-of`, `--skip-download`) fuer drei Tage
(2026-06-18 bis 2026-06-20), je einmal mit `syntaxerror_spotoptim_submit.py`
(Single-LightGBM) und einmal mit `syntaxerror_ensemble_test.py`
(LGBM+XGBoost, `--lgbm-weight 0.5`), sonst identische Bedingungen:

- isolierte Worktree (`git worktree add --detach /tmp/se-ensemble-backtest`),
  damit nichts am echten Repo-Zustand haengt
- pro Tag wurde NUR der zum Zieltag passende historische ENTSO-E-Rohdaten-
  Snapshot (`data/raw/entsoe_load_*.csv`, Stand Vorabend) in `data/raw/`
  eingespielt und `merge_build_manual(keep_forecast_future=True)` darauf neu
  ausgefuehrt, um die `interim/energy_load.csv` leakage-frei fuer den
  jeweiligen Zieltag neu aufzubauen (kein Wiederverwenden des aktuellen,
  vollstaendigen Caches)
- `--n-trials 10 --n-initial 5` (reduziert ggue. den 25-100 der echten
  Laeufe, fuer Tempo -- siehe Laufzeit-Caveat unten)
- `--n-jobs 0` (seriell) fuer beide Scripts -- Pflicht fuers Ensemble
  (siehe `team4_ensemble_factory`/`weighted_ensemble_factory`-Kommentare
  zum macOS-Fork/OpenMP-Crash), zur Vergleichbarkeit auch fuer das
  Single-LightGBM-Script
- Ground Truth (tatsaechliche Last + ENTSO-E-Day-Ahead-Prognose) aus dem
  juengsten verfuegbaren Snapshot (`entsoe_load_..._202606250000.csv`),
  der alle drei Zieltage vollstaendig abdeckt

## Ergebnis: MAE/RMSE (MW) im Backtest gegen die tatsaechliche Last

| Tag | MAE LightGBM-only | MAE Ensemble (0.5/0.5) | MAE ENTSO-E-Baseline | RMSE LightGBM-only | RMSE Ensemble | RMSE ENTSO-E |
|---|---|---|---|---|---|---|
| 2026-06-18 | 1736 | **1482** | 2366 | 1951 | 1775 | 2654 |
| 2026-06-19 | 1403 | **1097** | 3301 | 1550 | 1253 | 3402 |
| 2026-06-20 | 1737 | **1497** | 1589 | 2046 | 1630 | 2007 |
| **Ø** | **1625** | **1359** | **2419** | **1849** | **1553** | **2687** |

Rohdaten: `ensemble_weight_test_results.csv` (dieses Verzeichnis),
Submissions: `submissions/backtest_spotoptim_test/`,
`submissions/backtest_ensemble_test/`.

## Fazit

Equal-Weight-Ensemble schlaegt Single-LightGBM an allen 3 Tagen (Ø ca. 16%
niedrigerer MAE) und schlaegt die ENTSO-E-Baseline deutlich. Das bestaetigt
den frueheren Befund aus `xgb_comparison.md` (dort n=3, andere Tage:
2026-06-11/16/17) -- zusammengenommen 6/6 Tagen, an denen das
Equal-Weight-Ensemble besser war als Single-LightGBM.

**Naechster Schritt (offen):** dieselben 3 (oder mehr) Tage mit isoliertem
LightGBM-MAE und isoliertem XGBoost-MAE durchlaufen lassen, daraus per
Inverse-Error-Formel ein `--lgbm-weight` != 0.5 ableiten und gegen den
Equal-Weight-Fall hier backtesten.

## Caveats

- n=3 Tage, kleine Stichprobe (gepoolt mit `xgb_comparison.md`: n=6).
- Seitentabellen (Wetter) liefen live/aktuell mit, nicht historisch
  nachgebildet -- gleiches Restrisiko wie in `xgb_comparison.md` dokumentiert.
- **Laufzeit:** das Ensemble war pro Tag ca. 10-15x langsamer als
  Single-LightGBM (XGBoost `n_estimators=1000`, einzelthreadig wegen des
  macOS-Fork-Workarounds) -- trotz nur 10 Trials kein "schneller" Test
  (ca. 12-15 Min/Tag fuers Ensemble vs. ca. 1 Min/Tag fuer Single-LightGBM).
- `--lgbm-weight` war fix auf 0.5 (Default); kein Sweep ueber andere Werte.
