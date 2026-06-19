# Neighbourhood Manager

A desktop app for managing your Hay Day neighborhood (clan).
Track members, derby performance, donations, levels, and an automatic
activity-score system that helps you spot your most engaged members
at a glance.

Built with Python and Tkinter.

## Features

### Member management
- Track every member's level, role, join date, and notes
- Four roles: **Member / Elder / Co-Leader / Leader** with color-coded chips and row tints
- Mark members as in-clan or former — former members stay in your database for history
- Search by name or tag, filter by activity status
- Persistent UI preferences per clan (e.g. show/hide former members)

### Snapshot system
Three types of snapshots capture different aspects of your neighborhood
over time:

- **After-Derby** — full derby data: tasks completed, points scored, fate decision (stay/warning/kick)
- **Quick** — just current levels, useful between derbies
- **Donations** — weekly Crops/Foods/Tools donated and requested per member

A clean two-step workflow lets you first pick which members the snapshot
covers, then fill in their data — the second step only shows the members
you selected.

### Activity score system
Members earn activity points based on five metrics:

- Derby task completion %
- Derby participation rate
- Levels gained in the last 30 days
- Donations in the last 4 weeks
- Manual bonuses you award (with a required comment)

For each metric, in-clan members are ranked and points awarded:

| Rank   | Points |
| ------ | ------ |
| 1      | 5      |
| 2 - 6  | 3      |
| 7 - 15 | 2      |
| 16+    | 1      |
| no performance | 0 |

The Activity tab shows a leaderboard with a per-category breakdown for
each member. Click any row to see exactly how someone earned their score.

### Statistics
The Statistics tab gives you the clan-wide picture:

- Activity status distribution (inactive / below target / on track / new)
- Top members by activity score, donations, requests, derby task completion %, and total derby points
- Average level trend over time
- Donations trend chart (clan-wide weekly throughput)
- Members flagged for warning or kick

### Derby Planner & Predictor
Plan your next derby from your own recorded history. The planner builds a
**dependability profile** for every member — participation rate, average and
*expected* points (average discounted by how often they actually show up),
consistency, and a trend — then sorts the roster by who contributes most.

- Tick members in or out and watch the **predicted points** update live, with
  an optimistic ceiling and expected task-completion %.
- Each member gets a **risk tier**: Reliable / Inconsistent / Risky / Unknown.
- Set a points target and hit **Auto-pick best lineup** to fill the most
  dependable roster that reaches it.
- **Save lineups as plans** — they persist with the clan and can be reloaded
  later.

See [`docs/derby_planner.md`](docs/derby_planner.md) for the full method.

### Other tools
The app also includes a small **Expansion Helper** for tracking silo / barn
upgrades, and the **Derby Planner** described above. Both live under
**Other tools** in the main menu.

More tools are coming soon.

## Install & run

You need **Python 3.10 or newer** (3.11 recommended).

```bash
# clone the repo
git clone https://github.com/<your-username>/neighbourhood-manager.git
cd neighbourhood-manager

# (optional but recommended) make a virtual environment
python -m venv .venv
# on Windows:
.venv\Scripts\activate
# on macOS/Linux:
source .venv/bin/activate

# install dependencies
pip install -r requirements.txt

# run the app
python src/main.py
```

### Dependencies

- [Pillow](https://pypi.org/project/Pillow/) — image rendering
- [matplotlib](https://pypi.org/project/matplotlib/) — charts
- [pygame](https://pypi.org/project/pygame/) — background music & SFX

Tkinter is part of the Python standard library on most platforms. On
some Linux distributions you may need to install it separately:

```bash
# Debian/Ubuntu
sudo apt install python3-tk
```

## Build a Windows .exe

Run `build_exe.bat` from the project root on a Windows machine. It uses
PyInstaller to bundle the app into a single executable.

## Data storage

All your data is stored locally as JSON files inside the project folder:

- `profiles/` — your player profile(s) and preferences
- `neighborhoods/` — one JSON file per clan, with members, snapshots, manual bonuses, and UI prefs
- `settings/` — global app settings (audio, theme, video)

Nothing is ever uploaded anywhere. You can back up the project folder
to keep your history safe, or copy it to another machine.

## Customization

- **Theme editor**: App Settings → Video → pick any of 6 base colors. Hover variants and panel shades are derived automatically. Activity status colors (red/amber/green/grey) stay fixed for readability.
- **Background music**: drop `.mp3` files into `audio/music/` (or use the **📁 Open folder** button in App Settings → Audio).
- **Activity rules**: configure expected level-gain rates per level range in App Settings → Neighbourhood → Activity rules. Members with less than 7 days of data are considered "New player" unless they over-perform.

## Project structure

```
neighbourhood-manager/
├── assets/        # PNG icons (Hay Day style)
├── audio/
│   ├── music/     # drop .mp3 files here
│   └── sfx/click.mp3
├── profiles/      # per-profile data (gitignored)
├── neighborhoods/ # per-clan data (gitignored)
├── settings/      # global settings (gitignored)
├── screenshots/   # screenshots of the UI
├── src/           # Python source code
├── tests/         # pytest suite for the pure-logic layer
├── docs/          # design notes (e.g. Derby Planner)
├── build_exe.bat  # Windows .exe build script
├── requirements.txt
├── requirements-dev.txt
└── README.md
```

## Development & tests

The app's business logic lives in pure modules under `src/` (no GUI or disk
dependencies) and is covered by a `pytest` suite in `tests/`. The GUI layer
(Tkinter) is intentionally not exercised in tests, since CI runners are
headless.

```bash
pip install -r requirements-dev.txt
pytest -q
```

Tests run automatically on every push and pull request via GitHub Actions
(`.github/workflows/ci.yml`) across Python 3.10–3.12.

## License

MIT — feel free to use, fork, and modify.

## Disclaimer

This is a **fan-made tool** for personal use by Hay Day players who want
to manage their neighborhoods better. It is not affiliated with, endorsed
by, or sponsored by Supercell. "Hay Day" is a trademark of Supercell.
This app does not interact with the game in any way — you enter all data
manually based on what you see in-game.
