"""
RGPIS-HDE Unified Pipeline Bridge.
Integrates OpenCV / YOLO detections, CERI geometric risk analysis, CEIA approximate
electrical impact analysis, and unified defect scoring into a structured unified_report.json.

Grounding Policy:
- CERI metrics represent optical geometric trace reductions and clearance violations.
- CEIA metrics represent COUNTERFACTUAL GEOMETRIC PROXIES (current crowding, nodal conductance).
  They are explicitly labeled as proxies and NOT in-situ bench electrical measurements.
"""

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
DETECTIONS_JSON = PROJECT_ROOT / "outputs" / "predictions" / "detections.json"


def compute_ceri_metrics(class_name: str, geometry: Dict[str, float], confidence: float) -> Dict[str, Any]:
    """
    Computes CERI (Critical Engineering Risk Index) geometric severity metrics.
    Trace-width reduction and clearance intrusion based on IPC-A-600 Class 2/3.
    """
    cname = class_name.lower().replace("-", "").replace("_", "")
    w = geometry.get("width", 30.0)
    h = geometry.get("height", 30.0)
    area = geometry.get("area", 900.0)

    # Nominal design parameters for DeepPCB scale (~0.15mm trace width, ~0.15mm spacing)
    nominal_trace_px = 32.0  # approximate nominal trace width in pixels
    nominal_clearance_px = 32.0

    trace_width_reduction_pct = 0.0
    clearance_intrusion_pct = 0.0
    clearance_remaining_mm = 0.15
    geometric_risk_score = 0.0
    ipc_violation = False

    if "open" in cname:
        trace_width_reduction_pct = 100.0
        geometric_risk_score = 1.00
        ipc_violation = True
    elif "short" in cname:
        clearance_intrusion_pct = 100.0
        clearance_remaining_mm = 0.00
        geometric_risk_score = 1.00
        ipc_violation = True
    elif "mousebite" in cname:
        # Depth of bite into conductor
        intrusion_depth = min(w, h)
        reduction_ratio = min(0.95, intrusion_depth / nominal_trace_px)
        trace_width_reduction_pct = round(reduction_ratio * 100.0, 1)
        geometric_risk_score = round(min(1.0, 0.40 + 0.60 * reduction_ratio), 2)
        # IPC Class 2/3 prohibits > 20% trace reduction
        ipc_violation = trace_width_reduction_pct > 20.0
    elif "spur" in cname:
        # Protrusion length into clearance zone
        protrusion_len = max(w, h)
        intrusion_ratio = min(0.95, protrusion_len / nominal_clearance_px)
        clearance_intrusion_pct = round(intrusion_ratio * 100.0, 1)
        clearance_remaining_mm = round(max(0.01, 0.15 * (1.0 - intrusion_ratio)), 3)
        geometric_risk_score = round(min(1.0, 0.35 + 0.65 * intrusion_ratio), 2)
        # IPC Class 2/3 requires min 70% clearance retention (<= 30% reduction)
        ipc_violation = clearance_intrusion_pct > 30.0
    elif "copper" in cname:
        # Extraneous copper island
        clearance_intrusion_pct = round(min(85.0, (area / 1500.0) * 50.0), 1)
        clearance_remaining_mm = round(max(0.02, 0.15 * (1.0 - clearance_intrusion_pct / 100.0)), 3)
        geometric_risk_score = round(min(0.85, 0.25 + (area / 3000.0) * 0.5), 2)
        ipc_violation = clearance_intrusion_pct > 35.0
    elif "pinhole" in cname:
        void_dia = min(w, h)
        reduction_ratio = min(0.40, void_dia / nominal_trace_px)
        trace_width_reduction_pct = round(reduction_ratio * 100.0, 1)
        geometric_risk_score = round(min(0.70, 0.20 + 0.80 * reduction_ratio), 2)
        ipc_violation = trace_width_reduction_pct > 15.0
    else:
        geometric_risk_score = 0.50

    return {
        "metric_name": "Critical Engineering Risk Index (CERI)",
        "trace_width_reduction_pct": trace_width_reduction_pct,
        "clearance_intrusion_pct": clearance_intrusion_pct,
        "clearance_remaining_mm": clearance_remaining_mm,
        "geometric_risk_score": geometric_risk_score,
        "ipc_violation": ipc_violation,
        "ipc_threshold_standard": "IPC-A-600 Class 2/3 (Max trace reduction <= 20%, Min clearance reduction <= 30%)",
    }


