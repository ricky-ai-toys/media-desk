"""This-week-vs-last word clouds for the web deck.

Two server-rendered PNGs per edition, generated from that edition's
transcript chunks:

  {eid}.png       THIS WEEK — ink words, signal-red risers (terms whose
                  frequency jumped versus the previous edition)
  {eid}.prev.png  LAST WEEK — same pipeline on the previous edition's
                  frequencies, drawn in muted grey so it reads as context

Anchor/guest/show names and broadcast chatter never reach the cloud: a
static blocklist is extended at runtime with guest/org/show tokens pulled
from interview_entries, so presenter names disappear without per-name
hardcoding. PNGs are cached under data/wordclouds/.
"""
import re
from collections import Counter
from pathlib import Path

from . import config, db

FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)

# Broadcast filler and other words that carry no editorial signal.
_STOP_EXTRA = {
    "said", "says", "will", "that", "this", "with", "from", "have", "what",
    "about", "would", "their", "there", "which", "they", "been", "more",
    "also", "them", "were", "than", "then", "when", "your", "just", "like",
    "into", "over", "after", "amid", "some", "very", "much", "many", "make",
    "made", "going", "really", "think", "know", "because", "still", "back",
    "down", "well", "even", "most", "here", "does", "did", "doing", "talk",
    "talked", "looks", "look", "week", "show", "anchor", "guest", "question",
    "questions", "company", "companies", "market", "markets", "percent",
    # TV-chatter filler
    "today", "tomorrow", "yesterday", "gonna", "wanna", "gotta", "kind",
    "sort", "actually", "basically", "literally", "thing", "things",
    "stuff", "point", "points", "idea", "sure", "maybe", "perhaps", "mean",
    "means", "meant", "want", "wants", "wanted", "tell", "tells", "told",
    "saying", "come", "comes", "came", "take", "takes", "taken", "give",
    "gives", "gave", "keep", "keeps", "kept", "quite", "pretty", "right",
    "okay", "yeah", "thank", "thanks", "welcome", "please", "sorry",
    "folks", "everyone", "somebody", "anybody", "something", "anything",
    "nothing", "always", "never", "often", "usually", "again", "already",
    "almost", "around", "ahead", "join", "joining", "joined", "live",
    "host", "hosts", "hosting", "presenter", "listen", "watch", "hear",
    # spoken-English connective tissue
    "coming", "course", "last", "seeing", "looking", "story", "next",
    "every", "another", "others", "whole", "less", "absolutely",
    "according", "accordingly", "certainly", "obviously", "clearly",
    "exactly", "hopefully", "probably", "crazy", "huge", "kinda", "sorta",
}

# Channels / programmes / well-known presenter tokens (lowercase).
_NAME_STATIC = {
    "cnbc", "bloomberg", "reuters", "squawk", "street", "signs", "asia",
    "haslinda", "amin", "news", "radio", "television", "tv", "wire",
    "exclusive", "breaking",
}

_WORD = re.compile(r"[a-z]{4,}")

# Common given names — presenters and guests that never made it into the
# interview table still should not surface as cloud words.
_FIRST_NAMES = {
    "paul", "john", "david", "michael", "james", "robert", "peter", "mark",
    "martin", "richard", "thomas", "chris", "christopher", "daniel",
    "matt", "matthew", "andrew", "joseph", "charles", "william", "george",
    "henry", "edward", "ryan", "kevin", "brian", "jason", "justin", "eric",
    "patrick", "sean", "adam", "nathan", "gary", "larry", "steve",
    "stephen", "kenneth", "scott", "gregory", "samuel", "benjamin",
    "mary", "linda", "karen", "susan", "sarah", "emily", "emma", "olivia",
    "sophia", "grace", "lucy", "julia", "maria", "hannah", "rachel",
    "rebecca", "laura", "claire", "diana", "irene", "joanna", "kate",
}


def _stopwords() -> set[str]:
    stop = set(_STOP_EXTRA) | _NAME_STATIC | _FIRST_NAMES
    try:
        from wordcloud import STOPWORDS
        stop |= set(STOPWORDS)
    except ImportError:
        pass
    return stop | _name_tokens()


