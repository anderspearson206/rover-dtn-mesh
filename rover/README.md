# rover

Runs on the rovers' Jetsons (MuSHR cars: rover 1 = `robot@192.168.2.21`, rover 2 = `robot@192.168.2.22`; Ubuntu 18.04, ROS Melodic).

| File | What it does |
|---|---|
| `radio_daemon.py` | All DTN logic for the rover (the ESP32 is only a relay), location reports, remote ROS start/stop, route hand-off to `rover_nav.py`, relay-rover decisions. Python 3.6+ |
| `rover_nav.py` | ROS node (Python 2): publishes the fused pose on `/car/fused_odom` and follows routes with pure pursuit |
| `calib_distance.py` | Hand-run calibration of the wheel distance gain and steering centre |
| `deploy.sh` | Copies the files above + the shared `common/` modules to a car |
| [`car/`](car/README.md) | Fixed MuSHR controller launcher (a lost controller no longer starts the stack) |

## On the car

Everything sits flat in `~/catkin_ws/src/mushr/mushr_base/mushr_base/mushr_base/src/`: these files plus `odom_fusion.py`, `relay_brain.py`, `route_plan.py` and `site_map.py` from `common/`. The scripts look for `../common` only in the repo layout, so the flat copy works as it is.

```bash
rover/deploy.sh 21                 # copy to rover 1 (changed files backed up as *.bak_<date> first)
rover/deploy.sh 22 --restart       # rover 2, then restart radio_daemon.service (asks for sudo)
rover/deploy.sh 21 --dry-run       # only show what differs
```

`rover_nav.py` and `odom_fusion.py` are reloaded only when the ROS stack restarts (Stop/Start ROS on the dashboard). Terrain and link tables for the relay role go in `~/terrain` on the car.

### radio_daemon.service

`/etc/systemd/system/radio_daemon.service` (`Restart=always`, `KillMode=process`) sources ROS + catkin and runs:

```bash
python3 -u radio_daemon.py --serial /dev/serial/by-id/usb-1a86_USB_Serial-if00-port0 --interval 1 \
    --ros-location-topic /car/fused_odom --ros-control --site fountain --terrain-dir /home/robot/terrain
```

Logs: `journalctl -u radio_daemon -f`. To change flags, edit `ExecStart`, then `sudo systemctl daemon-reload && sudo systemctl restart radio_daemon`. Don't run a second copy by hand, because both would fight over the serial port.

## radio_daemon.py

```bash
python3 radio_daemon.py --serial /dev/ttyUSB0                          # bench / by hand
python3 radio_daemon.py --serial /dev/ttyUSB0 --interval 0.5 --bw-limit 1 --run-tag bw1
python3 radio_daemon.py --serial /dev/ttyUSB0 --comms-on 30 --comms-off 60
```

| Flag | Default | Notes |
|---|---|---|
| `--serial` / `--baud` | `/dev/ttyUSB0` / 115200 | ESP32 port |
| `--node-id` | auto | Normally read from the ESP32 (`STATUS_RESP`) |
| `--mode` | `standby` | `active` runs an experiment with the CLI settings right away |
| `--interval` | 1 | Seconds between data bundles (0 = none) |
| `--payload-bytes` | 0 | Pad data payloads to N bytes (max 1024) |
| `--routing` / `--spray-count` | `epidemic` | or `spray-wait` |
| `--retransmit-s` | 5 | Re-send a bundle the BS hasn't acked after this long |
| `--bw-limit` / `--bw-burst` / `--bw-order` / `--bw-count-telemetry` | off | Data bundles/s budget (token bucket) |
| `--comms-on` / `--comms-off` / `--comms-phase` | 0 | Periodic radio windows on BS time |
| `--lat` / `--lon` / `--alt` | — | Fixed location instead of a ROS topic |
| `--loc-interval` | 1 | Seconds between location reports |
| `--ros-location-topic` | — | Pose source; `/car/fused_odom` with `rover_nav.py` |
| `--ros-wheel-topic` | — | Daemon's own fusion (T265 topic + wheel odometry); not with `/car/fused_odom` |
| `--ros-control` | off | Let the dashboard start/stop the ROS stack (`teleop.launch use_t265:=true`, never the planner) |
| `--nav-dir` | `/tmp/rover_nav` | Files shared with `rover_nav.py` |
| `--site` / `--terrain-dir` / `--linktab` | — | Enable the relay role (needs numpy) |
| `--log-dir` / `--run-tag` / `--no-log` | `rover_logs` | Event log |
| `--state-interval` / `--status-interval` | 1 / 5 | State snapshots in the log / `@ROVER_STATUS` to the BS |

The CLI comms flags are only defaults; the BS's fleet control overrides them. Run `--help` for the details.

- **Standby**: no data bundles, no comms limits, radio on. Beacons, ACK maps, location and status keep flowing.
- **Experiments**: on a BS start the rover drops queued data from the previous run, resets counters, applies the settings and mirrors its log to `rover_logs/exp_<name>_<node>_<time>.jsonl`. At the end it writes `..._summary.json`.
- **Comms modes**: the bandwidth limit applies only to data bundles. In periodic mode the radio is fully off in the off-window, and all peers age out, so the next window behaves like a real outage.
- **BS time**: the Jetsons have no NTP. Rovers take the BS clock from control messages (`FleetClock`) and use it for experiment starts and radio windows.
- **Logging**: `rover_logs/rover_<time>[_<tag>].jsonl`, one JSON event per line (`tx`, `rx_*`, `bundle_*`, `peer_up/down`, `radio_on/off`, `error`, plus a `state` snapshot every second). A summary is written on shutdown. Load the log with `pandas.read_json(path, lines=True)`.

## rover_nav.py

Started by `teleop.launch` (`<node pkg="mushr_base" type="rover_nav.py" name="rover_nav" output="screen" />`; needs `chmod +x`, which `deploy.sh` does). It publishes the fused pose at 50 Hz and follows routes from `radio_daemon.py` (via `/tmp/rover_nav/route.json`) on the navigation mux input. It drives only while RB is held, unless the dashboard sets "Drive without RB" (then it uses the `Autonomy` mux input and the radio deadman). It stops at the end of the route, more than 2.5 m off the route, or on Stop from the BS. Status goes back as `nav=`, `ni=`/`np=`, `xte=` in `@ROVER_STATUS`.

## calib_distance.py

Drive a taped straight line. The script compares `/car/vesc/odom` with the true distance and suggests `speed_to_erpm_gain`. On runs without steering input it uses the T265 heading to suggest `steering_angle_to_servo_offset`. It writes nothing.

```bash
nohup python -u calib_distance.py --true 6.6 --joy > ~/calib.log 2>&1 &   # then use the controller
```
