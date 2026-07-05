"""Public API layer — schemas for jobs, tools, and machines.

These modules define the contract between the kernel and its clients (CLI,
FreeCAD, web UI, etc.).  All schemas are serializable to YAML/JSON and use
plain Python dataclasses for zero-overhead interop.

Schemas are validated on construction.  A schema that fails validation is
rejected with a ``SchemaError`` before any kernel work begins.
"""
