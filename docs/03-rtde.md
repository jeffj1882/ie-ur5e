# RTDE (TCP :30004) — what we read and why

RTDE = **Real-Time Data Exchange**, UR's TCP-based telemetry + input interface
that runs at the real-time control loop frequency — **up to 500 Hz** on the
e-Series controllers (UR's official RTDE guide on docs.universal-robots.com).

Our stack uses `ur_rtde` (SDU Robotics' C++/Python binding) so we don't speak
the binary packet format directly. This doc is for when you need to debug
*why* a field value is what it is, or when you want to subscribe to variables
we don't currently expose.

## Protocol in 60 seconds

Setup sequence (every RTDE client does this exactly once on connect):

1. **V** — `RTDE_REQUEST_PROTOCOL_VERSION` — negotiate the protocol version (client sends the version it wants; server confirms).
2. **O** — `RTDE_CONTROL_PACKAGE_SETUP_OUTPUTS` — client sends a comma-separated list of output variables to subscribe to, plus the desired frequency. Server returns a recipe id + a list of data types.
3. **I** — `RTDE_CONTROL_PACKAGE_SETUP_INPUTS` — same, but for inputs the client wants to write.
4. **S** — `RTDE_CONTROL_PACKAGE_START` — begin streaming.
5. **P** — `RTDE_CONTROL_PACKAGE_PAUSE` — optional, pauses without tearing the subscription down.

Once started, the server emits one packet per tick at the negotiated rate,
containing exactly the subscribed fields in the order they were subscribed.

## What `motion.py` subscribes to

All fields read via `ur_rtde`'s `RTDEReceiveInterface` on port 30004. Types
follow UR's convention: `VECTOR6D` = six `double`s, `UINT32` = 32-bit unsigned
integer, etc.

| Field | Type | Used by | Meaning |
|---|---|---|---|
| `actual_q` | `VECTOR6D` | `get_joint_positions()` | 6 joint angles, radians, in `[base, shoulder, elbow, wrist1, wrist2, wrist3]` order. |
| `actual_qd` | `VECTOR6D` | `is_steady()` | 6 joint velocities, rad/s. We compare `abs(v) < threshold` for all 6 to decide if the arm is at rest. |
| `actual_TCP_pose` | `VECTOR6D` | `get_tcp_pose()` | `[x, y, z, rx, ry, rz]` in the base frame. XYZ in metres, rotation as an axis-angle vector in radians. |
| `actual_TCP_force` | `VECTOR6D` | `get_tcp_force()` | Generalized force at the TCP `[Fx, Fy, Fz, Tx, Ty, Tz]` in N and N·m. |
| `safety_status_bits` | `UINT32` | `SafetyMonitor._run()` | One bit per safety state. See [04-safety.md](04-safety.md) for the full map. |
| `robot_mode` | `INT32` | `SafetyMonitor._run()` | Same state machine as Dashboard's `robotmode`, but as an integer enum: `-1` NO_CONTROLLER, `0` DISCONNECTED, `1` CONFIRM_SAFETY, `2` BOOTING, `3` POWER_OFF, `4` POWER_ON, `5` IDLE, `6` BACKDRIVE, `7` RUNNING, `8` UPDATING_FIRMWARE. |

## What `motion.py` writes (via `RTDEControlInterface`)

Writes go through `ur_rtde`'s higher-level `rtde_control` wrapper — it
synthesizes URScript under the hood, feeds it through the controller's
Primary Interface, and uses RTDE only for handshake/status. The calls we make:

| Wrapper method | What it does on the arm |
|---|---|
| `moveJ(joints, speed, accel)` | Joint-space trapezoidal move to an absolute joint target. Blocks until steady. |
| `moveL(pose, speed, accel)` | Linear Cartesian move in the base frame. Blocks until steady. |
| `setPayload(mass_kg, cog_xyz)` | Live-update the controller's payload model — crucial after picking or releasing an object. |
| `setTcp(pose)` | Live-update the TCP offset. |
| `teachMode()` / `endTeachMode()` | Enter / leave freedrive. While in teach mode the brakes are released but servos compensate for gravity so you can pull the arm around by hand. |
| `stopScript()` | Clean program abort — we call this on `UR5eMotion.__exit__`. |

## Useful output variables we don't subscribe to today

If you need any of these, add them to the RTDE config we pass `ur_rtde`'s
`RTDEReceiveInterface`. UR exposes many more — these are the useful-for-us ones.

| Field | Type | When you'd want it |
|---|---|---|
| `target_q` / `target_qd` | `VECTOR6D` | Planner's target vs. actual for dragging out a following-error plot. |
| `actual_current` | `VECTOR6D` | Joint motor currents — useful for collision detection. |
| `actual_TCP_speed` | `VECTOR6D` | TCP linear + angular velocity. |
| `runtime_state` | `UINT32` | Program-level running/paused/stopped flag (1 = running, 2 = paused, 3 = stopped). |
| `output_bit_registers0_to_31` | `UINT32` | 32 general-purpose output bits — handy for lightweight robot → PC signalling without opening another TCP socket. |
| `timestamp` | `DOUBLE` | Controller tick time. Useful for drift detection if you care about jitter. |

## Watchdog math

Our `SafetyMonitor` (`src/ie_ur5e/safety.py`) polls the RTDE receive side at
125 Hz (config: `config/robot.yaml:rtde_frequency`). If the monitor can't
read a fresh packet for **>100 ms** (`watchdog_ms: 100`), it trips:

- `WatchdogTripped` is raised on the next `assert_safe()` call.
- `on_fault(snap)` callbacks fire once with a synthetic `SafetySnapshot(bits=0, mode=DISCONNECTED)`.
- All subsequent motion calls refuse until a fresh packet arrives **and**
  `assert_safe()` is called explicitly — we deliberately do not auto-reset.

100 ms is ~12 packets at 125 Hz. That's enough slack for a transient switch
flap but short enough that a real RTDE disconnect (cable unplug, controller
reboot) is caught before any motion command is sent.

## References

- UR tutorial page: *Real-Time Data Exchange (RTDE) Guide* —
  https://docs.universal-robots.com/tutorials/communication-protocol-tutorials/rtde-guide.html
- `ur_rtde` SDU Python/C++ binding: https://sdurobotics.gitlab.io/ur_rtde/
- UR developer portal, RTDE section: https://www.universal-robots.com/developer/communication-protocol/rtde/
