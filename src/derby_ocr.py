"""
Derby screenshot import — parsing & member matching (pure logic).

The Hay Day "Neighborhood Derby Task Log" screen lists, per member, a row like::

    <Farm name>      <tasks_done>/<tasks_max>      <points>

e.g. ``You (Tardos)   9/9   2791``. This module turns the OCR'd (or pasted)
text of that screen into structured rows, fuzzily matches each row's farm
name to a known clan member, and assembles an after-derby snapshot the rest
of the app already understands (see ui_new_snapshot_tab.py / neighborhood_manager).

Everything here is pure: no GUI, no disk, no OCR engine. The image→text step
lives in ocr_engine.py (an optional dependency); this module takes the text
and is fully unit-testable. That split is deliberate — OCR is fuzzy and
environment-dependent, but the parsing/matching rules are exact and worth
locking down with tests.

Validation bounds below are derived from Hay Day's derby mechanics and are
used only to *flag* suspicious values (warnings), never to silently drop data —
OCR makes mistakes and the user reviews everything before saving.
"""

import difflib
import re
import unicodedata
from typing import Optional


# ----- validation bounds (Hay Day derby mechanics) --------------------------
# A member's available task count (the Y in "X/Y") is set by their personal
# derby LEAGUE, not by the neighborhood, so denominators legitimately differ
# from row to row:
#     Rookie 5 · Novice 6 · Professional 7 · Expert 8 · Champion 9
# Each member may also buy ONE extra task (+1), so a standard derby tops out at
# Y = 10. Power Derby variants go higher (up to ~15). Points per task run 50-320
# in standard derbies and up to ~400 in themed derbies, so a member's whole-
# derby total is realistically <= tasks_done * 400. These bounds only raise
# *warnings* in the review UI — OCR misreads should be flagged, never dropped.
LEAGUE_TASK_COUNTS = {
    "rookie": 5, "novice": 6, "professional": 7, "expert": 8, "champion": 9,
}
MAX_TASKS_PER_MEMBER = 15          # Champion(9)+extra, with Power Derby headroom
MAX_POINTS_PER_TASK = 400          # highest themed single-task value
MAX_POINTS_PER_MEMBER = 6000       # generous whole-derby ceiling (Power Derby)
MAX_BINGOS_PER_MEMBER = 3          # since 2018 a card can score up to 3 lines
DEFAULT_TASKS_MAX = 8              # Expert allotment; fallback when OCR loses Y

# Lines that are obviously headers / chrome, not member rows.
_HEADER_KEYWORDS = (
    "farm name", "tasks", "points", "bingo", "derby", "task log",
    "neighborhood", "neighbourhood", "rewards", "reward",
)

# Matching: a normalized-name similarity at or above this counts as a match.
DEFAULT_MATCH_THRESHOLD = 0.6


# ----- text normalization ---------------------------------------------------

def _strip_emoji_and_marks(text: str) -> str:
    """Drop emoji, symbols and combining marks, keeping letters/digits/space.
    Hay Day names are full of decorative glyphs that OCR mangles; for *matching*
    we want the plain readable core."""
    out = []
    for ch in unicodedata.normalize("NFKD", text):
        cat = unicodedata.category(ch)
        # L* = letters, N* = numbers, Zs = space; keep those, drop the rest
        if cat[0] in ("L", "N") or ch.isspace():
            out.append(ch)
    return "".join(out)


