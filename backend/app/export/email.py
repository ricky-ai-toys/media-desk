"""Email export — renders a v5-layout-compatible bilingual HTML email from the
DB edition (builds to templates/email_layout_reference.md: gradient hero,
4 agenda cards, 2x2 narratives, 3 interview groups, 2x2 PR counsel, ZH mirror)."""
import html
import re


def first_sentence(s: str, max_words: int = 22) -> str:
    s = str(s).strip()
    for sep in [". ", "。", "! ", "？", "; "]:
        i = s.find(sep)
        if i != -1:
            s = s[:i + 1]
            break
    words = s.split()
    if len(words) > max_words:
        s = " ".join(words[:max_words]).rstrip(",;:") + "…"
    return s


CSS = """
:root{--navy:#12233f;--blue:#2458d3;--light-blue:#edf3ff;--red:#c8394b;--light-red:#fff0f2;
--green:#197458;--light-green:#eaf8f2;--amber:#9b6308;--light-amber:#fff5df;}
body{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#f4f6fa;color:#1a2233;}
.shell{max-width:760px;margin:0 auto;background:#fff;}
.hero{background:linear-gradient(135deg,#10213e 0%,#2458d3 70%,#6652b9 100%);color:#fff;
padding:28px 32px;}
.hero .brand{font-size:11px;letter-spacing:2px;text-transform:uppercase;opacity:.85;}
.hero h1{font-size:26px;margin:6px 0 2px;}
.hero .period{font-size:13px;opacity:.9;}
.hero .deck{font-size:14px;opacity:.95;margin-top:10px;line-height:1.5;}
.meta-row{display:flex;gap:12px;margin-top:16px;}
.meta-cell{background:rgba(255,255,255,.12);border-radius:8px;padding:8px 12px;flex:1;
font-size:12px;line-height:1.4;}
.meta-cell b{display:block;font-size:16px;}
section{padding:24px 32px;border-top:1px solid #e8ecf4;}
h2{font-size:16px;color:var(--navy);margin:0 0 4px;}
.intro{font-size:12px;color:#5b6577;margin-bottom:12px;}
.summary-box{border-left:4px solid var(--blue);background:var(--light-blue);padding:10px 14px;
font-size:13px;margin-bottom:14px;}
.card-table{width:100%;border-collapse:collapse;}
td.rank{font-family:Consolas,monospace;font-size:18px;color:var(--blue);width:44px;vertical-align:top;}
td.card-body{padding:0 8px 12px 0;}
.card-title{font-weight:600;font-size:14px;}
.card-copy{font-size:12.5px;color:#3a4358;margin-top:2px;line-height:1.45;}
.badge{display:inline-block;font-size:10.5px;padding:2px 8px;border-radius:10px;margin-left:6px;
vertical-align:2px;}
.badge.rising{background:#fff0f2;color:#c8394b;}
.badge.fading{background:#f1f3f7;color:#5b6577;}
.badge.accelerating{background:#eaf8f2;color:#197458;}
.badge.shifting{background:#fff5df;color:#9b6308;}
.badge.stable{background:#edf3ff;color:#2458d3;}
.narrative-table{width:100%;border-collapse:collapse;}
.narrative-table td{width:50%;border:1px solid #e4e9f2;padding:12px;vertical-align:top;}
.narrative-table h3{font-size:13.5px;margin:0 0 6px;color:var(--navy);}
.shift{font-size:12px;font-weight:600;margin-bottom:6px;}
.shift.from{color:var(--red);}
.shift.to{color:var(--green);}
.narrative-table p{font-size:12.5px;color:#3a4358;margin:4px 0 0;line-height:1.5;}
.group h3{font-size:13.5px;color:var(--navy);margin:14px 0 2px;}
.group .role{font-size:12px;color:#5b6577;margin-bottom:6px;}
.group ul{margin:0 0 8px;padding-left:18px;}
.group li{font-size:12.5px;color:#3a4358;margin-bottom:4px;line-height:1.45;}
.pr-table{width:100%;border-collapse:collapse;margin-bottom:10px;}
.pr-table td{width:50%;border:1px solid #e4e9f2;padding:12px;vertical-align:top;font-size:12.5px;line-height:1.5;}
.pr-table td.risk{background:var(--light-red);} .pr-table td.opportunity{background:var(--light-green);}
.pr-table td.prepare{background:var(--light-blue);} .pr-table td.avoid{background:var(--light-amber);}
.pr-table h3{font-size:13px;margin:0 0 6px;}
.lang-banner{background:var(--navy);color:#fff;padding:10px 32px;font-size:13px;}
.footer{padding:16px 32px;font-size:11.5px;color:#5b6577;background:#f7f8fb;}
@media(max-width:600px){.meta-row{flex-wrap:wrap;}.meta-cell{min-width:44%;}
.narrative-table td,.pr-table td{width:100%;display:block;}}
"""


