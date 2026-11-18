#!/usr/bin/env python3
"""Evaluate the trained checkpoint on the reserved design-held-out test set."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from ultralytics import YOLO


PROJECT = Path(__file__).resolve().parents[1]
DATA = PROJECT / "datasets" / "deeppcb_audit" / "yolo" / "data.yaml"
DEFAULT_WEIGHTS = PROJECT / "outputs" / "yolo_training" / "deeppcb_yolo26n_seed2026_02" / "weights" / "best.pt"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights", type=Path, default=DEFAULT_WEIGHTS)
    parser.add_argument("--data", type=Path, default=DATA, help="YOLO data.yaml")
    parser.add_argument("--device", default=None)
    parser.add_argument("--report", type=Path, default=None, help="Metrics JSON output path")
    args = parser.parse_args()
    weights = args.weights.expanduser().resolve()
    data = args.data.expanduser().resolve()
    if not weights.is_file():
        parser.error(f"Model checkpoint not found: {weights}")
    if not data.is_file():
        parser.error(f"Dataset configuration not found: {data}")
    device = args.device or ("mps" if torch.backends.mps.is_available() else "cpu")
    model = YOLO(str(weights))
    result = model.val(
        data=str(data),
        split="test",
        imgsz=640,
        device=device,
        workers=0,
        plots=True,
        project=str(PROJECT / "outputs" / "yolo_training"),
        name=f"{weights.parents[1].name}_heldout_test",
        exist_ok=True,
    )
    report = {
        "weights": str(weights),
        "dataset_config": str(data),
        "split": "design-held-out test",
        "device": device,
        "metrics": {key: float(value) for key, value in result.results_dict.items()},
    }
    report_path = args.report.expanduser().resolve() if args.report else weights.parents[1] / "test_metrics.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Saved report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
