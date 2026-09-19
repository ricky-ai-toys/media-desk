"""This-week-vs-last word clouds for the web deck.

Two server-rendered PNGs per edition, generated from that edition's
transcript chunks:

  {eid}.png       THIS WEEK — ink words, signal-red risers
  {eid}.prev.png  LAST WEEK — same pipeline, muted grey context

Editorial quality comes from three mechanisms:

* Terms, not word salad — unigrams plus frequent bigrams ("central bank",
  "treasury yield"), with simple plurals folded into their singular.
* Lift scoring — a term's weight is its count this week multiplied by how
  far it sits above its own background average over previous editions.
  Words like "year", "good" or "business" appear every week in similar
  numbers, so their lift ~1 and they sink; terms that genuinely spiked
  rise to the top without needing to be stoplisted.
* Noise filters — stopwords for TV chatter and generic words, plus
  guest/org/show tokens pulled dynamically from interview_entries.

PNGs are cached under data/wordclouds/.
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

# Broadcast filler and generic words that carry no editorial signal.
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
    # generic time / quantity / quality words — ever-present, zero signal
    "good", "bad", "great", "nice", "best", "better", "worse", "year",
    "years", "month", "months", "time", "times", "long", "short", "term",
    "terms", "first", "second", "third", "number", "numbers", "part",
    "parts", "world", "global", "business", "money", "cash", "high",
    "higher", "low", "lower", "space", "left", "away", "lot", "lots",
    "half", "piece", "side", "hold", "holds", "might", "must", "shall",
    "among", "within", "upon", "whose", "guys", "able", "hand", "hands",
    "continue", "different", "difference", "least", "little", "moment",
    "seen", "need", "needs", "strong", "interesting", "expect", "expected",
    "getting", "worth", "really", "quite", "perhaps",
    "across", "along", "toward", "towards", "despite", "whether", "instead",
    "rather", "morning", "later", "move", "moves", "three", "four", "five",
    "six", "seven", "eight", "ten", "lanka", "baba",
}

# Channels / programmes / well-known presenter tokens (lowercase).
_NAME_STATIC = {
    "cnbc", "bloomberg", "reuters", "squawk", "street", "signs", "asia",
    "haslinda", "amin", "news", "radio", "television", "tv", "wire",
    "exclusive", "breaking", "hong", "kong",
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
    "brandon", "doug", "stuart", "trevor", "aaron", "carl", "ralph",
    "dean", "glenn", "oscar", "hugo", "leon", "ross", "stan", "victor",
    "anthony", "gerald", "marvin", "clifford", "wilbur", "norman",
}

# Scale/quantity words — finance flavor but zero editorial content.
_QUANTITY = {"billion", "million", "trillion", "hundred", "thousands", "dozens"}

# How many previous editions form the background average for lift scoring.
_BG_EDITIONS = 4

# Minimum lift for a term to be drawn at all — kills ever-present words.
_MIN_LIFT = 1.25

# Tail cut: terms below this share of the top score are dropped.
_MIN_SHARE = 0.05


def _stopwords() -> set[str]:
    stop = set(_STOP_EXTRA) | _NAME_STATIC | _FIRST_NAMES | _QUANTITY
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


def _edition(edition_id: str) -> dict | None:
    with db.conn() as c:
        row = c.execute(
            "SELECT id, start_date, end_date, created_at FROM editions WHERE id=?",
            (edition_id,)).fetchone()
    return dict(row) if row else None


def _fresh(png: Path, created_at: str) -> bool:
    """A cached cloud is valid only if drawn no earlier than the edition's
    last write — re-synthesis must not keep serving the old image."""
    if not png.exists() or not created_at:
        return False
    try:
        mtime = datetime.datetime.fromtimestamp(
            png.stat().st_mtime, tz=datetime.timezone.utc).isoformat()
    except OSError:
        return False
    return mtime >= created_at


def _prev_editions(edition: dict, limit: int = _BG_EDITIONS) -> list[dict]:
    """Editions immediately before this one, newest first."""
    with db.conn() as c:
        rows = c.execute(
            "SELECT id, start_date, end_date FROM editions WHERE start_date<? "
            "ORDER BY start_date DESC LIMIT ?",
            (edition["start_date"], limit)).fetchall()
    return [dict(r) for r in rows]


def _terms(edition: dict) -> Counter:
    """Unigram + bigram frequencies for one edition.

    Plurals fold into their singular ("earnings" survives — the -ings form
    is the real word); bigrams pair adjacent content words so phrases like
    "central bank" or "treasury yield" surface as single terms.
    """
    stop = _stopwords()
    with db.conn() as c:
        rows = c.execute(
            "SELECT tc.text FROM transcript_chunks tc JOIN episodes e "
            "ON e.id=tc.episode_id WHERE e.pub_date BETWEEN ? AND ?",
            (edition["start_date"], edition["end_date"])).fetchall()

    stream: list[str] = []
    for (text,) in rows:
        stream.extend(_WORD.findall((text or "").lower()))
    content = [w for w in stream if w not in stop]

    counts: Counter = Counter(content)
    fold: dict[str, str] = {}
    for w in list(counts):
        if w.endswith("s") and not w.endswith(("ss", "us", "is", "as", "ings")):
            base = w[:-1]
            if base in counts:
                fold[w] = base
                counts[base] += counts.pop(w)
    if fold:
        counts = Counter({w: n for w, n in counts.items() if w not in fold})
        content = [fold.get(w, w) for w in content]

    counts.update(f"{a} {b}" for a, b in zip(content, content[1:]))
    return counts


def _scored(cur: Counter, bg: Counter, prev_week: Counter,
            is_bigram: callable) -> tuple[dict[str, float], set[str]] | None:
    """Lift-scored terms for the cloud plus the riser set for colouring.

    score = count × lift^1.5 where lift = (count+1)/(background+2).
    A term needs count ≥ 3 (unigram) / ≥ 2 (bigram) and lift ≥ _MIN_LIFT;
    the tail is cut at a fraction of the top score so transcription junk
    never renders. Risers — drawn red — must have roughly doubled versus
    last week, and only the strongest few keep the colour so red stays a
    signal instead of painting the whole cloud.
    """
    scored: dict[str, float] = {}
    for w, n in cur.items():
        if is_bigram(w):
            if n < 2:
                continue
        elif n < 3:
            continue
        lift = (n + 1) / (bg.get(w, 0) + 2)
        if lift < _MIN_LIFT:
            continue
        scored[w] = n * lift ** 1.5
    if len(scored) < 8:
        return None
    top_score = max(scored.values())
    top = {w: s for w, s in scored.items() if s >= top_score * _MIN_SHARE}
    top = dict(sorted(top.items(), key=lambda kv: -kv[1])[:60])

    risers = set()
    for w in top:
        n = cur[w]
        pw = prev_week.get(w, 0)
        if is_bigram(w):
            if n >= 6 and n >= pw * 2 + 6:
                risers.add(w)
        elif n >= 5 and n >= pw * 2 + 4:
            risers.add(w)
    risers = set(sorted(risers, key=lambda w: -top[w])[:30])
    return top, risers


def _plain_top(cur: Counter, is_bigram: callable) -> dict[str, float] | None:
    """Plain frequency ranking — used for the muted last-week cloud."""
    scored = {w: float(n) for w, n in cur.items()
              if n >= (2 if is_bigram(w) else 3)}
    top = dict(sorted(scored.items(), key=lambda kv: -kv[1])[:80])
    return top if len(top) >= 8 else None


_INK = "#3d444c"      # slate ink — carried context
_RED = "#a12b23"      # signal red — rising this week
_MUTED = "#8a9099"    # receded grey — last week's cloud


def _cloud(scored: dict[str, float], color_func) -> "WordCloud":
    from wordcloud import WordCloud
    wc = WordCloud(
        font_path=_font_path(), width=1000, height=320,
        background_color="#f7f6f1", mode="RGB", prefer_horizontal=0.95,
        relative_scaling=0.55, max_words=60, scale=2, collocations=False,
        color_func=color_func, random_state=7,
    )
    wc.generate_from_frequencies(scored)
    return wc


def build_png(edition_id: str, week: str = "this") -> bytes | None:
    """Cached PNG for the edition ('this' or 'prev'), or None when it
    cannot be produced."""
    ed = _edition(edition_id)
    if not ed:
        return None
    cache_dir = Path(config.ROOT / "data" / "wordclouds")
    suffix = "" if week == "this" else ".prev"
    cached = cache_dir / f"{edition_id}{suffix}.png"
    if _fresh(cached, ed.get("created_at") or ""):
        return cached.read_bytes()

    try:
        from wordcloud import WordCloud  # noqa: F401  availability probe
    except ImportError:
        return None
    if not _font_path():
        return None
    is_bigram = lambda w: " " in w  # noqa: E731

    cur = _terms(ed)
    prevs = _prev_editions(ed)
    prev_week = _terms(prevs[0]) if prevs else Counter()
    bg_terms: Counter = Counter()
    for p in prevs:
        bg_terms.update(_terms(p))
    bg = Counter({w: n / len(prevs) for w, n in bg_terms.items()}) if prevs else Counter()

    results: dict[str, bytes] = {}

    cur_scored = _scored(cur, bg, prev_week, is_bigram)
    if cur_scored is None:
        return None
    top, risers = cur_scored
    results["this"] = _png_bytes(
        _cloud(top, lambda w, **_k: _RED if w in risers else _INK),
        cache_dir / f"{edition_id}.png")

    if prevs:
        prev_scored = _plain_top(prev_week, is_bigram)
        if prev_scored:
            results["prev"] = _png_bytes(
                _cloud(prev_scored, lambda w, **_k: _MUTED),
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
