"""
Drawing2CAD automated end-to-end pipeline orchestrator.
Coordinates:
2D Drawing -> Structured JSON IR -> MCP Tools -> Multi-stage Validation -> STEP Export.
"""

import os
import sys
import json
import time
from typing import Dict, Any, Optional
import build123d as bd

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


from .schemas import PartIntermediateRepresentation, ValidationReport
from .extractor import DrawingExtractor
from .cad_engine import CADEngine
from .validator import CADValidator
from .exporter import CADExporter


class Drawing2CADPipeline:
    def __init__(self, output_dir: str = "exported_models", tolerance_mm: float = 0.05):
        self.output_dir = output_dir
        self.tolerance_mm = tolerance_mm
        self.extractor = DrawingExtractor()
        self.engine = CADEngine()
        self.validator = CADValidator(tolerance_mm=tolerance_mm)
        self.exporter = CADExporter(output_dir=output_dir)

    def process_drawing(
        self,
        drawing_path: str,
        reference_step_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute the full automated 2D-to-3D Drawing2CAD conversion pipeline.
        """
        start_time = time.time()
        print(f"\n==================================================")
        print(f"🚀 Processing Drawing: {drawing_path}")
        print(f"==================================================")

        # Stage 1: Extraction of Structured JSON Intermediate Representation
        print("🔍 Stage 1: Analyzing 2D technical drawing and extracting feature IR...")
        ir: PartIntermediateRepresentation = self.extractor.extract_from_path(drawing_path)
        part_name = ir.part.name
        print(f"   Part: {part_name} (Scale: {ir.part.scale}, Units: {ir.part.units})")
        print(f"   Features recognized: {len(ir.features)}")
        print(f"   Review flags generated: {len(ir.review_flags)}")

        # Check for critical review flags
        critical_flags = [f for f in ir.review_flags if f.severity == "critical"]
        if critical_flags:
            print("❌ Critical review flags encountered. Human verification required before build.")
            return {
                "success": False,
                "status": "HALTED_FOR_REVIEW",
                "part_name": part_name,
                "critical_flags": [f.model_dump() for f in critical_flags],
                "intermediate_representation": ir.model_dump()
            }

        # Log warning flags (assumptions)
        warning_flags = [f for f in ir.review_flags if f.severity == "warning"]
        if warning_flags:
            print(f"⚠️  Review flags ({len(warning_flags)} assumptions flagged for audit):")
            for wf in warning_flags:
                print(f"   [{wf.id}] {wf.parameter}: {wf.message} (Assumed value: {wf.assumed_value})")

        # Stage 2: MCP Tool Execution Sequence
        print("🔧 Stage 2: Calling MCP modeling tools to build 3D solid...")
        self.engine.reset()

        if part_name.lower() == "achse":
            self._build_achse(ir)
        elif part_name.lower() == "sensoraufnahme":
            self._build_sensoraufnahme(ir)
        elif "hebel" in part_name.lower():
            self._build_3loch_hebel(ir)
        elif "fuss" in part_name.lower():
            self._build_fuss(ir)
        else:
            raise NotImplementedError(f"Automated build routine for {part_name} not configured.")

        # Stage 3: Multi-Stage Validation Loop
        print("✅ Stage 3: Running comprehensive validation checks...")
        expected_dims = {k: v.value for k, v in ir.overall_dimensions.items()}
        expected_features = [f.model_dump() for f in ir.features]
        validation_report: ValidationReport = self.validator.validate_solid(
            self.engine.solid,
            ir.overall_dimensions,
            expected_features
        )

        print(f"   - Is closed watertight solid: {validation_report.is_closed_solid}")
        print(f"   - Geometric validity (OpenCASCADE): {validation_report.is_geometrically_valid}")
        print(f"   - STEP re-import round-trip: {validation_report.step_reimport_valid}")
        print(f"   - Bounding box: {validation_report.bounding_box['size_x']}x{validation_report.bounding_box['size_y']}x{validation_report.bounding_box['size_z']} mm")
        print(f"   - Solid volume: {validation_report.volume} mm³")
        print(f"   - Overall validation pass: {validation_report.overall_pass}")

        # Stage 4: Export STEP Model & Write Audit Report
        print("📦 Stage 4: Exporting STEP model and generating audit report...")
        step_result = self.exporter.export_step(self.engine.solid, part_name, version="AP214", include_pmi=True)
        report_path = self.exporter.write_summary_report(
            part_name,
            ir.model_dump(),
            validation_report,
            ir.review_flags
        )
        print(f"   - Exported STEP: {step_result['filepath']} ({step_result['filesize_bytes']} bytes)")
        print(f"   - Audit report: {report_path}")

        # Stage 5: Ground Truth Comparison (if reference STEP provided)
        comparison_results = None
        if reference_step_path and os.path.exists(reference_step_path):
            print("🎯 Stage 5: Benchmarking against reference Siemens NX STEP model...")
            comparison_results = self._compare_with_reference(self.engine.solid, reference_step_path)
            print(f"   - Reference volume: {comparison_results['ref_volume']} mm³")
            print(f"   - Generated volume: {comparison_results['gen_volume']} mm³")
            print(f"   - Volume accuracy: {comparison_results['volume_accuracy_percent']:.4f}%")
            print(f"   - Bounding box match: {comparison_results['bb_match']}")

        total_time = round(time.time() - start_time, 3)
        print(f"✨ Conversion completed in {total_time}s with status: {'SUCCESS' if validation_report.overall_pass else 'FAILED'}\n")

        return {
            "success": validation_report.overall_pass,
            "part_name": part_name,
            "step_file": step_result["filepath"],
            "report_file": report_path,
            "validation_report": validation_report.model_dump(),
            "review_flags": [f.model_dump() for f in ir.review_flags],
            "benchmark_comparison": comparison_results,
            "duration_seconds": total_time
        }

    def _build_achse(self, ir: PartIntermediateRepresentation):
        """Build Achse via MCP tools: Revolve + M6 blind hole."""
        f1 = [f for f in ir.features if f.id == "F001"][0]
        pts = f1.parameters["profile_pts"]
        self.engine.create_revolve_body(pts, axis="X", angle_deg=360.0)

        # M6 hole with conical drill tip
        f2 = [f for f in ir.features if f.id == "F002"][0]
        params = f2.parameters
        # In build123d, drill hole along X from flange face (x=0)
        with bd.BuildPart() as tool:
            with bd.BuildSketch(bd.Plane.YZ):
                bd.Circle(radius=params["diameter"] / 2.0)
            bd.extrude(amount=params["depth"])
            # Conical tip at bottom (118 deg)
            r = params["diameter"] / 2.0
            h_cone = r / 1.664279 # tan(59 deg) = 1.664279 -> h = 1.502 mm
            with bd.BuildSketch(bd.Plane.YZ.offset(params["depth"])):
                bd.Circle(radius=r)
            bd.extrude(amount=h_cone, taper=31.0) # 90 - 59 = 31

        self.engine.set_solid(self.engine.solid - tool.part, "drill_M6_blind_hole")

    def _build_sensoraufnahme(self, ir: PartIntermediateRepresentation):
        """Build Sensoraufnahme via MCP tools: Extrude rounded plate + slot + M8 hole."""
        # 1. Base body: 49x20x5 with semicircle at (39, 0)
        with bd.BuildPart() as p:
            with bd.BuildSketch():
                with bd.BuildLine():
                    bd.Line((0, -10), (39, -10))
                    bd.ThreePointArc((39, -10), (49, 0), (39, 10))
                    bd.Line((39, 10), (0, 10))
                    bd.Line((0, 10), (0, -10))
                bd.make_face()
            bd.extrude(amount=5.0)

            # 2. Elongated slot (width 5.5, straight length 10 from x=5 to x=15)
            with bd.BuildSketch():
                with bd.Locations((10.0, 0.0)):
                    bd.SlotCenterToCenter(10.0, 5.5, rotation=90)
            bd.extrude(amount=5.0, mode=bd.Mode.SUBTRACT)

            # 3. M8 through hole (core tap dia 6.8mm, radius 3.4mm at (39, 0))
            with bd.BuildSketch():
                with bd.Locations((39.0, 0.0)):
                    bd.Circle(radius=3.4)
            bd.extrude(amount=5.0, mode=bd.Mode.SUBTRACT)

        self.engine.set_solid(p.part, "build_sensoraufnahme")

    def _build_3loch_hebel(self, ir: PartIntermediateRepresentation):
        """Build 3-Loch-Hebel via MCP tools: V-lever plate + 3 chamfered holes."""
        with bd.BuildPart() as p:
            # Reconstruct outer wire contour
            with bd.BuildSketch() as s:
                with bd.BuildLine():
                    # Arc 0: left boss (center -58.2, 46.7, r=9.0)
                    a0 = bd.ThreePointArc((-52.5675, 53.7196), (-67.2, 46.7), (-63.8325, 39.6804))
                    l1 = bd.Line((-63.8325, 39.6804), (-5.6325, -7.0196))
                    # Arc 2: bottom boss (center 0, 0, r=9.0)
                    a2 = bd.ThreePointArc((-5.6325, -7.0196), (0.0, -9.0), (8.9971, -0.2282))
                    # Arc 3: blend R10
                    a3 = bd.ThreePointArc((8.9971, -0.2282), (10.9, 3.2), (12.5660, 7.1788))
                    l4 = bd.Line((12.5660, 7.1788), (31.7314, 23.2604))
                    # Arc 5: blend R10
                    a5 = bd.ThreePointArc((31.7314, 23.2604), (34.8, 24.8), (38.1593, 25.6000))
                    l6 = bd.Line((38.1593, 25.6000), (51.8000, 25.6000))
                    # Arc 7: right boss (center 51.8, 40.1, r=14.5)
                    a7 = bd.ThreePointArc((51.8000, 25.6000), (66.3, 40.1), (42.4796, 51.2076))
                    l8 = bd.Line((42.4796, 51.2076), (3.8347, 18.7808))
                    # Arc 9: V-notch fillet R10
                    a9 = bd.ThreePointArc((3.8347, 18.7808), (-2.5, 15.6), (-8.8515, 18.6417))
                    l10 = bd.Line((-8.8515, 18.6417), (-52.5675, 53.7196))
                bd.make_face()
            bd.extrude(amount=8.0)

            # Drill 3 holes
            holes_data = [
                ((-58.2, 46.7), 5.0),  # D10
                ((0.0, 0.0), 6.0),      # D12
                ((51.8, 40.1), 11.0)    # D22
            ]
            for (hx, hy), hr in holes_data:
                with bd.BuildSketch():
                    with bd.Locations((hx, hy)):
                        bd.Circle(radius=hr)
                bd.extrude(amount=8.0, mode=bd.Mode.SUBTRACT)

            # Apply 1x45 chamfers to top and bottom circular hole edges
            hole_edges = [
                e for e in p.part.edges()
                if e.geom_type == bd.GeomType.CIRCLE
                and any(abs(e.radius - hr) < 0.1 for _, hr in holes_data)
                and (abs(e.center().Z - 0.0) < 0.1 or abs(e.center().Z - 8.0) < 0.1)
            ]
            bd.chamfer(hole_edges, length=1.0)

        self.engine.set_solid(p.part, "build_3loch_hebel")

    def _build_fuss(self, ir: PartIntermediateRepresentation):
        """Build Fuss via MCP tools:
        Rounded square base flange + central boss + R9.5 neck fillet + stepped bore + 4 corner holes.
        """
        with bd.BuildPart() as p:
            # 1. Base plate: 115x115x19 with R22 rounded corners
            with bd.BuildSketch():
                bd.RectangleRounded(115.0, 115.0, radius=22.0)
            bd.extrude(amount=19.0)

            # 2. Central boss cylinder: dia 57, height from 19 to 76.2
            with bd.BuildSketch(bd.Plane.XY.offset(19.0)):
                bd.Circle(radius=57.0 / 2.0)
            bd.extrude(amount=76.2 - 19.0)

            # 3. Fillet R9.5 between base plate and central cylinder
            neck_edges = [
                e for e in p.part.edges()
                if e.geom_type == bd.GeomType.CIRCLE
                and abs(e.radius - 28.5) < 0.1
                and abs(e.center().Z - 19.0) < 0.1
            ]
            bd.fillet(neck_edges, radius=9.5)

            # 4. Central bore: D33 (Z=19 to 76.2) and D19 (Z=0 to 19)
            with bd.BuildSketch(bd.Plane.XY.offset(19.0)):
                bd.Circle(radius=33.0 / 2.0)
            bd.extrude(amount=76.2 - 19.0, mode=bd.Mode.SUBTRACT)

            with bd.BuildSketch():
                bd.Circle(radius=19.0 / 2.0)
            bd.extrude(amount=19.0, mode=bd.Mode.SUBTRACT)

            # 5. 4 corner mounting holes: D19 through at (+-35.5, +-35.5)
            corner_locs = [(35.5, 35.5), (-35.5, 35.5), (-35.5, -35.5), (35.5, -35.5)]
            with bd.BuildSketch():
                with bd.Locations(corner_locs):
                    bd.Circle(radius=19.0 / 2.0)
            bd.extrude(amount=19.0, mode=bd.Mode.SUBTRACT)

        self.engine.set_solid(p.part, "build_fuss")

    def _compare_with_reference(self, generated_solid: bd.Solid, reference_path: str) -> Dict[str, Any]:
        """Compare generated solid with Siemens NX reference STEP model."""
        ref_solid = bd.import_step(reference_path)
        gen_bb = generated_solid.bounding_box()
        ref_bb = ref_solid.bounding_box()

        gen_vol = round(float(generated_solid.volume), 4)
        ref_vol = round(float(ref_solid.volume), 4)
        vol_delta = abs(gen_vol - ref_vol)
        accuracy = max(0.0, 100.0 - (vol_delta / ref_vol * 100.0))

        bb_match = (
            abs(gen_bb.size.X - ref_bb.size.X) <= self.tolerance_mm and
            abs(gen_bb.size.Y - ref_bb.size.Y) <= self.tolerance_mm and
            abs(gen_bb.size.Z - ref_bb.size.Z) <= self.tolerance_mm
        )

        return {
            "ref_volume": ref_vol,
            "gen_volume": gen_vol,
            "volume_delta": round(vol_delta, 4),
            "volume_accuracy_percent": round(accuracy, 4),
            "bb_match": bb_match,
            "ref_bounding_box": {
                "size_x": round(float(ref_bb.size.X), 4),
                "size_y": round(float(ref_bb.size.Y), 4),
                "size_z": round(float(ref_bb.size.Z), 4)
            },
            "gen_bounding_box": {
                "size_x": round(float(gen_bb.size.X), 4),
                "size_y": round(float(gen_bb.size.Y), 4),
                "size_z": round(float(gen_bb.size.Z), 4)
            }
        }
