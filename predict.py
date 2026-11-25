#!/usr/bin/env python3
"""
predict.py - Production-ready YOLO PCB Defect Detection Module

Designed for direct integration with:
- CERI (Geometric Defect Severity and Risk: trace-width loss, clearance intrusion)
- CEIA (Counterfactual Electrical Impact Analysis: defect-affected copper regions & current density simulation)

Features:
- Programmatic import: `from predict import PCBDefectDetector, detect_defects`
- CLI execution: `python predict.py --source <image> --save-json --save-img`
- Strictly maps bounding boxes to original unscaled image pixel dimensions (x_min, y_min, x_max, y_max)
- Supports file paths, numpy ndarray (cv2 image), or PIL Image
- ROI extraction helper for geometric/electrical copper analysis
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import cv2
import numpy as np
from ultralytics import YOLO

# Project root and default weights
PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_WEIGHTS = (
    PROJECT_ROOT
    / "outputs"
    / "yolo_training"
    / "deeppcb_dspcbsd_real6166_seed2026_02"
    / "weights"
    / "best.pt"
)

# Standard DeepPCB / DsPCBSD 6-class taxonomy
CLASS_MAP = {
    0: "open",
    1: "short",
    2: "mousebite",
    3: "spur",
    4: "copper",
    5: "pin-hole",
}


class PCBDefectDetector:
    """
    YOLO-based PCB Defect Detector for downstream CERI and CEIA analysis modules.
    Keeps model loaded in memory for high-performance batch inference.
    """

    def __init__(
        self,
        weights: Union[str, Path] = DEFAULT_WEIGHTS,
        device: Optional[str] = None,
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.45,
    ):
        """
        Initialize detector with trained checkpoint.

        Args:
            weights: Path to trained best.pt checkpoint
            device: 'mps' (Apple Silicon), 'cuda', or 'cpu' (auto-detected if None)
            conf_threshold: Minimum detection confidence threshold
            iou_threshold: NMS IoU threshold
        """
        self.weights_path = Path(weights).resolve()
        if not self.weights_path.is_file():
            raise FileNotFoundError(f"Model checkpoint not found: {self.weights_path}")

        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold

        # Load YOLO model
        self.model = YOLO(str(self.weights_path))

        # Select device
        if device:
            self.device = device
        else:
            import torch
            if torch.backends.mps.is_available():
                self.device = "mps"
            elif torch.cuda.is_available():
                self.device = "cuda"
            else:
                self.device = "cpu"

        # Model classes mapping
        self.classes = getattr(self.model, "names", CLASS_MAP)

    def detect(
        self,
        image: Union[str, Path, np.ndarray],
        conf: Optional[float] = None,
        iou: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Run inference on an image and return structured detection results
        with bounding boxes in the original image pixel coordinates.

        Args:
            image: Path to image file, or OpenCV BGR/grayscale numpy array
            conf: Override confidence threshold (optional)
            iou: Override IoU threshold (optional)

        Returns:
            Structured dictionary ready for CERI / CEIA consumption:
            {
                "image_name": str,
                "image_path": str or None,
                "image_width": int,
                "image_height": int,
                "total_defects": int,
                "detections": [
                    {
                        "defect_id": int (1-based index),
                        "class_id": int,
                        "class_name": str,
                        "confidence": float (0.0 to 1.0),
                        "bbox": {
                            "x_min": float,
                            "y_min": float,
                            "x_max": float,
                            "y_max": float
                        },
                        "geometry": {
                            "width": float,
                            "height": float,
                            "center_x": float,
                            "center_y": float,
                            "area": float
                        }
                    }, ...
                ]
            }
        """
        conf = conf if conf is not None else self.conf_threshold
        iou = iou if iou is not None else self.iou_threshold

        image_path_str: Optional[str] = None
        image_name = "numpy_array"

        # Determine original dimensions
        if isinstance(image, (str, Path)):
            image_path = Path(image).resolve()
            if not image_path.is_file():
                raise FileNotFoundError(f"Image not found: {image_path}")
            image_path_str = str(image_path)
            image_name = image_path.name
            img_bgr = cv2.imread(image_path_str)
            if img_bgr is None:
                raise ValueError(f"Unable to read image at: {image_path_str}")
            orig_h, orig_w = img_bgr.shape[:2]
            source_input = image_path_str
        elif isinstance(image, np.ndarray):
            orig_h, orig_w = image.shape[:2]
            source_input = image
        else:
            raise TypeError(f"Unsupported image type: {type(image)}. Expected Path, str, or np.ndarray")

        # Run inference via Ultralytics
        results = self.model.predict(
            source=source_input,
            conf=conf,
            iou=iou,
            device=self.device,
            imgsz=640,
            save=False,
            verbose=False,
        )

        result = results[0]
        detections: List[Dict[str, Any]] = []

        if result.boxes is not None and len(result.boxes) > 0:
            boxes = result.boxes
            xyxy_arr = boxes.xyxy.cpu().numpy()  # original pixel coordinates
            conf_arr = boxes.conf.cpu().numpy()
            cls_arr = boxes.cls.cpu().numpy().astype(int)

            for idx, (box, score, cls_id) in enumerate(zip(xyxy_arr, conf_arr, cls_arr), start=1):
                x_min, y_min, x_max, y_max = [float(round(val, 2)) for val in box]
                
                # Clip coordinates to original image bounds
                x_min = max(0.0, min(float(orig_w), x_min))
                y_min = max(0.0, min(float(orig_h), y_min))
                x_max = max(0.0, min(float(orig_w), x_max))
                y_max = max(0.0, min(float(orig_h), y_max))

                w = round(x_max - x_min, 2)
                h = round(y_max - y_min, 2)
                cx = round(x_min + w / 2.0, 2)
                cy = round(y_min + h / 2.0, 2)
                area = round(w * h, 2)

                class_name = self.classes.get(cls_id, f"class_{cls_id}")

                detections.append({
                    "defect_id": idx,
                    "class_id": int(cls_id),
                    "class_name": class_name,
                    "confidence": float(round(score, 4)),
                    "bbox": {
                        "x_min": x_min,
                        "y_min": y_min,
                        "x_max": x_max,
                        "y_max": y_max,
                    },
                    "geometry": {
                        "width": w,
                        "height": h,
                        "center_x": cx,
                        "center_y": cy,
                        "area": area,
                    },
                })

        return {
            "image_name": image_name,
            "image_path": image_path_str,
            "image_width": int(orig_w),
            "image_height": int(orig_h),
            "total_defects": len(detections),
            "detections": detections,
        }

    def detect_batch(
        self,
        images: List[Union[str, Path, np.ndarray]],
        conf: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Run detection over a list of images."""
        return [self.detect(img, conf=conf) for img in images]

    def extract_rois(
        self,
        image: Union[str, Path, np.ndarray],
        detections: Optional[Dict[str, Any]] = None,
        padding: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Helper for CERI & CEIA:
        Extracts cropped Regions of Interest (ROI) around each defect from the
        original image with optional padding for geometric trace analysis.
        """
        if isinstance(image, (str, Path)):
            img = cv2.imread(str(image))
        else:
            img = image.copy()

        if detections is None:
            detections = self.detect(img)

        h, w = img.shape[:2]
        rois = []

        for det in detections["detections"]:
            bbox = det["bbox"]
            x1 = max(0, int(bbox["x_min"]) - padding)
            y1 = max(0, int(bbox["y_min"]) - padding)
            x2 = min(w, int(bbox["x_max"]) + padding)
            y2 = min(h, int(bbox["y_max"]) + padding)

            roi_patch = img[y1:y2, x1:x2]
            rois.append({
                "defect_id": det["defect_id"],
                "class_name": det["class_name"],
                "confidence": det["confidence"],
                "bbox_original": bbox,
                "crop_coords": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                "roi_image": roi_patch,
            })

        return rois

    def annotate_image(
        self,
        image: Union[str, Path, np.ndarray],
        detection_result: Optional[Dict[str, Any]] = None,
    ) -> np.ndarray:
        """Render annotated bounding boxes and labels onto the original image."""
        if isinstance(image, (str, Path)):
            annotated = cv2.imread(str(image))
        else:
            annotated = image.copy()

        if detection_result is None:
            detection_result = self.detect(annotated)

        # Color palette per class
        colors = {
            "open": (0, 0, 255),        # Red
            "short": (255, 0, 0),       # Blue
            "mousebite": (0, 165, 255),  # Orange
            "spur": (255, 0, 255),      # Magenta
            "copper": (0, 255, 255),    # Yellow
            "pin-hole": (0, 255, 0),    # Green
        }

        for det in detection_result["detections"]:
            cname = det["class_name"]
            score = det["confidence"]
            bbox = det["bbox"]
            color = colors.get(cname, (0, 255, 0))

            x1, y1 = int(bbox["x_min"]), int(bbox["y_min"])
            x2, y2 = int(bbox["x_max"]), int(bbox["y_max"])

            # Draw rectangle
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

            # Draw label
            label = f"{cname} {score:.2f}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(annotated, (x1, max(0, y1 - th - 6)), (x1 + tw + 4, y1), color, -1)
            cv2.putText(
                annotated,
                label,
                (x1 + 2, y1 - 4),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 0, 0) if cname in ("copper", "pin-hole") else (255, 255, 255),
                1,
                cv2.LINE_AA,
            )

        return annotated


