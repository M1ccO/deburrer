from __future__ import annotations

import json
from dataclasses import asdict
from enum import Enum
from pathlib import Path
from typing import Any, Dict

from .models import (
    FacePatch,
    FaceRegion,
    FeatureLoop,
    FeatureSample,
    FeatureSourceKind,
)

SCHEMA_VERSION = 1


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    return value


def feature_loop_to_document(loop: FeatureLoop) -> Dict[str, Any]:
    return {
        "schema": "fc_deburr.feature_loop",
        "schema_version": SCHEMA_VERSION,
        "feature_loop": _json_value(asdict(loop)),
    }


def feature_loop_from_document(document: Dict[str, Any]) -> FeatureLoop:
    if document.get("schema") != "fc_deburr.feature_loop":
        raise ValueError("Not an fc_deburr feature-loop document")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported feature-loop schema version")

    data = document.get("feature_loop")
    if not isinstance(data, dict):
        raise ValueError("Missing feature_loop object")
    samples_data = data.get("samples")
    if not isinstance(samples_data, list) or len(samples_data) < 3:
        raise ValueError("A feature loop requires at least three samples")

    samples = tuple(
        FeatureSample(
            position=_vec(item, "position"),
            tangent=_vec(item, "tangent"),
            guide_normal=_vec(item, "guide_normal"),
            other_normal=_vec(item, "other_normal"),
            source_edge_id=str(item.get("source_edge_id", "")),
        )
        for item in samples_data
    )
    return FeatureLoop(
        id=str(data["id"]),
        samples=samples,
        closed=bool(data["closed"]),
        source_kind=FeatureSourceKind(data.get("source_kind", "wire")),
        center_xyz=(
            _vec(data, "center_xyz")
            if data.get("center_xyz") is not None
            else None
        ),
        source_object_id=str(data.get("source_object_id", "")),
        source_edge_ids=tuple(str(v) for v in data.get("source_edge_ids", [])),
        guide_face_id=str(data.get("guide_face_id", "")),
        c0_vertex_id=str(data.get("c0_vertex_id", "")),
        reversed_from_selection=bool(data.get("reversed_from_selection", False)),
    )


def save_feature_loop(path: str | Path, loop: FeatureLoop) -> None:
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(feature_loop_to_document(loop), stream, indent=2)


def load_feature_loop(path: str | Path) -> FeatureLoop:
    with open(path, encoding="utf-8") as stream:
        return feature_loop_from_document(json.load(stream))


def face_region_to_document(region: FaceRegion) -> Dict[str, Any]:
    return {
        "schema": "fc_deburr.face_region",
        "schema_version": SCHEMA_VERSION,
        "face_region": _json_value(asdict(region)),
    }


def face_region_from_document(document: Dict[str, Any]) -> FaceRegion:
    if document.get("schema") != "fc_deburr.face_region":
        raise ValueError("Not an fc_deburr face-region document")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported face-region schema version")
    data = document.get("face_region")
    if not isinstance(data, dict):
        raise ValueError("Missing face_region object")
    patches_data = data.get("patches")
    if not isinstance(patches_data, list) or not patches_data:
        raise ValueError("A face region requires at least one face patch")
    return FaceRegion(
        id=str(data["id"]),
        patches=tuple(
            FacePatch(
                id=str(patch["id"]),
                brep=str(patch["brep"]),
                area=float(patch["area"]),
            )
            for patch in patches_data
        ),
        center_xyz=_vec(data, "center_xyz"),
        source_object_id=str(data.get("source_object_id", "")),
    )


def save_face_region(path: str | Path, region: FaceRegion) -> None:
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(face_region_to_document(region), stream, indent=2)


def load_feature(path: str | Path):
    with open(path, encoding="utf-8") as stream:
        document = json.load(stream)
    if document.get("schema") == "fc_deburr.feature_loop":
        return feature_loop_from_document(document)
    if document.get("schema") == "fc_deburr.face_region":
        return face_region_from_document(document)
    raise ValueError("Unsupported fc_deburr feature document")


def _vec(item: Dict[str, Any], key: str):
    value = item.get(key)
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError("%s must contain three numbers" % key)
    return tuple(float(component) for component in value)
