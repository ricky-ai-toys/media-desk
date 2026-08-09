"""Daily episode analysis: runs the v4 daily-analysis prompt against a transcript
via the LLM and stores markdown + structured hot-topics/tension into the DB."""
import re

from .. import db, llm

DAILY_SYSTEM = (
    "You are a senior media analyst dissecting a single episode of Bloomberg Asia TV. "
    "Read the transcript and produce a structured analysis. Work only from the transcript — "
    "no outside research, no invented quotes, no tickers not stated in the transcript. "
    "Single-source synthesis: attribute interpretive claims to the outlet "
    "('Bloomberg framed…') rather than stating them as independent fact."
)

DAILY_OUTLINE = """
Output EXACTLY these Markdown sections:

## 1. Episode Header
- Show name
- Date
- Anchor(s)
- Episode title

## 2. Hot Topics (3-5)
For each: **N. Topic Title** (bold, numbered, specific — e.g. "SMIC $4.3B Shanghai IPO" not "China IPOs")
- *Description:* 1-2 sentences
- *China lens:* Political / Commercial / Tech / Macro / N/A
- *Tone:* Label (score), e.g. Cautious (-1), Bullish (+2)

## 3. Reporting Frame
### Dominant Frame — one sentence, the editorial spine.
### Verbatim Quotes (3-5) — each: "Quote" — Full Name, Title, Firm, Month D; and a sentiment label + numeric score.
### Sentiment Summary — table: Domain | Sentiment | Score | Key Driver
### Framing Amplification — which angles are repeated or emphasized.
### Framing Suppression — which angles are downplayed, ignored, or not asked.
### Contrarian Views — divergent views, verbatim quote, full attribution. "None identified" if absent.

## 4. Corporate Voices
Table: Company | Spokesperson | Role | Topic | Stance (Bullish/Bearish/Neutral) | Quote (verbatim)

## 5. Anchor-Guest Tension
Numbered blocks. For each exchange:
1. **Anchor question:** [verbatim question]
   **Guest reply:** [verbatim or closest transcript quote]
   **Tension point:** [what is being contested, 1-2 sentences: challenge, evasion, complacency, or alignment]

## 6. Anchor's Forecasting Push
**Forecast requested:** [what the anchor pressed the guest to predict]
**Guest forecast:** [verbatim or closest]
**Confidence markers:** [hedges, "unlikely", "too early", numbers given]

## 7. Agenda Signal
- **Topic-level agenda cue:** [one sentence: what should PR/comms desks watch next from this episode]
- **Weak signals:** [1-2 bullets of early, faint signals worth watching]

Keep quotes verbatim from the transcript. Do not editorialize outside the sections."""


def analyze_episode(episode_id: str, transcript: str, show: str, date: str, title: str) -> dict:
    user = (f"Show: {show or 'unknown'}\nDate: {date}\nEpisode title: {title or episode_id}\n"
            f"Transcript word count: {len(transcript.split())}\n\nTRANSCRIPT:\n{transcript}\n\n{DAILY_OUTLINE}")
    md = llm.chat([
        {"role": "system", "content": DAILY_SYSTEM},
        {"role": "user", "content": user},
    ], max_tokens=8192)
    db.upsert_analysis(episode_id, md, _hot_topics(md), _tension(md))
    return md


def _hot_topics(md: str) -> list[dict]:
    return [{"rank": int(m.group(1)), "title": m.group(2).strip()}
            for m in re.finditer(r"\*\*(\d+)\.\s+(.+?)\*\*", md)]


def _tension(md: str) -> list[dict]:
    return [{"block": b[:200]} for b in re.split(r"\n\s*\d+\.?\s*\*\*Anchor question[:\*]*", md or "")[1:]]