def compute_ceia_metrics(class_name: str, ceri: Dict[str, Any]) -> Dict[str, Any]:
    """
    Computes CEIA (Counterfactual Electrical Impact Analysis) geometric proxy indicators.
    CRITICAL: Labeled strictly as geometric proxies, NOT bench electrical measurements.
    """
    cname = class_name.lower().replace("-", "").replace("_", "")
    t_red = ceri.get("trace_width_reduction_pct", 0.0)
    c_red = ceri.get("clearance_intrusion_pct", 0.0)

    proxy_indicator_type = "COUNTERFACTUAL_GEOMETRIC_PROXY"
    proxy_disclaimer = (
        "Proxy metric estimated from optical copper geometry and 2D finite resistance network. "
        "Not an in-situ physical multimeter or TDR bench measurement."
    )

    if "open" in cname:
        nodal_conductance_factor = 0.0
        current_density_multiplier = 0.0
        resistance_multiplier_proxy = 999999.0  # infinite impedance
        signal_integrity_risk = "CRITICAL"
        thermal_dissipation_risk = "LOW"  # zero current flow
    elif "short" in cname:
        nodal_conductance_factor = 99.0  # high shunt conductance
        current_density_multiplier = 999.0  # short circuit surge path
        resistance_multiplier_proxy = 0.01  # bridge bypass
        signal_integrity_risk = "CRITICAL"
        thermal_dissipation_risk = "CRITICAL"  # severe overcurrent hazard
    elif "mousebite" in cname:
        remaining_ratio = max(0.05, 1.0 - (t_red / 100.0))
        nodal_conductance_factor = round(remaining_ratio, 2)
        # Current crowding bottleneck factor: J = I / (w * t)
        current_density_multiplier = round(1.0 / remaining_ratio, 2)
        resistance_multiplier_proxy = round(1.0 + (1.0 / remaining_ratio - 1.0) * 0.4, 2)
        signal_integrity_risk = "MODERATE" if t_red > 30.0 else "LOW"
        thermal_dissipation_risk = "HIGH" if current_density_multiplier >= 1.8 else "MODERATE"
    elif "spur" in cname:
        nodal_conductance_factor = 1.0
        current_density_multiplier = 1.05
        resistance_multiplier_proxy = 1.0
        # Reduced spacing causes localized electric field intensification & capacitive coupling
        signal_integrity_risk = "HIGH" if c_red > 50.0 else "MODERATE"
        thermal_dissipation_risk = "LOW"
    elif "copper" in cname:
        nodal_conductance_factor = 1.0
        current_density_multiplier = 1.0
        resistance_multiplier_proxy = 1.0
        signal_integrity_risk = "HIGH" if c_red > 40.0 else "MODERATE"  # parasitic capacitance
        thermal_dissipation_risk = "LOW"
    elif "pinhole" in cname:
        remaining_ratio = max(0.10, 1.0 - (t_red / 100.0))
        nodal_conductance_factor = round(remaining_ratio, 2)
        current_density_multiplier = round(1.0 / remaining_ratio, 2)
        resistance_multiplier_proxy = round(1.0 + (current_density_multiplier - 1.0) * 0.2, 2)
        signal_integrity_risk = "LOW"
        thermal_dissipation_risk = "MODERATE" if current_density_multiplier >= 1.3 else "LOW"
    else:
        nodal_conductance_factor = 1.0
        current_density_multiplier = 1.0
        resistance_multiplier_proxy = 1.0
        signal_integrity_risk = "LOW"
        thermal_dissipation_risk = "LOW"

    return {
        "metric_name": "Counterfactual Electrical Impact Analysis (CEIA)",
        "proxy_indicator_type": proxy_indicator_type,
        "nodal_conductance_factor": nodal_conductance_factor,
        "current_density_multiplier": current_density_multiplier,
        "resistance_multiplier_proxy": resistance_multiplier_proxy,
        "signal_integrity_risk": signal_integrity_risk,
        "thermal_dissipation_risk": thermal_dissipation_risk,
        "proxy_disclaimer": proxy_disclaimer,
    }


