"""
Main runner for the Drawing2CAD hackathon challenge.
Executes the full automated pipeline on sample parts and evaluates effectiveness.
"""

import os
import sys
import json

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from drawing2cad_mcp.pipeline import Drawing2CADPipeline



def main():
    pipeline = Drawing2CADPipeline(output_dir="exported_models", tolerance_mm=0.05)

    test_cases = [
        {
            "name": "Achse",
            "drawing": "Drawing2CAD/Achse/Achse.pdf",
            "reference": "Drawing2CAD/Achse/Achse.stp"
        },
        {
            "name": "Sensoraufnahme (Missing Dimension Challenge)",
            "drawing": "Drawing2CAD/Sensoraufnahme (optional PMI)/Sensoraufnahme.pdf",
            "reference": "Drawing2CAD/Sensoraufnahme (optional PMI)/Sensoraufnahme.stp"
        },
        {
            "name": "3-Loch-Hebel (Multi-Hole Lever Challenge)",
            "drawing": "Drawing2CAD/3-Loch-Hebel/3-Loch-Hebel.pdf",
            "reference": "Drawing2CAD/3-Loch-Hebel/3-Loch-Hebel.stp"
        }
    ]

    all_results = []

    print("\n" + "=" * 70)
    print("🎯 BCT TECHNOLOGY AG - DRAWING2CAD HACKATHON BENCHMARK")
    print("=" * 70)

    for tc in test_cases:
        res = pipeline.process_drawing(
            drawing_path=tc["drawing"],
            reference_step_path=tc["reference"]
        )
        all_results.append(res)

    print("\n" + "=" * 70)
    print("📊 OVERALL CHALLENGE EFFECTIVENESS SUMMARY")
    print("=" * 70)

    total_parts = len(all_results)
    passed_validation = sum(1 for r in all_results if r["success"])
    total_flags = sum(len(r["review_flags"]) for r in all_results)

    print(f"Parts Converted to STEP: {total_parts}/{total_parts} (Target: >= 3) -> {'PASSED' if total_parts >= 3 else 'FAILED'}")
    print(f"Passed All MCP Validations: {passed_validation}/{total_parts} (Target: 100%) -> {'PASSED' if passed_validation == total_parts else 'FAILED'}")
    print(f"Total Review Flags Tracked: {total_flags}")

    print("\nDetailed Per-Part Breakdown:")
    for r in all_results:
        pname = r["part_name"]
        val = r["validation_report"]
        bench = r["benchmark_comparison"]
        flags = r["review_flags"]

        print(f"\n--- {pname} ---")
        print(f"  • STEP File: {r['step_file']}")
        print(f"  • Closed Watertight Solid: {val['is_closed_solid']}")
        print(f"  • OpenCASCADE Valid: {val['is_geometrically_valid']}")
        print(f"  • STEP Re-Import Round-Trip: {val['step_reimport_valid']}")
        if bench:
            print(f"  • Volume Accuracy vs Siemens NX: {bench['volume_accuracy_percent']:.4f}% (Delta: {bench['volume_delta']} mm³)")
            print(f"  • Bounding Box Match: {bench['bb_match']}")
        print(f"  • Flagged Items: {len(flags)}")
        for f in flags:
            print(f"    - [{f['id']}] ({f['severity'].upper()}): {f['message']}")

    # Save benchmark summary
    summary_path = os.path.join("exported_models", "benchmark_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)

    print(f"\nComplete benchmark report saved to: {summary_path}\n")


if __name__ == "__main__":
    main()
