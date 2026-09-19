"""Generate the GitHub Pages site into docs/: a tabbed status dashboard
(docs/index.html, raw static -- no Jekyll front matter, so the theme cannot alter it)
plus the analysis reports (docs/analysis/*.md, Jekyll-rendered).

IMPORTANT -- this site is PUBLIC. GitHub Pages on a private repo is publicly readable
on this plan. Publishing the analysis reports was an explicit owner decision
(2026-09-19): the engine mechanics, occupancy numbers and policy defects in them are
public and search-indexable while the competition is running.

Still NOT published, and must not be: agent source (`agents/*.py`), the policy
template and its parameter values, the raw evidence dumps (`analysis/*.json`), and
full game replays (move-by-move HTML) -- a replay of our own real submission shows
our policy's exact behaviour, which is a bigger leak than the written analysis.
Replays are rendered locally (tools/pull_episodes.py --replays N) and stay a private
CI workflow artifact; the dashboard links to the Actions run, not to the file.

Keep the Pages source pointed at /docs, never at the repo root.
"""
import csv, html, json, statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEED = ROOT / "analysis" / "feedback"
DOCS = ROOT / "docs"

# Filled in by pull-feedback.yml from ${{ github.repository }} / ${{ github.run_id }};
# harmless placeholders when run locally.
REPO_SLUG = "the-genius-man/kaggriculture-agent"


def esc(s):
    return html.escape(str(s), quote=True)


def read_leaderboard():
    files = sorted((FEED / "lb_extract").glob("*.csv")) if (FEED / "lb_extract").exists() else []
    if not files:
        return None
    rows = list(csv.DictReader(open(files[-1], encoding="utf-8-sig", errors="replace")))
    scores = [float(r["Score"]) for r in rows]
    mine = [r for r in rows if "nickazaria" in (r.get("TeamMemberUserNames") or "").lower()]
    return {"teams": len(rows), "leader": scores[0], "median": statistics.median(scores),
            "me": mine[0] if mine else None, "top": rows[:10]}


def read_submissions():
    f = FEED / "submissions.csv"
    if not f.exists():
        return []
    return list(csv.DictReader(open(f, encoding="utf-8", errors="replace")))[:10]


def read_episodes():
    f = FEED / "episodes.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def collect_reports():
    reports = []
    for r in sorted((ROOT / "analysis").glob("*.md")):
        body = r.read_text(encoding="utf-8")
        title = next((l.lstrip("# ").strip() for l in body.splitlines() if l.startswith("# ")), r.stem)
        dst = DOCS / "analysis" / r.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text("---\ntitle: %s\n---\n\n%s" % (title.replace('"', "'"), body), encoding="utf-8")
        reports.append((title, "analysis/%s" % r.with_suffix(".html").name))
    return reports


