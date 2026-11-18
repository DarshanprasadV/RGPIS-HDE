# RGPIS-HDE PCB Inspection

This repository contains the OpenCV reference-guided inspection prototype and the next roadmap phase, a DeepPCB dataset audit with YOLO label preparation. The DeepPCB images remain in their original location; the generated YOLO image folders use symlinks to that source.

## Current progress

### OpenCV foundation — implemented in the supplied project

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
