"""Summarize occupancy / crop mix / actions from a Kaggriculture replay JSON."""
import json
import sys
from collections import Counter
from pathlib import Path

CROPS = ["WHEAT", "CARROT", "MELON", "TOMATO", "STRAWBERRY"]
DAYS = [5, 10, 15, 20, 25, 29]


def tile_stats(tiles):
    crops = Counter()
    animals = 0
    weeds = 0
    empty = 0
    locked = 0
    productive = 0
    for row in tiles:
        for t in row:
            if t == "LOCKED":
                locked += 1
            elif t is None:
                empty += 1
            elif isinstance(t, dict):
                if t.get("crop") in CROPS:
                    crops[t["crop"]] += 1
                    productive += 1
                elif t.get("animal"):
                    animals += 1
                    productive += 1
                elif t.get("kind") == "WEED":
                    weeds += 1
                else:
                    # empty coop/pasture still occupies a tile
                    productive += 1
    return {
        "productive": productive,
        "animals": animals,
        "weeds": weeds,
        "empty": empty,
        "locked": locked,
        "crops": {c: crops[c] for c in CROPS},
    }


def farm_from_step(step, seat):
    obs = step[seat].get("observation") or step[seat]
    farms = obs.get("farms") if isinstance(obs, dict) else None
    if farms is None:
        return None
    return farms[seat]


def summarize(path, focus_name="Whoopie"):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    info = data.get("info") or {}
    names = info.get("TeamNames") or info.get("teamNames") or []
    rewards = data.get("rewards") or [s.get("reward") for s in data["steps"][-1]]
    steps = data["steps"]
    focus = 0
    for i, n in enumerate(names):
        if focus_name.lower() in str(n).lower():
            focus = i
            break
    opp = 1 - focus
    out = {
        "episode": Path(path).stem,
        "teams": names,
        "focus_seat": focus,
        "focus_name": names[focus] if names else focus_name,
        "opponent_name": names[opp] if len(names) > opp else str(opp),
        "rewards": rewards,
        "won": rewards[focus] > rewards[opp] if rewards[0] is not None else None,
        "margin": (rewards[focus] - rewards[opp]) if rewards[0] is not None else None,
        "n_steps": len(steps),
        "seed": (info.get("seed") or data.get("configuration", {}).get("seed")),
        "snapshots": {},
        "actions": {"focus": Counter(), "opp": Counter()},
    }
    for day in DAYS:
        idx = min(day * 24 + 23, len(steps) - 1)
        snap = {}
        for seat, label in ((focus, "focus"), (opp, "opp")):
            farm = farm_from_step(steps[idx], seat)
            if farm is None:
                continue
            st = tile_stats(farm["tiles"])
            st["cash"] = farm.get("money")
            st["hands"] = len(farm.get("hands") or [])
            st["quadrants"] = len(farm.get("unlocked_quadrants") or [])
            snap[label] = st
        out["snapshots"][str(day)] = snap
    for i, step in enumerate(steps[1:], 1):
        for seat, label in ((focus, "focus"), (opp, "opp")):
            act = step[seat].get("action") or {}
            units = [act.get("farmer") or []] + list(act.get("hands") or [])
            for u in units:
                if u:
                    out["actions"][label][u[0]] += 1
    out["actions"]["focus"] = dict(out["actions"]["focus"])
    out["actions"]["opp"] = dict(out["actions"]["opp"])
    return out


def main():
    paths = sys.argv[1:]
    reports = [summarize(p) for p in paths]
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