def _name_tokens() -> set[str]:
    """Guest / organisation / show tokens from past interviews."""
    out: set[str] = set()
    try:
        with db.conn() as c:
            rows = c.execute(
                "SELECT guest, org, show FROM interview_entries "
                "WHERE IFNULL(guest,'')<>'' OR IFNULL(org,'')<>'' "
                "OR IFNULL(show,'')<>''").fetchall()
        for g, o, s in rows:
            for name in (g, o, s):
                out.update(_WORD.findall((name or "").lower()))
    except Exception:
        pass
    return out


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
    # Fold simple plurals into their singular when both occur, so
    # "year"/"years" pool their weight ("earnings"/"holdings" survive —
    # the -ings form is the real word).
    for w in list(counts):
        if w.endswith("s") and not w.endswith(("ss", "us", "is", "as", "ings")):
            base = w[:-1]
            if base in counts:
                counts[base] += counts.pop(w)
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


def _scored(freqs: Counter, prev: Counter) -> tuple[dict[str, float], set[str]] | None:
    """Score a week's terms against a baseline; None when too sparse.

    Carried context keeps its raw weight; risers get boosted so what is
    new this week dominates the picture.
    """
    scored: dict[str, float] = {}
    risers: set[str] = set()
    for w, n in freqs.items():
        if n < 2:
            continue
        p = prev.get(w, 0)
        rise = n - p
        if rise > 0 and n >= 3:
            risers.add(w)
        scored[w] = n + max(0, rise) * 2
    top = dict(sorted(scored.items(), key=lambda kv: -kv[1])[:80])
    return (top, risers) if len(top) >= 8 else None


def _cloud(scored: dict[str, float], color_func) -> "WordCloud":
    from wordcloud import WordCloud
    wc = WordCloud(
        font_path=_font_path(), width=1000, height=320,
        background_color="#f7f6f1", mode="RGB", prefer_horizontal=0.95,
        relative_scaling=0.55, max_words=80, scale=2, collocations=False,
        color_func=color_func, random_state=7,
    )
    wc.generate_from_frequencies(scored)
    return wc


_INK = "#3d444c"      # slate ink — carried context
_RED = "#a12b23"      # signal red — rising this week
_MUTED = "#8a9099"    # receded grey — last week's cloud


def build_png(edition_id: str, week: str = "this") -> bytes | None:
    """Cached PNG for the edition ('this' or 'prev'), or None when it
    cannot be produced."""
    cache_dir = Path(config.ROOT / "data" / "wordclouds")
    suffix = "" if week == "this" else ".prev"
    cached = cache_dir / f"{edition_id}{suffix}.png"
    if cached.exists():
        return cached.read_bytes()

    try:
        from wordcloud import WordCloud  # noqa: F401  availability probe
    except ImportError:
        return None
    if not _font_path():
        return None
    ed = _edition(edition_id)
    if not ed:
        return None
    prev_ed = _prev_edition(ed)

    cur = _freqs(ed)
    prev_freqs = _freqs(prev_ed) if prev_ed else Counter()

    results: dict[str, bytes] = {}
    cur_scored = _scored(cur, prev_freqs)
    if cur_scored is None:
        return None
    top, risers = cur_scored
    results["this"] = _png_bytes(
        _cloud(top, lambda w, **_k: _RED if w in risers else _INK),
        cache_dir / f"{edition_id}.png")

    prev_scored = _scored(prev_freqs, Counter()) if prev_ed else None
    if prev_scored:
        results["prev"] = _png_bytes(
            _cloud(prev_scored[0], lambda w, **_k: _MUTED),
            cache_dir / f"{edition_id}.prev.png")

    return results.get(week)


def _png_bytes(wc, png_path: Path) -> bytes:
    """Persist a cache copy and return encoded PNG bytes."""
    png_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = png_path.with_suffix(".tmp.png")
    wc.to_image().save(tmp, format="PNG")
    data = tmp.read_bytes()
    tmp.replace(png_path)
    return data
