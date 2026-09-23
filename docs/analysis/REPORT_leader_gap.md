---
title: Why we are losing: we leave our own land empty
---

# Why we are losing: we leave our own land empty

Measured 2026-09-23 from 35 real Kaggle replays. Supersedes the "leader profile"
section of `REPORT_deployment_diagnosis.md`, which was built on the wrong games.

## 0. We had been studying the wrong opponents

Kaggle matches simulation episodes on rating. Our agents sit near 620, so every
opponent we have ever recorded sits near 620 too. Checked directly: across **233
distinct opponents** in our entire episode history, **zero** appear in the leaderboard
top 20.

Every replay behind the earlier diagnosis was therefore mid-field play beating
mid-field play, and `agents/main_leader.py` — the "leader-style" opponent the whole
promotion gate has been tuned against — was reconstructed from those same ~620-rated
opponents. That explains the pattern that kept repeating: candidates cleared 75–81%
against `main_leader` and then won ~46–53% of real games. The gate was not lying, it
was answering a different question.

Reaching the real leaders needed a different route. `ListEpisodes` only accepts a
`submissionId` (a `teamId` payload returns 400), but its response carries every
involved team's `publicLeaderboardSubmissionId`, and every episode exposes both
agents' Elo. So a best-first crawl over the episode graph, always expanding the
highest-rated agent seen, reaches the top of the table in **two API calls**
(`tools/find_top_submissions.py`).

Reference opponent used below: **Majkel1337**, rank 2, leaderboard 3065.7,
submission `56459657` — 161 episodes, **130/160 wins**, mean cash **111,679** against
opponents' 98,725. Our three most recent submissions average ~78,000.

## 1. The dominant gap

Means per game. Ours = 10 worst losses from each of the last three submissions;
leader = 5 wins by Majkel1337.

| metric | **leader** | ours (early_cash_bias) | V14 | V15-search |
|---|---:|---:|---:|---:|
| **bare owned tiles, day 12** | **0.0** | 32.7 | 33.2 | 40.1 |
| bare owned tiles, day 7 | **0.0** | 16.6 | 16.6 | 17.8 |
| bare owned tiles, day 25 | **1.2** | 24.3 | 20.8 | 23.2 |
| productive tiles, day 10 | **74.6** | 36.4 | 32.7 | 32.6 |
| productive tiles, day 20 | **73.8** | 52.6 | 53.6 | 50.1 |
| crops, day 10 | **57.2** | 21.4 | 18.6 | 17.6 |
| animals, day 10 | 17.4 | 15.0 | 14.1 | 15.0 |
| hands, day 20 | 11.6 | 12.0 | 12.0 | 11.0 |

**The leader ends every single day with zero bare owned tiles.** We carry 20–40 bare
tiles from day 7 to the end of the game. Animal counts and hand counts are already
comparable — the entire productive-tile deficit is **crops**: 57 vs ~19 at day 10.

Note also that our crop count *falls* between day 7 and day 10 (V14: 23.6 → 18.6). We
harvest and then leave the tile bare.

## 2. What the hands are doing instead

Whole-game action counts, mean per game:

| action | **leader** | ours (ecb) | V14 | V15 |
|---|---:|---:|---:|---:|
| PLANT | **275** | 104 | 104 | 99 |
| **PASS (idle)** | **94** | 455 | 370 | 393 |
| WATER | 1274 | 793 | 764 | 677 |
| HARVEST | 512 | 302 | 292 | 292 |
| COLLECT_FERTILIZER | 430 | 249 | 221 | 253 |
| FERTILIZE | 186 | 75 | 59 | 64 |
| movement (N+S+E+W) | **3,216** | 4,372 | 4,172 | 4,161 |

We **move 30% more and idle 4–5× more** while 20–40 of our own tiles sit empty. This
is not a worker-capacity problem — we field *more* hands than the leader by day 20.

## 3. The market consequence

Units traded, mean per game:

| | **leader** | ours (ecb) | V14 | V15 |
|---|---:|---:|---:|---:|
| SELL wheat | **409** | 103 | 88 | 101 |
| SELL carrot | **222** | 20 | 22 | 27 |
| BUY_SEED wheat | **154** | 57 | 53 | 57 |
| BUY_SEED carrot | **78** | 6 | 11 | 10 |
| BUY_PRODUCT wheat | 235 | 264 | 262 | 314 |

The leader runs a high-throughput short-cycle economy: buy cheap wheat/carrot seed,
fill every tile, sell the output. We **buy more wheat than we sell** — wheat is only a
feed input for us, never a crop business.

## 4. Root causes in the code

Two, both in `policy/policy_template.py`, both now parameterised and off by default.

