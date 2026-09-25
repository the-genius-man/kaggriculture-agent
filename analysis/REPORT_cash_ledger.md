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
