"""Single source of truth for the weekly report spec.

Every count range, vocabulary and word budget lives here exactly once:
the synthesis prompt (weekly.py) renders from it and the QC gate (qc.py)
enforces from it. Previously both sides hardcoded their own copies and
had already drifted (prompt said 22-word summaries, QC tolerated 24).

Change a number here and both sides move together.
"""

REPORT_TITLE = "International Financial Media Weekly"

# --- section count contracts ------------------------------------------------
TOPIC_RANGE = (3, 5)           # agenda topics per edition
NARRATIVE_RANGE = (3, 4)       # narratives per edition
MEDIA_EXCHANGES_MIN = 3        # at least this many questioning patterns
WATCHPOINT_RANGE = (3, 5)
WEEK_AHEAD_RANGE = (3, 5)
COMMS_BOXES_MIN = 3
QUESTIONS_PER_GROUP = (3, 5)

# --- controlled vocabularies ------------------------------------------------
PRIORITIES = ("critical", "high", "medium")
MOMENTA = ("accelerating", "rising", "stable", "fading")
EVIDENCE_LEVELS = ("strong", "moderate", "emerging")
QUESTION_CATEGORIES = ("policy_credibility", "market_consequences",
                       "corporate_exposure", "narrative_durability")
EVIDENCE_STATUSES = ("confirmed", "supported", "emerging", "interpretive")

# --- word budgets -----------------------------------------------------------
THESIS_MAX_WORDS = 25
SUMMARY_MAX_WORDS = 22         # prompt budget for agenda summaries
CELL_MAX_WORDS = 10            # driver/why/next_test/stakes/… cells
COMMS_IMPLICATION_MAX_WORDS = 14
TERSE_QC_WORDS = 24            # QC tolerance for summaries (prompt - 2 slack)


def counts_line() -> str:
    """The 'EXACTLY …' sentence shared by prompt and documentation."""
    return (
        f"EXACTLY {TOPIC_RANGE[0]}-{TOPIC_RANGE[1]} agenda topics, "
        f"EXACTLY {NARRATIVE_RANGE[0]}-{NARRATIVE_RANGE[1]} narratives, "
        f"{MEDIA_EXCHANGES_MIN} media_exchanges, "
        f"{WATCHPOINT_RANGE[0]}-{WATCHPOINT_RANGE[1]} watchpoints, "
        f"recurring question groups of "
        f"{QUESTIONS_PER_GROUP[0]}-{QUESTIONS_PER_GROUP[1]} questions each. "
        "No paragraphs."
    )
