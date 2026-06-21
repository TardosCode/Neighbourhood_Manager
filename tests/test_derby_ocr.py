"""
Tests for derby_ocr — parsing & member matching for Derby Task Log screenshots.

The SAMPLE_LOG below mirrors the real screenshot the feature was built around
(IMG_2762: a Neighborhood Derby Task Log), including its header chrome and the
trailing Bingo rewards line, so the parser is exercised against realistic text.
"""

import derby_ocr as ocr


# Mirrors the attached screenshot's content as OCR might return it.
SAMPLE_LOG = """\
Neighborhood Derby Task Log
Farm Name        Tasks   Points
You (Tardos)     9/9     2791
Belaki farm      8/8     2553
Jeydi            5/8     1180
Sentos           7/8     1244
Bakarsulu's farm 3/8     662
Kaodryn farm     3/8     609
Karasayon??      4/8     540
Bingo rewards    Bingo   Points
                 1       0
"""


# --------------------------------------------------------------------------
# numeric repair helpers
# --------------------------------------------------------------------------

def test_fix_numeric_ocr():
    assert ocr._to_int("2791") == 2791
    assert ocr._to_int("2,791") == 2791
    assert ocr._to_int("l0") == 10        # l -> 1
    assert ocr._to_int("8OO") == 800      # O -> 0
    assert ocr._to_int("S40") == 540      # S -> 5
    assert ocr._to_int("abc") is None


def test_normalize_name_strips_decoration():
    assert ocr.normalize_name("You (Tardos)") == "you tardos"
    assert ocr.normalize_name("  Belaki   farm ") == "belaki farm"
    assert ocr.normalize_name("🌾Jeydi⭐") == "jeydi"
    assert ocr.normalize_name("Bakarsulu's farm") == "bakarsulus farm"


# --------------------------------------------------------------------------
# parse_task_log
# --------------------------------------------------------------------------

def test_parse_full_log():
    result = ocr.parse_task_log(SAMPLE_LOG)
    rows = result["rows"]
    assert len(rows) == 7

    first = rows[0]
    assert first["name"] == "You (Tardos)"
    assert first["tasks_done"] == 9
    assert first["tasks_max"] == 9
    assert first["points"] == 2791
    assert first["warnings"] == []

    # spot-check a mid and last row
    assert rows[2]["name"] == "Jeydi"
    assert (rows[2]["tasks_done"], rows[2]["tasks_max"], rows[2]["points"]) == (5, 8, 1180)
    assert rows[6]["name"] == "Karasayon??"
    assert rows[6]["points"] == 540


def test_parse_extracts_bingo():
    result = ocr.parse_task_log(SAMPLE_LOG)
    assert result["bingo"] == {"count": 1, "points": 0}


def test_parse_skips_headers_no_false_rows():
    result = ocr.parse_task_log(SAMPLE_LOG)
    # none of the header lines should sneak into rows or skipped-as-data
    names = [r["name"].lower() for r in result["rows"]]
    assert "farm name" not in names
    assert all("bingo" not in n for n in names)


def test_parse_handles_ocr_digit_noise():
    text = "Sentos     7/8     l244\nKaodryn farm   3/8   6O9"
    rows = ocr.parse_task_log(text)["rows"]
    assert rows[0]["points"] == 1244     # l244 -> 1244
    assert rows[1]["points"] == 609      # 6O9 -> 609


def test_parse_names_with_spaces_and_punct():
    rows = ocr.parse_task_log("Bakarsulu's farm 3/8 662")["rows"]
    assert len(rows) == 1
    assert rows[0]["name"] == "Bakarsulu's farm"
    assert rows[0]["tasks_done"] == 3


def test_parse_records_unparseable_lines():
    text = "Valid Name 5/8 100\nthis is just noise with no numbers"
    result = ocr.parse_task_log(text)
    assert len(result["rows"]) == 1
    assert any("noise" in s for s in result["skipped"])


