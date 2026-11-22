#!/usr/bin/env python3
"""
RGPIS-HDE PCB Defect Advisory CLI Runner.
Provides simple single-defect testing, interactive mode, and full 8-case benchmark.
Powered by Meta Llama 3.2 1B Instruct on PyTorch ExecuTorch (XNNPACK CPU).
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from llama_advisory.defect_advisor import PCBDefectAdvisor
from llama_advisory.test_suite import run_benchmark, TEST_CASES


def print_header(title: str):
    print("\n" + "=" * 72)
    print(f"  {title}")
    print("=" * 72)


def print_advisory(res: dict):
    print("\n" + "─" * 72)
    print("  📋 PCB DEFECT ADVISORY REPORT")
    print("─" * 72)
    print(f"  Defect Type        : {res.get('defect_type', 'N/A').upper()}")
    print(f"  Detection Conf     : {res.get('confidence', 'N/A')}")
    print(f"  Coordinates (BBox) : {res.get('location', [0, 0, 0, 0])}")
    print(f"  Advisory Engine    : {res.get('engine', 'N/A')}")
    print(f"  Validation Status  : {res.get('verification_status', 'FALLBACK')}")

    if res.get("raw_generated"):
        print(f"\n  📝 Raw Llama-Generated Text (from ExecuTorch):")
        raw = res['raw_generated'].strip()
        print(f"     \"{raw}\"")

    print(f"\n  📖 Explanation:")
    print(f"     {res.get('explanation', 'N/A')}")

    print(f"\n  ⚠️  Possible Consequences:")
    consequences = res.get("possible_consequences", [])
    if isinstance(consequences, list):
        for c in consequences:
            print(f"     • {c}")
    else:
        print(f"     • {consequences}")

    print(f"\n  🔍 Recommended Verification Procedure:")
    proc = res.get("recommended_verification_procedure", [])
    if isinstance(proc, list):
        for i, step in enumerate(proc, 1):
            print(f"     {i}. {step}")
    else:
        print(f"     1. {proc}")

    print(f"\n  🛠️  Operator Guidance:")
    print(f"     {res.get('operator_guidance', 'N/A')}")

    uw = res.get("uncertainty_warning")
    if uw:
        print(f"\n  ⚡ Uncertainty Warning:")
        print(f"     {uw}")

    print(f"\n  ⚖️  Regulatory & Safety Disclaimer:")
    print(f"     {res.get('disclaimer', 'N/A')}")

    metrics = res.get("metrics", {})
    print("\n" + "─" * 72)
    print("  ⚡ Execution Metrics (ExecuTorch Offline Runtime)")
    print("─" * 72)
    print(f"  Inference Latency  : {metrics.get('latency_seconds', 0.0):.2f} seconds")
    print(f"  Tokens Generated   : {metrics.get('generated_tokens', 0)} tokens")
    print(f"  Generation Speed   : {metrics.get('tokens_per_second', 0.0):.2f} tokens/second")
    print(f"  Peak RAM Usage     : {metrics.get('ram_usage_mb', 0.0):.1f} MB")
    print(f"  Runtime Backend    : {metrics.get('engine', 'ExecuTorch XNNPACK CPU')}")
    print("─" * 72 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="RGPIS-HDE Llama 3.2 ExecuTorch Industrial PCB Defect Advisor"
    )
    parser.add_argument(
        "--defect",
        type=str,
        default="open_circuit",
        help="Defect type (open_circuit, short_circuit, mouse_bite, spur, spurious_copper, pin_hole, unknown)",
    )
    parser.add_argument(
        "--confidence",
        type=float,
        default=0.94,
        help="Detection confidence (e.g., 0.94)",
    )
    parser.add_argument(
        "--location",
        type=int,
        nargs=4,
        default=[120, 240, 165, 275],
        help="Bounding box coordinates [ymin, xmin, ymax, xmax]",
    )
    parser.add_argument(
        "--file",
        type=str,
        default=None,
        help="Path to a JSON file containing defect info (e.g., --file defect.json)",
    )
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Run full 8-case industrial test benchmark suite",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Interactive mode: enter defect parameters dynamically",
    )

    args = parser.parse_args()

    if args.benchmark:
        run_benchmark()
        return

    if args.file:
        with open(args.file, "r") as f:
            raw_data = json.load(f)
        # Handle YOLO predict.py output format or direct defect dict
        if isinstance(raw_data, list) and raw_data:
            defect_input = raw_data[0]
        elif isinstance(raw_data, dict) and "detections" in raw_data and raw_data["detections"]:
            det = raw_data["detections"][0]
            cname = det.get("class_name", "unknown")
            class_map = {
                "open": "open_circuit",
                "short": "short_circuit",
                "mousebite": "mouse_bite",
                "spur": "spur",
                "copper": "spurious_copper",
                "pin-hole": "pin_hole",
            }
            mapped_name = class_map.get(cname, cname)
            bbox = det.get("bbox", {})
            if isinstance(bbox, dict):
                loc = [int(bbox.get("y_min", 0)), int(bbox.get("x_min", 0)), int(bbox.get("y_max", 0)), int(bbox.get("x_max", 0))]
            else:
                loc = [0, 0, 0, 0]
            defect_input = {
                "defect_type": mapped_name,
                "confidence": float(det.get("confidence", 0.90)),
                "location": loc,
            }
        else:
            defect_input = raw_data
    elif args.interactive:
        print_header("RGPIS-HDE Interactive Defect Advisory Console")
        print("Available DeepPCB categories: open_circuit, short_circuit, mouse_bite, spur, spurious_copper, pin_hole")
        try:
            d_type = input("\nEnter defect type [open_circuit]: ").strip() or "open_circuit"
            c_str = input("Enter confidence score (0.0 - 1.0) [0.94]: ").strip() or "0.94"
            conf = float(c_str)
        except (KeyboardInterrupt, ValueError):
            print("\nExiting.")
            return
        defect_input = {
            "defect_type": d_type,
            "confidence": conf,
            "location": [100, 200, 150, 250],
        }
    else:
        defect_input = {
            "defect_type": args.defect,
            "confidence": args.confidence,
            "location": args.location,
        }

    print_header("Running ExecuTorch Llama 3.2 1B Inference")
    print(f"Target Input: {json.dumps(defect_input)}")
    print("Loading model and generating advisory...")

    advisor = PCBDefectAdvisor()
    advisor.initialize()

    res = advisor.advise(defect_input, max_new_tokens=380)
    print_advisory(res)


if __name__ == "__main__":
    main()
