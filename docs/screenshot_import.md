# Import derby results from a screenshot

Entering a whole derby by hand is tedious. This feature reads the **Neighborhood
Derby Task Log** screen straight from a screenshot (or pasted text), matches each
farm name to a clan member, and pre-fills a new after-derby snapshot for you to
review and save.

## How to use it

1. In the game, open the derby and tap the **Task Log** (the list of members with
   their tasks and points). Take a screenshot.
2. In the app: **Neighbourhood Manager → New Snapshot → 📷 Import derby screenshot**.
3. Either:
   - **Load screenshot…** — if you have Tesseract OCR installed, the app reads the
     image directly; or
   - **Paste text** — on a phone this is often easiest: use Google Lens or your
     phone's built-in "copy text from image", then paste into the box.
4. Press **Parse**. The app extracts each `Name — X/Y — Points` row and guesses
   which member it is.
5. **Review & match**: fix any member assignment (dropdown), correct any number
   the OCR misread (rows with suspicious values are flagged), and skip rows that
   aren't members.
6. **Use these results** → the New Snapshot editor opens pre-filled. Adjust levels
   / fate if you like, then **Save**.

Nothing is uploaded anywhere — OCR runs locally (or you paste text yourself),
consistent with the app's "your data stays on your machine" promise.

## Optional: local OCR with Tesseract

The paste workflow needs no extra software. To read images directly, install:

```bash
pip install -r requirements-ocr.txt        # pytesseract (Pillow is already a dep)
```

…plus the **Tesseract engine** itself:

- **Windows:** install from <https://github.com/UB-Mannheim/tesseract/wiki>
- **macOS:** `brew install tesseract`
- **Debian/Ubuntu:** `sudo apt install tesseract-ocr`

If Tesseract isn't found, the importer just tells you and falls back to paste.

## Multiple screenshots & overlapping rows

A neighbourhood often doesn't fit in one screenshot. You can add several:

- **Load** (or paste) each screenshot in turn — they **stack** in the text box
  rather than replacing what's there. Load shot 1, then shot 2, then press Parse
  once.
- When two screenshots **overlap** (the same member shows up on both because the
  list scrolled), the importer **merges those duplicates automatically** before
  the review table — each member appears exactly once. The fuller reading wins
  (so a row clipped at a screenshot edge can't override the complete one), and a
  note tells you how many duplicates were merged.
- Even if a duplicate slipped through, there's no double-counting: member
  matching is **one-to-one** (a member binds to a single row), and the final
  snapshot is keyed by member, so a member can only appear once.
- The one caveat the note reminds you of: if **two different members genuinely
  share a display name**, they'd be merged — check the review table in that
  (rare) case and fix it by hand.

## How matching works

- Names are normalized (emoji/punctuation stripped, case-folded) and compared to
  your members with fuzzy matching; the best match above a confidence threshold
  is pre-selected, and each row is bound to at most one member.
- Unmatched rows default to "skip" — assign them manually, or skip foreign farms.

## Why the denominators differ (8/8 vs 9/9)

That's expected: the second number is each member's **league task allotment**
(Rookie 5 … Champion 9, +1 if they bought an extra task). See
[`hayday_derby_reference.md`](hayday_derby_reference.md). The parser keeps each
member's own `tasks_max` rather than assuming one value for the whole clan.

## What's tested

The parsing and member-matching logic (`src/derby_ocr.py`) is pure and covered by
`tests/test_derby_ocr.py` — including the exact sample from a real task-log
screenshot, OCR digit-noise repair (e.g. `l244 → 1244`, `6O9 → 609`), one-to-one
member binding, and snapshot assembly. The OCR image step (`src/ocr_engine.py`)
is an optional, lazily-imported wrapper around Tesseract.
