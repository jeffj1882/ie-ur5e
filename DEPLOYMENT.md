# DEPLOYMENT — ie-ur5e

Operator-facing handoff for switching the control stack from URSim to the real
UR5e (s/n 20235501783, e-Series, PolyScope 5.x). Read top-to-bottom the first
time; after that, use the section TOC.

1. [Switching from URSim to the real UR5e](#1-switching-from-ursim-to-the-real-ur5e)
2. [Network setup](#2-network-setup)
3. [First-connection checklist](#3-first-connection-checklist)
4. [Troubleshooting](#4-troubleshooting)
5. [Apple Silicon / URSim gotchas](#5-apple-silicon--ursim-gotchas)

---

## 1. Switching from URSim to the real UR5e

1. **Pick a host IP for the arm.** Write it down. We'll use `192.168.1.10` throughout.

2. **Set it on the pendant:**
   `Settings → System → Network → Static Address`
   - IP: `192.168.1.10`
   - Subnet: `255.255.255.0`
   - Gateway: leave empty (unless you're routing off-subnet)

3. **Enable Remote Control.** Without this, Dashboard write commands (`power on`, `load`, `play`) return "Robot is not in remote control" and the motion stack can't steer anything.
   `Settings → System → Remote Control → ON`
   Top-right corner of the pendant flips to the Remote-Control badge.

4. **Tell our stack where the arm is.** Edit `.env` in the project root:
   ```bash
   ROBOT_IP=192.168.1.10
   ```
   Or export it for a single session:
   ```bash
   export ROBOT_IP=192.168.1.10
   ```
   That's the only code change needed. `connection.py:resolve_host()` reads `ROBOT_IP` first, then falls back to `config/robot.yaml:host_ip`.

5. **Sanity-check the Dashboard is reachable:**
   ```bash
   ie-ur5e-dash robotmode             # expect POWER_OFF, IDLE, or BOOTING
   ie-ur5e-dash safetystatus          # expect NORMAL
   ie-ur5e-dash is-in-remote-control  # must return true
   ```

6. **Power on and release brakes from the pendant** (first time — confirm nothing's in the workspace). Once brakes are released, every subsequent cycle can be scripted:
   ```bash
   ie-ur5e-dash power-on
   ie-ur5e-dash brake-release
   ```

7. **Launch the panel and verify live telemetry:**
   ```bash
   make api-dev
   open http://127.0.0.1:8080
   ```
   Safety LED should go green, TCP pose should be streaming, `remote = yes`.

---

## 2. Network setup

### The recommendation: a dedicated isolated subnet

Don't put the arm on your office LAN. Run it on a dedicated small switch (or a USB-Ethernet adapter on the Mac) so pendant traffic, Dashboard commands, and the 125 Hz RTDE stream never contend with anything else.

```
┌─────────────┐    Cat-5e    ┌─────────────┐    Cat-5e    ┌─────────────┐
│   MacBook   │─────────────▶│  Unmanaged  │─────────────▶│    UR5e     │
│ 192.168.1.2 │              │   switch    │              │192.168.1.10 │
└─────────────┘              └─────────────┘              └─────────────┘
```

- Use a real switch, not a cheap unpowered hub.
- Keep the cable run short (< 10 m) and don't daisy-chain.
- If you must share the LAN: VLAN the arm and give it QoS priority.

### Mac static IP on the USB-Ethernet side

```
System Settings → Network → (your USB-Ethernet adapter) → Details → TCP/IP
  Configure IPv4: Manually
  IP:      192.168.1.2
  Subnet:  255.255.255.0
  Router:  (blank)
  DNS:     (blank)
```

Test:
```bash
ping -c 3 192.168.1.10
nc -z -v 192.168.1.10 29999      # Dashboard
nc -z -v 192.168.1.10 30004      # RTDE
```

---

## 3. First-connection checklist

Before running `ie-ur5e-dash power-on` or any `move_j`:

- [ ] Pendant is in **Remote Control** mode (top-right badge visible).
- [ ] **Both** e-stops are released (pendant e-stop + cabinet e-stop, if wired).
- [ ] No human inside the work envelope. Cage door shut. Light curtains clear.
- [ ] **Payload is configured** on the pendant (or in `config/robot.yaml:payload_kg`) and matches the actual tooling. A wrong payload = runaway protective stops the first time you accelerate.
- [ ] **TCP is configured** — centre-of-tool offset from the flange, in `config/robot.yaml:tcp_offset = [x, y, z, rx, ry, rz]`.
- [ ] `ie-ur5e-dash robotmode` returns `IDLE` (brakes released, not `POWER_OFF`).
- [ ] `ie-ur5e-dash safetystatus` returns `NORMAL`.
- [ ] First motion is always a slow `move_j` to `home_joints_rad` — do not hand-craft a cartesian pose for the very first move of the day.
- [ ] Teach-pendant speed slider is at 50% or less until you've watched one full cycle.

---

## 4. Troubleshooting

### `RTDE connection refused` / `read: End of file [asio.misc:2]`
The Dashboard reports robotmode:
- `POWER_OFF` → run `ie-ur5e-dash power-on && ie-ur5e-dash brake-release`.
- `NO_CONTROLLER` → URControl isn't running; on URSim this is the Apple-Silicon emulation bug (§5). On the real arm this means the controller hasn't finished booting — wait 60 s.
- `BOOTING` → just wait.
- `DISCONNECTED` → cable, switch, or IP mismatch. Re-run the `ping` + `nc -z` checks from §2.

### `Robot is not in remote control` on any Dashboard write command
The pendant is in local mode. Flip `Settings → System → Remote Control → ON`. The badge on the top-right of the pendant must show "Remote".

### Protective stop won't clear
1. Read `safetystatus` — confirm it really is `PROTECTIVE_STOP` and not `VIOLATION` or `FAULT` (different recovery path).
2. Physically verify the workspace — figure out **what caused it** before clearing. 99% of the time the cause is a cartesian collision or an incorrect payload / TCP.
3. `ie-ur5e-dash unlock-protective-stop` — or click "Acknowledge Protective Stop" in the web panel (the red bar only appears when safety = `PROTECTIVE_STOP`).
4. If the stop re-trips on the next motion → your payload is wrong. Fix `config/robot.yaml:payload_kg` before trying again.

### Freedrive not responding
- Need `IDLE` + `NORMAL` + remote control — confirm all three via `/state`.
- Under the hood `teachMode()` returns false; motion.py turns that into `MotionError: teachMode failed to engage`.
- Some URSim tags also refuse teachmode under emulation — verify against the real arm before assuming a code bug.

### Panel shows `motion_available: false` but everything else works
`/state` returns Dashboard-only data when RTDE can't connect. Causes, in decreasing order of probability:
- Arm is powered off. `ie-ur5e-dash power-on`.
- Arm is in protective stop. See above.
- Running against URSim on Apple Silicon — §5.

### Watchdog trip: "RTDE silent for >100ms — refusing to issue motion"
`SafetyMonitor` saw the receive thread go quiet for more than 100 ms. Usually a network hiccup (spotty wifi, busy switch). Fix the link and re-enter the `UR5eMotion` context manager; the watchdog is not auto-resetting by design. For diagnostics, watch `safety_bits` on the panel — if it's stuck at `0x0000` the RTDE session has dropped entirely.

---

## 5. Apple Silicon / URSim gotchas

URSim e-Series is an **amd64-only container**. On Apple Silicon, any Docker runtime must translate x86_64 binaries. Our experience on this machine:

- **QEMU-user** (what `colima` registers by default): URControl — the real-time robot controller binary inside URSim — crashes on boot with:
  ```
  Mutex, Unknown - Could not set the attributes. Error code = 95
  Unknown Mutex::Mutex() calling exit(-1)
  ```
  This is a gap in qemu-user's pthread_mutexattr emulation. No known software workaround. Reproduces on every ursim_e-series tag we tried (5.11, 5.14, 5.18, 5.21).

- **What *does* work under QEMU:** the Dashboard Server (port 29999) and noVNC pendant (port 6080) run on Java/Felix, unaffected by the mutex bug. Phase 2 and Phase 3 verify fully; `ie-ur5e-dash` commands succeed; the web panel renders and shows Dashboard state. Only RTDE (and therefore motion) is dead.

- **Rosetta via `colima --vm-type vz --vz-rosetta`:** on our colima 0.10.1 host, the `/mnt/lima-rosetta` mount + binfmt_misc/rosetta registration that *should* show up inside the Linux VM does not appear. `/proc/sys/fs/binfmt_misc` contains only `qemu-x86_64`. Result: URControl still goes through qemu and still crashes.

- **Known-working paths:**
  1. **Docker Desktop on the Mac.** Its Rosetta integration is wired correctly. You can run Docker Desktop *alongside* colima; pin URSim to DD and leave the rest of your containers on colima.
  2. **Old x86 hardware.** A refurbished Intel ThinkCentre Tiny, NUC, or any amd64 Linux box. URSim runs native, boots in ~20 s, no emulation pain. Plug it into the same dedicated switch as the arm and point `ROBOT_IP` at it.
  3. **Our `rpi-ursim/` image** — builds an Ubuntu 24.04 arm64 Raspberry Pi image with URSim preinstalled. **Likely hits the same mutex bug** because the Pi uses the same qemu-user translator, but is worth a shot if you have a spare Pi 5 and no spare x86 box. See `rpi-ursim/README.md`.
  4. **Don't wait for URSim — test against the real arm.** Phase 4's code is proven correct via 9 offline unit tests driving a `FakeReceive`. Phase 3 is proven against URSim's live Dashboard. The only thing URSim-under-emulation would add to your confidence is watching the 200 × 200 mm square trace in simulation first. Run it on the arm at pendant speed-slider 10%, hand on the e-stop.

- **PolyScope X URSim** (`universalrobots/ursim_polyscopex`) ships native arm64 images — no emulation needed. We do *not* recommend it as a target for this stack: your arm is PolyScope 5, and PolyScope X ships a different URScript surface and a different safety protocol. You'd be testing against a near-but-not-identical simulator.
