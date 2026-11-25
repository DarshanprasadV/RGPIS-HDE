"""
RGPIS-HDE Inspection Logger Module
Provides persistent audit logging, historical tracking, and export capabilities (CSV / JSONL)
for real-time PCB automated optical inspection (AOI) runs, conforming to IPC-A-600 quality standards.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

logger = logging.getLogger("RGPIS-HDE.InspectionLogger")

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
LOG_DIR = PROJECT_ROOT / "outputs" / "logs"
JSONL_LOG_PATH = LOG_DIR / "inspection_history.jsonl"
CSV_LOG_PATH = LOG_DIR / "inspection_log.csv"

_LOCK = threading.Lock()

CSV_HEADERS = [
    "inspection_id",
    "timestamp_iso",
    "timestamp_readable",
    "board_id",
    "image_name",
    "inspection_mode",
    "disposition",
    "total_defects",
    "p1_critical",
    "p2_high",
    "p3_medium",
    "p4_low",
    "max_trace_loss_pct",
    "max_current_density_A_m2",
    "max_unified_risk_score",
    "defect_classes",
    "inference_duration_seconds",
    "ipc_classification",
]


def ensure_log_dir() -> None:
    """Ensures log directory and initialized files exist."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if not CSV_LOG_PATH.exists():
        with open(CSV_LOG_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_HEADERS)
    if not JSONL_LOG_PATH.exists():
        JSONL_LOG_PATH.touch()


def log_inspection(
    intel_or_summary: Dict[str, Any],
    image_name: str,
    board_id: Optional[str] = None,
    mode: str = "LIVE_CAMERA",
    duration_seconds: float = 0.0,
    disposition_override: Optional[str] = None,
    status: str = "success",
) -> Dict[str, Any]:
    """
    Atomically appends an inspection result to the JSONL history and CSV log.
    
    Args:
        intel_or_summary: Full engineering intelligence dictionary or summary.
        image_name: Filename of the analyzed PCB image.
        board_id: Board identifier (defaults to stem of image_name).
        mode: LIVE_CAMERA, FILE_UPLOAD, SAMPLE_BENCHMARK, CONTINUOUS_SCAN.
        duration_seconds: Latency in seconds.
        disposition_override: Used for NON-PCB or special states.
        status: success, not_a_pcb, error.
        
    Returns:
        The complete logged inspection record.
    """
    ensure_log_dir()

    now = datetime.now()
    iso_ts = now.isoformat()
    readable_ts = now.strftime("%Y-%m-%d %H:%M:%S")
    insp_id = f"INSP-{now.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"

    stem = board_id or Path(image_name).stem
    meta = intel_or_summary.get("metadata", {})
    summary = intel_or_summary.get("board_summary", {})
    board_level = intel_or_summary.get("board_level_intelligence", {})
    defects = intel_or_summary.get("individual_defect_intelligence", [])

    if status == "not_a_pcb":
        disposition = "NON-PCB"
        total_defects = 0
        p1 = p2 = p3 = p4 = 0
        max_trace_loss = 0.0
        max_current_density = 0.0
        max_risk = 0.0
        classes_str = "None (OOD Scene)"
        ipc_classification = "Non-Circuit Scene (Optical Gatekeeper Filtered)"
        defects_summary = []
    else:
        disposition = disposition_override or summary.get("overall_disposition", "REVIEW")
        total_defects = summary.get("total_defects", len(defects))
        pbreakdown = summary.get("priority_breakdown", {})
        p1 = pbreakdown.get("P1_CRITICAL", summary.get("critical_defects_count", 0))
        p2 = pbreakdown.get("P2_HIGH", summary.get("high_risk_count", 0))
        p3 = pbreakdown.get("P3_MEDIUM", summary.get("medium_risk_count", 0))
        p4 = pbreakdown.get("P4_LOW", summary.get("low_risk_count", 0))

        # CERI & CEIA extrema
        max_trace_loss = 0.0
        max_current_density = 0.0
        classes_set = set()

        defects_summary = []
        for d in defects:
            cname = d.get("class_name", "unknown")
            classes_set.add(cname)
            ceri = d.get("ceri_metrics", {}).get("trace_width_reduction_pct", 0.0)
            if ceri > max_trace_loss:
                max_trace_loss = ceri
            j_val = d.get("ceia_proxies", {}).get("current_density_A_m2", 0.0)
            if j_val > max_current_density:
                max_current_density = j_val
            
            defects_summary.append({
                "defect_id": d.get("defect_id"),
                "class_name": cname,
                "priority": d.get("priority", "P3"),
                "bbox": d.get("bbox", {}),
                "action": d.get("action_summary", ""),
            })

        max_risk = float(summary.get("max_unified_risk_score", 0.0))
        classes_str = ", ".join(sorted(classes_set)) if classes_set else "None"
        ipc_classification = (
            "IPC-A-600 Class 2/3 Non-Conforming (Quarantine)"
            if disposition == "REJECT"
            else "IPC-A-600 Class 3 Conforming (Approved)"
            if disposition == "ACCEPT"
            else "IPC-A-600 Engineering Review Required"
        )

    record = {
        "inspection_id": insp_id,
        "timestamp_iso": iso_ts,
        "timestamp_readable": readable_ts,
        "board_id": stem,
        "image_name": image_name,
        "inspection_mode": mode,
        "status": status,
        "disposition": disposition,
        "total_defects": total_defects,
        "priority_breakdown": {
            "P1_CRITICAL": p1,
            "P2_HIGH": p2,
            "P3_MEDIUM": p3,
            "P4_LOW": p4,
        },
        "max_trace_loss_pct": round(float(max_trace_loss), 2),
        "max_current_density_A_m2": float(max_current_density),
        "max_unified_risk_score": round(float(max_risk), 1),
        "defect_classes": sorted(list(classes_set)) if status != "not_a_pcb" else [],
        "defect_classes_str": classes_str,
        "inference_duration_seconds": round(float(duration_seconds), 2),
        "ipc_classification": ipc_classification,
        "board_condition": board_level.get("board_condition", "Inspection Complete"),
        "defects": defects_summary,
    }

    # Atomically write to both JSONL and CSV
    with _LOCK:
        try:
            with open(JSONL_LOG_PATH, "a", encoding="utf-8") as f_jsonl:
                f_jsonl.write(json.dumps(record, ensure_ascii=False) + "\n")

            with open(CSV_LOG_PATH, "a", newline="", encoding="utf-8") as f_csv:
                writer = csv.writer(f_csv)
                writer.writerow([
                    record["inspection_id"],
                    record["timestamp_iso"],
                    record["timestamp_readable"],
                    record["board_id"],
                    record["image_name"],
                    record["inspection_mode"],
                    record["disposition"],
                    record["total_defects"],
                    p1,
                    p2,
                    p3,
                    p4,
                    record["max_trace_loss_pct"],
                    record["max_current_density_A_m2"],
                    record["max_unified_risk_score"],
                    record["defect_classes_str"],
                    record["inference_duration_seconds"],
                    record["ipc_classification"],
                ])
            logger.info(f"Logged inspection {insp_id} for board '{stem}' -> {disposition}")
        except Exception as e:
            logger.error(f"Failed to append inspection log: {e}")

    return record


