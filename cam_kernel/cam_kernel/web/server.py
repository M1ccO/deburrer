"""FastAPI server for the CAM kernel web UI.

Routes:
  GET  /                       — main page
  POST /api/jobs               — create job from feature JSON
  POST /api/jobs/{id}/model    — upload STL 3D model
  GET  /api/jobs/{id}/model_data — STL mesh data for viewer
  POST /api/jobs/{id}/fixture  — upload fixture STL for collision checks
  POST /api/jobs/{id}/stock    — upload stock STL for material removal
  POST /api/jobs/{id}/step     — load STEP file via OCCT, extract features
  POST /api/jobs/{id}/tool     — configure tool
  POST /api/jobs/{id}/op       — configure operation
  POST /api/jobs/{id}/calc     — run pipeline
  GET  /api/jobs/{id}/preview  — preview payload JSON
  GET  /api/jobs/{id}/nc       — NC output
  GET  /api/jobs/{id}/status   — job status
"""

from __future__ import annotations

import io
import json
import traceback
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from .session import get_store, JobSession

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="CAM Kernel", version="0.1.0")
store = get_store()


@app.exception_handler(Exception)
async def unhandled_exception(_request: Request, exc: Exception):
    """Keep API failures machine-readable instead of returning plain text."""
    traceback.print_exception(type(exc), exc, exc.__traceback__)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error: {}".format(exc),
            "error_type": type(exc).__name__,
        },
    )


@app.get("/", response_class=HTMLResponse)
async def index():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.post("/api/jobs")
async def create_job(file: UploadFile = File(...)):
    """Create a new job session from an uploaded file.

    Accepts JSON feature files or STEP/STL files. For non-JSON files,
    just creates a session — the client uploads to the specific
    endpoint (e.g. /step) afterward.
    """
    filename = (file.filename or "").lower()
    ext = filename.split(".")[-1] if "." in filename else ""

    if ext == "json":
        try:
            content = await file.read()
            feature = json.loads(content)
        except json.JSONDecodeError as e:
            raise HTTPException(400, f"Invalid JSON: {e}")
        except Exception as e:
            raise HTTPException(400, f"Failed to read file: {e}")

        session = store.create()
        session.feature_json = feature
        session.status = "feature_loaded"
        feature_info = _extract_feature_info(feature)
        return JSONResponse({
            "id": session.id,
            "status": session.status,
            "feature": feature_info,
        })

    if ext in ("step", "stp", "stl"):
        session = store.create()
        return JSONResponse({
            "id": session.id,
            "status": "created",
            "hint": f"Use /api/jobs/{session.id}/{ext} to upload the file",
        })

    raise HTTPException(400, f"Unsupported file extension: {ext}")


@app.post("/api/jobs/{session_id}/model")
async def upload_model(session_id: str, file: UploadFile = File(...)):
    session = _get_session(session_id)
    filename = (file.filename or "").lower()

    if filename.endswith(".stl"):
        content = await file.read()
        triangles, normals = _parse_stl_binary(content)
        vertices, indices = _triangles_to_flat(triangles)
        session.model_data = {
            "format": "stl",
            "vertices": vertices,
            "normals": normals,
            "indices": indices,
            "triangle_count": len(triangles),
        }
        session.status = "model_loaded"
        return JSONResponse({
            "id": session_id,
            "status": session.status,
            "format": "stl",
            "triangle_count": len(triangles),
        })
    elif filename.endswith(".stp") or filename.endswith(".step"):
        raise HTTPException(400, "STEP files require OCCT (cadquery-ocp). Use STL for now, or extract features via FreeCAD and upload the JSON file.")
    else:
        raise HTTPException(400, "Unsupported format. Upload .stl, .step, or feature .json")


@app.post("/api/jobs/{session_id}/fixture")
async def upload_fixture(session_id: str, file: UploadFile = File(...)):
    """Upload a fixture STL for collision checking."""
    session = _get_session(session_id)
    filename = (file.filename or "").lower()
    if not filename.endswith(".stl"):
        raise HTTPException(400, "Fixture upload supports .stl files only")
    content = await file.read()
    triangles, normals = _parse_stl_binary(content)
    vertices, indices = _triangles_to_flat(triangles)
    session.fixture_data = {
        "format": "stl",
        "filename": file.filename,
        "vertices": vertices,
        "normals": normals,
        "indices": indices,
        "triangle_count": len(triangles),
    }
    session.status = "fixture_loaded"
    return JSONResponse({
        "id": session_id,
        "status": session.status,
        "fixture": {
            "filename": file.filename,
            "triangle_count": len(triangles),
        },
    })


@app.post("/api/jobs/{session_id}/stock")
async def upload_stock(session_id: str, file: UploadFile = File(...)):
    """Upload a stock STL for material removal simulation."""
    session = _get_session(session_id)
    filename = (file.filename or "").lower()
    if not filename.endswith(".stl"):
        raise HTTPException(400, "Stock upload supports .stl files only")
    content = await file.read()
    triangles, normals = _parse_stl_binary(content)
    vertices, indices = _triangles_to_flat(triangles)
    session.stock_data = {
        "format": "stl",
        "filename": file.filename,
        "vertices": vertices,
        "normals": normals,
        "indices": indices,
        "triangle_count": len(triangles),
    }
    session.status = "stock_loaded"
    return JSONResponse({
        "id": session_id,
        "status": session.status,
        "stock": {
            "filename": file.filename,
            "triangle_count": len(triangles),
        },
    })


