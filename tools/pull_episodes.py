"""Fetch our real per-episode results, and which of our submissions are still active,
from Kaggle. Optionally download and render a few real replays.

This closes the "episode download" TODO. Verified 2026-09-19/20 (kaggle-cli docs,
kaggle>=2 installed by CI):
  - `kaggle competitions episodes <submission_id>` is the documented, official way to
    list a submission's episodes (this repo previously called the unauthenticated
    internal `competitions.EpisodeService/ListEpisodes` endpoint directly with
    `submissionId` -- that still works and is kept as a fallback needing no
    credentials, but the CLI command is the stable, documented surface).
  - `kaggle competitions team-submissions <team_id>` lists, per its own --help text,
    "every active submission for simulation competitions" -- this is the authoritative
    source for which submissions are still live, not a guess by submission date.
  - `kaggle competitions replay <episode_id>` downloads the real replay JSON. It was
    previously reported here as unavailable; that was only true of the raw internal
    GetEpisodeReplay endpoint called without a login. The documented CLI command
    works (needs the same KAGGLE_API_TOKEN as everything else in this repo).

Kaggle's rule for this class of competition (per Kaggle's own docs and confirmed by
the user): only your 2 most recent submissions keep receiving new episodes and count
for final scoring; older ones are frozen. `team-submissions` is asked first to confirm
this directly; if that call fails (e.g. no credentials), the two most recent
submissions by date are assumed active and this is stated in the output.
"""
import argparse, csv, json, statistics, subprocess, sys, urllib.request
from pathlib import Path

BASE = "https://www.kaggle.com/api/i/competitions.EpisodeService/"


def cli_json(args, timeout=120):
    """Run a kaggle CLI subcommand and parse --format json / --json output. Returns
    None (never raises) on any failure, so callers can fall back."""
    try:
        r = subprocess.run(["kaggle"] + args, capture_output=True, text=True, timeout=timeout)
    except Exception as e:
        print("warn: kaggle %s -> %s" % (" ".join(args), e), file=sys.stderr)
        return None
    if r.returncode != 0:
        print("warn: kaggle %s -> %s" % (" ".join(args), r.stderr.strip()[:200]), file=sys.stderr)
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        print("warn: kaggle %s did not return JSON" % " ".join(args), file=sys.stderr)
        return None


def active_submission_ids(team_id):
    """The submissions Kaggle is still matching, per its own team-submissions call.
    Returns a set of submission-id strings, or None if the call failed."""
    d = cli_json(["competitions", "team-submissions", str(team_id), "--format", "json"])
    if d is None:
        return None
    ids = set()
    rows = d if isinstance(d, list) else d.get("submissions", d.get("teamSubmissions", []))
    for row in rows if isinstance(rows, list) else []:
        sid = row.get("id") or row.get("submissionId") or row.get("ref")
        if sid is not None:
            ids.add(str(sid))
    return ids or None


def call_unauth(method, payload, timeout=90):
    """Fallback: the unauthenticated internal endpoint. No credentials needed, and
    verified 2026-09-19 to still work with `submissionId` (teamId is no longer
    accepted). Kept only for when the CLI/credentials are unavailable."""
    req = urllib.request.Request(BASE + method, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def episodes_for(submission_id):
    """Try the documented CLI first, fall back to the unauthenticated internal call.
    Normalises both into the same row shape."""
    d = cli_json(["competitions", "episodes", str(submission_id), "--format", "json"])
    if d is not None:
        rows = d if isinstance(d, list) else d.get("episodes", [])
        out = []
        for e in rows:
            if e.get("state") not in (None, "COMPLETED", "EPISODE_STATE_COMPLETE"):
                continue
            our_cash = e.get("reward") if "reward" in e else e.get("ourReward")
            opp_cash = e.get("opponentReward")
            if our_cash is None or opp_cash is None:
                continue  # CLI schema unconfirmed; skip rows we can't interpret safely
            out.append({"episode": e.get("id") or e.get("episodeId"), "end": e.get("endTime"),
                        "our_cash": our_cash, "opp_cash": opp_cash, "won": our_cash > opp_cash,
                        "opponent": e.get("opponentTeamName") or e.get("opponent")})
        if out:
            return out
        print("warn: CLI episodes call returned no usable rows for %s, falling back"
              % submission_id, file=sys.stderr)
    try:
        d = call_unauth("ListEpisodes", {"submissionId": int(submission_id)})
    except Exception as e:
        print("warn: unauth episode fetch failed for %s: %s" % (submission_id, e), file=sys.stderr)
        return []
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
                     "opponent": names.get(opp.get("teamId")) or opp.get("teamId")})
    return rows


