"""Render the policy at several configs and actually call agent() on a synthetic
observation. Catches "crashes on the first move" before a Kaggle kernel does.

Written after a real incident on 2026-09-23: a crop_value rewrite left `value`
assigned only inside an `if cash_discount<1.0` branch, so every config using the
DEFAULT (1.0) raised UnboundLocalError on its first call. The one-shot gate happened
to test cash_discount=0.80 and passed cleanly, so the bug shipped, and the 150-minute
search died on trial 0 with `max() iterable argument is empty` -- support.worker's
timing list was empty because the agent never completed a single call. Two hours of
kernel time to discover a missing assignment.

No kaggle_environments import: the observation schema below is taken from a real
downloaded replay, so this runs anywhere in about a second.
"""
import importlib.util, itertools, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "league"))
import support  # noqa: E402

N = 10  # full board is 10x10, four 5x5 quadrants


def observation(day=0, hour=0, money=3000, player=0, unlocked=1, planted=0):
    """Minimal but schema-accurate board (keys verified against a real replay)."""
    tiles = []
    for y in range(N):
        row = []
        for x in range(N):
            quad = (x // 5) + (y // 5) * 2
            row.append(None if quad < unlocked else "LOCKED")
        tiles.append(row)
    placed = 0
    for y in range(N):
        for x in range(N):
            if placed >= planted or tiles[y][x] is not None:
                continue
            tiles[y][x] = {"kind": "PLANT", "crop": "WHEAT", "planted_day": max(0, day - 2),
                           "yield_units": 1, "watered_today": False, "consecutive_unwatered": 1}
            placed += 1
    farm = {"farmer": [4, 4], "hands": [[4, 5], [5, 4]], "hires_today": 0,
            "money": money, "tiles": tiles, "unlocked_quadrants": list(range(unlocked))}
    other = {**farm, "tiles": [row[:] for row in tiles]}
    prices = {"WHEAT": 25, "CARROT": 35, "MELON": 250, "TOMATO": 60, "STRAWBERRY": 120,
              "MILK": 160, "WOOL": 200, "EGG": 50, "FERTILIZER": 100}
    return {"day": day, "hour": hour, "player": player,
            "farms": [farm, other] if player == 0 else [other, farm],
            "private": {"shed": {"WHEAT": 3}, "seeds": {"WHEAT": 2, "CARROT": 1},
                        "inventories": [{}, {}, {}]},
            "market": {"prices": prices}, "town": {"unlocked_shops": []}}


def load(source):
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(source)
        path = f.name
    spec = importlib.util.spec_from_file_location("smoke_candidate", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.agent


def main():
    template = (ROOT / "policy" / "policy_template.py").read_text(encoding="utf-8")
    # Defaults first -- that is exactly the case the incident missed -- then the
    # corners of every lever that can change which code path runs.
    configs = [("BASE defaults", {})]
    for disc, fill, urgency, tpu in itertools.product(
            (1.0, 0.8), (0, 12), (1.0, 6.0), (0, 7)):
        configs.append(("disc=%s fill=%s urgency=%s tpu=%s" % (disc, fill, urgency, tpu),
                        dict(cash_discount=disc, seed_fill=fill, plant_urgency=urgency,
                             tiles_per_unit=tpu)))
    # The per-quadrant expansion gate divides by a quadrant tile count, so exercise it
    # on boards with 1, 2 and 3 quadrants unlocked and at both threshold extremes.
    for gate, util in itertools.product((0, 1), (0.0, 0.95)):
        configs.append(("fill_gate=%s land_util=%s" % (gate, util),
                        dict(land_fill_gate=gate, land_util=util, land=4,
                             land_deadline=26, land_buffer=300)))
    # v18 levers: day-0 opening, reserve, strawberry rush (land-first ordering), the
    # short-cycle harvest rule and fertilizer carry, at off and on.
    for opening, rush, short in itertools.product((0, 1), (0, 24), (0, 1)):
        configs.append(("opening=%s rush=%s short=%s" % (opening, rush, short),
                        dict(opening_animals=opening, opening_reserve=60 * opening,
                             strawberry_rush=rush, rush_deadline=8, short_harvest=short,
                             fert_deposit_units=4 + 8 * short, fert_in_window=short,
                             seed_fill=4, land_util=0.95)))
    states = [dict(day=0, hour=0, money=3000, unlocked=1, planted=0),
              dict(day=8, hour=10, money=9000, unlocked=2, planted=24),   # part-full 2nd
              dict(day=12, hour=9, money=30000, unlocked=3, planted=50),  # part-full 3rd
              dict(day=0, hour=0, money=0, unlocked=1, planted=0),      # broke
              dict(day=9, hour=13, money=120, unlocked=2, planted=20),
              dict(day=19, hour=21, money=40000, unlocked=3, planted=40),
              dict(day=29, hour=23, money=90000, unlocked=3, planted=10)]

    failures = 0
    for label, params in configs:
        agent = load(support.render(template, params))
        for seat in (0, 1):
            for st in states:
                try:
                    out = agent(observation(player=seat, **st))
                    assert isinstance(out, dict) and "farmer" in out and "market" in out, out
                except Exception as e:
                    failures += 1
                    print("FAIL  %-44s seat=%d %s -> %s: %s"
                          % (label, seat, st, type(e).__name__, e))
    print("smoke: %d configs x %d states x 2 seats, %d failures"
          % (len(configs), len(states), failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
