"""Submit to a Kaggle competition only if (a) confirm==SUBMIT and (b) today's
submission count is below the daily cap. Records the attempt to analysis/submissions_log.csv.
Kaggriculture is a Simulations/agent competition: verify the first real submission
registers the agent, not a CSV."""
import argparse, csv, datetime, os, subprocess, sys
from pathlib import Path

def today_count(comp):
    r = subprocess.run(["kaggle","competitions","submissions",comp,"-v"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr); return None
    today = datetime.datetime.utcnow().strftime("%Y-%m-%d"); n = 0
    for row in csv.reader(r.stdout.splitlines()[1:]):    # header + rows
        if row and today in ",".join(row): n += 1
    return n

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--file", required=True); p.add_argument("--message", required=True)
    p.add_argument("--confirm", required=True); p.add_argument("--cap", type=int, default=5)
    a = p.parse_args(); comp = os.environ["COMPETITION"]
    if a.confirm.strip() != "SUBMIT":
        sys.exit("Refused: confirm was not 'SUBMIT'.")
    if not Path(a.file).exists():
        sys.exit(f"Refused: file not found: {a.file}")
    n = today_count(comp)
    if n is None: sys.exit("Refused: could not read submission history.")
    print(f"Submissions today: {n}/{a.cap}")
    if n >= a.cap: sys.exit(f"Refused: daily cap reached ({n}/{a.cap}).")
    subprocess.run(["kaggle","competitions","submit",comp,"-f",a.file,"-m",a.message], check=True)
    log = Path("analysis/submissions_log.csv"); log.parent.mkdir(exist_ok=True, parents=True)
    new = not log.exists()
    with log.open("a", newline="") as f:
        w = csv.writer(f)
        if new: w.writerow(["utc","file","message","count_before","cap"])
        w.writerow([datetime.datetime.utcnow().isoformat(), a.file, a.message, n, a.cap])
    print("Submitted and logged.")

if __name__ == "__main__": main()
