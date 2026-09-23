"""Bounded validation gate. Renders the current candidate (policy/policy_template.py +
candidate.json), plays it vs V9 and V12 on fresh holdout seeds (both seats), applies the
promotion gates, then writes main.py + validation.json to --out. Used by the Kaggle
kernel; also runnable locally. Gate here is a pre-filter; V13 is added automatically if
agents/main_v13.py exists. This is an internal-league gate, not a leaderboard result."""
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "league"))
import support  # noqa

# opponent -> min win rate. main_leader.py is a leader-style opponent (see
# analysis/REPORT_deployment_diagnosis.md): the league is otherwise all our own
# lineage, which has not predicted leaderboard placement.
# main_leader2.py is the reference opponent that matters: it is profile-matched to a
# rank-2 leaderboard team from real replays (2026-09-23), whereas main_leader.py was
# built from ~600-rated opponents in our own games and so never represented the top of
# the table. Kept at the same 0.55 floor, but read its number first.
GATES = {"main_v9.py": 0.80, "main_v12.py": 0.60, "main_v13.py": 0.55,
         "main_leader.py": 0.55, "main_leader2.py": 0.55}

def occupancy(rows, days=("10", "20")):
    """Mean cash / productive tiles / bare owned tiles at a couple of checkpoints."""
    import statistics
    out = {}
    for d in days:
        snaps = [r["snapshots"][d] for r in rows if d in r.get("snapshots", {})]
        if not snaps:
            continue
        def m(key):
            vals = [s[key] for s in snaps if isinstance(s.get(key), (int, float))]
            return round(statistics.mean(vals), 1) if vals else None
        out["day" + d] = {"cash": m("cash"), "productive": None, "bare": m("bare"),
                          "crops": m("crops"), "animals": m("animals"), "hands": m("hands"),
                          "quadrants": m("quadrants"), "weeds": m("weeds"),
                          "unwatered": m("unwatered")}
        c, an, hd = out["day" + d]["crops"], out["day" + d]["animals"], out["day" + d]["hands"]
        if c is not None and an is not None:
            out["day" + d]["productive"] = round(c + an, 1)
            # Tiles carried per hand. The leader's trace sits at 6.3-6.8 all game
            # (25 tiles/4 hands, 50/8, 74.6/11); ours runs ~3.5, which is the real
            # shape of the occupancy gap.
            if hd:
                out["day" + d]["per_hand"] = round((c + an) / max(1.0, hd), 2)
    return out


def evaluate(cand, opp, seeds):
    rows = []
    for s in seeds:
        rows.append(support.worker((cand, opp, s, 0)))     # candidate at seat 0
        rows.append(support.worker((cand, opp, s, 1)))     # candidate at seat 1
    # worker always seats the first arg (candidate) at `seat` and reports that seat's
    # cash, so both calls are candidate-perspective; seat cancels over the pair.
    su = support.summary(rows); lo, hi = support.seed_margin_interval(rows)
    return su, (lo, hi), rows

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=str(ROOT)); p.add_argument("--seeds", type=int, default=24)
    p.add_argument("--seed-base", type=int, default=40000000)
    p.add_argument("--candidate", default=str(ROOT / "candidate.json"))
    a = p.parse_args(); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    params = json.loads(Path(a.candidate).read_text()) if Path(a.candidate).exists() else {}
    agent_src = support.render((ROOT / "policy" / "policy_template.py").read_text(), params)
    cand_path = out / "main.py"; cand_path.write_text(agent_src)
    seeds = [a.seed_base + i for i in range(a.seeds)]
    report = {"candidate_params": params, "seeds": len(seeds), "seed_base": a.seed_base,
              "opponents": {}, "gate_pass": True}
    for opp_name, min_wr in GATES.items():
        opp = ROOT / "agents" / opp_name
        if not opp.exists():
            report["opponents"][opp_name] = {"skipped": "agent file absent"}; continue
        su, (lo, hi), rows = evaluate(str(cand_path), str(opp), seeds)
        ok = su["win_rate"] >= min_wr and lo > 0
        report["opponents"][opp_name] = {
            "win_rate": round(su["win_rate"], 3), "min_required": min_wr,
            "mean_margin": round(su["mean_margin"]), "margin_ci90": [round(lo), round(hi)],
            "mean_cash": round(su["mean_cash"]), "pass": ok,
            # Occupancy, not just the verdict: the replay study showed win rate alone
            # hid the actual defect (bare owned land) for weeks.
            "occupancy": occupancy(rows)}
        report["gate_pass"] &= ok
    (out / "validation.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print("GATE:", "PASS" if report["gate_pass"] else "FAIL", "-> main.py exported to", cand_path)

if __name__ == "__main__": main()
