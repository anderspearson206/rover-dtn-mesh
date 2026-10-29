# firmware

ESP-IDF project for the ESP32-C5 nodes. A single binary runs on every node: the base station runs the full DTN stack, and rovers run a thin relay for the Jetson's `radio_daemon.py`.

## Build and flash

Requires **ESP-IDF v6.0** with `IDF_PATH` set. Run from this folder:

```bash
idf.py build
idf.py -p COM13 flash            # COM13 = BS on the bench
idf.py -p COM13 monitor
idf.py -p COM13 flash monitor
```

No `menuconfig` is needed: there is no router SSID or mesh config, and the channel and band are hardcoded. `sdkconfig.defaults*` are tracked. `sdkconfig` and `build/` are generated (git-ignored).

## Hardware

- **MCU**: ESP32-C5, 5 GHz only, channel 36 (no DFS)
- **Rover host**: Jetson over USB (`/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0` on the cars), i.e. UART0. UART1 on GPIO 6/7 is an alternative (see below).
- **BS peripherals**: 16×2 I2C LCD (PCF8574, addr `0x27`), pushbutton, status LED

| Pin | Function |
|---|---|
| GPIO 9 | Pushbutton (BS only) |
| GPIO 10 | Status LED (all nodes) |
| GPIO 7 | LCD SDA (BS) / UART1 RX from Jetson |
| GPIO 8 | LCD SCL (BS) |

### Node IDs

Node ID = `(mac[4] << 8) | mac[5]` of the STA MAC, printed at boot.

| Node | Bench port | Node ID | MAC suffix | Car |
|---|---|---|---|---|
| Base Station | COM13 | 23768 | `eb:5c:d8` | — |
| Rover B | — | 57936 | `e2:50` | rover 1, `192.168.2.21` |
| Rover C | — | 54272 | `d4:00` | rover 2, `192.168.2.22` |

> The BS is not auto-detected: a node is the BS when its ID equals `BASE_STATION_NODE_ID` in `main/mesh_main.c`. With different BS hardware, change that constant.

## Configuration

Constants at the top of `main/mesh_main.c`:

| Constant | Value | Notes |
|---|---|---|
| `BASE_STATION_NODE_ID` | 23768 | Match to your BS hardware |
| `ESPNOW_CHANNEL` | 36 | 5 GHz UNII-1, 5180 MHz, no DFS; all nodes must match |
| `PEER_TIMEOUT_MS` | 15000 | An unheard peer is marked inactive after this |
| `MAX_BUNDLES_IN_RAM` | 150 | BS bundle store slots |
| `BUNDLE_PAYLOAD_SIZE` | 1024 | Max payload bytes per bundle |
| `HOST_UART_PORT` | `UART_NUM_0` | USB; `UART_NUM_1` + GPIO 6/7 for a wired Jetson UART |
| `HOST_UART_BAUD` | 115200 | Must match the daemon's `--baud` |
| `HOST_MAX_PAYLOAD` | 1100 | Larger host frames are dropped (a relayed bundle is up to 6 + 1 + 1053 bytes) |
| `HOST_PULL_ENABLED` | 0 | Pulls off since 2026-10-23: the BS laptop never answers them, and the 500 ms wait dropped control frames |
| `HOST_PULL_INTERVAL_MS` | 1000 | Pull period when enabled (legacy `jetson_daemon.py` only) |

## Architecture

### Node roles

`app_main` reads the node ID and branches:

- **Base Station**: `rx_process_task`, `beacon_task`, `bundle_tx_task`, `host_uart_task`, `ui_update_task`.
- **Rover**: only `relay_rx_task` + `relay_host_task` (+ `ui_update_task`). `relay_rx_task` sends each received ESP-NOW frame to the Jetson as `WIFI_RX` `[src_mac:6][rssi:1][air bytes]`; `relay_host_task` broadcasts each `WIFI_TX` payload verbatim and answers `QUERY_STATUS` (node ID + channel). No bundle store, beacons or peer table. The DTN code still compiles but never runs on a rover.

### Base station stack

- **Bundle store**: flat array of `ram_bundle_t` slots (`dtn_bundle_t`: source, dest, prev_node, sequence number, creation time, lifetime, hop count/limit, payload; plus `is_empty`/`forwarded`). `data_mutex` protects the store and `peer_list[]`.
- **`beacon_task`**: broadcasts `beacon_pkt_t` (node_id + timestamp_ms) every 1 s, for peer discovery and clock offsets.
- **`rx_process_task`**: fed from a queue by the ESP-NOW receive callback, which must not call `esp_now_send`. Beacons refresh the peer and its clock offset and emit `@NET:`. Bundles are deduplicated by `(source, creation_time, seq)`, and `@METRIC:` + `@DTN_RX:` are printed. The BS frees the slot after printing.
- **`bundle_tx_task`**: every 1 s it expires timed-out peers (`esp_now_del_peer`) and sends un-forwarded bundles to active peers. It never holds the mutex during `esp_now_send`.
- **`host_uart_task`**: binary host protocol (below). `WIFI_TX` control frames from the BS laptop go **unicast** to each active peer (`host_wifi_tx`; acknowledged and retried by ESP-NOW), or broadcast if no peer is active. Send statistics go out as `@TXSTAT`.
- **Clock sync**: per-peer `clock_offset_ms = peer_timestamp − bs_now_ms` from beacons. Latency = `(now − creation_time) + offset`, clamped to 0.

