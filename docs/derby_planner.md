# Derby Planner & Predictor

The Derby Planner turns your recorded derby history into advice for the **next**
derby. It lives under **Other tools → 🏇 Derby Planner** and reads the same
after-derby snapshots the rest of the app already collects — no new data entry
is required to start using it.

## What it answers

- **Who can I count on?** Each member gets a *risk tier* based on how often they
  actually join derbies and how steady their scores are.
- **How many points will this lineup likely score?** Pick members and get a
  participation-adjusted projection plus an optimistic ceiling.
- **Who should I pick to hit a target?** Auto-pick builds the most dependable
  lineup to reach a points goal.

## The numbers, explained

All figures come from **after-derby snapshots** (the snapshot type that records
`derby_participated`, `tasks_done / tasks_max`, and `derby_points`). Quick and
donation snapshots are ignored here.

For each member, `member_derby_profile()` computes:

| Field | Meaning |
| ----- | ------- |
| `participation_rate` | participated derbies ÷ derbies on record |
| `avg_points` | mean points across derbies they **joined** (skips don't drag it down) |
| `avg_tasks`, `avg_completion` | mean tasks done, mean `tasks_done / tasks_max` |
| `consistency` | `1 − (stddev ÷ mean)` of their points, clamped to `0…1` |
| `trend` | recent-half average minus older-half average (positive = improving) |
| **`expected_points`** | `avg_points × participation_rate` — the headline prediction |

`expected_points` is the key idea: a player who scores 1000 but shows up half
the time is worth ~500 to your planning, the same as a steady 500-point player
who always joins.

### Risk tiers

| Tier | Rule | Read it as |
| ---- | ---- | ---------- |
| **Reliable** | participation ≥ 80% **and** consistency ≥ 70% | Build around them |
| **Inconsistent** | participates, but erratic scores or 50–80% turnout | Usable, watch them |
| **Risky** | participation < 50% | May not show up |
| **Unknown** | fewer than 2 derbies on record | Not enough data yet |

Thresholds are constants at the top of `src/derby_planner.py`
(`RELIABLE_MIN_PARTICIPATION`, `RELIABLE_MIN_CONSISTENCY`,
`RISKY_MAX_PARTICIPATION`) so they're easy to tune in one place.

## Predicting a lineup

`predict_lineup(data, member_ids)` returns:

- `predicted_points` — sum of each pick's `expected_points` (the realistic call)
- `predicted_points_optimistic` — sum of `avg_points` (if everyone shows up)
- `predicted_completion` — mean of the picks' average task-completion %
- `risk_members` — selected members who are *risky* or *unknown*

## Auto-pick

`recommend_lineup(data, target_points=…, max_slots=30)` greedily adds members in
descending `expected_points` order until the target is projected to be met (or
slots run out). Members with no derby history are never auto-picked — you can't
predict a contribution for someone with no record — but you can still add them
manually in the UI.

## Saved plans

Plans persist on the neighborhood file under a `derby_plans` key:

```json
{
  "plan_id": "<uuid>",
  "name": "Derby 2026-06-19",
  "created_at": "<iso datetime>",
  "derby_date": "2026-06-21",
  "target_points": 18000,
  "member_ids": ["#A", "#C", "..."],
  "notes": ""
}
```

Older neighborhood files that predate this feature simply have no `derby_plans`
key; it's added transparently on first save (see `NeighborhoodManager.load`).

## Design notes

- **Pure logic, fully tested.** `src/derby_planner.py` has zero GUI/disk
  dependencies; `tests/test_derby_planner.py` covers profiles, predictions,
  recommendations and plan CRUD. The Tkinter screen
  (`src/ui_derby_planner.py`) is a thin view over it.
- **Nothing is cached.** Like every other statistic in the app, profiles are
  recomputed from raw snapshots on each render, so editing history updates the
  plan immediately.

## Running the tests

```bash
pip install pytest
pytest -q
```
