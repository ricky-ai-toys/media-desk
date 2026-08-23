"""This-week-vs-last word cloud for the web deck.

Term frequencies come from the edition's transcript chunks; the previous
edition's frequencies dampen carried-over words so what rises this week is
what gets visual weight. Rendered server-side with amueller/word_cloud into
a PNG that matches the deck palette (paper background, ink words, signal-red
risers). The PNG is cached under data/wordclouds/.
"""
import datetime
import re
from collections import Counter
from pathlib import Path

from . import config, db

FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)

_STOP_EXTRA = {
    "said", "says", "will", "that", "this", "with", "from", "have", "what",
    "about", "would", "their", "there", "which", "they", "been", "more",
    "also", "them", "were", "than", "then", "when", "your", "just", "like",
    "into", "over", "after", "amid", "some", "very", "much", "many", "make",
    "made", "going", "really", "think", "know", "because", "still", "back",
    "down", "well", "even", "most", "here", "does", "did", "doing", "talk",
    "talked", "looks", "look", "week", "show", "anchor", "guest", "question",
    "questions", "company", "companies", "market", "markets", "percent",
}

_WORD = re.compile(r"[a-z]{4,}")


def _stopwords() -> set[str]:
    try:
        from wordcloud import STOPWORDS
        return set(STOPWORDS) | _STOP_EXTRA
    except ImportError:
        return set(_STOP_EXTRA)


def _font_path() -> str | None:
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            return p
    return None


def _freqs(edition: dict) -> Counter:
    stop = _stopwords()
    counts: Counter = Counter()
    with db.conn() as c:
        rows = c.execute(
            "SELECT tc.text FROM transcript_chunks tc JOIN episodes e "
            "ON e.id=tc.episode_id WHERE e.pub_date BETWEEN ? AND ?",
            (edition["start_date"], edition["end_date"])).fetchall()
    for (text,) in rows:
        counts.update(w for w in _WORD.findall((text or "").lower())
                      if w not in stop)
    return counts


def _prev_edition(edition: dict) -> dict | None:
    with db.conn() as c:
        row = c.execute(
            "SELECT id, start_date, end_date FROM editions WHERE start_date<? "
            "ORDER BY start_date DESC LIMIT 1",
            (edition["start_date"],)).fetchone()
    return dict(row) if row else None


def _edition(edition_id: str) -> dict | None:
    with db.conn() as c:
        row = c.execute(
            "SELECT id, start_date, end_date FROM editions WHERE id=?",
            (edition_id,)).fetchone()
    return dict(row) if row else None


def build_png(edition_id: str) -> bytes | None:
    """PNG for the edition, or None when it cannot be produced."""
    try:
        from wordcloud import WordCloud
    except ImportError:
        return None
    font = _font_path()
    if not font:
        return None
    ed = _edition(edition_id)
    if not ed:
        return None

    cur = _freqs(ed)
    prev = _freqs(_prev_edition(ed)) if _prev_edition(ed) else Counter()

    scored: dict[str, float] = {}
    risers: set[str] = set()
    for w, n in cur.items():
        if n < 2:
            continue
        p = prev.get(w, 0)
        rise = n - p
        if rise > 0 and n >= 3:
            risers.add(w)
        scored[w] = n + max(0, rise) * 2
    top = dict(sorted(scored.items(), key=lambda kv: -kv[1])[:80])
    if len(top) < 8:
        return None

    def color_func(word: str, **_kw) -> str:
        if word in risers:
            return "#a12b23"          # signal red — new/rising this week
        return "#3d444c"              # slate ink — carried context

    wc = WordCloud(
        font_path=font, width=640, height=230, background_color="#f7f6f1",
        mode="RGB", prefer_horizontal=0.95, relative_scaling=0.55,
        max_words=80, scale=2, collocations=False,
        color_func=color_func, random_state=7,
    )
    wc.generate_from_frequencies(top)
    return _png_bytes(wc, Path(config.ROOT / "data" / "wordclouds") / f"{edition_id}.png")


def _png_bytes(wc, png_path: Path) -> bytes:
    """Persist a cache copy and return encoded PNG bytes."""
    png_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = png_path.with_suffix(".tmp.png")
    wc.to_image().save(tmp, format="PNG")
    data = tmp.read_bytes()
    tmp.replace(png_path)
    return data
