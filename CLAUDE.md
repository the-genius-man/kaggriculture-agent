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
  quota before any submission.** `tools/submit_guarded.py` enforces this
  (`DAILY_SUBMISSION_CAP`) and is wired to the `submit-to-kaggle` PR label
  (`.github/workflows/submit-on-label.yml`) — labeling a candidate PR submits it. That
  label is the human approval gate on this plan (see "Gate status" below); do not add
  it without having read the candidate's numbers first.
- **Only your latest 2 submissions are "active."** Kaggle keeps matching new episodes
  against your **2 most recent** submissions; older ones stop receiving new episodes
  and their score is frozen at whatever it was when they aged out. As of 2026-09-18
  that is `main_v14.py` (17:11) and `main_v12.py` (16:21) — every earlier submission
  (`main_v13.py`, `main_v11.py`, `main_v9.py`, both `main.py` uploads, ...) is frozen
  history, not a live comparison point. Submitting a new agent retires whichever of
  the current two is older. Do not read a frozen submission's rating as if it were
  still accumulating evidence.
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

## Current status (measured through 2026-09-23)

Evidence: `analysis/REPORT_leader_gap.md` (2026-09-23, real replays of an actual
leaderboard leader — read this one first) and `analysis/REPORT_deployment_diagnosis.md`
(earlier, and wrong wherever it calls `main_leader.py` a leader profile).

- **Standing: rank 5,821 of 9,871 teams, score 621.5** (`b10905cc7ace.py`, the
  `early_cash_bias` candidate submitted 2026-09-22 22:59; pulled 2026-09-23). V14 read
  641.2 on 2026-09-22 and 611.5 a day later with no code change — the clearest
  reminder that the +/-60 noise band is wider than anything we tune.
- **Active submissions: `b10905cc7ace.py` (621.5) and `main_v14.py` (611.5).**
  Everything else is frozen history: V15-search 632.0, V12 617.7, V9 612.0, V13 599.6,
  V11 586.6 — all inside the rating's own noise band, so treat every version we have
  ever shipped as indistinguishable on score alone.
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
- **`agents/main_leader.py` is NOT a leader profile, and never was.** Corrected
  2026-09-23: it was built from the behaviour of opponents in *our* replays, and
  Kaggle matches simulation episodes on rating, so all of them sit near our ~620. Of
  **233 distinct opponents** in our entire episode history, **zero** appear in the
  leaderboard top 20. Every "leader profile" claim made before 2026-09-23 describes
  mid-field play. This is why candidates kept clearing 75-81% against it and then
  winning ~46-53% of real games: the gate was not lying, it was answering a different
  question. Its mechanism fixes are still real (melons at max yield 17% -> 86%,
  strawberry dry-out deaths 8.0 -> 4.0); its *status* as a reference for the top of
  the table is not. See `analysis/REPORT_leader_gap.md`.
- **To study actual leaders, crawl to them.**
  `competitions.EpisodeService/ListEpisodes` only accepts `submissionId` (a `teamId`
  payload 400s), but its response carries every involved team's
  `publicLeaderboardSubmissionId` and every episode exposes both agents' Elo, so a
  best-first crawl over the episode graph reaches the top in **2 calls**
  (`tools/find_top_submissions.py`). `tools/fetch_study_replays.py` +
  `tools/analyze_replays.py` + the `study-replays` workflow turn real replays into
  compact per-seat metrics without importing the simulator.
- **The V14 candidate FAILS the gate, and only because of `main_leader`.** Kaggle
  kernel holdout 2026-09-19, 24 fresh seeds both seats: vs V9 100% (+11,167), vs V12
  93.8% (+10,290), vs **main_leader 33.3% (-2,400, CI90 [-4410, -549])**, V13 skipped
  (file absent). `gate_pass: false`. The candidate beats every agent we have ever
  written and loses to the first opponent that does not share our lineage.
- **But 33.3% was seed-specific.** A second sample (12 seeds, base 96000000) gave
  45.8%. Pooled over 72 games V14 wins **37.5% (95% CI 26.3-48.7%)**. main_leader is
  better, but not by two-to-one, and 48 games does not resolve this to better than
  about +/-13 points. Budget seeds accordingly.
