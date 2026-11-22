import json
import csv
import os
import argparse
import html

# ============================================================
# RGPIS-HDE UNIFIED DEFECT INTELLIGENCE ENGINE
# CERI + CEIA Integration
# ============================================================

DEFAULT_CERI = "outputs/ceri_ceia/ceri/ceri_report.json"
DEFAULT_CEIA = "outputs/ceri_ceia/ceia/ceia_report.json"
DEFAULT_OUTPUT = "outputs/ceri_ceia/integrated"

# Configurable weighting
CERI_WEIGHT = 0.65
CEIA_WEIGHT = 0.35

# CEIA impact normalization
CEIA_IMPACT_SCORES = {
    "CRITICAL - OPEN CIRCUIT RISK": 100,
    "CRITICAL - SHORT CIRCUIT RISK": 100,
    "HIGH ELECTRICAL IMPACT": 85,
    "MODERATE-HIGH ELECTRICAL IMPACT": 70,
    "MODERATE ELECTRICAL IMPACT": 60,
    "MODERATE GEOMETRIC COPPER LOSS": 55,
    "LOW GEOMETRIC CHANGE - REVIEW": 30,
    "LOW ESTIMATED IMPACT": 20,
    "COPPER GAIN / BRIDGE REVIEW": 65,
    "COPPER GAIN / CLEARANCE / BRIDGE REVIEW": 65,
    "UNQUANTIFIED": 50,
    "UNQUANTIFIED - GEOMETRY REVIEW REQUIRED": 50,
}

CRITICAL_CLASSES = {"open", "short"}


def load_json(path):
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Report not found: {path}")

    with open(path, "r") as f:
        return json.load(f)


def normalize_class(value):
    return str(value or "unknown").strip().lower().replace("_", "-")


def get_ceri_detections(data):
    return data.get("detections", [])


def get_ceia_results(data):
    return data.get("results", [])


def bbox_to_xyxy(bbox):
    if isinstance(bbox, dict):
        keys = ("x_min", "y_min", "x_max", "y_max")
        if all(k in bbox for k in keys):
            return tuple(float(bbox[k]) for k in keys)

    if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        return tuple(float(v) for v in bbox)

    return None


def get_bbox(item):
    return bbox_to_xyxy(item.get("bbox"))


def bbox_iou(a, b):
    if a is None or b is None:
        return 0.0

    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    intersection = iw * ih

    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)

    union = area_a + area_b - intersection

    return intersection / union if union > 0 else 0.0


def match_ceia(ceri_detection, ceia_results, used_indices):
    """
    Match CERI and CEIA detections.

    Priority:
    1. Same defect ID and class
    2. Same class with best bounding-box IoU
    """

    ceri_id = ceri_detection.get("defect_id")
    ceri_class = normalize_class(
        ceri_detection.get("class_name", ceri_detection.get("class"))
    )
    ceri_bbox = get_bbox(ceri_detection)

    # Exact ID + class matching
    for i, ceia in enumerate(ceia_results):
        if i in used_indices:
            continue

        ceia_id = ceia.get("defect_id")
        ceia_class = normalize_class(ceia.get("class"))

        if ceri_id == ceia_id and ceri_class == ceia_class:
            used_indices.add(i)
            return ceia, "ID_AND_CLASS"

    # Geometric fallback matching
    best_i = None
    best_iou = 0.0

    for i, ceia in enumerate(ceia_results):
        if i in used_indices:
            continue

        if normalize_class(ceia.get("class")) != ceri_class:
            continue

        overlap = bbox_iou(ceri_bbox, get_bbox(ceia))

        if overlap > best_iou:
            best_iou = overlap
            best_i = i

    if best_i is not None and best_iou >= 0.30:
        used_indices.add(best_i)
        return ceia_results[best_i], f"BBOX_IOU_{best_iou:.3f}"

    return None, "NO_MATCH"


def ceri_score(detection):
    risk = detection.get("risk", {})
    score = risk.get("score")

    try:
        score = float(score)
    except (TypeError, ValueError):
        score = None

    if score is not None:
        return max(0.0, min(100.0, score))

    category = str(risk.get("category", "")).upper()

    fallback = {
        "CRITICAL": 95,
        "HIGH": 80,
        "MODERATE": 55,
        "LOW": 25,
    }

    return float(fallback.get(category, 50))


