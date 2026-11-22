#!/usr/bin/env python3
"""
RGPIS-HDE Engineering Intelligence Master Runner.
Transforms defect detections into an explainable, actionable PCB Engineering Intelligence Report.

Usage:
  # Analyze default board (deep_12100046.jpg with all 6 defect types):
  python -m llama_advisory.run_engineering_intelligence

  # Analyze specific image or report:
  python -m llama_advisory.run_engineering_intelligence --image deep_12100052.jpg
  python -m llama_advisory.run_engineering_intelligence --file llama_advisory/sample_unified_report.json

  # Ask a specific question:
  python -m llama_advisory.run_engineering_intelligence --query "Why was this PCB rejected?"

  # Launch interactive Q&A session:
  python -m llama_advisory.run_engineering_intelligence --qa
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

from llama_advisory.unified_pipeline_bridge import (
    load_unified_report_from_file_or_detections,
)
from llama_advisory.engineering_intelligence import EngineeringIntelligenceEngine
from llama_advisory.engineer_qa import EngineerQAInterface, run_interactive_qa_session
from llama_advisory.dashboard_generator import (
    generate_dashboard_html,
    generate_markdown_report,
)


def print_banner():
    print("\n" + "=" * 78)
    print("  🔬 RGPIS-HDE PCB ENGINEERING INTELLIGENCE LAYER")
    print("  Bharat AI-SoC Challenge 2026/27 | Offline ExecuTorch Llama 3.2 Engine")
    print("=" * 78)


def print_executive_summary(report: dict, intel: dict, html_path: Path, md_path: Path, json_path: Path):
    meta = report.get("metadata", {})
    summary = report.get("board_summary", {})
    board_level = intel.get("board_level_intelligence", {})
    defects = intel.get("individual_defect_intelligence", [])
    actions = intel.get("corrective_action_recommendations", [])
    process = intel.get("process_intelligence", {})

    disp = summary.get("overall_disposition", "UNKNOWN")
    board_id = meta.get("board_id", "PCB")
    total = summary.get("total_defects", len(defects))
    p1 = summary.get("critical_defects_count", 0)
    p2 = summary.get("high_risk_count", 0)
    max_score = summary.get("max_unified_risk_score", 0.0)

    print("\n" + "─" * 78)
    print(f"  BOARD IDENTIFIER     : {board_id}")
    print(f"  FINAL DISPOSITION    : {disp}")
    print(f"  UNIFIED RISK SCORE   : {max_score}/100")
    print(f"  DEFECT DISTRIBUTION  : {total} Total | {p1} Critical (P1) | {p2} High Risk (P2)")
    print(f"  INSPECTION STANDARD  : IPC-A-600 / IPC-6012 Class 2/3")
    print(f"  RUNTIME BACKEND      : ExecuTorch (XNNPACK CPU Offline)")
    print("─" * 78)

    print("\n  📋 1. BOARD-LEVEL INTELLIGENCE REPORT:")
    print(f"     Condition : {board_level.get('board_condition')}")
    print(f"     Rationale : {board_level.get('acceptance_rationale')}")
    print("     Major Risks:")
    for r in board_level.get("major_risks", []):
        print(f"       • ⚠️  {r}")
    print("     Immediate Priorities:")
    for p in board_level.get("immediate_priorities", []):
        print(f"       • 🎯 {p}")

    print("\n  🛠️  2. PRIORITIZED CORRECTIVE ACTION PLAN:")
    for a in actions[:4]:
        print(f"     Step #{a.get('step_number')} [{a.get('priority_level')} - Score {a.get('unified_score')}]: {a.get('defect_name')}")
        print(f"       Action : {a.get('recommended_action')}")
        print(f"       Verify : {'; '.join(a.get('verification_procedure', []))}")

    print("\n  🏭 3. MANUFACTURING PROCESS INTELLIGENCE (HYPOTHESES):")
    print(f"     Pattern   : {process.get('pattern_summary')}")
    print("     Hypotheses:")
    for h in process.get("fab_stage_hypotheses", []):
        print(f"       • 🔬 {h}")
    print("     Recommended Audits:")
    for inv in process.get("recommended_investigations", []):
        print(f"       • ✅ {inv}")

    print("\n" + "─" * 78)
    print("  📁 GENERATED INTELLIGENCE ARTIFACTS & DASHBOARDS:")
    print(f"  • Interactive HTML Dashboard : {html_path}")
    print(f"  • Formal Markdown Traveler   : {md_path}")
    print(f"  • Structured JSON Model      : {json_path}")
    print("─" * 78 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="RGPIS-HDE Engineering Intelligence Master Runner"
    )
    parser.add_argument(
        "--image",
        type=str,
        default=None,
        help="Target image name from detections (e.g. deep_12100046.jpg or deep_12100052.jpg)",
    )
    parser.add_argument(
        "--file",
        type=str,
        default=None,
        help="Path to pre-existing unified_report.json or detections JSON",
    )
    parser.add_argument(
        "--query",
        type=str,
        default=None,
        help="Direct question for contextual Engineer Q&A",
    )
    parser.add_argument(
        "--qa",
        action="store_true",
        help="Launch interactive Engineer Q&A terminal session after analysis",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Run in fast deterministic mode (skips heavy LLM autoregression)",
    )
    parser.add_argument(
        "--all-llama",
        action="store_true",
        help="Run Llama generation across every individual defect (slower)",
    )

    args = parser.parse_args()
    print_banner()

    # Step 1: Ingest and build Unified Report
    target_img = args.image
    if not target_img and not args.file:
        target_img = "deep_12100046.jpg"  # default showcase board with all 6 classes

    print(f"  Loading Unified Inspection Data (Target: {target_img or args.file})...")
    report = load_unified_report_from_file_or_detections(input_path=args.file, target_image=target_img)

    # Step 2: Initialize Engineering Intelligence Engine
    engine = EngineeringIntelligenceEngine()
    use_llama = not args.fast
    max_llama_defects = 6 if args.all_llama else 1

    print(f"  Generating Engineering Intelligence (Llama Engine: {'ACTIVE' if use_llama else 'FAST_MODE'})...")
    start_t = time.time()
    intel = engine.analyze_board(report, use_llama=use_llama, max_defects_llama=max_llama_defects)
    total_dur = round(time.time() - start_t, 2)

    # Step 3: Export Artifacts
    board_id = report.get("metadata", {}).get("board_id", "board")
    out_dir = PROJECT_ROOT / "outputs" / "intelligence"
    out_dir.mkdir(parents=True, exist_ok=True)

    html_file = out_dir / f"{board_id}_intelligence_dashboard.html"
    md_file = out_dir / f"{board_id}_engineering_report.md"
    json_file = out_dir / f"{board_id}_engineering_intelligence.json"

    generate_dashboard_html(report, intel, html_file)
    generate_markdown_report(report, intel, md_file)
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(intel, f, indent=2)

    # Step 4: Display Summary
    print_executive_summary(report, intel, html_file, md_file, json_file)

    # Step 5: Answer Single Query if requested
    if args.query:
        print("\n" + "=" * 78)
        print(f"  🔍 CONTEXTUAL ENGINEER Q&A")
        print("=" * 78)
        qa = EngineerQAInterface(report, intel, engine.engine)
        ans = qa.answer_query(args.query, use_llama=use_llama)
        print(f"\n  Engineer Query : \"{args.query}\"")
        print(f"  Intelligence   : {ans['answer']}")
        print(f"  Engine Source  : {ans['engine']} (Latency: {ans['latency_seconds']}s)\n")

    # Step 6: Interactive Q&A Session if requested
    if args.qa:
        qa = EngineerQAInterface(report, intel, engine.engine)
        qa.initialize()
        print("\n" + "=" * 78)
        print("  Entering Interactive Engineer Q&A Console (Type 'exit' to quit)...")
        print("=" * 78 + "\n")
        while True:
            try:
                q = input("Engineer Q: ").strip()
                if not q:
                    continue
                if q.lower() in ("exit", "quit", "q"):
                    break
                ans = qa.answer_query(q, use_llama=use_llama)
                print(f"\nIntelligence Answer:\n{ans['answer']}")
                print(f"[Engine: {ans['engine']} | Latency: {ans['latency_seconds']}s]\n")
            except (KeyboardInterrupt, EOFError):
                break


if __name__ == "__main__":
    main()
