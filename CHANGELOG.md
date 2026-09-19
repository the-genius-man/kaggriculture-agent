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
- **policy_001 (experiment)** — occupancy-first template in `policy/policy_001.py`.
  Seed-safe PLANT (engine drops a whole crop if demand exceeds stock), fill-before-expand,
  delayed water/care while filling, focused seed buys, opening wheat for cashflow.
  Screened as named strategies against V12 (`experiments/exp_policy_001.py`). V5 tapes
  are not in the pool. **No `main.py`:** occupancy at day 20 reached ~70 on 3-quad
  configs (vs ~45 on V13), but cash vs V12 did not clear the promotion bar. Best
  named config `boey_land2` was 4/6 and +712 on the 3-seed screen, 9/12 and +6065
  on a 6-seed confirm, then **13/24 (0.54) and +1113** on a fresh 12-seed holdout
  vs V12, and 0.75 vs V9. Pooled 26/42 vs V12 is only a noisy hint, not a promotion.
- **v12_delta (experiment)** — V12 scorer plus plant-quota / yield-aware melon
  (`policy/v12_delta.py`). Live Majkel/SpaTaro/THIRD FARM games fill 3 quadrants
  by day 10 (~74 tiles) and drip-sell fertilizer; copying occupancy onto V12
  *lost* EV. `gate_only` screened 6/8 +4042 vs V12 then holdout **8/16 (0.50) +498**.
  vs V9 holdout 13/16 (0.81). No `main.py`.
- **v12_gate (not submitted)** — `gate_fert` = V12 scorer + plant quota + yield-aware
  melon + fertilizer drip-sell + day-0 sheep burst. Saved as `agents/main_v12_gate.py`.
  Measured vs V12 (internal, not ladder): 6/8 screen, 12/16 holdout, 16/24 expand =
  **34/48 (0.71), mean margin ~+1500, min ~-5.5k**. vs V9 12/16 (0.75). Does not
  clear the V9>=80% promotion gate. `main.py` not written. V12 left untouched.
- **v12_quota (not submitted)** — plant-quota only (no sheep burst, no fert drip).
  Ablation showed those extras were noisy. Fresh holdouts: **16/16 vs V12** then
  **19/24 (0.79)**; vs V9 **16/16**. Saved as `agents/main_v12_quota.py`. Still a
  2-quadrant V12-shaped farm; a live V12 just lost −30k to a strawberry 3-quad
  opponent. Not submitted. Live slots as of this note: V14 551.6 (Nick, CI) + V12 611.
- **v12_fill (not submitted)** — fill-and-sell on the V12 scorer. Plant quota +
  melon peak 12, fill Q2 with strawberries (drip seeds, meter premium sells at 4/turn),
  expand only after ~88% occupancy. Creative screen vs V12: `fill2_dense` **8/8**,
  `hold_straw` 7/8 then collapsed **8/16**, early Q3 / Sauls-pace blew up.
  `fill_then_q3` (dense fill then land=3 by day 14): screen **8/8 +11.7k**, holdout
  **13/16 +5.3k**, expand **22/24 +8.9k** = **43/48 vs V12 (0.90)**; vs V9 **14/16
  (0.88)**. Day-20 occupancy ~69 on ~2.5 quads (V12 stays ~42 on 2). Frozen as
  `agents/main_v12_fill.py`. 2-quad-only fallback `agents/main_v12_fill2.py` was
  **44/48 vs V12 (0.92)** and **16/16 vs quota_only**, but does not close the live
  3-quad gap. `main.py` not written. V12 left untouched. Internal self-play, not a
  ladder result.
