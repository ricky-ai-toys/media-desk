"""Build a synthetic fixture DB so the test-suite runs without production data.

Two editions (2026-08-03..07 and 2026-08-10..14), 40 episodes with transcript
chunks, per-episode analyses in the exact DAILY_OUTLINE markdown format, 60
wire articles, interview entries and QC-passing v2 edition payloads.

Usage:  python scripts/make_fixture_db.py [db_path]
Default db_path: $MEDIA_DESK_DB or <repo>/data/media.db
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app import config  # noqa: E402
from backend.app import db  # noqa: E402

W1 = ("2026-08-03", "2026-08-07")
W2 = ("2026-08-10", "2026-08-14")
SHOWS = ["The Asia Trade", "The China Show", "Insight with Haslinda Amin",
         "Bloomberg Daybreak Asia"]
WEEKDAYS = ["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07",
            "2026-08-10", "2026-08-11", "2026-08-12", "2026-08-13", "2026-08-14"]

TOPICS = [
    "Yen intervention watch as dollar weakens",
    "Nvidia AI capex cycle extends",
    "Hormuz shipping risk lifts oil",
    "China property easing widens",
    "Fed rate path splits voters",
    "Korea chip rally faces leverage test",
]

_TRANSCRIPT = (
    "Good morning from Hong Kong. The yen is in focus as the dollar weakens "
    "and traders watch for intervention from Tokyo. Nvidia shares extend gains "
    "as the AI capex cycle broadens across Asia. Oil climbs on Hormuz shipping "
    "risk while China property easing widens to more cities. The Fed rate path "
    "splits voters ahead of the September meeting. Korea chip rally faces a "
    "leverage test as retail flows surge. Inflation data due later this week "
    "will shape the dollar and the yen outlook for investors across the region. "
) * 12


def _daily_md(show: str, date: str, topics: list[str]) -> str:
    hot = "\n".join(
        f"**{i}. {t}**\n- *Description:* Desk discussion of {t.lower()}.\n"
        f"- *China lens:* Macro\n- *Tone:* Cautious ({-1 if i % 2 else 2})"
        for i, t in enumerate(topics, 1))
    return f"""## 1. Episode Header
- Show name: {show}
- Date: {date}
- Anchor(s): Fixture Anchor
- Episode title: {show} fixture {date}

## 2. Hot Topics
{hot}

## 3. Reporting Frame
### Dominant Frame — Policy credibility under market pressure.

## 4. Corporate Voices
| Company | Spokesperson | Role | Topic | Stance | Quote |
|---|---|---|---|---|---|

## 5. Anchor–Guest Tension
1. **Anchor question:** Do you believe the yen defense can hold?
   **Guest reply:** The ministry has limited room to challenge the dollar trend.
   **Tension point:** Credibility of the intervention threat is being challenged.
2. **Anchor question:** Is the Nvidia capex cycle overheating?
   **Guest reply:** We see disciplined spending, not a bubble.
   **Tension point:** The anchor pushes on circular financing risk.

## 6. Anchor's Forecasting Push
**Forecast requested:** Year-end dollar yen level.
**Guest forecast:** Too early to call with confidence.

