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

Fallback champion: V12 trial-23. V14 is a promising but unvalidated candidate; see
`CHANGELOG.md` and `CLAUDE.md`.

## Kaggle MCP (optional)

Claude Code can connect a Kaggle MCP server to read the leaderboard and your
submissions, run the league on a Kaggle Kernel, and submit. See the **Kaggle MCP**
section of `CLAUDE.md` for the security and submission-approval rules, and copy
`.mcp.json.example` to `.mcp.json` to configure it (credentials come from your
environment, never the repo).
