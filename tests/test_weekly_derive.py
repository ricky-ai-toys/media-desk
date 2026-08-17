"""Pure-function tests for weekly schema v2 legacy derivation (no LLM)."""
from backend.app.synth.weekly import _derive_legacy


def test_legacy_fields_derived_from_v2():
    data = _derive_legacy({
        "thesis_en": "Intervention meets carry trade.",
        "thesis_zh": "干预遇上套利。",
        "question_groups": [
            {"category": "policy_credibility",
             "questions_en": ["Will Tokyo act again?", "Does BOJ confirm?"],
             "questions_zh": ["东京会再出手吗？", "日银会确认吗？"]},
            {"category": "market_consequences",
             "questions_en": ["Where does JPY settle?"],
             "questions_zh": ["日元在哪企稳？"]},
        ],
        "top_questions_next_week_en": ["Next week's top"],
        "top_questions_next_week_zh": ["下周重点"],
        "watchpoints": [{
            "trigger_en": "USDJPY above 158",
            "shift_en": "Coverage moves to policy credibility",
            "narrative_en": "FX credibility",
            "priority_raises_en": "If officials intervene",
            "trigger_zh": "美日158",
            "shift_zh": "转向政策公信力",
            "narrative_zh": "汇率公信力",
            "priority_raises_zh": "官员干预",
        }],
        "media_exchanges": [{
            "pattern_en": "p", "premise_en": "p", "response_en": "r", "lesson_en": "l",
            "pattern_zh": "p", "premise_zh": "p", "response_zh": "r", "lesson_zh": "l",
        }],
        "comms_boxes": [{
            "title_en": "FX", "title_zh": "汇率",
            "implication_en": "Companies face renewed scrutiny on translation FX.",
            "implication_zh": "公司面临汇兑压力审查。",
            "risky_en": "Calling the staying power theater is risky.",
            "risky_zh": "称干预为表演有风险。",
            "questions_likely_en": ["Hedge disclosures"],
            "questions_likely_zh": ["对冲披露"],
            "evidence_to_prepare_en": ["Hedge disclosures"],
            "evidence_to_prepare_zh": ["对冲披露"],
        }],
        "pr_counsel": {"opportunity_en": "SEO", "opportunity_zh": "机会"},
    })

    assert data["week_summary_en"] == "Intervention meets carry trade."
    assert data["recurring_questions_en"] == [
        "Will Tokyo act again?", "Does BOJ confirm?", "Where does JPY settle?"]
    assert data["watchlist_en"] == ["USDJPY above 158"]
    # pr_counsel is never stitched from comms_boxes: missing cells stay empty
    # and raise a warning; QC's pr_counsel_complete gate handles enforcement.
    assert data["pr_counsel"]["risk_en"] == ""
    assert data["pr_counsel"]["prepare_en"] == ""
    assert data["pr_counsel"]["opportunity_en"] == "SEO"
    assert any("pr_counsel incomplete" in w for w in data["warnings"])
    ex = data["media_exchanges"][0]
    assert ex["likely_to_recur"] is True
    assert data["evidence_statuses"] == []
    assert data["top_questions_next_week_en"] == ["Next week's top"]