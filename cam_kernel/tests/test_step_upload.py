"""End-to-end test of the STEP upload flow."""
import sys
import os
from pathlib import Path

sys.path.insert(0, '.')

from fastapi.testclient import TestClient
from cam_kernel.cam_kernel.web.server import app


client = TestClient(app)


def test_step_upload_flow():
    """Test the full STEP upload flow that the web UI uses."""
    step_path = Path("cam_kernel/tests/geometry_regression/parts/cylinder.step")
    assert step_path.exists(), f"Test STEP not found: {step_path}"

    # Step 1: Create a session by uploading the STEP file
    with open(step_path, "rb") as f:
        resp1 = client.post(
            "/api/jobs",
            files={"file": ("cylinder.step", f, "application/step")},
        )
    assert resp1.status_code == 200, f"Create session failed: {resp1.status_code} {resp1.text}"
    data1 = resp1.json()
    assert "id" in data1, f"No session id in response: {data1}"
    session_id = data1["id"]
    print(f"  Session ID: {session_id}")

    # Step 2: Upload the STEP to /step endpoint
    with open(step_path, "rb") as f:
        resp2 = client.post(
            f"/api/jobs/{session_id}/step",
            files={"file": ("cylinder.step", f, "application/step")},
        )
    assert resp2.status_code == 200, f"STEP upload failed: {resp2.status_code} {resp2.text}"
    data2 = resp2.json()
    assert data2["status"] == "feature_loaded", f"Bad status: {data2}"
    assert "feature" in data2
    assert data2["feature"]["sample_count"] > 0
    assert data2["topology"]["face_count"] > 0
    assert data2["topology"]["edge_count"] > 0

    model = client.get(f"/api/jobs/{session_id}/model_data")
    assert model.status_code == 200
    model_data = model.json()
    assert len(model_data["triangle_face_indices"]) == model_data["triangle_count"]
    assert len(model_data["topology"]["faces"]) == data2["topology"]["face_count"]
    assert len(model_data["topology"]["edges"]) == data2["topology"]["edge_count"]
    print(f"  Samples: {data2['feature']['sample_count']}")

    planar_face = next(
        face
        for face in model_data["topology"]["faces"]
        if face["surface_type"] == "plane"
    )
    face_response = client.post(
        f"/api/jobs/{session_id}/selection",
        json={"kind": "face", "face_index": planar_face["index"], "spacing": 1.0},
    )
    assert face_response.status_code == 200, face_response.text
    face_data = face_response.json()
    assert face_data["selection"]["kind"] == "face"
    assert face_data["feature"]["sample_count"] >= 2

    tool_response = client.post(
        f"/api/jobs/{session_id}/tool",
        json={
            "id": "ball_6",
            "kind": "ball",
            "diameter": 6.0,
            "stickout": 30.0,
            "cutting_length": 12.0,
            "tip_radius": 3.0,
        },
    )
    assert tool_response.status_code == 200
    operation_response = client.post(
        f"/api/jobs/{session_id}/op",
        json={
            "id": "finish_face",
            "operation_type": "face",
            "motion_mode": "indexed_3_plus_2",
            "feed": 800.0,
            "safety_lift": 3.0,
            "surface_tolerance": 0.05,
            "path_sample_spacing": 2.0,
            "surface_direction": "auto",
        },
    )
    assert operation_response.status_code == 200
    calculate_response = client.post(
        f"/api/jobs/{session_id}/calc",
        json={
            "operation_type": "face",
            "program_number": 1200,
            "tool_code": "T01",
            "work_offset": "G54",
        },
    )
    assert calculate_response.status_code == 200, calculate_response.text
    calculated = calculate_response.json()
    assert calculated["has_preview"]
    assert calculated["has_nc"]

    edge_id = model_data["topology"]["edges"][0]["id"]
    edge_response = client.post(
        f"/api/jobs/{session_id}/selection",
        json={"kind": "edge", "edge_ids": [edge_id], "spacing": 1.0},
    )
    assert edge_response.status_code == 200, edge_response.text
    edge_data = edge_response.json()
    assert edge_data["selection"]["edge_ids"] == [edge_id]
    assert edge_data["feature"]["sample_count"] >= 2


