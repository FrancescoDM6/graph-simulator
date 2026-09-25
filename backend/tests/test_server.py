from fastapi.testclient import TestClient

from graphsim.server import app, sim


def test_viewer_gets_a_snapshot_and_can_step_and_reset():
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        first = ws.receive_json()
        assert first["running"] is False
        assert any(n["kind"] == "agent" for n in first["nodes"])

        ws.send_json({"command": "step"})
        after_step = ws.receive_json()
        assert after_step["tick"] == first["tick"] + 1
        assert after_step["metrics"] is not None

        ws.send_json({"command": "reset", "seed": 5})
        after_reset = ws.receive_json()
        assert after_reset["tick"] == 0
        assert after_reset["seed"] == 5


def test_history_endpoint_returns_events_for_one_entity():
    sim.reset(seed=2)
    for _ in range(50):
        sim.step()
    agent_id = next(iter(sim.world.agents))

    with TestClient(app) as client:
        history = client.get(f"/api/entities/{agent_id}/history").json()

    assert history, "an agent should have some history after 50 ticks"
    assert all(agent_id in event["subjects"] for event in history)
