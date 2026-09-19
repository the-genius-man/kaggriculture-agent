"""Submit to a Kaggle competition only if (a) confirm==SUBMIT and (b) today's
submission count is below the daily cap. Records the attempt to analysis/submissions_log.csv.
Kaggriculture is a Simulations/agent competition: verify the first real submission
registers the agent, not a CSV.

Quota check: `kaggle competitions submission-limits --json` is the real, documented
endpoint for this (kaggle-cli docs, kaggle>=2). Its exact JSON shape is not pinned
here, so this parses defensively and falls back to the old CSV-date-count heuristic
(counting today's date in `kaggle competitions submissions -v`) if the command is
missing, errors, or returns a shape we don't recognise -- this must never be *more*
permissive than before, only more accurate when it can be.
"""
import argparse, csv, datetime, json, os, re, subprocess, sys
from pathlib import Path


def _dig(obj, *keys):
    """First present int-like value at any of these keys, at top level or one
    level of nesting (the exact submission-limits schema is unconfirmed)."""
    def scan(o):
        if isinstance(o, dict):
            for k in keys:
                if k in o and isinstance(o[k], (int, float)):
                    return int(o[k])
            for v in o.values():
                r = scan(v)
                if r is not None:
                    return r
        elif isinstance(o, list):
            for v in o:
                r = scan(v)
                if r is not None:
                    return r
        return None
    return scan(obj)


def used_today_via_limits(comp):
    """Preferred path: the real quota endpoint. Returns None (not int(-1)) on any
    failure so the caller falls back rather than trusting a guess."""
    r = subprocess.run(["kaggle", "competitions", "submission-limits", comp, "--json"],
                        capture_output=True, text=True)
    if r.returncode != 0:
        print("submission-limits unavailable:", r.stderr.strip()[:200], file=sys.stderr)
        return None
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        print("submission-limits did not return JSON", file=sys.stderr)
        return None
    remaining = _dig(data, "remaining", "remainingSubmissions", "submissionsRemaining")
    limit = _dig(data, "limit", "dailyLimit", "maxSubmissions", "cap")
    used = _dig(data, "used", "submissionsToday", "submissionCount", "count")
    if used is not None:
        return used, limit
    if remaining is not None and limit is not None:
        return max(0, limit - remaining), limit
    print("submission-limits JSON had none of the expected keys: %s" % list(data)[:10],
          file=sys.stderr)
    return None


def used_today_via_csv(comp):
    """Fallback heuristic: count today's UTC date in the submissions list. Fragile
    (string match on a date, no timezone guarantee from Kaggle) -- kept only for when
    submission-limits itself is unavailable."""
    r = subprocess.run(["kaggle", "competitions", "submissions", comp, "-v"],
                        capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        return None
    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    n = 0
    for row in csv.reader(r.stdout.splitlines()[1:]):
        if row and today in ",".join(row):
            n += 1
    return n


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--file", required=True)
    p.add_argument("--message", required=True)
    p.add_argument("--confirm", required=True)
    p.add_argument("--cap", type=int, default=5)
    a = p.parse_args()
    comp = os.environ["COMPETITION"]
    if a.confirm.strip() != "SUBMIT":
        sys.exit("Refused: confirm was not 'SUBMIT'.")
    if not Path(a.file).exists():
        sys.exit(f"Refused: file not found: {a.file}")

    via_limits = used_today_via_limits(comp)
    if via_limits is not None:
        n, reported_cap = via_limits
        source = "submission-limits"
        cap = reported_cap if reported_cap else a.cap
    else:
        n = used_today_via_csv(comp)
        source = "date-count fallback"
        cap = a.cap
    if n is None:
        sys.exit("Refused: could not determine today's submission count from any source.")

    print(f"Submissions today: {n}/{cap}  (source: {source})")
    if n >= cap:
        sys.exit(f"Refused: daily cap reached ({n}/{cap}).")

    subprocess.run(["kaggle", "competitions", "submit", comp, "-f", a.file, "-m", a.message],
                    check=True)
    log = Path("analysis/submissions_log.csv")
    log.parent.mkdir(exist_ok=True, parents=True)
    new = not log.exists()
    with log.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["utc", "file", "message", "count_before", "cap", "source"])
        w.writerow([datetime.datetime.utcnow().isoformat(), a.file, a.message, n, cap, source])
    print("Submitted and logged.")


if __name__ == "__main__":
    main()
