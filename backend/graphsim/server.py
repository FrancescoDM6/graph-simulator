"""Live server: runs one simulation and streams a snapshot to every viewer after each tick.

Run from backend/:   uv run uvicorn graphsim.server:app --port 8000

WebSocket /ws
    server -> viewer: a snapshot (see serialize.py) after every tick or control change
    viewer -> server: {"command": "play" | "pause" | "step"}
                      {"command": "set_speed", "ticks_per_second": 8}
                      {"command": "reset", "seed": 42}
REST
    GET /api/entities/{id}/history   every event involving that node
    GET /api/metrics?last=200        recent per-tick metrics
"""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from graphsim import engine, serialize
from graphsim.config import SimConfig
from graphsim.events import Event
from graphsim.world_gen import build_world

MIN_SPEED, MAX_SPEED = 0.5, 30.0  # ticks per second
IDLE_POLL_SECONDS = 0.05  # how often the loop checks for "play" while paused


class Simulation:
    """The one running world, plus the playback controls viewers share."""

    def __init__(self, seed: int = 1) -> None:
        self.running = False
        self.ticks_per_second = 4.0
        self.viewers: list[WebSocket] = []
        self.reset(seed)

    def reset(self, seed: int) -> None:
        self.world = build_world(SimConfig(), seed)
        self.last_events: list[Event] = []

    def step(self) -> None:
        self.last_events = engine.step(self.world)

    def snapshot(self) -> dict[str, Any]:
        message = serialize.snapshot(self.world, self.last_events)
        message["running"] = self.running
        message["ticks_per_second"] = self.ticks_per_second
        return message

    async def broadcast(self) -> None:
        message = self.snapshot()
        for viewer in list(self.viewers):
            try:
                await viewer.send_json(message)
            except Exception:  # the viewer went away mid-send; forget it
                self.viewers.remove(viewer)

    async def handle(self, command: dict[str, Any]) -> None:
        name = command.get("command")
        if name == "play":
            self.running = True
        elif name == "pause":
            self.running = False
        elif name == "step":
            self.running = False
            self.step()
        elif name == "set_speed":
            speed = float(command.get("ticks_per_second", self.ticks_per_second))
            self.ticks_per_second = min(MAX_SPEED, max(MIN_SPEED, speed))
        elif name == "reset":
            self.running = False
            self.reset(int(command.get("seed", self.world.seed)))
        await self.broadcast()

    async def run_forever(self) -> None:
        while True:
            if self.running:
                self.step()
                await self.broadcast()
                await asyncio.sleep(1 / self.ticks_per_second)
            else:
                await asyncio.sleep(IDLE_POLL_SECONDS)


sim = Simulation()


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop_task = asyncio.create_task(sim.run_forever())
    yield
    loop_task.cancel()


app = FastAPI(title="graphsim", lifespan=lifespan)


@app.websocket("/ws")
async def viewer_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    sim.viewers.append(websocket)
    await websocket.send_json(sim.snapshot())
    try:
        while True:
            await sim.handle(await websocket.receive_json())
    except WebSocketDisconnect:
        if websocket in sim.viewers:
            sim.viewers.remove(websocket)


@app.get("/api/entities/{entity_id}/history")
def entity_history(entity_id: str) -> list[dict[str, Any]]:
    return [serialize.event_dict(e) for e in sim.world.log.for_entity(entity_id)]


@app.get("/api/metrics")
def recent_metrics(last: int = 200) -> list[dict[str, Any]]:
    return [asdict(m) for m in sim.world.metrics.history[-last:]]
