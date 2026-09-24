"""Download a study set of real replays: our worst losses, and a leaderboard leader's wins.

Two sources, because they answer different questions:
  * our own losses  -> what our agent does wrong against the field it actually meets;
  * a top team's wins -> what a 3000-rated policy does, which our episodes never show
    (measured 2026-09-23: none of the 233 opponents we have faced is in the top 20,
    because matchmaking pairs similar ratings).

Episode listing uses the public read-only endpoint (no credentials). Replay download
uses `kaggle competitions replay`, which does need KAGGLE_API_TOKEN, so this is meant
to run in CI. Raw replays stay a private artifact; tools/analyze_replays.py turns them
into the compact summary that is safe and cheap to move around.
"""
import argparse, csv, json, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from find_top_submissions import episodes_for  # noqa: E402


def download(episode_id, out_dir, retries=2):
    out_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(out_dir.glob(f"*{episode_id}*"))
    if existing:
        return existing[0]
    for attempt in range(retries + 1):
        r = subprocess.run(["kaggle", "competitions", "replay", str(episode_id),
                            "-p", str(out_dir)], capture_output=True, text=True, timeout=300)
        if r.returncode == 0:
            hit = sorted(out_dir.glob(f"*{episode_id}*"))
            if hit:
                return hit[0]
        print("warn: replay %s attempt %d -> %s" % (episode_id, attempt + 1,
              (r.stderr or r.stdout).strip()[:160]), file=sys.stderr)
        time.sleep(3)
    return None


def recent_submissions(path, limit):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("ref"):
                rows.append((row["ref"], row.get("fileName", "?")))
    return rows[:limit]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--submissions", default="analysis/feedback/submissions.csv")
    p.add_argument("--ours", type=int, default=3, help="how many of our recent submissions")
    p.add_argument("--losses", type=int, default=10, help="worst losses per submission")
    p.add_argument("--wins", type=int, default=0,
                    help="best wins per submission too -- losses alone bias the picture,"
                         " since they cannot show what the agent does when it works")
    p.add_argument("--top-submission", default=None, help="a leader's submission id")
    p.add_argument("--top-wins", type=int, default=5)
    p.add_argument("--out", default="analysis/feedback/study")
    a = p.parse_args()

    out = Path(a.out)
    index = {"ours": [], "leader": []}

    for sid, name in recent_submissions(a.submissions, a.ours):
        try:
            rows = episodes_for(sid)
        except Exception as e:
            print("warn: could not list episodes for %s: %s" % (sid, str(e)[:120]), file=sys.stderr)
            continue
        losses = sorted((r for r in rows if not r["won"]),
                        key=lambda r: r["our_cash"] - r["opp_cash"])[:a.losses]
        wins = sorted((r for r in rows if r["won"]),
                      key=lambda r: -(r["our_cash"] - r["opp_cash"]))[:a.wins]
        print("%s (%s): %d episodes, taking %d worst losses and %d best wins"
              % (sid, name, len(rows), len(losses), len(wins)))
        for r in losses + wins:
            path = download(r["episode"], out / ("ours_%s" % sid))
            if path:
                index["ours"].append({**r, "submission": sid, "file": path.name,
                                       "agent": name})

    if a.top_submission:
        try:
            rows = episodes_for(a.top_submission)
        except Exception as e:
            print("warn: leader episode list failed: %s" % str(e)[:120], file=sys.stderr)
            rows = []
        wins = sorted((r for r in rows if r["won"]),
                      key=lambda r: -(r["our_cash"] - r["opp_cash"]))[:a.top_wins]
        print("leader %s: %d episodes, taking %d best wins" % (a.top_submission, len(rows), len(wins)))
        for r in wins:
            path = download(r["episode"], out / ("leader_%s" % a.top_submission))
            if path:
                index["leader"].append({**r, "submission": a.top_submission, "file": path.name})

    out.mkdir(parents=True, exist_ok=True)
    (out / "index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
    print("downloaded: %d of ours, %d leader" % (len(index["ours"]), len(index["leader"])))
    print("->", out / "index.json")


if __name__ == "__main__":
    main()
