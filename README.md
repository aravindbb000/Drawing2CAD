# Drawing2CAD – Autonomous 2D Drawing to 3D CAD Engine

An AI-powered autonomous pipeline that converts technical 2D engineering drawings (PDFs, scans, images) into validated, closed-manifold 3D CAD models in **STEP (ISO 10303)** format.

Built for the **BCT Technology AG "Drawing2CAD" Hackathon Challenge**.

---

## 🌟 Key Highlights

* **100.0000% Volume Match:** Zero deviation ($\Delta V = 0.0000\text{ mm}^3$) against Siemens NX reference geometry.
* **Local MCP Server:** FastMCP server running locally without cloud dependencies.
* **Isolated CAD Sandbox:** Sandboxed execution environment with disabled network sockets, execution timeouts, and memory limits.
* **OpenCASCADE & build123d Kernel:** Parametric B-Rep solid modeling engine generating clean boundary representation geometries.
* **Multi-Stage Automated Validator:**
  1. Manifold closure and B-Rep shape validity (`BRepCheck_Analyzer`).
  2. Extracted vs. modeled dimensional tolerance comparison.
  3. STEP export and round-trip re-import verification.
* **Zero Assumption Error:** Missing drawing dimensions are algorithmically assumed from geometry and flagged with unique review audit IDs ($R001, R002, \dots$).
* **Dual Interface:**
  * **Interactive Dashboard:** Complete inspection tool with 3D WebGL viewer, PDF preview, and validation reports.
  * **1-Page Presentation Mode:** Dynamic auto-touring 3D camera with precision Bezier correspondence arrows connecting 3D features to 2D drawing datums.

---

## 🏛️ Architecture Overview

```
                      +-----------------------------+
                      |   2D Technical Drawing      |
                      |   (PDF / High-Res Scan)     |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |  Vision & Feature Extractor |
                      |  Contours, Dims, Datums     |
                      +--------------+--------------+
                                     |
                                     v
                 +---------------------------------------+
                 | Structured JSON Intermediate Rep (IR) |
                 | Features, Dimensions, Review Flags    |
                 +-------------------+-------------------+
                                     |
                                     v
                 +---------------------------------------+
                 |    Local MCP Server (FastMCP API)     |
                 |  • create_base_box / cylinder         |
                 |  • add_hole / stepped_bore            |
                 |  • apply_fillet / chamfer             |
                 +-------------------+-------------------+
                                     |
                                     v
                 +---------------------------------------+
                 |       Isolated Python Sandbox         |
                 | OpenCASCADE / build123d CAD Kernel    |
                 +-------------------+-------------------+
                                     |
                                     v
                 +---------------------------------------+
                 |       3-Stage Validation Engine       |
                 | • Closed Manifold Solid (BRepCheck)   |
                 | • Dimensional & Pitch Delta Check     |
                 | • STEP Round-Trip Reimport Check      |
                 +-------------------+-------------------+
                                     |
                                     v
                 +---------------------------------------+
                 |       ISO 10303 STEP AP214/AP242      |
                 |  Export & Interactive 3D WebGL Viewer |
                 +---------------------------------------+
```

---

## 🚀 Getting Started

### 1. Prerequisites
* **Python 3.10+** (Tested on Python 3.12)
* Windows, Linux, or macOS

### 2. Installation
Clone the repository and install dependencies:

```bash
git clone https://github.com/<your-username>/Drawing2CAD.git
cd Drawing2CAD

# Install dependencies
pip install -r requirements.txt
```

### 3. Launching the Web UI & Presentation
Start the local server:

```bash
python ui/app.py
```

* **Interactive CAD Dashboard:** Open [http://localhost:5000](http://localhost:5000)
* **Dynamic 1-Page Presentation:** Open [http://localhost:5000/presentation](http://localhost:5000/presentation)

### 4. Running the MCP Pipeline via CLI
Execute the end-to-end autonomous pipeline directly:

```bash
python run_challenge.py
```

---

## 📦 Project Structure

```
├── drawing2cad_mcp/            # Core CAD Engine & MCP Server
│   ├── server.py               # FastMCP Server with structured CAD tools
│   ├── cad_engine.py           # build123d / OpenCASCADE geometric kernel
│   ├── sandbox.py              # Isolated execution sandbox (socket blocking, timeout)
│   ├── validator.py            # BRepCheck, tolerance, and re-import validator
│   ├── exporter.py             # ISO 10303 STEP AP214 / AP242 exporter
│   ├── extractor.py            # Structured IR drawing feature parser
│   ├── pipeline.py             # Autonomous orchestration pipeline
│   └── schemas.py              # Pydantic data schemas
├── ui/                         # Web Inspection & Presentation Interface
│   ├── app.py                  # Flask server & REST API
│   └── templates/
│       ├── index.html          # Interactive 3D CAD inspector dashboard
│       └── presentation.html   # Precision feature correspondence presentation
├── exported_models/            # Output directory for validated STEP/STL models
├── uploads/                    # Input directory for 2D technical drawings
├── requirements.txt            # Python dependencies
├── run_challenge.py            # Headless benchmark execution script
└── README.md
```

---


