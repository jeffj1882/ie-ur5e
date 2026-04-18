# URScript — the surface our stack actually uses

Our code never writes URScript by hand. `ur_rtde`'s `RTDEControlInterface`
generates it under the hood and feeds it through the controller's Primary
Interface (port 30001). This page is a map of which URScript primitives end
up on the wire when you call our Python APIs — so you can read
`URScript_Manual_SW5.11.pdf` with the right grep targets.

## Our calls → URScript primitives

| `UR5eMotion` method | URScript call (simplified) | Manual section |
|---|---|---|
| `move_j(joints, speed, accel)` | `movej([q0..q5], a=accel, v=speed)` | § 1. Module `motion` → `movej()` |
| `move_l(pose, speed, accel)` | `movel(p[x,y,z,rx,ry,rz], a=accel, v=speed)` | § 1. Module `motion` → `movel()` |
| `set_tcp(pose)` | `set_tcp(p[x,y,z,rx,ry,rz])` | § 1. Module `interfaces` → `set_tcp()` |
| `set_payload(mass, cog)` | `set_payload(m=mass, cog=[cx,cy,cz])` | § 1. Module `interfaces` → `set_payload()` |
| `freedrive()` context (enter) | `teach_mode()` | § 1. Module `interfaces` → `teach_mode()` |
| `freedrive()` context (exit) | `end_teach_mode()` | § 1. Module `interfaces` → `end_teach_mode()` |
| `UR5eMotion.__exit__` | `stopj(a=<decel>)` + disconnect | § 1. Module `motion` → `stopj()` |

## URScript types you'll see in the manual

- `pose` — a `p[...]` literal. 6-element Cartesian `[x, y, z, rx, ry, rz]`; XYZ in metres, rotation vector in radians (axis × angle).
- `joint positions` — bare list `[q0, q1, q2, q3, q4, q5]`, radians.
- `speed` — rad/s for `movej`, m/s for `movel`.
- `acceleration` — rad/s² for `movej`, m/s² for `movel`.
- `blend radius` — metres; controls how tightly successive `move*` calls merge. We don't pass a blend radius, so each move fully settles before the next starts.

## URScript functions worth knowing (not currently used)

Reach for these when our `UR5eMotion` API isn't expressive enough — they're
all available via `ur_rtde`'s control interface (each Python method maps to
one URScript call).

| URScript function | When to use |
|---|---|
| `movec(via, to, a, v, r)` | Circular move through `via` ending at `to`. Useful for arc welding trajectories. |
| `servoj(q, t, lookahead_time, gain)` | Low-latency servo target — subscribe to external pose from the Mac and push targets at 500 Hz. |
| `speedj([qd], a)` / `speedl([xd], a)` | Velocity-mode control (joint / TCP) instead of position. |
| `force_mode(task_frame, selection, wrench, type, limits)` / `end_force_mode()` | Compliant-motion mode — arm gives way along selected axes until a force threshold is met. Critical for any insertion / polishing / grinding workflow. |
| `stopj(a)` / `stopl(a)` | Controlled decel stop. `ur_rtde`'s `stopScript()` wraps this. |
| `protective_stop()` | Trigger an intentional protective stop from inside a program (for abort). |
| `popup(msg, title, warning, error)` | Pendant popup from URScript — distinct from the Dashboard `popup` command. |
| `sync()` | Force-flush output buffers. Use if you see stale register values on the receiver. |

## Coordinate frames

- **Base frame** — origin at the centre of the base flange, Z up, X out of the front of the base. All `p[...]` values we pass to `movel` are in this frame unless we explicitly wrap them with `pose_trans()`.
- **TCP frame** — origin at the tool tip as configured in Installation → General → TCP. `get_tcp_pose()` returns the TCP pose **in base frame**.
- **Tool flange frame** — origin at the mechanical flange face. Only matters when you're measuring tool offsets.

## Rotation representation

UR uses **rotation vectors** everywhere, not Euler angles. A rotation vector
`[rx, ry, rz]` encodes:
- Axis = `[rx, ry, rz] / ||[rx, ry, rz]||`
- Angle = `||[rx, ry, rz]||` (radians)

Practical consequences:
- Tool-pointing-down from base = `[π, 0, 0]` (rotate 180° around X-axis).
- Small corrections ≠ small Euler deltas. Don't treat `rx` as "roll" — it isn't.
- To add a rotation to a pose, use URScript `pose_trans(pose, delta_pose)` or equivalent numpy `scipy.spatial.transform.Rotation` arithmetic in Python.

## Why we don't ship custom URScript

Short answer: the controller is happier serving a single long-running script
from `ur_rtde` than it is loading, playing, and stopping ad-hoc URP programs
for every command. Our `UR5eMotion` keeps an RTDE control session open for
the lifetime of the context manager; each `move_j` / `move_l` call is a
discrete URScript command injected into that session.

If you need PolyScope-level programming — conveyor tracking, complex program
flow, operator-visible dialogs — write the URP on the pendant and drive it
from our Dashboard client: `ie-ur5e-dash load my.urp && ie-ur5e-dash play`.
