"""Locate a strong leaderboard team's current submission id, so its real games can be
listed and downloaded.

Why this exists: Kaggle matches us against similarly-rated opponents, so our own
episodes only ever contain mid-field play. Measured 2026-09-23: across 233 distinct
opponents in our episode history, ZERO appear in the leaderboard top 20. To study how
the actual leaders play we have to fetch *their* episodes, which needs their
submission id.

`competitions.EpisodeService/ListEpisodes` only accepts `submissionId` (a `teamId`
payload 400s), but its response carries a `teams` array whose entries include
`publicLeaderboardSubmissionId`. So a best-first crawl over the episode graph --
always expanding the highest-rated agent seen so far, since each episode exposes both
agents' Elo -- reaches the top of the table quickly. Measured: 2 calls to surface a
rank-2 team. No credentials needed; this is the public read-only endpoint.
"""
import argparse, heapq, json, re, sys, urllib.request
from pathlib import Path

BASE = "https://www.kaggle.com/api/i/competitions.EpisodeService/"


def call(method, payload, timeout=60):
    req = urllib.request.Request(BASE + method, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def leaderboard_team_ids(path):
    """teamId -> (name, score) from a saved `kaggle competitions leaderboard` dump."""
    out = {}
    if not Path(path).exists():
        return out
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"\s*(\d+)\s+(.+?)\s+\d{4}-\d{2}-\d{2} [\d:.]+\s+([\d.]+)\s*$", line)
        if m:
            out[int(m.group(1))] = (m.group(2).strip(), float(m.group(3)))
    return out


def crawl(seed_submission, targets, max_calls=40):
    """Best-first over the episode graph. Returns (hits, ranked_agents, teams)."""
    seen, teams, best, hits = set(), {}, {}, {}
    frontier = [(-600.0, int(seed_submission))]
    calls = 0
    while frontier and calls < max_calls:
        _, sid = heapq.heappop(frontier)
        if sid in seen:
            continue
        seen.add(sid)
        calls += 1
        try:
            d = call("ListEpisodes", {"submissionId": int(sid)})
        except Exception as e:
            print("warn: ListEpisodes(%s) -> %s" % (sid, str(e)[:100]), file=sys.stderr)
            continue
        for t in d.get("teams", []):
            teams[t["id"]] = t.get("teamName")
            lb_sub = t.get("publicLeaderboardSubmissionId")
            if lb_sub and (not targets or t["id"] in targets):
                hits[t["id"]] = {"team": t.get("teamName"), "submission": lb_sub}
        for e in d.get("episodes", []):
            for a in e.get("agents", []):
                score = a.get("updatedScore") or a.get("initialScore") or 0
                asid, tid = a.get("submissionId"), a.get("teamId")
                if tid and (tid not in best or score > best[tid][0]):
                    best[tid] = (score, asid)
                if asid and asid not in seen:
                    heapq.heappush(frontier, (-score, asid))
        if targets and hits:
            break
    ranked = sorted(({"team": teams.get(t, t), "team_id": t, "rating": round(s, 1),
                      "submission": sub} for t, (s, sub) in best.items()),
                    key=lambda r: -r["rating"])
    return hits, ranked, calls


def episodes_for(submission_id):
    d = call("ListEpisodes", {"submissionId": int(submission_id)})
    names = {t["id"]: t.get("teamName") for t in d.get("teams", [])}
    rows = []
    for e in d.get("episodes", []):
        if e.get("state") != "COMPLETED":
            continue
        me = next((a for a in e["agents"] if a.get("submissionId") == int(submission_id)), None)
        op = next((a for a in e["agents"] if a.get("submissionId") != int(submission_id)), None)
        if not me or not op or me.get("reward") is None or op.get("reward") is None:
            continue
        rows.append({"episode": e["id"], "our_cash": me["reward"], "opp_cash": op["reward"],
                     "won": me["reward"] > op["reward"], "end": e.get("endTime"),
                     "opp_rating": round(op.get("updatedScore") or op.get("initialScore") or 0, 1),
                     "opponent": names.get(op.get("teamId")) or op.get("teamId")})
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--seed", default="56475549", help="a submission id to start crawling from")
    p.add_argument("--leaderboard", default="analysis/feedback/leaderboard.txt")
    p.add_argument("--max-calls", type=int, default=40)
    p.add_argument("--out", default="analysis/feedback/top_players.json")
    p.add_argument("--episodes-for", default=None,
                    help="skip the crawl and just list this submission's episodes")
    p.add_argument("--print-submission", action="store_true",
                    help="print only the best leader submission id (for shell capture)")
    a = p.parse_args()

    if a.episodes_for:
        rows = episodes_for(a.episodes_for)
        print(json.dumps(rows, indent=1))
        return

    targets = leaderboard_team_ids(a.leaderboard)
    if not a.print_submission:
        print("leaderboard targets:", len(targets))
    hits, ranked, calls = crawl(a.seed, set(targets), a.max_calls)
    result = {"calls": calls, "leaderboard_hits": [], "strongest_seen": ranked[:15]}
    for tid, h in hits.items():
        name, score = targets.get(tid, (h["team"], None))
        result["leaderboard_hits"].append({"team_id": tid, "team": name,
                                            "leaderboard_score": score,
                                            "submission": h["submission"]})
    # Prefer the highest-scoring confirmed leaderboard team; fall back to the
    # strongest agent the crawl saw at all.
    result["leaderboard_hits"].sort(key=lambda h: -(h["leaderboard_score"] or 0))
    chosen = (result["leaderboard_hits"] or result["strongest_seen"] or [{}])[0]
    result["chosen"] = chosen

    if a.print_submission:
        print(chosen.get("submission", ""))
        return

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result, indent=1)[:2000])
    print("->", a.out)


if __name__ == "__main__":
    main()
