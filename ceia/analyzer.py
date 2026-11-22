
import cv2
import json
import csv
import os
import math
import argparse

# ============================================================
# CEIA - Counterfactual Electrical Impact Analysis
# Version 0.2
#
# Reference-guided regional copper discrepancy analysis and
# simplified electrical impact estimation.
#
# IMPORTANT:
# This is a software prototype, not a PCB field solver.
# Regional copper ratio is NOT actual trace cross-section.
# Electrical estimates are NOT experimentally validated.
# ============================================================


# ------------------------- CONFIGURATION -------------------------

COPPER_RESISTIVITY = 1.68e-8  # Ohm-meter, approximate at 20 C

DEFAULT_CURRENT = 1.0
DEFAULT_TRACE_WIDTH_MM = 0.50
DEFAULT_COPPER_THICKNESS_UM = 35.0
DEFAULT_TRACE_LENGTH_MM = 50.0

ROI_PADDING = 8
MIN_AREA_RATIO = 0.01
SEGMENTATION_THRESHOLD = 127

SUPPORTED_DEFECT_CLASSES = {
    "open",
    "short",
    "mousebite",
    "spur",
    "pin-hole",
    "copper"
}


# ------------------------- UTILITIES ---------------------------

def load_image(path):
    image = cv2.imread(path, cv2.IMREAD_GRAYSCALE)

    if image is None:
        raise FileNotFoundError(
            f"Could not load image: {path}"
        )

    return image


def load_json(path):
    with open(path, "r") as file:
        return json.load(file)


def extract_detections(data):
    """
    Supports a list of detections or a dictionary containing
    a 'detections' list.
    """

    if isinstance(data, list):
        return data

    if isinstance(data, dict) and "detections" in data:

        detections = data["detections"]

        if isinstance(detections, list):
            return detections

    raise ValueError(
        "Could not locate a valid detections list in YOLO JSON."
    )


def extract_bbox(detection):
    """
    Supports:
        bbox = {
            x_min, y_min, x_max, y_max
        }

    and:
        bbox = [x1, y1, x2, y2]
    """

    bbox = detection.get("bbox")

    if bbox is None:
        bbox = detection.get("box")

    if bbox is None:
        raise ValueError(
            "Detection does not contain bbox or box."
        )

    if isinstance(bbox, dict):

        required = [
            "x_min",
            "y_min",
            "x_max",
            "y_max"
        ]

        if not all(key in bbox for key in required):
            raise ValueError(
                f"Incomplete bbox dictionary: {bbox}"
            )

        return (
            float(bbox["x_min"]),
            float(bbox["y_min"]),
            float(bbox["x_max"]),
            float(bbox["y_max"])
        )

    if isinstance(bbox, (list, tuple)) and len(bbox) == 4:

        return tuple(map(float, bbox))

    raise ValueError(
        f"Unsupported bbox format: {bbox}"
    )


def get_class_name(detection):

    class_name = detection.get(
        "class_name",
        detection.get("class", "unknown")
    )

    return str(class_name).strip().lower()


def get_confidence(detection):

    try:
        confidence = float(
            detection.get("confidence", 0.0)
        )

    except (TypeError, ValueError):
        confidence = 0.0

    return max(0.0, min(1.0, confidence))


def copper_mask(image):
    """
    Assumption:
    Copper is darker than the background.

    Dark pixels become white foreground pixels.
    """

    _, mask = cv2.threshold(
        image,
        SEGMENTATION_THRESHOLD,
        255,
        cv2.THRESH_BINARY_INV
    )

    return mask


def clamp_bbox(
    bbox,
    image_shape,
    padding=ROI_PADDING
):
    height, width = image_shape[:2]

    x1, y1, x2, y2 = bbox

    if not all(math.isfinite(v) for v in bbox):
        raise ValueError(
            "Bounding box contains non-finite coordinates."
        )

    # Normalize coordinate order.
    left = min(x1, x2)
    right = max(x1, x2)
    top = min(y1, y2)
    bottom = max(y1, y2)

    x1 = max(
        0,
        int(math.floor(left)) - padding
    )

    y1 = max(
        0,
        int(math.floor(top)) - padding
    )

    x2 = min(
        width,
        int(math.ceil(right)) + padding
    )

    y2 = min(
        height,
        int(math.ceil(bottom)) + padding
    )

    if x2 <= x1 or y2 <= y1:
        raise ValueError(
            "Bounding box is outside the image or invalid."
        )

    return x1, y1, x2, y2