**(a) A bare tile loses the per-unit auction.** Each unit takes only its single
highest-scoring offer. A PLANT bid is `max(plant_floor, crop_score)` ≈ 40–133, against
WATER at `95 + hour*4 + 120*consecutive_unwatered` and FEED at `190 + …`. Planting
loses nearly every turn, so bare tiles stay bare while hands maintain what is already
planted. → `plant_urgency` (default 1.0 = unchanged) scales the bare-tile bid.

**(b) A flat seed stock cannot fill land.** Seed buying topped every crop up to
`seed_stock` (default **2**) regardless of how much ground stood empty, so planting
was throttled to a trickle. This also explains the earlier finding that raising
`seed_stock` 2→6 *hurt*: it bought 6 of **everything**, so ~600 cash of strawberry
seed and ~480 of melon seed starved the very expansion it was meant to feed, while the
cheap crops that actually fill tiles (WHEAT 10, CARROT 20) stayed capped at 6. The
lever was never wrong, its shape was. → `seed_fill` (default 0 = unchanged) buys
against the count of bare tiles, cheapest value-per-cash first.

## 5. Three attempted fixes, all measured, all failed

| round | config | v9 | v12 | main_leader | day-10 bare | day-10 cash | day-10 hands | day-10 weeds |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| baseline V14 | `strawberry_target=30` | ~100% | ~94% | 33–45% | ~32 | ~900 | 9 | 0 |
| 1 | `+plant_urgency 2.5, seed_fill 12` | 79.2% | 85.4% | **6.2%** | 18.3 | 1,159 | — | 0 |
| 2 | `+tiles_per_unit 7, hire_pace 1, survival_bias 1, distance_weight .85`, urgency 2.0 | 56.2% | 68.8% | **8.3%** | 28.4 | 2,075 | 12 | 0 |
| 3 | urgency **6.0** | **0%** | **0%** | **0%** | **4.9** | **2.7** | **0** | **7.1** |

Round 3 is the informative one. Bidding 240 for a bare tile **did** fill the land —
bare fell from 21–28 to 4.9, exactly as the auction arithmetic predicted. And it lost
every game.

**Land was never the binding constraint.** The system is a closed cash loop:

> seed costs cash → cash buys hands → hands water → watering keeps crops alive →
> crops produce income → income buys seed

Round 3 spent the bank on seed (cash → **2.7**), so it hired **zero hands**, so
nothing was watered, so crops died (weeds 0 → **7.1**), so income never started.
Optimising one link broke the loop.

Two of my own explanations were falsified by measurement along the way, which is worth
recording so they are not re-proposed:

* *"planting past watering throughput kills crops"* — false at rounds 1–2: weeds were
  **0** at day 10 and 1–2 at day 20. Nothing was withering; planting simply was not
  happening. It only became true at round 3, once hands hit zero.
* *"the leader maximises planting"* — false. They hold a **constant 6.3–6.8 productive
  tiles per hand** all game and raise the ceiling by hiring, not by over-planting.

## 6. What the leader's early game actually is

Their cash stays deliberately **low** through day 7 — 139 (d3), 338 (d5), 299 (d7) —
and then jumps to **6,876** by day 10. They are not accumulating; they are
recycling. The engine is short-cycle crops: WHEAT first-yields on day 2 and peaks on
day 4, so it can be harvested, sold and replanted three times before a melon yields
once. Over a game they sell **409 wheat and 222 carrot units** to our ~100 and ~22.

Our `crop_value` cannot see this. It scores value per tile-turn — melon rates 133
against wheat's 17 — and is blind to *when* the cash arrives. So we plant the slow
high-value crops and have no income at all before day 10, which is precisely the
window in which the leader funds three quadrants, eleven hands and eighteen animals.
`early_cash_bias` (2026-09-22) was aimed at this and was too weak to matter: melon's
raw score is ~4× wheat's, and the bias never overturns it.

## 7. Where this leaves us

Hand-picked configurations have now failed on this system four times running
(`land=4`, `survival_bias` alone, `early_cash_bias`, and rounds 1–3 above). The
parameters are strongly coupled — that is the finding — and coupled systems are what
the TPE search exists for. The search space now carries the new levers
(`plant_urgency`, `seed_fill`, `early_cash_bias`) alongside `tiles_per_unit`,
`hire_pace`, `crop_style` and `land_deadline`, so the next honest step is a search
over that space rather than a fifth guess.

`agents/main_leader2.py` is **not** yet a credible leader stand-in: every candidate
tried beats it 98–100%, including the round-3 config that wins 0% against everything
else. Its win rate currently carries no information, so it is deliberately not a gate
condition (floor 0.0) until it can lose to something.

## 8. Standing caution

Everything above is measured. This project has now twice mistaken an internal gate
result for a leaderboard result (V15: 81.2% gate → 52.8% real; `early_cash_bias`:
75–79% gate → 46% real). Only the leaderboard settles it.
