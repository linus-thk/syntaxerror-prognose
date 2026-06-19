# target_corruption_policy="heal" -- Backtest-Ergebnis (verworfen)

Frage: lindert `policy="heal"` (statt `"truncate"`) das Problem, dass eine
einzelne korrupte Stunde mitten in der Nacht den ganzen Rest des Trainings-
tages mit verwirft? (Siehe Chat-Diskussion 2026-06-18/19 zu
"corrupt target tail".)

## Methode

Gleicher Aufbau wie der XGBoost-Vergleich: historischer Replay fuer
06-11/06-16/06-17, `--as-of`, `--skip-download`, isolierte Worktree,
Ensemble an, `n_trials=10 n_initial=5`, seriell (`--n-jobs 0`). Einzige
Aenderung ggue. dem bisherigen Bestwert (`backtest_xgb`, MAE 2794/712/1217):
`TARGET_CORRUPTION_POLICY="heal"`, `TARGET_MAX_HEAL_HOURS=5`,
`TARGET_ANCHOR_ZONE_HOURS=8`.

## Ergebnis: 2 von 3 Laeufen brechen hart ab

| Tag | Ergebnis |
|---|---|
| 2026-06-11 | Prozess von aussen gekillt (Signal 9, vermutlich Ressourcen-Konflikt mit dem parallel laufenden echten Produktions-Lauf) -- kein Policy-Befund |
| 2026-06-16 | **TargetCorruptionError, harter Abbruch, keine Submission.** "2 flagged hour(s) lie within the anchor zone (8 h before cutoff=2026-06-15 10:00:00+00:00)." |
| 2026-06-17 | **TargetCorruptionError, harter Abbruch, keine Submission.** "3 flagged hour(s) lie within the anchor zone (8 h before cutoff=2026-06-16 09:00:00+00:00)." |

Anders als `"truncate"` degradiert `"heal"` bei einer Verletzung der
Anchor-Zone nicht (keine Submission, nur schlechter) -- es **verweigert
komplett** und wirft eine Exception. `anchor_zone_hours=8` war zu klein:
die beobachteten Korruptionen lagen bei zwei von drei Tagen naeher am
Cutoff als 8h.

## Fazit

`TARGET_CORRUPTION_POLICY` wurde auf `"truncate"` zurueckgesetzt
(2026-06-19, siehe Kommentar im Code). Ein harter Totalausfall ist bei
einer harten taeglichen Deadline schlimmer als eine etwas schlechtere,
aber garantiert vorhandene Submission.

**Falls "heal" nochmal versucht werden soll:** `TARGET_ANCHOR_ZONE_HOURS`
deutlich groesser waehlen (deutlich >8h noetig, basierend auf diesem
Sample reicht 8h nicht), erneut backtesten -- und zusaetzlich pruefen, ob
sich der harte Abbruch bei Anchor-Zone-Verletzung softwareseitig abfangen
laesst (z.B. Fallback auf "truncate" statt Exception), damit ein
Konfigurationsfehler nie eine komplette Submission kostet.