def fetch_replay(episode_id, out_dir):
    """Download a real replay via the documented CLI. Returns the saved path, or None."""
    out_dir.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["kaggle", "competitions", "replay", str(episode_id), "-p", str(out_dir)],
                        capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        print("warn: replay download failed for episode %s: %s"
              % (episode_id, r.stderr.strip()[:200]), file=sys.stderr)
        return None
    matches = sorted(out_dir.glob(f"*{episode_id}*"))
    return matches[0] if matches else None


def render_replay_html(replay_path, out_path):
    """Reconstruct the game from a downloaded replay JSON and render playable HTML.
    Verified: kaggle_environments' own toJSON() round-trips through make(steps=...);
    Kaggle's downloaded replay follows the same engine and should carry the same
    'configuration'/'steps' shape."""
    import contextlib, io
    data = json.loads(Path(replay_path).read_text(encoding="utf-8"))
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        from kaggle_environments import make
    env = make("kaggriculture", configuration=data.get("configuration", {}), steps=data["steps"])
    out_path.write_text(env.render(mode="html", width=1000, height=700), encoding="utf-8")
    return [s.reward for s in env.steps[-1]]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--submissions", default="analysis/feedback/submissions.csv")
    p.add_argument("--team-id", default=None, help="verify active submissions via team-submissions")
    p.add_argument("--out", default="analysis/feedback")
    p.add_argument("--limit", type=int, default=6, help="how many recent submissions to check")
    p.add_argument("--replays", type=int, default=0,
                    help="download + render this many worst losses as local HTML (needs auth)")
    a = p.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    subs = list(csv.DictReader(open(a.submissions, encoding="utf-8", errors="replace")))[:a.limit]

    active_ids = active_submission_ids(a.team_id) if a.team_id else None
    if active_ids is None:
        # Kaggle's own rule (confirmed): only the 2 most recent submissions stay
        # active. submissions.csv is already newest-first.
        active_ids = {s["ref"] for s in subs[:2]}
        active_source = "assumed: 2 most recent by date (team-submissions unavailable)"
    else:
        active_source = "confirmed via team-submissions"
    print("active submissions (%s): %s" % (active_source, sorted(active_ids)))

    report, everything, worst_overall = [], {}, []
    for s in subs:
        sid, name = s.get("ref"), s.get("fileName")
        if not (sid or "").isdigit():
            continue
        is_active = sid in active_ids
        rows = episodes_for(sid)
        everything[sid] = {"file": name, "active": is_active, "episodes": rows}
        status = "ACTIVE" if is_active else "frozen"
        if not rows:
            print("%-14s [%s] %s: no completed episodes" % (name, status, sid))
            continue
        wr = statistics.mean(r["won"] for r in rows)
        line = ("%-14s [%s] %3d games  win %5.1f%%  our cash %6d  opp cash %6d"
                % (name, status, len(rows), 100 * wr,
                   statistics.mean(r["our_cash"] for r in rows),
                   statistics.mean(r["opp_cash"] for r in rows)))
        print(line)
        report.append(line)
        for r in rows:
            worst_overall.append({**r, "submission": sid, "file": name})

    (out / "episodes.json").write_text(json.dumps(everything, indent=1), encoding="utf-8")
    (out / "episodes_summary.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("->", out / "episodes.json")

    if a.replays and worst_overall:
        worst = sorted(worst_overall, key=lambda r: r["our_cash"] - r["opp_cash"])[:a.replays]
        replay_dir = out / "replays"
        html_dir = out / "replays_html"
        for r in worst:
            raw = fetch_replay(r["episode"], replay_dir)
            if not raw:
                continue
            try:
                html_path = html_dir / f"episode_{r['episode']}.html"
                html_dir.mkdir(parents=True, exist_ok=True)
                cash = render_replay_html(raw, html_path)
                print("rendered", html_path, "final cash", cash)
            except Exception as e:
                print("warn: could not render episode %s: %s" % (r["episode"], e), file=sys.stderr)


if __name__ == "__main__":
    main()
