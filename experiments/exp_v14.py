"""V14 before/after experiment (repo-aware).

Measures Boey-style diagnostics (day-20 productive tiles, strawberry/wheat plots,
melon harvest yields) plus head-to-head vs V9 and V12, for the V13-lineage baseline
(strawberry_target=0) and V14 (strawberry_target=30). Small samples by default.
This is an internal-league signal, NOT a leaderboard result (see CLAUDE.md).

Run from the repo root:  python experiments/exp_v14.py
"""
import sys, contextlib, io, importlib.util, statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "league"))
import support  # noqa: E402

POLICY_V14 = ROOT / "policy" / "policy_template.py"
AGENTS = ROOT / "agents"
SEEDS = [30090000 + i for i in range(3)]

def _write(path, template_path, params):
    path.write_text(support.render(template_path.read_text(), params)); return str(path)

def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m.agent

def rollout(a_path, b_path, seed, collect=False):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        from kaggle_environments import make
    A = _load(a_path, "A"); B = _load(b_path, "B")
    env = make("kaggriculture", configuration={"seed": seed, "episodeSteps": 720}); env.run([A, B])
    f = env.steps[-1]; out = dict(cash=f[0].reward, rival=f[1].reward)
    if collect:
        farm = env.steps[min(19*24+23, 719)][0].observation.farms[0]
        cc = {c: 0 for c in ["WHEAT", "CARROT", "MELON", "TOMATO", "STRAWBERRY"]}; anim = 0
        for row in farm.tiles:
            for t in row:
                if isinstance(t, dict):
                    if t.get("crop") in cc: cc[t["crop"]] += 1
                    if t.get("animal"): anim += 1
        out["day20"] = dict(crops=cc, productive=sum(cc.values()) + anim)
        mel = []
        for i in range(1, len(env.steps) - 1):
            t0 = env.steps[i][0].observation.farms[0].tiles
            t1 = env.steps[i + 1][0].observation.farms[0].tiles
            for y, row in enumerate(t0):
                for x, tile in enumerate(row):
                    if isinstance(tile, dict) and tile.get("crop") == "MELON" and tile.get("yield_units", 0) > 0:
                        nxt = t1[y][x]
                        if not (isinstance(nxt, dict) and nxt.get("crop") == "MELON"):
                            mel.append(tile.get("yield_units", 0))
        out["melon_yields"] = mel
    return out

def compare(cand, label, opp, seeds, collect=False):
    wins = g = 0; marg, d20, mel = [], [], []
    for s in seeds:
        r0 = rollout(cand, opp, s, collect); r1 = rollout(opp, cand, s, False)
        for cc, oc in [(r0["cash"], r0["rival"]), (r1["rival"], r1["cash"])]:
            marg.append(cc - oc); wins += cc > oc; g += 1
        if collect: d20.append(r0["day20"]); mel += r0["melon_yields"]
    line = f"  vs {label:4s}: win={wins/g:.2f} mean_margin={statistics.mean(marg):+.0f} min={min(marg):+.0f}"
    if collect and d20:
        straw = statistics.mean(d["crops"]["STRAWBERRY"] for d in d20)
        wheat = statistics.mean(d["crops"]["WHEAT"] for d in d20)
        prod = statistics.mean(d["productive"] for d in d20)
        below6 = sum(1 for y in mel if y < 6)
        line += (f"\n    day20(seat0): productive={prod:.0f} straw={straw:.1f} wheat={wheat:.1f}"
                 f" | melon harvests below 6 units: {below6}/{len(mel)}")
    print(line)

def main():
    tmp = ROOT / "experiments" / "_tmp"; tmp.mkdir(exist_ok=True)
    base = _write(tmp / "_baseline.py", POLICY_V14, {})
    v14 = _write(tmp / "_v14.py", POLICY_V14, {"strawberry_target": 30})
    v9, v12 = str(AGENTS / "main_v9.py"), str(AGENTS / "main_v12.py")
    # Note: policy_template.py is V14, so the melon fix is active in BOTH rows below
    # (~0-3/60 sub-6 harvests here vs ~52/60 on the pre-fix v2 template). This script
    # isolates the strawberry_target effect.
    print("V14 code, strawberry_target=0 (melon fix active):")
    compare(base, "V9", v9, SEEDS, collect=True); compare(base, "V12", v12, SEEDS, collect=True)
    print("\nV14 (strawberry_target=30):")
    compare(v14, "V9", v9, SEEDS, collect=True); compare(v14, "V12", v12, SEEDS, collect=True)
    print("\nNote: internal-league signal on a small sample, not a leaderboard result.")

if __name__ == "__main__":
    main()
