import re
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Set, Tuple


@dataclass(frozen=True)
class Vocab:
    municipalities: Set[str]
    land_use: Set[str]
    plz: Set[str]


_DATE_RANGE_RE = re.compile(
    r"(?P<y1>\d{4})\s*(?:[-–—\.]{2}|\.\.|bis|-)\s*(?P<y2>\d{4})"
)
_ABS_RANGE_RE = re.compile(
    r"(?P<d1>\d{4}-\d{2}-\d{2})\s*(?:\.\.|[-–—]|bis)\s*(?P<d2>\d{4}-\d{2}-\d{2})"
)
_LAST_N_RE = re.compile(r"\blast\s+(?P<n>\d{1,2})\s+(?P<u>years?|months?)\b", re.I)
_SINCE_RE = re.compile(r"\bseit|since\s+(?P<y>\d{4})", re.I)
_YEAR_IN_RE = re.compile(r"\bin\s+(?P<y>\d{4})\b", re.I)
_MONTHLY_RE = re.compile(r"\bmonthly\b|\bper month\b|\bmonatlich\b", re.I)
_GBY_MUNI_RE = re.compile(r"\bby municipality\b|\bnach gemeinde\b|\bnach kommune\b", re.I)
_GBY_LU_RE = re.compile(r"\bby land use\b|\bnach nuta\b|\bnach nutzung\b", re.I)
_PLZ_RE = re.compile(r"\b(\d{5})\b")
_SPLIT_LIST_RE = re.compile(r"[,\;/]| und |&| plus ", re.I)

# Strict land-use whitelist (case-preserving)
_LAND_USE_CANON = {
    "WA", "WR", "MI", "GE", "GI", "W", "M", "WB", "WRZ", "SO", "MK", "MIW", "MD", "MW"
}


def _ymd(y: int, m: int = 1, d: int = 1) -> str:
    return f"{y:04d}-{m:02d}-{d:02d}"


def _clip_default_window(start: str, end: str) -> Tuple[str, str]:
    lo = "2011-01-01"
    hi = "2030-12-31"
    return (max(start, lo), min(end, hi))


def load_vocab(con) -> Vocab:
    muni = set(
        (x[0] or "").strip().lower()
        for x in con.execute(
            "select distinct municipality from brw where municipality is not null"
        ).fetchall()
    )
    lu = set(
        (x[0] or "").strip()
        for x in con.execute(
            "select distinct land_use from brw where land_use is not null"
        ).fetchall()
    )
    plz = set(
        (x[0] or "").strip()
        for x in con.execute(
            "select distinct plz from brw where plz is not null"
        ).fetchall()
    )
    return Vocab(municipalities=muni, land_use=lu, plz=plz)


def _parse_window(text: str) -> Tuple[str, str]:
    s = text.strip()

    m = _ABS_RANGE_RE.search(s)
    if m:
        return _clip_default_window(m.group("d1"), m.group("d2"))

    m = _DATE_RANGE_RE.search(s)
    if m:
        y1, y2 = int(m.group("y1")), int(m.group("y2"))
        start, end = _ymd(min(y1, y2)), _ymd(max(y1, y2), 12, 31)
        return _clip_default_window(start, end)

    m = _LAST_N_RE.search(s)
    if m:
        n = int(m.group("n"))
        unit = m.group("u").lower()
        today = date(2030, 12, 31)  # fixed ceiling per scope
        if "year" in unit:
            start = date(today.year - n + 1, 1, 1)
        else:
            # months
            months = n
            y = today.year
            mth = today.month
            total = y * 12 + (mth - 1) - (months - 1)
            y2 = total // 12
            m2 = (total % 12) + 1
            start = date(y2, m2, 1)
        return _clip_default_window(start.isoformat(), today.isoformat())

    m = _SINCE_RE.search(s)
    if m:
        y = int(m.group("y"))
        return _clip_default_window(_ymd(y), "2030-12-31")

    m = _YEAR_IN_RE.search(s)
    if m:
        y = int(m.group("y"))
        return _ymd(y), _ymd(y, 12, 31)

    # Fallback default window
    return "2011-01-01", "2030-12-31"


def _extract_groupby(text: str) -> str:
    if _MONTHLY_RE.search(text):
        return "month"
    if _GBY_MUNI_RE.search(text):
        return "municipality"
    if _GBY_LU_RE.search(text):
        return "land_use"
    return "none"


def _normalize_tokens(text: str) -> List[str]:
    dirty = re.split(r"[\s\.,;:/\-]+", text.lower())
    return [t for t in dirty if t]


def _extract_municipalities(text: str, vocab: Vocab) -> Optional[List[str]]:
    raw = _SPLIT_LIST_RE.split(text)
    picks: List[str] = []
    for frag in raw:
        tok = frag.strip().lower()
        if not tok:
            continue
        if tok in vocab.municipalities:
            picks.append(tok)
            continue
        # try accent-insensitive compare
        norm = tok.replace("ö", "o").replace("ü", "u").replace("ä", "a").replace("ß", "ss")
        for m in vocab.municipalities:
            mn = m.replace("ö", "o").replace("ü", "u").replace("ä", "a").replace("ß", "ss")
            if norm == mn:
                picks.append(m)
                break
    if not picks:
        # try word tokens against vocab
        for t in _normalize_tokens(text):
            if t in vocab.municipalities:
                picks.append(t)
    return sorted(set(picks)) or None


def _extract_land_use(text: str, vocab: Vocab) -> Optional[List[str]]:
    # Accept whitelist only; keep case
    found = []
    for code in _LAND_USE_CANON:
        if re.search(rf"\b{re.escape(code)}\b", text):
            if code in vocab.land_use or code in _LAND_USE_CANON:
                found.append(code)
    return sorted(set(found)) or None


def _extract_plz(text: str, vocab: Vocab) -> Optional[List[str]]:
    found = [m.group(1) for m in _PLZ_RE.finditer(text)]
    found = [p for p in found if p in vocab.plz]
    return sorted(set(found)) or None


def parse(text: str, vocab: Vocab) -> Dict:
    gb = _extract_groupby(text)
    start, end = _parse_window(text)
    muni = _extract_municipalities(text, vocab)
    lu = _extract_land_use(text, vocab)
    plz = _extract_plz(text, vocab)

    spec = {
        "date_range": {"start": start, "end": end},
        "groupby": gb,
    }
    if muni:
        spec["municipality"] = muni
    if lu:
        spec["land_use"] = lu
    if plz:
        spec["plz"] = plz
    return spec
