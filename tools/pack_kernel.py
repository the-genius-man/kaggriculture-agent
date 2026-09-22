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
    What search.yml runs. Pass --checkpoint-dataset <owner/slug> to resume a prior
    run's checkpoint.zip instead of starting a fresh League from cycle 0. It can't be
    embedded like the source payload -- checkpoint.zip runs ~2MB and Kaggle caps
    kernel *script* source at 1MB (a real 400 from SaveKernel, confirmed 2026-09-22)
    -- so search.yml uploads it as a private Kaggle Dataset first and this just wires
    that dataset into kernel-metadata.json's dataset_sources. Kaggle mounts it at
    /kaggle/input/<slug>/checkpoint.zip, and run_search_template.py unpacks it into
    /kaggle/working before League() is constructed. League's own manifest check
    (league.py's __init__) still guards this: if league.py/support.py/
    policy_template.py/the fixed agents changed since the checkpoint was made, the
    resume is refused, not silently corrupted.
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


def write_metadata(slug, checkpoint_dataset=None):
    meta = ROOT / "kernel" / "kernel-metadata.json"
    m = json.loads(meta.read_text())
    m["id"] = slug
    # Kaggle requires the id's slug to equal the slugified title, so this must
    # always be derived from `slug`, not a separate name. search.yml passes its own
    # distinct slug (KERNEL_SLUG-search) so the two kernels never collide.
    m["title"] = slug.split("/")[-1]
    # Always set explicitly (not just when resuming) so a stale dataset_sources from
    # a previous resume run doesn't leak into this file's checked-in state.
    m["dataset_sources"] = [checkpoint_dataset] if checkpoint_dataset else []
    meta.write_text(json.dumps(m, indent=2) + "\n")
    print("metadata id/title ->", m["id"], "/", m["title"],
          "dataset_sources ->", m["dataset_sources"])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["validate", "search"], default="validate")
    p.add_argument("--seeds", default="24", help="validate mode: holdout seeds per opponent")
    p.add_argument("--seed-base", default="40000000",
                    help="validate mode: first seed (validate.py's own default); pass a different"
                         " base for a genuinely independent second sample, not just a bigger one")
    p.add_argument("--minutes", default="150", help="search mode: time budget for this run")
    p.add_argument("--slug", default=None, help="Kaggle kernel slug, e.g. user/kaggriculture-agent")
    p.add_argument("--checkpoint-dataset", default=None,
                    help="search mode: owner/slug of a Kaggle Dataset holding checkpoint.zip to resume from")
    a = p.parse_args()
    print("packing kernel payload (mode=%s):" % a.mode)
    payload = build_payload()

    if a.mode == "validate":
        template_name = "run_template.py"
        substitutions = {"__PAYLOAD__": payload, "__SEEDS__": a.seeds, "__SEED_BASE__": a.seed_base}
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
        write_metadata(a.slug, a.checkpoint_dataset)


if __name__ == "__main__":
    main()
