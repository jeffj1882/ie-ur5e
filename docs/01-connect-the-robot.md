# Connecting the UR5e (first-time runbook)

Takes you from a boxed arm to `ie-ur5e-dash robotmode → IDLE` and a streaming
telemetry panel. Every numbered step cites the UR5e User Manual (**SW 5.21**,
document `710-965-00`) and the Dashboard Server reference (**e-Series 2022**)
that `docs/manuals/fetch.sh` drops into this directory.

> **If these instructions and the UR PDF ever disagree, the PDF wins.** Open
> an issue so we can fix this page.

---

## 0. Before you power anything

Check you actually have everything.

- [ ] UR5e arm — write down the **serial number on the arm** (PolyScope asks for it on first boot; ref: § 6.2, p. 49).
- [ ] Control Box (Standard, OEM AC, or OEM DC — the pendant asks which; ref: § 6.2, p. 49).
- [ ] Teach Pendant (note: **3PE vs Standard** — if yours has the blue 3-position enabling button on the back, it's 3PE and PolyScope must be told so; ref: § 7.4.2, p. 66).
- [ ] Robot cable (arm → control box) and mains cable (control box → wall).
- [ ] Cat 5e/6 Ethernet cable for the Mac-side link.
- [ ] A dedicated small unmanaged switch (or USB-Ethernet adapter on the Mac). Do **not** share the LAN — see `DEPLOYMENT.md § 2`.

## 1. Mount the arm

Ref: UR5e User Manual § 5 (Assembly and Mounting), pp. 34–46.

1. Bolt the arm to a rigid surface (table, plinth, robot stand). The manual's § 5.2 has the stand-stiffness calculation if you're building one from scratch.
2. Leave at least the control-box clearance specified in § 5.5 (p. 43) on every side for airflow.
3. Route the robot cable from the arm's base to the control box's **Robot** port (§ 5.7, p. 45). Finger-tight the locking ring.
4. Connect mains. The arm discharges for **30 seconds** after mains removal — note this for any later re-cabling (§ 6.6, p. 52).

> **Mounting orientation matters.** § 6.8 (p. 58) explains that the controller needs to know whether you mounted the arm on a floor (0°), a wall (90°), upside-down (180°), or at an arbitrary tilt — so gravity compensation works. You set this on the pendant after first boot in **Installation → General → Mounting**.

## 2. Wire the Ethernet link

Ref: § 7.2 (Control Box Connection Ports), p. 62 and § 7.3 (Ethernet), p. 63.

The control box exposes, under its base plate, a single **RJ-45 Ethernet port** rated **10 / 100 / 1000 Mb/s**.

```
┌──────────────┐      Cat 5e       ┌───────────┐      Cat 5e       ┌─────────────┐
│   MacBook    │──(USB-Ethernet)──▶│  Switch   │──────────────────▶│  UR5e ctrl  │
│ 192.168.1.2  │                   │ unmanaged │                   │192.168.1.10 │
└──────────────┘                   └───────────┘                   └─────────────┘
```

Route the Ethernet cable through the base plate, through an appropriate cable gland, and plug it into the port on the underside of the control box (see § 7.3 photo, p. 63).

## 3. First power-on

Ref: § 6.1–6.3, pp. 49–50, and § 8.1 (Quick System Start-up), p. 106.

1. Plug in mains. **Do not** touch the power button yet.
2. Unlatch the e-stop button on the pendant (twist clockwise).
3. Press the power button on the pendant — control box boots, PolyScope loads (§ 6.1, p. 49).
4. **First boot only:** pendant asks for robot type (UR5), control-box variant (Standard/OEM AC/OEM DC), and the serial number off the arm sticker. Tap **OK** (§ 6.2, p. 49).
5. The pendant shows the **Initialize** screen. Robot state = **NO_CONTROLLER** → **POWER_OFF** over ~10 s.
6. Tap **ON** on PolyScope. State transitions to yellow **IDLE** — controller is running, joints still braked (§ 6.3, p. 50).
7. Verify **Active Payload** and **Mounting** panels match reality (bare flange = 0.000 kg; if you mounted the arm to a floor, mounting angle = 0°).
8. **Clear the work envelope of humans.** Keep your hand on the e-stop.
9. Tap **START**. The brakes release with an audible click and some slight motion. State goes green **NORMAL** (§ 6.3, p. 50).

If you get a **Cannot Proceed** dialog, go through § 6.4 (p. 50) — almost always means the mounting wasn't confirmed.

## 4. Set the network config on the pendant

1. Pendant → **☰ Hamburger → Settings → System → Network**.
2. Set **Static Address**:
   - IP address: `192.168.1.10`
   - Subnet mask: `255.255.255.0`
   - Default gateway: *(blank, unless you route off-subnet)*
3. Tap **Apply**. The pendant may warn that Ethernet-dependent URCaps will restart.

## 5. Configure the Mac side

On macOS:
- System Settings → Network → your USB-Ethernet adapter → Details → TCP/IP
- Configure IPv4: **Manually**
- IP: `192.168.1.2` — Subnet: `255.255.255.0` — Router: *blank*

Verify both directions:
```bash
ping -c 3 192.168.1.10           # ICMP
nc -z -v 192.168.1.10 29999      # Dashboard Server port
nc -z -v 192.168.1.10 30004      # RTDE port
```

All three must succeed before the next step.

## 6. Turn on Remote Control on the pendant

Without this, our `DashboardClient` will get *"Robot is not in remote control"* on every write command, and `ie-ur5e-dash power-on` will fail.

1. Pendant → **Settings → System → Remote Control → ON**.
2. The top-right corner of the pendant flips from a person icon to the **Remote** badge. Our `ie-ur5e-dash is-in-remote-control` will now return `true`.

The Dashboard Server's response reference (p. 11 of `DashboardServer_e-Series_2022.pdf`) confirms this — the `is in remote control` command returns `"true"` or `"false"` exactly as our client parses it.

## 7. Point our stack at the arm

On the Mac:
```bash
cd ~/Development/ur5e-control
echo 'ROBOT_IP=192.168.1.10' > .env        # or `export ROBOT_IP=192.168.1.10`
```

## 8. First real command round-trip

```bash
ie-ur5e-dash robotmode              # → IDLE   (from § 6.3 state machine)
ie-ur5e-dash safetystatus           # → NORMAL
ie-ur5e-dash is-in-remote-control   # → true
ie-ur5e-dash popup "hello UR5e"     # arm pendant shows a popup
ie-ur5e-dash close-popup            # dismiss it
```

All four should succeed. If any fails see `DEPLOYMENT.md § 4` or
[02-dashboard-server.md](02-dashboard-server.md).

## 9. Configure payload and TCP before moving

This is the single most common cause of day-1 protective stops.

1. Pendant → **Installation → General → Payload** (§ 7.11.4, pp. 96–100).
   - Enter **Mass** (kg) — the total weight attached to the flange, not just the gripper.
   - Enter **Center of Gravity** (CoG) as `cx, cy, cz` in **mm** from the flange origin.
   - For heavy or asymmetric tooling, tap **Use custom Inertia Matrix** and fill in `Ixx … Iyz` (§ "Setting Inertia Values", p. 100). Otherwise PolyScope computes inertia assuming a uniform-density sphere — fine for a simple gripper, wrong for a long welding torch.
   - If you don't know the payload precisely, use **Payload Estimation Wizard** (§ "Using the Payload Estimation Wizard", p. 99) — the arm moves itself through 4 poses and computes mass + CoG from joint torques.
2. Pendant → **Installation → General → TCP**. Enter the `x, y, z, rx, ry, rz` offset from the flange to the actual tool tip.
3. Mirror both into `config/robot.yaml` so our code sees the same values:
   ```yaml
   payload_kg: 1.25           # match Installation → Payload → Mass
   tcp_offset: [0, 0, 0.12, 0, 0, 0]   # x, y, z in m; r* in rad
   ```

## 10. Launch the web panel

```bash
make api-dev
open http://127.0.0.1:8080
```

Expected readout at idle:
- Safety LED **green**
- `safety: NORMAL`, `mode: IDLE`, `remote: yes`
- TCP pose and joint readouts streaming at 20 Hz
- Safety bits showing `0x0001` (NORMAL_MODE bit; see [04-safety.md](04-safety.md))

## 11. First motion — slowly

The UR quick-start (§ 8.1, p. 106) guides you to teach a first program from the pendant. Our version: run the programmatic home move, with the pendant speed slider at ≤ 50 % and your hand on the e-stop.

From the web panel, click **Home**. The arm moves to `config/robot.yaml:home_joints_rad` at 0.5 rad/s. Watch for:
- Joint readouts changing smoothly (no ratcheting)
- Safety LED stays green throughout
- No protective-stop banner appears

If the Home button gives you a 503 with `motion unavailable`, `UR5eMotion` couldn't open an RTDE session. Usual causes (in order of likelihood):
1. Remote Control is off — go back to § 6.
2. Payload is wildly wrong and the controller refused to brake-release — re-check § 7.11.4 (p. 96).
3. `ROBOT_IP` in `.env` doesn't match what's on the pendant.

## 12. When you're done for the day

```bash
# on the Mac
make sim-down          # only if URSim was also running
```

On the pendant:
1. Tap **Power Off** on the Initialize screen or the footer.
2. Hold the pendant power button for ~2 s — confirm **Power Off** in the shutdown dialog.
3. Only now unplug the mains cable. UR recommends waiting **30 s** for stored energy to discharge before disconnecting anything else (§ 6.6, p. 52).

---

## Quick reference — the state machine you'll see

Drawn from the `robotmode` definitions in `DashboardServer_e-Series_2022.pdf` p. 6
and the Initialize flow in the User Manual § 6.3 (p. 50).

```
POWER_OFF ─── tap ON ───▶ POWER_ON ─── wait ──▶ IDLE ─── tap START ──▶ RUNNING
   ▲                                              │                      │
   │                                         brake release          program exit
   │                                              │                      │
   └─────────── tap Power Off ◀──────────────────┴──────────────────────┘
```

Add these two transient states you'll see during boot:
```
NO_CONTROLLER ───▶ BOOTING ───▶ DISCONNECTED ───▶ POWER_OFF
```

…and these safety-related modes, orthogonal to robotmode:
- **NORMAL** — safe-to-move
- **REDUCED** — safety-rated speed/force reduction engaged
- **PROTECTIVE_STOP** — see [04-safety.md](04-safety.md)
- **SAFEGUARD_STOP** — safeguard I/O, light curtain, door switch
- **SYSTEM_EMERGENCY_STOP** / **ROBOT_EMERGENCY_STOP** — one of the e-stops latched
- **RECOVERY** — joint limits violated, need to back off manually
- **FAULT** / **VIOLATION** — hardware or config error; check flight report

Full response table: [02-dashboard-server.md](02-dashboard-server.md).
