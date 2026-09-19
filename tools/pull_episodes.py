"""Fetch our real per-episode results from Kaggle's episode API.

This closes the "episode download" TODO that this repo has carried. It is the only
source of *measured* leaderboard performance: per game, our cash, the opponent's
cash, who they were, and the rating before/after.

Notes, verified 2026-09-19:
  - the endpoint is unauthenticated, so this needs no Kaggle credentials;
  - `teamId` is NO LONGER an accepted filter ("You must specify at least one ID
    filter"); `submissionId` is;
  - GetEpisodeReplay 404s unauthenticated, so full replays are still not downloadable
    here. Only results are.
"""
import argparse, csv, json, statistics, urllib.request
from pathlib import Path

BASE = "https://www.kaggle.com/api/i/competitions.EpisodeService/"

def call(method, payload, timeout=120):
    req = urllib.request.Request(BASE + method, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

def episodes_for(submission_id):
    d = call("ListEpisodes", {"submissionId": int(submission_id)})
    names = {t["id"]: t.get("teamName") for t in d.get("teams", [])}
    rows = []
    for e in d.get("episodes", []):
        if e.get("state") != "COMPLETED":
            continue
        me = next((a for a in e["agents"] if a.get("submissionId") == int(submission_id)), None)
        opp = next((a for a in e["agents"] if a.get("submissionId") != int(submission_id)), None)
        if not me or not opp or me.get("reward") is None or opp.get("reward") is None:
            continue
        rows.append({"episode": e["id"], "end": e.get("endTime"),
                     "our_cash": me["reward"], "opp_cash": opp["reward"],
                     "won": me["reward"] > opp["reward"],
                     "opponent": names.get(opp.get("teamId")) or opp.get("teamId"),
                     "rating_before": me.get("initialScore"), "rating_after": me.get("updatedScore")})
    rows.sort(key=lambda r: r["end"] or "")
    return rows

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--submissions", default="analysis/feedback/submissions.csv")
    p.add_argument("--out", default="analysis/feedback")
    p.add_argument("--limit", type=int, default=6, help="how many recent submissions")
    a = p.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    subs = list(csv.DictReader(open(a.submissions, encoding="utf-8", errors="replace")))[:a.limit]
    report, everything = [], {}
    for s in subs:
        sid, name = s.get("ref"), s.get("fileName")
        if not (sid or "").isdigit():
            continue
        try:
            rows = episodes_for(sid)
        except Exception as e:                      # never fail the whole pull on one id
            print("warn %s (%s): %s" % (name, sid, e)); continue
        everything[sid] = {"file": name, "episodes": rows}
        if not rows:
            print("%-14s %s: no completed episodes yet" % (name, sid)); continue
        wr = statistics.mean(r["won"] for r in rows)
        line = ("%-14s %3d games  win %5.1f%%  our cash %6d  opp cash %6d  rating %.1f"
                % (name, len(rows), 100 * wr, statistics.mean(r["our_cash"] for r in rows),
                   statistics.mean(r["opp_cash"] for r in rows), rows[-1]["rating_after"] or 0))
        print(line); report.append(line)
        for r in sorted(rows, key=lambda r: r["our_cash"] - r["opp_cash"])[:3]:
            sub = "      worst loss vs %-20s %6d vs %6d" % (str(r["opponent"])[:20], r["our_cash"], r["opp_cash"])
            print(sub); report.append(sub)
    (out / "episodes.json").write_text(json.dumps(everything, indent=1), encoding="utf-8")
    (out / "episodes_summary.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("->", out / "episodes.json")

if __name__ == "__main__":
    main()
