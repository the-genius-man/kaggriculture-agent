# CLAUDE.md — working agreement for the Kaggriculture agent

This file is guidance for Claude Code (and any assistant) working in this repo.
Read it before changing code. It encodes hard constraints and the honesty rules
that this project has depended on.

## What this project is

An agent for the Kaggle **Kaggriculture** competition (`kaggle-environments`
`kaggriculture`, a 720-step / 30-day two-farm game; final cash is the reward).
The policy is an explicit, parameterised Python scorer, not a neural net. Stronger
agents are found by Optuna TPE search over the policy's parameters, validated by a
self-play league with strict promotion gates.

## Hard constraints (do not silently change these)

- **Pinned dependencies:** `kaggle-environments==1.32.7`, `optuna==4.5.0`. The
  simulator version is part of the game-cache key and the league manifest. Changing
  it invalidates cached games and checkpoints.
- **Promotion gates (unchanged since V12/V13):** a challenger is promoted only if,
  on **fresh unseen seeds**, it beats **V9 >= 80%**, the **current champion >= 60%**,
  and **every** league opponent **>= 55%**, each with a positive mean margin and a
  positive seed-bootstrap lower bound. If nothing qualifies, keep the incumbent.
- **Always keep V9 and V13 as comparison baselines** and run **fresh holdouts**
  (>= 24 seeds, both seats). Never evaluate only on training seeds.
- **Preserve exact fallbacks.** `agents/main_v12.py` is the confirmed champion
  (V12 trial-23, `sha256 dffae949e74e...`). Never overwrite a known-good agent; add
  a new versioned file instead.
- **Explicit version numbering.** Every candidate policy and notebook carries its
  version. Do not reuse a version number for different code.
- **Kaggle limits:** at most **5 submissions per day**. **Check the actual remaining
  quota before any submission.** No submission automation is wired up here.
- **Kaggle access is via an optional MCP connection (see "Kaggle MCP" below), not
  assumed.** If it is connected: reads (leaderboard, submissions, remaining quota,
  competition/dataset/kernel files) may be used freely; **a submission is taken only
  on explicit human approval, one at a time, after checking the day's remaining
  quota**. Never automate the 5th-of-5 away.
- **Long training runs belong on Kaggle or Colab**, not on a local machine that may
  shut down. Use `notebooks/kaggriculture_enhanced_game_v2.ipynb` there. Use Claude
  Code locally for development, tests and orchestration, then pull artifacts
  (`main.py`, checkpoint, reports) back into the repo.

## Honesty rules (these matter as much as the code)

- **Report measured results, not assumed ones.** Distinguish Kaggle rating, Optuna
  objective values and in-game cash: they are different quantities.
- **Self-play / reconstructed opponents are not leaderboard opponents.** Beating V9
  or V12 in the internal league does not prove a leaderboard gain.
- **Replaying an opponent's fixed recorded actions against a changed agent is
  open-loop.** It shows what happened; it does not prove you would beat that adaptive
  opponent. Validate changes in the league, not only against replays.
- **Gross sales are not profit.** Strawberry/wheat/fertilizer turnover includes
  feeding, inventory and market churn. Ablate market behaviour before copying it.
- **A higher maximum cash in one game does not establish a stronger policy.** There
  is no income ceiling and none should be imposed.

## Current status (as of V14 work)

- Confirmed champion / fallback: **V12 trial-23** (`agents/main_v12.py`).
- Head-to-head measurement (single-CPU, small samples): V12's edge over V9 is small
  and noisy. Beating V9 *decisively and repeatably* is the real bar.
- **Enhanced Game v2** (`notebooks/`) adds phase-dependent policy params, a throughput
  auto-benchmark (a GPU does not accelerate this CPU simulator; profiling showed the
  time is Python deepcopy/struct/validation), and one widened bound (`plant_floor`).
- **V14** (`policy/policy_template.py`, `league/`): two evidence-based changes from the
  leaderboard-replay analysis:
  1. **Melon maturity fix.** `MELON` peak corrected `10 -> 12` to match the engine's
     growth window, so melons are harvested yield-aware (at 6 units or the window
     end) instead of force-harvested at age 10 below max. Measured: premature sub-6
     melon harvests dropped from ~90% to ~0-5%.
  2. **Strawberry occupancy target** (`strawberry_target`, searchable): suppress the
     per-plot saturation discount until a target strawberry count is established.
     Measured: day-20 strawberries ~5 -> ~13-15 (wheat rebalanced down, not removed).
- **Not yet closed:** productive **occupancy**. V13 fills ~45/75 tiles at day 20; the
  strongest observed opponent (Boey) fills ~75/75. V14 is ~49-51. The biggest lever
  from the analysis is still open.

## What the leaderboard analysis says to work on next