@app.post("/api/jobs/{session_id}/step")
async def upload_step_extract(session_id: str, file: UploadFile = File(...)):
    """Load a STEP file via OCCT and extract edge deburr features."""
    session = _get_session(session_id)
    content = await file.read()

    import tempfile, os
    fd, tmppath = tempfile.mkstemp(suffix=".step")
    try:
        with os.fdopen(fd, "wb") as temporary_file:
            temporary_file.write(content)

        try:
            import sys
            from pathlib import Path
            root = Path(__file__).resolve().parent.parent.parent.parent
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
        except Exception:
            pass

        from cam_kernel.cam_kernel.geometry.occt_session import OcctSession
        from cam_kernel.cam_kernel.geometry.feature_extract import (
            sample_edge_chain_from_shape,
            topology_selection_payload,
        )
        from cam_kernel.cam_kernel.geometry.tessellation_cache import (
            tessellate_selectable_flat,
        )

        with OcctSession() as sess:
            shape = sess.load_step(tmppath)

            total_faces = shape.face_count

            vflat, nflat, iflat, triangle_faces = tessellate_selectable_flat(
                shape,
                tolerance_mm=0.1,
            )
            topology = topology_selection_payload(shape)
            session.model_data = {
                "format": "step_tessellated",
                "vertices": vflat,
                "normals": nflat,
                "indices": iflat,
                "triangle_face_indices": triangle_faces,
                "triangle_count": len(iflat) // 3,
                "topology": topology,
            }
            session.step_content = content
            session.step_filename = file.filename or "step_import.step"

            # Try each face and pick the first one that passes feature validation
            best_samples = None
            best_face = 0
            best_error = None
            for fi in range(total_faces):
                try:
                    samples = sample_edge_chain_from_shape(shape, spacing=0.5, face_index=fi)
                    if samples.sample_count < 3:
                        continue

                    # Quick validation check
                    from fc_deburr.geometry.vectors import normalize
                    issues = 0
                    for s in samples.samples:
                        try:
                            normalize(s.tangent)
                            normalize(s.guide_normal)
                            normalize(s.other_normal)
                        except Exception:
                            issues += 1
                    if issues > 0:
                        continue

                    best_samples = samples
                    best_face = fi
                    break
                except Exception as e:
                    best_error = str(e)
                    continue

            if best_samples is None:
                # Fallback to first face
                best_samples = sample_edge_chain_from_shape(shape, spacing=0.5, face_index=0)
                best_face = 0

            feature_id = (file.filename or "step_import").replace(
                ".step",
                "",
            ).replace(".stp", "")
            session.feature_json = _feature_document_from_samples(
                best_samples,
                feature_id=feature_id,
                source_object_id=file.filename or "",
                guide_face_id=topology["faces"][best_face]["id"],
            )
            session.status = "feature_loaded"
            session.topology_selection = {
                "kind": "face",
                "face_index": best_face,
            }

            return JSONResponse({
                "id": session_id,
                "status": session.status,
                "feature": {
                    "type": "wire",
                    "id": file.filename,
                    "closed": best_samples.closed,
                    "sample_count": best_samples.sample_count,
                    "center": list(best_samples.center_xyz) if best_samples.center_xyz else None,
                    "face_index": best_face,
                    "total_faces": total_faces,
                },
                "topology": {
                    "face_count": len(topology["faces"]),
                    "edge_count": len(topology["edges"]),
                    "selection_mode": "face",
                },
            })
    except ModuleNotFoundError as exc:
        if exc.name == "OCP" or (exc.name and exc.name.startswith("OCP.")):
            raise HTTPException(
                503,
                "STEP import requires the cadquery-ocp package in the Python "
                "environment running the web UI. Install it with "
                "'python -m pip install \"cadquery-ocp>=7.7\"' and restart "
                "the server.",
            ) from exc
        raise
    except HTTPException:
        raise
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(
            422,
            "STEP import failed: {}".format(exc),
        ) from exc
    finally:
        try:
            os.unlink(tmppath)
        except Exception:
            pass