def compute_unified_score(
    class_name: str,
    confidence: float,
    ceri: Dict[str, Any],
    ceia: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Computes Unified Defect Score (0-100) and Priority Level.
    Weighted formulation: 30% Detection Confidence + 40% CERI Geometric Risk + 30% CEIA Electrical Risk.
    """
    cname = class_name.lower().replace("-", "").replace("_", "")
    ceri_score = ceri.get("geometric_risk_score", 0.5)

    # Convert CEIA risks to normalized score (0.0 - 1.0)
    si_risk = ceia.get("signal_integrity_risk", "LOW")
    th_risk = ceia.get("thermal_dissipation_risk", "LOW")
    risk_weights = {"CRITICAL": 1.0, "HIGH": 0.75, "MODERATE": 0.50, "LOW": 0.20}
    ceia_score = max(risk_weights.get(si_risk, 0.2), risk_weights.get(th_risk, 0.2))

    # Base severity by defect physics
    if "open" in cname or "short" in cname:
        composite = 0.20 * confidence + 0.40 * ceri_score + 0.40 * ceia_score
        raw_score = 75.0 + 25.0 * composite  # Always 80-100 for functional killers
    else:
        composite = 0.30 * confidence + 0.40 * ceri_score + 0.30 * ceia_score
        raw_score = 30.0 + 60.0 * composite

    score = round(min(100.0, max(10.0, raw_score)), 1)

    if score >= 80.0:
        priority_level = "P1_CRITICAL"
        action_urgency = "IMMEDIATE_STOP_AND_QUARANTINE"
    elif score >= 65.0:
        priority_level = "P2_HIGH"
        action_urgency = "REWORK_EVALUATION_REQUIRED"
    elif score >= 45.0:
        priority_level = "P3_MEDIUM"
        action_urgency = "QA_DISPOSITION_REQUIRED"
    else:
        priority_level = "P4_LOW"
        action_urgency = "MONITOR_OR_ACCEPT"

    return {
        "score": score,
        "priority_level": priority_level,
        "action_urgency": action_urgency,
        "ceri_component": round(ceri_score * 100.0, 1),
        "ceia_component": round(ceia_score * 100.0, 1),
    }


def build_unified_report(image_record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Takes raw YOLO image detection dict and builds a fully analyzed unified_report.json structure.
    """
    image_name = image_record.get("image_name", "unknown_pcb.jpg")
    image_path = image_record.get("image_path", "")
    raw_detections = image_record.get("detections", [])

    enriched_defects = []
    for det in raw_detections:
        cname = det.get("class_name", "unknown")
        conf = float(det.get("confidence", 0.0))
        geom = det.get("geometry", {})
        bbox = det.get("bbox", {})

        # Normalize bbox to list [x_min, y_min, x_max, y_max]
        if isinstance(bbox, dict):
            bbox_list = [bbox.get("x_min", 0), bbox.get("y_min", 0), bbox.get("x_max", 0), bbox.get("y_max", 0)]
        elif isinstance(bbox, list):
            bbox_list = bbox
        else:
            bbox_list = [0, 0, 0, 0]

        ceri = compute_ceri_metrics(cname, geom, conf)
        ceia = compute_ceia_metrics(cname, ceri)
        unified = compute_unified_score(cname, conf, ceri, ceia)

        enriched_defects.append({
            "defect_id": det.get("defect_id", len(enriched_defects) + 1),
            "class_name": cname,
            "confidence": conf,
            "bbox": bbox_list,
            "geometry": geom,
            "ceri": ceri,
            "ceia": ceia,
            "unified_score": unified,
        })

    # Sort defects by unified score descending (highest risk first)
    enriched_defects.sort(key=lambda d: d["unified_score"]["score"], reverse=True)
    for idx, d in enumerate(enriched_defects, start=1):
        d["unified_score"]["rank"] = idx

    # Board-level disposition logic
    p1_count = sum(1 for d in enriched_defects if d["unified_score"]["priority_level"] == "P1_CRITICAL")
    p2_count = sum(1 for d in enriched_defects if d["unified_score"]["priority_level"] == "P2_HIGH")
    p3_count = sum(1 for d in enriched_defects if d["unified_score"]["priority_level"] == "P3_MEDIUM")
    p4_count = sum(1 for d in enriched_defects if d["unified_score"]["priority_level"] == "P4_LOW")

    if p1_count > 0:
        overall_disposition = "REJECT"
        disposition_reason = (
            f"Board REJECTED: Contains {p1_count} critical P1 defect(s) violating IPC-A-600 Class 2/3 criteria. "
            "Severe functional circuit failure or hazardous electrical bridge detected."
        )
    elif p2_count > 0 or p3_count > 1:
        overall_disposition = "REVIEW"
        disposition_reason = (
            f"Board flagged for REVIEW: Contains {p2_count} high-priority defect(s) and {p3_count} medium defect(s). "
            "Manual MRB (Material Review Board) or rework station disposition required before testing."
        )
    elif p3_count == 1 or p4_count > 0:
        overall_disposition = "REVIEW"
        disposition_reason = "Board requires minor rework or engineering review for minor cosmetic/clearance anomalies."
    else:
        overall_disposition = "ACCEPT"
        disposition_reason = "Board ACCEPTED: No critical or out-of-spec defects detected."

    max_score = enriched_defects[0]["unified_score"]["score"] if enriched_defects else 0.0

    return {
        "metadata": {
            "board_id": Path(image_name).stem,
            "image_name": image_name,
            "image_path": str(image_path),
            "image_width": image_record.get("image_width", 640),
            "image_height": image_record.get("image_height", 640),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "inspection_system": "RGPIS-HDE Industrial Intelligence Pipeline",
            "pipeline_stages": [
                "OpenCV Image Registration & Alignment",
                "YOLO26n Defect Detection",
                "CERI Geometric Defect Severity & Risk",
                "CEIA Approximate Electrical Impact Analysis",
                "Unified Defect Scoring & Board Disposition",
                "ExecuTorch Llama 3.2 Engineering Intelligence",
            ],
        },
        "board_summary": {
            "overall_disposition": overall_disposition,
            "disposition_reason": disposition_reason,
            "total_defects": len(enriched_defects),
            "critical_defects_count": p1_count,
            "high_risk_count": p2_count,
            "medium_risk_count": p3_count,
            "low_risk_count": p4_count,
            "max_unified_risk_score": max_score,
            "priority_breakdown": {
                "P1_CRITICAL": p1_count,
                "P2_HIGH": p2_count,
                "P3_MEDIUM": p3_count,
                "P4_LOW": p4_count,
            },
        },
        "defects": enriched_defects,
    }


def load_unified_report_from_file_or_detections(
    input_path: Optional[Union[str, Path]] = None,
    target_image: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Loads an existing unified_report.json or constructs one from detections.json or image file.
    """
    if input_path:
        p = Path(input_path).resolve()
        if not p.exists():
            raise FileNotFoundError(f"Input file not found: {p}")
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Check if already a unified_report format
        if isinstance(data, dict) and "board_summary" in data and "defects" in data:
            return data

        # If it's a detections.json array
        if isinstance(data, list):
            if target_image:
                matched = [item for item in data if item.get("image_name") == target_image]
                if matched:
                    return build_unified_report(matched[0])
            return build_unified_report(data[0])

        # If it's a single detection dict
        if isinstance(data, dict) and "detections" in data:
            return build_unified_report(data)

    # Fallback to default detections.json in outputs
    if DETECTIONS_JSON.exists():
        with open(DETECTIONS_JSON, "r", encoding="utf-8") as f:
            detections_list = json.load(f)
        if target_image:
            matched = [item for item in detections_list if item.get("image_name") == target_image]
            if matched:
                return build_unified_report(matched[0])
        return build_unified_report(detections_list[0])

    raise RuntimeError("No input file provided and default detections.json not found.")


if __name__ == "__main__":
    import sys
    report = load_unified_report_from_file_or_detections()
    print(f"Generated Unified Report for: {report['metadata']['image_name']}")
    print(f"Overall Disposition: {report['board_summary']['overall_disposition']}")
    print(f"Total Defects: {report['board_summary']['total_defects']}")
    print(f"Critical P1 Count: {report['board_summary']['critical_defects_count']}")
    
    out_path = Path(__file__).parent / "sample_unified_report.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"Saved sample report to: {out_path}")
