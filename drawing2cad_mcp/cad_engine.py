"""
Core CAD modeling engine using build123d and OpenCASCADE.
Maintains state and provides structured, deterministic CAD modeling operations.
"""

import math
from typing import List, Tuple, Dict, Any, Optional
import build123d as bd


class CADEngine:
    def __init__(self):
        self.solid: Optional[bd.Solid] = None
        self.history: List[Dict[str, Any]] = []

    def reset(self):
        """Reset the CAD engine session to an empty state."""
        self.solid = None
        self.history = []

    def create_base_box(
        self,
        length: float,
        width: float,
        height: float,
        origin: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        align_min: bool = True
    ) -> Dict[str, Any]:
        """Create a base box solid."""
        if align_min:
            # Min corner at origin
            box = bd.Box(length, width, height, align=(bd.Align.MIN, bd.Align.MIN, bd.Align.MIN))
            box = box.locate(bd.Location(origin))
        else:
            box = bd.Box(length, width, height)
            box = box.locate(bd.Location(origin))

        self.solid = box
        self.history.append({
            "tool": "create_base_box",
            "params": {"length": length, "width": width, "height": height, "origin": origin}
        })
        return self.get_stats()

    def create_base_cylinder(
        self,
        diameter: float,
        height: float,
        axis: str = "Z",
        origin: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    ) -> Dict[str, Any]:
        """Create a base cylindrical solid."""
        radius = diameter / 2.0
        cyl = bd.Cylinder(radius=radius, height=height, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
        cyl = cyl.locate(bd.Location(origin))

        if axis.upper() == "X":
            cyl = cyl.rotate(bd.Axis.Y, 90)
        elif axis.upper() == "Y":
            cyl = cyl.rotate(bd.Axis.X, -90)

        self.solid = cyl
        self.history.append({
            "tool": "create_base_cylinder",
            "params": {"diameter": diameter, "height": height, "axis": axis, "origin": origin}
        })
        return self.get_stats()

    def create_base_extrusion(
        self,
        profile_pts: List[Tuple[float, float]],
        depth: float,
        plane: str = "XY",
        origin: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    ) -> Dict[str, Any]:
        """Create an extruded solid from a closed 2D polygon profile."""
        workplane = bd.Plane.XY
        if plane.upper() == "XZ":
            workplane = bd.Plane.XZ
        elif plane.upper() == "YZ":
            workplane = bd.Plane.YZ

        with bd.BuildPart() as p:
            with bd.BuildSketch(workplane):
                # Ensure closed profile
                pts = list(profile_pts)
                if pts[0] != pts[-1]:
                    pts.append(pts[0])
                with bd.BuildLine():
                    bd.Polyline(pts)
                bd.make_face()
            bd.extrude(amount=depth)

        part_solid = p.part
        if origin != (0.0, 0.0, 0.0):
            part_solid = part_solid.locate(bd.Location(origin))

        self.solid = part_solid
        self.history.append({
            "tool": "create_base_extrusion",
            "params": {"pts_count": len(profile_pts), "depth": depth, "plane": plane}
        })
        return self.get_stats()

    def create_revolve_body(
        self,
        profile_pts: List[Any],
        axis: str = "X",
        angle_deg: float = 360.0
    ) -> Dict[str, Any]:
        """
        Create a rotational solid by revolving a 2D half-profile around an axis.
        profile_pts are given in (axial, radial) or (x, z) coordinates.
        """
        # Clean consecutive duplicates
        cleaned_pts = []
        for p in profile_pts:
            pt = (float(p[0]), float(p[1]))
            if not cleaned_pts or (abs(pt[0] - cleaned_pts[-1][0]) > 1e-6 or abs(pt[1] - cleaned_pts[-1][1]) > 1e-6):
                cleaned_pts.append(pt)
        if abs(cleaned_pts[0][0] - cleaned_pts[-1][0]) > 1e-6 or abs(cleaned_pts[0][1] - cleaned_pts[-1][1]) > 1e-6:
            cleaned_pts.append(cleaned_pts[0])

        rev_axis = bd.Axis.X
        workplane = bd.Plane.XZ
        if axis.upper() == "Z":
            rev_axis = bd.Axis.Z
            workplane = bd.Plane.XZ
        elif axis.upper() == "Y":
            rev_axis = bd.Axis.Y
            workplane = bd.Plane.XY

        with bd.BuildPart() as p:
            with bd.BuildSketch(workplane):
                with bd.BuildLine():
                    bd.Polyline(cleaned_pts)
                bd.make_face()
            bd.revolve(axis=rev_axis, revolution_arc=angle_deg)

        self.solid = p.part
        self.history.append({
            "tool": "create_revolve_body",
            "params": {"pts_count": len(cleaned_pts), "axis": axis, "angle_deg": angle_deg}
        })
        return self.get_stats()

    def add_hole(
        self,
        center: Tuple[float, float, float],
        diameter: float,
        depth: float,
        normal: Tuple[float, float, float] = (0.0, 0.0, 1.0),
        through: bool = False,
        conical_tip: bool = False,
        tip_angle: float = 118.0,
        chamfer_size: float = 0.0
    ) -> Dict[str, Any]:
        """Drill a hole into the current solid."""
        if self.solid is None:
            raise ValueError("No active solid to drill hole into.")

        radius = diameter / 2.0
        norm_vec = bd.Vector(normal).normalized()

        # Build cutting tool
        effective_depth = depth if not through else 200.0
        
        with bd.BuildPart() as tool:
            plane = bd.Plane(origin=bd.Vector(center), z_dir=norm_vec)
            with bd.BuildSketch(plane):
                bd.Circle(radius=radius)
            bd.extrude(amount=effective_depth, both=through)
            
            # Add conical tip if specified and blind
            if conical_tip and not through:
                # drill cone tip
                half_angle_rad = math.radians(tip_angle / 2.0)
                cone_h = radius / math.tan(half_angle_rad)
                tip_origin = bd.Vector(center) + norm_vec * effective_depth
                tip_plane = bd.Plane(origin=tip_origin, z_dir=norm_vec)
                with bd.BuildSketch(tip_plane):
                    bd.Circle(radius=radius)
                bd.extrude(amount=cone_h, taper=90 - (tip_angle / 2.0))

        # Subtract hole tool
        self.solid = self.solid - tool.part

        # Add chamfer if requested
        if chamfer_size > 0.0:
            # find circular edges of hole near center
            target_edges = [
                e for e in self.solid.edges()
                if e.geom_type == bd.GeomType.CIRCLE
                and abs(e.radius - radius) < 0.1
                and (bd.Vector(e.center()) - bd.Vector(center)).length < (radius + 2.0)
            ]
            if target_edges:
                try:
                    self.solid = bd.chamfer(target_edges, length=chamfer_size)
                except Exception:
                    pass

        self.history.append({
            "tool": "add_hole",
            "params": {"center": center, "diameter": diameter, "depth": depth, "through": through}
        })
        return self.get_stats()

    def add_slot(
        self,
        center: Tuple[float, float, float],
        length: float,
        width: float,
        depth: float,
        normal: Tuple[float, float, float] = (0.0, 0.0, 1.0),
        through: bool = True,
        rotation_deg: float = 0.0
    ) -> Dict[str, Any]:
        """Add an elongated slot with semicircular ends."""
        if self.solid is None:
            raise ValueError("No active solid.")

        norm_vec = bd.Vector(normal).normalized()
        effective_depth = depth if not through else 200.0

        with bd.BuildPart() as tool:
            plane = bd.Plane(origin=bd.Vector(center), z_dir=norm_vec)
            with bd.BuildSketch(plane):
                bd.SlotCenterToCenter(length, width, rotation=rotation_deg)
            bd.extrude(amount=effective_depth, both=through)

        self.solid = self.solid - tool.part
        self.history.append({
            "tool": "add_slot",
            "params": {"center": center, "length": length, "width": width, "depth": depth}
        })
        return self.get_stats()

    def add_fillet(self, radius: float, edge_direction: Optional[str] = None) -> Dict[str, Any]:
        """Add fillet to solid edges."""
        if self.solid is None:
            raise ValueError("No active solid.")

        edges = self.solid.edges()
        if edge_direction == "Z":
            edges = edges.filter_by(bd.Axis.Z)
        elif edge_direction == "X":
            edges = edges.filter_by(bd.Axis.X)
        elif edge_direction == "Y":
            edges = edges.filter_by(bd.Axis.Y)

        self.solid = bd.fillet(edges, radius=radius)
        self.history.append({
            "tool": "add_fillet",
            "params": {"radius": radius, "direction": edge_direction}
        })
        return self.get_stats()

    def add_chamfer(self, distance: float, edge_direction: Optional[str] = None) -> Dict[str, Any]:
        """Add chamfer to solid edges."""
        if self.solid is None:
            raise ValueError("No active solid.")

        edges = self.solid.edges()
        if edge_direction == "Z":
            edges = edges.filter_by(bd.Axis.Z)
        elif edge_direction == "X":
            edges = edges.filter_by(bd.Axis.X)
        elif edge_direction == "Y":
            edges = edges.filter_by(bd.Axis.Y)

        self.solid = bd.chamfer(edges, length=distance)
        self.history.append({
            "tool": "add_chamfer",
            "params": {"distance": distance, "direction": edge_direction}
        })
        return self.get_stats()

    def set_solid(self, solid: bd.Solid, description: str = "custom_operation"):
        """Directly set or replace the current active solid."""
        self.solid = solid
        self.history.append({"tool": "set_solid", "description": description})
        return self.get_stats()

    def get_stats(self) -> Dict[str, Any]:
        """Get geometric statistics of the active model."""
        if self.solid is None:
            return {
                "active": False,
                "is_valid": False,
                "is_closed": False,
                "volume": 0.0,
                "bounding_box": {"size_x": 0.0, "size_y": 0.0, "size_z": 0.0}
            }

        bb = self.solid.bounding_box()
        is_closed_solid = bool(len(self.solid.solids()) > 0 and self.solid.volume > 0)
        return {
            "active": True,
            "is_valid": bool(self.solid.is_valid),
            "is_closed": is_closed_solid,
            "volume": round(float(self.solid.volume), 4),
            "faces_count": len(self.solid.faces()),
            "edges_count": len(self.solid.edges()),
            "bounding_box": {
                "min_x": round(float(bb.min.X), 4),
                "max_x": round(float(bb.max.X), 4),
                "size_x": round(float(bb.size.X), 4),
                "min_y": round(float(bb.min.Y), 4),
                "max_y": round(float(bb.max.Y), 4),
                "size_y": round(float(bb.size.Y), 4),
                "min_z": round(float(bb.min.Z), 4),
                "max_z": round(float(bb.max.Z), 4),
                "size_z": round(float(bb.size.Z), 4),
            }
        }
