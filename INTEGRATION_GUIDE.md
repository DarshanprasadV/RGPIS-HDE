# RGPIS-HDE Integration Guide

This guide documents all integration layers of the RGPIS-HDE pipeline:
1. **YOLO Defect Detection** — trained YOLO26n model, Python API, JSON/CSV output schema.
2. **CERI** — Geometric Defect Severity and Risk (trace-width loss, clearance intrusion).
3. **CEIA** — Counterfactual Electrical Impact Analysis (geometry-based proxies, current-density model).
4. **Unified Scoring** — combined P1–P4 priority ranking and board ACCEPT/REJECT decision.
5. **Engineering Intelligence Layer** — ExecuTorch Llama 3.2 1B producing structured reports, per-defect explanations, corrective actions, process hypotheses, and Q&A.

---

## 1. Trained Model & Checkpoint Specifications

* **Checkpoint Location:**  
  `outputs/yolo_training/deeppcb_dspcbsd_real6166_seed2026_02/weights/best.pt`
* **Architecture:** YOLO26n (2.39M parameters, 5.4 GFLOPs, ~3.8ms inference on Apple MPS)
* **Dataset Config:** `datasets/mixed_real_6167/yolo/data.yaml`
* **Training Dataset:** 6,166 real PCB boards (DeepPCB + DsPCBSD+)

### Defect Class Taxonomy & ID Mapping

| Class ID | Class Name | Common Defect Pattern | Primary Downstream Impact |
| :---: | :---: | :--- | :--- |
| **0** | `open` | Broken / discontinuous trace | Open circuit, zero conductivity (CERI / CEIA) |
| **1** | `short` | Spurious copper bridge between distinct traces | Short circuit, severe leakage / cross-talk |
| **2** | `mousebite` | Concave bite/edge nick on copper trace | Trace-width loss, localized resistance increase |
| **3** | `spur` | Narrow copper projection/protrusion | Clearance intrusion, potential dielectric breakdown |
| **4** | `copper` | Isolated unwanted copper patch | Capacitive coupling, clearance reduction |
| **5** | `pin-hole` | Microscopic void/hole inside copper area | Resistance hot-spot, current concentration |

### Evaluation Metrics (Design-Held-Out Test Set)

* **Overall Precision:** **92.82%**
* **Overall Recall:** **95.08%**
* **mAP@50:** **96.57%**
* **mAP@50-95:** **77.75%**

---

## 2. Python Programmatic API (`predict.py`)

The module can be directly imported into your Python codebase without subprocess or CLI overhead:

```python
from predict import PCBDefectDetector, detect_defects
import cv2

# Method A: One-line detection
results = detect_defects("path/to/aligned_pcb.jpg", conf=0.25)
print(f"Total defects found: {results['total_defects']}")

# Method B: Reusable detector class (recommended for pipelines)
detector = PCBDefectDetector()

# Accepts file path OR OpenCV numpy image array (e.g. from registration module)
img_bgr = cv2.imread("test_images/deep_12100052.jpg")
results = detector.detect(img_bgr, conf=0.25)

for det in results["detections"]:
    print(f"Defect #{det['defect_id']}: {det['class_name']} ({det['confidence']:.2f})")
    bbox = det["bbox"]
    print(f"  Coordinates: [{bbox['x_min']}, {bbox['y_min']}, {bbox['x_max']}, {bbox['y_max']}]")
```

---

## 3. Structured Output Schema

The output coordinates strictly map to the **original unscaled PCB image coordinates** (not the internal 640×640 YOLO tensor size).

### JSON Schema
```json
{
  "image_name": "deep_12100046.jpg",
  "image_path": "/path/to/deep_12100046.jpg",
  "image_width": 640,
  "image_height": 640,
  "total_defects": 6,
  "detections": [
    {
      "defect_id": 1,
      "class_id": 4,
      "class_name": "copper",
      "confidence": 0.9250,
      "bbox": {
        "x_min": 383.26,
        "y_min": 179.71,
        "x_max": 427.11,
        "y_max": 227.38
      },
      "geometry": {
        "width": 43.85,
        "height": 47.67,
        "center_x": 405.19,
        "center_y": 203.55,
        "area": 2090.33
      }
    }
  ]
}
```

