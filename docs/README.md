# ie-ur5e / docs

Operator- and integrator-facing references that bridge **this control stack** to
the **official UR documentation** for the UR5e (s/n 20235501783, e-Series,
PolyScope 5.x). Every page here cites the UR source by section + page number
so you can verify claims against the primary material.

## Index

| Doc | What it covers |
|---|---|
| [01-connect-the-robot.md](01-connect-the-robot.md) | End-to-end runbook: unbox → mount → wire → first boot → enable remote → first `ie-ur5e-dash robotmode`. |
| [02-dashboard-server.md](02-dashboard-server.md) | Exact command syntax + response strings for TCP :29999, mapped to our `DashboardClient` methods. |
| [03-rtde.md](03-rtde.md) | RTDE (TCP :30004) protocol summary and the subset of variables our `motion.py` / `safety.py` subscribe to. |
| [04-safety.md](04-safety.md) | Stop categories, protective-stop and emergency-stop recovery, our safety watchdog's contract. |
| [05-urscript-surface.md](05-urscript-surface.md) | The narrow URScript surface `ur_rtde` exposes to us: `movej`, `movel`, `teach_mode`, `set_payload`, `set_tcp`, safe-stop idioms. |
| [manuals/](manuals/) | Vendor PDFs — not checked into the repo. Run `./manuals/fetch.sh` to download (UR copyright, ~40 MB). |

## When to reach for the PDF vs. these docs

- **UR's PDF** — authoritative on hardware, safety thresholds, safety-rated I/O, stop-distance tables, mechanical tolerances, CE/UL compliance, pendant UI screenshots.
- **This `docs/` folder** — authoritative on *how our stack talks to the robot*: which RTDE fields we poll, which Dashboard replies our typed exceptions map to, what `ROBOT_IP` / payload / TCP must be set to for our code to behave correctly.

If the two ever disagree, **UR's PDF wins**. Open an issue so we can update our docs.

## Fetching the PDFs

```bash
cd docs/manuals
./fetch.sh
```

Downloads:
- `UR5e_User_Manual_SW5.21.pdf` (~20 MB) — [UR download page](https://www.universal-robots.com/download/manuals-e-seriesur20ur30/user/ur5e/521/user-manual-ur5e-e-series-sw-521-english-international-en/)
- `DashboardServer_e-Series_2022.pdf` (~224 KB) — [UR article](https://www.universal-robots.com/articles/ur/dashboard-server-e-series-port-29999/)
- `URScript_Manual_SW5.11.pdf` (~768 KB) — the last publicly-archived full script manual.

All are UR A/S copyright. Do not redistribute.
