# Where the leaders' extra 50,000 comes from: an exact cash ledger

Measured 2026-09-25. Tool: `tools/money_ledger.py` (new). It re-runs each real replay
through the pinned engine from its recorded actions, with every cash and tile mutator
wrapped, so each sale, purchase, hire, harvest, dry-out, rot and shed overflow is
logged per seat as it happens. **All 95 real replays re-simulated to the exact final
cash** recorded by Kaggle, so these are ledgers, not estimates.

## Data

| group | games | source | caveat |
|---|---:|---|---|
| **DECEM** (3012.8, top 5) | 20 | real, submission 56526629 | best **wins** only; opponents rated 440-800 |
| **Majkel1337** (rank 2 on 09-23) | 5 | real, submission 56459657 | best wins only |
| v17 real | 12 | real, 8 worst losses + 4 best wins | |
| v16 real | 12 | real, 8 worst losses + 4 best wins | |
| v17 local | 6 | local, v17 vs v16, seeds 97100000+7919k | |

Leader samples are wins, so they overstate the leaders' average (Majkel's 161-game
mean is 111,679, not 135,625). The mechanisms below are large enough that this does
not change the conclusions, but the absolute cash targets should come from the
111k figure.

**Local v17 reproduces real v17 closely** (final cash 88.2k vs 83.3k; day-10 crops
30.3 vs 28.2; wheat 2.98 vs 3.05 units per harvest; day-20 strawberries 28 vs 26), so
the production gap can be worked on locally with this tool, without spending
submissions.

## 1. It is not a leak

| lost before sale (base-price value) | DECEM | Majkel | v17 real | v16 real |
|---|---:|---:|---:|---:|
| dry-out + rot + shed overflow | 1,784 | 1,637 | 972 | 183 |

The leaders lose **more** production than we do. Dry-out deaths, rot, animal escapes
and shed overflow are all under 2% of revenue for everyone. Spend is also the same
(~31k for us and Majkel, 38.6k for DECEM), and so is total labour (~7,100-7,500
unit-turns). The whole gap is **revenue**: 165-173k against 111-114k.

## 2. The gap is days 10-19, and it is decided by day 8

| revenue | DECEM | Majkel | v17 real | v16 real |
|---|---:|---:|---:|---:|
| days 0-9 | 14,119 | 14,653 | 7,949 | 8,317 |
| **days 10-19** | **78,851** | **74,213** | **40,546** | **42,484** |
| days 20-29 | 79,734 | 75,637 | 62,772 | 63,189 |

About two thirds of the revenue gap is days 10-19. What the leaders have in the
ground by then:

| | DECEM | Majkel | v17 real | v16 real |
|---|---:|---:|---:|---:|
| **strawberries, day 7** | **19** | **23** | **0** | **0** |
| strawberries, day 10 | 22 | 26 | 1 | 0 |
| crops, day 10 | 60.0 | 57.2 | 28.2 | 32.1 |
| animals, day 10 | 21 | 17 | 13 | 12 |
| 3rd quadrant bought (day) | 9.0 | 8.0 | 14.2 | never |
| quadrants, day 10 | **4.0** | 3.0 | 2.0 | 1.9 |

Strawberries first yield at age 10, so a crop planted on day 6 pays out on days 16-22,
exactly the window where the leaders pull ahead. Ours go in on days 10-13 and pay out
on days 20-28. The number of strawberries we plant is fine (26-28 per game for v17 and
the leaders alike). **They are planted about 7 days too late.** DECEM also owns
**all four quadrants by day 10**, which is worth noting against the 09-20 finding that
land=4 lost as a standalone lever: the leader's version buys it early and fills it.

Cash on hand is **not** what separates the leaders in days 0-9. Their bank is as empty
as ours (d3: 20-139, d7: ~300, ours 76-233). They spend exactly the same 3,000 on
day 0. The difference is what that spending buys, and when.

Majkel's day 6 shows how it is funded: **4,601 revenue in a single day, spent the same
day (4,787)** on 17 strawberries, the 2nd quadrant and 5 animals. The ledger does not
yet split revenue by item and day, so what was sold in that burst is still open.
It is the next thing to measure.

## 3. Short-cycle crops: harvested one day earlier, fertilized, twice the throughput

| | DECEM | Majkel | v17 real | v16 real |
|---|---:|---:|---:|---:|
| wheat: units per harvest | **4.39** | **4.10** | 3.05 | 3.44 |
| wheat: mean age at harvest (days) | **3.17** | **3.06** | 3.94 | 3.98 |
| carrot: units per harvest | 3.22 | 3.13 | 2.23 | 2.64 |
| wheat + carrot planted | 226 | 224 | 122 | 103 |
| FERTILIZE actions | **234** | **186** | 42 | 74 |
| revenue, wheat + carrot + tomato | 35,901 | 36,121 | 8,277 | 9,842 |