- **V15 passed the gate, was submitted, and was rolled back the same day
  (2026-09-19).** The Optuna search (`search.yml`, main_leader in the pool) found
  `survival_bias=0.45` -- much gentler than the 1.0/2.0 this repo's own hand sweep
  tried, which is why the hand sweep missed it. Gate result: 81.2% vs main_leader
  (margin +3,393, CI90 entirely positive), 66.7% vs V14. Submitted 14:33, and its
  **real win rate was diagnosed at only 52.8%** (36 games, near a coin flip) -- the
  gate result meant "beats main_leader on 48 games," not "beats the leaderboard."
  `main_v14.py` was resubmitted 14:43 the same day to revert the slot. V15 is
  technically still one of the two "active" submissions (632.0) only because nothing
  has been submitted since, **not** because it's ahead of V14 (641.2).
- **V15 still has the two original problems, unfixed.** Real replays of its worst
  losses (downloaded via `kaggle competitions replay`) and 12 local games vs
  main_leader agree: day-10 cash ~$1,700 (opponents ~10x higher), and **0 games where
  V15 reached a 4th quadrant** -- its promoted config is `land: 3`, a hard ceiling
  regardless of cash on hand. The "unwatered tile count" signal from the earlier
  diagnosis turned out to be a false lead: the engine only kills a tile after **two
  consecutive** dry days, and a maxed ongoing crop gains nothing from daily
  rewatering, so a high "not watered today" snapshot count is not itself dangerous --
  only a rising weed count is. Full write-up: `analysis/REPORT_deployment_diagnosis.md`.
- **`land=4` was tested as a standalone lever and closed negative (2026-09-20).** The
  first two attempts couldn't even reach a 4th quadrant: `land_deadline` gated every
  quadrant purchase including the 4th, so both were silently capped at land=3 despite
  the config. Fixed by splitting out a separate `land4_deadline`; retested clean:
  16/16 games actually reached the 4th quadrant, but win rate vs main_leader collapsed
  to **6.2%** (comparable mean cash to land=3, ~76-83k). Buying a 4th quadrant,
  correctly implemented, is a net negative in isolation — the extra land cost and
  production spread over 100 tiles isn't paid back without deeper joint retuning of
  staffing/fertilizer/watering. Closed as a standalone lever; not worth another blind
  search cycle chasing it alone.
- **The 55%/60%/80% gate is a floor, not a target.** Clearing it against main_leader
  on one opponent's 48 games does not mean the candidate is strong against the field.
  The day-10 cash gap remains the next thing to isolate, independent of land count —
  not land=4 again.
- **`early_cash_bias=2.0` was submitted 2026-09-22 and is live.** Gate 75.0% then
  79.2% vs main_leader across two independent seed bases (pooled 77.1% over 96
  games) — consistent, unlike V14's 33.3%/45.8% split. Real result: **621.5 rating,
  46.2% win rate over 26 games**. Third time a gate result did not survive contact
  with the leaderboard.
- **The real gap, measured 2026-09-23 against a rank-2 team** (Majkel1337, 3065.7,
  130/160 wins, mean cash 111,679 vs our ~78,000), from 35 real replays:
  **they end every day with zero bare owned tiles; we carry 20-40.** They hold a
  constant **6.3-6.8 productive tiles per hand** all game (25 at 4 hands, 50 at 8,
  74.6 at 11) — we run ~2.1-3.6. They PLANT 275 times to our ~100, idle (PASS) 94
  times to our 370-455, and move 3,216 steps to our 4,372. Their early game is a
  short-cycle cash engine (409 wheat + 222 carrot units sold; cash held at
  139/338/299 through day 7, then 6,876 by day 10).
- **The system is a closed cash loop, and single levers make it worse.** seed costs
  cash -> cash buys hands -> hands water -> watering keeps crops alive -> crops earn
  -> income buys seed. Measured, each alone: `plant_urgency` fills the land but
  drains cash to 2.7 and hires **zero** hands (0% win rate); `cash_discount` picks the
  right crops but at ~100 plants a game just harvests less value per tile. **Four
  hand-picked configs in a row have failed for this reason** — prefer the search.
