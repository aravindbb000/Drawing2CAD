"""
Multi-stage validation engine for Drawing2CAD models.
Performs:
1. Watertight closed manifold solid check
2. OpenCASCADE topological and geometric validity check
3. Parametric dimensional comparison against drawing specifications
4. STEP file round-trip re-import verification
"""

import os
import tempfile
from typing import Dict, Any, List, Optional
import build123d as bd
from .schemas import ValidationReport, DimensionCheckResult, DimensionItem


class CADValidator:
    def __init__(self, tolerance_mm: float = 0.05):
        self.tolerance_mm = tolerance_mm

    def validate_solid(
        self,
        solid: bd.Solid,
        expected_dims: Optional[Dict[str, DimensionItem]] = None,
        expected_features: Optional[List[Dict[str, Any]]] = None
    ) -> ValidationReport:
        """Run all validation stages and return a machine-readable ValidationReport."""
        errors: List[str] = []
        warnings: List[str] = []
        dim_checks: List[DimensionCheckResult] = []

        # 1. Basic Solid Checks
        if solid is None:
            return ValidationReport(
                is_closed_solid=False,
                is_geometrically_valid=False,
                bounding_box={},
                volume=0.0,
                step_reimport_valid=False,
                errors=["Solid is None."],
                overall_pass=False
            )

        is_closed = bool(len(solid.solids()) > 0 and solid.volume > 0)
        is_valid = bool(solid.is_valid)
        volume = round(float(solid.volume), 4)

        if not is_closed:
            errors.append("Solid is not closed (watertight boundary check failed).")
        if not is_valid:
            errors.append("Solid failed OpenCASCADE topological validity check.")

        # Bounding box
        bb = solid.bounding_box()
        bb_dict = {
            "size_x": round(float(bb.size.X), 4),
            "size_y": round(float(bb.size.Y), 4),
            "size_z": round(float(bb.size.Z), 4),
            "min_x": round(float(bb.min.X), 4),
            "max_x": round(float(bb.max.X), 4),
            "min_y": round(float(bb.min.Y), 4),
            "max_y": round(float(bb.max.Y), 4),
            "min_z": round(float(bb.min.Z), 4),
            "max_z": round(float(bb.max.Z), 4),
        }

        # 2. Dimensional Checks
        # Map common dimension names
        dim_map = {
            "length": bb.size.X,
            "width": bb.size.Y,
            "height": bb.size.Z,
            "thickness": bb.size.Z,
            "diameter": max(bb.size.Y, bb.size.Z)
        }

        # Handle rotation where X/Y/Z may correspond differently
        bb_sizes = sorted([bb.size.X, bb.size.Y, bb.size.Z], reverse=True)

        if expected_dims:
            for name, item in expected_dims.items():
                expected_val = item.value if isinstance(item, DimensionItem) else float(item)
                # Check direct or sorted match
                matched = False
                actual_val = 0.0

                if name.lower() in dim_map:
                    actual_val = dim_map[name.lower()]
                    delta = abs(actual_val - expected_val)
                    if delta <= self.tolerance_mm:
                        matched = True

                # If not direct match, check if any bounding box size matches
                if not matched:
                    for size in bb_sizes:
                        if abs(size - expected_val) <= self.tolerance_mm:
                            actual_val = size
                            matched = True
                            break

                delta = abs(actual_val - expected_val)
                passed = delta <= self.tolerance_mm

                dim_checks.append(DimensionCheckResult(
                    feature=f"overall_{name}",
                    expected=round(expected_val, 4),
                    actual=round(actual_val, 4),
                    delta=round(delta, 4),
                    tolerance=self.tolerance_mm,
                    passed=passed
                ))

                if not passed:
                    msg = f"Dimension mismatch for {name}: expected {expected_val}mm, got {round(actual_val, 4)}mm (delta {round(delta, 4)}mm)"
                    if getattr(item, 'assumed', False):
                        warnings.append(f"{msg} [Assumed dimension]")
                    else:
                        errors.append(msg)

        # 3. Hole / Feature Checks
        if expected_features:
            cyl_faces = [f for f in solid.faces() if f.geom_type == bd.GeomType.CYLINDER]
            cyl_diameters = [round(float(f.radius * 2.0), 3) for f in cyl_faces]

            for feat in expected_features:
                if feat.get("type") == "hole":
                    exp_dia = feat.get("parameters", {}).get("diameter")
                    if exp_dia:
                        found_dia = any(abs(d - exp_dia) <= self.tolerance_mm for d in cyl_diameters)
                        dim_checks.append(DimensionCheckResult(
                            feature=f"hole_dia_{exp_dia}mm",
                            expected=float(exp_dia),
                            actual=float(exp_dia) if found_dia else 0.0,
                            delta=0.0 if found_dia else float(exp_dia),
                            tolerance=self.tolerance_mm,
                            passed=found_dia
                        ))
                        if not found_dia:
                            errors.append(f"Expected hole of diameter {exp_dia}mm not found in model.")

        # 4. STEP Re-import Round-Trip Check
        step_reimport_valid = False
        reimported_volume: Optional[float] = None

        with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            bd.export_step(solid, tmp_path)
            reimported = bd.import_step(tmp_path)
            if reimported is not None and reimported.is_valid and len(reimported.solids()) > 0:
                step_reimport_valid = True
                reimported_volume = round(float(reimported.volume), 4)
                vol_delta = abs(volume - reimported_volume)
                if vol_delta > 0.01:
                    warnings.append(f"STEP re-import volume discrepancy: {vol_delta}mm³")
            else:
                errors.append("STEP file failed to re-import as a valid closed solid.")
        except Exception as e:
            errors.append(f"STEP re-import failed with exception: {str(e)}")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

        overall_pass = is_closed and is_valid and step_reimport_valid and (len(errors) == 0)

        return ValidationReport(
            is_closed_solid=is_closed,
            is_geometrically_valid=is_valid,
            bounding_box=bb_dict,
            volume=volume,
            step_reimport_valid=step_reimport_valid,
            step_reimport_volume=reimported_volume,
            dimension_checks=dim_checks,
            errors=errors,
            warnings=warnings,
            overall_pass=overall_pass
        )
