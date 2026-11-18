#!/usr/bin/env python3
"""Fine-tune a pretrained Ultralytics detector on the audited DeepPCB split."""

from __future__ import annotations

import argparse
from pathlib import Path

import torch
from ultralytics import YOLO


PROJECT = Path(__file__).resolve().parents[1]
DATA = PROJECT / "datasets" / "deeppcb_audit" / "yolo" / "data.yaml"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="yolo26n.pt", help="Pretrained Ultralytics model checkpoint")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--data", type=Path, default=DATA, help="YOLO data.yaml (defaults to audited DeepPCB)")
    parser.add_argument("--patience", type=int, default=20, help="Early stopping patience")
    parser.add_argument("--device", default=None, help="Training device (auto: MPS if available, otherwise CPU)")
    parser.add_argument("--name", default="deeppcb_yolo26n_seed2026")
    args = parser.parse_args()
    data = args.data.expanduser().resolve()
    if not data.is_file():
        parser.error(f"Dataset configuration not found: {data}")

    device = args.device or ("mps" if torch.backends.mps.is_available() else "cpu")
    print(f"Training device: {device}")
    run_root = PROJECT / "outputs" / "yolo_training"
    run_name = args.name
    suffix = 2
    while (run_root / run_name).exists():
        run_name = f"{args.name}_{suffix:02d}"
        suffix += 1
    if run_name != args.name:
        print(f"Using fresh run name: {run_name}")
    model = YOLO(args.model)
    result = model.train(
        data=str(data),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=device,
        workers=0,
        seed=2026,
        deterministic=True,
        pretrained=True,
        patience=args.patience,
        close_mosaic=10,
        cache=False,
        project=str(run_root),
        name=run_name,
        exist_ok=False,
        plots=True,
        save=True,
        val=True,
    )
    print(f"Training finished. Run directory: {result.save_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