### CSV Schema (`outputs/predictions/detections.csv`)
Columns:
`image_name, image_width, image_height, defect_id, class_id, class_name, confidence, x_min, y_min, x_max, y_max, box_width, box_height, area`

---

## 4. Integration with CERI & CEIA

### A. CERI Integration (Geometric Severity & Trace Width Loss)
Use the built-in `extract_rois()` helper to extract defect crops with customizable padding around traces:

```python
from predict import PCBDefectDetector
import cv2

detector = PCBDefectDetector()
img = cv2.imread("test_images/deep_12100046.jpg")
detections = detector.detect(img)

# Extract cropped image patches around each defect
rois = detector.extract_rois(img, detections, padding=15)

for roi in rois:
    patch = roi["roi_image"]  # numpy ndarray of the defect area
    bbox = roi["bbox_original"]
    
    if roi["class_name"] in ("mousebite", "open"):
        # CERI: Compute remaining copper trace width vs nominal width
        print(f"Analyzing trace reduction for {roi['class_name']} at {bbox}")
    elif roi["class_name"] in ("spur", "copper"):
        # CERI: Compute clearance intrusion into neighbouring conductor
        print(f"Analyzing clearance distance for {roi['class_name']} at {bbox}")
```

### B. CEIA Integration (Counterfactual Electrical Impact)
For current-density simulation:
1. Use `bbox` coordinates to isolate the local resistance grid node.
2. For an `open`, set nodal conductance $G_{ij} = 0$.
3. For a `short`, add bridge conductance $G_{bridge} = \sigma \cdot \frac{A}{L}$.
4. For a `mousebite`, reduce cross-sectional area proportional to `geometry.area` to model current bottlenecking.

---

## 5. Note on Segmentation Masks
The primary YOLO model is an **Object Detection** network (`yolo26n` bounding boxes). If pixel-level binary masks of the defect area are required for trace geometry:
1. Extract the ROI using `detector.extract_rois(image, padding=10)`.
2. Apply Otsu / Adaptive thresholding or difference comparison against the golden reference template (`datasets/reference/golden.png`) on that local ROI patch to get the exact binary copper pixel mask.

---

## 6. CLI Usage

To batch process images and export both JSON, CSV, and visual annotated images:

```bash
python predict.py \
  --source test_images/ \
  --output-dir outputs/predictions \
  --conf 0.25 \
  --save-json \
  --save-csv \
  --save-img
```
Outputs are written to:
* `outputs/predictions/detections.json`
* `outputs/predictions/detections.csv`
* `outputs/predictions/*_annotated.jpg`

---

## 5. Engineering Intelligence Layer

The Engineering Intelligence Layer consumes the **unified defect report** (`unified_report.json`) produced by CERI + CEIA + unified scoring and generates five structured intelligence outputs via **Llama 3.2 1B running 100% offline on ExecuTorch (XNNPACK CPU)**.

### Architecture

```
outputs/predictions/detections.json
        │
        ▼
llama_advisory/unified_pipeline_bridge.py   ← computes CERI, CEIA, Unified Scores
        │
        ▼
llama_advisory/sample_unified_report.json   ← intermediate structured board report
        │
        ▼
llama_advisory/engineering_intelligence.py  ← orchestrates all 5 Llama inference passes
        │
        ├── llama_advisory/prompt_templates.py    ← prompt builders + schema validators
        ├── llama_advisory/executorch_engine.py   ← ExecuTorch XNNPACK inference wrapper
        └── llama_advisory/engineer_qa.py         ← contextual Q&A (fast-path + Llama)
        │
        ▼
llama_advisory/dashboard_generator.py      ← HTML dashboard + Markdown traveler + JSON
        │
        ▼
outputs/intelligence/<board>_intelligence_dashboard.html
outputs/intelligence/<board>_engineering_report.md
outputs/intelligence/<board>_engineering_intelligence.json
```

### Output JSON Schema (`engineering_intelligence.json`)