def ceia_score(ceia):
    if ceia is None:
        return 50.0

    defect_class = normalize_class(ceia.get("class"))

    # Explicit failure-mode override
    if defect_class in CRITICAL_CLASSES:
        return 100.0

    impact = str(ceia.get("impact", "")).strip().upper()

    if impact in CEIA_IMPACT_SCORES:
        return float(CEIA_IMPACT_SCORES[impact])

    # Fallback from resistance-change estimate
    electrical = ceia.get("electrical", {})
    change = electrical.get("change", {})
    resistance_change = change.get("resistance_percent")

    if resistance_change is not None:
        try:
            resistance_change = abs(float(resistance_change))
            if resistance_change >= 100:
                return 90.0
            if resistance_change >= 50:
                return 80.0
            if resistance_change >= 20:
                return 65.0
            if resistance_change >= 10:
                return 50.0
            return 30.0
        except (TypeError, ValueError):
            pass

    return 50.0


def classify_priority(score, defect_class):
    defect_class = normalize_class(defect_class)

    if defect_class in CRITICAL_CLASSES:
        return "CRITICAL"

    if score >= 80:
        return "CRITICAL"
    if score >= 60:
        return "HIGH"
    if score >= 40:
        return "MODERATE"
    return "LOW"


def generate_integrated_recommendation(
    defect_class, priority, ceri, ceia
):
    defect_class = normalize_class(defect_class)

    if defect_class == "open":
        return (
            "CRITICAL: Perform continuity testing and verify "
            "whether the conductive path is interrupted."
        )

    if defect_class == "short":
        return (
            "CRITICAL: Inspect potential copper bridging and "
            "verify isolation between conductors."
        )

    if defect_class == "mousebite":
        return (
            "Inspect edge damage and remaining trace width. "
            "Check whether a critical current path is affected."
        )

    if defect_class == "pin-hole":
        return (
            "Inspect the copper void and determine whether it "
            "intersects a critical conductor or pad."
        )

    if defect_class == "spur":
        return (
            "Inspect protruding copper and adjacent clearance. "
            "Check for potential bridging."
        )

    if defect_class == "copper":
        return (
            "Review copper geometry discrepancy, trace width, "
            "clearance, and possible unintended connections."
        )

    if priority == "CRITICAL":
        return "Immediate engineering inspection recommended."

    if priority == "HIGH":
        return "Prioritize manual PCB engineering inspection."

    if priority == "MODERATE":
        return "Review the defect and confirm geometry against the reference."

    return "Record defect and perform routine engineering review."


def integrate(ceri_data, ceia_data):
    ceri_detections = get_ceri_detections(ceri_data)
    ceia_results = get_ceia_results(ceia_data)

    used_ceia = set()
    integrated = []

    for ceri in ceri_detections:
        ceia, match_method = match_ceia(
            ceri, ceia_results, used_ceia
        )

        defect_class = normalize_class(
            ceri.get("class_name", ceri.get("class"))
        )

        geometry_score = ceri_score(ceri)
        electrical_score = ceia_score(ceia)

        # Weighted composite
        unified_score = (
            CERI_WEIGHT * geometry_score
            + CEIA_WEIGHT * electrical_score
        )

        # Critical failure-mode override
        critical_override = defect_class in CRITICAL_CLASSES

        if critical_override:
            unified_score = max(95.0, unified_score)

        unified_score = round(
            min(100.0, max(0.0, unified_score)), 2
        )

        priority = classify_priority(
            unified_score, defect_class
        )

        if critical_override:
            priority = "CRITICAL"

        recommendation = generate_integrated_recommendation(
            defect_class, priority, ceri, ceia
        )

        ceri_risk = ceri.get("risk", {})
        ceri_geometry = ceri.get("geometry_metrics", {})
        ceia_geometry = ceia.get("geometry", {}) if ceia else {}
        electrical = ceia.get("electrical", {}) if ceia else {}

        integrated.append({
            "defect_id": ceri.get("defect_id"),
            "class": defect_class,
            "confidence": ceri.get("confidence"),
            "bbox": ceri.get("bbox"),

            "matching": {
                "status": "MATCHED" if ceia else "UNMATCHED",
                "method": match_method
            },

            "ceri": {
                "risk_score": geometry_score,
                "risk_category": ceri_risk.get("category"),
                "geometry_metrics": ceri_geometry,
                "measurement_status": ceri.get("measurement_status")
            },

            "ceia": {
                "impact": ceia.get("impact") if ceia else "UNAVAILABLE",
                "impact_score": electrical_score,
                "geometry": ceia_geometry,
                "electrical": electrical,
                "recommendation": (
                    ceia.get("recommendation") if ceia else None
                )
            },

            "unified_score": unified_score,
            "priority": priority,
            "critical_override": critical_override,
            "recommendation": recommendation
        })

    # Include CEIA detections unmatched by CERI
    unmatched_ceia = [
        item for i, item in enumerate(ceia_results)
        if i not in used_ceia
    ]

    priority_order = {
        "CRITICAL": 0,
        "HIGH": 1,
        "MODERATE": 2,
        "LOW": 3
    }

    integrated.sort(
        key=lambda x: (
            priority_order.get(x["priority"], 4),
            -x["unified_score"]
        )
    )

    distribution = {
        "CRITICAL": 0,
        "HIGH": 0,
        "MODERATE": 0,
        "LOW": 0
    }

    for item in integrated:
        distribution[item["priority"]] += 1

    overall_score = (
        sum(item["unified_score"] for item in integrated)
        / len(integrated)
        if integrated else 0.0
    )

    if distribution["CRITICAL"] > 0:
        board_status = "REJECT - CRITICAL DEFECTS DETECTED"
    elif distribution["HIGH"] > 0:
        board_status = "HOLD - HIGH PRIORITY DEFECTS"
    elif distribution["MODERATE"] > 0:
        board_status = "REVIEW REQUIRED"
    else:
        board_status = "LOW RISK - REVIEW BEFORE RELEASE"

    return {
        "project": "RGPIS-HDE",
        "module": "Unified Defect Intelligence",
        "version": "0.1",
        "scoring": {
            "ceri_weight": CERI_WEIGHT,
            "ceia_weight": CEIA_WEIGHT,
            "formula": "0.65*CERI + 0.35*CEIA",
            "critical_override_classes": sorted(CRITICAL_CLASSES),
            "note": (
                "Prototype score. CERI and CEIA partly use "
                "correlated image geometry; score is not calibrated "
                "or validated against production failure data."
            )
        },
        "total_detections": len(integrated),
        "matched_detections": sum(
            1 for item in integrated
            if item["matching"]["status"] == "MATCHED"
        ),
        "unmatched_ceia_detections": len(unmatched_ceia),
        "priority_distribution": distribution,
        "mean_unified_score": round(overall_score, 2),
        "board_status": board_status,
        "results": integrated,
        "unmatched_ceia": unmatched_ceia
    }


