# XGBoost-Ensemble vs. reines LightGBM -- kontrollierter Backtest-Vergleich

Frage: macht das LightGBM+XGBoost-Ensemble (`team4_ensemble_factory`,
`USE_XGBOOST_ENSEMBLE`) die Prognose schlechter, wie der erste Eindruck aus
den echten Produktions-Submissions (06-16/06-17 vs. die LightGBM-only-Tage
davor) nahelegte?

## Methode

Historischer Replay (`--as-of`, `--skip-download`) für drei Tage, je einmal
mit und einmal ohne Ensemble, sonst identische Bedingungen:

- gleiche historische Rohdaten-Snapshots (`data/raw/entsoe_load_*.csv`,
  passend zum jeweiligen Zieltag -- nur die Load/Ziel-Spalte wurde historisch
  korrekt eingesetzt, Wetter/Renewable/Preis-Seitentabellen blieben die
  aktuellen, geringes Restrisiko für Leakage auf diesen Nebenfeatures)
- `--n-trials 10 --n-initial 5` (reduziert ggü. den 25-100 der echten Läufe,
  fuer Tempo)
- isolierte Worktree (`git worktree add --detach /tmp/se-xgb-backtest`),
  damit nichts am echten Repo-Zustand haengt
- Ensemble-Variante musste **seriell** laufen (`--n-jobs 0`): parallel
  (`n_jobs=-1`, fork-basiert) crashte zu 100% mit
  `RuntimeError: All initial design evaluations failed` -- der in
  `team4_ensemble_factory` dokumentierte macOS-Fork/OpenMP-Konflikt war hier
  reproduzierbar. Die reine LightGBM-Variante lief problemlos parallel.

## Ergebnis: MAE (MW) im Backtest gegen die tatsaechliche Last

| Tag | ohne XGBoost (Probe) | mit XGBoost (Probe) | ENTSO-E Baseline | **echte Produktions-Submission** |
|---|---|---|---|---|
| 2026-06-11 | 2848 | **2794** | 4270 | 2954 (LightGBM-only, vor Ensemble-Einfuehrung) |
| 2026-06-16 | 894 | **712** | 1874 | 4113 (Ensemble, 100 Trials parallel) |
| 2026-06-17 | 1489 | **1217** | 1973 | 3501 (Ensemble, 100 Trials parallel) |

## Fazit

Das Ensemble ist in diesem kontrollierten Vergleich an allen drei Tagen
**besser**, nicht schlechter, als reines LightGBM -- der erste Verdacht
(XGBoost verschlechtert die Prognose) hat sich nicht bestaetigt.

Auffaelliger ist ein anderer Effekt: beide Probe-Varianten (10 Trials)
schlagen die echten Produktions-Submissions (25-100 Trials, teils parallel)
an 06-16 und 06-17 drastisch (894/712 vs. 4113; 1489/1217 vs. 3501). Das
deckt sich mit der zuvor beobachteten Tag-zu-Tag-Instabilitaet der
SpotOptim-Hyperparameter (z.B. `learning_rate` 0.009->0.26->0.09,
`n_estimators` 4242->381->2844 an 06-15/16/17): ein groesseres/parallel
laufendes Tuning-Budget scheint sich hier eher auf Rauschen im kleinen
Validierungsfenster zu ueberanpassen, statt die Prognose zuverlaessig zu
verbessern.

**Empfehlung:** `USE_XGBOOST_ENSEMBLE = True` beibehalten (bereits so
gesetzt). Der naechste Hebel ist nicht das Modell, sondern das
Tuning-Budget/-Setup -- siehe die fruehere Diskussion zur
Hyperparameter-Instabilitaet.

## Caveats

- n=3 Tage, kleine Stichprobe.
- Seitentabellen (Wetter/Renewable/Preis) wurden nicht pro Tag historisch
  nachgebildet, nur Forderung/Ziel-Last; geringes Leakage-Risiko auf diesen
  Nebenfeatures.
- Probe-Laeufe nutzten 10 statt 25-100 Trials -- der Vergleich
  ohne-vs-mit-XGBoost ist dadurch fair (beide Varianten gleich behandelt),
  der Vergleich Probe-vs-Produktion vermischt Trial-Budget mit allem anderen.
- Rohdaten/Logs der Probe-Laeufe liegen unter `/tmp/se-xgb-backtest/`
  (Worktree, ggf. nicht dauerhaft) sowie als CSVs unter
  `submissions/backtest_noxgb/` und `submissions/backtest_xgb/` in diesem
  Repo (nicht committet).
