"""Bundle the repo source into a self-contained Kaggle kernel script.

`kaggle kernels push` uploads only the file named by `code_file` -- it cannot carry
extra files -- and this repo is private, so the kernel cannot clone it either. So the
source it needs is embedded as a base64 tar.gz and unpacked at runtime.
"""
import base64, io, json, sys, tarfile
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
                print("  skip (absent):", name); continue
            if src.is_file():
                tar.add(src, arcname=name); print("  +", name); continue
            for f in sorted(src.rglob("*")):
                if f.is_file() and not any(p in SKIP for p in f.parts) and f.suffix != ".pyc":
                    tar.add(f, arcname=str(f.relative_to(ROOT)).replace("\\", "/"))
            print("  +", name + "/")
    return base64.b64encode(buf.getvalue()).decode()

def main():
    seeds = sys.argv[1] if len(sys.argv) > 1 else "24"
    slug = sys.argv[2] if len(sys.argv) > 2 else None
    print("packing kernel payload:")
    payload = build_payload()
    template = (ROOT / "kernel" / "run_template.py").read_text(encoding="utf-8")
    out = template.replace("__PAYLOAD__", payload).replace("__SEEDS__", seeds)
    (ROOT / "kernel" / "run.py").write_text(out, encoding="utf-8")
    print("kernel/run.py written: %.1f KB (payload %.1f KB)"
          % (len(out) / 1024, len(payload) / 1024))
    if slug:
        meta = ROOT / "kernel" / "kernel-metadata.json"
        m = json.loads(meta.read_text())
        m["id"] = slug
        # Kaggle requires the id's slug to equal the slugified title.
        m["title"] = slug.split("/")[-1]
        meta.write_text(json.dumps(m, indent=2) + "\n")
        print("metadata id/title ->", m["id"], "/", m["title"])

if __name__ == "__main__":
    main()
