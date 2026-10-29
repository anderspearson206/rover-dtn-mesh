# rover/car

Fixed copies of the MuSHR controller launcher on both cars (`mushr_launcher.service`). It waits for the PlayStation controller, starts the stack on **OPTIONS** (`car_startup.launch`, which includes the autonomous planner) and stops it on **SHARE**.

| File | What it does |
|---|---|
| `controller_launcher.sh` | OPTIONS→SHARE loop; starts the stack only when `wait_button.py` exits 0, and stops a running stack if the controller drops |
| `wait_button.py` | Blocks until a button is pressed. Exit codes: 0 pressed, 1 usage/permission error, 2 controller missing or lost |

Why: the original `wait_button.py` crashed when `/dev/input/js0` vanished, and the launcher treated that as OPTIONS. A car driving out of Bluetooth range then started the goals mission with nothing blocking it (rover 1, twice on 2026-10-22).

These are installed by hand, because they live in the MuSHR package's `scripts/` folder, not next to the radio files. `systemctl cat mushr_launcher.service` shows the path. Keep the old copies as `*.bak_<date>`, then run `sudo systemctl restart mushr_launcher.service`. Check with `journalctl -u mushr_launcher.service -f`.
