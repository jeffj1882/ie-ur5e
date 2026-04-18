# ie-ur5e

Python control stack for the Improvised Electronics UR5e (serial 20235501783, PolyScope 5.x, e-Series).

Built phase-by-phase against **URSim** before touching the physical arm.

## Quickstart

```bash
make install      # create venv, install deps
make sim-up       # start URSim in Docker (Phase 2)
make api-dev      # launch web control panel on :8080 (Phase 5)
```

Set `ROBOT_IP` in `.env` (or env) to point at URSim (`127.0.0.1`) or the real arm (`192.168.1.10`).

## UR Port Reference

| Port  | Service               | Purpose                                    |
|-------|-----------------------|--------------------------------------------|
| 29999 | Dashboard Server      | Load/play/stop programs, power, popups     |
| 30001 | Primary Client        | 10 Hz robot state + URScript ingestion     |
| 30002 | Secondary Client      | 10 Hz robot state (read-only clients)      |
| 30003 | Realtime Interface    | 500 Hz robot state, low-latency monitoring |
| 30004 | RTDE                  | Configurable-rate I/O, used by `ur_rtde`   |

## Project Layout

```
src/ie_ur5e/
  connection.py   config + host resolution
  dashboard.py    port 29999 async client (Phase 3)
  motion.py       ur_rtde wrapper             (Phase 4)
  safety.py       RTDE safety watchdog        (Phase 4)
  api.py          FastAPI control panel       (Phase 5)
tests/            mirrors src/ie_ur5e/
examples/         hello_move, telemetry_stream
config/robot.yaml host_ip, rtde_frequency, tcp, payload, home
scripts/          wait_for_ursim.py
ursim_programs/   mounted into URSim container for URP files
```

## Console scripts

- `ie-ur5e-check` — assert package imports and config loads
- `ie-ur5e-dash` — Dashboard CLI (Phase 3)
- `ie-ur5e-api`  — FastAPI service (Phase 5)

## Make targets

| Target          | Purpose                                 |
|-----------------|-----------------------------------------|
| `install`       | `uv sync` dev + runtime deps            |
| `lint`          | `ruff check` + `ruff format --check`    |
| `test`          | `pytest` (integration tests auto-skip)  |
| `sim-up`        | Start URSim, block until ready          |
| `sim-down`      | Stop & remove URSim container           |
| `sim-logs`      | Tail URSim logs                         |
| `sim-shell`     | Shell into URSim container              |
| `sim-teach`     | Open pendant at http://localhost:6080   |
| `connect-check` | Run `ie-ur5e-check`                     |
| `api-dev`       | `uvicorn` with reload                   |

## Platform notes

Apple Silicon (arm64): URSim runs under `linux/amd64` emulation — functional but slow.
Intel (x86_64): native, full speed.
