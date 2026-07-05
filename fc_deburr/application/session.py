from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..domain.models import FaceRegion, FeatureLoop, Operation, ToolDefinition
from ..domain.serialization import load_feature
from ..machine.post_ntx import NtxPostSettings, post_ntx_tcp
from ..machine.profiles import MachineProfile
from ..preview.builder import build_face_preview, build_preview
from ..preview.models import PreviewDocument
from .pipeline import PipelineResult, calculate_toolpath
from .face_pipeline import calculate_face_toolpath


@dataclass
class DeburrSession:
    """The sole mutable owner of application state.

    Widgets display values and adapters create immutable input.  Recalculation
    replaces all derived state atomically so stale preview/NC cannot survive a
    changed feature or operation.
    """

    feature_path: Optional[Path] = None
    feature: Optional[FeatureLoop | FaceRegion] = None
    result: Optional[PipelineResult] = None
    preview: Optional[PreviewDocument] = None
    nc_text: Optional[str] = None

    def load_feature(self, path: str | Path) -> FeatureLoop:
        feature = load_feature(path)
        self.feature_path = Path(path)
        self.feature = feature
        self._clear_derived()
        return feature

    def calculate(
        self,
        tool: ToolDefinition,
        operation: Operation,
        profile: MachineProfile,
    ) -> PipelineResult:
        if self.feature is None:
            raise ValueError("Load a feature job before calculating")
        if isinstance(self.feature, FaceRegion):
            result = calculate_face_toolpath(
                self.feature, tool, operation, profile
            )
            preview = build_face_preview(
                self.feature, result, tool=tool, profile=profile
            )
        else:
            result = calculate_toolpath(
                self.feature, tool, operation, profile
            )
            preview = build_preview(
                self.feature, result, tool=tool, profile=profile
            )
        self.result = result
        self.preview = preview
        self.nc_text = None
        return result

    def post(
        self, profile: MachineProfile, settings: NtxPostSettings
    ) -> str:
        if self.result is None:
            raise ValueError("Calculate and validate a toolpath before posting")
        nc_text = post_ntx_tcp(self.result.machine_path, profile, settings)
        self.nc_text = nc_text
        return nc_text

    def _clear_derived(self):
        self.result = None
        self.preview = None
        self.nc_text = None