## Host UART protocol

```
[SOF 0xAA][CMD][LEN_LO][LEN_HI][PAYLOAD × LEN][CRC16_LO][CRC16_HI]
```

CRC-16/CCITT over `[CMD, LEN_LO, LEN_HI, PAYLOAD...]`.

| CMD | Hex | Direction | Payload |
|---|---|---|---|
| `TX_BUNDLE` | `0x01` | host → ESP32 | raw `dtn_bundle_t` |
| `QUERY_STATUS` | `0x02` | host → ESP32 | none |
| `QUERY_PEERS` | `0x03` | host → ESP32 | none |
| `PULL_REQ` | `0x10` | ESP32 → host | none |
| `BUNDLE_DATA` | `0x11` | host → ESP32 | raw `dtn_bundle_t` |
| `NO_BUNDLES` | `0x12` | host → ESP32 | none |
| `ANTIPKT_NOTIFY` | `0x13` | ESP32 → host | `antipkt_id_t` (10 bytes) |
| `BUNDLE_PUSH` | `0x14` | ESP32 → host | raw `dtn_bundle_t` |
| `ACK` | `0x20` | ESP32 → host | 1 byte (0 ok, 1 error) |
| `STATUS_RESP` | `0x21` | ESP32 → host | `host_status_t` (6 bytes) |
| `PEERS_RESP` | `0x22` | ESP32 → host | n × `host_peer_entry_t` (4 bytes) |
| `WIFI_TX` | `0x30` | host → ESP32 | over-air bytes (rover: broadcast; BS: fleet control, unicast) |
| `WIFI_RX` | `0x31` | ESP32 → host | `[src_mac:6][rssi:1][air bytes]` (rover relay) |

`radio_daemon.py` uses only `WIFI_TX`/`WIFI_RX` + `QUERY_STATUS`/`STATUS_RESP`. The bundle-centric commands belong to the legacy `jetson_daemon.py` model.

With `HOST_UART_PORT = UART_NUM_0`, ASCII log lines and binary frames share the USB port; the host tools demux on the `0xAA` SOF byte. Don't run `idf.py monitor` at the same time.

**Wired Jetson UART (optional)**: set `HOST_UART_PORT UART_NUM_1`, `HOST_UART_TX_PIN 6`, `HOST_UART_RX_PIN 7`. Wire GPIO 6 → Jetson RX, GPIO 7 ← Jetson TX and share GND, then run the daemon with `--serial /dev/ttyTHS1`. UART0 stays free for debugging. The LCD must be removed, because it shares GPIO 7.

## BS serial output

Read by `basestation/bs_core.py`. Rover telemetry lines (`@LOCATION:`, `@ROVER_STATUS`, ...) arrive as bundle payload text printed by the BS.

| Prefix | Format | Meaning |
|---|---|---|
| `@NET:` | `@NET:<node>:<parent>:<rssi>` | Beacon heard (topology heartbeat); `@NET:<bs_id>:0:0` self-heartbeat every 5 s |
| `@DTN_RX:` | `@DTN_RX:<src>:<prev>:<seq>:<receiver>:<hops>` | Data bundle received at the BS |
| `@METRIC:` | `@METRIC:<src>:<seq>:<hops>:<latency_ms>` | End-to-end latency, clock-corrected |
| `@ANTIPKT_FAIL:` | `@ANTIPKT_FAIL:<src>:<seq>:<prev>` | Duplicate from the same forwarder: its antipacket didn't arrive |
| `@FERRY_DUP:` | `@FERRY_DUP:<src>:<seq>:<first_prev>:<dup_prev>` | Same bundle via two forwarders (expected with epidemic routing) |
| `@DEDUP:` | `@DEDUP:<src>:<seq>:...` | Duplicate dropped |
| `@TXSTAT:` | `@TXSTAT:<ctrl_in>:<ctrl_sent>:<ctrl_err>:<uni_ok>:<uni_fail>` | Every 10 s, cumulative: control frames from the laptop, unicast copies queued, send errors, acknowledged / unacknowledged unicasts |
| `@NODE_RESTART:` | `@NODE_RESTART:<node_id>` | A rover's boot_id changed (its daemon restarted) |

## Gotchas

- **Band mode call order**: `esp_wifi_set_band_mode(WIFI_BAND_MODE_5G_ONLY)` must be called *after* `esp_wifi_start()`; before, it returns `ESP_ERR_WIFI_NOT_STARTED`.
- **Returning peers**: a timed-out peer that comes back is already in `peer_list` with `active=false`. The inactive→active transition resets `forwarded=false` on all stored bundles and re-adds the peer with `esp_now_add_peer`.
- **UART RTS reset (Linux)**: on `/dev/ttyUSB*`, set `rts=False` right after opening the port, or the ESP32-C5 silently resets.
- `main/Documents - Shortcut.lnk` is a stray Windows shortcut, not part of the build.