# Standalone function for quick one-line calling
_global_detector: Optional[PCBDefectDetector] = None


def detect_defects(
    image: Union[str, Path, np.ndarray],
    weights: Union[str, Path] = DEFAULT_WEIGHTS,
    conf: float = 0.25,
    device: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Convenience function for modules to call in 1 line:
    ```python
    from predict import detect_defects
    results = detect_defects("path/to/pcb.jpg")
    ```
    """
    global _global_detector
    if _global_detector is None or str(_global_detector.weights_path) != str(Path(weights).resolve()):
        _global_detector = PCBDefectDetector(weights=weights, device=device, conf_threshold=conf)
    return _global_detector.detect(image, conf=conf)


def save_detection_csv(results: List[Dict[str, Any]], output_path: Union[str, Path]) -> None:
    """Save structured detection results to CSV format."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "image_name",
        "image_width",
        "image_height",
        "defect_id",
        "class_id",
        "class_name",
        "confidence",
        "x_min",
        "y_min",
        "x_max",
        "y_max",
        "box_width",
        "box_height",
        "area",
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for res in results:
            img_name = res["image_name"]
            img_w = res["image_width"]
            img_h = res["image_height"]
            for det in res["detections"]:
                bbox = det["bbox"]
                geo = det["geometry"]
                writer.writerow({
                    "image_name": img_name,
                    "image_width": img_w,
                    "image_height": img_h,
                    "defect_id": det["defect_id"],
                    "class_id": det["class_id"],
                    "class_name": det["class_name"],
                    "confidence": det["confidence"],
                    "x_min": bbox["x_min"],
                    "y_min": bbox["y_min"],
                    "x_max": bbox["x_max"],
                    "y_max": bbox["y_max"],
                    "box_width": geo["width"],
                    "box_height": geo["height"],
                    "area": geo["area"],
                })


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run PCB defect detection using trained YOLO checkpoint."
    )
    parser.add_argument(
        "--source",
        type=str,
        default="test_images/deep_12100046.jpg",
        help="Path to image file or directory of images",
    )
    parser.add_argument(
        "--weights",
        type=str,
        default=str(DEFAULT_WEIGHTS),
        help="Path to best.pt weights",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=0.25,
        help="Confidence threshold (default 0.25)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="outputs/predictions",
        help="Directory to save output files",
    )
    parser.add_argument(
        "--save-json",
        action="store_true",
        default=True,
        help="Save detections as JSON (default: True)",
    )
    parser.add_argument(
        "--save-csv",
        action="store_true",
        default=True,
        help="Save detections as CSV (default: True)",
    )
    parser.add_argument(
        "--save-img",
        action="store_true",
        default=True,
        help="Save annotated visualization image (default: True)",
    )
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="Inference device: 'mps', 'cuda', 'cpu'",
    )

    args = parser.parse_args()
    source_path = Path(args.source)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Collect images
    if source_path.is_dir():
        image_files = sorted(
            [p for p in source_path.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp")]
        )
    elif source_path.is_file():
        image_files = [source_path]
    else:
        raise FileNotFoundError(f"Source not found: {source_path}")

    print(f"Loaded {len(image_files)} image(s) from {source_path}")
    detector = PCBDefectDetector(weights=args.weights, device=args.device, conf_threshold=args.conf)

    all_results = []
    for img_path in image_files:
        res = detector.detect(img_path)
        all_results.append(res)
        print(f"[{res['image_name']}] Found {res['total_defects']} defect(s):")
        for det in res["detections"]:
            print(
                f"  - {det['class_name'].upper():10s} (conf: {det['confidence']:.2f}) "
                f"at [{det['bbox']['x_min']}, {det['bbox']['y_min']}, {det['bbox']['x_max']}, {det['bbox']['y_max']}]"
            )

        if args.save_img:
            annotated = detector.annotate_image(img_path, res)
            out_img_path = output_dir / f"{img_path.stem}_annotated.jpg"
            cv2.imwrite(str(out_img_path), annotated)
            print(f"  Saved visual annotation -> {out_img_path}")

    if args.save_json:
        json_path = output_dir / "detections.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(all_results if len(all_results) > 1 else all_results[0], f, indent=2)
        print(f"Saved JSON detections -> {json_path}")

    if args.save_csv:
        csv_path = output_dir / "detections.csv"
        save_detection_csv(all_results, csv_path)
        print(f"Saved CSV detections -> {csv_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
