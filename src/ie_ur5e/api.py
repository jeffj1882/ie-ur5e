"""FastAPI web control panel for the UR5e on :8080.

Degrades gracefully when RTDE can't connect: Dashboard-only endpoints stay
live so the operator can inspect robotmode and issue power/brake commands
from the panel even while URControl is down (e.g. URSim on Apple Silicon
or a real arm that's powered off).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from ie_ur5e.connection import RobotConfig, load_config
from ie_ur5e.dashboard import (
    DashboardClient,
    DashboardError,
    ProgramNotLoaded,
    RobotNotInRemoteControl,
)
from ie_ur5e.motion import MotionError, UR5eMotion

_STATIC_DIR = Path(__file__).parent / "static"
_TELEMETRY_HZ = 20.0


# ── Request / response schemas ──────────────────────────────────────────────
class PowerRequest(BaseModel):
    on: bool


class MoveJRequest(BaseModel):
    joints: list[float] = Field(..., min_length=6, max_length=6)
    speed: float = 0.5
    accel: float = 1.0


class MoveLRequest(BaseModel):
    pose: list[float] = Field(..., min_length=6, max_length=6)
    speed: float = 0.25
    accel: float = 1.2


class FreedriveRequest(BaseModel):
    enable: bool


class LoadRequest(BaseModel):
    program: str


class JogJointRequest(BaseModel):
    index: int = Field(..., ge=0, le=5)
    delta: float  # radians
    speed: float = 0.3
    accel: float = 1.0


class JogTcpRequest(BaseModel):
    axis: str  # one of x, y, z, rx, ry, rz
    delta: float  # metres for x/y/z, radians for rx/ry/rz
    speed: float = 0.05
    accel: float = 0.5


# ── Lifespan ────────────────────────────────────────────────────────────────
@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    cfg = load_config()
    app.state.config = cfg
    app.state.dashboard = DashboardClient(cfg.host_ip)
    app.state.motion_lock = asyncio.Lock()
    app.state.motion = None
    app.state.motion_error: str | None = None

    with contextlib.suppress(Exception):
        await app.state.dashboard.connect()

    # Motion connect is blocking; bounce to a thread.
    try:
        motion = UR5eMotion(cfg.host_ip, cfg)
        await asyncio.to_thread(motion.__enter__)
        app.state.motion = motion
    except MotionError as e:
        app.state.motion_error = str(e)

    try:
        yield
    finally:
        if app.state.motion is not None:
            await asyncio.to_thread(app.state.motion.__exit__, None, None, None)
        with contextlib.suppress(Exception):
            await app.state.dashboard.close()


app = FastAPI(title="ie-ur5e", lifespan=lifespan)


# ── Helpers ─────────────────────────────────────────────────────────────────
def _dash(app: FastAPI) -> DashboardClient:
    return app.state.dashboard


def _cfg(app: FastAPI) -> RobotConfig:
    return app.state.config


def _require_motion(app: FastAPI) -> UR5eMotion:
    if app.state.motion is None:
        raise HTTPException(
            status_code=503,
            detail=(f"motion unavailable — {app.state.motion_error or 'RTDE not connected'}"),
        )
    return app.state.motion


async def _run_motion(app: FastAPI, fn, *args: Any, **kwargs: Any):  # type: ignore[no-untyped-def]
    """Serialize + off-thread motion calls."""
    async with app.state.motion_lock:
        return await asyncio.to_thread(fn, *args, **kwargs)


def _programs_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "ursim_programs"


# ── Root ────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    html = (_STATIC_DIR / "index.html").read_text()
    return html


# ── Dashboard-backed endpoints ──────────────────────────────────────────────
@app.get("/state")
async def state() -> dict[str, Any]:
    d = _dash(app)
    out: dict[str, Any] = {
        "host": _cfg(app).host_ip,
        "motion_available": app.state.motion is not None,
        "motion_error": app.state.motion_error,
    }
    try:
        out["robotmode"] = (await d.robotmode()).value
        out["safety"] = (await d.safetystatus()).value
        out["remote_control"] = await d.is_in_remote_control()
        loaded = await d.get_loaded_program()
        out["loaded_program"] = loaded
    except DashboardError as e:
        out["dashboard_error"] = str(e)

    m = app.state.motion
    if m is not None:
        tcp = await asyncio.to_thread(m.get_tcp_pose)
        out["tcp"] = tcp.to_list()
        out["joints"] = await asyncio.to_thread(m.get_joint_positions)
        out["force"] = await asyncio.to_thread(m.get_tcp_force)
        snap = m.monitor.latest() if m.monitor else None
        if snap is not None:
            out["safety_bits"] = snap.bits
    return out


@app.post("/power")
async def power(req: PowerRequest) -> dict[str, str]:
    d = _dash(app)
    reply = await (d.power_on() if req.on else d.power_off())
    return {"reply": reply}


@app.post("/brake_release")
async def brake_release() -> dict[str, str]:
    return {"reply": await _dash(app).brake_release()}


@app.post("/stop")
async def stop() -> dict[str, str]:
    return {"reply": await _dash(app).stop()}


@app.post("/estop_ack")
async def estop_ack() -> dict[str, str]:
    return {"reply": await _dash(app).unlock_protective_stop()}


@app.post("/play")
async def play() -> dict[str, str]:
    try:
        return {"reply": await _dash(app).play()}
    except DashboardError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/programs")
async def programs() -> dict[str, list[str]]:
    p = _programs_dir()
    if not p.exists():
        return {"programs": []}
    return {"programs": sorted(f.name for f in p.iterdir() if f.suffix == ".urp")}


@app.post("/load")
async def load_program(req: LoadRequest) -> dict[str, str]:
    # URSim sees our ursim_programs dir as /ursim/programs — map the name.
    path = f"/ursim/programs/{req.program}" if "/" not in req.program else req.program
    try:
        return {"reply": await _dash(app).load(path)}
    except ProgramNotLoaded as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RobotNotInRemoteControl as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


# ── Motion endpoints ────────────────────────────────────────────────────────
@app.post("/move_j")
async def move_j(req: MoveJRequest) -> dict[str, str]:
    m = _require_motion(app)
    try:
        await _run_motion(app, m.move_j, req.joints, req.speed, req.accel)
    except MotionError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"status": "ok"}


@app.post("/move_l")
async def move_l(req: MoveLRequest) -> dict[str, str]:
    m = _require_motion(app)
    try:
        await _run_motion(app, m.move_l, req.pose, req.speed, req.accel)
    except MotionError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"status": "ok"}


@app.post("/home")
async def home() -> dict[str, str]:
    m = _require_motion(app)
    try:
        await _run_motion(app, m.move_j, _cfg(app).home_joints_rad, 0.5, 1.0)
    except MotionError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"status": "ok"}


@app.post("/jog/joint")
async def jog_joint(req: JogJointRequest) -> dict[str, str]:
    m = _require_motion(app)
    joints = await asyncio.to_thread(m.get_joint_positions)
    joints[req.index] += req.delta
    try:
        await _run_motion(app, m.move_j, joints, req.speed, req.accel)
    except MotionError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"status": "ok"}


@app.post("/jog/tcp")
async def jog_tcp(req: JogTcpRequest) -> dict[str, str]:
    axis_map = {"x": 0, "y": 1, "z": 2, "rx": 3, "ry": 4, "rz": 5}
    if req.axis not in axis_map:
        raise HTTPException(status_code=400, detail=f"unknown axis {req.axis!r}")
    m = _require_motion(app)
    pose = (await asyncio.to_thread(m.get_tcp_pose)).to_list()
    pose[axis_map[req.axis]] += req.delta
    try:
        await _run_motion(app, m.move_l, pose, req.speed, req.accel)
    except MotionError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"status": "ok"}


@app.post("/freedrive")
async def freedrive(req: FreedriveRequest) -> dict[str, str]:
    m = _require_motion(app)
    if req.enable:
        if not await asyncio.to_thread(m._control.teachMode):  # type: ignore[union-attr]
            raise HTTPException(status_code=400, detail="teachMode rejected")
    else:
        await asyncio.to_thread(m._control.endTeachMode)  # type: ignore[union-attr]
    return {"status": "ok"}


# ── Telemetry WebSocket @ 20 Hz ─────────────────────────────────────────────
@app.websocket("/telemetry")
async def telemetry(ws: WebSocket) -> None:
    await ws.accept()
    period = 1.0 / _TELEMETRY_HZ
    try:
        while True:
            frame: dict[str, Any] = {}
            try:
                frame["robotmode"] = (await _dash(app).robotmode()).value
                frame["safety"] = (await _dash(app).safetystatus()).value
            except DashboardError:
                frame["robotmode"] = "UNKNOWN"
                frame["safety"] = "UNKNOWN"
            m = app.state.motion
            if m is not None:
                tcp = await asyncio.to_thread(m.get_tcp_pose)
                frame["tcp"] = tcp.to_list()
                frame["joints"] = await asyncio.to_thread(m.get_joint_positions)
                frame["force"] = await asyncio.to_thread(m.get_tcp_force)
                snap = m.monitor.latest() if m.monitor else None
                frame["safety_bits"] = snap.bits if snap else 0
            await ws.send_text(json.dumps(frame))
            await asyncio.sleep(period)
    except WebSocketDisconnect:
        return