- **`crop_value` was blind to *when* cash arrives** (fixed 2026-09-23). It scored
  value per tile-turn, so MELON rated 133 against WHEAT's 17 on size alone, though a
  melon ties a tile ~12 days for one payment while wheat recycles three times.
  `cash_discount` (default 1.0 = unchanged) discounts revenue by `d**first` with the
  impatience fading as the bank fills. This was the structural reason knob-tuning
  kept failing: no parameter can express what the formula cannot see.
- **Always run `python experiments/smoke_agent.py` before spending kernel time.** It
  renders the policy at BASE defaults plus every lever corner and actually calls
  `agent()` on a synthetic observation, in about a second, with no simulator import.
  It exists because a `crop_value` rewrite left `value` assigned only inside an
  `if cash_discount<1.0` branch: the one-shot gate happened to test 0.80, passed, and
  the bug reached a 150-minute search, which died on trial 0 with a thoroughly
  unhelpful `max() iterable argument is empty`. It is now a step in `train.yml` and
  `search.yml`.

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
4. **Fourth quadrant, jointly with staffing/routing/watering capacity — not alone.**
   Tested standalone on 2026-09-20 and closed negative (6.2% win rate vs main_leader,
   correctly implemented, comparable cash to land=3) — the extra land only pays off if
   staffing, fertilizer and watering scale with it, which needs a joint search, not a
   hand-picked config. Do not force it (opponents beat V13 with three quadrants) and
   do not assume three is optimal either.
5. **Market-transaction ablation** before imitating heavy wheat/fertilizer churn.
6. **Survival-priced watering and in-window fertilizer.** Already demonstrated in
   `agents/main_leader.py`; port into the searchable policy as parameters
   (`survival_bias`, `tiles_per_unit`, `seed_stock`) rather than hard-coding them.
7. **Late-game collapse after day 25**, where we drop to ~20 productive tiles and the
   leaders hold ~70.

Do each as an explicit candidate with paired seeds, both seats, the same opponent
pool, against V9 and V13. Do not change all settings at once.

## Pipeline (GitHub Actions + kernel + Pages)

Two planes. **CI plane** = deterministic Kaggle-CLI scripts in `.github/workflows`:

- `train.yml` — packs the repo source into `kernel/run.py` (`tools/pack_kernel.py`;
  the repo is private and cloneless push carries only one file, so source is embedded
  as a base64 tar.gz), pushes it to a Kaggle Kernel, which runs
  `experiments/validate.py` (renders `candidate.json`, plays the gate vs
  V9/V12/V13/`main_leader` on fresh seeds), and returns `main.py` + `validation.json`.
  The workflow **assigns the resulting PR to the repo owner** — that is what sends the
  email — states the gate verdict (PASS/FAIL) in the PR title and opens it as a draft
  on FAIL, and opens an assigned issue instead if the kernel or PR step fails.
- `search.yml` — same packaging, but runs the resumable Optuna league
  (`league/league.py`) instead of the one-shot gate: a real TPE search over the
  policy's parameters against the frozen opponent pool. Longer-running, manual
  dispatch only (`minutes` input). Same PR/notify/failure handling as `train.yml`.
  The checkpoint (`checkpoint.zip`, containing `study.db`) is uploaded as a workflow
  artifact for continuing the search. **Resuming is automated** via the
  `resume_run_id` dispatch input (a prior `search-v15` run's ID): the workflow
  downloads that run's `search-checkpoint` artifact and publishes it as a private
  Kaggle Dataset (`<KAGGLE_USERNAME>/kaggriculture-search-checkpoint`, versioned in
  place on each resume), which `tools/pack_kernel.py --checkpoint-dataset` wires into
  `kernel-metadata.json`'s `dataset_sources`. It can't be embedded in the kernel
  script like the source payload is — Kaggle caps kernel *source* at 1MB and
  `checkpoint.zip` runs ~2MB, confirmed by a real `400` from `SaveKernel` on
  2026-09-22 before this was fixed. `league.py`'s own manifest check still refuses
  the resume (rather than silently restarting from cycle 0) if `league.py`/
  `support.py`/`policy_template.py`/the fixed agents changed since the checkpoint was
  made.
- `pull-feedback.yml` — refreshes leaderboard + our submissions + real episode results
  (`tools/pull_episodes.py`) into `analysis/feedback/`, and rebuilds the public status
  page (`tools/build_site.py` → `docs/`).
- `submit-on-label.yml` — **the submit button.** Adding the `submit-to-kaggle` label
  to a candidate PR submits that PR's agent: runs `tools/submit_guarded.py` (same-day
  quota check vs `DAILY_SUBMISSION_CAP`), comments the result back on the PR, and
  removes the label. This *is* the human approval gate on this plan (see "Gate status"
  below) — only people who can label the repo can trigger a submission, and it fires
  only after a human has read the assigned/emailed PR.