def test_validate_row_flags_anomalies():
    # completed > taken
    assert ocr.validate_row(9, 8, 500)
    # zero tasks_max
    assert ocr.validate_row(0, 0, 0)
    # tasks done but no points
    assert any("0 points" in w for w in ocr.validate_row(5, 8, 0))
    # sane row -> no warnings
    assert ocr.validate_row(8, 8, 2553) == []


# --------------------------------------------------------------------------
# matching to members
# --------------------------------------------------------------------------

def _members(*names):
    """Build a members dict keyed by synthetic tags."""
    out = {}
    for i, name in enumerate(names):
        out[f"#{i}"] = {"member_id": f"#{i}", "name": name, "in_clan": True}
    return out


def test_match_exact_and_fuzzy():
    members = _members("Tardos", "Belaki farm", "Jeydi", "Sentos")
    rows = ocr.parse_task_log(SAMPLE_LOG)["rows"]
    matched = ocr.match_rows_to_members(rows, members)

    by_name = {m["row"]["name"]: m for m in matched}
    # "You (Tardos)" should fuzzy-match the member "Tardos"
    assert by_name["You (Tardos)"]["member_name"] == "Tardos"
    # exact-ish names bind
    assert by_name["Belaki farm"]["member_name"] == "Belaki farm"
    assert by_name["Jeydi"]["member_name"] == "Jeydi"
    # an unknown farm stays unmatched
    assert by_name["Kaodryn farm"]["member_id"] is None


def test_match_is_one_to_one():
    # two rows that both look like "Jeydi" must not bind to the same member
    members = _members("Jeydi")
    rows = [
        {"name": "Jeydi", "tasks_done": 5, "tasks_max": 8, "points": 100,
         "raw": "", "warnings": []},
        {"name": "Jeydi", "tasks_done": 3, "tasks_max": 8, "points": 50,
         "raw": "", "warnings": []},
    ]
    matched = ocr.match_rows_to_members(rows, members)
    bound = [m for m in matched if m["member_id"] is not None]
    assert len(bound) == 1            # only one row claims the single member


def test_match_threshold_blocks_weak():
    members = _members("Completely Different Name")
    rows = [{"name": "xyz", "tasks_done": 1, "tasks_max": 8, "points": 10,
             "raw": "", "warnings": []}]
    matched = ocr.match_rows_to_members(rows, members, threshold=0.6)
    assert matched[0]["member_id"] is None
    # but candidates are still offered for manual selection
    assert matched[0]["candidates"]


# --------------------------------------------------------------------------
# building a snapshot
# --------------------------------------------------------------------------

def test_build_prefill_snapshot():
    members = _members("Tardos", "Belaki farm", "Jeydi", "Sentos")
    rows = ocr.parse_task_log(SAMPLE_LOG)["rows"]
    matched = ocr.match_rows_to_members(rows, members)
    snap = ocr.build_prefill_snapshot(matched, "2026-06-19")

    assert snap["type"] == "after_derby"
    assert snap["date"] == "2026-06-19"
    assert "snapshot_id" not in snap          # it's a NEW snapshot
    # only the 4 matched members become entries (Kaodryn/Karasayon/Bakarsulu
    # don't exist in this members dict)
    assert len(snap["entries"]) == 4
    e = snap["entries"][0]
    assert e["member_id"] == "#0"             # Tardos
    assert e["derby_participated"] is True
    assert e["tasks_done"] == 9 and e["tasks_max"] == 9
    assert e["derby_points"] == 2791
    assert "level" not in e                   # falls back to last known level


def test_build_prefill_uses_default_tasks_max_when_zero():
    members = _members("Alice")
    matched = [{
        "member_id": "#0", "member_name": "Alice", "score": 1.0,
        "candidates": [],
        "row": {"name": "Alice", "tasks_done": 4, "tasks_max": 0,
                "points": 300, "raw": "", "warnings": []},
    }]
    snap = ocr.build_prefill_snapshot(matched, "2026-06-19", default_tasks_max=8)
    assert snap["entries"][0]["tasks_max"] == 8
