# basestation

Runs on the BS laptop, connected to the BS ESP32's serial port.

| File | What it does |
|---|---|
| `bs_core.py` | Serial reading, parsing, logging, contact tracking, reports and fleet-control sending, without a GUI. Run on its own for headless logging |
| `bs_dashboard.py` | PySide6 + pyqtgraph GUI on top of `bs_core`; it only reads snapshots, so a slow or closed window never affects logging or control |
| `plan_runner.py` | Runs a prepared experiment plan (`analysis/waypoint_selection/plans/*.json`) step by step through `bs_core`'s route sending; used by the dashboard's "Experiment plan" box |
| `fetch_sat.py` | Downloads a north-up aerial photo (USGS NAIP, ~0.6 m/px) for a site's map background |

Uses `common/` (site maps, route planning, relay brain) and `radiomap/rm_generate.py` (BS moves). Python environment: `..\.venv` one level above the repo (PySide6, pyqtgraph, pyserial, numpy).

```bash
..\.venv\Scripts\python basestation/bs_dashboard.py --port COM5 --site fountain [--terrain-dir ../terrain] [--report-dir bs_reports]
..\.venv\Scripts\python basestation/bs_core.py --port COM5      # headless; Ctrl-C writes the summary
..\.venv\Scripts\python basestation/fetch_sat.py fountain range  # writes ../terrain/<site>_sat.png
```

Run from the repo root so sessions go to `bs_reports/`.

## Dashboard

- **Fleet control**: experiment name, data interval, bandwidth limit/burst/order, periodic radio on/off/phase, payload size, location interval. **Start experiment** starts a run fleet-wide 3 s later in a new session folder, **Apply live** changes the running one, and **Standby** stops it. Rovers out of range pick up the latest state when they hear the BS again.
- **Rovers table**: link UP/DOWN and its duration, RSSI, state, experiment, control version (green = applied), radio window, queue, gen/tx/retx/ack, recent and total data, latency, clock offset, status age.
- **Events**, **Timeline** (link lanes, throughput, latency, markers), **Topology** (Comms tab).
- **Map tab**: site map, rover tracks, alignment, route driving, relay role (below).
- **Toolbar**: Marker (Ctrl+M), Save summary (Ctrl+S), New session.
- **Warnings**: a red banner for an old BS firmware, `CONTROL NOT RECEIVED` when a rover hasn't taken a new control version within 10 s, and `POSE RESET` when a rover's `rover_nav.py` restarted after it was placed.

Session folder `bs_reports/session_<time>[_<experiment>]/`: `serial.log`, `deliveries.csv`, `contacts.csv`, `rover_status_<id>.csv`, `controls.csv`, `markers.csv`, `coverage.csv`, `alignments.csv`, `routes.csv`, `bs_position.json`, `dtn_summary_<time>.txt`, `node_<id>_boot<n>.txt`. See the docstring in `bs_core.py`.

## Map and rover alignment

With `--site <name>` the Map tab loads the site from the terrain folder (`--terrain-dir`, otherwise `terrain/` or `../terrain/` near the code; see `common/site_map.py`). Map coordinates: x = east, y = north, metres from the grid centre.

- **Layers**: shaded elevation or `<site>_sat.png`, the drivable mask, a predicted radio map, the BS.
- **Rovers**: track coloured by RSSI to the BS, current position and heading. Grey means no location for 5 s.
- **Alignment**: a rover's pose starts at (0, 0) whenever its ROS stack starts, so each rover gets its own offset and rotation onto the map. Choose the rover, press **Place on map…**, press on its spot and drag the way it faces. The arrows nudge the position and ↺ ↻ rotate it. Alignments are saved in `bs_reports/alignment_<site>.json` and logged to `alignments.csv`. `coverage.csv` keeps the raw odometry, so a run can be re-aligned afterwards.
- **Pose source**: "Camera-only pose" switches a rover from the fused pose (wheel distance + T265 heading) to the T265 alone.

## Route driving and the relay role

- **Drive route**: select the rover, press "Add waypoints…" and click points in driving order. `route_plan.Planner` runs A* over the drivable mask from the rover's current pose. "Send route" converts the route to the rover's odometry frame and sends it, and `rover/rover_nav.py` follows it. RB must be held unless "Drive without RB" is ticked. In that case the radio deadman (default 8 s) stops a rover that has lost its controller once it no longer hears the BS. Every route and stop is logged to `routes.csv`.
- **Experiment plan**: runs a prepared plan from `analysis/waypoint_selection/plans/` (written by `example.py` and `multi_agent_detour.py`; "Reload" picks up new files). A plan has variants, e.g. `naive` and `radio_map`, and roles (`rover1`, `rover2`); choose the variant and a rover for each role. "Show the plan's routes" draws them (dashed, one colour per role; squares = where a rover waits, triangle = start). "Drive to start" sends every assigned rover to the start point; "Run" starts all roles at once: each step is either a drive (A* from the rover to the step's first point, then the plan's own points, sent like "Send route"; done when the rover reports `done`) or a wait (start delay, relay stop, time at a waypoint). A rover that reports `stopped_off_route` / `stopped_bs` pauses its part of the plan. "Abort" stops the plan and its rovers' routes. Start, every step and the end are logged as markers (`#MARKER:plan-...` in `serial.log`, `markers.csv`), so a run can be cut into its steps afterwards. The RB / "Drive without RB" rules are the same as for a hand-sent route.
- **Relay**: pick a relay and an explorer rover and press Start relay. The relay rover keeps driving to the spot that maximises its weaker link (BS ↔ relay, relay ↔ explorer). Settings: speed, "ferry after", comfort, gain, look-ahead, link model, and "Measured RSSI". The targets are drawn as diamonds, and "why:" shows the reason for the last decision. See `common/relay_brain.py`.

## Moving the BS

The site's own radio maps are for the surveyed BS cell. **Move BS…** (Map tab) and a click puts the BS somewhere else. `bs_core` then runs `radiomap/rm_generate.py` in the background with the RadioLunaDiff models from [lunar-mesh-env](https://github.com/anderspearson206/lunar-mesh-env) (default `~/Documents/lunar-mesh-env` and its `.venv`; `--rm-env` to change). PMNet arrives after ~10 s and the full map after ~25 s on CPU. Maps are cached as `<site>_rm58_<model>@<col>_<row>.npy`. **Reset BS** goes back to the surveyed cell. The position is kept in `bs_reports/bs_position_<site>.json` and in each session as `bs_position.json`.
