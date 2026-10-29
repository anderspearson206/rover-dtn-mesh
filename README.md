# ESP32-C5 DTN Rover Mesh

A Delay-Tolerant Networking (DTN) mesh for a fleet of ground rovers. Each rover (a MuSHR car with a Jetson) carries an **ESP32-C5** as its wireless modem. The nodes talk over **ESP-NOW** on 5 GHz channel 36, with epidemic store-and-forward routing of a BPv7-inspired bundle format.

**Deployment**: rovers + 1 fixed base station (BS); currently two rovers, built to scale to N. Most data flows rover → BS. Links come and go as the rovers drive, so bundles are carried (ferried) across disconnections by other rovers.

**Split of work**:

- **Rover**: the ESP32 is a _pure broadcast relay_. It broadcasts every frame the Jetson hands it and passes every received frame back with source MAC + RSSI. All DTN logic (beacons, bundle store, routing, antipackets/dedup, ACK maps) runs in `rover/radio_daemon.py` on the Jetson, alongside route following (`rover_nav.py`) and the relay-rover brain.
- **Base station**: the ESP32 runs the full DTN stack in firmware and prints `@`-lines on its serial port. The BS laptop runs `basestation/bs_dashboard.py`, which logs everything and controls the fleet (experiments, ROS start/stop, routes, relay role) over the mesh.

One firmware binary serves both: it picks its role at boot from its node ID.

## Repository layout

| Folder | What's in it |
|---|---|
| [`firmware/`](firmware/README.md) | ESP-IDF project for the ESP32-C5 (BS stack + rover relay), host UART protocol, BS serial output |
| [`basestation/`](basestation/README.md) | BS laptop: `bs_core.py` (headless logging + fleet control), `bs_dashboard.py` (GUI), `fetch_sat.py` |
| [`rover/`](rover/README.md) | Runs on the cars: `radio_daemon.py`, `rover_nav.py`, `calib_distance.py`, `deploy.sh`; `car/` has the MuSHR controller-launcher fix |
| [`common/`](common/README.md) | Modules shared by the BS, the rovers and the offline tools: `site_map`, `route_plan`, `relay_brain`, `odom_fusion` |
| [`radiomap/`](radiomap/README.md) | Predicted radio maps and relay link tables (RadioLunaDiff / Colab), and tools to check them |
| [`analysis/`](analysis/README.md) | Offline track repair (`fix_track.py`, `trace_path.py`, `map_match.py`) and the archived experiment analysis in `data_analysis/` |
| [`legacy/`](legacy/README.md) | Superseded tools: `mesh_visualizer.py`, `jetson_daemon.py` (+ its Python 2.7 port) |

Not in the repo:

- `../terrain/`: site maps, radio maps, link tables.
- `../.venv/`: the BS laptop's Python environment.
- `bs_reports/`: BS session logs.
- `rover_logs/`: rover event logs.

Run the Python tools from the repo root (e.g. `python basestation/bs_dashboard.py ...`), so `bs_reports/` lands in the usual place. Scripts find the shared modules in `common/` by themselves.

## Quick start

### 1. Flash the ESP32-C5s

```bash
cd firmware
idf.py build                # ESP-IDF v6.0, IDF_PATH set
idf.py -p COM13 flash       # base station
idf.py -p COM14 flash       # each rover (same binary)
```

The BS prints `I am the Base Station` at boot and rovers print `I am a Rover`. See [firmware/README.md](firmware/README.md).

### 2. Rovers

On the cars, `radio_daemon.py` runs at boot as `radio_daemon.service`. To update the files on a car:

```bash
rover/deploy.sh 21 --restart     # rover 1 (robot@192.168.2.21); 22 = rover 2
```

To run it by hand (bench, or a Jetson without the service):

```bash
python3 rover/radio_daemon.py --serial /dev/ttyUSB0     # or COM14 on Windows
```

See [rover/README.md](rover/README.md).

### 3. Base station dashboard

```bash
..\.venv\Scripts\python basestation/bs_dashboard.py --port COM5 --site fountain
```

### Running an experiment

1. Rovers boot into **standby**: they send beacons, location and status, but no data bundles.
2. In the dashboard, enter an experiment name and settings under **Fleet control** and press **Start experiment**. Every rover starts 3 s later, and a new session folder named after the experiment is opened in `bs_reports/`.
3. Use **Marker** (Ctrl+M) for waypoints and events, and **Apply live** to change settings mid-run.
4. Press **Standby** to end the run. The rovers write their experiment summaries and the BS writes the session summary.
5. Afterwards, collect `rover_logs/exp_<name>_*` from each Jetson to go with the BS session folder.

## Status

| Feature | State |
|---|---|
| ESP-NOW transport, epidemic store-and-forward, antipackets | Done |
| DTN ferrying | Verified on the bench (2026-05-17); re-verification on the cars with the relay/daemon split still to do |
| Clock sync / latency correction; fleet runs on BS time | Done |
| Rover ESP32 = relay, DTN logic in `radio_daemon.py` | Done, running on both cars |
| Fleet control from the BS (experiments, ROS start/stop, pose source) | Done |
| Fused pose (wheel distance + T265 heading), route driving from the dashboard | Done, tested indoors and at the fountain site |
| Relay rover role (`relay_brain.py`) | Built; first outdoor runs 2026-10-22/23 |
| Downlink / delivery ACKs to rovers | Not yet done |

## Why ESP-NOW (not ESP-WIFI-MESH)

ESP-WIFI-MESH needs a router/AP, and its root election and topology management assume a persistent uplink. In a DTN network the connectivity is intentionally intermittent, so those assumptions don't hold. ESP-NOW is connectionless broadcast/unicast with no infrastructure, which fits store-and-forward.
