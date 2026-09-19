"""Screen V12-delta patches against V12. No main.py, no submit.

  python experiments/exp_v12_delta.py
"""
from __future__ import annotations

import concurrent.futures
import importlib.util
import json
import multiprocessing
import sys
import time
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "experiments"))
import exp_policy_001 as base  # noqa: E402

POLICY = ROOT / "policy" / "v12_delta.py"
OUT = ROOT / "experiments" / "_tmp_v12delta"
SCREEN_SEEDS = [30110100 + i for i in range(4)]
CONFIRM_SEEDS = [30110200 + i for i in range(8)]

V12_CFG = dict(
    animals=10, hands=9, land=2, crop_bias=1.674270690403267,
    care_bias=0.7224837832484434, fert_bias=1.3793708390542747,
    opponent_weight=0.0, liquidate=True, drop_units=3, drop_value=1000000,
    cash_release=True, deposit_bias=0.5561745205917409, feed_fix=False,
    care_cap=1.3, plant_floor=60, hire_pace=1, workload_hiring=False,
    work_per_hand=6, keep_late_hands=True, land_util=0.35, land_buffer=700,
    late_rotate=14, empty_ok=2, fill_push=80, water_relax_hour=18,
    sell_cap=6, seed_n=2, land_deadline=18,
)

STRATEGIES = {
    "quota_only": dict(fill_push=0, late_rotate=99, sell_cap=9, empty_ok=99, water_relax_hour=0),
    "quota_meter": dict(
        fill_push=0, late_rotate=99, sell_cap=9, empty_ok=99, water_relax_hour=0, meter=4,
    ),
    "fill2_gap": dict(
        fill_push=140, late_rotate=99, sell_cap=8, empty_ok=2, water_relax_hour=16,
        land=2, land_util=0.35, straw_drip=2, straw_drip_land=1, wheat_drip=1,
        drop_units=2, hands=10, plant_floor=70, meter=4, care_when_filling=0.35,
    ),
    "fill2_dense": dict(
        fill_push=140, late_rotate=99, sell_cap=8, empty_ok=2, water_relax_hour=16,
        land=2, land_util=0.88, land_min_day=3, straw_drip=2, drop_units=2,
        hands=11, plant_floor=70, meter=4, care_when_filling=0.35,
    ),
    "fill_then_q3": dict(
        fill_push=140, late_rotate=99, sell_cap=8, empty_ok=2, water_relax_hour=16,
        land=3, land_util=0.88, land_min_day=3, land_deadline=14, straw_drip=2,
        drop_units=2, hands=11, plant_floor=70, meter=4, care_when_filling=0.35,
    ),
    "late_q3": dict(
        fill_push=120, late_rotate=99, sell_cap=8, empty_ok=2, water_relax_hour=16,
        land=2, q3_day=10, land_util=0.85, land_min_day=4, straw_drip=2,
        wheat_drip=1, drop_units=2, hands=11, animals=14, meter=4, plant_floor=70,
        care_when_filling=0.35,
    ),
    "hold_straw": dict(
        fill_push=120, late_rotate=99, sell_cap=8, empty_ok=2, water_relax_hour=16,
        land=3, land_util=0.9, land_min_day=4, land_deadline=12, straw_drip=2,
        drop_units=2, hands=11, meter=2, straw_hold_day=14, plant_floor=75,
        care_when_filling=0.3,
    ),
    "sauls_pace": dict(
        fill_push=160, late_rotate=99, sell_cap=8, empty_ok=2, water_relax_hour=15,
        land=3, land_util=0.90, land_min_day=3, land_deadline=11, straw_drip=2,
        straw_drip_land=1, wheat_drip=1, drop_units=2, hands=12, animals=16,
        plant_floor=80, meter=4, hire_pace=1, care_when_filling=0.25,
    ),
}

