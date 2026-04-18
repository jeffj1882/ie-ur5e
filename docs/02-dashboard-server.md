# Dashboard Server (TCP :29999) — command reference

Source: `DashboardServer_e-Series_2022.pdf` in `docs/manuals/`. All command
strings and response strings below are the exact wire-level syntax UR
documents there; they are protocol facts, not prose, so our client parses
them verbatim.

## Protocol basics

- TCP port **29999** on the controller IP.
- Commands are ASCII, **newline-terminated** (`\n`).
- Commands are **case-insensitive**.
- The server sends a banner on connect:
  `Connected: Universal Robots Dashboard Server\n`
  Our `DashboardClient.connect()` in `src/ie_ur5e/dashboard.py:108` consumes
  this banner before issuing the first real command.

## Commands our `DashboardClient` uses

Mapped to `src/ie_ur5e/dashboard.py:DashboardClient` methods. Python method →
wire command → response shape → minimum SW version (source: PDF pp. 5–12).

| `DashboardClient` method | Wire command | Success response | Failure response | Min SW | Remote-only |
|---|---|---|---|---|---|
| `robotmode()` | `robotmode` | `Robotmode: <mode>` where `<mode>` ∈ `NO_CONTROLLER, DISCONNECTED, CONFIRM_SAFETY, BOOTING, POWER_OFF, POWER_ON, IDLE, BACKDRIVE, RUNNING` | — | 5.0.0 | no |
| `safetystatus()` | `safetystatus` | `Safetystatus: <status>` where `<status>` ∈ `NORMAL, REDUCED, PROTECTIVE_STOP, RECOVERY, SAFEGUARD_STOP, SYSTEM_EMERGENCY_STOP, ROBOT_EMERGENCY_STOP, VIOLATION, FAULT, AUTOMATIC_MODE_SAFEGUARD_STOP, SYSTEM_THREE_POSITION_ENABLING_STOP` | — | 5.4.0 | no |
| `power_on()` | `power on` | `Powering on` | `Not in remote control` | 5.0.0 | **yes** |
| `power_off()` | `power off` | `Powering off` | — | 5.0.0 | **yes** |
| `brake_release()` | `brake release` | `Brake releasing` | — | 5.0.0 | **yes** |
| `unlock_protective_stop()` | `unlock protective stop` | `Protective stop releasing` | `Cannot unlock protective stop until 5s after occurrence. Always inspect cause of protective stop before unlocking` | 5.0.0 | **yes** |
| `popup(msg)` | `popup <msg>` | `showing popup` | — | 5.0.0 | no |
| `close_popup()` | `close popup` | `closing popup` | — | 5.0.0 | no |
| `play()` | `play` | `Starting program` | `Failed to execute: play` | 5.0.0 | **yes** |
| `stop()` | `stop` | `Stopped` | `Failed to execute: stop` | 5.0.0 | **yes** |
| `pause()` | `pause` | `Pausing program` | `Failed to execute: pause` | 5.0.0 | **yes** |
| `load(program)` | `load <program.urp>` | `Loading program: <program.urp>` | `File not found: <name>` or `Error while loading program: <name>` | 5.0.0 | **yes** |
| `get_loaded_program()` | `get loaded program` | `Loaded program: <path>` | `No program loaded` | 5.0.0 | no |
| `is_in_remote_control()` | `is in remote control` | `true` | `false` | 5.6.0 | no |

The "Remote-only" column maps to UR's `x` column in the PDF. Sending any of
those commands while Remote Control is off raises `RobotNotInRemoteControl`
(see `src/ie_ur5e/dashboard.py:211`).

## Commands we don't wrap but might want later

Documented in the same PDF (pp. 6–13). Handy for operators / scripts; if a
real workflow needs one, add it to `DashboardClient`.

| Command | Response shape | Purpose |
|---|---|---|
| `running` | `Program running: true` / `Program running: false` | Is a program executing? |
| `programState` | `STOPPED` / `PLAYING` / `PAUSED` | Program execution state with loaded path. |
| `isProgramSaved` | `true <name>` / `false <name>` | Has the active program been saved since last edit? |
| `load installation <name>.installation` | `Loading installation: <name>` | Switch installations without reloading a program. |
| `close safety popup` | `closing safety popup` | Dismiss safety-rated popups (e.g. payload reminder). |
| `restart safety` | `Restarting safety` | Clear a safety fault / violation. Robot lands in POWER_OFF afterwards. **Use cautiously**; the PDF (p. 11) flags it. |
| `quit` | `Disconnected` | Client-side graceful close. |
| `shutdown` | `Shutting down` | Powers off controller and PolyScope. |
| `addToLog <msg>` | `Added log message` | Writes a line into the pendant log so you can correlate CLI activity with pendant activity. |
| `PolyscopeVersion` | e.g. `URSoftware 5.21.0.xxxxxxx` | Full version string. |
| `version` | e.g. `5.21.0.xxxxx` | Numeric version only. |
| `get serial number` | e.g. `20235501783` | Arm serial — should match the sticker on your UR5e. |
| `get robot model` | `UR5` (also `UR3`, `UR10`, `UR16`) | Which UR model the controller thinks it's running. |
| `set operational mode <manual\|automatic>` | `Setting operational mode: <mode>` | **Disables pendant user-password** when called — intended for keycard readers. Clear with `clear operational mode` when done. |
| `get operational mode` | `MANUAL`, `AUTOMATIC`, or `NONE` | `NONE` if the "Mode" password hasn't been configured in Settings. Min SW 5.6.0. |
| `clear operational mode` | `operational mode is no longer controlled by Dashboard Server` | Returns control to pendant. |
| `generate flight report <controller\|software\|system>` | `<report-id>` on success | Kick off a flight report. Can take minutes; wait ≥ 30 s between calls of the same type. Min SW 5.8.0. |
| `generate support file <dir-path>` | `Completed successfully: <file.zip>` | Bundle all flight reports + system state into a zip under the given programs/ subdir. Up to 10 min. |

## Rate-limit / lockout quirks worth remembering

Both from the PDF, `Unlock Protective Stop` section (p. 5):

1. **5-second minimum before you can `unlock protective stop`.** If you hit it faster, the server replies `Cannot unlock protective stop until 5s after occurrence.` — our client returns that string verbatim from `unlock_protective_stop()` rather than raising.
2. **50 protective stops per joint per 8 hours** triggers internal fault `163: TOO_FREQUENT_PROTECTIVE_STOPS`. After that, the server enforces a 5 s cooldown between clear attempts and surfaces the fault in the log. If you see this, **stop** and find the root cause — a wrong payload, an obstacle, a bad waypoint — before clearing again.

## Terminal sanity-check snippet

Straight from PDF § 2 "Dashboard Examples" (p. 14), adapted for Unix `nc`:

```bash
printf 'robotmode\nsafetystatus\nis in remote control\nquit\n' | nc 192.168.1.10 29999
```

Expected output (example):
```
Connected: Universal Robots Dashboard Server
Robotmode: IDLE
Safetystatus: NORMAL
true
Disconnected
```

Same round-trip through our stack:
```bash
ROBOT_IP=192.168.1.10 ie-ur5e-dash robotmode
ROBOT_IP=192.168.1.10 ie-ur5e-dash safetystatus
ROBOT_IP=192.168.1.10 ie-ur5e-dash is-in-remote-control
```