See `analysis/REPORT_boey_leaders.md` (4 Boey wins) and the V13 loss diagnosis.
Priorities, in order:

1. **Productive occupancy / crop scheduling.** Fill owned, reachable tiles early;
   establish a large strawberry crop by ~day 10-15 the way Boey does, then rotate to
   short-cycle crops late. This is the main gap.
2. **Routing / job allocation.** Boey used fewer move commands and more harvests at
   the same worker cap. Tune region homes, commitment and distance weighting; the
   worker ceiling is not the problem.
3. **Season-aware crop replacement** (early melon -> dense strawberry -> late wheat/
   short crops), driven by remaining game horizon.
4. **Fourth quadrant as a *tested* option**, evaluated together with planting,
   staffing, routing and time-to-recover. Do not force it (opponents beat V13 with
   three quadrants) and do not assume three is optimal.
5. **Market-transaction ablation** before imitating heavy wheat/fertilizer churn.

Do each as an explicit candidate with paired seeds, both seats, the same opponent
pool, against V9 and V13. Do not change all settings at once.

## Pipeline (GitHub Actions + kernel + MCP)

Two planes. **CI plane** = deterministic Kaggle-CLI scripts in `.github/workflows`:
`train.yml` pushes `kernel/` to a Kaggle Kernel, which clones the repo, runs
`experiments/validate.py` (renders `candidate.json`, plays the gate vs V9/V12/V13 on
fresh seeds), and returns `main.py` + `validation.json`; the workflow opens a PR.
`pull-feedback.yml` refreshes leaderboard + our submissions into `analysis/feedback/`.
`submit.yml` is manual, needs the `production` environment approval AND passes
`tools/submit_guarded.py` (same-day quota check vs `DAILY_SUBMISSION_CAP`).

**Reasoning plane** = Claude Code + Kaggle MCP: reads the pulled replays/leaderboard,
diagnoses the last 10-20 games, writes findings to `analysis/`, and opens a code PR.

**Two human gates, always:** merging a candidate PR, and approving a submission. The
loop never merges its own code or spends a submission on its own.

Repo config needed: secrets `KAGGLE_USERNAME`, `KAGGLE_KEY`; vars `KERNEL_SLUG`,
`KAGGLE_COMPETITION`, `DAILY_SUBMISSION_CAP`; a `production` environment with a
required reviewer. Note: a kernel cannot reliably self-submit an agent competition, so
produce (auto) and submit (gated) are separate; and episode/replay download is a
competition-specific TODO in `tools/pull_feedback.py`.

## Kaggle MCP (optional connection)

A Kaggle MCP server lets Claude Code talk to the Kaggle API directly: list/download
competition files, view the leaderboard and your submission history, push/pull
Kaggle Kernels, manage datasets, and submit. This closes the loop the project has
lacked (a real external score, and persistent runs on a Kernel instead of a local
machine). It does not change the honesty rules or the promotion gates.

Community servers exist (e.g. PyPI `mcp-server-kaggle`, `Seif-Sameh/Kaggle-mcp`,
`Dishant27/kaggle-MCP`, `54yyyu/kaggle-mcp`) plus a hosted Composio connector. They
are third-party and hold a full-access Kaggle key, so:

- **Secrets:** put credentials in the environment (`KAGGLE_USERNAME`, `KAGGLE_KEY`) or
  a gitignored `~/.kaggle/kaggle.json`. Never commit them. `.mcp.json` here uses
  `${VAR}` expansion so no key is stored in the repo. Review the server source (or use
  a vetted host) before trusting it with the key; prefer least privilege.
- **Submission governance:** read tools are fine to use on your own. `competition_submit`
  is human-approved only, one at a time, after a quota check. Kaggriculture is an
  agent/episode ("Simulations") competition, so confirm the first real submission
  registers the agent correctly rather than assuming the CSV path applies.
- **Loop:** use the MCP to pull leaderboard + submission scores back into `analysis/`
  and to run the league on a Kernel; keep exported `main.py` and checkpoints in the
  repo. The external score is the metric of record; the internal league is a proxy.

Setup sketch: copy `.mcp.json.example` to `.mcp.json`, point it at your chosen server,
export the two env vars, and start Claude Code in the repo.

## How to run

- **Full league (Kaggle/Colab):** open `notebooks/kaggriculture_enhanced_game_v2.ipynb`,
  enable Internet, select CPU, run all. It exports `main.py` + a resumable checkpoint
  and makes **no** submission.
- **Local dev/tests:** `pip install -r requirements.txt`, then e.g.
  `python experiments/exp_v14.py` (before/after occupancy, strawberry and melon
  metrics + head-to-head vs V9/V12).
- Checkpoints are Enhanced-Game-format and are **not** interchangeable across v1/v2/
  V12/V13. Start a new output folder when code or opponents change.
