# Changelog

Versions are explicit and cumulative. Older agents are preserved as fallbacks.

- **V9** — coordinated farming baseline; still a strong reference. Kaggle rating ~612
  (historical, user-reported).
- **V11** — deadline-aware final-day liquidation. Reported to underperform V9
  (~607.2 vs 612).
- **V12** — Optuna parameter search over the policy. **Trial-23 promoted** (holdout
  win rate ~0.72 pooled across the league). This is the current fallback champion,
  `agents/main_v12.py`, sha256 `dffae949e74e...`.
- **V13** — structural-policy search (region routing, phase-agnostic). Analysed
  against 11 real leaderboard replays (4 wins, 7 losses). Diagnosis: under-produces
  strawberries and under-fills land; overtaken late.
- **Enhanced Game v1** — resumable self-play league (generalist + exploiter search,
  promotion gates, fresh holdouts).
- **Enhanced Game v2** — phase-dependent policy params, throughput auto-benchmark,
  widened `plant_floor`. See `notebooks/`.
- **V14 (in progress)** — melon maturity fix (peak 10->12, yield-aware harvest) and a
  searchable `strawberry_target` for early occupancy. Preliminary local signal is
  positive vs V9 and V12; occupancy gap to the strongest opponent is not yet closed.
  Needs a full searched + fresh-holdout validation run before any submission.
