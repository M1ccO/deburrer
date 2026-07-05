# CAM Kernel

Standalone Python CAM kernel for multiaxis deburring and surface finishing.
Built around OCCT for B-Rep geometry and STEP exchange, with pluggable
collision, kinematics, and post-processing.

## Architecture

```
cam_kernel/
  api/         YAML/JSON schemas for jobs, tools, machines
  geometry/    OCCT session, STEP I/O, topology graph, feature extraction
  sampling/    Edge and face sampling, local frame construction
  tools/       Cutter models, holder models, engagement rules
  contact/     OpenCAMLib bridge, local contact solvers
  posture/     Axis seeding, posture cost, optimization
  kinematics/  Machine-specific IK (NTX2500), branch selection
  collision/   FCL scene management, gouge checks, envelope
  smoothing/   Pose filtering, joint-space filtering, feed planning
  post/        FANUC NTX post-processor, NC formatters
  viz/         Backplot, debug export
  native/      Rust and C++ performance-critical modules
```

## Deburring-first roadmap

1. **MVP**: STEP intake, OCCT feature graph, edge/face deburring, indexed 3+2
2. **v1**: Continuous 5-axis deburring, posture cost optimization, FCL collision
3. **v2**: 4+1 and surface finishing, multi-machine abstraction, stock-aware

## Usage

```python
from cam_kernel.geometry import OcctSession, StepIO
from cam_kernel.sampling import EdgeSampler
from cam_kernel.contact import OclBridge
from cam_kernel.kinematics import Ntx2500Model
from cam_kernel.collision import FclScene
from cam_kernel.post import FanucNtxPost
```

## Development

```bash
pip install -e ".[dev]"
pytest
```
