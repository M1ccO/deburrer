class DeburrError(Exception):
    """Base class for expected, user-actionable deburr failures."""


class SelectionError(DeburrError):
    """The FreeCAD selection cannot define the requested feature."""


class GeometryError(DeburrError):
    """The selected geometry cannot support the requested operation."""


class ValidationError(DeburrError):
    """A path failed a safety or machine-profile invariant."""
