from __future__ import annotations

from ..application.pipeline import PipelineResult
from ..domain.models import (
    FaceRegion,
    FeatureLoop,
    MotionKind,
    ToolDefinition,
)
from ..geometry.vectors import add, scale
from ..machine.kinematics import (
    axis_machine_from_b,
    axis_model_from_bc,
    machine_to_model,
)
from ..machine.profiles import MachineProfile
from .models import (
    PreviewDocument,
    PreviewMarker,
    PreviewPolyline,
    PreviewToolGeometry,
    PreviewToolPose,
    PreviewVector,
)


def build_preview(
    feature: FeatureLoop,
    result: PipelineResult,
    axis_length: float = 2.0,
    vector_stride: int = 4,
    tool: ToolDefinition | None = None,
    profile: MachineProfile | None = None,
) -> PreviewDocument:
    """Build immutable renderer input without giving a widget solver ownership."""

    source = PreviewPolyline(
        name="Source edge",
        points=tuple(sample.position for sample in feature.samples),
        color="#00d7ff",
        closed=feature.closed,
    )
    contacts = PreviewPolyline(
        name="Cutter contact",
        points=tuple(
            point.contact_xyz
            for point in result.model_path.points
            if point.motion is MotionKind.CUT and point.contact_xyz is not None
        ),
        color="#65e572",
        closed=True,
    )
    target_a = PreviewPolyline(
        name="Guide-face boundary",
        points=tuple(
            point.target_a_xyz
            for point in result.model_path.points
            if point.motion is MotionKind.CUT and point.target_a_xyz is not None
        ),
        color="#43e0a3",
        closed=True,
    )
    target_b = PreviewPolyline(
        name="Other-face boundary",
        points=tuple(
            point.target_b_xyz
            for point in result.model_path.points
            if point.motion is MotionKind.CUT and point.target_b_xyz is not None
        ),
        color="#9bef5b",
        closed=True,
    )
    cut = PreviewPolyline(
        name="Cutter reference",
        points=tuple(
            point.xyz
            for point in result.model_path.points
            if point.motion is MotionKind.CUT
        ),
        color="#ffd23f",
        closed=False,
    )
    first_cut_index = next(
        index
        for index, point in enumerate(result.model_path.points)
        if point.motion is MotionKind.CUT
    )
    last_cut_index = max(
        index
        for index, point in enumerate(result.model_path.points)
        if point.motion is MotionKind.CUT
    )
    approach = PreviewPolyline(
        name="Approach",
        points=tuple(
            point.xyz
            for point in result.model_path.points[: first_cut_index + 1]
        ),
        color="#ff6868",
        dashed=True,
    )
    retract = PreviewPolyline(
        name="Retract",
        points=tuple(
            point.xyz
            for point in result.model_path.points[last_cut_index:]
        ),
        color="#ff6868",
        dashed=True,
    )
    cut_points = tuple(
        point
        for point in result.model_path.points
        if point.motion is MotionKind.CUT
    )
    stride = max(1, vector_stride)
    profile = profile or MachineProfile()
    poses = _machine_poses(result, profile)
    cut_poses = tuple(
        pose for pose in poses if pose.motion is MotionKind.CUT
    )
    axis_vectors = tuple(
        PreviewVector(
            start=pose.cutter_reference,
            end=add(
                pose.cutter_reference,
                scale(pose.tool_axis_b_only, axis_length),
            ),
            color="#b58cff",
        )
        for pose in cut_poses
    )
    direction = PreviewVector(
        start=feature.samples[0].position,
        end=feature.samples[1].position,
        color="#ffffff",
    )
    markers = [
        PreviewMarker("C0 / start", feature.samples[0].position, "#ffffff"),
    ]
    if feature.center_xyz is not None:
        markers.append(
            PreviewMarker("Wire center", feature.center_xyz, "#57a8ff")
        )
    return PreviewDocument(
        polylines=(source, target_a, target_b, contacts, cut, approach, retract),
        vectors=(direction,) + axis_vectors,
        markers=tuple(markers),
        b_values=tuple(point.b_deg for point in result.machine_path.points),
        c_values=tuple(point.c_deg for point in result.machine_path.points),
        warnings=result.machine_path.warnings,
        tool=_preview_tool(tool),
        tool_poses=poses,
        spindle_origin=profile.workpiece.origin_xyz,
        spindle_axis=profile.workpiece.spindle_axis,
    )