Wheat is watered for yield on ages 2, 3 and 4 (+1 each, **+2 if fertilized**) starting
from 1 unit. Fertilized, it reaches 5 at age 3. The leaders harvest at age 3 with 4.4
units. We wait until age 4 and still get 3.0, one watering short even of the
unfertilized maximum of 4. Per tile-day that is **1.39 wheat vs 0.76, 1.8×**, before
counting that they plant twice as many.

We collect fertilizer from animals and mostly **sell** it (9-12k revenue at ~60/unit).
The leaders sell a similar amount *and* spread 186-234 units on crops. One fertilizer
unit covers 3 days, i.e. two +1 waterings on wheat (~2 × 42) or a doubled strawberry
production (~160-240), so on crops it is worth more than its ~60 sale price.

## 4. Routing: same labour, a quarter less walking

| | DECEM | Majkel | v17 real | v16 real |
|---|---:|---:|---:|---:|
| unit-turns | 7,496 | 7,180 | 7,102 | 7,882 |
| MOVE | 3,004 | 3,216 | 4,177 | 4,640 |
| PASS | 371 | 94 | 425 | 799 |

Also: **v17 fields zero hands on day 1** (it spends to ~3 cash on day 0; hands expire
every night and must be re-hired). Both leaders keep enough back to hire 4 on day 1.

## What this says to build, in order of measured size

1. **Strawberry block planted by day 6-7** (≈20 plants), funded the way the leaders
   fund it. Biggest single effect: it moves ~20 strawberries' output into days 16-22.
   Needs the day-6 funding mechanism measured first (next ledger extension).
2. **Wheat/carrot harvest rule: harvest at age 3, fertilize them, never skip the
   in-window watering.** A rule, not a weight: it is what the engine pays for.
3. **Fertilizer on crops, not to market,** while crops are in their window.
4. **3rd quadrant by day 8-9** and fill it with the short-cycle engine (1+2 supply the
   cash for it).
5. Keep a day-1 hiring reserve. Small and free.

The internal gate should be told about this directly: score candidates on **revenue in
days 10-19** and **strawberries in the ground on day 7**, alongside wins. These are the
two numbers that separate a 3000-rated agent from ours, and neither depends on who the
opponent is.

## 5. First attempt at the fixes, screened locally (2026-09-25)

Each lever was added to `policy/policy_template.py` off by default (rendering v17's
config reproduces v17 byte for byte and move for move), then screened with
`experiments/screen_ledger.py`: v17 + overrides vs v16, paired seeds, both seats.

| variant (on v17) | games | win vs v16 | margin | own final cash | strawb d7 | milk rev |
|---|---:|---:|---:|---:|---:|---:|
| v17 | 16 / 16 | 44% / 25% | -873 / -2,789 | 87.8k / 92.8k | 0 | 29-37k |
| `short_harvest` + fert window + carry 12 | 16 / 16 | **75% / 75%** | **+10,969 / +14,193** | 92.2k / 91.1k | 0 | 34k |
| + fert_bias 2.5 | 16 | 56% | -1,760 | 82.8k | 0 | 30k |
| opening (3 sheep + 2 cows, reserve 60) | 16 | 25% | -3,812 | 81.5k | 0 | — |
| strawberry rush 22 by day 8 | 16 / 12 | 0% / 0% | -15,098 / -11,985 | 72.7k / 70.0k | 17 | 19k |
| all of the above | 16 / 12 | 25% / 33% | -4,640 / -3,518 | 76.1k / 70.5k | 22 | 13k |

(Two numbers = two independent seed sets, bases 97100000 and 97300000.)

What this shows:

* **Copying the leaders' inputs does not copy their economy.** The rush put 22
  strawberries in the ground by day 7, as the leaders do, and lost every game: the
  seed money came out of animal buying (day-10 animals 13 -> 8, milk revenue 29k ->
  19k), and the extra strawberries sold ~15% cheaper. The leaders afford both because
  their days 0-9 revenue is 14k to our 7-9k. **We have not yet reproduced that.**
* `short_harvest` is the only lever that wins, and it wins on **margin, not cash**:
  our own final cash is flat vs v17 while v16's falls. It works through the shared
  market, so it says less about the leaderboard than its win rate suggests.
* Raising the fertilizer bid did not raise fertilizer use (64 -> 64 actions). The
  binding limit is collection (leaders 430 a game, us 170-270), not priority.
* All six levers are now in the search space (`league/league.py` FOCUS, 18 dims),
  because they are coupled on the cash loop and every hand pick here, like every hand
  pick before it, broke a different link.