ABLATION = {
    "quota_only": dict(fill_push=0, late_rotate=99, sell_cap=9, empty_ok=99, water_relax_hour=0),
    "quota_fert": dict(fill_push=0, late_rotate=99, sell_cap=9, empty_ok=99, water_relax_hour=0, fert_drip=1),
    "quota_sheep": dict(fill_push=0, late_rotate=99, sell_cap=9, empty_ok=99, water_relax_hour=0, sheep_burst=3),
    "gate_fert": dict(fill_push=0, late_rotate=99, sell_cap=9, empty_ok=99, water_relax_hour=0, fert_drip=1, sheep_burst=3),
    "majkel_time": dict(
        fill_push=60, late_rotate=14, sell_cap=8, empty_ok=2, water_relax_hour=16,
        fert_drip=1, sheep_burst=3, land=3, land_util=0.88, land_deadline=12,
        animals=16, hands=11, straw_drip=1, wheat_drip=1, seed_n=2,
    ),
}


def render(params):
    cfg = dict(V12_CFG, **params)
    return POLICY.read_text(encoding="utf-8").replace(
        "CFG = {}  # replaced by the trainer", "CFG = " + repr(cfg), 1
    )


def eval_named(name, params, opponent, seeds, workers):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.py"
    path.write_text(render(params), encoding="utf-8")
    jobs = [(str(path), str(opponent), seed, seat) for seed in seeds for seat in (0, 1)]
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=workers, mp_context=multiprocessing.get_context("spawn")
    ) as pool:
        rows = list(pool.map(base.play, jobs))
    summary = base.summarise(rows)
    summary["name"] = name
    summary["day10_quads"] = statistics.mean(r["day10"]["quadrants"] for r in rows)
    (OUT / f"{name}.json").write_text(json.dumps(dict(summary=summary, games=rows), indent=2), encoding="utf-8")
    return summary


def main():
    workers = max(1, min(4, (multiprocessing.cpu_count() or 2)))
    print(f"v12_delta screen vs V12  seeds={SCREEN_SEEDS}  workers={workers}", flush=True)
    t0 = time.perf_counter()
    screen = []
    for name, params in STRATEGIES.items():
        print(f"running {name}...", flush=True)
        s = eval_named(name, params, base.V12, SCREEN_SEEDS, workers)
        screen.append(s)
        print("  " + base.fmt(s) + f"  q10={s['day10_quads']:.1f}", flush=True)
    screen.sort(key=lambda s: (s["win_rate"], s["mean_margin"]), reverse=True)
    print("\nScreen ranking:", flush=True)
    for s in screen:
        print("  " + base.fmt(s) + f"  q10={s['day10_quads']:.1f}", flush=True)
    best = screen[0]
    confirm = None
    if best["win_rate"] >= 0.6 and best["mean_margin"] > 0:
        print(f"\nConfirming {best['name']}...", flush=True)
        confirm = eval_named(best["name"] + "_holdout", STRATEGIES[best["name"]], base.V12, CONFIRM_SEEDS, workers)
        print("  " + base.fmt(confirm), flush=True)
        vs9 = eval_named(best["name"] + "_vs9", STRATEGIES[best["name"]], base.V9, CONFIRM_SEEDS, workers)
        print("  vs9 " + base.fmt(vs9), flush=True)
        confirm["vs_v9"] = vs9
    else:
        print("\nNo strategy cleared win>=0.60 and positive margin. No main.py.", flush=True)
    report = dict(
        opponent="main_v12.py",
        screen_seeds=SCREEN_SEEDS,
        confirm_seeds=CONFIRM_SEEDS,
        elapsed_s=round(time.perf_counter() - t0, 1),
        screen=screen,
        confirm=confirm,
        note="Internal self-play. Not a leaderboard result. main.py not written unless holdout beats V12.",
    )
    (OUT / "screen_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT / 'screen_report.json'} in {report['elapsed_s']}s", flush=True)


if __name__ == "__main__":
    main()
