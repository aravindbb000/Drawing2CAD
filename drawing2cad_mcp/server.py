"""
Drawing2CAD Model Context Protocol (MCP) Server.
Runs locally and provides standard parametric 3D CAD modeling,
validation, and export tools over MCP standard protocol.
"""

from typing import List, Dict, Any, Optional
from fastmcp import FastMCP
from .cad_engine import CADEngine
from .sandbox import CADSandbox
from .validator import CADValidator
from .exporter import CADExporter
from .schemas import DimensionItem

# Initialize MCP server
mcp = FastMCP("Drawing2CAD-Engine", instructions="Local OpenCASCADE CAD generation and validation engine")

# Global session engine instances
engine = CADEngine()
sandbox = CADSandbox(timeout_seconds=30)
validator = CADValidator(tolerance_mm=0.05)
exporter = CADExporter(output_dir="exported_models")


@mcp.tool()
def create_base_box(length: float, width: float, height: float, origin: List[float] = [0.0, 0.0, 0.0]) -> Dict[str, Any]:
    """Create a rectangular solid base body with length (X), width (Y), and height (Z)."""
    return engine.create_base_box(length, width, height, tuple(origin))


@mcp.tool()
def create_base_cylinder(diameter: float, height: float, axis: str = "Z", origin: List[float] = [0.0, 0.0, 0.0]) -> Dict[str, Any]:
    """Create a cylindrical base body with given diameter and height along axis X, Y, or Z."""
    return engine.create_base_cylinder(diameter, height, axis, tuple(origin))


@mcp.tool()
def create_base_extrusion(profile_pts: List[List[float]], depth: float, plane: str = "XY") -> Dict[str, Any]:
    """Create an extruded solid from a closed 2D polygon profile list [[x1, y1], [x2, y2], ...]."""
    pts = [tuple(p) for p in profile_pts]
    return engine.create_base_extrusion(pts, depth, plane)


@mcp.tool()
def create_revolve_body(profile_pts: List[List[float]], axis: str = "X", angle_deg: float = 360.0) -> Dict[str, Any]:
    """Create a rotational body by revolving a 2D half-profile around an axis (default X axis)."""
    pts = [tuple(p) for p in profile_pts]
    return engine.create_revolve_body(pts, axis, angle_deg)


@mcp.tool()
def add_hole(
    center: List[float],
    diameter: float,
    depth: float,
    normal: List[float] = [0.0, 0.0, 1.0],
    through: bool = False,
    conical_tip: bool = False,
    tip_angle: float = 118.0,
    chamfer_size: float = 0.0
) -> Dict[str, Any]:
    """Drill a cylindrical hole at center (x, y, z) into the current solid."""
    return engine.add_hole(
        tuple(center), diameter, depth, tuple(normal),
        through=through, conical_tip=conical_tip, tip_angle=tip_angle, chamfer_size=chamfer_size
    )


@mcp.tool()
def add_slot(
    center: List[float],
    length: float,
    width: float,
    depth: float,
    normal: List[float] = [0.0, 0.0, 1.0],
    through: bool = True,
    rotation_deg: float = 0.0
) -> Dict[str, Any]:
    """Add an elongated slot with rounded semicircular ends at center (x, y, z)."""
    return engine.add_slot(
        tuple(center), length, width, depth, tuple(normal), through=through, rotation_deg=rotation_deg
    )


@mcp.tool()
def add_fillet(radius: float, direction: Optional[str] = None) -> Dict[str, Any]:
    """Add fillet (rounding) of given radius to solid edges, optionally filtering by direction (X, Y, Z)."""
    return engine.add_fillet(radius, direction)


@mcp.tool()
def add_chamfer(distance: float, direction: Optional[str] = None) -> Dict[str, Any]:
    """Add chamfer (bevel) of given distance to solid edges, optionally filtering by direction (X, Y, Z)."""
    return engine.add_chamfer(distance, direction)


@mcp.tool()
def execute_sandbox_script(script_code: str, timeout_seconds: int = 30) -> Dict[str, Any]:
    """
    Fallback execution of arbitrary Python / build123d script in an isolated sandbox
    with no network access and strict timeout.
    """
    sb = CADSandbox(timeout_seconds=timeout_seconds)
    result = sb.execute_script(script_code)
    if result.get("success") and result.get("step_path"):
        import build123d as bd
        reimported = bd.import_step(result["step_path"])
        engine.set_solid(reimported, "sandbox_script")
    return result


@mcp.tool()
def validate_model(
    expected_dims: Optional[Dict[str, float]] = None,
    expected_features: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Run complete validation:
    1. Closed solid check
    2. OpenCASCADE geometric validity check
    3. Dimensional comparison against expected values
    4. STEP file round-trip re-import check
    """
    exp_dim_items = None
    if expected_dims:
        exp_dim_items = {k: DimensionItem(value=v) for k, v in expected_dims.items()}
    report = validator.validate_solid(engine.solid, exp_dim_items, expected_features)
    return report.model_dump()


@mcp.tool()
def export_step(part_name: str, version: str = "AP214", include_pmi: bool = False) -> Dict[str, Any]:
    """Export the active solid model to STEP ISO 10303 format."""
    if engine.solid is None:
        return {"success": False, "error": "No active solid to export."}
    return exporter.export_step(engine.solid, part_name, version, include_pmi)


@mcp.tool()
def get_model_status() -> Dict[str, Any]:
    """Get the current CAD model bounding box, volume, validity, and statistics."""
    return engine.get_stats()


@mcp.tool()
def reset_model() -> Dict[str, Any]:
    """Reset the CAD engine session to start a new model."""
    engine.reset()
    return {"success": True, "message": "CAD engine reset."}


if __name__ == "__main__":
    # Start FastMCP server on stdio or sse
    mcp.run()
