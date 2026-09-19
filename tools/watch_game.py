"""Render a game between two agents to a playable HTML file you can open in a browser.

Kaggle's GetEpisodeReplay is 404 unauthenticated (see tools/pull_episodes.py), so we
cannot watch real leaderboard games this way -- only games we run ourselves.

    python tools/watch_game.py agents/main_v14.py agents/main_leader.py --seed 94000000
"""
import argparse, contextlib, io, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "league"))

def main():
    p = argparse.ArgumentParser()
    p.add_argument("left"); p.add_argument("right")
    p.add_argument("--seed", type=int, default=94000000)
    p.add_argument("--out", default=None)
    a = p.parse_args()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        from kaggle_environments import make
    import support
    env = make("kaggriculture", configuration={"seed": a.seed, "episodeSteps": 720})
    env.run([support.load_agent(a.left, "left"), support.load_agent(a.right, "right")])
    cash = [s.reward for s in env.steps[-1]]
    out = Path(a.out or "replay_%s_vs_%s_%d.html"
               % (Path(a.left).stem, Path(a.right).stem, a.seed))
    out.write_text(env.render(mode="html", width=1000, height=700), encoding="utf-8")
    print("%s %d  vs  %s %d" % (Path(a.left).name, cash[0], Path(a.right).name, cash[1]))
    print("winner:", Path(a.left if cash[0] > cash[1] else a.right).name)
    print("-> %s (%.1f MB) - open it in a browser" % (out, out.stat().st_size / 1e6))

if __name__ == "__main__":
    main()
