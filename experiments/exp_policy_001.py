"""Screen policy_001 strategies against V12.

Internal league signal only. Does not write main.py and does not submit.
V5 tapes are not in the pool.

  python experiments/exp_policy_001.py
"""
from __future__ import annotations

import concurrent.futures
import contextlib
import importlib.util
import io
import json
import multiprocessing
import statistics
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POLICY = ROOT / "policy" / "policy_001.py"
V12 = ROOT / "agents" / "main_v12.py"
V9 = ROOT / "agents" / "main_v9.py"
OUT = ROOT / "experiments" / "_tmp_policy001"
SCREEN_SEEDS = [30100100 + i for i in range(3)]
CONFIRM_SEEDS = [30100200 + i for i in range(6)]

DEFAULTS = dict(
    animals=18, hands=12, land=3, crop_bias=1.5, care_bias=1.1, fert_bias=1.1,
    opponent_weight=0.0, liquidate=True, drop_units=4, drop_value=1000000,
    cash_release=True, deposit_bias=0.35, feed_fix=True, care_cap=1.3,
    plant_floor=70, hire_pace=1, workload_hiring=False, work_per_hand=8,
    keep_late_hands=True, land_util=0.88, land_buffer=700,
    commitment=1.3, region_weight=0.8, distance_weight=0.55, dig_value=75,
    animal_deadline=12, land_deadline=12, expansion_hands=8, night_deposit=True,
    late_day=22, crop_bias_late=1.6, plant_floor_late=50, deposit_bias_late=0.4,
    strawberry_target=28, occupancy_push=160, melon_cap=10, seed_buffer=8,
    hire_base=6, melon_open_days=10, fill_frac=0.95, crop_style="balanced",
    animal_style="balanced", mid_day=12, crop_bias_mid=1.5, plant_floor_mid=70,
    deposit_bias_mid=0.35, care_bias_mid=1.1, water_relax_hour=16,
    care_when_filling=0.2, seed_focus=2, wheat_open=5, wheat_open_days=8,
    open_cash_floor=400, animal_reserve=250, animal_slot_cap=3,
)

STRATEGIES = {
    "fill_core": {},
    "boey_season": dict(
        crop_style="melon_open", melon_cap=11, melon_open_days=8,
        strawberry_target=32, animals=18, occupancy_push=180, hire_base=6,
        land=3, land_util=0.9, plant_floor=80,
    ),
    "straw_wall": dict(
        crop_style="orchard", strawberry_target=36, melon_cap=6,
        occupancy_push=180, plant_floor=80, animals=16,
    ),
    "livestock": dict(
        animals=22, animal_style="milk", strawberry_target=20, occupancy_push=120,
        seed_buffer=6, land_util=0.85, care_when_filling=0.5,
    ),
    "two_quad_dense": dict(
        land=2, hands=11, animals=14, strawberry_target=18, occupancy_push=180,
        land_util=0.9, hire_base=6, plant_floor=80,
    ),
    "fast_expand": dict(
        land_util=0.7, land_deadline=10, occupancy_push=140, hire_base=7,
        expansion_hands=7, strawberry_target=24, plant_floor=70,
    ),
}

