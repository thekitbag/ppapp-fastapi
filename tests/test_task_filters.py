from fastapi.testclient import TestClient
from datetime import datetime, timedelta

from app.main import app

client = TestClient(app)


def create_task(**kwargs):
    resp = client.post("/api/v1/tasks", json=kwargs)
    assert resp.status_code == 201
    return resp.json()


def test_filter_by_project_only():
    # Create two projects via API
    p1 = client.post("/api/v1/projects", json={"name": "P1"}).json()
    p2 = client.post("/api/v1/projects", json={"name": "P2"}).json()

    t1 = create_task(title="Proj t1", status="week", project_id=p1["id"])
    t2 = create_task(title="Proj t2", status="week", project_id=p2["id"])
    t3 = create_task(title="Proj t3", status="week")

    r = client.get(f"/api/v1/tasks?project_id={p1['id']}")
    assert r.status_code == 200
    ids = {t["id"] for t in r.json()}
    assert t1["id"] in ids
    assert t2["id"] not in ids
    assert t3["id"] not in ids

    # cleanup
    for tid in [t1["id"], t2["id"], t3["id"]]:
        client.delete(f"/api/v1/tasks/{tid}")
    client.delete(f"/api/v1/projects/{p1['id']}")
    client.delete(f"/api/v1/projects/{p2['id']}")


def test_filter_by_goal_link_or_legacy():
    # Create proper hierarchy: Annual -> Quarterly -> Weekly
    annual = client.post("/api/v1/goals", json={"title": "Annual", "type": "annual"}).json()
    quarterly = client.post("/api/v1/goals", json={"title": "Q1", "type": "quarterly", "parent_goal_id": annual["id"]}).json()
    goal = client.post("/api/v1/goals", json={"title": "W1", "type": "weekly", "parent_goal_id": quarterly["id"]}).json()

    # Create tasks
    t_link = create_task(title="Linked", status="week")
    t_legacy = create_task(title="Legacy", status="week", goal_id=goal["id"])  # legacy field
    t_other = create_task(title="Other", status="week")

    # Link t_link via goal API
    link_resp = client.post(f"/api/v1/goals/{goal['id']}/link-tasks", json={"goal_id": goal["id"], "task_ids": [t_link["id"]]})
    assert link_resp.status_code == 200

    r = client.get(f"/api/v1/tasks?goal_id={goal['id']}")
    assert r.status_code == 200
    ids = {t["id"] for t in r.json()}
    assert t_link["id"] in ids
    assert t_legacy["id"] in ids
    assert t_other["id"] not in ids

    # cleanup
    for tid in [t_link["id"], t_legacy["id"], t_other["id"]]:
        client.delete(f"/api/v1/tasks/{tid}")
    # Delete in reverse order of hierarchy
    client.delete(f"/api/v1/goals/{goal['id']}")
    client.delete(f"/api/v1/goals/{quarterly['id']}")
    client.delete(f"/api/v1/goals/{annual['id']}")


def test_filter_by_single_and_multiple_tags_and_unknown():
    t_a = create_task(title="Tag A", status="week", tags=["a", "b"]) 
    t_b = create_task(title="Tag B", status="week", tags=["a"]) 
    t_c = create_task(title="Tag C", status="week", tags=["b"]) 
    t_d = create_task(title="No tags", status="week")

    # single tag
    r = client.get("/api/v1/tasks?tags=a")
    assert r.status_code == 200
    ids = {t["id"] for t in r.json()}
    assert t_a["id"] in ids and t_b["id"] in ids
    assert t_c["id"] not in ids and t_d["id"] not in ids

    # multiple tags AND semantics
    r = client.get("/api/v1/tasks?tags=a&tags=b")
    ids = {t["id"] for t in r.json()}
    assert t_a["id"] in ids
    assert t_b["id"] not in ids and t_c["id"] not in ids and t_d["id"] not in ids

    # unknown tag => empty
    r = client.get("/api/v1/tasks?tags=__unknown__")
    assert r.status_code == 200
    assert len(r.json()) == 0

    # cleanup
    for tid in [t_a["id"], t_b["id"], t_c["id"], t_d["id"]]:
        client.delete(f"/api/v1/tasks/{tid}")