@app.post("/api/jobs/{session_id}/selection")
async def select_step_feature(session_id: str, request: Request):
    """Replace the active feature with an explicitly selected STEP face/edge."""
    session = _get_session(session_id)
    if not session.step_content or not session.model_data:
        raise HTTPException(400, "This session has no STEP topology to select.")
    body = await request.json()
    kind = str(body.get("kind", "")).lower()
    spacing = float(body.get("spacing", 0.5))
    if spacing <= 0.0:
        raise HTTPException(400, "Selection sample spacing must be positive.")

    import os
    import tempfile

    fd, tmppath = tempfile.mkstemp(suffix=".step")
    try:
        with os.fdopen(fd, "wb") as temporary_file:
            temporary_file.write(session.step_content)
        from cam_kernel.cam_kernel.geometry.occt_session import OcctSession
        from cam_kernel.cam_kernel.geometry.feature_extract import (
            sample_edge_chain_from_shape,
            sample_selected_edges_from_shape,
        )

        with OcctSession() as occt_session:
            shape = occt_session.load_step(tmppath)
            if kind == "face":
                face_index = int(body.get("face_index", -1))
                face_count = len(
                    session.model_data.get("topology", {}).get("faces", ())
                )
                if face_index < 0 or face_index >= face_count:
                    raise HTTPException(400, "Select one valid model face.")
                samples = sample_edge_chain_from_shape(
                    shape,
                    spacing=spacing,
                    face_index=face_index,
                )
                face_info = session.model_data["topology"]["faces"][face_index]
                feature_id = "face_{}_boundary".format(face_index)
                guide_face_id = face_info["id"]
                selection = {
                    "kind": "face",
                    "face_index": face_index,
                    "face_id": face_info["id"],
                    "surface_type": face_info["surface_type"],
                    "area": face_info["area"],
                }
            elif kind == "edge":
                edge_ids = tuple(str(value) for value in body.get("edge_ids", ()))
                if not edge_ids:
                    raise HTTPException(400, "Select at least one model edge.")
                samples = sample_selected_edges_from_shape(
                    shape,
                    edge_ids,
                    spacing=spacing,
                )
                feature_id = "selected_edges"
                guide_face_id = ""
                selection = {
                    "kind": "edge",
                    "edge_ids": list(edge_ids),
                }
            else:
                raise HTTPException(400, "Selection kind must be face or edge.")

        if samples.sample_count < 2:
            raise HTTPException(422, "Selected topology produced too few samples.")
        session.feature_json = _feature_document_from_samples(
            samples,
            feature_id=feature_id,
            source_object_id=session.step_filename,
            guide_face_id=guide_face_id,
        )
        session.pipeline_result = None
        session.preview_json = None
        session.nc_output = None
        session.topology_selection = selection
        session.status = "feature_selected"
        return JSONResponse(
            {
                "id": session.id,
                "status": session.status,
                "selection": selection,
                "feature": _extract_feature_info(session.feature_json),
            }
        )
    except HTTPException:
        raise
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(422, "Feature selection failed: {}".format(exc)) from exc
    finally:
        try:
            os.unlink(tmppath)
        except OSError:
            pass


@app.get("/api/jobs/{session_id}/model_data")
async def get_model_data(session_id: str):
    session = _get_session(session_id)
    if not session.model_data:
        raise HTTPException(404, "No model uploaded")
    return JSONResponse(session.model_data)


@app.post("/api/jobs/{session_id}/tool")
async def configure_tool(session_id: str, request: Request):
    session = _get_session(session_id)
    body = await request.json()
    session.tool_json = body
    session.status = "tool_configured"
    return JSONResponse({"id": session_id, "status": session.status, "tool": body})


@app.post("/api/jobs/{session_id}/op")
async def configure_operation(session_id: str, request: Request):
    session = _get_session(session_id)
    body = await request.json()
    if (
        str(body.get("motion_mode", "indexed_3_plus_2"))
        == "indexed_3_plus_2"
        and str((session.tool_json or {}).get("kind", "ball")) == "ball"
    ):
        body["lead_deg"] = 0.0
        body["tilt_deg"] = 0.0
    session.operation_json = body
    session.status = "operation_configured"
    return JSONResponse({"id": session_id, "status": session.status, "operation": body})


@app.post("/api/jobs/{session_id}/calc")
async def calculate(session_id: str, request: Request):
    session = _get_session(session_id)
    if not session.feature_json:
        raise HTTPException(400, "No feature data loaded")
    if not session.tool_json:
        raise HTTPException(400, "No tool configured")

    op_json = dict(session.operation_json or {})
    try:
        body = await request.json()
        for k, v in body.items():
            if v or k not in op_json:
                op_json[k] = v
    except Exception:
        pass

    try:
        if str(op_json.get("operation_type", "edge")).lower() == "face":
            selection = session.topology_selection or {}
            if selection.get("kind") != "face":
                raise ValueError(
                    "Face finishing requires one model face selected in the viewer."
                )
            result = _run_occt_face_pipeline(
                session,
                session.tool_json,
                op_json,
            )
        else:
            result = _run_pipeline(
                session.feature_json,
                session.tool_json,
                op_json,
                model_data=session.model_data,
            )
        session.pipeline_result = result
        session.preview_json = result.get("preview_json")
        session.nc_output = result.get("nc_output")
        session.status = "calculated"
        session.errors = result.get("errors", [])

        collision_status = _run_collision_checks(session, result)
        if collision_status is not None:
            session.collision_status = collision_status

        return JSONResponse({
            "id": session_id,
            "status": session.status,
            "has_preview": session.preview_json is not None,
            "has_nc": session.nc_output is not None,
            "metrics": result.get("metrics"),
            "errors": session.errors,
            "collision": collision_status,
        })
    except Exception as e:
        session.status = "error"
        session.errors = [str(e), traceback.format_exc()]
        import logging
        logging.getLogger("cam_kernel").error("Pipeline failed: %s", traceback.format_exc())
        raise HTTPException(500, str(e))


@app.get("/api/jobs/{session_id}/preview")
async def get_preview(session_id: str):
    session = _get_session(session_id)
    if not session.preview_json:
        raise HTTPException(404, "No preview available — run calculate first")
    return JSONResponse(json.loads(session.preview_json))


@app.get("/api/jobs/{session_id}/nc", response_class=PlainTextResponse)
async def get_nc(session_id: str):
    session = _get_session(session_id)
    if not session.nc_output:
        raise HTTPException(404, "No NC output — run calculate first")
    return session.nc_output


@app.get("/api/jobs/{session_id}/status")
async def get_status(session_id: str):
    session = _get_session(session_id)
    return JSONResponse({
        "id": session.id,
        "status": session.status,
        "errors": session.errors,
    })


