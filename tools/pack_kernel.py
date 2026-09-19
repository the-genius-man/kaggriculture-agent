"""Bundle the repo source into a self-contained Kaggle kernel script.

`kaggle kernels push` uploads only the file named by `code_file` -- it cannot carry
extra files -- and this repo is private, so the kernel cannot clone it either. So the
source it needs is embedded as a base64 tar.gz and unpacked at runtime.

Two modes:
  validate (default) -- kernel/run_template.py: renders candidate.json through
    policy_template.py, plays the one-shot promotion gate on fresh seeds, exports
    main.py + validation.json. What train.yml runs.
  search -- kernel/run_search_template.py: runs the resumable Optuna league
    (league/league.py) for a bounded time budget against the full opponent pool.
    What search.yml runs.
"""
import argparse, base64, io, json, sys, tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INCLUDE = ["policy", "league", "agents", "experiments", "candidate.json", "requirements.txt"]
SKIP = {"__pycache__"}


def build_payload():
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name in INCLUDE:
            src = ROOT / name
            if not src.exists():
                print("  skip (absent):", name)
                continue
            if src.is_file():
                tar.add(src, arcname=name)
                print("  +", name)
                continue
            for f in sorted(src.rglob("*")):
                if f.is_file() and not any(p in SKIP for p in f.parts) and f.suffix != ".pyc":
                    tar.add(f, arcname=str(f.relative_to(ROOT)).replace("\\", "/"))
            print("  +", name + "/")
    return base64.b64encode(buf.getvalue()).decode()


def write_metadata(slug):
    meta = ROOT / "kernel" / "kernel-metadata.json"
    m = json.loads(meta.read_text())
    m["id"] = slug
    # Kaggle requires the id's slug to equal the slugified title, so this must
    # always be derived from `slug`, not a separate name. search.yml passes its own
    # distinct slug (KERNEL_SLUG-search) so the two kernels never collide.
    m["title"] = slug.split("/")[-1]
    meta.write_text(json.dumps(m, indent=2) + "\n")
    print("metadata id/title ->", m["id"], "/", m["title"])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["validate", "search"], default="validate")
    p.add_argument("--seeds", default="24", help="validate mode: holdout seeds per opponent")
    p.add_argument("--minutes", default="150", help="search mode: time budget for this run")
    p.add_argument("--slug", default=None, help="Kaggle kernel slug, e.g. user/kaggriculture-agent")
    a = p.parse_args()
    print("packing kernel payload (mode=%s):" % a.mode)
    payload = build_payload()

    if a.mode == "validate":
        template_name = "run_template.py"
        substitutions = {"__PAYLOAD__": payload, "__SEEDS__": a.seeds}
    else:
        template_name = "run_search_template.py"
        substitutions = {"__PAYLOAD__": payload, "__MINUTES__": a.minutes}

    template = (ROOT / "kernel" / template_name).read_text(encoding="utf-8")
    for k, v in substitutions.items():
        template = template.replace(k, v)
    (ROOT / "kernel" / "run.py").write_text(template, encoding="utf-8")
    print("kernel/run.py written: %.1f KB (payload %.1f KB)"
          % (len(template) / 1024, len(payload) / 1024))
    if a.slug:
        write_metadata(a.slug)


if __name__ == "__main__":
    main()
