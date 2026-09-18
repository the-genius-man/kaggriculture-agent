# Kaggle kernel body. Clones the repo at a fixed ref, installs pinned deps, runs the
# bounded validation, and writes main.py + validation.json to /kaggle/working.
# Placeholders __REPO__ and __REF__ are filled by the train workflow before push.
# Private repo: add a GitHub PAT as a Kaggle secret and use it in the clone URL.
import subprocess, sys, os

REPO = "__REPO__"      # e.g. owner/name
REF  = "__REF__"       # commit sha or branch
WORK = "/kaggle/working"

def sh(*c): subprocess.run(list(c), check=True)

sh("git", "clone", "--depth", "1", f"https://github.com/{REPO}.git", "src")
os.chdir("src"); sh("git", "fetch", "--depth", "1", "origin", REF); sh("git", "checkout", REF)
sh(sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt")
# Bounded validation: validate the current candidate vs V9/V12 on fresh holdout seeds,
# export main.py, write validation.json. (Full search is a separate, longer kernel.)
sh(sys.executable, "experiments/validate.py", "--out", WORK, "--seeds", "24")
print("kernel done ->", os.listdir(WORK))