def write_csv(report, path):
    fields = [
        "defect_id", "class", "confidence",
        "ceri_score", "ceri_category",
        "ceia_impact", "ceia_score",
        "unified_score", "priority",
        "critical_override", "match_status",
        "recommendation"
    ]

    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()

        for item in report["results"]:
            writer.writerow({
                "defect_id": item["defect_id"],
                "class": item["class"],
                "confidence": item["confidence"],
                "ceri_score": item["ceri"]["risk_score"],
                "ceri_category": item["ceri"]["risk_category"],
                "ceia_impact": item["ceia"]["impact"],
                "ceia_score": item["ceia"]["impact_score"],
                "unified_score": item["unified_score"],
                "priority": item["priority"],
                "critical_override": item["critical_override"],
                "match_status": item["matching"]["status"],
                "recommendation": item["recommendation"]
            })


def write_dashboard(report, path):
    rows = []

    colors = {
        "CRITICAL": "#dc2626",
        "HIGH": "#ea580c",
        "MODERATE": "#d97706",
        "LOW": "#16a34a"
    }

    for item in report["results"]:
        priority = item["priority"]
        color = colors.get(priority, "#64748b")

        rows.append(f"""
        <tr>
          <td>{html.escape(str(item['defect_id']))}</td>
          <td>{html.escape(item['class'].upper())}</td>
          <td>{float(item['confidence'] or 0):.3f}</td>
          <td>{item['ceri']['risk_score']:.2f}</td>
          <td>{html.escape(str(item['ceia']['impact']))}</td>
          <td><b>{item['unified_score']:.2f}</b></td>
          <td><span class="priority" style="background:{color}">
              {priority}</span></td>
          <td>{html.escape(item['recommendation'])}</td>
        </tr>
        """)

    distribution_cards = []

    for category, count in report["priority_distribution"].items():
        color = colors.get(category, "#64748b")
        distribution_cards.append(f"""
        <div class="card">
          <div class="count" style="color:{color}">{count}</div>
          <div>{category}</div>
        </div>
        """)

    table_rows = "\n".join(rows)
    cards = "\n".join(distribution_cards)

    document = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RGPIS-HDE Unified Defect Intelligence</title>
