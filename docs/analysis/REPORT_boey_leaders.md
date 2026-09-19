---
title: Analysis of the four supplied leaderboard replays
---

# Analysis of the four supplied leaderboard replays

The fourth quadrant remains an active strategy candidate. These games do not establish that three quadrants are optimal. They demonstrate how much production a coordinated policy can obtain from its available land.

## Evidence and validation

Replayed all 719 transitions in each of the four games using the pinned Kaggriculture engine (kaggle-environments 1.32.7). All 2,876 reconstructed transitions matched the recorded game state; cash transaction ledgers reconcile with final cash. Boey is the common player, winning all four supplied games. This is a selected sample, not a leaderboard rank verification or a controlled comparison with V13.

| Replay | Boey cash | Opponent | Opponent cash | Boey margin |
|---|---:|---|---:|---:|
| 110304539 | 89,426 | DSM | 82,090 | 7,336 |
| 110304588 | 122,829 | SpaTaro | 107,055 | 15,774 |
| 110315401 | 116,143 | Majkel1337 | 103,272 | 12,871 |
| 110320804 | 116,470 | Unknown Mother-Goose | 104,703 | 11,767 |

Mean Boey final cash: 111,217. All eight player appearances ended with three quadrants. Thus this sample contains no direct fourth-quadrant experiment.

## Expansion becomes production quickly

Boey buys the second quadrant on day 7, hour 2 in every game, then the third between day 9, hour 7 and day 10, hour 2. By the end of day 10, an average 74.75 of 75 owned tiles contain crops or animals. That level persists through day 20. The third quadrant has 24–25 productive tiles at day 20.

Boey reaches 12 hands in each game and has 11 at day 20. This is within V13's existing maximum: the observed gap cannot be explained simply by a higher worker ceiling.

| End-of-day snapshot, Boey mean | Day 5 | Day 10 | Day 15 | Day 20 | Day 25 |
|---|---:|---:|---:|---:|---:|
| Productive tiles | 24.75 | 74.75 | 74.75 | 74.75 | 70.25 |
| Strawberry plots | 4 | 28.5 | 34 | 33.75 | 11.25 |
| Wheat plots | 1.5 | 17.75 | 21.5 | 21.5 | 35.25 |
| Melon plots | 10.25 | 10.75 | 0.5 | 0 | 0 |
| Animals | 9 | 17.75 | 18.75 | 18.75 | 18 |

V13 averaged approximately 44.8 productive tiles at day 20 across the earlier 11 replays. Boey's 74.75 indicates a large utilization gap worth testing. Different opponents, prices and seeds prevent treating the cash difference as a causal estimate.

## Corrections to the earlier diagnosis

**Wheat quantity alone is not the problem.** Boey maintains about 21.5 wheat plots alongside 33.75 strawberry plots at day 20. V13's corresponding averages were about 17.8 wheat and 3.7 strawberry plots. The stronger diagnosis is insufficient productive occupancy and crop scheduling, particularly early establishment of a much larger strawberry crop. Removing wheat indiscriminately could damage feeding and production.

**Age-10 melon harvesting can be correct.** The engine instrumentation records 43 successful Boey melon harvests: every one at age 10, every one yielding six units. V13 often harvested below six at that age. Care and fertilizer timing, combined with a decision based on actual yield, deserve testing; a blanket rule to wait until age 12 is not supported by these games. The replay evidence establishes the outcome, not the unseen policy's internal decision rule.

**Raw sales are not farm production.** Boey repeatedly buys and sells wheat and fertilizer, including both wheat actions in the same turn. In the first game, wheat sales were 202,207 but purchases were 187,086: the difference is 15,121 before other costs. Wheat sold totaled 5,792 units, while actual wheat harvested was 878 units. Across four games, wheat sales minus purchases averaged 13,756.75 and fertilizer sales minus purchases averaged 13,548.25. These amounts combine farm output, feeding, inventory and market transactions; they are not isolated arbitrage profit. Market behavior needs an ablation before copying it.

**Action allocation warrants investigation.** Boey averages roughly 3,172 move commands versus V13's 4,213, and 505 harvest commands versus 270, with similar worker limits. This supports investigating routing and job allocation. Commands are not all successful actions, and this descriptive comparison does not prove a routing advantage by itself.

The observed season progresses from an early melon crop to dense strawberries and then more wheat and short-duration crops late. That is consistent with planning around the remaining season, but replays cannot reveal the underlying algorithm or training method.

## How to evaluate the fourth quadrant

Keep both three- and four-quadrant policies in the search. Evaluate expansion together with planting, worker allocation, routing and the time remaining to recover land, seed and labor costs. Buying land without filling and servicing it is a different policy from productive expansion.

Use paired seeds, both seats and the same opponent pool to compare: the current V13 baseline; improved production scheduling with three quadrants; and that scheduling with a conditional fourth-quadrant purchase. Report final cash and margins, purchase timing, productive tile-hours, worker costs and realized harvests. Tune each expansion policy sufficiently to avoid giving the fourth quadrant an unsuitable three-quadrant staffing plan.

Boey also walks units through the unowned southeast quadrant. Passage through it is not evidence of owning it or earning production there.

## Implications for V9 and the next challenger

Because these are examples of the play style V9 was primarily trained against, they are useful regression scenarios. They do not prove V9 reproduced that style. Compare V9 and V13 directly on expansion timing, occupancy, strawberry establishment, melon yield and worker travel under matched games.

Prioritize coordinated planting and job scheduling, timely crop care, and season-aware crop replacement. Preserve fourth-quadrant expansion as a tested option. Evaluate market transactions separately so gross turnover does not disguise production results.

No policy was changed, no training run was launched, and no Kaggle submission was made during this analysis.

Supporting files: `reconstructed_games.json` (verified ledgers), `patterns.json` (daily states and expansion observations), `boey_season_summary.json`, and `leader_production_comparison.png`.