# Round 2: cash-efficiency variants after occupancy filled but still lost EV to V12.
ROUND2 = {
    "v12_mirror": dict(
        animals=10, hands=9, land=2, crop_bias=1.674270690403267,
        care_bias=0.7224837832484434, fert_bias=1.3793708390542747,
        drop_units=3, deposit_bias=0.5561745205917409, feed_fix=False,
        plant_floor=60, work_per_hand=6, land_util=0.35, occupancy_push=0,
        strawberry_target=0, hire_base=4, seed_buffer=2, seed_focus=5,
        wheat_open=0, wheat_open_days=0, night_deposit=False, fill_frac=0,
        care_when_filling=1.0, water_relax_hour=0, animal_slot_cap=0,
        open_cash_floor=80, animal_reserve=200, melon_cap=99, land_deadline=18,
        animal_deadline=12, expansion_hands=1, plant_floor_late=60,
        plant_floor_mid=60, crop_bias_late=1.674270690403267,
        crop_bias_mid=1.674270690403267, crop_style="balanced",
    ),
    "v12_plus_fill": dict(
        animals=10, hands=9, land=2, crop_bias=1.674270690403267,
        care_bias=0.7224837832484434, fert_bias=1.3793708390542747,
        drop_units=3, deposit_bias=0.5561745205917409, feed_fix=False,
        plant_floor=60, land_util=0.75, occupancy_push=100, strawberry_target=12,
        hire_base=4, seed_buffer=4, night_deposit=False, fill_frac=0.9,
        wheat_open=3, wheat_open_days=6, water_relax_hour=14, care_when_filling=0.4,
        land_deadline=18, melon_cap=10,
    ),
    "compact_fill": dict(
        land=2, hands=9, animals=12, occupancy_push=140, strawberry_target=16,
        melon_cap=10, land_util=0.85, hire_base=5, night_deposit=False,
        fill_frac=0.92, plant_floor=70, wheat_open=4,
    ),
    "boey_land2": dict(
        crop_style="melon_open", melon_cap=11, melon_open_days=8,
        strawberry_target=24, animals=16, occupancy_push=180, hire_base=6,
        land=2, land_util=0.9, plant_floor=80, night_deposit=False,
    ),
    "boey_straw18": dict(
        crop_style="melon_open", melon_cap=11, strawberry_target=18,
        occupancy_push=180, land=3, plant_floor=80, night_deposit=False,
        animals=18, hire_base=6, land_util=0.9,
    ),
    "melon_cash": dict(
        crop_style="melon_open", melon_cap=14, strawberry_target=12,
        land=2, animals=12, hands=10, occupancy_push=120, night_deposit=False,
        plant_floor=70, wheat_open=4, hire_base=5,
    ),
}


def render(params):
    cfg = dict(DEFAULTS, **params)
    return POLICY.read_text(encoding="utf-8").replace(
        "CFG = {}  # replaced by the trainer", "CFG = " + repr(cfg), 1
    )


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.agent


def _snap(farm):
    crops = {c: 0 for c in ("WHEAT", "CARROT", "MELON", "TOMATO", "STRAWBERRY")}
    animals = weeds = empty = locked = 0
    for row in farm.tiles:
        for t in row:
            if t == "LOCKED":
                locked += 1
            elif t is None:
                empty += 1
            elif isinstance(t, dict):
                if t.get("crop") in crops:
                    crops[t["crop"]] += 1
                elif t.get("animal"):
                    animals += 1
                elif t.get("kind") == "WEED":
                    weeds += 1
    return dict(
        crops=crops,
        animals=animals,
        weeds=weeds,
        empty=empty,
        productive=sum(crops.values()) + animals,
        quadrants=len(farm.unlocked_quadrants),
        hands=len(farm.hands),
        cash=farm.money,
    )


def play(job):
    cand, opp, seed, seat = job
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        from kaggle_environments import make
    A = _load(cand, "A")
    B = _load(opp, "B")
    env = make("kaggriculture", configuration={"seed": seed, "episodeSteps": 720})
    env.run([A, B] if seat == 0 else [B, A])
    final = env.steps[-1]
    cash = final[seat].reward
    rival = final[1 - seat].reward
    day5 = _snap(env.steps[min(5 * 24 + 23, 719)][seat].observation.farms[seat])
    day10 = _snap(env.steps[min(10 * 24 + 23, 719)][seat].observation.farms[seat])
    day20 = _snap(env.steps[min(20 * 24 + 23, 719)][seat].observation.farms[seat])
    return dict(
        seed=seed, seat=seat, cash=cash, rival=rival, win=cash > rival,
        margin=cash - rival, day5=day5, day10=day10, day20=day20,
    )


