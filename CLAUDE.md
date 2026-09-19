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
- **Kaggle CLI 2.x with token auth.** The stored credential is a new-style Kaggle API
  token, not a legacy 32-hex key: the 1.x `KAGGLE_USERNAME`+`KAGGLE_KEY` scheme 401s on
  every endpoint. Workflows install `kaggle>=2` and pass `KAGGLE_API_TOKEN` (sourced
  from the `KAGGLE_KEY` secret); there is no `~/.kaggle/kaggle.json`. In 2.x the
  competition is a **positional** argument — `-c` is gone.
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
- **The Kaggle rating is noisier than the differences we tune on.** `main_v12.py`
  read 626.5 / 679.0 / 656.8 / 617.7 in one afternoon, unchanged. That +/-60 swing is
  wider than the whole spread across every version we have shipped. No single
  submission establishes that a change helped.
- **A fresh submission sits at its unplayed initial rating (600.0) for a while.**
  V14 read 600.0 at 17:2x and 645.3 by 19:1x on 2026-09-18. Never compare a fresh
  submission against a settled one; re-read both in the same pull.

## Current status (measured 2026-09-18/19)

See `analysis/REPORT_deployment_diagnosis.md` for the evidence behind all of this.

- **Standing: rank 5,499 of 9,462 teams, score 645.3.** Field median 780.5, leader
  3,205.2. We are in the bottom 42% of the field, not near the front.
- **Best deployed agent: V14 (645.3).** V12 617.7, V9 612.0, V13 599.6, V11 586.6 —
  all inside the rating's own noise band, so treat them as indistinguishable.
- Confirmed fallback: **V12 trial-23** (`agents/main_v12.py`, `sha256 dffae949e74e...`).
  Note V12 is configured `'land': 2`, so it is hard-capped at 50 of 75 tiles.
- `agents/main_v13.py` **does not exist in this repo**, so the `main_v13.py` arm of the
  gate in `experiments/validate.py` silently skips. Either restore the file or stop
  claiming V13 as a baseline.
- **Two engine mechanics dominate production** (from `kaggriculture.py`; the env
  README's crop table contradicts the code and is wrong):
  - one-time crops gain yield **only** from `WATER`, inside age window
    `[(max_yield_day+1)//2, max_yield_day]`, +1 per watered day, +2 if fertilized;
  - **two consecutive unwatered days turn the tile into a WEED.** An unwatered plant
    is not a slow plant, it is a dead plant in two days.
- **Measured gaps.** Day-20 productive tiles: V12 45.5 of 50 owned, V14 51.5 of 75;
  the leader profile is 74.75 of 75 **by day 10**. V14 loses 8 strawberries per game
  to dry-out. Melons clear at 5 of 6 units in 19 of 23 cases (leaders: 43/43 at 6).
  Production collapses after day 25.
- **Ruled out:** the 1s `actTimeout` (we peak at 0.075-0.105s) and the worker ceiling
  (V14 reaches 12 hands; leaders run 11-12).
- **The early-game constraint is cash, not seeds or land.** At day 10 our agents hold
  320-880 cash while the leader profile has spent ~6,000 from a 3,000 start. Raising
  the seed stock from 2 to 6 *lowered* day-10 occupancy and cash — bulk seed buying
  starves expansion.
- **Known policy defect:** `policy_template.py` prices a watering job at
  `95+hour*4+120*consecutive_unwatered` (~215 for a plant dying tonight) against a
  harvest at ~364, then divides by distance. Losing a strawberry costs its 100 seed
  plus ~480 of future yield, so survival watering is underpriced by roughly 10x.
- **`agents/main_leader.py`** is a league opponent built to the leaders' measured
  behavioural profile (not a reconstruction of their policy). Its mechanism fixes
  work: melons at max yield 17% -> 86%, strawberry dry-out deaths 8.0 -> 4.0.
- **The V14 candidate FAILS the gate, and only because of `main_leader`.** Kaggle
  kernel holdout 2026-09-19, 24 fresh seeds both seats: vs V9 100% (+11,167), vs V12
  93.8% (+10,290, CI90 [7954, 12798]), vs **main_leader 33.3% (-2,400, CI90
  [-4410, -549])**, V13 skipped (file absent). `gate_pass: false`. The candidate beats
  every agent we have ever written and loses two games in three to the first opponent
  that does not share our lineage. Do not read past this: the old pool could not
  detect it.
- `main_leader` has not yet been run through the gate **as a candidate**. That is the
  obvious next experiment.

## What the leaderboard analysis says to work on next

See `analysis/REPORT_deployment_diagnosis.md` (measured, current) and
`analysis/REPORT_boey_leaders.md` (4 Boey wins). Priorities, reordered by what the
measurements actually support:

0. **Early cash generation, days 1-10.** This is the binding constraint: occupancy
   cannot exceed what the bank can fund, and everything else follows occupancy. The
   leaders fund expansion out of early revenue (short-cycle wheat, day-4 eggs, market
   churn). Our agents reach day 10 with an empty bank.
1. **Productive occupancy / crop scheduling.** Fill owned, reachable tiles early;
   establish a large strawberry crop by ~day 10-15 the way Boey does, then rotate to
   short-cycle crops late. Gated by (0); do not tune it in isolation.
2. **Routing / job allocation.** Boey used fewer move commands and more harvests at
   the same worker cap. Tune region homes, commitment and distance weighting; the
   worker ceiling is not the problem.
3. **Season-aware crop replacement** (early melon -> dense strawberry -> late wheat/
   short crops), driven by remaining game horizon.
4. **Fourth quadrant as a *tested* option**, evaluated together with planting,
   staffing, routing and time-to-recover. Do not force it (opponents beat V13 with
   three quadrants) and do not assume three is optimal.
5. **Market-transaction ablation** before imitating heavy wheat/fertilizer churn.
6. **Survival-priced watering and in-window fertilizer.** Already demonstrated in
   `agents/main_leader.py`; port into the searchable policy as parameters
   (`survival_bias`, `tiles_per_unit`, `seed_stock`) rather than hard-coding them.
7. **Late-game collapse after day 25**, where we drop to ~20 productive tiles and the
   leaders hold ~70.

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
`KAGGLE_COMPETITION`, `DAILY_SUBMISSION_CAP`; a `production` environment.

**Gate status (2026-09-18): the `production` environment exists but is UNPROTECTED.**
Required reviewers returned HTTP 422 — protection rules on a private repo need GitHub
Pro/Team. Until the repo is public or the plan is upgraded, the only submission guards
are the `SUBMIT` confirm string and the same-day quota check in `submit_guarded.py`.
`submit.yml` also has no commit step, so the `analysis/submissions_log.csv` audit trail
it writes is discarded with the runner. Note: a kernel cannot reliably self-submit an agent competition, so
produce (auto) and submit (gated) are separate; and episode **results** are now fetched by
`tools/pull_episodes.py` (verified 2026-09-19): Kaggle's `ListEpisodes` endpoint is
unauthenticated and takes a `submissionId` (`teamId` is no longer accepted). It gives
per game: our cash, the opponent's cash, their team, and the rating before/after.
**Full replay download is still not available** — `GetEpisodeReplay` 404s at every
method name and casing tried without a logged-in session. Games can only be *watched*
locally, via `tools/watch_game.py`, between agents we hold.

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