def normalize_name(name: str) -> str:
    """Canonical form used for fuzzy matching: emoji/punctuation stripped,
    collapsed whitespace, casefolded."""
    cleaned = _strip_emoji_and_marks(name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().casefold()
    return cleaned


def _fix_numeric_ocr(token: str) -> str:
    """Repair the digit confusions OCR commonly makes inside a numeric token:
    O/o→0, l/I/|→1, S→5, B→8. Also strips thousands separators and spaces.
    Only ever applied to tokens we already expect to be numbers."""
    repl = {"O": "0", "o": "0", "l": "1", "I": "1", "|": "1",
            "S": "5", "B": "8"}
    return "".join(repl.get(c, c) for c in token if c not in ", . ")


def _to_int(token: str) -> Optional[int]:
    fixed = _fix_numeric_ocr(token)
    if fixed.isdigit():
        return int(fixed)
    return None


# ----- row parsing ----------------------------------------------------------

# name (lazy, >=1 char) <ws> done / max <ws> points(end of line)
# done/max digits may carry OCR letter-noise, so accept a broad charset and
# repair it afterwards via _to_int.
_ROW_RE = re.compile(
    r"^\s*(?P<name>.+?)\s+"
    r"(?P<done>[0-9OoIlBS|]{1,3})\s*/\s*(?P<max>[0-9OoIlBS|]{1,3})\s+"
    r"(?P<points>[0-9OoIlBS|.,  ]{1,9})\s*$"
)


def _is_header_line(line: str) -> bool:
    low = normalize_name(line)
    if not low:
        return True
    # a line made up only of header words (no member data) is chrome
    return any(kw in low for kw in _HEADER_KEYWORDS) and not _ROW_RE.match(line)


def validate_row(tasks_done: int, tasks_max: int, points: int) -> list:
    """Return a list of human-readable warnings for one parsed row.
    Empty list means the values look sane."""
    warnings = []
    if tasks_max <= 0:
        warnings.append("tasks max is 0 — OCR likely misread it")
    if tasks_done > tasks_max:
        warnings.append(f"completed ({tasks_done}) exceeds available ({tasks_max})")
    if tasks_max > MAX_TASKS_PER_MEMBER:
        warnings.append(f"unusually many tasks ({tasks_max}) — max is ~10")
    if points > MAX_POINTS_PER_MEMBER:
        warnings.append(f"unusually high points ({points})")
    # a member can't realistically score more than ~400 per completed task
    if tasks_done > 0 and points > tasks_done * MAX_POINTS_PER_TASK:
        warnings.append(
            f"points ({points}) high for {tasks_done} tasks — check the read")
    if tasks_done > 0 and points == 0:
        warnings.append("completed tasks but 0 points — check the read")
    return warnings


def parse_task_log(text: str) -> dict:
    """Parse the OCR'd text of a Derby Task Log screen.

    Returns::

        {
          "rows":    [ {name, tasks_done, tasks_max, points, raw, warnings}, ... ],
          "bingo":   {"count": int, "points": int} or None,
          "skipped": [ "<raw line>", ... ],   # non-empty lines we couldn't parse
        }
    """
    rows = []
    skipped = []
    bingo = None
    saw_bingo_header = False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        low = normalize_name(line)
        if "bingo" in low:
            # The bingo summary line (and/or its value line). Capture any
            # two trailing integers as (count, points) if present. Use the RAW
            # line for digits — never the letter-repaired form, which would turn
            # the word "Bingo" itself (B->8, o->0) into spurious numbers.
            saw_bingo_header = True
            nums = re.findall(r"\d+", line)
            if len(nums) >= 2:
                bingo = {"count": int(nums[-2]), "points": int(nums[-1])}
            continue

        if saw_bingo_header and bingo is None:
            # The line right after a "Bingo rewards" header may hold the values.
            nums = re.findall(r"\d+", line)
            if len(nums) >= 2 and not _ROW_RE.match(line):
                bingo = {"count": int(nums[0]), "points": int(nums[1])}
                continue

        if _is_header_line(line):
            continue

        m = _ROW_RE.match(line)
        if not m:
            skipped.append(line)
            continue

        done = _to_int(m.group("done"))
        tmax = _to_int(m.group("max"))
        pts = _to_int(m.group("points"))
        if done is None or tmax is None or pts is None:
            skipped.append(line)
            continue

        name = m.group("name").strip()
        rows.append({
            "name": name,
            "tasks_done": done,
            "tasks_max": tmax,
            "points": pts,
            "raw": line,
            "warnings": validate_row(done, tmax, pts),
        })

    return {"rows": rows, "bingo": bingo, "skipped": skipped}


# ----- matching parsed rows to clan members ---------------------------------

def _member_name_index(members: dict) -> dict:
    """Map normalized member name -> member_id for fuzzy lookup. If two members
    normalize to the same string, the first one wins (rare; flagged by review)."""
    index = {}
    for mid, m in members.items():
        norm = normalize_name(m.get("name", ""))
        if norm and norm not in index:
            index[norm] = mid
    return index


# ----- merging duplicate rows (multiple / overlapping screenshots) ----------

def merge_duplicate_rows(rows: list) -> tuple:
    """Collapse rows that refer to the same farm by normalized name.

    A neighbourhood's task log often doesn't fit in one screenshot, so the user
    pastes/loads several. Where they overlap, the same member appears twice.
    This folds those into one row: since the values describe the *same* final
    standings, the richer reading wins (max of tasks_done / tasks_max / points),
    so a row that got cut off at a screenshot edge can never beat the full one.

    Returns ``(merged_rows, n_merged)`` where ``n_merged`` is how many duplicate
    rows were absorbed. Order follows first appearance, and each surviving row
    gains a ``merged_count`` (1 = seen once). Rows whose name can't be
    normalized (OCR garbage) are never merged — they're kept as-is so nothing is
    silently lost.
    """
    merged = []
    index_by_key = {}
    n_merged = 0
    for row in rows:
        key = normalize_name(row["name"])
        if key and key in index_by_key:
            n_merged += 1
            target = merged[index_by_key[key]]
            target["tasks_done"] = max(target["tasks_done"], row["tasks_done"])
            target["tasks_max"] = max(target["tasks_max"], row["tasks_max"])
            target["points"] = max(target["points"], row["points"])
            target["merged_count"] = target.get("merged_count", 1) + 1
            target["warnings"] = validate_row(
                target["tasks_done"], target["tasks_max"], target["points"])
        else:
            new = dict(row)
            new["merged_count"] = 1
            if key:
                index_by_key[key] = len(merged)
            merged.append(new)
    return merged, n_merged


def match_rows_to_members(rows: list, members: dict,
                          threshold: float = DEFAULT_MATCH_THRESHOLD) -> list:
    """Attach a best-guess member to each parsed row.

    Returns a list parallel to ``rows``::

        {
          "row":          <the parsed row dict>,
          "member_id":    "<tag>" or None,
          "member_name":  "<current name>" or None,
          "score":        0.0..1.0 similarity of the chosen match,
          "candidates":   [(member_id, name, score), ...]  # top few, best first
        }

    A row only auto-binds to a member when the best similarity is >= threshold;
    otherwise member_id is None and the user picks in the review UI.
    """
    index = _member_name_index(members)
    norm_to_member = list(index.items())   # [(norm_name, member_id), ...]
    norm_names = [n for n, _ in norm_to_member]

    used = set()
    results = []
    for row in rows:
        target = normalize_name(row["name"])
        scored = []
        for norm, mid in norm_to_member:
            score = difflib.SequenceMatcher(None, target, norm).ratio()
            scored.append((mid, members[mid].get("name", mid), score))
        scored.sort(key=lambda t: -t[2])

        chosen_id = None
        chosen_name = None
        chosen_score = scored[0][2] if scored else 0.0
        # take the best candidate that clears the threshold and isn't already
        # claimed by an earlier row (one member per row)
        for mid, name, score in scored:
            if score >= threshold and mid not in used:
                chosen_id, chosen_name, chosen_score = mid, name, score
                used.add(mid)
                break

        results.append({
            "row": row,
            "member_id": chosen_id,
            "member_name": chosen_name,
            "score": chosen_score,
            "candidates": scored[:5],
        })
    return results


# ----- assembling a snapshot ------------------------------------------------

def build_prefill_snapshot(matched: list, date: str,
                           derby_comment: str = "",
                           default_tasks_max: int = DEFAULT_TASKS_MAX) -> dict:
    """Turn matched rows into an after-derby snapshot dict ready to hand to
    NewSnapshotTab as a prefill (for a NEW snapshot — no snapshot_id).

    Only rows that resolved to a member_id are included. Every included member
    is marked as having participated (they appear in the task log), with their
    parsed tasks/points. Levels are intentionally omitted so the snapshot
    editor falls back to each member's last known level.
    """
    entries = []
    seen = set()
    for item in matched:
        mid = item.get("member_id")
        if not mid or mid in seen:
            continue
        seen.add(mid)
        row = item["row"]
        tmax = row["tasks_max"] if row["tasks_max"] > 0 else default_tasks_max
        entries.append({
            "member_id": mid,
            "derby_participated": True,
            "tasks_done": row["tasks_done"],
            "tasks_max": tmax,
            "derby_points": row["points"],
        })
    return {
        "date": date,
        "type": "after_derby",
        "derby_comment": derby_comment,
        "entries": entries,
    }