def render_email(edition: dict) -> str:
    d = edition["data"]
    man = edition["manifest"] or {}
    episodes = man.get("episodes", [])
    strands = len({e.get("program", "?") for e in episodes}) or 1
    outlets = ", ".join(d.get("monitored_outlets", []))
    days = len({e.get("date", "") for e in episodes if e.get("date")}) or 0
    srcs = d.get("source_file_count", len(episodes))
    cards = ""
    for t in d.get("agenda_topics", []):
        badge = t.get("direction") or t.get("momentum") or "stable"
        cards += f"""<tr><td class="rank">{t['rank']:02d}</td><td class="card-body">
<div class="card-title">{html.escape(t['title_en'])}<span class="badge {html.escape(badge)}">{badge.title()}</span></div>
<div class="card-copy">{html.escape(first_sentence(t['summary_en'], 22))}</div></td></tr>"""
    narratives = d.get("narratives", [])
    nrows = ""
    for i in range(0, len(narratives), 2):
        cells = ""
        for n in narratives[i:i + 2]:
            cells += f"""<td><h3>{html.escape(n['title_en'])}</h3>
<div class="shift from">← {html.escape(n.get('from_en', ''))}</div>
<div class="shift to">→ {html.escape(n.get('to_en', ''))}</div>
<p>{html.escape(first_sentence(n.get('analysis_en') or n.get('why_en') or '', 35))}</p></td>"""
        nrows += f"<tr>{cells}</tr>"
    groups = ""
    for g in d.get("interview_groups_en", []):
        qs = "".join(f"<li>{html.escape(first_sentence(q, 16))}</li>" for q in g.get("questions_en", []))
        groups += f"""<div class="group"><h3>{html.escape(g['title_en'])}</h3>
<div class="role">{html.escape(g.get('role_en', ''))}</div><ul>{qs}</ul></div>"""
    pr = d.get("pr_counsel", {})
    pr_table = f"""<table class="pr-table"><tr>
<td class="risk"><h3>Narrative risk</h3>{html.escape(first_sentence(pr.get('risk_en', ''), 30))}</td>
<td class="opportunity"><h3>Opportunity</h3>{html.escape(first_sentence(pr.get('opportunity_en', ''), 30))}</td></tr>
<tr><td class="prepare"><h3>Prepare for</h3>{html.escape(first_sentence(pr.get('prepare_en', ''), 30))}</td>
<td class="avoid"><h3>Avoid</h3>{html.escape(first_sentence(pr.get('avoid_en', ''), 30))}</td></tr></table>"""
    watch = "".join(f"<li>{html.escape(w[:140])}</li>" for w in d.get("watchlist_en", []))
    watch = f"<h3>Carry-over watchlist</h3><ul>{watch}</ul>" if watch else ""
    zh_cards = ""
    for t in d.get("agenda_topics", []):
        zh_cards += f"""<tr><td class="rank">{t['rank']:02d}</td><td class="card-body">
<div class="card-title">{html.escape(t.get('title_zh', ''))}<span class="badge {html.escape(t.get('direction') or t.get('momentum') or 'stable')}">{(t.get('direction') or t.get('momentum') or 'stable').title()}</span></div>
<div class="card-copy">{html.escape(first_sentence(t.get('summary_zh', ''), 22))}</div></td></tr>"""
    zh_groups = ""
    for g in d.get("interview_groups_zh", []):
        qs = "".join(f"<li>{html.escape(first_sentence(q, 16))}</li>" for q in g.get("questions_zh", []))
        zh_groups += f"""<div class="group"><h3>{html.escape(g.get('title_zh', ''))}</h3>
<div class="role">{html.escape(g.get('role_zh', ''))}</div><ul>{qs}</ul></div>"""
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><style>{CSS}</style></head>
<body><div class="shell">
<div class="hero"><div class="brand">International Financial Media Weekly</div>
<h1>International Financial Media Weekly</h1>
<div class="period">{d['start_date']} to {d['end_date']}</div>
<div class="deck">{html.escape(d.get('week_summary_en', ''))}</div>
<div class="meta-row">
<div class="meta-cell"><b>{srcs}</b>programs reviewed</div>
<div class="meta-cell"><b>{strands}</b>program strand(s)</div>
<div class="meta-cell"><b>{days}</b>broadcast days</div>
<div class="meta-cell"><b>{html.escape(outlets)}</b>source in this edition</div></div></div>
<section><h2>This week's media agenda</h2>
<div class="intro">Topics are selected dynamically from the week's coverage — not a standing list.</div>
<table class="card-table">{cards}</table></section>
<section><h2>Narrative shifts</h2><table class="narrative-table">{nrows}</table></section>
{_week_ahead(d)}
<section><h2>What television interviewers kept asking</h2>{groups}</section>
<section><h2>PR counsel</h2>{pr_table}{watch}</section>
<div class="lang-banner">中文摘要 · 本节为完整中文编辑版本，并非逐句机械翻译。</div>
<section><h2>本周媒体议程</h2>
<table class="card-table">{zh_cards}</table></section>
<section><h2>叙事转向</h2>
<table class="narrative-table">{_zh_narratives(d)}</table></section>
<section><h2>电视主播反复追问的问题</h2>{zh_groups}</section>
<section><h2>公关建议</h2>{_zh_pr(d)}{_zh_watchlist(d)}</section>
<div class="footer"><b>PDF attachment:</b> full bilingual report, interview log and methodology appendix.<br>
Prepared from the supplied media universe: {html.escape(outlets)} · {d['start_date']} to {d['end_date']}</div>
</div></body></html>"""


def _zh_narratives(d: dict) -> str:
    n = d.get("narratives", [])
    rows = ""
    for i in range(0, len(n), 2):
        cells = ""
        for x in n[i:i + 2]:
            cells += f"""<td><h3>{html.escape(x.get('title_zh', ''))}</h3>
