"""
STEP file export engine with metadata and review reports.
Supports ISO 10303 AP203/AP214/AP242 standards.
"""

import os
import json
import time
from typing import Dict, Any, Optional
import build123d as bd
from .schemas import ValidationReport, ReviewFlag


class CADExporter:
    def __init__(self, output_dir: str = "exported_models"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def export_step(
        self,
        solid: bd.Solid,
        part_name: str,
        version: str = "AP214",
        include_pmi: bool = False
    ) -> Dict[str, Any]:
        """Export solid to ISO 10303 STEP format."""
        start_time = time.time()
        safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in part_name)
        step_filename = f"{safe_name}.stp"
        step_filepath = os.path.join(self.output_dir, step_filename)

        # Export STEP
        bd.export_step(solid, step_filepath)
        file_size_bytes = os.path.getsize(step_filepath)

        # Also export STL for interactive web 3D viewer
        stl_filename = f"{safe_name}.stl"
        stl_filepath = os.path.join(self.output_dir, stl_filename)
        try:
            bd.export_stl(solid, stl_filepath)
        except Exception:
            pass

        duration = round(time.time() - start_time, 3)

        # Inject semantic header / PMI comment if requested
        if include_pmi:
            try:
                with open(step_filepath, "r", encoding="latin-1") as f:
                    content = f.read()

                pmi_comment = f"/* STEP AP242 Semantic Model - Drawing2CAD Automated Conversion - Part: {part_name} */\n"
                if "HEADER;" in content:
                    content = content.replace("HEADER;", f"HEADER;\n{pmi_comment}")
                    with open(step_filepath, "w", encoding="latin-1") as f:
                        f.write(content)
            except Exception:
                pass

        return {
            "success": True,
            "filename": step_filename,
            "filepath": os.path.abspath(step_filepath),
            "filesize_bytes": file_size_bytes,
            "standard": version,
            "duration_seconds": duration
        }

    def write_summary_report(
        self,
        part_name: str,
        ir_json: Dict[str, Any],
        validation_report: ValidationReport,
        review_flags: list,
        output_path: Optional[str] = None
    ) -> str:
        """Write a comprehensive machine-readable and human-readable audit report."""
        safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in part_name)
        report_path = output_path or os.path.join(self.output_dir, f"{safe_name}_report.json")

        report_data = {
            "part_name": part_name,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status": "APPROVED" if validation_report.overall_pass else "NEEDS_REVIEW",
            "overall_pass": validation_report.overall_pass,
            "bounding_box": validation_report.bounding_box,
            "volume_mm3": validation_report.volume,
            "step_reimport_valid": validation_report.step_reimport_valid,
            "review_flags_count": len(review_flags),
            "review_flags": [f.model_dump() if hasattr(f, 'model_dump') else f for f in review_flags],
            "dimension_checks": [d.model_dump() if hasattr(d, 'model_dump') else d for d in validation_report.dimension_checks],
            "errors": validation_report.errors,
            "warnings": validation_report.warnings,
            "intermediate_representation": ir_json
        }

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2)

        return os.path.abspath(report_path)
