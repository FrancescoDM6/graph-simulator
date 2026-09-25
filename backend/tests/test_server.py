"""The viewer's API, against a throwaway run database."""

import time

import pytest
from fastapi.testclient import TestClient

from graphsim import runner, server
from graphsim.config import load_scenario


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DATABASE", tmp_path / "runs.db")
    with TestClient(server.app) as client:
        yield client


def wait_until_done(client, run_id: int) -> dict:
    for _ in range(300):
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] != "running":
            return run
        time.sleep(0.05)
    raise TimeoutError(run_id)


def test_scenario_describes_goods_occupations_variants_and_timeline(client):
    info = client.get("/api/scenario").json()
    assert {"food", "ore"} <= info["goods"].keys()
    assert info["occupations"]["merchant"]["brokers"] is True
    assert "no_gifting" in info["variants"]
    assert info["timeline"][0]["metric"]


def test_start_a_run_then_read_everything_about_it(client):
    started = client.post("/api/runs", json={"seed": 1, "ticks": 60}).json()
    run = wait_until_done(client, started["id"])
    assert run["status"] == "done" and run["ticks_done"] == 60
    run_id = run["id"]

    series = client.get(f"/api/runs/{run_id}/metrics", params={"names": "gini_coin"}).json()
    assert len(series["series"]["gini_coin"]) == 60
    assert "population.farmer" in series["names"]

    snaps = client.get(f"/api/runs/{run_id}/snapshots", params={"first": 10, "count": 3}).json()
    assert [s["tick"] for s in snaps] == [10, 11, 12]

    notable = client.get(f"/api/runs/{run_id}/events").json()
    assert notable and not any(e["detail"] for e in notable)
    trusted = client.get(f"/api/runs/{run_id}/events", params={"kinds": "trusted"}).json()
    trail = client.get(f"/api/runs/{run_id}/events/{trusted[0]['id']}/trail").json()
    assert trail["causes"][0]["kind"] in ("trade", "gift")

    agent_id = snaps[0]["nodes"][0]["id"]
    history = client.get(f"/api/runs/{run_id}/agents/{agent_id}/history").json()
    assert history["lifetime"]["agent_id"] == agent_id and history["ticks"]
    ledger = client.get(f"/api/runs/{run_id}/trust", params={"agent": agent_id}).json()
    assert all(entry["event"]["id"] == entry["event_id"] for entry in ledger)

    lineage = client.get(f"/api/runs/{run_id}/communities").json()
    assert lineage["communities"]
    members = client.get(f"/api/runs/{run_id}/communities/members", params={"tick": 30}).json()
    assert members

    # Asking for the same run again returns the stored one.
    assert client.post("/api/runs", json={"seed": 1, "ticks": 60}).json()["id"] == run_id


def test_a_bad_variant_is_a_clear_error(client):
    response = client.post("/api/runs", json={"seed": 1, "ticks": 10, "variant": "nope"})
    assert response.status_code == 400 and "unknown variant" in response.json()["detail"]


def test_summary_runs_can_be_opened_at_full_detail(client, tmp_path):
    scenario = load_scenario()
    scenario.database = tmp_path / "runs.db"
    summary_id = runner.run(scenario, seed=2, ticks=40, level="summary")
    full = client.post(f"/api/runs/{summary_id}/materialize").json()
    full = wait_until_done(client, full["id"])
    assert full["level"] == "full" and full["seed"] == 2
    assert client.get(f"/api/runs/{full['id']}/snapshots").json()


def test_unknown_experiment_is_404(client):
    assert client.get("/api/experiments/nope").status_code == 404


def test_ledger_community_and_org_pages(client):
    started = client.post("/api/runs", json={"seed": 1, "ticks": 300}).json()
    run_id = wait_until_done(client, started["id"])["id"]

    broker = next(
        n["id"]
        for n in client.get(f"/api/runs/{run_id}/snapshots", params={"first": 300}).json()[0][
            "nodes"
        ]
        if n["kind"] == "agent" and n["occupation"] == "merchant"
    )
    ledger = client.get(f"/api/runs/{run_id}/agents/{broker}/flows").json()
    assert ledger["flows"] and ledger["lifetime"]
    assert ledger["by_category"]["coin"]["commission"] > 0

    lineage = client.get(f"/api/runs/{run_id}/communities").json()["communities"]
    cid = lineage[0]["community_id"]
    page = client.get(f"/api/runs/{run_id}/communities/{cid}").json()
    assert page["record"]["community_id"] == cid and page["history"]
    assert all(f"community-{cid}" in e["subjects"] for e in page["events"])
    members = client.get(f"/api/runs/{run_id}/communities/members", params={"tick": 100})
    assert members.status_code == 200

    founded = client.get(f"/api/runs/{run_id}/events", params={"kinds": "founded_org"}).json()
    if founded:  # seed 1 founds an organization early on
        org_id = founded[0]["subjects"][1]
        org = client.get(f"/api/runs/{run_id}/orgs/{org_id}").json()
        assert org["history"] and org["events"]
