"""Poll a kernel until it completes; exit non-zero on error/timeout."""
import subprocess, sys, time
slug = sys.argv[1]
hours = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0   # search.yml passes a longer one
deadline = time.time() + hours*3600
while time.time() < deadline:
    out = subprocess.run(["kaggle","kernels","status",slug], capture_output=True, text=True)
    s = (out.stdout + out.stderr).lower(); print(s.strip())
    if "complete" in s: sys.exit(0)
    if "error" in s or "failed" in s: sys.exit(1)
    time.sleep(30)
print("timeout waiting for kernel"); sys.exit(1)