def summarise(rows):
    return dict(
        games=len(rows),
        win_rate=statistics.mean(r["win"] for r in rows),
        mean_margin=statistics.mean(r["margin"] for r in rows),
        min_margin=min(r["margin"] for r in rows),
        mean_cash=statistics.mean(r["cash"] for r in rows),
        day5_prod=statistics.mean(r["day5"]["productive"] for r in rows),
        day10_prod=statistics.mean(r["day10"]["productive"] for r in rows),
        day20_prod=statistics.mean(r["day20"]["productive"] for r in rows),
        day10_straw=statistics.mean(r["day10"]["crops"]["STRAWBERRY"] for r in rows),
        day20_straw=statistics.mean(r["day20"]["crops"]["STRAWBERRY"] for r in rows),
        day20_wheat=statistics.mean(r["day20"]["crops"]["WHEAT"] for r in rows),
        day10_empty=statistics.mean(r["day10"]["empty"] for r in rows),
        day20_weeds=statistics.mean(r["day20"]["weeds"] for r in rows),
    )


def eval_named(name, params, opponent, seeds, workers):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.py"
    path.write_text(render(params), encoding="utf-8")
    jobs = [(str(path), str(opponent), seed, seat) for seed in seeds for seat in (0, 1)]
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=workers, mp_context=multiprocessing.get_context("spawn")
    ) as pool:
        rows = list(pool.map(play, jobs))
    summary = summarise(rows)
    summary["name"] = name
    (OUT / f"{name}.json").write_text(json.dumps(dict(summary=summary, games=rows), indent=2), encoding="utf-8")
    return summary


def fmt(s):
    return (
        f"{s['name']:16s}  win={s['win_rate']:.2f}  margin={s['mean_margin']:+.0f}  "
        f"min={s['min_margin']:+.0f}  cash={s['mean_cash']:.0f}  "
        f"d5={s['day5_prod']:.0f} d10={s['day10_prod']:.0f} d20={s['day20_prod']:.0f}  "
        f"straw10={s['day10_straw']:.0f} straw20={s['day20_straw']:.0f} wheat20={s['day20_wheat']:.0f}  "
        f"empty10={s['day10_empty']:.0f} weeds20={s['day20_weeds']:.1f}"
    )


def main():
    import sys
    round2 = "--round2" in sys.argv
    strategies = ROUND2 if round2 else STRATEGIES
    report_name = "screen_report_r2.json" if round2 else "screen_report.json"
    workers = max(1, min(4, (multiprocessing.cpu_count() or 2)))
    print(f"policy_001 {'round2' if round2 else 'screen'} vs V12  seeds={SCREEN_SEEDS}  workers={workers}")
    print("internal league only; no main.py; no submission\n")
    t0 = time.perf_counter()
    screen = []
    for name, params in strategies.items():
        print(f"running {name}...", flush=True)
        s = eval_named(name, params, V12, SCREEN_SEEDS, workers)
        screen.append(s)
        print("  " + fmt(s), flush=True)
    screen.sort(key=lambda s: (s["win_rate"], s["mean_margin"]), reverse=True)
    print("\nScreen ranking:")
    for s in screen:
        print("  " + fmt(s))
    best = screen[0]
    confirm = None
    if best["win_rate"] >= 0.6 and best["mean_margin"] > 0:
        print(f"\nConfirming {best['name']} vs V12 on {len(CONFIRM_SEEDS)} fresh seeds, both seats...")
        confirm = eval_named(best["name"] + "_holdout", strategies[best["name"]], V12, CONFIRM_SEEDS, workers)
        print("  " + fmt(confirm), flush=True)
        print("\nAlso vs V9 on the same holdout seeds...")
        vs9 = eval_named(best["name"] + "_vs9", strategies[best["name"]], V9, CONFIRM_SEEDS, workers)
        print("  " + fmt(vs9), flush=True)
        confirm["vs_v9"] = vs9
    else:
        print("\nNo strategy cleared the screen bar (win_rate>=0.60 and positive mean margin). No main.py.")
    report = dict(
        opponent="main_v12.py",
        screen_seeds=SCREEN_SEEDS,
        confirm_seeds=CONFIRM_SEEDS,
        elapsed_s=round(time.perf_counter() - t0, 1),
        screen=screen,
        confirm=confirm,
        note="Internal self-play vs V12/V9. Not a leaderboard result. main.py not written.",
    )
    (OUT / report_name).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT / report_name} in {report['elapsed_s']}s")


if __name__ == "__main__":
    main()
