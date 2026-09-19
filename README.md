# Kaggriculture agent

An agent for the Kaggle Kaggriculture competition, improved by Optuna parameter
search over an explicit policy, validated by a self-play league with strict
promotion gates.

**Read `CLAUDE.md` first** — it holds the hard constraints (pinned deps, promotion
gates, submission limits) and the honesty rules this project runs on.

## Layout

- `agents/` — reference and fallback agents. `main_v12.py` is the confirmed champion.
- `policy/policy_template.py` — the V14 parameterised policy (phase params, melon fix,
  strawberry occupancy target). The league renders candidates from this template.
- `league/league.py`, `league/support.py` — the self-play search, game runner, scoring
  and promotion logic.
- `notebooks/kaggriculture_enhanced_game_v2.ipynb` — runnable on Kaggle/Colab; runs the
  league, exports `main.py` + a resumable checkpoint, makes no submission.
- `experiments/` — local scripts: `exp_v14.py` (before/after occupancy, strawberry and
  melon metrics + head-to-head), `run_match.py`, `headtohead.py`, `profile_game.py`.
- `analysis/` — leaderboard-replay diagnoses and their evidence files.

## Quick start (local dev)

```bash
pip install -r requirements.txt
python experiments/exp_v14.py     # measured before/after on a few seeds (CPU, ~minutes)
```

## Full training run

Do it on Kaggle or Colab (persistent CPU runner), not a local machine. Open the
notebook in `notebooks/`, enable Internet, select CPU, run all cells. Pull the
exported `main.py`, checkpoint and reports back into the repo. Then check the
remaining daily submission quota before submitting anything.

## Status

**Rank 5,499 of 9,462 teams, score 645.3** (field median 780.5, leader 3,205.2) as of
2026-09-18. Best deployed agent is V14; V12 617.7, V9 612.0, V13 599.6, V11 586.6.

Treat those differences as noise: `main_v12.py` read 626.5 / 679.0 / 656.8 / 617.7 in
a single afternoon without changing. A freshly submitted agent also sits at its
unplayed initial rating of 600.0 for a while, so never compare a fresh submission
against a settled one.

The measured reasons we are losing — cash-starved early game gating occupancy, crops
dying of thirst, melons harvested a unit short, production collapsing after day 25 —
are in `analysis/REPORT_deployment_diagnosis.md`. Read `CLAUDE.md` for the constraints.

## Kaggle credentials

The Kaggle CLI 2.x uses a single API token. Workflows install `kaggle>=2` and pass
`KAGGLE_API_TOKEN` (from the `KAGGLE_KEY` repo secret); the old
`KAGGLE_USERNAME`+`KAGGLE_KEY`/`kaggle.json` scheme returns 401 on every endpoint.
In 2.x the competition is a positional argument, not `-c`.

Run `kaggle-auth-check.yml` to diagnose credential problems; it prints the shape of
the stored values (length, stray quotes) without revealing them.

## Kaggle MCP (optional)

Claude Code can connect a Kaggle MCP server to read the leaderboard and your
submissions, run the league on a Kaggle Kernel, and submit. See the **Kaggle MCP**
section of `CLAUDE.md` for the security and submission-approval rules, and copy
`.mcp.json.example` to `.mcp.json` to configure it (credentials come from your
environment, never the repo).
