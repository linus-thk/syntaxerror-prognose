# Weight Sweep: LGBM vs XGBoost Blend

Backtested days: 2026-06-18, 2026-06-19, 2026-06-20  |  n_trials=10, n_initial=5  |  Pipeline: syntaxerror_ensemble_test.py

## Ø MAE (MW) vs. LGBM-Gewichtung

| LGBM weight | XGB weight | Ø MAE |
|---|---|---|
| 0.0 | 1.0 | **1319**  |
| 0.1 | 0.9 | **1296**  |
| 0.2 | 0.8 | **1274**  |
| 0.3 | 0.7 | **1253**  |
| 0.4 | 0.6 | **1234**  |
| 0.5 | 0.5 | **1217**  |
| 0.6 | 0.4 | **1200**  |
| 0.7 | 0.3 | **1188**  |
| 0.8 | 0.2 | **1186**  |
| 0.9 | 0.1 | **1185** ← best |
| 1.0 | 0.0 | **1188**  |

**Bestes Gewicht (Sweep):** lgbm=0.9 → Ø MAE 1185 MW
**Bates-Granger-Gewicht:** lgbm=0.526  (aus LGBM-MAE 1188 MW, XGB-MAE 1319 MW)

## Referenzwerte

- Ensemble 0.5/0.5 (backtest_ensemble_test): Ø MAE 1359 MW
- Reines LightGBM (backtest_spotoptim_test):  Ø MAE 1625 MW

## Caveats

- Post-hoc blend: die verwendeten LGBM- und XGB-Modelle wurden jeweils mit Gewichtung 1.0/0.0 optimiert (Hyperparameter für Einzelmodell, nicht für Ensemble). Ein echter Training-Run mit dem optimalen Gewicht würde Hyperparameter für die Blending-Gewichtung gemeinsam optimieren → die Kurve unterschätzt leicht das Potenzial des optimalen Gewichts.
- n=3 Tage, kleine Stichprobe.
- Seitentabellen nicht historisch nachgebildet (gleiches Restrisiko wie in ensemble_weight_test.md dokumentiert).