def safe_percentage_change(before, after):

    if before is None or after is None:
        return None

    if before <= 0:
        return None

    return (
        (after - before) / before
    ) * 100.0


def validate_parameters(
    current,
    trace_width_mm,
    trace_length_mm,
    copper_thickness_um
):

    values = {
        "current": current,
        "trace_width_mm": trace_width_mm,
        "trace_length_mm": trace_length_mm,
        "copper_thickness_um": copper_thickness_um
    }

    for name, value in values.items():

        if not math.isfinite(value):
            raise ValueError(
                f"{name} must be finite."
            )

    if current <= 0:
        raise ValueError(
            "Current must be greater than zero."
        )

    if trace_width_mm <= 0:
        raise ValueError(
            "Trace width must be greater than zero."
        )

    if trace_length_mm <= 0:
        raise ValueError(
            "Trace length must be greater than zero."
        )

    if copper_thickness_um <= 0:
        raise ValueError(
            "Copper thickness must be greater than zero."
        )


# ------------------------- ELECTRICAL MODEL ---------------------

def calculate_electrical_parameters(
    current,
    trace_length_mm,
    trace_width_mm,
    copper_thickness_um,
    copper_ratio
):
    """
    Simplified uniform-trace electrical model.

    Copper ratio is an ROI-level image-derived proxy.

    It is NOT a measurement of the actual trace cross-section.

    The model assumes:
        - Uniform trace width
        - Uniform copper thickness
        - Uniform current distribution
        - Constant current
        - Copper resistivity at approximately 20 C
        - Regional copper ratio approximates remaining
          conductive cross-sectional area

    These assumptions are not physically established
    by the input PCB images.
    """

    if copper_ratio is None:
        raise ValueError(
            "Copper ratio is unavailable."
        )

    if not math.isfinite(copper_ratio):
        raise ValueError(
            "Copper ratio must be finite."
        )

    # --------------------------------------------------------
    # UNIT CONVERSION
    # --------------------------------------------------------

    length_m = trace_length_mm / 1000.0
    width_m = trace_width_mm / 1000.0
    thickness_m = copper_thickness_um / 1e6

    healthy_area = width_m * thickness_m

    # Copper loss is modeled as a reduced cross-sectional area.
    # Copper gain is not used to increase nominal trace area,
    # because ROI copper gain may be unrelated to trace width.
    defective_ratio = max(
        MIN_AREA_RATIO,
        min(1.0, copper_ratio)
    )

    defective_area = (
        healthy_area * defective_ratio
    )

    # --------------------------------------------------------
    # RESISTANCE
    # --------------------------------------------------------

    healthy_resistance = (
        COPPER_RESISTIVITY
        * length_m
        / healthy_area
    )

    defective_resistance = (
        COPPER_RESISTIVITY
        * length_m
        / defective_area
    )

    # --------------------------------------------------------
    # CURRENT DENSITY
    # --------------------------------------------------------

    healthy_current_density = (
        current / healthy_area
    )

    defective_current_density = (
        current / defective_area
    )

    # --------------------------------------------------------
    # POWER
    # --------------------------------------------------------

    healthy_power = (
        current ** 2
        * healthy_resistance
    )

    defective_power = (
        current ** 2
        * defective_resistance
    )

    # --------------------------------------------------------
    # RELATIVE CHANGES
    # --------------------------------------------------------

    resistance_change = safe_percentage_change(
        healthy_resistance,
        defective_resistance
    )

    current_density_change = safe_percentage_change(
        healthy_current_density,
        defective_current_density
    )

    power_change = safe_percentage_change(
        healthy_power,
        defective_power
    )

    return {

        "analysis_status": "ESTIMATED",

        "analysis_reason": (
            "Simplified uniform-trace model using an "
            "image-derived regional copper ratio."
        ),

        "healthy": {

            "conductive_area_m2": healthy_area,

            "resistance_ohm": healthy_resistance,

            "current_density_A_per_m2":
                healthy_current_density,

            "power_loss_W": healthy_power
        },

        "defective": {

            "conductive_area_m2": defective_area,

            "resistance_ohm": defective_resistance,

            "current_density_A_per_m2":
                defective_current_density,

            "power_loss_W": defective_power
        },

        "change": {

            "resistance_percent":
                resistance_change,

            "current_density_percent":
                current_density_change,

            "power_loss_percent":
                power_change
        }
    }