**Reasoning plane** = Claude Code (with Kaggle MCP, if connected): reads the pulled
episodes/leaderboard, diagnoses losses, writes findings to `analysis/`, and opens a
code PR.

**Two human actions, always:** merging a candidate/search PR into the policy, and
adding the `submit-to-kaggle` label. Nothing in CI merges its own code or labels its
own PR.

Repo config needed: secrets `KAGGLE_USERNAME`, `KAGGLE_KEY`; vars `KERNEL_SLUG`,
`KAGGLE_COMPETITION`, `DAILY_SUBMISSION_CAP`; GitHub Pages source set to `/docs`
(**never the repo root** — see below); Settings → Actions → General → "Allow GitHub
Actions to create and approve pull requests" enabled (needed for `gh pr create`).

**Gate status (2026-09-19):** the `production` GitHub *environment* exists but is
UNPROTECTED — required reviewers return HTTP 422 (protection rules on a private repo
need GitHub Pro/Team) — so it enforces nothing and is not used by any workflow. The
actual approval gate is the `submit-to-kaggle` **label**, combined with the PR
assignment/email from `train.yml`/`search.yml`. `submit_guarded.py`'s quota check is
still the only thing standing between a label click and a real submission.

**GitHub Pages is publicly readable even on this private repo.** It was found
pre-configured to serve the **repo root** (`agents/*.py`, `policy/policy_template.py`
would have published on the first build) and has been repointed to `/docs`. Owner
decision 2026-09-19: `analysis/*.md` reports ARE published to `/docs` — they are
public and search-indexable while the competition runs. Agent source, the policy
template, its parameter values, and the raw JSON evidence dumps are **not** published
and must never be added to `docs/`; `tools/build_site.py`'s docstring states this
boundary and `tools/build_site.py` itself must be the only writer of `docs/`.

Episode **results** and **replays** are fetched by `tools/pull_episodes.py`, revised
2026-09-20 on the documented `kaggle-cli` command surface (`kaggle-cli/docs/
simulation_competitions.md`), not the raw internal API used at first:

- `kaggle competitions episodes <submission_id>` lists a submission's games (falls
  back to the unauthenticated internal `ListEpisodes` endpoint, kept working, if the
  CLI/credentials are unavailable);
- `kaggle competitions team-submissions <team_id>` is the **authoritative** source for
  which submissions are still active — pass `--team-id` (ours is `16899024`); without
  it, the tool assumes the 2 most recent by date and says so;
- `kaggle competitions replay <episode_id>` **does** download the real replay JSON —
  the earlier finding that replay download was unavailable was true only of the raw
  internal `GetEpisodeReplay` endpoint called without a login, not of this documented,
  authenticated command.
- `--replays N` downloads the N worst real losses and renders them to playable HTML
  locally (`kaggle_environments.make(steps=...)` round-trips a downloaded replay's
  `configuration`/`steps`, verified). **These are not published** — a replay of a real
  submission shows our policy's exact move-by-move behaviour, a bigger leak than the
  written analysis — they stay a private CI workflow artifact
  (`pull-feedback.yml` → `replays_html` artifact, collaborators only).

Games between agents we hold (not real leaderboard opponents) can also be rendered
and watched offline via `tools/watch_game.py`.

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
