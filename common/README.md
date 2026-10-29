# common

Modules shared by the base station, the rovers and the offline tools. Each script that uses them adds this folder to `sys.path`. On the cars they are copied flat next to `radio_daemon.py` / `rover_nav.py` (`rover/deploy.sh`).

| File | What it does | Used by |
|---|---|---|
| `site_map.py` | Terrain sites (`<site>_meta.json`, terrain, drivable mask, radio maps, satellite image) and the rover odometry → map alignment. `find_terrain_dir()` tries `terrain/`, `../terrain/` and `../../terrain/` from here | almost everything |
| `route_plan.py` | A* over the drivable mask (keeps to the middle of paths), smoothing and Douglas-Peucker simplification | dashboard, relay brain |
| `relay_brain.py` | Where the relay rover should be: maximises the weaker of BS ↔ relay and relay ↔ explorer, using link tables, measured RSSI or log-distance | rover daemon, dashboard, `radiomap/relay_replay.py` |
| `odom_fusion.py` | Dead reckoning: distance from the wheels, heading from the T265 | `rover_nav.py`, `radio_daemon.py` |

Compatibility on the cars:

- **`odom_fusion.py`** must stay Python 2-compatible, because `rover_nav.py` runs under ROS Melodic: no f-strings, no annotations.
- **`route_plan.py`, `relay_brain.py` and `site_map.py`** must work with numpy 1.13 (the Jetsons' `python3-numpy`): give `np.pad` an explicit `mode`, and don't use `nan_to_num(nan=)`.

```bash
python common/route_plan.py --site fountain 34,12 -30,0 34,12                  # plan and plot
python common/relay_brain.py --site fountain --bs=44.5,-62.5 --explorer=-20,30  # one relay decision
```