## 7. Agenda Signal
- **Topic-level agenda cue:** Watch the yen and Hormuz risk into next week.
- **Weak signals:** Korea leveraged ETF flows."""


def _week_payload(start: str, end: str, topics: list[dict]) -> dict:
    return {
        "report_title": "International Financial Media Weekly",
        "start_date": start, "end_date": end,
        "monitored_outlets": ["The Asia Trade", "The China Show",
                              "Insight with Haslinda Amin", "Bloomberg Daybreak Asia"],
        "source_file_count": 20, "episode_count": 20,
        "thesis_en": "Policy credibility is the thread linking the week's stories.",
        "thesis_zh": "政策公信力是串联本周各条主线的核心张力。",
        "week_summary_en": "Policy credibility is the thread linking the week's stories.",
        "week_summary_zh": "政策公信力是串联本周各条主线的核心张力。",
        "agenda_topics": topics,
        "narratives": [{
            "title_en": f"Narrative {i}", "title_zh": f"叙事{i}",
            "from_en": "old frame", "to_en": "new frame",
            "from_zh": "旧框架", "to_zh": "新框架",
            "driver_en": "driver", "driver_zh": "驱动",
            "why_en": "why it matters", "why_zh": "为何重要",
            "next_test_en": "next test", "next_test_zh": "下一检验",
        } for i in range(1, 5)],
        "comms_boxes": [{
            "title_en": f"Box {i}", "title_zh": f"板块{i}",
            "implication_en": "implication", "implication_zh": "启示",
            "questions_likely_en": ["q1"], "questions_likely_zh": ["问1"],
            "evidence_to_prepare_en": ["e1"], "evidence_to_prepare_zh": ["据1"],
            "risky_en": "risky", "risky_zh": "风险",
        } for i in range(1, 4)],
        "question_groups": [{
            "category": c,
            "questions_en": [f"Question {c} one?", f"Question {c} two?"],
            "questions_zh": [f"{c}问题一？", f"{c}问题二？"],
        } for c in ("policy_credibility", "market_consequences")],
        "top_questions_next_week_en": ["Will the yen defense hold?"],
        "top_questions_next_week_zh": ["日元防线守得住吗？"],
        "media_exchanges": [{
            "pattern_en": f"pattern {i}", "premise_en": "premise",
            "response_en": "response", "lesson_en": "lesson",
            "pattern_zh": f"模式{i}", "premise_zh": "预设",
            "response_zh": "回应", "lesson_zh": "启示", "likely_to_recur": True,
        } for i in range(1, 4)],
        "watchpoints": [{
            "trigger_en": f"trigger {i}", "shift_en": "shift",
            "affected_en": "affected", "priority_raises_en": "raises",
            "trigger_zh": f"触发{i}", "shift_zh": "转向",
            "affected_zh": "受影响", "priority_raises_zh": "升级",
        } for i in range(1, 4)],
        "week_ahead_events": [
            {"date": "2026-08-17", "event_en": "BOJ minutes", "event_zh": "日银纪要",
             "why_en": "yen policy clue", "why_zh": "日元政策线索"},
            {"date": "2026-08-19", "event_en": "FOMC minutes", "event_zh": "美联储纪要",
             "why_en": "rate path clue", "why_zh": "利率路径线索"},
            {"date": "2026-08-21", "event_en": "Japan CPI", "event_zh": "日本CPI",
             "why_en": "inflation read", "why_zh": "通胀读数"},
        ] if end == W2[1] else [
            {"date": "2026-08-10", "event_en": "China trade data", "event_zh": "中国贸易数据",
             "why_en": "export read", "why_zh": "出口读数"},
            {"date": "2026-08-12", "event_en": "US CPI", "event_zh": "美国CPI",
             "why_en": "inflation read", "why_zh": "通胀读数"},
            {"date": "2026-08-14", "event_en": "Retail sales", "event_zh": "零售销售",
             "why_en": "consumption read", "why_zh": "消费读数"},
        ],
        "evidence_statuses": [
            {"section": "Thesis", "status": "supported", "note": "digests"},
            {"section": "Agenda topics", "status": "supported", "note": "traceable"},
        ],
        "interview_groups_en": [{
            "title_en": f"Group {i}", "role_en": "strategist",
            "questions_en": ["q one?", "q two?", "q three?"],
        } for i in range(1, 4)],
        "interview_groups_zh": [{
            "title_zh": f"组别{i}", "role_zh": "策略师",
            "questions_zh": ["问题一？", "问题二？", "问题三？"],
        } for i in range(1, 4)],
        "pr_counsel": {
            "risk_en": "risk", "risk_zh": "风险",
            "opportunity_en": "opportunity", "opportunity_zh": "机遇",
            "prepare_en": "prepare", "prepare_zh": "准备",
            "avoid_en": "avoid", "avoid_zh": "避免",
        },
        "watchlist_en": ["yen defense"], "watchlist_zh": ["日元防线"],
        "recurring_questions_en": ["Will the yen defense hold?",
                                   "Is the AI capex cycle overheating?",
                                   "Does Hormuz risk lift oil further?"],
        "recurring_questions_zh": ["日元防线守得住吗？", "AI资本开支过热了吗？",
                                   "霍尔木兹风险会推高油价吗？"],
        "warnings": [],
    }


def build(db_path: Path) -> Path:
    os.environ["MEDIA_DESK_DB"] = str(db_path)
    config.DB_PATH = db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    db.init_db()

    # episodes + chunks + analyses (4 shows x 5 days x 2 weeks = 40)
    n = 0
    for date in WEEKDAYS:
        for show in SHOWS:
            n += 1
            ep_id = f"fix{n:03d}"
            db.upsert_episode({
                "id": ep_id, "source_id": "bloomberg_asia_trade",
                "title": f"{show} fixture {date}", "show_name": show,
                "pub_date": date, "url": f"https://example.com/{ep_id}",
                "kind": "yt", "words": len(_TRANSCRIPT.split()),
                "transcript_path": f"data/transcripts/{ep_id}.txt",
            })
            db.replace_chunks(ep_id, [_TRANSCRIPT[:4000], _TRANSCRIPT[4000:]])
            db.upsert_analysis(ep_id, _daily_md(show, date, TOPICS), None, None)

    # wire articles (60) across both weeks
    arts = [
        ("Yen slides as dollar strength tests Tokyo resolve", "bloomberg_wire"),
        ("Nvidia leads AI capex boom across Asia suppliers", "cnbc_wire"),
        ("Oil climbs as Hormuz shipping risk returns", "ft_home"),
        ("China widens property easing to more cities", "wire_markets"),
        ("Fed voters split on the September rate path", "bloomberg_wire"),
        ("Korea chip rally draws leveraged retail flows", "cnbc_wire"),
    ]
    for i in range(60):
        t, src = arts[i % len(arts)]
        db.upsert_article({
            "source_id": src, "title": f"{t} ({i})",
            "link": f"https://wire.example.com/{i}", "summary": t,
            "pub_date": WEEKDAYS[i % len(WEEKDAYS)], "author": "Fixture",
        })

    # editions
    for w_i, (start, end) in enumerate((W1, W2), 1):
        topics = [{
            "rank": r, "title_en": t, "title_zh": f"议题{r}",
            "summary_en": f"Summary of {t.lower()}.",
            "summary_zh": f"议题{r}的中文摘要。",
            "priority": ("critical", "high", "high", "medium")[r - 1],
            "momentum": ("accelerating", "rising", "stable", "fading")[r - 1],
            "evidence": ("strong", "moderate", "moderate", "emerging")[r - 1],
            "coverage": 4 - (r % 2),
            "driver_en": "driver", "driver_zh": "驱动",
            "next_test_en": "next test", "next_test_zh": "检验",
            "stakes_en": "stakes", "stakes_zh": "影响",
        } for r, t in enumerate(TOPICS[w_i - 1:w_i + 3], 1)]
        data = _week_payload(start, end, topics)
        manifest = {"start_date": start, "end_date": end, "episodes": [
            {"date": d, "file": f"{d}.txt", "program": s, "title": f"{s} {d}"}
            for d in WEEKDAYS[(w_i - 1) * 5:w_i * 5] for s in SHOWS]}
        eid = db.upsert_edition(data, manifest, None)
        db.replace_interview_entries(eid, [{
            "guest": "Fixture Guest", "org": "Fixture Capital", "role": "strategist",
            "show": SHOWS[i % len(SHOWS)], "date": d,
            "tone": ("challenging", "evasive", "supportive")[i % 3],
            "questions": ["Do you believe the yen defense can hold?"],
            "notable_quotes": ["The ministry has limited room."],
            "confidence": 0.6,
        } for i, d in enumerate(WEEKDAYS[(w_i - 1) * 5:w_i * 5])])
    return db_path


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        os.environ.get("MEDIA_DESK_DB",
                       Path(__file__).resolve().parents[1] / "data" / "media.db"))
    print(f"fixture DB written to {build(target)}")