def test_json_upload_flow():
    """Test the JSON feature upload flow."""
    from fc_deburr.domain.serialization import feature_loop_to_document
    from fc_deburr.domain.models import FeatureLoop, FeatureSample, FeatureSourceKind
    import json
    import tempfile

    feature = FeatureLoop(
        id="test",
        samples=(
            FeatureSample(position=(0, 0, 0), tangent=(1, 0, 0),
                          guide_normal=(0, 1, 0), other_normal=(0, 0, 1)),
            FeatureSample(position=(10, 0, 0), tangent=(1, 0, 0),
                          guide_normal=(0, 1, 0), other_normal=(0, 0, 1)),
            FeatureSample(position=(10, 10, 0), tangent=(0, 1, 0),
                          guide_normal=(-1, 0, 0), other_normal=(0, 0, 1)),
        ),
        closed=True,
        source_kind=FeatureSourceKind.WIRE,
    )
    doc = feature_loop_to_document(feature)

    resp = client.post(
        "/api/jobs",
        files={"file": ("test.json", json.dumps(doc).encode(), "application/json")},
    )
    assert resp.status_code == 200, f"JSON upload failed: {resp.status_code} {resp.text}"
    data = resp.json()
    assert "id" in data
    assert "feature" in data
    assert data["feature"]["sample_count"] == 3
    print(f"  Session ID: {data['id']}, samples: {data['feature']['sample_count']}")


def test_invalid_step_returns_structured_error():
    """Backend import failures must stay JSON-readable for the browser."""
    resp1 = client.post(
        "/api/jobs",
        files={"file": ("broken.step", b"not a STEP file", "application/step")},
    )
    assert resp1.status_code == 200
    session_id = resp1.json()["id"]

    resp2 = client.post(
        f"/api/jobs/{session_id}/step",
        files={"file": ("broken.step", b"not a STEP file", "application/step")},
    )
    assert resp2.status_code == 422
    assert resp2.headers["content-type"].startswith("application/json")
    assert resp2.json()["detail"].startswith("STEP import failed:")


def test_open_step_edge_calculates_an_indexed_deburr_path():
    step_path = Path("cam_kernel/tests/geometry_regression/parts/box.step")
    with open(step_path, "rb") as step_file:
        create_response = client.post(
            "/api/jobs",
            files={"file": ("box.step", step_file, "application/step")},
        )
    session_id = create_response.json()["id"]

    with open(step_path, "rb") as step_file:
        upload_response = client.post(
            f"/api/jobs/{session_id}/step",
            files={"file": ("box.step", step_file, "application/step")},
        )
    assert upload_response.status_code == 200

    model_data = client.get(f"/api/jobs/{session_id}/model_data").json()
    edge_id = model_data["topology"]["edges"][0]["id"]
    selection_response = client.post(
        f"/api/jobs/{session_id}/selection",
        json={"kind": "edge", "edge_ids": [edge_id], "spacing": 1.0},
    )
    assert selection_response.status_code == 200, selection_response.text
    assert selection_response.json()["feature"]["closed"] is False

    client.post(
        f"/api/jobs/{session_id}/tool",
        json={
            "id": "ball_6",
            "kind": "ball",
            "diameter": 6.0,
            "stickout": 30.0,
            "cutting_length": 12.0,
            "tip_radius": 3.0,
        },
    )
    client.post(
        f"/api/jobs/{session_id}/op",
        json={
            "id": "deburr_open",
            "operation_type": "edge",
            "motion_mode": "indexed_3_plus_2",
            "ball_engagement": 0.25,
            "feed": 800.0,
            "safety_lift": 3.0,
        },
    )
    calculate_response = client.post(
        f"/api/jobs/{session_id}/calc",
        json={
            "operation_type": "edge",
            "program_number": 1201,
            "tool_code": "T01",
            "work_offset": "G54",
        },
    )

    assert calculate_response.status_code == 200, calculate_response.text
    assert calculate_response.json()["has_preview"]
    assert calculate_response.json()["has_nc"]


def test_unsupported_extension():
    """Test that unsupported file extensions are rejected."""
    resp = client.post(
        "/api/jobs",
        files={"file": ("test.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 400
    print(f"  Correctly rejected .txt: {resp.json()}")
