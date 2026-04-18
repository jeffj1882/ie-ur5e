# Safety — stops, bits, and recovery

All safety behaviour below is enforced **by the robot controller itself**,
not by our software. Our `SafetyMonitor` is a read-only observer that
**refuses to issue motion** when the controller says it's unsafe — it is
*not* a replacement for UR's safety-rated hardware (the 3PE button, the
e-stops, the SafetyI/O, and the certified safety controller).

References throughout:
- UR5e User Manual SW 5.21 § 3 *Safety* (pp. 28–32).
- `DashboardServer_e-Series_2022.pdf` §§ on `safetystatus`, `unlock protective stop`, `restart safety` (pp. 9–11).
- Our monitor implementation: `src/ie_ur5e/safety.py`.

## Safety status bits (from RTDE `safety_status_bits`)

Indices match UR's RTDE recipe order. Our `safety.py:SafetyBit` enum matches
exactly.

| Bit | Name | Meaning |
|---:|---|---|
| 0 | `NORMAL_MODE` | Default safe-to-move. Should be set whenever none of the red-zone bits below are. |
| 1 | `REDUCED_MODE` | Safety-rated reduced-speed/force region is active. The arm is moving, but clipped to reduced limits. |
| 2 | `PROTECTIVE_STOPPED` | A protective stop has been triggered — likely a collision, payload mismatch, or joint limit. Requires human acknowledgment before motion resumes. |
| 3 | `RECOVERY_MODE` | A joint is past its safety-rated limit. You must hand-drive (freedrive or backdrive) the arm back inside its envelope before brakes will release. |
| 4 | `SAFEGUARD_STOPPED` | Safeguard I/O (door switch, light curtain) is interrupted. Clears automatically when the safeguard condition clears — no manual ack required. |
| 5 | `SYSTEM_EMERGENCY_STOPPED` | An emergency stop on the external Safety I/O line is latched. |
| 6 | `ROBOT_EMERGENCY_STOPPED` | The pendant e-stop (the red mushroom on the pendant) is latched. |
| 7 | `EMERGENCY_STOPPED` | One of the e-stops is latched (aggregate bit). |
| 8 | `VIOLATION` | Violation of a non-safety-rated limit (tool-flange limit, workspace plane). Auto-clearable by moving back into the envelope. |
| 9 | `FAULT` | Controller-side fault (software, comms, or sensor). Usually needs a `restart safety` via Dashboard and a controller reboot. |
| 10 | `STOPPED_DUE_TO_SAFETY` | Aggregate flag — true while any of the above stop bits are set. |

`SafetySnapshot.is_normal` (in `safety.py:SafetySnapshot`) returns true iff
bit 0 is set **and** none of bits 2, 4, 5, 6, 7, 8, 9 are set.

## Stop categories (from User Manual § 3.5)

UR lists the IEC 60204-1 stop categories the arm implements — paraphrasing
§ 3.5, pp. 32, for cross-reference only:

- **Category 0 stop** — immediate power removal. Fastest but can leave the arm in an awkward pose.
- **Category 1 stop** — controlled deceleration, then power removal once stopped.
- **Category 2 stop** — controlled deceleration, power stays on. This is what a *protective* stop is.

The pendant e-stop mushroom is a **Cat 1** stop by default. Safeguard-I/O
triggers a **Cat 2** stop unless configured otherwise. All of this is
configurable under Installation → Safety on the pendant.

## Recovery procedures by stop type

### Protective stop (`PROTECTIVE_STOP`, bit 2)

Symptoms: arm holds position, pendant shows a safety popup, `robotmode` stays
`IDLE`, `safetystatus` reports `PROTECTIVE_STOP`. Our panel's red bar with the
"Acknowledge Protective Stop" button appears automatically.

