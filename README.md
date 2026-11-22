# RGPIS-HDE PCB Inspection

> **Bharat AI-SoC Challenge 2026/27** — Fully offline, edge-deployable PCB defect inspection and engineering intelligence system.

This repository contains:
1. **Trained YOLO26n PCB Defect Detection Model** (`best.pt`) — **92.8% Precision**, **95.1% Recall**, mAP@50 96.57%.
2. **CERI + CEIA Analysis** — Geometric risk scoring and counterfactual electrical impact (geometry-based proxies, IPC-A-600 grounded).
3. **Engineering Intelligence Layer** — Llama 3.2 1B via ExecuTorch (100% offline, XNNPACK CPU) generating board-level reports, per-defect explanations, corrective action plans, process hypotheses, and an interactive Q&A interface.
4. **OpenCV reference-guided inspection prototype** — homography registration, difference mapping, cleanup, and validation.
5. **Full dataset release** with 5,100+ real PCB defect images and YOLO annotations.

---

## 🏗️ Full System Pipeline

```
Test Image
    │
    ▼
OpenCV (alignment & preprocessing)
    │
    ▼
YOLO26n Defect Detection  ──► detections.json
    │
    ▼
CERI (Geometric Risk)  +  CEIA (Electrical Proxy)
    │
    ▼
Unified Defect Scoring & Board Decision  ──► unified_report.json
    │
    ▼
Engineering Intelligence Layer (Llama 3.2 1B · ExecuTorch · XNNPACK)
    │
    ├── Board-Level Intelligence Report
    ├── Per-Defect Engineering Analysis (all 6 defect classes)
    ├── Prioritized Corrective Action Plan
    ├── Manufacturing Process Hypotheses
    └── Engineer Q&A Interface
         │
         ▼
    HTML Dashboard  +  Markdown Traveler  +  JSON Export
```

---

---

## 🤖 Engineering Intelligence Layer (NEW)

The Llama 3.2 1B model runs entirely **offline on-device** via ExecuTorch (XNNPACK CPU backend, SpinQuant INT4 quantization, ~1.03 GB model).

### Setup

```bash
# One-time: create the llama_advisory venv (Python 3.11 required)
python3.11 -m venv llama_advisory/venv
llama_advisory/venv/bin/pip install executorch==1.6.0 torch==2.15.0

# Download model (place at):
# llama_advisory/models/llama_3_2_1b_xnnpack_spinquant.pte
```

### Run Engineering Intelligence

```bash
# Fast mode — deterministic analysis in <1 second (no model load needed)
llama_advisory/venv/bin/python -m llama_advisory.run_engineering_intelligence --fast

# Full Llama mode — all 5 intelligence layers via ExecuTorch (~50-60s, ~1.1 GB RAM)
llama_advisory/venv/bin/python -m llama_advisory.run_engineering_intelligence

# Different image
llama_advisory/venv/bin/python -m llama_advisory.run_engineering_intelligence \
    --image deep_50600035.jpg

# Ask a specific question (Llama-powered Q&A)
llama_advisory/venv/bin/python -m llama_advisory.run_engineering_intelligence \
    --query "Why was this PCB rejected?"

# Interactive Q&A session
llama_advisory/venv/bin/python -m llama_advisory.run_engineering_intelligence --qa

# Full demo menu (includes options [6] Engineering Intelligence + [7] Q&A)
llama_advisory/venv/bin/python llama_advisory/demo.py
```

### Output Artifacts

All outputs are written to `outputs/intelligence/`:

| File | Description |
| :--- | :--- |
| `<board>_intelligence_dashboard.html` | Interactive HTML dashboard with defect map, risk charts, and per-defect cards |
| `<board>_engineering_report.md` | Markdown traveler report (board decision, priorities, corrective actions) |
| `<board>_engineering_intelligence.json` | Structured JSON export (all 5 intelligence layers, schema-validated) |

### Intelligence Layers

| Layer | Description | Engine |
| :--- | :--- | :--- |
| **Board-Level Report** | ACCEPT/REJECT decision, top risks, highest-priority defects | ExecuTorch Llama |
| **Per-Defect Analysis** | What/why/consequences/corrective action/verification for every defect | ExecuTorch Llama |
| **Corrective Action Plan** | IPC-A-600 grounded, ranked by unified score | Deterministic + Llama |
| **Process Hypotheses** | Cross-defect manufacturing pattern analysis (framed as hypotheses only) | ExecuTorch Llama |
| **Engineer Q&A** | Contextual answers grounded in actual CERI/CEIA/score data | Fast-path + Llama |

> **Note:** CEIA electrical values are geometry-based proxies computed from bounding-box dimensions — they are **not** physical bench measurements. All process patterns are explicitly labelled as *hypotheses*, not confirmed root causes.

### Verified Performance (Apple M-series CPU via XNNPACK)

| Metric | Value |
| :--- | :--- |
| Model load time | ~4.4 s |
| Board-level generation | ~17 s (307 prompt tokens) |
| Per-defect generation | ~24 s (475 prompt tokens) |
| Process intelligence | ~8 s (227 prompt tokens) |
| Peak RAM | ~1.1 GB |
| Fast-mode (deterministic) | <0.1 s |

---

## 🚀 Quick Start: YOLO Defect Detection

Test YOLO defect detection on any sample image using Apple MPS or CPU:

