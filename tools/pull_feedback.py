"""Read-only feedback pull: leaderboard + our submissions into <out>/. Episode/replay
download is competition-specific (kaggle-environments 'Simulations' comps expose it via
the ListEpisodes endpoint, not the plain CLI); left as a clearly-marked best-effort stub
so the deterministic parts never fail on it."""
import argparse, subprocess, sys
from pathlib import Path

def run(cmd, outfile):
    r = subprocess.run(cmd, capture_output=True, text=True)
    Path(outfile).write_text(r.stdout or r.stderr)
    print(f"{'ok  ' if r.returncode==0 else 'warn'} {' '.join(cmd)} -> {outfile}")
    if r.returncode != 0:                      # say WHY, or the pull is undiagnosable
        for line in (r.stderr or r.stdout or "<no output>").strip().splitlines()[:8]:
            print("      " + line)
    return r.returncode == 0

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--competition", required=True); p.add_argument("--out", required=True)
    a = p.parse_args(); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    run(["kaggle","competitions","leaderboard",a.competition,"--show"], out/"leaderboard.txt")
    run(["kaggle","competitions","submissions",a.competition,"-v"], out/"submissions.csv")
    # TODO(episodes): our earlier replay analysis used kaggle-environments 1.32.7 replays.
    # Wire the ListEpisodes endpoint here to fetch the last 10-20 of OUR games for the
    # Claude Code + MCP diagnosis step. Left as a stub: competition-specific, unverified.
    (out/"README.txt").write_text(
        "leaderboard.txt / submissions.csv are refreshed by CI.\n"
        "Diagnosis of the last 10-20 games is done by Claude Code + Kaggle MCP, which\n"
        "writes its findings to analysis/ and opens a PR. Episode download is a TODO.\n")
    print("feedback pull done ->", out)

if __name__ == "__main__": main()
