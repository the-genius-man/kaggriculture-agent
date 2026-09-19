# Deployment diagnosis: where the agent actually stands, and why

Measured 2026-09-18/19 against the live competition and the pinned engine
(`kaggle-environments==1.32.7`). Everything below is a measurement or a quote from
engine source; nothing is inferred from internal league results alone.

## 1. Standing: below the median of the field

Full public leaderboard download (9,462 teams, 2026-09-18T19:16Z):

| | |
|---|---:|
| Our rank | **5,499 / 9,462** |
| Our score | 645.3 |
| Field median | 780.5 |
| Leader (Majkel1337) | 3,205.2 |

We are in the bottom 42%, not near the front. The gap to the leader is ~2,560 points.

## 2. The rating is noisier than the differences we tune on

`main_v12.py` read four times in one afternoon, unchanged:

| 16:5x | 17:13 | 17:2x | 19:1x |
|---:|---:|---:|---:|
| 626.5 | 679.0 | 656.8 | 617.7 |

That is a ±60 swing on a fixed agent. The entire spread across every version we have
shipped — V11 586.6, V13 599.6, V9 612.0, V12 617.7, V14 645.3 — fits inside that
band. **At our submission volume, no single submission can tell us whether a change
helped.** A freshly submitted agent also sits at exactly 600.0 (the unplayed initial
rating) for some time: V14 read 600.0 at 17:2x and 645.3 by 19:1x. Comparing a fresh
submission against a settled one measures nothing.

## 3. Two engine mechanics drive every production failure

From `kaggriculture.py` (not the env README, whose crop table disagrees with the code):

```
one-time crops gain yield ONLY from the WATER action, inside the age window
    [(max_yield_day+1)//2, max_yield_day]     +1 per watered day, +2 if fertilized
two consecutive unwatered days  ->  the tile becomes a WEED (crop destroyed)
```

Yield does not accrue passively. An unwatered plant is not a slow plant, it is a
dead plant in two days.

## 4. Measured production gaps (2 seeds/agent vs V9 — directional, not definitive)

| day 20 | owned tiles | productive | % of owned |
|---|---:|---:|---:|
| V12 | 50 | 45.5 | 91% |
| V14 | 75 | 51.5 | 69% |
| Leader profile (Boey replays) | 75 | **74.75 — by day 10** | 99.7% |

**Two different land failures.** V12 is configured `'land': 2` — hard-capped at 50
tiles, half the leaders' farm. It fills that land well and still cannot compete on
volume. V14 raised it to 3 and owns 75, but fills only 69%.

**The ramp, not the ceiling, is the gap.** The leaders are fully productive on day
10. V14 has 33 productive tiles on day 10 and 51.5 on day 20, and never arrives.
Most of the season is played on a half-built farm.

**Crops die of thirst.** V14 loses 8.0 strawberries per game to dry-out — the
100-cost seed, our most expensive, is our most common casualty. Unwatered-at-day-end
rises with occupancy (3 on day 20, 6 on day 29).

**Melons finish a unit short.** Yield units when the tile cleared:

| | 4 | 5 | 6 |
|---|---:|---:|---:|
| V12 | 1 | 17 | 1 |
| V14 | 0 | 19 | 4 |
| Leader replays | 0 | 0 | 43 |

Reaching 6 unfertilized needs 6 waterings in the 7-day window; fertilized needs 3.
This is watering coverage and fertilizer, **not harvest age**. V14's 10 -> 12 maturity
change does match the engine, but it buys the missing unit by holding the tile two
extra days rather than fertilizing.

**Late-game collapse.** Productive tiles crater from day 25 to 29 (V14 52 -> 22 with
8.5 weeds; V12 37.5 -> 10.5). The leaders still hold 70.25 on day 25.

## 5. The policy-level defect

`policy_template.py` prices a watering job at `95 + hour*4 + 120*consecutive_unwatered`
— about 215 for a plant that dies tonight — while a nearby harvest offers
`100 + yield_units*price*0.55`, about 364 for a ripe strawberry, and the score is
then divided by distance. Losing a strawberry costs its 100 seed plus roughly 480 of
future yield. **Survival watering is underpriced by about an order of magnitude**, so
the agent rationally walks past dying crops.

## 6. What is NOT the problem

- **Turn timeout.** `actTimeout` is 1s; we peak at 0.075s (V12) and 0.105s (V14).
- **Worker ceiling.** V14 reaches 12 hands; the leaders run 11–12.
- **Seed stocking.** Raising the seed stock from 2 to 6 *lowered* day-10 occupancy
  (31.5 -> 24) and day-10 cash (880 -> 320). Buying seeds in bulk starves expansion.

## 7. The real early-game constraint: cash

At day 10 our agents hold 320–880 cash. The leader profile has bought two extra
quadrants (3,000) and planted ~50 tiles by then, of which ~28 are 100-cost
strawberries. That is on the order of 6,000 spent from a 3,000 start, so the leaders
are **funding expansion out of early revenue** — short-cycle wheat, animal products
from day 4 (eggs), and the wheat/fertilizer market churn noted in
`REPORT_boey_leaders.md`. Our agents reach day 10 with an empty bank and therefore
cannot fill the land they own.

Ordering the levers by what the measurements support:

1. **Early cash generation, days 1–10.** This gates occupancy, which gates everything.
2. **Survival-priced watering** and **fertilizer inside the yield window** (both
   demonstrated below).
3. **Late-game production collapse** from day 25.
4. Routing/job allocation — still open, unmeasured here.

## 8. `agents/main_leader.py`: a leader-style opponent