```bash
# Predict on a sample image
.venv/bin/yolo predict \
  model=outputs/yolo_training/deeppcb_dspcbsd_real6166_seed2026_02/weights/best.pt \
  source=test_images/deep_12100046.jpg \
  conf=0.25 \
  save=True \
  device=mps

# Or predict on all sample images
.venv/bin/yolo predict \
  model=outputs/yolo_training/deeppcb_dspcbsd_real6166_seed2026_02/weights/best.pt \
  source=test_images/ \
  conf=0.25 \
  save=True \
  device=mps
```
Results and annotated bounding box images are saved automatically to `runs/detect/predict/`.

---

## 📊 Model Performance (Held-out Test Set)

* **Overall Precision:** **92.82%**
* **Overall Recall:** **95.08%** (catches ~95 out of 100 defects)
* **mAP@50:** **96.57%**
* **mAP@50-95:** **77.75%**

| Defect Class | Precision | Recall | mAP@50 |
| :--- | :---: | :---: | :---: |
| **spur** | 100.00% | 97.57% | 99.22% |
| **pin-hole** | 100.00% | 99.27% | 99.50% |
| **copper** | 99.50% | 99.17% | 99.38% |
| **short** | 98.80% | 82.18% | 97.03% |
| **mousebite** | 98.54% | 98.39% | 99.17% |
| **open** | 60.09% | 93.92% | 85.15% |
| **Overall** | **92.82%** | **95.08%** | **96.57%** |

---

## 📦 Full Training Dataset (5,100+ Images)

The complete dataset (images + YOLO format annotations) is published as a release asset:
* **Direct Download:** [pcb_dataset_6167.zip (v1.0.0)](https://github.com/DarshanprasadV/RGPIS-HDE/releases/download/v1.0.0/pcb_dataset_6167.zip)
* **Releases Page:** [GitHub Releases v1.0.0](https://github.com/DarshanprasadV/RGPIS-HDE/releases/tag/v1.0.0)

To unpack and setup:
```bash
curl -L -o dataset.zip https://github.com/DarshanprasadV/RGPIS-HDE/releases/download/v1.0.0/pcb_dataset_6167.zip
unzip -q dataset.zip
```

---

## OpenCV Foundation


- Image loading, reference/test comparison, difference maps, and annotation visualization.
- ORB feature matching and RANSAC homography registration, with saved alignment outputs.
- Difference-map cleanup, defect-box coverage checks, and related visual outputs under `outputs/`.
- The bundled demo pair is 640 × 640 grayscale with 10 annotation boxes. These scripts demonstrate the processing steps; they do not by themselves establish validation across a production image set.

The class display in `image_processing/showannotation.py` now follows the DeepPCB README: ID 5 is copper and ID 6 is pin-hole.

### Dataset audit — prepared

The audit tool scans the DeepPCB `PCBData` directory, checks image/template/label pairing and bounding boxes, writes a manifest and issue list, creates a deterministic board-design-level split, and converts boxes to normalized YOLO `class x_center y_center width height` labels.

## Recreate the audit

```bash
python tools/audit_deeppcb.py \
  --source /path/to/DeepPCB-master/PCBData \
  --output datasets/deeppcb_audit
```

The tool uses the Python standard library. Generated files include:

- `datasets/deeppcb_audit/summary.json` — counts, class map, board-design split, and audit notes.
- `datasets/deeppcb_audit/manifest.csv` — one row per test image, including its template and annotation paths.
- `datasets/deeppcb_audit/issues.csv` — detected missing or malformed files and labels.
- `datasets/deeppcb_audit/yolo/data.yaml` — Ultralytics dataset configuration.
- `datasets/deeppcb_audit/yolo/images/{train,val,test}/` — symlinks to source test images.
- `datasets/deeppcb_audit/yolo/labels/{train,val,test}/` — converted YOLO labels, including empty label files where no boxes are present.

The generated image symlinks point to the source path used at audit time. If the source folder moves, rerun the audit. The split is seed-controlled; class balance and the held-out board designs should be reviewed and recorded alongside any model experiment.

## Dataset terms

The DeepPCB repository includes an MIT license file for repository code, while its README says the dataset may be used only for research. Treat the data as research-use-only unless the authors grant additional rights. Do not infer commercial data rights from the code license, and retain attribution and applicable notices when using or distributing permitted material.

## Dependencies

The existing OpenCV scripts use the packages listed in `requirements.txt`. The dataset audit itself has no third-party dependencies. YOLO training uses Ultralytics and PyTorch in the project-local `.venv` environment.

### YOLO baseline training

The project includes a VS Code task named **Train DeepPCB YOLO26n baseline**. Open this folder in VS Code, then choose **Terminal → Run Task** and select that task. It trains from `yolo26n.pt`, with seed 2026, 640-pixel inputs, batch size 8, and patience 20. The script selects Apple MPS when PyTorch reports it available, otherwise it uses CPU. Run artifacts are written under `outputs/yolo_training/`.

The first baseline run completed on the Apple M5 MPS device. It stopped at epoch 74 after early stopping; the best validation checkpoint was from epoch 55. The held-out design test evaluation is in `outputs/yolo_training/deeppcb_yolo26n_seed2026_02/test_metrics.json`, and a readable summary is in `outputs/yolo_training/deeppcb_yolo26n_seed2026_02/baseline_report.md`.

The pretrained checkpoint is downloaded on first run. The open-source Ultralytics package and models use AGPL-3.0; review that license before distributing this software or weights as part of a proprietary product. The current project use is a research/student prototype.