def create_unquantified_electrical_result(reason):
    """
    Standard electrical result for defects whose electrical
    properties cannot responsibly be quantified from the ROI.
    """

    return {

        "analysis_status": "NOT_QUANTIFIED",

        "analysis_reason": reason,

        "healthy": {

            "conductive_area_m2": None,

            "resistance_ohm": None,

            "current_density_A_per_m2": None,

            "power_loss_W": None
        },

        "defective": {

            "conductive_area_m2": None,

            "resistance_ohm": None,

            "current_density_A_per_m2": None,

            "power_loss_W": None
        },

        "change": {

            "resistance_percent": None,

            "current_density_percent": None,

            "power_loss_percent": None
        }
    }


# ------------------------- IMPACT CLASSIFICATION ---------------

def classify_electrical_impact(
    defect_class,
    copper_loss_percent,
    copper_gain_percent,
    resistance_change_percent
):
    """
    Prototype impact classification.

    Thresholds are software heuristics.
    They are NOT IPC standards or validated engineering
    failure thresholds.
    """

    defect_class = defect_class.lower()

    # --------------------------------------------------------
    # FAILURE MODES
    # --------------------------------------------------------

    if defect_class == "open":
        return "CRITICAL - OPEN CIRCUIT RISK"

    if defect_class == "short":
        return "CRITICAL - SHORT CIRCUIT RISK"

    # --------------------------------------------------------
    # UNQUANTIFIED GEOMETRY
    # --------------------------------------------------------

    if copper_loss_percent is None:
        return "UNQUANTIFIED - GEOMETRY REVIEW REQUIRED"

    # --------------------------------------------------------
    # COPPER GAIN / BRIDGE RISK
    # --------------------------------------------------------

    if copper_gain_percent is not None and copper_gain_percent > 0:

        if defect_class in ("spur", "short", "copper"):
            return "COPPER GAIN / CLEARANCE / BRIDGE REVIEW"

    # --------------------------------------------------------
    # COPPER LOSS
    # --------------------------------------------------------

    if copper_loss_percent >= 50:
        return "HIGH GEOMETRIC COPPER LOSS - REVIEW"

    if copper_loss_percent >= 20:
        return "MODERATE-HIGH GEOMETRIC COPPER LOSS"

    if copper_loss_percent >= 10:
        return "MODERATE GEOMETRIC COPPER LOSS"

    if copper_loss_percent > 0:
        return "LOW GEOMETRIC CHANGE - REVIEW"

    if defect_class in ("spur", "copper"):
        return "COPPER GEOMETRY / CLEARANCE REVIEW"

    if resistance_change_percent is not None:

        if resistance_change_percent > 0:
            return "ESTIMATED RESISTANCE INCREASE - REVIEW"

    return "LOW ESTIMATED GEOMETRIC IMPACT"


def generate_recommendation(
    defect_class,
    copper_loss_percent,
    copper_gain_percent,
    impact
):

    defect_class = defect_class.lower()

    if defect_class == "open":

        return (
            "Inspect the conductive path for interruption. "
            "Verify continuity using electrical testing."
        )

    if defect_class == "short":

        return (
            "Inspect possible unintended copper bridging. "
            "Verify isolation between adjacent conductors."
        )

    if defect_class == "mousebite":

        return (
            "Inspect edge copper loss and remaining trace width. "
            "Check whether the affected region intersects "
            "a current-carrying path."
        )

    if defect_class == "spur":

        return (
            "Inspect protruding copper and nearby conductor "
            "clearance. Verify whether the copper extension "
            "creates a bridge risk."
        )

    if defect_class == "pin-hole":

        return (
            "Inspect the localized copper void. Determine "
            "whether it intersects a conductive path or "
            "critical copper region."
        )

    if defect_class == "copper":

        return (
            "Inspect the copper geometry discrepancy. "
            "Check for unintended copper, clearance violation, "
            "or trace-width variation."
        )

    if copper_loss_percent is None:

        return (
            "Regional copper comparison is unquantified. "
            "Perform manual engineering review."
        )

    if copper_loss_percent >= 20:

        return (
            "Inspect significant regional copper loss. "
            "Verify trace constriction, continuity, and "
            "remaining copper width."
        )

    if copper_gain_percent is not None and copper_gain_percent > 0:

        return (
            "Inspect regional copper gain. Verify conductor "
            "clearance and possible unwanted copper extension."
        )

    return "Manual engineering review recommended."


# ------------------------- MAIN CEIA ---------------------------