<div class="shift from">← {html.escape(x.get('from_zh', ''))}</div>
<div class="shift to">→ {html.escape(x.get('to_zh', ''))}</div>
<p>{html.escape(first_sentence(x.get('analysis_zh') or x.get('why_zh') or '', 35))}</p></td>"""
        rows += f"<tr>{cells}</tr>"
    return rows


def _zh_pr(d: dict) -> str:
    pr = d.get("pr_counsel", {})
    return f"""<table class="pr-table"><tr>
<td class="risk"><h3>叙事风险</h3>{html.escape(first_sentence(pr.get('risk_zh', ''), 30))}</td>
<td class="opportunity"><h3>机遇</h3>{html.escape(first_sentence(pr.get('opportunity_zh', ''), 30))}</td></tr>
<tr><td class="prepare"><h3>需准备</h3>{html.escape(first_sentence(pr.get('prepare_zh', ''), 30))}</td>
<td class="avoid"><h3>需避免</h3>{html.escape(first_sentence(pr.get('avoid_zh', ''), 30))}</td></tr></table>"""


def _week_ahead(d: dict) -> str:
    """Dated events to watch — omitted entirely when absent (no empty blocks)."""
    events = d.get("week_ahead_events") or []
    if not events:
        return ""
    rows = "".join(
        f"<tr><td class='rank'>{html.escape(str(e.get('date', ''))[5:].replace('-', '/'))}</td>"
        f"<td class='card-body'><div class='card-title'>{html.escape(e.get('event_en', ''))}</div>"
        f"<div class='card-copy'>{html.escape(e.get('why_en', ''))}</div></td></tr>"
        for e in events)
    return ("<section><h2>Week ahead</h2>"
            "<div class='intro'>Dates are calendar items supplied with the corpus; "
            "verify against official schedules before acting.</div>"
            f"<table class='card-table'>{rows}</table></section>")


def _zh_watchlist(d: dict) -> str:
    items = d.get("watchlist_zh") or []
    if not items:
        return ""
    lis = "".join(f"<li>{html.escape(str(w)[:140])}</li>" for w in items)
    return f"<h3>延续观察清单</h3><ul>{lis}</ul>"


def email_subject(edition: dict) -> str:
    d = edition["data"]
    return f"International Financial Media Weekly {d['start_date']} to {d['end_date']}"