def test_search_title_and_description():
    t1 = create_task(title="Foo bar", status="week")
    t2 = create_task(title="Something else", description="has FOO inside", status="week")
    t3 = create_task(title="No match", status="week")

    r = client.get("/api/v1/tasks?search=foo")
    assert r.status_code == 200
    ids = {t["id"] for t in r.json()}
    assert t1["id"] in ids and t2["id"] in ids
    assert t3["id"] not in ids

    # cleanup
    for tid in [t1["id"], t2["id"], t3["id"]]:
        client.delete(f"/api/v1/tasks/{tid}")


def test_due_date_range_filters():
    base = datetime(2025, 9, 1, 10, 0, 0)
    in_range_soft = create_task(title="Soft in range", status="week", soft_due_at=(base + timedelta(days=1)).isoformat())
    in_range_hard = create_task(title="Hard in range", status="week", hard_due_at=(base + timedelta(days=2)).isoformat())
    out_before = create_task(title="Before", status="week", soft_due_at=(base - timedelta(days=1)).isoformat())
    out_after = create_task(title="After", status="week", soft_due_at=(base + timedelta(days=10)).isoformat())
    no_due = create_task(title="No due", status="week")

    # full range 2025-09-01..2025-09-07
    r = client.get("/api/v1/tasks?due_date_start=2025-09-01&due_date_end=2025-09-07")
    assert r.status_code == 200
    ids = {t["id"] for t in r.json()}
    assert in_range_soft["id"] in ids and in_range_hard["id"] in ids
    assert out_before["id"] not in ids and out_after["id"] not in ids and no_due["id"] not in ids

    # start only
    r = client.get("/api/v1/tasks?due_date_start=2025-09-02")
    ids = {t["id"] for t in r.json()}
    assert out_before["id"] not in ids

    # end only
    r = client.get("/api/v1/tasks?due_date_end=2025-09-03")
    ids = {t["id"] for t in r.json()}
    assert out_after["id"] not in ids

    # cleanup
    for tid in [in_range_soft["id"], in_range_hard["id"], out_before["id"], out_after["id"], no_due["id"]]:
        client.delete(f"/api/v1/tasks/{tid}")


def test_combined_filters_status_project_tags_search():
    # Project
    proj = client.post("/api/v1/projects", json={"name": "Combo"}).json()

    # Tasks
    good = create_task(title="Foo alpha", status="week", project_id=proj["id"], tags=["x", "y"])
    wrong_status = create_task(title="Foo alpha", status="backlog", project_id=proj["id"], tags=["x", "y"])
    wrong_project = create_task(title="Foo alpha", status="week", tags=["x", "y"])  # no project
    missing_tag = create_task(title="Foo alpha", status="week", project_id=proj["id"], tags=["x"])  # missing y
    wrong_search = create_task(title="Bar beta", status="week", project_id=proj["id"], tags=["x", "y"])  # search mismatch

    q = f"/api/v1/tasks?status=week&project_id={proj['id']}&tags=x&tags=y&search=foo"
    r = client.get(q)
    assert r.status_code == 200
    ids = [t["id"] for t in r.json()]
    assert good["id"] in ids
    assert wrong_status["id"] not in ids
    assert wrong_project["id"] not in ids
    assert missing_tag["id"] not in ids
    assert wrong_search["id"] not in ids

    # cleanup
    for tid in [good["id"], wrong_status["id"], wrong_project["id"], missing_tag["id"], wrong_search["id"]]:
        client.delete(f"/api/v1/tasks/{tid}")
    client.delete(f"/api/v1/projects/{proj['id']}")
