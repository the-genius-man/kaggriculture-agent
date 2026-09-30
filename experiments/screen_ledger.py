"""Screen policy variants locally on the production numbers that separate the leaders
from us (analysis/REPORT_cash_ledger.md), not only on wins against our own lineage.

Each variant is v17's promoted config plus overrides, rendered from the current
policy template, played against an opponent file on paired seeds in BOTH seats,
with tools/money_ledger.py instrumentation. Reports per variant: win rate and mean
margin vs the opponent, final cash, revenue in days 10-19, strawberries in the
ground on day 7, wheat units per harvest, FERTILIZE actions, day-10 crops/animals.

This is a screen, not the gate: local opponents are not leaderboard opponents.

  python experiments/screen_ledger.py --variants experiments/v18_variants.json \
      --opponent agents/main_v16.py --seeds 8 --out screen.json
"""
import argparse, json, multiprocessing as mp, statistics as st, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "league")); sys.path.insert(0, str(ROOT / "tools"))


def _job(args):
    path, opp, seed, seat = args
    sys.path.insert(0, str(ROOT / "tools"))  # spawned workers (Windows) start clean
    import money_ledger as ml
    ml._instrument()
    a, b = (path, opp) if seat == 0 else (opp, path)
    g = ml.play_game(a, b, seed)
    return path, seed, seat, g["seats"][seat], g["seats"][1 - seat]["final_cash"]


def summarise(rows):
    me = [r[3] for r in rows]; opp = [r[4] for r in rows]
    m = lambda xs: st.mean(xs) if xs else 0.
    wheat = [u for s in me for _, u in s["harvest_age_units"].get("WHEAT", [])]
    return {
        "games": len(me),
        "win_rate": m([1. if s["final_cash"] > o else .5 if s["final_cash"] == o else 0. for s, o in zip(me, opp)]),
        "margin": m([s["final_cash"] - o for s, o in zip(me, opp)]),
        "final_cash": m([s["final_cash"] for s in me]),
        "rev_d10_19": m([sum(s["revenue_by_day"][d] for d in range(10, 20)) for s in me]),
        "rev_d0_9": m([sum(s["revenue_by_day"][d] for d in range(0, 10)) for s in me]),
        "strawberries_d7": m([s["daily"][7]["by_crop"].get("STRAWBERRY", 0) for s in me]),
        "strawberries_d10": m([s["daily"][10]["by_crop"].get("STRAWBERRY", 0) for s in me]),
        "wheat_units_per_harvest": m(wheat),
        "fertilize": m([s["actions"].get("FERTILIZE", 0) for s in me]),
        "crops_d10": m([s["daily"][10]["crops"] for s in me]),
        "animals_d10": m([s["daily"][10]["animals"] for s in me]),
        "quadrants_d10": m([s["daily"][10]["quadrants"] for s in me]),
        "cash_d10": m([s["daily"][10]["cash"] for s in me]),
        "hands_d1": m([s["daily"][1]["hands"] for s in me]),
        "hands_d7": m([s["daily"][7]["hands"] for s in me]),
        "dryout_deaths": m([sum(s["dryout_deaths"].values()) for s in me]),
        "strawb_harvested": m([s["harvested"].get("STRAWBERRY", 0) for s in me]),
        "strawb_price": m([s["avg_sell_price"].get("STRAWBERRY", 0) for s in me]),
        "strawb_planted": m([s["planted"].get("STRAWBERRY", 0) for s in me]),
        "wheat_planted": m([s["planted"].get("WHEAT", 0) for s in me]),
        "spend_seeds": m([sum(v for k, v in s["spend_by_item"].items() if k.startswith("seed:")) for s in me]),
        "spend_animals": m([sum(s["spend_by_item"].get(k, 0) for k in ("COW", "SHEEP", "GOOSE")) for s in me]),
        **{"rev_" + it: m([s["revenue_by_item"].get(it, 0) for s in me])
           for it in ("WHEAT", "CARROT", "STRAWBERRY", "MELON", "MILK", "WOOL", "EGG", "FERTILIZER")},
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--variants", required=True, help="JSON {name: {param: value}} applied over --base")
    ap.add_argument("--base", default=str(ROOT / "experiments" / "v17_params.json"))
    ap.add_argument("--opponent", required=True)
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--seed-base", type=int, default=97100000)
    ap.add_argument("--workers", type=int, default=max(1, mp.cpu_count() - 1))
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    import support
    template = (ROOT / "policy" / "policy_template.py").read_text(encoding="utf-8")
    base = json.loads(Path(a.base).read_text())
    variants = json.loads(Path(a.variants).read_text())
    tmp = Path(tempfile.mkdtemp(prefix="screen_"))
    paths = {}
    for name, over in variants.items():
        p = tmp / f"{name}.py"; p.write_text(support.render(template, {**base, **over}), encoding="utf-8")
        paths[str(p)] = name
    seeds = [a.seed_base + 7919 * i for i in range(a.seeds)]
    jobs = [(p, a.opponent, sd, seat) for p in paths for sd in seeds for seat in (0, 1)]
    with mp.Pool(a.workers) as pool:
        rows = pool.map(_job, jobs, chunksize=1)
    out = {}
    for p, name in paths.items():
        out[name] = summarise([r for r in rows if r[0] == p])
    Path(a.out).write_text(json.dumps({"opponent": a.opponent, "seeds": seeds, "base": base,
                                       "variants": variants, "results": out}, indent=1))
    keys = list(next(iter(out.values())))
    print(f"{'':<24}" + "".join(f"{n[:11]:>12}" for n in out))
    for k in keys:
        print(f"{k:<24}" + "".join(f"{out[n][k]:>12.2f}" for n in out))


if __name__ == "__main__":
    main()
