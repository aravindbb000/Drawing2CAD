"""
Flask web server for Drawing2CAD UI.
Provides REST API for 2D technical drawing viewing, automated MCP CAD generation,
validation checks, and interactive 3D WebGL preview.
"""

import os
import sys
import json
from flask import Flask, render_template, jsonify, request, send_from_directory, send_file
import pymupdf

# Ensure project root is on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from drawing2cad_mcp.pipeline import Drawing2CADPipeline

app = Flask(__name__, template_folder="templates")
pipeline = Drawing2CADPipeline(output_dir=os.path.join(BASE_DIR, "exported_models"))

SAMPLE_PARTS = [
    {
        "id": "Fuss",
        "name": "Fuss (Mounting Flange Foot)",
        "drawing_pdf": os.path.join(BASE_DIR, "Drawing2CAD", "Fuss", "Fuss_dwg.pdf"),
        "reference_stp": os.path.join(BASE_DIR, "Drawing2CAD", "Fuss", "Fuss.stp"),
        "preview_img": "Fuss_dwg.png",
        "description": "Square flange base (115x115x19) with 4x D19 holes, R9.5 fillet, central boss, and stepped bore."
    }
]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/presentation")
def presentation():
    return render_template("presentation.html")


@app.route("/api/samples", methods=["GET"])
def get_samples():
    return jsonify(SAMPLE_PARTS)


@app.route("/api/drawing/<filename>", methods=["GET"])
def get_drawing_image(filename):
    drawings_dir = os.path.join(BASE_DIR, "rendered_drawings")
    return send_from_directory(drawings_dir, filename)


@app.route("/api/model/<part_name>/stl", methods=["GET"])
def get_model_stl(part_name):
    exported_dir = os.path.join(BASE_DIR, "exported_models")
    filename = f"{part_name}.stl"
    return send_from_directory(exported_dir, filename, mimetype="model/stl")


@app.route("/api/model/<part_name>/step", methods=["GET"])
def download_step(part_name):
    exported_dir = os.path.join(BASE_DIR, "exported_models")
    filename = f"{part_name}.stp"
    filepath = os.path.join(exported_dir, filename)
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True, download_name=filename)
    return jsonify({"error": "File not found"}), 404


@app.route("/api/model/<part_name>/report", methods=["GET"])
def get_report(part_name):
    exported_dir = os.path.join(BASE_DIR, "exported_models")
    filename = f"{part_name}_report.json"
    filepath = os.path.join(exported_dir, filename)
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    return jsonify({"error": "Report not found"}), 404


@app.route("/api/convert", methods=["POST"])
def convert_part():
    data = request.json or {}
    part_id = data.get("part_id")

    sample = next((s for s in SAMPLE_PARTS if s["id"].lower() == part_id.lower()), None)
    if not sample:
        return jsonify({"error": f"Part ID '{part_id}' not found."}), 404

    # Run the Drawing2CAD pipeline
    result = pipeline.process_drawing(
        drawing_path=sample["drawing_pdf"],
        reference_step_path=sample["reference_stp"]
    )
    result["preview_img"] = sample["preview_img"]
    return jsonify(result)


@app.route("/api/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "Empty filename"}), 400

    uploads_dir = os.path.join(BASE_DIR, "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    save_path = os.path.join(uploads_dir, file.filename)
    file.save(save_path)

    drawings_dir = os.path.join(BASE_DIR, "rendered_drawings")
    os.makedirs(drawings_dir, exist_ok=True)

    # Render preview image if PDF or copy image
    base_stem = os.path.splitext(file.filename)[0]
    ext = os.path.splitext(file.filename)[1].lower()
    preview_img_name = f"{base_stem}.png"
    preview_img_path = os.path.join(drawings_dir, preview_img_name)
    try:
        if ext == ".pdf":
            doc = pymupdf.open(save_path)
            page = doc[0]
            pix = page.get_pixmap(dpi=200)
            pix.save(preview_img_path)
        else:
            import shutil
            shutil.copy2(save_path, preview_img_path)
    except Exception as e:
        print(f"Error rendering preview: {e}")

    # Check for corresponding reference STEP file in Drawing2CAD folders
    ref_step = None
    clean_stem = base_stem.replace("_dwg", "").replace("-dwg", "")
    for root, dirs, files in os.walk(os.path.join(BASE_DIR, "Drawing2CAD")):
        for f in files:
            if f.lower().endswith(".stp") and clean_stem.lower() in f.lower():
                ref_step = os.path.join(root, f)
                break
        if ref_step:
            break

    # Process uploaded drawing
    result = pipeline.process_drawing(drawing_path=save_path, reference_step_path=ref_step)
    result["preview_img"] = preview_img_name
    return jsonify(result)


if __name__ == "__main__":
    print("\n🚀 Starting Drawing2CAD Web UI on http://localhost:5000 ...")
    app.run(host="0.0.0.0", port=5000, debug=False)
