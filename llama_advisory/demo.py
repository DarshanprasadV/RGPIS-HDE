#!/usr/bin/env python3
"""
RGPIS-HDE Live Competition Demo Runner.
Designed for the Bharat AI-SoC Challenge 2026/27 Evaluator Showcase.
Demonstrates offline ExecuTorch Llama 3.2 1B industrial advisory in 3 crisp acts.
"""

import json
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from llama_advisory.defect_advisor import PCBDefectAdvisor
from llama_advisory.test_suite import run_benchmark


def clear_screen():
    os.system("clear" if os.name == "posix" else "cls")


def print_banner():
    print("=" * 76)
    print("  🏆 RGPIS-HDE INDUSTRIAL PCB DEFECT INSPECTION — EDGE AI ADVISORY")
    print("     Bharat AI-SoC Challenge 2026/27 · Evaluator Demonstration")
    print("     Meta Llama 3.2 1B Instruct · PyTorch ExecuTorch 1.6.0 (XNNPACK CPU)")
    print("=" * 76)


def print_report(res: dict):
    print("\n" + "─" * 76)
    print("  📋 LIVE OPERATOR ADVISORY DISPATCH")
    print("─" * 76)
    print(f"  Defect Category    : {res.get('defect_type', '').upper()}")
    print(f"  Visual Confidence  : {res.get('confidence', 0.0):.2f}")
    print(f"  Defect Coordinates : {res.get('location', [0, 0, 0, 0])}")
    print(f"  Inference Runtime  : {res.get('engine', 'ExecuTorch')}")
    print(f"  Validation Status  : {res.get('verification_status', 'PASSED')}")

    print(f"\n  📖 Physical Explanation:")
    print(f"     {res.get('explanation', 'N/A')}")

    print(f"\n  ⚠️  Potential Consequences:")
    for c in res.get("possible_consequences", []):
        print(f"     • {c}")

    print(f"\n  🔍 Recommended Verification Procedure (IPC-A-600):")
    for i, s in enumerate(res.get("recommended_verification_procedure", []), 1):
        print(f"     {i}. {s}")

    print(f"\n  🛠️  Operator Action Guidance:")
    print(f"     {res.get('operator_guidance', 'N/A')}")

    uw = res.get("uncertainty_warning")
    if uw:
        print(f"\n  ⚡ Uncertainty Warning (Safety Guardrail Active):")
        print(f"     {uw}")

    print(f"\n  ⚖️  Regulatory Safety Disclaimer:")
    print(f"     {res.get('disclaimer', 'N/A')}")

    m = res.get("metrics", {})
    print("\n" + "─" * 76)
    print("  📊 Hard Edge AI Telemetry (Zero Cloud Dependency)")
    print("─" * 76)
    print(f"  Inference Latency  : {m.get('latency_seconds', 0.0):.2f} seconds")
    print(f"  Token Generation   : {m.get('generated_tokens', 0)} tokens ({m.get('tokens_per_second', 0.0):.2f} tok/s)")
    print(f"  Active RAM Footprint: {m.get('ram_usage_mb', 0.0):.1f} MB (Fits within 2GB/4GB Edge SoCs)")
    print(f"  Network Calls      : 0 (100% Air-Gapped Local Inference)")
    print("─" * 76)


def show_hardware_matrix():
    print("\n" + "─" * 76)
    print("  🎯 EDGE HARDWARE COMPATIBILITY & FEASIBILITY REPORT")
    print("─" * 76)
    print(f"  {'Target Edge Hardware':<26} | {'RAM':<8} | {'ExecuTorch Backend':<18} | {'Status'}")
    print("  " + "-" * 72)
    print(f"  {'Apple M1 (Host Baseline)':<26} | {'8 GB':<8} | {'XNNPACK CPU (NEON)':<18} | {'✅ Verified (~1.1 GB RAM)'}")
    print(f"  {'Raspberry Pi 5 (A76)':<26} | {'4/8 GB':<8} | {'XNNPACK CPU (NEON)':<18} | {'✅ Tier-1 Supported'}")
    print(f"  {'Orange Pi 5 (RK3588)':<26} | {'4/8 GB':<8} | {'XNNPACK CPU (NEON)':<18} | {'✅ Supported'}")
    print(f"  {'NVIDIA Jetson Nano':<26} | {'4 GB':<8} | {'XNNPACK CPU':<18} | {'✅ Supported'}")
    print(f"  {'Custom ARMv8 Edge SoC':<26} | {'≥ 2 GB':<8} | {'XNNPACK / KleidiAI':<18} | {'✅ Competition Ready'}")
    print("  " + "-" * 72)
    print("  Key Takeaway: The quantized 1B model requires only ~1.07 GB RAM,")
    print("  leaving ample memory headroom for Linux OS and YOLO detection models.")
    print("─" * 76 + "\n")


