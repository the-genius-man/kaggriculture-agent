"""Exact per-seat money ledger for a Kaggriculture game: where every unit of cash came
from, where it went, and what production was lost before it could be sold.

`analyze_replays.py` reads snapshots; it can say *how many* tiles were productive but
not *what they earned*. This re-runs the game through the real engine with its cash and
tile mutators wrapped, so every sale, purchase, hire, land buy, harvest, dry-out death,
rot and shed overflow is logged at the moment it happens, attributed to its seat.

Two modes, same instrumentation:

  --replay FILE...    re-simulate a downloaded Kaggle replay from its recorded actions
                      (checks the re-simulated final cash matches the replay's rewards;
                      a mismatch is reported, never silently accepted)
  --play A B --seeds  play two local agent files on the given seeds

Replays stay private (CLAUDE.md); this summary is what travels. Needs the pinned
`kaggle-environments==1.32.7`.
"""
import argparse, contextlib, importlib.util, io, json, statistics, sys
from collections import Counter, defaultdict
from pathlib import Path

with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    from kaggle_environments import make
    from kaggle_environments.envs.kaggriculture import kaggriculture as K

CROPS = list(K.CROPS)
BASE = {k: v["base"] for k, v in K.MARKET_PARAMS.items()}
SNAP_DAYS = (3, 5, 7, 10, 12, 15, 20, 25, 29)

CTX = {"farms": None, "step": 0, "log": None}


def _pid(farm):
    farms = CTX["farms"] or []
    for i, f in enumerate(farms):
        if f is farm:
            return i
    return None


def _new_seat():
    return {
        "revenue": Counter(), "sold_units": Counter(), "spend": Counter(), "bought_units": Counter(),
        "harvested": Counter(), "planted": Counter(), "actions": Counter(),
        "dryout_deaths": Counter(), "dryout_units_lost": Counter(),
        "rot_units_lost": Counter(), "rot_deaths": Counter(), "animal_escapes": Counter(),
        "overflow_units": Counter(), "revenue_by_day": Counter(), "spend_by_day": Counter(),
        "unit_turns": 0, "daily": {}, "harvest_age_units": defaultdict(list),
    }


