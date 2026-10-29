# analysis

Offline work on recorded BS sessions (`bs_reports/session_*`).

| File | What it does |
|---|---|
| `fix_track.py` | Corrects odometry drift in a session's `coverage.csv` when runs start and end at the BS. Turn model (closes each out-and-back leg) or `--model pf` (map-matching to the drivable paths). Writes `coverage_fixed[_pf].csv` + plots |
| `trace_path.py` | GUI: trace the route you actually drove on the map and slide the logged samples along it, with pins for known positions. For when `fix_track.py` can't recover the track |
| `map_match.py` | Particle-filter map matching (`LiveMatcher`) used by `fix_track.py --model pf` |
| [`data_analysis/`](data_analysis/README.md) | Archived real experiment runs (raw session copies + terrain) and their figures and summaries; `run_all.py` regenerates everything |

```bash
python analysis/fix_track.py bs_reports/<session> --site fountain                # turn model
python analysis/fix_track.py bs_reports/<session> --site fountain --rotate -30   # turn the result about the BS
python analysis/fix_track.py bs_reports/<session> --site fountain --model pf --follow 3:2
python analysis/trace_path.py bs_reports/<session> --site fountain
..\.venv\Scripts\python analysis\data_analysis\run_all.py
```

`fix_track.py`: `--leg-heading LEG:DEG` sets the direction a leg set off in, and `fix_track_candidates.png` shows the likely ones. If the session's BS is not at the surveyed cell, missing radio maps are generated with `radiomap/rm_generate.py`.
