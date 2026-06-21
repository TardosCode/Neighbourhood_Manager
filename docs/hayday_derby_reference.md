# Hay Day Derby — mechanics reference

Notes the app's derby features are built on, so validation bounds and labels
match the real game. Cross-checked against the Hay Day Fandom wiki and
corroborating guides (2025–2026). Items marked *uncertain* are left
configurable rather than hard-coded.

## Tasks and the "X / Y" in the Task Log

- The **Neighborhood Derby Task Log** lists each member as `Farm name — X/Y — Points`.
- **X = tasks completed**, **Y = tasks available** to that member.
- **Y is per-member and set by their personal derby _league_**, not by the
  neighborhood — so different rows legitimately show different denominators:

  | League | Tasks (Y) |
  | ------ | --------- |
  | Rookie | 5 |
  | Novice | 6 |
  | Professional | 7 |
  | Expert | 8 |
  | Champion | 9 |

- Each member may **buy one extra task** (+1), so a standard derby tops out at
  **Y = 10**. Power Derby variants go higher (≈15). *(Extra-task diamond cost
  is reported as 2 or 10 depending on source — uncertain.)*
- **Therefore `8/8` next to `9/9` is valid data, not an error.** The app stores
  `tasks_max` per member per snapshot and never assumes a single clan-wide value.

## Points

- Standard tasks award **50–320 points**; themed/special derby tasks up to **~400**.
- The **Points** column is that member's **cumulative** derby points (sum across
  their completed tasks), not a per-task value.
- Realistic single-member ceiling: ~10 tasks × ~320 ≈ **3,200** (standard);
  up to ~**4,000** themed. The app warns above ~6,000 (Power Derby head-room)
  and flags totals greater than `tasks_done × 400`.

## Bingo

- In Bingo Derbies each member gets a card; lines can be horizontal, vertical
  or diagonal. Since 2018 a member can score up to **3 bingo lines**.
- The log's "Bingo rewards — Bingo: N, Points: M" means N lines completed and M
  bonus points. In **reward-bingo** derbies the bonus points are 0 (lines grant
  reward columns instead), which is why the sample screenshot shows `Bingo 1 / Points 0`.

## Structure

- Roughly **weekly cadence**, ~**4 active days** *(sources conflict; treat as
  configurable)*.
- **5 leagues** (Rookie → Champion) gate task counts and matchmaking; members of
  one neighborhood can be in different leagues.
- **Horseshoes** are neighborhood-wide point checkpoints granting reward picks;
  they do **not** change task counts.
- **"Fate" (keep / warn / kick)** is **not** an in-game feature — kicking and
  opting-out are real leader actions, but the keep/warn/kick framework is a
  community management convention (and a convenience this app provides).

## Validation bounds used by the app

These live in `src/derby_ocr.py` and only raise *warnings* during screenshot
review (OCR misreads are flagged, never silently dropped):

| Bound | Value |
| ----- | ----- |
| Tasks available per member (Y) | 5–10 standard (warn above 15) |
| Tasks completed (X) | `X ≤ Y` |
| Points per task | ≤ ~400 |
| Points per member (whole derby) | warn above ~6,000, or above `X × 400` |
| Bingos per member | ≤ 3 |

## Sources

- Hay Day Wiki (Fandom): [Derby](https://hayday.fandom.com/wiki/Derby),
  [Derby Types](https://hayday.fandom.com/wiki/Derby_Types),
  [Derby Tasks](https://hayday.fandom.com/wiki/Derby_Tasks),
  [Power Derby Tasks](https://hayday.fandom.com/wiki/Power_Derby_Tasks),
  [Neighborhood Management](https://hayday.fandom.com/wiki/Neighborhood_Management)
- [Hay Day Official — Power Derby league task counts (Facebook)](https://www.facebook.com/HayDayOfficial/photos/a.315469888537585/2034817493269474/)
- [Sportskeeda — Derby tips](https://www.sportskeeda.com/esports/5-tips-completing-hayday-s-derby-event)
- [How Bingo Derby works — BingoCardTemplate.org](http://www.bingocardtemplate.org/in-depth/how-does-bingo-derby-work-on-hay-day/)
