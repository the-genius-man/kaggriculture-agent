"""Turn downloaded Kaggle replay JSONs into compact, comparable per-seat metrics.

Deliberately parses the raw replay structure directly rather than reconstructing the
game through kaggle_environments: no simulator import, no pinned-version dependency,
and the output is a few hundred bytes per game instead of ~2MB, which is what makes it
practical to compare dozens of games at once.

Reports, for BOTH seats of every replay, a day-by-day trace (cash, owned/productive
tiles, crops by type, animals, hands, weeds) plus whole-game action and market-order
counts. That is the shape needed to answer "what does a leader do in days 1-10 that we
do not", which is the open question in analysis/REPORT_deployment_diagnosis.md.

Replays themselves stay private (see CLAUDE.md); this summary is what travels.
"""
import argparse, json, statistics, sys
from collections import Counter
from pathlib import Path

DAYS = [3, 5, 7, 10, 12, 15, 20, 25, 29]
CROPS = ["WHEAT", "CARROT", "MELON", "TOMATO", "STRAWBERRY"]


def _obs(step_entry):
    """A step entry is per-agent: {observation, action, reward, status}."""
    if isinstance(step_entry, dict):
        return step_entry.get("observation") or {}
    return {}


def _farm(obs, seat):
    farms = obs.get("farms")
    if isinstance(farms, list) and len(farms) > seat:
        return farms[seat] or {}
    return {}


def tile_stats(farm):
    tiles = farm.get("tiles") or []
    crops = Counter()
    animals = Counter()
    weeds = empty = locked = 0
    for row in tiles:
        for t in row:
            if t == "LOCKED":
                locked += 1
            elif t is None:
                empty += 1
            elif isinstance(t, dict):
                if t.get("crop"):
                    crops[t["crop"]] += 1
                elif t.get("animal"):
                    animals[t["animal"]] += 1
                elif t.get("kind") == "WEED":
                    weeds += 1
    return crops, animals, weeds, empty, locked


def analyse_replay(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    steps = data.get("steps") or []
    if not steps:
        return {"file": Path(path).name, "error": "no steps", "top_keys": list(data)[:12]}
    n_seats = len(steps[0]) if isinstance(steps[0], list) else 1
    out = {"file": Path(path).name, "steps": len(steps), "seats": n_seats, "per_seat": []}

    for seat in range(n_seats):
        # Prefer this seat's own observation; fall back to seat 0's shared view.
        def obs_at(i):
            row = steps[i]
            o = _obs(row[seat]) if isinstance(row, list) and len(row) > seat else {}
            if not o.get("farms") and isinstance(row, list) and row:
                o = _obs(row[0])
            return o

        trace = {}
        for day in DAYS:
            idx = min(day * 24 + 23, len(steps) - 1)
            o = obs_at(idx)
            f = _farm(o, seat)
            if not f:
                continue
            crops, animals, weeds, empty, locked = tile_stats(f)
            trace[str(day)] = {
                "cash": f.get("money"),
                "quadrants": len(f.get("unlocked_quadrants") or []),
                "hands": len(f.get("hands") or []),
                "crops": sum(crops.values()),
                "animals": sum(animals.values()),
                "productive": sum(crops.values()) + sum(animals.values()),
                "weeds": weeds,
                "empty_owned": empty,
                "by_crop": {c: crops[c] for c in CROPS if crops[c]},
                "by_animal": dict(animals),
            }

        actions = Counter()
        market = Counter()
        market_units = Counter()
        for row in steps[1:]:
            entry = row[seat] if isinstance(row, list) and len(row) > seat else None
            act = (entry or {}).get("action") if isinstance(entry, dict) else None
            if not isinstance(act, dict):
                continue
            for unit in [act.get("farmer")] + list(act.get("hands") or []):
                if unit:
                    actions[unit[0] if isinstance(unit, list) else str(unit)] += 1
            for order in act.get("market") or []:
                if isinstance(order, list) and order:
                    key = order[0] if len(order) < 2 else f"{order[0]}:{order[1]}"
                    market[key] += 1
                    if len(order) > 2 and isinstance(order[2], (int, float)):
                        market_units[key] += order[2]

        final = steps[-1]
        reward = None
        if isinstance(final, list) and len(final) > seat and isinstance(final[seat], dict):
            reward = final[seat].get("reward")
        out["per_seat"].append({"seat": seat, "final_cash": reward, "trace": trace,
                                "actions": dict(actions.most_common()),
                                "market_orders": dict(market.most_common(14)),
                                "market_units": dict(market_units.most_common(14))})
    return out


def table(reports, label):
    """Mean day-by-day trace across a set of (report, seat) pairs."""
    rows = []
    for day in DAYS:
        vals = {k: [] for k in ("cash", "productive", "crops", "animals", "hands",
                                 "quadrants", "weeds")}
        for rep, seat in reports:
            s = next((x for x in rep.get("per_seat", []) if x["seat"] == seat), None)
            t = (s or {}).get("trace", {}).get(str(day))
            if not t:
                continue
            for k in vals:
                if isinstance(t.get(k), (int, float)):
                    vals[k].append(t[k])
        if vals["cash"]:
            rows.append((day, {k: statistics.mean(v) for k, v in vals.items() if v}))
    lines = [f"  {label}  (n={len(reports)} game-seats)",
             "   day |     cash | prod | crop | anml | hand | quad | weed"]
    for day, m in rows:
        lines.append("  %4d | %8.0f | %4.1f | %4.1f | %4.1f | %4.1f | %4.1f | %4.1f"
                     % (day, m.get("cash", 0), m.get("productive", 0), m.get("crops", 0),
                        m.get("animals", 0), m.get("hands", 0), m.get("quadrants", 0),
                        m.get("weeds", 0)))
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("replays", nargs="+", help="replay JSON files or directories")
    p.add_argument("--out", default=None, help="write the full JSON report here")
    p.add_argument("--schema", action="store_true", help="dump one replay's structure and exit")
    a = p.parse_args()

    paths = []
    for r in a.replays:
        pth = Path(r)
        paths.extend(sorted(pth.glob("*.json")) if pth.is_dir() else [pth])
    if not paths:
        print("no replay files found", file=sys.stderr)
        return 1

    if a.schema:
        data = json.loads(paths[0].read_text(encoding="utf-8"))
        print("top-level keys:", list(data))
        steps = data.get("steps") or []
        print("steps:", len(steps), "| step[0] type:", type(steps[0]).__name__ if steps else None)
        if steps and isinstance(steps[0], list) and steps[0]:
            print("agents per step:", len(steps[0]), "| agent keys:", list(steps[0][0]))
            o = steps[0][0].get("observation", {})
            print("observation keys:", list(o))
            f = (o.get("farms") or [{}])[0]
            print("farm keys:", list(f))
        return 0

    reports = [analyse_replay(p) for p in paths]
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(reports, indent=1), encoding="utf-8")
        print("->", a.out)

    for rep in reports:
        if rep.get("error"):
            print(rep["file"], "ERROR", rep["error"], rep.get("top_keys"))
            continue
        cashes = [s.get("final_cash") for s in rep["per_seat"]]
        print("\n=== %s  final cash %s ===" % (rep["file"], cashes))
        for s in rep["per_seat"]:
            print(table([(rep, s["seat"])], "seat %d" % s["seat"]))
            print("   actions:", s["actions"])
            print("   market :", s["market_units"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