def render(lb, subs, eps, reports):
    active_ids = {sid for sid, d in eps.items() if d.get("active")}
    parts = []

    # ---- Standing --------------------------------------------------------------
    if lb and lb["me"]:
        m = lb["me"]
        parts.append(f"""
<h2>Standing</h2>
<p class="big">Rank {int(m['Rank']):,} of {lb['teams']:,} &mdash; score {esc(m['Score'])}</p>
<p class="muted">Field median {lb['median']:.1f} &middot; leader {lb['leader']:.1f}</p>
<div class="callout">Ratings drift: the same unchanged agent has read 60 points apart
within a single afternoon. Treat small differences as noise, not a verdict.</div>""")
    else:
        parts.append("<h2>Standing</h2><p class=\"muted\">No leaderboard pull yet.</p>")

    # ---- Submissions -------------------------------------------------------
    rows = ""
    for s in subs:
        sid = s.get("ref", "")
        active = sid in active_ids
        badge = '<span class="badge active">active</span>' if active else '<span class="badge frozen">frozen</span>'
        rows += (f"<tr><td>{badge}</td><td><code>{esc(s.get('fileName',''))}</code></td>"
                 f"<td>{esc(s.get('date','')[:16])}</td><td class=\"num\">{esc(s.get('publicScore') or '&mdash;')}</td></tr>\n")
    parts.append(f"""
<h2>Submissions</h2>
<p class="muted">Kaggle keeps matching new episodes against only your <b>2 most
recent</b> submissions; older ones are frozen &mdash; their score stops moving and
they no longer count toward the final leaderboard.</p>
<table><thead><tr><th></th><th>agent</th><th>submitted (UTC)</th><th>score</th></tr></thead>
<tbody>{rows}</tbody></table>""")

    # ---- Performance (real per-episode results) --------------------------
    perf = ""
    any_active_data = False
    for sid, d in eps.items():
        if not d.get("active") or not d.get("episodes"):
            continue
        any_active_data = True
        rs = d["episodes"]
        wr = 100 * statistics.mean(r["won"] for r in rs)
        our = statistics.mean(r["our_cash"] for r in rs)
        opp = statistics.mean(r["opp_cash"] for r in rs)
        worst = sorted(rs, key=lambda r: r["our_cash"] - r["opp_cash"])[:5]
        wrows = "".join(f"<tr><td>{esc(r.get('opponent',''))}</td>"
                         f"<td class=\"num\">{r['our_cash']:,.0f}</td>"
                         f"<td class=\"num\">{r['opp_cash']:,.0f}</td></tr>\n" for r in worst)
        perf += f"""
<h3><code>{esc(d.get('file',sid))}</code></h3>
<p>{len(rs)} real games &middot; win rate {wr:.1f}% &middot; our cash {our:,.0f} avg &middot; opponent cash {opp:,.0f} avg</p>
<details><summary>Worst 5 losses</summary>
<table><thead><tr><th>opponent</th><th>our cash</th><th>their cash</th></tr></thead>
<tbody>{wrows}</tbody></table></details>"""
    if not any_active_data:
        perf = "<p class=\"muted\">No episode data pulled yet for the active submissions.</p>"
    parts.append(f"""
<h2>Performance</h2>
{perf}
<div class="callout">Full move-by-move replays of these games are rendered privately
(they show our policy's exact behaviour) and kept as a CI workflow artifact, not
published here &mdash; see the
<a href="https://github.com/{REPO_SLUG}/actions/workflows/pull-feedback.yml">pull-feedback
runs</a> (repo collaborators only).</div>""")

    # ---- Leaderboard (collapsible top 10) ---------------------------------
    if lb:
        trows = "".join(f"<tr><td>{esc(r['Rank'])}</td><td>{esc(r['TeamName'])}</td>"
                         f"<td class=\"num\">{esc(r['Score'])}</td></tr>\n" for r in lb["top"])
        parts.append(f"""
<h2>Leaderboard</h2>
<details><summary>Top 10</summary>
<table><thead><tr><th>#</th><th>team</th><th>score</th></tr></thead>
<tbody>{trows}</tbody></table></details>""")
    else:
        parts.append("<h2>Leaderboard</h2><p class=\"muted\">No leaderboard pull yet.</p>")

    # ---- Analysis (sub-tabs, iframed pre-rendered pages) -------------------
    if reports:
        subtabs = "".join(f'<button class="subtab" data-frame="rf{i}" onclick="showFrame({i})">{esc(t)}</button>'
                          for i, (t, _) in enumerate(reports))
        frames = "".join(f'<iframe id="rf{i}" class="report-frame" src="{esc(u)}" hidden></iframe>'
                         for i, (t, u) in enumerate(reports))
        parts.append(f"""
<h2>Analysis</h2>
<div class="subtabs">{subtabs}</div>
{frames}
<script>function showFrame(n){{document.querySelectorAll('.report-frame').forEach((f,i)=>f.hidden=i!==n);
document.querySelectorAll('.subtab').forEach((b,i)=>b.classList.toggle('active',i===n));}}
showFrame(0);</script>""")
    else:
        parts.append("<h2>Analysis</h2><p class=\"muted\">No reports yet.</p>")

    sections = ["standing", "submissions", "performance", "leaderboard", "analysis"]
    labels = ["Standing", "Submissions", "Performance", "Leaderboard", "Analysis"]
    panels = "".join(f'<section id="{s}" class="panel">{p}</section>' for s, p in zip(sections, parts))
    nav = "".join(f'<button class="navlink" data-tab="{s}" onclick="showTab(\'{s}\')">{l}</button>'
                  for s, l in zip(sections, labels))

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kaggriculture agent — status</title>
<style>
:root{{--bg:#fafaf8;--panel:#fff;--text:#1a1a1a;--muted:#6b6b6b;--border:#e2e2df;
--accent:#0b6b4f;--active:#0b6b4f;--frozen:#8a8a86;}}
@media (prefers-color-scheme: dark){{
:root{{--bg:#15161a;--panel:#1d1e23;--text:#eceae6;--muted:#9a9a96;--border:#33343a;
--accent:#3ecf8e;--active:#3ecf8e;--frozen:#7a7a76;}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--text);font:15px/1.55 -apple-system,Segoe UI,Roboto,sans-serif;
padding:1.25rem clamp(16px,4vw,16px) 3rem}}
h1{{font-size:1.3rem;margin:0 0 .25rem}}
h2{{font-size:1.1rem;border-bottom:1px solid var(--border);padding-bottom:.4rem;margin-top:0}}
h3{{font-size:.95rem;margin:1.2rem 0 .3rem}}
.top{{display:flex;flex-wrap:wrap;gap:.5rem 1rem;justify-content:space-between;align-items:flex-start;
margin-bottom:1rem}}
.byline{{color:var(--muted);font-size:.85rem;max-width:60ch}}
nav{{display:flex;flex-wrap:wrap;gap:.35rem;justify-content:flex-end}}
.navlink{{background:transparent;border:1px solid var(--border);color:var(--text);border-radius:6px;
padding:.4rem .7rem;font-size:.85rem;cursor:pointer}}
.navlink.active{{background:var(--accent);color:#fff;border-color:var(--accent)}}
main{{max-width:900px;margin:0 auto}}
.panel{{display:none;background:var(--panel);border:1px solid var(--border);border-radius:10px;
padding:1.25rem 1.5rem;margin-bottom:1rem}}
.panel.active{{display:block}}
.big{{font-size:1.3rem;font-weight:600;margin:.3rem 0}}
.muted{{color:var(--muted)}}
.callout{{background:rgba(11,107,79,.08);border-left:3px solid var(--accent);padding:.6rem .9rem;
border-radius:4px;font-size:.9rem;margin-top:.8rem}}
table{{width:100%;border-collapse:collapse;font-size:.88rem;margin:.5rem 0}}
th,td{{text-align:left;padding:.35rem .5rem;border-bottom:1px solid var(--border)}}
td.num,th.num{{text-align:right;font-variant-numeric:tabular-nums}}
code{{background:rgba(127,127,127,.15);padding:.1rem .3rem;border-radius:4px;font-size:.85em}}
details{{margin:.5rem 0}}
summary{{cursor:pointer;color:var(--accent);font-weight:500}}
.badge{{font-size:.72rem;padding:.15rem .5rem;border-radius:99px;color:#fff}}
.badge.active{{background:var(--active)}}
.badge.frozen{{background:var(--frozen)}}
.subtabs{{display:flex;flex-wrap:wrap;gap:.4rem;margin-bottom:.75rem}}
.subtab{{background:transparent;border:1px solid var(--border);color:var(--text);border-radius:6px;
padding:.35rem .65rem;font-size:.85rem;cursor:pointer}}
.subtab.active{{background:var(--accent);color:#fff;border-color:var(--accent)}}
.report-frame{{width:100%;height:75vh;border:1px solid var(--border);border-radius:8px}}
footer{{max-width:900px;margin:1.5rem auto 0;color:var(--muted);font-size:.8rem;text-align:center}}
</style>
</head>
<body>
<div class="top">
  <div>
    <h1>Kaggriculture agent</h1>
    <p class="byline">Status dashboard, generated from the CI feedback pull. Agent
    source and policy parameters are not published here.</p>
  </div>
  <nav>{nav}</nav>
</div>
<main>{panels}</main>
<footer>Generated by <code>tools/build_site.py</code>.</footer>
<script>
function showTab(id){{
  document.querySelectorAll('.panel').forEach(p=>p.classList.toggle('active',p.id===id));
  document.querySelectorAll('.navlink').forEach(b=>b.classList.toggle('active',b.dataset.tab===id));
  try{{localStorage.setItem('kag_tab',id);}}catch(e){{}}
}}
(function(){{
  var t='standing';
  try{{t=localStorage.getItem('kag_tab')||t;}}catch(e){{}}
  showTab(t);
}})();
</script>
</body>
</html>"""


def main():
    DOCS.mkdir(exist_ok=True)
    lb = read_leaderboard()
    subs = read_submissions()
    eps = read_episodes()
    reports = collect_reports()
    (DOCS / "index.html").write_text(render(lb, subs, eps, reports), encoding="utf-8")
    cfg = DOCS / "_config.yml"
    if not cfg.exists():
        cfg.write_text("theme: jekyll-theme-minimal\ntitle: Kaggriculture agent\n", encoding="utf-8")
    print("wrote", DOCS / "index.html")


if __name__ == "__main__":
    main()
