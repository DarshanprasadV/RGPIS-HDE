# PCB Defect Detection Integration Guide (CERI & CEIA)

This guide documents the trained YOLO defect detection module for seamless integration into:
1. **CERI** — Geometric Defect Severity and Risk (trace-width loss, clearance intrusion).
2. **CEIA** — Counterfactual Electrical Impact Analysis (defect-affected copper regions, current-density simulation).

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
