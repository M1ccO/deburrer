"""Edge sampler — OCCT-backed and FreeCAD-compatible.

Provides two backends for edge sampling:
1. **OCCT** — direct B-Rep sampling via `feature_extract.sample_edge_chain_from_shape`
2. **FreeCAD** — delegates to the existing wire adapter

The OCCT backend is the primary; FreeCAD is a fallback for when
running inside the FreeCAD Python environment.

Usage::

    from cam_kernel.sampling.edge_sampler import sample_edge

    samples = sample_edge(shape)           # OCCT
    samples = sample_edge(wire_obj)        # FreeCAD (auto-detected)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

Vec3 = Tuple[float, float, float]


@dataclass(frozen=True)
class EdgeSample:
    position: Vec3
    tangent: Vec3
    guide_normal: Vec3
    other_normal: Vec3
    edge_id: str = ""
    chain_index: int = 0


@dataclass(frozen=True)
class EdgeChainSamples:
    id: str
    samples: Tuple[EdgeSample, ...]
    closed: bool
    center_xyz: Optional[Vec3] = None
    source_edge_ids: Tuple[str, ...] = ()

    @property
    def sample_count(self) -> int:
        return len(self.samples)


def sample_edge(source, spacing: float = 0.5) -> EdgeChainSamples:
    """Sample edges from a shape or FreeCAD wire.

    Auto-detects the source type:
    - TopoShape / TopoDS_Shape → OCCT backend
    - FreeCAD Part.Shape / Wire → FreeCAD adapter
    - EdgeChain → OCCT with topology graph

    Args:
        source: OCCT shape, FreeCAD wire, or EdgeChain.
        spacing: Sample spacing in mm.

    Returns:
        EdgeChainSamples with position, tangent, guide_normal, other_normal.
    """
    if _is_occt_shape(source):
        return _sample_occt(source, spacing)
    if _is_freecad_wire(source):
        return _sample_freecad(source, spacing)
    raise TypeError(f"Unsupported source type: {type(source)}")


def _is_occt_shape(obj) -> bool:
    try:
        from OCP.TopoDS import TopoDS_Shape
        return isinstance(obj, TopoDS_Shape) or hasattr(obj, "_shape")
    except ImportError:
        return False


def _is_freecad_wire(obj) -> bool:
    try:
        import FreeCAD
        import Part
        return isinstance(obj, Part.Wire) or hasattr(obj, "Shape")
    except ImportError:
        return False


def _sample_occt(shape, spacing: float) -> EdgeChainSamples:
    from ..geometry.feature_extract import sample_edge_chain_from_shape

    result = sample_edge_chain_from_shape(shape, spacing)
    return EdgeChainSamples(
        id=result.id,
        samples=tuple(
            EdgeSample(
                position=s.position,
                tangent=s.tangent,
                guide_normal=s.guide_normal,
                other_normal=s.other_normal,
                edge_id=s.edge_id,
                chain_index=s.chain_index,
            )
            for s in result.samples
        ),
        closed=result.closed,
        center_xyz=result.center_xyz,
    )


def _sample_freecad(wire, spacing: float) -> EdgeChainSamples:
    from fc_deburr.freecad_adapter.wire import sample_loop

    loop = sample_loop(wire, spacing, center_pct=5.0)
    return EdgeChainSamples(
        id=loop.id,
        samples=tuple(
            EdgeSample(
                position=s.position,
                tangent=s.tangent,
                guide_normal=s.guide_normal,
                other_normal=s.other_normal,
                edge_id=s.source_edge_id,
            )
            for s in loop.samples
        ),
        closed=loop.closed,
        center_xyz=loop.center_xyz,
        source_edge_ids=loop.source_edge_ids,
    )
