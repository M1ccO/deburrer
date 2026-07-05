"""Tool models — cutter and holder geometry for contact solving.

Defines the geometric shapes used by the contact solver:
- Ball endmill (hemisphere + cylinder shank)
- Chamfer mill (cone + tip flat + cylinder shank)
- Bull-nose mill (corner-radius cylinder + flat bottom)
- Drill / tap (future)

Each cutter model provides:
- Signed-distance function from the cutter body
- Point-on-surface queries for contact touching
- Tangency constraints for chamfer face engagement
- Mesh generation for collision bodies and visualization

Bridges to ``fc_deburr.domain.models.ToolDefinition`` and the existing
``fc_deburr.solver`` analytic solvers.
"""