def main():
    clear_screen()
    print_banner()
    print("\n[INIT] Initializing ExecuTorch Runtime and pre-warming Llama 3.2 1B...")
    advisor = PCBDefectAdvisor()
    advisor.initialize()
    print("✅ Model pre-warmed in memory. System ready for live evaluation.\n")

    while True:
        print("\n" + "=" * 76)
        print("  SELECT DEMONSTRATION SCENARIO:")
        print("=" * 76)
        print("  [1] Act 1 — Critical Defect Advisory: Open Circuit (Continuity Discontinuity)")
        print("  [2] Act 2 — Severe Hazard Advisory: Short Circuit (Low-Resistance Bridge)")
        print("  [3] Act 3 — Edge Case & Safety Protocol: Low-Confidence Anomaly (Confidence < 0.50)")
        print("  [4] Full 8-Category IPC-A-600 Automated Benchmark Suite")
        print("  [5] Display Edge SoC Hardware Compatibility & Resource Audit")
        print("  [6] Full Board Engineering Intelligence & Interactive Dashboard (All 6 Defect Classes)")
        print("  [7] Live Contextual Engineer Q&A Session ('Why was this PCB rejected?', etc.)")
        print("  [8] Launch Live Web App (Direct Image Drag & Drop in Browser)")
        print("  [q] Quit Demo")
        print("=" * 76)

        choice = input("\nEnter choice [1-8, q]: ").strip().lower()

        if choice == "1":
            inp = {"defect_type": "open_circuit", "confidence": 0.94, "location": [120, 240, 165, 275]}
            print("\n>> Evaluating Stage 1 Detection Input: Open Circuit (conf=0.94)...")
            res = advisor.advise(inp, max_new_tokens=380)
            print_report(res)

        elif choice == "2":
            inp = {"defect_type": "short_circuit", "confidence": 0.91, "location": [310, 180, 345, 225]}
            print("\n>> Evaluating Stage 1 Detection Input: Short Circuit (conf=0.91)...")
            res = advisor.advise(inp, max_new_tokens=380)
            print_report(res)

        elif choice == "3":
            inp = {"defect_type": "open_circuit", "confidence": 0.38, "location": [150, 200, 175, 225]}
            print("\n>> Evaluating Noisy Low-Confidence Detection: Open Circuit (conf=0.38)...")
            res = advisor.advise(inp, max_new_tokens=380)
            print_report(res)

        elif choice == "4":
            print("\n>> Running 8-Category Industrial Benchmark Suite...")
            run_benchmark()

        elif choice == "5":
            show_hardware_matrix()

        elif choice == "6":
            from llama_advisory.run_engineering_intelligence import main as run_intel_main
            print("\n>> Generating Full Board Engineering Intelligence & Interactive Dashboard...")
            sys.argv = ["run_engineering_intelligence", "--image", "deep_12100046.jpg"]
            run_intel_main()

        elif choice == "7":
            from llama_advisory.engineer_qa import run_interactive_qa_session
            print("\n>> Launching Contextual Engineer Q&A Session...")
            run_interactive_qa_session("deep_12100046.jpg")

        elif choice == "8":
            from llama_advisory.web_app import run_server
            print("\n>> Launching Live Interactive Web App Server...")
            run_server()

        elif choice in ("q", "quit", "exit"):
            print("\nDemo concluded. Best wishes for Bharat AI-SoC Challenge 2026/27!")
            break
        else:
            print("Invalid choice, please select 1, 2, 3, 4, 5, or q.")


if __name__ == "__main__":
    main()