1. **Identify the cause before clearing.** Check the pendant log — PolyScope logs *why* the protective stop tripped (joint torque, TCP force, singularity approach, etc).
2. Remove whatever triggered it: reduce speed, fix the payload, get the operator's hand out of the way.
3. Wait **≥ 5 seconds** after the stop occurred — the controller rate-limits clears. The Dashboard Server PDF (p. 10) is explicit: an earlier `unlock protective stop` returns `Cannot unlock protective stop until 5s after occurrence`.
4. Click **Acknowledge Protective Stop** in the web panel, or run `ie-ur5e-dash unlock-protective-stop`. Both send the Dashboard command `unlock protective stop`. Success response: `Protective stop releasing`.
5. **Before moving again**, call `ie-ur5e-dash safetystatus` and confirm it returned to `NORMAL`.

The **50-stops-per-joint-per-8-hours** rate limit (Dashboard PDF p. 5) triggers fault `163: TOO_FREQUENT_PROTECTIVE_STOPS`. Once that fires, stop and diagnose — if you can't go 8 hours without stacking 50 stops on one joint, something is fundamentally wrong with the payload config, the program, or the workspace.

### Emergency stop (`*_EMERGENCY_STOP`, bits 5/6/7)

Symptoms: arm brakes, `robotmode` goes `POWER_OFF`, `safetystatus` reports
`ROBOT_EMERGENCY_STOP` (pendant button) or `SYSTEM_EMERGENCY_STOP` (external
I/O).

1. Figure out why someone hit the e-stop. Do not rush this step.
2. Reset the e-stop physically — pendant button: twist clockwise to release. External: fix whatever asserted the Safety I/O input.
3. On the pendant, tap through the safety popup and then ON → START to re-initialize the arm (back through the § 6.3, p. 50 sequence).
4. Confirm `safetystatus == NORMAL` before issuing any motion.

### Safeguard stop (`SAFEGUARD_STOP`, bit 4)

Symptoms: arm decelerates and holds, `safetystatus` reports `SAFEGUARD_STOP`.

1. Fix the safeguard condition — door back closed, light curtain clear.
2. Most safeguard signals auto-clear. If the controller's Safety I/O is configured for "Manual Reset", press the reset button your integrator wired.
3. No Dashboard command is needed for a self-clearing safeguard.

### Recovery mode (`RECOVERY`, bit 3)

Symptoms: a joint has been driven past its safety-rated limit — typically
after a collision that bumped the arm. Brakes won't release normally.

1. Enable **Backdrive** on the pendant (Installation → General → Backdrive).
2. Manually push each offending joint back inside its limits.
3. Exit Backdrive, tap ON → START, confirm `NORMAL`.

### Fault (`FAULT`, bit 9)

Symptoms: `robotmode` stuck in `NO_CONTROLLER` or `DISCONNECTED`, `safetystatus`
reports `FAULT`.

1. Read the pendant log. If it points at a specific joint or subsystem, that's your lead.
2. Generate a flight report for UR support:
   ```bash
   ie-ur5e-dash robotmode                        # confirm the controller is reachable at all
   printf 'generate flight report system\nquit\n' | nc $ROBOT_IP 29999
   ```
3. If the log says something generic, try `restart safety` via Dashboard — the PDF (p. 11) warns **always check the log first** because this clears controller state. The robot will land in `POWER_OFF` afterwards; go back through § 6 of the User Manual to re-initialize.
4. If `restart safety` doesn't clear the fault, power-cycle the control box (mains off, wait 30 s for discharge per § 6.6, power on).

## Our watchdog contract

`SafetyMonitor` is the single choke-point our motion code consults. The rules
we enforce in `safety.py:SafetyMonitor.assert_safe`:

- **No snapshot yet** — `WatchdogTripped("safety monitor has no snapshot yet")`. We do not issue motion against a freshly-opened RTDE session until at least one packet has round-tripped.
- **Watchdog tripped** — `WatchdogTripped(...)` with the ms threshold. Caller must close and re-open the `UR5eMotion` context to clear.
- **Not NORMAL** — `NotInNormalMode(...)` with the raw `safety_status_bits` and `robot_mode` in the message. Caller is expected to clear the upstream cause (e-stop, protective stop, etc.) — not just retry.

Callbacks registered via `on_protective_stop`, `on_emergency_stop`,
`on_safeguard_stop`, `on_fault` fire **once on the transition** into the
matching bit, not continuously while the bit is set. A failing callback
cannot crash the monitor thread — we swallow exceptions in
`safety.py:_safe_call` deliberately.