def run_ceia(
    reference_path,
    test_path,
    detections_path,
    output_dir,
    current,
    trace_width_mm,
    trace_length_mm,
    copper_thickness_um
):

    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

    validate_parameters(
        current,
        trace_width_mm,
        trace_length_mm,
        copper_thickness_um
    )

    os.makedirs(
        output_dir,
        exist_ok=True
    )

    reference = load_image(reference_path)
    test = load_image(test_path)

    if reference.shape != test.shape:

        raise ValueError(
            "Reference and test images must have matching "
            "dimensions. Align them before CEIA."
        )

    reference_mask = copper_mask(reference)
    test_mask = copper_mask(test)

    yolo_data = load_json(detections_path)
    detections = extract_detections(yolo_data)

    results = []

    visual = cv2.cvtColor(
        test,
        cv2.COLOR_GRAY2BGR
    )

    print("\n" + "=" * 65)
    print("CEIA - COUNTERFACTUAL ELECTRICAL IMPACT ANALYSIS")
    print("=" * 65)

    print(f"Detections: {len(detections)}")
    print(f"Current: {current} A")
    print(f"Nominal trace width: {trace_width_mm} mm")
    print(f"Trace length: {trace_length_mm} mm")
    print(f"Copper thickness: {copper_thickness_um} um")

    # --------------------------------------------------------
    # DETECTION PROCESSING
    # --------------------------------------------------------

    for index, detection in enumerate(
        detections,
        start=1
    ):

        defect_class = get_class_name(detection)
        confidence = get_confidence(detection)
        bbox = extract_bbox(detection)

        x1, y1, x2, y2 = clamp_bbox(
            bbox,
            reference.shape
        )

        reference_roi = reference_mask[y1:y2, x1:x2]
        test_roi = test_mask[y1:y2, x1:x2]

        reference_copper_pixels = int(
            cv2.countNonZero(reference_roi)
        )

        test_copper_pixels = int(
            cv2.countNonZero(test_roi)
        )

        roi_pixels = int(
            reference_roi.size
        )

        # ----------------------------------------------------
        # REGIONAL COPPER CHANGE PROXY
        # ----------------------------------------------------

        if reference_copper_pixels > 0:

            copper_ratio = (
                test_copper_pixels
                / reference_copper_pixels
            )

            copper_loss_percent = max(
                0.0,
                (1.0 - copper_ratio) * 100.0
            )

            copper_gain_percent = max(
                0.0,
                (copper_ratio - 1.0) * 100.0
            )

        else:

            copper_ratio = None
            copper_loss_percent = None
            copper_gain_percent = None

        # ----------------------------------------------------
        # ELECTRICAL ANALYSIS
        # ----------------------------------------------------

        resistance_change = None

        if defect_class == "open":

            electrical = create_unquantified_electrical_result(
                "Possible conductive path interruption. "
                "Continuity and actual resistance cannot be "
                "determined from the image ROI."
            )

        elif defect_class == "short":

            electrical = create_unquantified_electrical_result(
                "Possible unintended conductive bridge. "
                "Bridge resistance and actual circuit topology "
                "cannot be determined from the image ROI."
            )

        elif copper_ratio is None:

            electrical = create_unquantified_electrical_result(
                "Reference copper was not detected in this ROI. "
                "Regional copper ratio cannot be calculated."
            )

        else:

            electrical = calculate_electrical_parameters(
                current=current,
                trace_length_mm=trace_length_mm,
                trace_width_mm=trace_width_mm,
                copper_thickness_um=copper_thickness_um,
                copper_ratio=copper_ratio
            )

            resistance_change = (
                electrical["change"]["resistance_percent"]
            )

        # ----------------------------------------------------
        # IMPACT
        # ----------------------------------------------------

        impact = classify_electrical_impact(
            defect_class=defect_class,
            copper_loss_percent=copper_loss_percent,
            copper_gain_percent=copper_gain_percent,
            resistance_change_percent=resistance_change
        )

        recommendation = generate_recommendation(
            defect_class=defect_class,
            copper_loss_percent=copper_loss_percent,
            copper_gain_percent=copper_gain_percent,
            impact=impact
        )

        # ----------------------------------------------------
        # RESULT OBJECT
        # ----------------------------------------------------

        result = {

            "defect_id": index,

            "class": defect_class,

            "confidence": confidence,

            "bbox": [x1, y1, x2, y2],

            "geometry": {

                "roi_pixels": roi_pixels,

                "reference_copper_pixels":
                    reference_copper_pixels,

                "test_copper_pixels":
                    test_copper_pixels,

                "copper_ratio":
                    copper_ratio,

                "copper_loss_percent":
                    copper_loss_percent,

                "copper_gain_percent":
                    copper_gain_percent
            },

            "electrical": electrical,

            "impact": impact,

            "recommendation": recommendation,

            "model_note": (
                "Regional copper ratio is an image-derived "
                "geometry proxy, not an actual trace cross-section. "
                "Electrical estimates use a simplified uniform-trace "
                "model and are not experimentally validated."
            )
        }

        results.append(result)

        # ----------------------------------------------------
        # VISUALIZATION
        # ----------------------------------------------------

        if defect_class in ("open", "short"):
            color = (0, 0, 255)       # Red

        elif impact.startswith("HIGH"):
            color = (0, 0, 255)

        elif impact.startswith("MODERATE"):
            color = (0, 165, 255)      # Orange

        elif impact.startswith("LOW"):
            color = (0, 255, 0)        # Green

        else:
            color = (255, 0, 255)       # Magenta

        cv2.rectangle(
            visual,
            (x1, y1),
            (x2, y2),
            color,
            2
        )

        label = f"{index}:{defect_class}"

        cv2.putText(
            visual,
            label,
            (x1, max(15, y1 - 5)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1,
            cv2.LINE_AA
        )

        # ----------------------------------------------------
        # TERMINAL OUTPUT
        # ----------------------------------------------------

        print(
            f"\nDefect #{index}: {defect_class.upper()}"
        )

        print(
            f"YOLO confidence: {confidence:.4f}"
        )

        if copper_loss_percent is not None:

            print(
                f"Regional copper loss proxy: "
                f"{copper_loss_percent:.2f}%"
            )

        else:

            print(
                "Regional copper loss proxy: UNQUANTIFIED"
            )

        if copper_gain_percent is not None:

            print(
                f"Regional copper gain proxy: "
                f"{copper_gain_percent:.2f}%"
            )

        if electrical["analysis_status"] == "ESTIMATED":

            print(
                "Healthy resistance:",
                f"{electrical['healthy']['resistance_ohm']:.8f} Ohm"
            )

            print(
                "Estimated defective resistance:",
                f"{electrical['defective']['resistance_ohm']:.8f} Ohm"
            )

            print(
                "Resistance change:",
                f"{resistance_change:.2f}%"
                if resistance_change is not None
                else "UNQUANTIFIED"
            )

            print(
                "Healthy current density:",
                f"{electrical['healthy']['current_density_A_per_m2']:.4f} A/m2"
            )

            print(
                "Estimated defective current density:",
                f"{electrical['defective']['current_density_A_per_m2']:.4f} A/m2"
            )

            print(
                "Healthy power loss:",
                f"{electrical['healthy']['power_loss_W']:.8f} W"
            )

            print(
                "Estimated defective power loss:",
                f"{electrical['defective']['power_loss_W']:.8f} W"
            )

        else:

            print(
                "Electrical analysis:",
                electrical["analysis_status"]
            )

            print(
                "Reason:",
                electrical["analysis_reason"]
            )

        print("Impact:", impact)

        print("Recommendation:", recommendation)

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    impact_counts = {}

    for result in results:

        category = result["impact"]

        impact_counts[category] = (
            impact_counts.get(category, 0) + 1
        )

    summary = {

        "module": "CEIA",

        "version": "0.2",

        "description": (
            "Counterfactual Electrical Impact Analysis"
        ),

        "total_defects": len(results),

        "impact_distribution": impact_counts,

        "parameters": {

            "current_A": current,

            "nominal_trace_width_mm":
                trace_width_mm,

            "trace_length_mm":
                trace_length_mm,

            "copper_thickness_um":
                copper_thickness_um,

            "copper_resistivity_ohm_m":
                COPPER_RESISTIVITY,

            "roi_padding_pixels":
                ROI_PADDING,

            "segmentation_threshold":
                SEGMENTATION_THRESHOLD
        },

        "assumptions": [

            "Reference and test PCB images are aligned.",

            "Dark pixels are treated as copper.",

            "The segmentation threshold is fixed at 127.",

            "Regional copper ratio is a geometry proxy.",

            "Regional copper ratio is not actual trace cross-sectional area.",

            "Nominal trace width and copper thickness are assumed.",

            "Electrical estimation uses a uniform equivalent trace.",

            "Current is assumed constant for the simplified model.",

            "Open and short defects are not assigned fabricated resistance values.",

            "Copper gain is not assumed to increase intended trace cross-section.",

            "The model does not solve actual 2D current distribution.",

            "The model does not calculate actual temperature rise.",

            "The model does not establish circuit connectivity.",

            "Electrical estimates are not experimentally validated.",

            "Impact categories are prototype heuristics, not IPC standards."
        ],

        "results": results
    }

    # --------------------------------------------------------
    # JSON REPORT
    # --------------------------------------------------------

    report_path = os.path.join(
        output_dir,
        "ceia_report.json"
    )

    with open(report_path, "w") as file:

        json.dump(
            summary,
            file,
            indent=4,
            allow_nan=False
        )

    # --------------------------------------------------------
    # CSV REPORT
    # --------------------------------------------------------

    csv_path = os.path.join(
        output_dir,
        "ceia_report.csv"
    )

    with open(
        csv_path,
        "w",
        newline=""
    ) as file:

        writer = csv.writer(file)

        writer.writerow([

            "Defect ID",

            "Class",

            "Confidence",

            "Copper Loss Proxy %",

            "Copper Gain Proxy %",

            "Electrical Status",

            "Healthy Resistance Ohm",

            "Defective Resistance Ohm",

            "Resistance Change %",

            "Healthy Current Density A/m2",

            "Defective Current Density A/m2",

            "Healthy Power W",

            "Defective Power W",

            "Impact",

            "Recommendation"
        ])

        for result in results:

            geometry = result["geometry"]
            electrical = result["electrical"]

            writer.writerow([

                result["defect_id"],

                result["class"],

                result["confidence"],

                geometry["copper_loss_percent"],

                geometry["copper_gain_percent"],

                electrical["analysis_status"],

                electrical["healthy"]["resistance_ohm"],

                electrical["defective"]["resistance_ohm"],

                electrical["change"]["resistance_percent"],

                electrical["healthy"]["current_density_A_per_m2"],

                electrical["defective"]["current_density_A_per_m2"],

                electrical["healthy"]["power_loss_W"],

                electrical["defective"]["power_loss_W"],

                result["impact"],

                result["recommendation"]
            ])

    # --------------------------------------------------------
    # VISUAL OUTPUT
    # --------------------------------------------------------

    visual_path = os.path.join(
        output_dir,
        "ceia_annotated.jpg"
    )

    success = cv2.imwrite(
        visual_path,
        visual
    )

    if not success:

        raise IOError(
            f"Failed to save annotated image: {visual_path}"
        )

    # --------------------------------------------------------
    # FINAL STATUS
    # --------------------------------------------------------

    print("\n" + "=" * 65)
    print("CEIA ANALYSIS COMPLETE")
    print("=" * 65)

    print("Total defects:", len(results))

    print("Impact distribution:", impact_counts)

    print("JSON:", report_path)

    print("CSV:", csv_path)

    print("Visual:", visual_path)


# ------------------------- CLI -------------------------------

def main():

    parser = argparse.ArgumentParser(
        description=(
            "CEIA Counterfactual Electrical Impact Analysis"
        )
    )

    parser.add_argument(
        "--reference",
        default="datasets/reference/golden.png"
    )

    parser.add_argument(
        "--test",
        default="datasets/test/test.png"
    )

    parser.add_argument(
        "--detections",
        default="outputs/ceri_ceia/yolo_test/detections.json"
    )

    parser.add_argument(
        "--output-dir",
        default="outputs/ceri_ceia/ceia"
    )

    parser.add_argument(
        "--current",
        type=float,
        default=DEFAULT_CURRENT
    )

    parser.add_argument(
        "--trace-width-mm",
        type=float,
        default=DEFAULT_TRACE_WIDTH_MM
    )

    parser.add_argument(
        "--trace-length-mm",
        type=float,
        default=DEFAULT_TRACE_LENGTH_MM
    )

    parser.add_argument(
        "--copper-thickness-um",
        type=float,
        default=DEFAULT_COPPER_THICKNESS_UM
    )

    args = parser.parse_args()

    run_ceia(
        reference_path=args.reference,
        test_path=args.test,
        detections_path=args.detections,
        output_dir=args.output_dir,
        current=args.current,
        trace_width_mm=args.trace_width_mm,
        trace_length_mm=args.trace_length_mm,
        copper_thickness_um=args.copper_thickness_um
    )


if __name__ == "__main__":
    main()
