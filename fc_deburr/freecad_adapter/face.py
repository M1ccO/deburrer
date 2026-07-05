from __future__ import annotations

from ..domain.errors import SelectionError
from ..domain.models import FacePatch, FaceRegion

try:
    import Part
except ImportError:
    Part = None


def extract_face_region_from_selection(
    selection_ex,
    feature_id: str = "selected_faces",
) -> FaceRegion:
    """Capture selected faces as owned BREP snapshots for later path solving."""

    if Part is None:
        raise RuntimeError("Face extraction must run inside FreeCAD Python")
    faces = []
    face_ids = []
    source_names = []
    for selection in selection_ex:
        if selection.Object is not None:
            source_names.append(getattr(selection.Object, "Name", ""))
        for name, subobject in zip(
            selection.SubElementNames, selection.SubObjects
        ):
            if not isinstance(subobject, Part.Face):
                raise SelectionError(
                    "Face Finishing needs only the target faces selected"
                )
            faces.append(subobject)
            face_ids.append(str(name))
    if not faces:
        raise SelectionError("Select one or more faces to finish")

    patches = tuple(
        FacePatch(
            id=face_ids[index],
            brep=face.exportBrepToString(),
            area=float(face.Area),
        )
        for index, face in enumerate(faces)
    )
    bounds = [face.BoundBox for face in faces]
    center = (
        (min(bound.XMin for bound in bounds) + max(bound.XMax for bound in bounds))
        * 0.5,
        (min(bound.YMin for bound in bounds) + max(bound.YMax for bound in bounds))
        * 0.5,
        (min(bound.ZMin for bound in bounds) + max(bound.ZMax for bound in bounds))
        * 0.5,
    )
    return FaceRegion(
        id=feature_id,
        patches=patches,
        center_xyz=center,
        source_object_id=",".join(name for name in source_names if name),
    )