Built to give the league an opponent that is not our own lineage. It reproduces the
*measured behavioural profile* of the strongest observed leaderboard player; it is
**not** a reconstruction of that player's policy, which is unknown. Three changes
over V14: survival-priced watering, fertilizer from the start of the yield window,
and planting capped by watering throughput.

Measured effect (same 2 seeds vs V9):

| | V14 | main_leader |
|---|---:|---:|
| Melons at max yield (6) | 4 / 23 (17%) | **24 / 28 (86%)** |
| Strawberries lost to dry-out | 8.0 | **4.0** |
| Third quadrant owned by | day 15 | **day 10** |
| Day-20 productive tiles | 51.5 | 45.0 |
| Mean final cash | 84,101 | 72,263 |

The mechanism changes work exactly as the engine predicts.

### Head-to-head (8 fresh seeds, both seats, 16 games per opponent)

| main_leader vs | win rate | mean margin | margin CI90 | its cash | rival cash |
|---|---:|---:|---:|---:|---:|
| V14 | 62.5% | +1,091 | **[-55, 2,142]** | 83,720 | 82,629 |
| V12 | 62.5% | +2,030 | [261, 4,081] | 68,317 | 66,286 |
| V9 | 100% | +9,798 | [7,021, 12,771] | 77,385 | 67,587 |

Paired head-to-head puts it **at V14's level, not below it**. The table above compares
each agent against V9 on two seeds, which is a much weaker comparison and gave the
opposite impression.

### Kaggle-kernel holdout: 24 fresh seeds, both seats (48 games per opponent)

Run on the Kaggle kernel 2026-09-19, candidate = V14 rendered from `candidate.json`:

| V14 candidate vs | win rate | required | mean margin | margin CI90 | verdict |
|---|---:|---:|---:|---:|---|
| V9 | 100% | >= 80% | +11,167 | — | pass |
| V12 | 93.8% | >= 60% | +10,290 | [7,954, 12,798] | pass |
| V13 | — | >= 55% | — | — | **skipped, file absent** |
| **main_leader** | **33.3%** | >= 55% | **-2,400** | **[-4,410, -549]** | **fail** |

`gate_pass: false`.

### Correction: how much better is main_leader, really?

A second independent sample (12 fresh seeds, both seats, seed base 96000000) put V14
at **45.8%** against main_leader, margin +234, not 33.3%. Pooling both samples:

| sample | seed base | games | V14 wins |
|---|---|---:|---:|
| kernel holdout | 40000000 | 48 | 33.3% |
| local sweep | 96000000 | 24 | 45.8% |
| **pooled** | | **72** | **37.5%** (95% CI 26.3-48.7%) |

So main_leader is better than V14, but "loses two games in three" overstated it on one
seed set. Even 48 games does not pin this down to better than about +/-13 points.

### V15 search: no variant beat V14 (24 paired games each, seed base 96000000)

| config | win vs leader | margin | CI90 | own cash |
|---|---:|---:|---|---:|
| **V14 (control)** | 45.8% | **+234** | [-1831, +2095] | **83,856** |
| fert_bias 1.6 only | 54.2% | +515 | [-1606, +2818] | 77,714 |
| all 3 mechanics + fert 1.6 | 50.0% | -269 | [-2781, +2382] | 68,697 |
| all 3 + fert 1.6 + expansion | 50.0% | -13 | [-1964, +1996] | 70,182 |
| all 3 + fert 2.0 | 41.7% | -1,629 | [-3351, +42] | 69,632 |
| fert 1.6 + window, no cap | **4.2%** | -8,355 | [-11622, -5377] | 80,113 |

**Every margin interval straddles zero: nothing here is a measured improvement.** The
apparent sweep-1 winner (56.2% on 8 seeds) regressed to 50.0% on 24 games -- ordinary
small-sample selection. Two things are nonetheless real:

- **The mechanics interact strongly and are not independently good.** Alone, each
  *hurts*: survival_bias 6.2%, fert_in_window 6.2%, tiles_per_unit 18.8%. Opening the
  fertilizer window without the planting cap is catastrophic (4.2%) -- the agent
  fertilizes crops it then fails to water.
- **Configs that raise win rate lower cash.** The variants reach ~50% while earning
  68-78k against V14's 83.9k. They win marginal games and lose the big ones, which is
  the wrong trade when the leaderboard rewards cash.

Conclusion: hand-picked configs are not finding V15. The parameters now exist in the
template; finding a setting that genuinely beats main_leader is a job for the Optuna
search on the kernel, with main_leader in the opponent pool, not for eight hand
guesses at 16 games apiece.

`main_leader` has **not** been run through the gate as a *candidate*, which is the
next step: it would need >= 80% vs V9, >= 60% vs V12 and >= 55% vs every league
opponent on its own 24-seed holdout.

It is nonetheless **not a promotion candidate**: against V14 the margin's 90% interval
includes zero, so the gate's positive-lower-bound requirement fails, and 8 seeds is
below the 24-seed holdout the gate requires. It is committed as a league *opponent* —
its value is being a play style that is not our own lineage.

## Honesty notes

- Local games are against V9/V12/V14, not leaderboard opponents. Internal results
  have not transferred: V13 passed the internal gate and scored below V9 externally,
  and a v5 agent that beat v4 39/40 head-to-head scored 523.7.
- Occupancy and death counts are 2 seeds per agent. They are consistent and
  mechanically explained, but they are not a 24-seed holdout.
- The leader-profile column comes from four selected replays of one player
  (`REPORT_boey_leaders.md`), not from a rank-verified sample.