```json
{
  "board_id": "deep_12100046",
  "analysis_timestamp": "2026-11-22T...",
  "board_decision": "REJECT",
  "board_condition_summary": "...",
  "unified_score": 99.1,
  "total_defects": 6,
  "board_intelligence": {
    "major_risks": ["Open circuit: complete trace discontinuity at defect #1", "..."],
    "immediate_priorities": ["Defect #1 (OPEN): P1 Critical — rework or scrap", "..."],
    "decision_rationale": "...",
    "engine": "ExecuTorch-XNNPACK"
  },
  "defect_intelligence": [
    {
      "defect_id": 1,
      "class_name": "open",
      "priority": "P1",
      "unified_score": 99.1,
      "what_detected": "...",
      "why_significant": "...",
      "engineering_consequences": "...",
      "region_inspection": "...",
      "corrective_action": "...",
      "verification": "...",
      "ceri_risk_score": 0.95,
      "ceia_risk_score": 0.98,
      "engine": "ExecuTorch-XNNPACK"
    }
  ],
  "corrective_actions": {
    "summary": "...",
    "prioritized_actions": ["1. ...", "2. ..."],
    "ipc_references": ["IPC-A-600 Class 3", "..."]
  },
  "process_intelligence": {
    "pattern_summary": "...",
    "fab_stage_hypotheses": ["Etching process variation hypothesis: ...", "..."],
    "investigation_areas": ["..."],
    "confidence_note": "These are geometric-pattern hypotheses, not confirmed root causes."
  },
  "qa_session": null
}
```

> **Important:** `ceia_risk_score` and all CEIA electrical values are **geometry-based proxies** computed from bounding-box dimensions using counterfactual resistance network formulas. They are **not** physical bench measurements. Always display the `confidence_note` from `process_intelligence` to downstream consumers.

### Downstream Consumer Integration

**AOI / MES Systems** can ingest the JSON directly:

```python
import json

with open("outputs/intelligence/deep_12100046_engineering_intelligence.json") as f:
    ei = json.load(f)

decision   = ei["board_decision"]          # "ACCEPT" or "REJECT"
score      = ei["unified_score"]           # 0–100
priorities = ei["board_intelligence"]["immediate_priorities"]
actions    = ei["corrective_actions"]["prioritized_actions"]

for defect in ei["defect_intelligence"]:
    if defect["priority"] == "P1":
        print(f"[CRITICAL] {defect['class_name']} #{defect['defect_id']}: {defect['corrective_action']}")
```

**Q&A Interface** can be driven programmatically:

```python
from llama_advisory.engineer_qa import EngineerQA

qa = EngineerQA(unified_report_path="llama_advisory/sample_unified_report.json")
answer = qa.answer("Which defect is most critical?")
print(answer["answer"])
```

### CLI Reference

```bash
# Engineering Intelligence runner
llama_advisory/venv/bin/python -m llama_advisory.run_engineering_intelligence [OPTIONS]

Options:
  --image IMAGE     Source image name in test_images/ (default: deep_12100046.jpg)
  --file FILE       Load unified report directly from JSON file
  --fast            Deterministic mode — no model load, <0.1s
  --all-llama       Run Llama inference for every defect (not just first)
  --query QUERY     Answer a single question (Llama-powered)
  --qa              Launch interactive Q&A session
```

### Python Module Map

| Module | Role |
| :--- | :--- |
| `unified_pipeline_bridge.py` | Bridges YOLO detections → CERI/CEIA/Unified Score computation |
| `engineering_intelligence.py` | Orchestrates all 5 Llama inference passes |
| `engineer_qa.py` | Contextual Q&A (5 fast-path deterministic + open-ended Llama) |
| `dashboard_generator.py` | Generates HTML dashboard, Markdown traveler, JSON export |
| `run_engineering_intelligence.py` | Unified CLI entry point |
| `prompt_templates.py` | Prompt builders and schema validators for all 5 intelligence layers |
| `executorch_engine.py` | ExecuTorch XNNPACK inference wrapper (model load, generate, timing) |
| `demo.py` | Interactive demo menu — options [6] Engineering Intelligence, [7] Q&A |