def get_inspection_history(limit: int = 100, reverse: bool = True) -> List[Dict[str, Any]]:
    """Retrieves chronological inspection log entries."""
    ensure_log_dir()
    records: List[Dict[str, Any]] = []

    if not JSONL_LOG_PATH.exists():
        return records

    with _LOCK:
        try:
            with open(JSONL_LOG_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except Exception:
                            continue
        except Exception as e:
            logger.error(f"Error reading inspection history: {e}")

    if reverse:
        records.reverse()

    return records[:limit]


def get_inspection_stats() -> Dict[str, Any]:
    """Computes aggregate analytics and yield stats across logged inspections."""
    history = get_inspection_history(limit=1000, reverse=False)
    total = len(history)
    if total == 0:
        return {
            "total_inspections": 0,
            "accept_count": 0,
            "reject_count": 0,
            "review_count": 0,
            "non_pcb_count": 0,
            "yield_rate_pct": 0.0,
            "defect_density_avg": 0.0,
            "avg_latency_seconds": 0.0,
            "defect_distribution": {},
        }

    accepts = sum(1 for r in history if r.get("disposition") == "ACCEPT")
    rejects = sum(1 for r in history if r.get("disposition") == "REJECT")
    reviews = sum(1 for r in history if r.get("disposition") == "REVIEW")
    non_pcbs = sum(1 for r in history if r.get("disposition") == "NON-PCB")

    pcb_total = total - non_pcbs
    yield_rate = (accepts / pcb_total * 100.0) if pcb_total > 0 else 0.0

    total_defects = sum(r.get("total_defects", 0) for r in history)
    avg_defects = round(total_defects / pcb_total, 2) if pcb_total > 0 else 0.0

    durations = [r.get("inference_duration_seconds", 0.0) for r in history if r.get("inference_duration_seconds", 0.0) > 0]
    avg_latency = round(sum(durations) / len(durations), 2) if durations else 0.0

    # Defect class frequency tally
    dist: Dict[str, int] = {}
    for r in history:
        for c in r.get("defect_classes", []):
            dist[c] = dist.get(c, 0) + 1

    return {
        "total_inspections": total,
        "valid_pcb_inspections": pcb_total,
        "accept_count": accepts,
        "reject_count": rejects,
        "review_count": reviews,
        "non_pcb_count": non_pcbs,
        "yield_rate_pct": round(yield_rate, 1),
        "total_defects_logged": total_defects,
        "avg_defects_per_board": avg_defects,
        "avg_latency_seconds": avg_latency,
        "defect_distribution": dist,
    }


def clear_inspection_history() -> bool:
    """Safely clears the inspection log files."""
    ensure_log_dir()
    with _LOCK:
        try:
            with open(JSONL_LOG_PATH, "w", encoding="utf-8") as f:
                f.truncate(0)
            with open(CSV_LOG_PATH, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(CSV_HEADERS)
            return True
        except Exception as e:
            logger.error(f"Failed to clear inspection logs: {e}")
            return False


def seed_benchmark_inspections_if_empty() -> None:
    """Pre-populates the inspection log with verified benchmark boards if log is empty."""
    ensure_log_dir()
    if JSONL_LOG_PATH.stat().st_size > 0:
        return

    intel_dir = PROJECT_ROOT / "outputs" / "intelligence"
    benchmark_files = sorted(intel_dir.glob("*_engineering_intelligence.json"))
    for jf in benchmark_files:
        try:
            with open(jf, "r", encoding="utf-8") as f:
                intel = json.load(f)
            bid = jf.stem.replace("_engineering_intelligence", "")
            img_name = f"{bid}.jpg"
            log_inspection(
                intel_or_summary=intel,
                image_name=img_name,
                board_id=bid,
                mode="SAMPLE_BENCHMARK",
                duration_seconds=0.45,
            )
        except Exception as e:
            logger.warning(f"Failed to seed benchmark {jf.name}: {e}")
