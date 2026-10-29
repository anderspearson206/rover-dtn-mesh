# legacy

Superseded tools, kept for reference. They don't use `common/` and still run from here.

| File | Superseded by | Notes |
|---|---|---|
| `mesh_visualizer.py` | `basestation/bs_dashboard.py` | matplotlib live view of the BS serial port. Redraws everything every frame and is slow with the control panel |
| `jetson_daemon.py` | `rover/radio_daemon.py` | Daemon for the old model where the rover ESP32 held the DTN logic (`PULL_REQ`/`BUNDLE_DATA`/`BUNDLE_PUSH`). Current rover firmware is a relay, so it no longer works against it |
| `jetson_daemon_2.7.py` | — | Python 2.7 port of `jetson_daemon.py` |

## mesh_visualizer.py

```bash
python legacy/mesh_visualizer.py --port COM5     # options: --baud, --map-half <m>, --timeline <s>, --report-dir <dir>
```

Panels: mesh graph (RSSI-labelled edges; transfers red = direct, orange dashed = ferried), comms status and bundle events per rover, a radio map from `@LOCATION:`, and a 180 s comms timeline. It has a fleet-control strip (Start / Apply live / Standby) with the same control messages as the dashboard. Keys: `m` marker, `s` save summary, `r` new session, `h` help.

It writes the same core session files as `bs_core.py` to `bs_reports/session_<time>/` (`serial.log`, `deliveries.csv`, `contacts.csv`, `rover_status_<id>.csv`, `markers.csv`, `coverage.csv`, `dtn_summary_<time>.txt`, `node_<id>_boot<n>.txt`). On a serial reconnect or BS reboot, the session is summarised and a new one is started.
