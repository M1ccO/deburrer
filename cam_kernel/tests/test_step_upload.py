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
    print(f"  Samples: {data2['feature']['sample_count']}")


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


def test_unsupported_extension():
    """Test that unsupported file extensions are rejected."""
    resp = client.post(
        "/api/jobs",
        files={"file": ("test.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 400
    print(f"  Correctly rejected .txt: {resp.json()}")