<style>
body {{
    margin:0;
    padding:28px;
    background:#0f172a;
    color:#e2e8f0;
    font-family:Arial,Helvetica,sans-serif;
}}
.container {{max-width:1400px;margin:auto}}
h1 {{margin-bottom:5px}}
.subtitle {{color:#94a3b8;margin-bottom:25px}}
.status {{
    background:#1e293b;
    border-left:5px solid #f59e0b;
    padding:18px;
    border-radius:8px;
    margin-bottom:20px;
}}
.cards {{
    display:grid;
    grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
    gap:12px;margin:20px 0;
}}
.card {{
    background:#1e293b;padding:18px;border-radius:10px;
    text-align:center
}}
.count {{font-size:30px;font-weight:bold;margin-bottom:5px}}
.score {{
    background:#1e293b;padding:20px;border-radius:10px;
    margin:15px 0;font-size:18px
}}
table {{
    width:100%;border-collapse:collapse;background:#1e293b;
    margin-top:20px
}}
th,td {{
    padding:12px;text-align:left;border-bottom:1px solid #334155;
}}
th {{background:#334155}}
.priority {{
    padding:5px 10px;border-radius:6px;
    color:white;font-weight:bold;font-size:12px
}}
tr:hover {{background:#273449}}
.note {{
    color:#94a3b8;font-size:13px;margin-top:20px;
    line-height:1.6
}}
@media(max-width:800px) {{
    body {{padding:10px}}
    table {{font-size:12px}}
    th,td {{padding:7px}}
}}
</style>
</head>
<body>
<div class="container">
<h1>RGPIS-HDE</h1>
<div class="subtitle">Reference-Guided Dual-Domain Discrepancy
& Heterogeneous Edge Process Intelligence System</div>

<div class="status">
<strong>PCB Assessment:</strong>
{html.escape(report['board_status'])}
</div>

<div class="cards">
<div class="card">
<div class="count">{report['total_detections']}</div>
<div>Total Defects</div>
</div>
{cards}
<div class="card">
<div class="count">{report['matched_detections']}</div>
<div>CERI-CEIA Matched</div>
</div>
</div>

<div class="score">
<strong>Mean Unified Defect Score:</strong>
{report['mean_unified_score']:.2f} / 100
</div>

<h2>Unified Defect Analysis</h2>
<table>
<thead>
<tr>
<th>ID</th><th>Defect</th><th>Confidence</th>
<th>CERI</th><th>CEIA</th><th>Unified</th>
<th>Priority</th><th>Recommendation</th>
</tr>
</thead>
<tbody>
{table_rows}
</tbody>
</table>

<div class="note">
Unified score formula: 65% CERI geometry/risk score + 35% CEIA
electrical impact score. Open and short detections receive critical
priority overrides. This is an experimental prototype score, not a
validated manufacturing acceptance standard. Image-based geometry
and electrical approximations require engineering verification.
</div>
</div>
</body>
</html>
"""

    with open(path, "w", encoding="utf-8") as f:
        f.write(document)


def main():
    parser = argparse.ArgumentParser(
        description="RGPIS-HDE CERI-CEIA integration engine"
    )

    parser.add_argument("--ceri", default=DEFAULT_CERI)
    parser.add_argument("--ceia", default=DEFAULT_CEIA)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT)

    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    ceri_data = load_json(args.ceri)
    ceia_data = load_json(args.ceia)

    report = integrate(ceri_data, ceia_data)

    json_path = os.path.join(
        args.output_dir, "unified_report.json"
    )
    csv_path = os.path.join(
        args.output_dir, "unified_report.csv"
    )
    html_path = os.path.join(
        args.output_dir, "dashboard.html"
    )

    with open(json_path, "w") as f:
        json.dump(report, f, indent=4)

    write_csv(report, csv_path)
    write_dashboard(report, html_path)

    print("\n" + "=" * 65)
    print("RGPIS-HDE UNIFIED DEFECT INTELLIGENCE")
    print("=" * 65)
    print("Detections:", report["total_detections"])
    print("Matched:", report["matched_detections"])
    print("Unmatched CEIA:", report["unmatched_ceia_detections"])
    print("Priority distribution:", report["priority_distribution"])
    print("Mean unified score:", report["mean_unified_score"])
    print("Board status:", report["board_status"])

    print("\nRanked defects:")
    for item in report["results"]:
        print(
            f"#{item['defect_id']} {item['class'].upper():10s} "
            f"Score={item['unified_score']:6.2f} "
            f"Priority={item['priority']:8s} "
            f"CERI={item['ceri']['risk_score']:5.2f} "
            f"CEIA={item['ceia']['impact_score']:5.2f}"
        )

    print("\nIntegration complete.")
    print("JSON:", json_path)
    print("CSV:", csv_path)
    print("Dashboard:", html_path)


if __name__ == "__main__":
    main()
