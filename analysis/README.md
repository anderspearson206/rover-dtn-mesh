# analysis

Offline work on recorded BS sessions (`bs_reports/session_*`).

| File | What it does |
|---|---|
| `fix_track.py` | Corrects odometry drift in a session's `coverage.csv` when runs start and end at the BS. Turn model (closes each out-and-back leg) or `--model pf` (map-matching to the drivable paths). Writes `coverage_fixed[_pf].csv` + plots |
| `trace_path.py` | GUI: trace the route you actually drove on the map and slide the logged samples along it, with pins for known positions. For when `fix_track.py` can't recover the track |
| `map_match.py` | Particle-filter map matching (`LiveMatcher`) used by `fix_track.py --model pf` |
| `view_pgm.py` | Shows a PGM occupancy map (e.g. `mymapfountain2_crop_retouched.pgm`, a GIMP-retouched fountain map), prints its grey-value counts and writes a PNG next to it |
| [`data_analysis/`](data_analysis/README.md) | Archived real experiment runs (raw session copies + terrain) and their figures and summaries; `run_all.py` regenerates everything |
| [`waypoint_selection/`](waypoint_selection/README.md) | Where to put the BS, rover goals and relay spots around the fountain so naive planning loses the link and radio-map-aware planning keeps it; `mark_drive_area.py` marks where the rovers may drive |

```bash
python analysis/fix_track.py bs_reports/<session> --site fountain                # turn model
python analysis/fix_track.py bs_reports/<session> --site fountain --rotate -30   # turn the result about the BS
python analysis/fix_track.py bs_reports/<session> --site fountain --model pf --follow 3:2
python analysis/trace_path.py bs_reports/<session> --site fountain
python analysis/view_pgm.py analysis/mymapfountain2_crop_retouched.pgm
..\.venv\Scripts\python analysis\data_analysis\run_all.py
```

`fix_track.py`: `--leg-heading LEG:DEG` sets the direction a leg set off in, and `fix_track_candidates.png` shows the likely ones. If the session's BS is not at the surveyed cell, missing radio maps are generated with `radiomap/rm_generate.py`.