def _get_session(session_id: str) -> JobSession:
    session = store.get(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")
    return session


def _extract_feature_info(feature: dict) -> dict:
    """Extract summary info from a feature JSON for display."""
    data = feature.get("feature_loop", feature)
    info = {
        "type": data.get("source_kind", "unknown"),
        "id": data.get("id", "unknown"),
        "closed": data.get("closed", False),
    }
    if "samples" in data:
        info["sample_count"] = len(data["samples"])
    if "center_xyz" in data:
        info["center"] = data["center_xyz"]
    if data.get("source_kind") == "face":
        if "patches" in data:
            info["patch_count"] = len(data["patches"])
    return info


def _feature_document_from_samples(
    samples,
    feature_id: str,
    source_object_id: str,
    guide_face_id: str = "",
) -> dict:
    return {
        "schema": "fc_deburr.feature_loop",
        "schema_version": 1,
        "feature_loop": {
            "id": feature_id,
            "samples": [
                {
                    "position": list(sample.position),
                    "tangent": list(sample.tangent),
                    "guide_normal": list(sample.guide_normal),
                    "other_normal": list(sample.other_normal),
                    "source_edge_id": sample.edge_id,
                }
                for sample in samples.samples
            ],
            "closed": samples.closed,
            "source_kind": "wire",
            "center_xyz": (
                list(samples.center_xyz)
                if samples.center_xyz
                else [0.0, 0.0, 0.0]
            ),
            "source_object_id": source_object_id,
            "source_edge_ids": sorted(
                {sample.edge_id for sample in samples.samples}
            ),
            "guide_face_id": guide_face_id,
            "c0_vertex_id": "",
            "reversed_from_selection": False,
        },
    }


def _run_pipeline(
    feature_json: dict,
    tool_json: dict,
    op_json: dict,
    model_data: Optional[dict] = None,
) -> dict:
    """Run the deburring pipeline and return results.

    Uses the existing fc_deburr.application.pipeline module.
    """
    from fc_deburr.application.pipeline import calculate_toolpath
    from fc_deburr.application.job_metrics import estimate_job, format_metrics
    from fc_deburr.domain.models import (
        CutDirection,
        MotionMode,
        Operation,
        ToolDefinition,
        ToolKind,
    )
    from fc_deburr.domain.serialization import feature_loop_from_document, face_region_from_document
    from fc_deburr.machine.profiles import MachineProfile

    schema = feature_json.get("schema", "")
    if schema == "fc_deburr.face_region":
        doc = face_region_from_document(feature_json)
        return _run_face_pipeline(doc, tool_json, op_json)

    feature = feature_loop_from_document(feature_json)

    tool = ToolDefinition(
        id=tool_json.get("id", "web_tool"),
        kind=ToolKind(tool_json.get("kind", "ball")),
        diameter=float(tool_json.get("diameter", 6.0)),
        stickout=float(tool_json.get("stickout", 30.0)),
        cutting_length=float(tool_json.get("cutting_length", 12.0)),
        included_angle_deg=_opt_float(tool_json, "included_angle_deg"),
        tip_flat_diameter=float(tool_json.get("tip_flat_diameter", 0.2)),
        tip_radius=float(tool_json.get("tip_radius", 3.0)),
        contact_radius=_opt_float(tool_json, "contact_radius"),
        radial_correction=float(tool_json.get("radial_correction", 0)),
        axial_correction=float(tool_json.get("axial_correction", 0)),
    )

    motion_mode = MotionMode(op_json.get("motion_mode", "indexed_3_plus_2"))
    auto_index = op_json.get("auto_index", True)

    op = Operation(
        id=op_json.get("id", "web_op"),
        tool_id=tool.id,
        target_width=_opt_float(op_json, "target_width"),
        ball_break_width=_opt_float(op_json, "ball_break_width"),
        ball_engagement=_opt_float(op_json, "ball_engagement"),
        feed=float(op_json.get("feed", 800.0)),
        lead_deg=float(op_json.get("lead_deg", 0.0)),
        tilt_deg=float(op_json.get("tilt_deg", 0.0)),
        lead_in_length=float(op_json.get("lead_in_length", 2.0)),
        lead_out_length=float(op_json.get("lead_out_length", 2.0)),
        safety_lift=float(op_json.get("safety_lift", 3.0)),
        flip_side=bool(op_json.get("flip_side", False)),
        motion_mode=motion_mode,
        auto_index=auto_index,
        indexed_b_deg=_opt_float(op_json, "indexed_b_deg"),
        indexed_c_deg=_opt_float(op_json, "indexed_c_deg"),
        cut_direction=CutDirection(
            op_json.get("cut_direction", "forward")
        ),
        spring_passes=int(op_json.get("spring_passes", 0)),
        spring_feed_fraction=float(
            op_json.get("spring_feed_fraction", 0.5)
        ),
    )

    profile = MachineProfile()

    result = calculate_toolpath(feature, tool, op, profile)

    metrics = estimate_job(feature, result.machine_path, profile, model_path=result.model_path)
    metrics_text = format_metrics(metrics, profile)

    preview_json = _build_preview_json(
        feature,
        result,
        tool,
        profile,
        occt_mesh=model_data,
    )

    nc_output = ""
    if result.machine_path:
        from fc_deburr.machine.post_ntx import post_ntx_tcp, NtxPostSettings
        spindle_val = op_json.get("spindle_speed")
        if spindle_val and int(spindle_val) > 0:
            spindle_speed = int(spindle_val)
        else:
            spindle_speed = None

        settings = NtxPostSettings(
            program_number=int(op_json.get("program_number", 1000)),
            tool_code=str(op_json.get("tool_code", "T01")),
            work_offset=str(op_json.get("work_offset", "G54")),
            h_offset=int(op_json.get("h_offset", 1)),
            tcp_d=int(op_json.get("tcp_d", 9)),
            spindle_speed=spindle_speed,
            spindle_direction=op_json.get("spindle_direction", "M03"),
            coolant_on=bool(op_json.get("coolant", False)),
        )
        nc_output = post_ntx_tcp(result.machine_path, profile, settings)

    errors = []
    if result.kernel_diagnostics:
        for diag in result.kernel_diagnostics:
            if diag.severity == "error":
                errors.append(diag.message)

    return {
        "preview_json": preview_json,
        "nc_output": nc_output,
        "metrics": metrics_text,
        "errors": errors,
    }


def _run_face_pipeline(doc, tool_json: dict, op_json: dict) -> dict:
    from fc_deburr.application.face_pipeline import calculate_face_toolpath
    from fc_deburr.machine.post_ntx import post_ntx_tcp, NtxPostSettings
    from fc_deburr.machine.profiles import MachineProfile
    from fc_deburr.domain.models import (
        CutDirection,
        FaceRegion,
        FacePatch,
        FeatureSourceKind,
        Operation,
        ToolDefinition,
        ToolKind,
    )

    feature_json = op_json.get("_feature_json", {})
    patches = tuple(
        FacePatch(
            id=p.get("id", ""),
            brep=p.get("brep", ""),
            area=float(p.get("area", 0)),
        )
        for p in feature_json.get("patches", [])
    )
    region = FaceRegion(
        id=doc.id,
        patches=patches,
        center_xyz=doc.center_xyz or (0, 0, 0),
        source_kind=FeatureSourceKind.FACE,
        source_object_id=doc.source_object_id,
    )

    tool = ToolDefinition(
        id=tool_json.get("id", "web_ball"),
        kind=ToolKind.BALL,
        diameter=float(tool_json.get("diameter", 6.0)),
        stickout=float(tool_json.get("stickout", 30.0)),
        cutting_length=float(tool_json.get("cutting_length", 12.0)),
        tip_radius=float(tool_json.get("tip_radius", 3.0)),
    )

    op = Operation(
        id=op_json.get("id", "web_op"),
        tool_id=tool.id,
        ball_engagement=op_json.get("ball_engagement"),
        feed=float(op_json.get("feed", 800.0)),
        safety_lift=float(op_json.get("safety_lift", 3.0)),
        surface_tolerance=float(op_json.get("surface_tolerance", 0.01)),
        path_sample_spacing=float(op_json.get("path_sample_spacing", 0.5)),
        surface_direction=op_json.get("surface_direction", "auto"),
        cut_direction=CutDirection(
            op_json.get("cut_direction", "forward")
        ),
        spring_passes=int(op_json.get("spring_passes", 0)),
        spring_feed_fraction=float(
            op_json.get("spring_feed_fraction", 0.5)
        ),
    )

    profile = MachineProfile()
    result = calculate_face_toolpath(region, tool, op, profile)

    preview_json = None
    try:
        from fc_deburr.preview.builder import build_preview
        from fc_deburr.ui.web_preview.payload import build_json
        face_loop = _face_region_to_loop(region)
        preview_doc = build_preview(face_loop, result, tool=tool, profile=profile)
        preview_json = build_json(preview_doc)
    except Exception:
        preview_json = None

    nc_output = ""
    if result.machine_path:
        spindle_val = op_json.get("spindle_speed")
        spindle_speed = int(spindle_val) if spindle_val and int(spindle_val) > 0 else None
        settings = NtxPostSettings(
            program_number=int(op_json.get("program_number", 1000)),
            tool_code=str(op_json.get("tool_code", "T01")),
            work_offset=str(op_json.get("work_offset", "G54")),
            h_offset=int(op_json.get("h_offset", 1)),
            tcp_d=int(op_json.get("tcp_d", 9)),
            spindle_speed=spindle_speed,
        )
        nc_output = post_ntx_tcp(result.machine_path, profile, settings)

    metrics_text = "Face finishing path computed."
    try:
        from fc_deburr.application.job_metrics import estimate_job, format_metrics
        face_loop = _face_region_to_loop(region)
        m = estimate_job(face_loop, result.machine_path, profile, model_path=result.model_path)
        metrics_text = format_metrics(m, profile)
    except Exception:
        pass

    return {
        "preview_json": preview_json,
        "nc_output": nc_output,
        "metrics": metrics_text,
        "errors": [],
    }


def _run_occt_face_pipeline(session, tool_json: dict, op_json: dict) -> dict:
    """Calculate ball finishing directly from a face picked on an OCP STEP model."""
    import math
    import os
    import tempfile

    from cam_kernel.cam_kernel.geometry.occt_session import OcctSession
    from cam_kernel.cam_kernel.sampling.face_sampler import sample_face_from_shape
    from fc_deburr.application.job_metrics import estimate_job, format_metrics
    from fc_deburr.application.pipeline import PipelineResult
    from fc_deburr.domain.models import (
        CutDirection,
        FeatureLoop,
        FeatureSample,
        FeatureSourceKind,
        MotionKind,
        MotionMode,
        Operation,
        PathPoint,
        ToolDefinition,
        ToolKind,
        Toolpath,
    )
    from fc_deburr.geometry.vectors import (
        add,
        cross,
        normalize,
        rotate_about_axis,
        scale,
        sub,
    )
    from fc_deburr.machine.backends import LegacyNtxKinematicsBackend
    from fc_deburr.machine.post_ntx import NtxPostSettings, post_ntx_tcp
    from fc_deburr.machine.profiles import MachineProfile
    from fc_deburr.machine.validation import validate_machine_path
    from fc_deburr.solver.posture import realize_motion_mode
    from fc_deburr.solver.transforms import apply_spring_passes

    if not session.step_content:
        raise ValueError("The selected face has no retained STEP geometry.")
    if str(tool_json.get("kind", "ball")) != "ball":
        raise ValueError("Face finishing currently requires a ball end mill.")
    diameter = float(tool_json.get("diameter", 6.0))
    radius = diameter * 0.5
    scallop_height = float(op_json.get("surface_tolerance", 0.01))
    if not 0.0 < scallop_height < radius:
        raise ValueError("Surface tolerance must be between zero and ball radius.")
    stepover = 2.0 * math.sqrt(
        2.0 * radius * scallop_height - scallop_height * scallop_height
    )

    face_index = int(session.topology_selection["face_index"])
    fd, tmppath = tempfile.mkstemp(suffix=".step")
    try:
        with os.fdopen(fd, "wb") as temporary_file:
            temporary_file.write(session.step_content)
        with OcctSession() as occt_session:
            shape = occt_session.load_step(tmppath)
            grid = sample_face_from_shape(
                shape,
                face_index=face_index,
                stepover=stepover,
                sample_spacing=float(op_json.get("path_sample_spacing", 0.5)),
                direction=str(op_json.get("surface_direction", "auto")),
            )
    finally:
        try:
            os.unlink(tmppath)
        except OSError:
            pass

    tool = ToolDefinition(
        id=tool_json.get("id", "web_ball"),
        kind=ToolKind.BALL,
        diameter=diameter,
        stickout=float(tool_json.get("stickout", 30.0)),
        cutting_length=float(tool_json.get("cutting_length", 12.0)),
        tip_radius=float(tool_json.get("tip_radius", radius)),
    )
    operation = Operation(
        id=op_json.get("id", "web_face_finish"),
        tool_id=tool.id,
        feed=float(op_json.get("feed", 800.0)),
        safety_lift=float(op_json.get("safety_lift", 3.0)),
        lead_deg=float(op_json.get("lead_deg", 0.0)),
        tilt_deg=float(op_json.get("tilt_deg", 0.0)),
        surface_tolerance=scallop_height,
        path_sample_spacing=float(op_json.get("path_sample_spacing", 0.5)),
        surface_direction=str(op_json.get("surface_direction", "auto")),
        motion_mode=MotionMode(
            op_json.get("motion_mode", "indexed_3_plus_2")
        ),
        auto_index=bool(op_json.get("auto_index", True)),
        indexed_b_deg=_opt_float(op_json, "indexed_b_deg"),
        indexed_c_deg=_opt_float(op_json, "indexed_c_deg"),
        cut_direction=CutDirection(
            op_json.get("cut_direction", "forward")
        ),
        spring_passes=int(op_json.get("spring_passes", 0)),
        spring_feed_fraction=float(
            op_json.get("spring_feed_fraction", 0.5)
        ),
    )

    path_points = []
    preview_samples = []
    for pass_index, original_row in enumerate(grid.samples):
        reverse_pass = bool(pass_index % 2)
        if operation.cut_direction is CutDirection.REVERSE:
            reverse_pass = not reverse_pass
        row = tuple(reversed(original_row)) if reverse_pass else original_row
        cutter_points = []
        for sample_index, sample in enumerate(row):
            previous = row[max(0, sample_index - 1)].position
            following = row[min(len(row) - 1, sample_index + 1)].position
            tangent = normalize(sub(following, previous), "surface pass tangent")
            axis = sample.normal
            side = normalize(cross(tangent, axis), "surface posture side")
            if operation.lead_deg:
                axis = rotate_about_axis(axis, side, operation.lead_deg)
            if operation.tilt_deg:
                axis = rotate_about_axis(axis, tangent, operation.tilt_deg)
            axis = normalize(axis)
            ball_center = add(sample.position, scale(sample.normal, radius))
            tool_tip = sub(ball_center, scale(axis, radius))
            cutter_points.append((tool_tip, sample.position, axis, tangent))
            preview_samples.append(
                FeatureSample(
                    position=sample.position,
                    tangent=tangent,
                    guide_normal=sample.normal,
                    other_normal=sample.normal,
                    source_edge_id=sample.face_id,
                )
            )

        first_tip, first_contact, first_axis, first_tangent = cutter_points[0]
        last_tip, last_contact, last_axis, last_tangent = cutter_points[-1]
        pass_flag = "pass={}".format(pass_index)
        path_points.append(
            PathPoint(
                seq=len(path_points),
                xyz=add(first_tip, scale(first_axis, operation.safety_lift)),
                tool_axis=first_axis,
                motion=MotionKind.RAPID,
                tangent=first_tangent,
                flags=(pass_flag, "safe_start"),
            )
        )
        path_points.append(
            PathPoint(
                seq=len(path_points),
                xyz=first_tip,
                tool_axis=first_axis,
                motion=MotionKind.APPROACH,
                contact_xyz=first_contact,
                tangent=first_tangent,
                feed=operation.feed,
                flags=(pass_flag, "approach"),
            )
        )
        for tool_tip, contact, axis, tangent in cutter_points:
            path_points.append(
                PathPoint(
                    seq=len(path_points),
                    xyz=tool_tip,
                    tool_axis=axis,
                    motion=MotionKind.CUT,
                    contact_xyz=contact,
                    tangent=tangent,
                    feed=operation.feed,
                    flags=(pass_flag, "surface_finish"),
                )
            )
        path_points.append(
            PathPoint(
                seq=len(path_points),
                xyz=add(last_tip, scale(last_axis, operation.safety_lift)),
                tool_axis=last_axis,
                motion=MotionKind.RETRACT,
                tangent=last_tangent,
                flags=(pass_flag, "safe_end"),
            )
        )

    center = tuple(
        sum(sample.position[axis] for sample in preview_samples)
        / len(preview_samples)
        for axis in range(3)
    )
    feature = FeatureLoop(
        id=grid.id,
        samples=tuple(preview_samples),
        closed=False,
        source_kind=FeatureSourceKind.FACE,
        center_xyz=center,
        source_object_id=session.step_filename,
        guide_face_id="face_{}".format(face_index),
    )
    analytic_path = Toolpath(
        feature_id=feature.id,
        operation_id=operation.id,
        tool_id=tool.id,
        points=tuple(path_points),
        warnings=(
            "OCP face finishing: {} passes, {:.4f} mm stepover".format(
                grid.row_count,
                stepover,
            ),
        ),
        source_center_xyz=center,
    )
    profile = MachineProfile()
    realized = realize_motion_mode(analytic_path, tool, operation, profile)
    model_path = apply_spring_passes(realized.path, operation)
    machine_path = LegacyNtxKinematicsBackend().solve_path(
        model_path,
        profile,
        operation.motion_mode,
        realized.indexed_b_deg,
        realized.indexed_c_deg,
    )
    report = validate_machine_path(machine_path, profile)
    if not report.ok:
        raise ValueError(
            "Invalid face-finishing machine path: "
            + "; ".join(issue.message for issue in report.issues)
        )
    result = PipelineResult(
        model_path,
        machine_path,
        report,
        indexed_b_deg=realized.indexed_b_deg,
        indexed_c_deg=realized.indexed_c_deg,
    )
    metrics = estimate_job(
        feature,
        machine_path,
        profile,
        model_path=result.model_path,
    )
    preview_json = _build_preview_json(
        feature,
        result,
        tool,
        profile,
        occt_mesh=session.model_data,
    )
    spindle_value = op_json.get("spindle_speed")
    settings = NtxPostSettings(
        program_number=int(op_json.get("program_number", 1000)),
        tool_code=str(op_json.get("tool_code", "T01")),
        work_offset=str(op_json.get("work_offset", "G54")),
        h_offset=int(op_json.get("h_offset", 1)),
        tcp_d=int(op_json.get("tcp_d", 9)),
        spindle_speed=(
            int(spindle_value)
            if spindle_value and int(spindle_value) > 0
            else None
        ),
        spindle_direction=op_json.get("spindle_direction", "M03"),
        coolant_on=bool(op_json.get("coolant", False)),
    )
    return {
        "preview_json": preview_json,
        "nc_output": post_ntx_tcp(machine_path, profile, settings),
        "metrics": format_metrics(metrics, profile),
        "errors": [],
    }


def _face_region_to_loop(region) -> "FeatureLoop":
    """Convert a FaceRegion to a FeatureLoop for the preview builder."""
    from fc_deburr.domain.models import (
        FeatureLoop,
        FeatureSample,
        FeatureSourceKind,
    )

    samples = []
    for i, patch in enumerate(region.patches):
        if not patch.brep:
            continue
        samples.append(
            FeatureSample(
                position=region.center_xyz,
                tangent=(1.0, 0.0, 0.0),
                guide_normal=(0.0, 1.0, 0.0),
                other_normal=(0.0, 0.0, 1.0),
                source_edge_id=f"patch_{i}",
            )
        )
    return FeatureLoop(
        id=region.id,
        samples=tuple(samples),
        closed=True,
        source_kind=FeatureSourceKind.FACE,
        center_xyz=region.center_xyz,
    )


def _build_preview_json(feature, result, tool, profile,
                        occt_mesh: Optional[dict] = None) -> str:
    """Build a preview payload JSON matching the Three.js viewer format.

    If ``occt_mesh`` is given (a dict with ``vertices``, ``normals``,
    ``indices`` flat float arrays), it is injected as the ``workpiece``
    field so the viewer can render the part in the same group as
    the polylines (which gets the C-axis rotation applied).
    """
    from fc_deburr.preview.builder import build_preview
    from fc_deburr.ui.web_preview.payload import build_payload
    from cam_kernel.cam_kernel.geometry.occt_payload import indexed_mesh_to_triangles

    doc = build_preview(feature, result, tool=tool, profile=profile)
    payload = build_payload(doc)

    if occt_mesh is not None:
        try:
            triangles, normals = indexed_mesh_to_triangles(
                occt_mesh["vertices"],
                occt_mesh["normals"],
                occt_mesh["indices"],
            )
            positions = []
            face_normals = []
            for tri, nrm in zip(triangles, normals):
                for vertex in tri:
                    positions.extend(vertex)
                face_normals.extend(nrm)
                face_normals.extend(nrm)
                face_normals.extend(nrm)
            payload["workpiece"] = {
                "positions": positions,
                "normals": face_normals,
            }
        except Exception as e:
            payload["workpiece"] = None
            import logging
            logging.getLogger("cam_kernel").warning("Failed to inject OCCT mesh into preview: %s", e)
    else:
        payload["workpiece"] = None

    return json.dumps(payload)


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _opt_float(d: dict, key: str):
    val = d.get(key)
    return float(val) if val else None


def _run_collision_checks(session, result) -> Optional[dict]:
    """Run FCL-based gouge and holder collision checks.

    Returns a status dict, or None if collision is unavailable / not run.
    """
    from cam_kernel.collision.fcl_scene import FclScene, make_transform
    from cam_kernel.collision.gouge_checks import (
        GlobalGougeChecker,
        HolderCollisionChecker,
        fcl_available,
    )

    if not fcl_available():
        return {"status": "skipped", "reason": "python-fcl not installed"}

    if not session.model_data or "vertices" not in session.model_data:
        return {"status": "skipped", "reason": "no part model loaded"}

    if not result.machine_path or not result.machine_path.points:
        return {"status": "skipped", "reason": "no machine path"}

    try:
        scene = FclScene()
        part_id = scene.add_mesh(
            session.model_data["vertices"],
            session.model_data["indices"],
            name="part",
            is_static=True,
        )
        fixture_id = None
        if session.fixture_data and "vertices" in session.fixture_data:
            fixture_id = scene.add_mesh(
                session.fixture_data["vertices"],
                session.fixture_data["indices"],
                name="fixture",
                is_static=True,
            )

        cut_points = []
        cut_axes = []
        for pt in result.machine_path.points:
            cut_points.append(pt.xyz_radius)
            if hasattr(pt, "tool_axis") and pt.tool_axis is not None:
                cut_axes.append(pt.tool_axis)
            else:
                cut_axes.append((0.0, 0.0, 1.0))

        tool_kind = (session.tool_json or {}).get("kind", "ball")
        tool_diameter = float((session.tool_json or {}).get("diameter", 6.0))
        tool_radius = tool_diameter * 0.5

        status = {
            "status": "checked",
            "checked_stations": len(cut_points),
            "gouge": None,
            "holder": None,
        }

        with GlobalGougeChecker(scene, part_id, cutter_radius=tool_radius) as chk:
            gouge_report = chk.check_path(cut_points, cut_axes)
            status["gouge"] = {
                "gouge_detected": gouge_report.gouge_detected,
                "max_penetration_mm": gouge_report.max_penetration_mm,
                "diagnosis": gouge_report.diagnosis,
                "offending_station": gouge_report.offending_station,
            }

        holder_dia = max(tool_diameter * 1.8, 20.0)
        with HolderCollisionChecker(
            scene, part_id,
            holder_diameter_mm=holder_dia,
            holder_length_mm=50.0,
        ) as chk:
            coll = chk.check_holder_path(cut_points, cut_axes)
            status["holder"] = {
                "colliding": coll.colliding,
                "penetration_depth": coll.penetration_depth,
            }

        if fixture_id is not None:
            with HolderCollisionChecker(
                scene, fixture_id,
                holder_diameter_mm=holder_dia,
                holder_length_mm=50.0,
            ) as chk:
                fix_coll = chk.check_holder_path(cut_points, cut_axes)
                status["fixture"] = {
                    "colliding": fix_coll.colliding,
                    "penetration_depth": fix_coll.penetration_depth,
                }

        return status
    except Exception as e:
        return {"status": "error", "reason": str(e)}


def _parse_stl_binary(data: bytes):
    import struct

    triangles = []
    normals = []
    offset = 80
    count = struct.unpack_from("<I", data, offset)[0]
    offset += 4
    for _ in range(count):
        normal = struct.unpack_from("<fff", data, offset)
        offset += 12
        points = [struct.unpack_from("<fff", data, offset + i * 12) for i in range(3)]
        offset += 36
        triangles.append(points)
        normals.append(normal)
        offset += 2
    return triangles, normals


def _triangles_to_flat(triangles):
    vertices = []
    indices = []
    seen = {}
    for tri in triangles:
        for pt in tri:
            key = (round(pt[0], 6), round(pt[1], 6), round(pt[2], 6))
            if key not in seen:
                seen[key] = len(vertices)
                vertices.extend(pt)
            indices.append(seen[key])
    return vertices, indices


def main():
    """Launch the web UI server."""
    import os
    import uvicorn
    import webbrowser
    import sys
    from pathlib import Path
    from threading import Timer

    root = Path(__file__).resolve().parent.parent.parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    host = "127.0.0.1"
    port = 8910
    reload_enabled = os.environ.get(
        "CAM_KERNEL_RELOAD",
        "1",
    ).lower() not in ("0", "false", "no")

    def open_browser():
        webbrowser.open(f"http://{host}:{port}")

    Timer(1.0, open_browser).start()
    if reload_enabled:
        uvicorn.run(
            "cam_kernel.cam_kernel.web.server:app",
            host=host,
            port=port,
            log_level="info",
            reload=True,
            reload_dirs=(
                str(root / "fc_deburr"),
                str(root / "cam_kernel" / "cam_kernel"),
            ),
        )
    else:
        uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