def build_face_preview(
    region: FaceRegion,
    result: PipelineResult,
    axis_length: float = 2.0,
    vector_stride: int = 8,
    tool: ToolDefinition | None = None,
    profile: MachineProfile | None = None,
) -> PreviewDocument:
    try:
        import Part
    except ImportError as error:
        raise RuntimeError("Face preview requires FreeCAD Python") from error

    polylines = []
    for patch in region.patches:
        shape = Part.Shape()
        shape.importBrepFromString(patch.brep)
        face = shape.Faces[0]
        for edge in face.Edges:
            points = tuple(
                (float(point.x), float(point.y), float(point.z))
                for point in edge.discretize(Number=40)
            )
            polylines.append(
                PreviewPolyline(
                    name="%s boundary" % patch.id,
                    points=points,
                    color="#00d7ff",
                    closed=edge.isClosed(),
                )
            )

    pass_ids = sorted(
        {
            flag
            for point in result.model_path.points
            for flag in point.flags
            if flag.startswith("pass=")
        },
        key=lambda value: int(value.split("=", 1)[1]),
    )
    vectors = []
    for pass_id in pass_ids:
        owned = [
            point
            for point in result.model_path.points
            if pass_id in point.flags
        ]
        cuts = [point for point in owned if point.motion is MotionKind.CUT]
        if not cuts:
            continue
        polylines.extend(
            (
                PreviewPolyline(
                    name="%s contact" % pass_id,
                    points=tuple(point.contact_xyz for point in cuts),
                    color="#65e572",
                ),
                PreviewPolyline(
                    name="%s cutter" % pass_id,
                    points=tuple(point.xyz for point in cuts),
                    color="#ffd23f",
                ),
                PreviewPolyline(
                    name="%s approach" % pass_id,
                    points=(owned[0].xyz, owned[1].xyz, cuts[0].xyz),
                    color="#ff6868",
                    dashed=True,
                ),
                PreviewPolyline(
                    name="%s retract" % pass_id,
                    points=(cuts[-1].xyz, owned[-1].xyz),
                    color="#ff6868",
                    dashed=True,
                ),
            )
        )
        vectors.extend(
            PreviewVector(
                start=point.xyz,
                end=add(point.xyz, scale(point.tool_axis, axis_length)),
                color="#b58cff",
            )
            for point in cuts[:: max(1, vector_stride)]
        )
    profile = profile or MachineProfile()
    tool_poses = _machine_poses(result, profile)

    return PreviewDocument(
        polylines=tuple(polylines),
        vectors=tuple(vectors),
        markers=(
            PreviewMarker("Face center", region.center_xyz, "#57a8ff"),
        ),
        b_values=tuple(point.b_deg for point in result.machine_path.points),
        c_values=tuple(point.c_deg for point in result.machine_path.points),
        warnings=result.machine_path.warnings,
        tool=_preview_tool(tool),
        tool_poses=tool_poses,
        spindle_origin=profile.workpiece.origin_xyz,
        spindle_axis=profile.workpiece.spindle_axis,
    )


def _preview_tool(tool: ToolDefinition | None):
    if tool is None:
        return None
    return PreviewToolGeometry(
        kind=tool.kind.value,
        diameter=tool.diameter,
        stickout=tool.stickout,
        cutting_length=tool.cutting_length,
        included_angle_deg=tool.included_angle_deg,
        tip_flat_diameter=tool.tip_flat_diameter,
        tip_radius=tool.tip_radius,
    )


def _machine_poses(result: PipelineResult, profile: MachineProfile):
    if len(result.model_path.points) != len(result.machine_path.points):
        raise ValueError(
            "Model and machine paths must align for preview"
        )
    poses = []
    for model_point, machine_point in zip(
        result.model_path.points, result.machine_path.points
    ):
        axis_model = axis_model_from_bc(
            machine_point.b_deg, machine_point.c_deg, profile
        )
        machine_axis = axis_machine_from_b(
            machine_point.b_deg, profile
        )
        axis_model_b_only = machine_to_model(machine_axis, profile)
        physical_c = (
            machine_point.c_deg - profile.c_zero_offset_deg
        ) / profile.c_axis_sign
        poses.append(
            PreviewToolPose(
                cutter_reference=model_point.xyz,
                tool_axis=axis_model,
                tool_axis_b_only=axis_model_b_only,
                motion=machine_point.motion,
                machine_xyz_radius=machine_point.xyz_radius,
                b_deg=machine_point.b_deg,
                c_deg=machine_point.c_deg,
                part_rotation_deg=-physical_c,
            )
        )
    return tuple(poses)