def _instrument():
    orig_commit, orig_hire, orig_land = K._commit_unit, K._do_hire, K._do_buy_land
    orig_unit, orig_plants, orig_animals = K._apply_unit_action, K._daily_refresh_plants, K._daily_refresh_animals
    orig_decay, orig_drop = K._decay_plants, K._drop_inventories_to_shed

    def seat(farm):
        p = _pid(farm)
        return None if p is None else CTX["log"][p]

    def commit(op, item, price, farm, private, market, shed_capacity=100):
        before = farm["money"]
        ok = orig_commit(op, item, price, farm, private, market, shed_capacity)
        s = seat(farm)
        if ok and s is not None:
            day = CTX["step"] // 24
            delta = farm["money"] - before
            if op == "SELL":
                s["revenue"][item] += delta; s["sold_units"][item] += 1; s["revenue_by_day"][day] += delta
            else:
                key = ("seed:" if op == "BUY_SEED" else "") + item
                s["spend"][key] += -delta; s["bought_units"][key] += 1; s["spend_by_day"][day] += -delta
        return ok

    def hire(farm, private, board_size, mult=K.FARM_HAND_COST_MULT):
        before = farm["money"]; orig_hire(farm, private, board_size, mult)
        s = seat(farm)
        if s is not None and farm["money"] < before:
            s["spend"]["hire"] += before - farm["money"]; s["spend_by_day"][CTX["step"] // 24] += before - farm["money"]

    def land(farm, board_size):
        before = farm["money"]; orig_land(farm, board_size)
        s = seat(farm)
        if s is not None and farm["money"] < before:
            s["spend"]["land"] += before - farm["money"]; s["spend_by_day"][CTX["step"] // 24] += before - farm["money"]

    def unit(farm, private, idx, action, board_size, day, turns_per_day, shed_capacity=100):
        s = seat(farm)
        op = action[0] if isinstance(action, list) and action else "PASS"
        inv_before = dict(K._farmer_inventory(private, idx)) if op == "HARVEST" else None
        pos = K._farmer_position(farm, idx)
        tile_before = farm["tiles"][pos[1]][pos[0]] if pos is not None else None
        # The engine zeroes yield_units in place on HARVEST, so copy before acting.
        tile_before = dict(tile_before) if isinstance(tile_before, dict) else tile_before
        orig_unit(farm, private, idx, action, board_size, day, turns_per_day, shed_capacity)
        if s is None or pos is None:
            return
        s["unit_turns"] += 1
        s["actions"][op if op not in K.FARMER_MOVES else "MOVE"] += 1
        if op == "HARVEST":
            if isinstance(tile_before, dict) and tile_before.get("kind") == "PLANT":
                crop = tile_before["crop"]
                if not K.CROPS[crop]["ongoing"]:
                    # (age in days, units) per one-time-crop harvest: harvesting before
                    # the watering window closes forfeits yield the tile could still earn.
                    s["harvest_age_units"][crop].append((day - tile_before["planted_day"],
                                                         tile_before.get("yield_units", 0)))
            inv = K._farmer_inventory(private, idx)
            for k, v in inv.items():
                d = v - inv_before.get(k, 0)
                if d > 0:
                    s["harvested"][k] += d
        elif op == "PLANT" and tile_before is None:
            t = farm["tiles"][pos[1]][pos[0]]
            if isinstance(t, dict) and t.get("kind") == "PLANT":
                s["planted"][t["crop"]] += 1

    def plants(farm, current_day, turns_per_day):
        s = seat(farm)
        before = [[(t["crop"], t["yield_units"]) if isinstance(t, dict) and t.get("kind") == "PLANT" else None
                   for t in row] for row in farm["tiles"]]
        orig_plants(farm, current_day, turns_per_day)
        if s is None:
            return
        for y, row in enumerate(farm["tiles"]):
            for x, t in enumerate(row):
                b = before[y][x]
                if b and isinstance(t, dict) and t.get("kind") == "WEED":
                    s["dryout_deaths"][b[0]] += 1; s["dryout_units_lost"][b[0]] += b[1]

    def animals(farm, day):
        s = seat(farm)
        before = [[t.get("animal") if isinstance(t, dict) else None for t in row] for row in farm["tiles"]]
        orig_animals(farm, day)
        if s is None:
            return
        for y, row in enumerate(farm["tiles"]):
            for x, t in enumerate(row):
                if before[y][x] and not (isinstance(t, dict) and t.get("animal")):
                    s["animal_escapes"][before[y][x]] += 1

    def decay(farm, step):
        s = seat(farm)
        before = [[(t["crop"], t["yield_units"]) if isinstance(t, dict) and t.get("kind") == "PLANT" else None
                   for t in row] for row in farm["tiles"]]
        orig_decay(farm, step)
        if s is None:
            return
        for y, row in enumerate(farm["tiles"]):
            for x, t in enumerate(row):
                b = before[y][x]
                if not b:
                    continue
                if isinstance(t, dict) and t.get("kind") == "PLANT":
                    if t["yield_units"] < b[1]:
                        s["rot_units_lost"][b[0]] += b[1] - t["yield_units"]
                elif isinstance(t, dict) and t.get("kind") == "WEED":
                    s["rot_units_lost"][b[0]] += b[1]; s["rot_deaths"][b[0]] += 1

    def drop(private, capacity):
        held = Counter()
        for inv in private["inventories"]:
            for k, v in inv.items():
                held[k] += max(0, v)
        shed_before = Counter(private["shed"])
        orig_drop(private, capacity)
        for k, v in held.items():
            kept = private["shed"].get(k, 0) - shed_before.get(k, 0)
            if v - kept > 0:
                CTX["_overflow"][k] += v - kept

    K._commit_unit, K._do_hire, K._do_buy_land = commit, hire, land
    K._apply_unit_action, K._daily_refresh_plants = unit, plants
    K._daily_refresh_animals, K._decay_plants, K._drop_inventories_to_shed = animals, decay, drop


def _snapshot(farm, private, s, day):
    bare = crops = animals = weeds = structures = 0
    by_crop = Counter()
    for row in farm["tiles"]:
        for t in row:
            if t is None:
                bare += 1
            elif isinstance(t, dict):
                if t.get("kind") == "PLANT":
                    crops += 1; by_crop[t["crop"]] += 1
                elif t.get("animal"):
                    animals += 1
                elif t.get("kind") == "WEED":
                    weeds += 1
                else:
                    structures += 1
    s["daily"][day] = {"cash": round(farm["money"]), "bare": bare, "crops": crops, "animals": animals,
                       "weeds": weeds, "empty_structures": structures, "hands": len(farm["hands"]),
                       "quadrants": len(farm["unlocked_quadrants"]), "by_crop": dict(by_crop)}


def _wrap_interpreter(env, n):
    orig = env.interpreter

    def interp(state, e):
        obs0 = state[0].observation
        farms = getattr(obs0, "farms", None)
        CTX["farms"] = farms
        CTX["step"] = int(getattr(obs0, "step", 0) or 0)
        # Snapshot at hour 23, before end-of-day wipes hands and refreshes plants.
        if farms and CTX["step"] % 24 == 23:
            for i in range(n):
                _snapshot(farms[i], state[i].observation.private, CTX["log"][i], CTX["step"] // 24)
        # Overflow is per-private; route it to the seat whose private is being dropped.
        out = None
        if farms and (CTX["step"] + 1) % 24 == 0:
            before = [Counter() for _ in range(n)]
            CTX["_overflow"] = Counter()
            # _end_of_day drops in player order; capture per player by wrapping once.
            orig_drop = K._drop_inventories_to_shed
            calls = {"i": 0}

            def per_player(private, capacity):
                CTX["_overflow"] = Counter()
                orig_drop(private, capacity)
                i = calls["i"]; calls["i"] += 1
                if i < n:
                    CTX["log"][i]["overflow_units"].update(CTX["_overflow"])
            K._drop_inventories_to_shed = per_player
            try:
                out = orig(state, e)
            finally:
                K._drop_inventories_to_shed = orig_drop
        else:
            out = orig(state, e)
        return out

    env.interpreter = interp


def _finish(env, n, meta):
    obs0 = env.state[0].observation
    seats = []
    for i in range(n):
        s = CTX["log"][i]
        farm = obs0.farms[i]; private = env.state[i].observation.private
        leftover = Counter()
        for k, v in private["shed"].items():
            if v and k in BASE:
                leftover[k] += v
        seeds_left = {k: v for k, v in private["seeds"].items() if v}
        rev = sum(s["revenue"].values()); spend = sum(s["spend"].values())
        seats.append({
            "final_cash": round(farm["money"]), "revenue": round(rev), "spend": round(spend),
            "revenue_by_item": {k: round(v) for k, v in s["revenue"].most_common()},
            "sold_units": dict(s["sold_units"]),
            "avg_sell_price": {k: round(s["revenue"][k] / s["sold_units"][k], 1) for k in s["sold_units"]},
            "spend_by_item": {k: round(v) for k, v in s["spend"].most_common()},
            "bought_units": dict(s["bought_units"]),
            "harvested": dict(s["harvested"]), "planted": dict(s["planted"]),
            "harvest_age_units": {k: v for k, v in s["harvest_age_units"].items()},
            "actions": dict(s["actions"]), "unit_turns": s["unit_turns"],
            "dryout_deaths": dict(s["dryout_deaths"]), "dryout_units_lost": dict(s["dryout_units_lost"]),
            "rot_deaths": dict(s["rot_deaths"]), "rot_units_lost": dict(s["rot_units_lost"]),
            "animal_escapes": dict(s["animal_escapes"]), "overflow_units": dict(s["overflow_units"]),
            "unsold_at_end": dict(leftover), "seeds_left_at_end": seeds_left,
            "revenue_by_day": {d: round(s["revenue_by_day"].get(d, 0)) for d in range(30)},
            "spend_by_day": {d: round(s["spend_by_day"].get(d, 0)) for d in range(30)},
            "daily": {d: s["daily"][d] for d in sorted(s["daily"]) if d in SNAP_DAYS or True},
        })
    return {**meta, "seats": seats}


def replay_game(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    steps = data["steps"]; n = len(steps[0])
    seed = (data.get("info") or {}).get("seed")
    cfg = {k: v for k, v in data["configuration"].items() if k not in ("seed",) and v not in (None, {})}
    cfg["seed"] = seed
    env = make("kaggriculture", configuration=cfg)
    CTX["log"] = [_new_seat() for _ in range(n)]
    _wrap_interpreter(env, n)
    env.reset(n)
    for t in range(1, len(steps)):
        env.step([steps[t][i].get("action") for i in range(n)])
        if env.done:
            break
    expected = data.get("rewards") or []
    got = [env.state[i].reward for i in range(n)]
    names = (data.get("info") or {}).get("TeamNames") or [f"seat{i}" for i in range(n)]
    match = all(e is not None and g is not None and abs(e - g) < 0.5 for e, g in zip(expected, got))
    return _finish(env, n, {"file": Path(path).name, "episode": (data.get("info") or {}).get("EpisodeId"),
                            "teams": names, "replay_rewards": expected, "resim_rewards": got,
                            "resim_matches": match})


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m.agent


def play_game(a_path, b_path, seed):
    A = _load(a_path, "ledger_A"); B = _load(b_path, "ledger_B")
    env = make("kaggriculture", configuration={"seed": seed, "episodeSteps": 720})
    CTX["log"] = [_new_seat(), _new_seat()]
    _wrap_interpreter(env, 2)
    with contextlib.redirect_stdout(io.StringIO()):
        env.run([A, B])
    return _finish(env, 2, {"seed": seed, "teams": [Path(a_path).stem, Path(b_path).stem]})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--replay", nargs="*", default=[])
    ap.add_argument("--play", nargs=2, metavar=("A", "B"))
    ap.add_argument("--seeds", default="")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    _instrument()
    games = []
    for f in a.replay:
        g = replay_game(f); games.append(g)
        print(f"{g['file']}: {g['teams']} resim={g['resim_rewards']} replay={g['replay_rewards']} "
              f"match={g['resim_matches']}", file=sys.stderr)
    if a.play:
        for sd in [int(x) for x in a.seeds.split(",") if x]:
            g = play_game(a.play[0], a.play[1], sd); games.append(g)
            print(f"seed {sd}: {[s['final_cash'] for s in g['seats']]}", file=sys.stderr)
    Path(a.out).write_text(json.dumps(games, indent=1))


if __name__ == "__main__":
    main()
