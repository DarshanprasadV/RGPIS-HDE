import json
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parent.parent

REFERENCE_IMAGE = ROOT / "datasets/reference/golden.png"
TEST_IMAGE = ROOT / "datasets/test/test.png"
DETECTIONS_JSON = ROOT / "outputs/ceri_ceia/yolo_test/detections.json"

OUTPUT_DIR = ROOT / "outputs/ceri_ceia/ceri"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# Prototype heuristic risk weights.
# These are not IPC standards or experimentally validated thresholds.
CLASS_BASE_RISK = {
    "open": 95,
    "short": 100,
    "mousebite": 55,
    "spur": 60,
    "copper": 45,
    "pin-hole": 40,
}


def load_image(path):
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)

    if image is None:
        raise FileNotFoundError(f"Could not read image: {path}")

    return image


def copper_mask(image):
    """Extract dark PCB copper-like regions from a grayscale image."""

    _, mask = cv2.threshold(
        image,
        127,
        255,
        cv2.THRESH_BINARY_INV
    )

    return mask


def risk_category(score):
    if score >= 80:
        return "CRITICAL"
    elif score >= 60:
        return "HIGH"
    elif score >= 35:
        return "MODERATE"
    else:
        return "LOW"


def analyze_detection(detection, reference_mask, test_mask, padding=8):

    bbox = detection["bbox"]

    x1 = int(max(0, bbox["x_min"] - padding))
    y1 = int(max(0, bbox["y_min"] - padding))
    x2 = int(min(test_mask.shape[1], bbox["x_max"] + padding))
    y2 = int(min(test_mask.shape[0], bbox["y_max"] + padding))

    ref_roi = reference_mask[y1:y2, x1:x2]
    test_roi = test_mask[y1:y2, x1:x2]

    total_pixels = ref_roi.size

    if total_pixels == 0:
        return {
            "defect_id": detection["defect_id"],
            "class_name": detection["class_name"],
            "error": "Empty ROI"
        }

    ref_copper_pixels = int(cv2.countNonZero(ref_roi))
    test_copper_pixels = int(cv2.countNonZero(test_roi))

    area_loss = max(0, ref_copper_pixels - test_copper_pixels)
    area_gain = max(0, test_copper_pixels - ref_copper_pixels)

    area_loss_percent = (
        area_loss / ref_copper_pixels * 100
        if ref_copper_pixels > 0 else 0
    )

    area_gain_percent = (
        area_gain / ref_copper_pixels * 100
        if ref_copper_pixels > 0 else 0
    )

    # Pixel-level comparison between the reference and defective ROI.
    difference = cv2.absdiff(ref_roi, test_roi)

    changed_pixels = int(cv2.countNonZero(difference))

    changed_percent = (
        changed_pixels / total_pixels * 100
    )

    class_name = detection["class_name"].lower()

    base_risk = CLASS_BASE_RISK.get(class_name, 40)

    confidence = float(detection["confidence"])

    confidence_adjusted = base_risk * confidence

    # Geometry-change contribution (prototype heuristic).
    geometry_bonus = min(20, changed_percent * 0.5)

    risk_score = min(
        100,
        round(confidence_adjusted + geometry_bonus, 2)
    )

    # Class-specific minimum risk overrides.
    if class_name == "open":
        risk_score = max(risk_score, 90)

    elif class_name == "short":
        risk_score = max(risk_score, 95)

    return {
        "defect_id": detection["defect_id"],
        "class_name": class_name,
        "confidence": round(confidence, 4),
        "bbox": bbox,

        "roi": {
            "x_min": x1,
            "y_min": y1,
            "x_max": x2,
            "y_max": y2,
            "width": x2 - x1,
            "height": y2 - y1
        },

        "geometry_metrics": {
            "reference_copper_pixels": ref_copper_pixels,
            "test_copper_pixels": test_copper_pixels,
            "copper_area_loss_pixels": area_loss,
            "copper_area_gain_pixels": area_gain,
            "copper_area_loss_percent": round(
                area_loss_percent, 2
            ),
            "copper_area_gain_percent": round(
                area_gain_percent, 2
            ),
            "changed_pixels": changed_pixels,
            "changed_area_percent": round(
                changed_percent, 2
            )
        },

        "risk": {
            "score": risk_score,
            "category": risk_category(risk_score),
            "method": (
                "Class base risk × YOLO confidence + "
                "capped geometry change contribution"
            )
        },

        "measurement_status": (
            "PIXEL_BASED_ESTIMATE"
            if ref_copper_pixels > 0
            else "REFERENCE_COPPER_NOT_FOUND"
        )
    }


def main():

    reference = load_image(REFERENCE_IMAGE)
    test = load_image(TEST_IMAGE)

    if reference.shape != test.shape:
        raise ValueError(
            "Reference and test image dimensions differ. "
            "Registration is required before analysis."
        )

    reference_mask = copper_mask(reference)
    test_mask = copper_mask(test)

    with open(DETECTIONS_JSON, "r") as file:
        detection_data = json.load(file)

    results = []

    for detection in detection_data["detections"]:

        result = analyze_detection(
            detection,
            reference_mask,
            test_mask
        )

        results.append(result)

    valid_results = [
        result for result in results
        if "risk" in result
    ]

    summary = {
        "project": "RGPIS-HDE",
        "module": "CERI",
        "version": "0.1",
        "reference_image": str(REFERENCE_IMAGE),
        "test_image": str(TEST_IMAGE),
        "total_detections": len(results),

        "risk_distribution": {
            category: sum(
                1 for result in valid_results
                if result["risk"]["category"] == category
            )
            for category in [
                "CRITICAL",
                "HIGH",
                "MODERATE",
                "LOW"
            ]
        },

        "detections": results,

        "limitations": [
            "Measurements are pixel-based; no physical scale calibration is applied.",
            "YOLO bounding boxes are defect ROIs, not precise defect boundaries.",
            "Threshold-based copper segmentation may include image artifacts.",
            "Risk values use prototype heuristics and are not IPC-certified.",
            "Electrical impact is not calculated by CERI."
        ]
    }

    output_json = OUTPUT_DIR / "ceri_report.json"

    with open(output_json, "w") as file:
        json.dump(summary, file, indent=2)

    print("\n" + "=" * 55)
    print("CERI GEOMETRIC DEFECT RISK REPORT")
    print("=" * 55)

    print("Total detections:", len(results))

    for result in results:

        if "risk" not in result:
            print(
                "Defect",
                result["defect_id"],
                ": ERROR"
            )
            continue

        metrics = result["geometry_metrics"]

        print(
            f"\n#{result['defect_id']} "
            f"{result['class_name'].upper():10}"
            f" | Risk: {result['risk']['score']:5.1f}"
            f" | {result['risk']['category']}"
        )

        print(
            f"  Copper area loss: "
            f"{metrics['copper_area_loss_percent']:.2f}%"
            f" | Area gain: "
            f"{metrics['copper_area_gain_percent']:.2f}%"
            f" | Changed ROI: "
            f"{metrics['changed_area_percent']:.2f}%"
        )

    print("\nRisk distribution:", summary["risk_distribution"])
    print("\nReport saved:", output_json)


if __name__ == "__main__":
    main()
