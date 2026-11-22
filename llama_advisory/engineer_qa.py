"""
RGPIS-HDE Contextual Engineer Q&A Interface.
Allows quality engineers and operators to interrogate the PCB inspection results,
ask why the board was rejected, which defect is most critical, what corrective actions
are recommended, and explore potential electrical consequences.

Powered by ExecuTorch Llama 3.2 1B Instruct offline runtime, with grounding in
IPC-A-600, CERI geometric risk scores, and CEIA electrical proxies.
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from llama_advisory.executorch_engine import ExecuTorchLlamaEngine
from llama_advisory.prompt_templates import build_engineer_qa_prompt
from llama_advisory.unified_pipeline_bridge import load_unified_report_from_file_or_detections

logger = logging.getLogger("EngineerQA")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class EngineerQAInterface:
    """
    Contextual Q&A session manager grounded in PCB inspection analysis data.
    """

    def __init__(
        self,
        report: Dict[str, Any],
        intelligence: Optional[Dict[str, Any]] = None,
        engine: Optional[ExecuTorchLlamaEngine] = None,
    ):
        self.report = report
        self.intelligence = intelligence or {}
        self.engine = engine or ExecuTorchLlamaEngine()
        self._is_loaded = False

    def initialize(self):
        """Pre-loads the ExecuTorch model."""
        if not self._is_loaded:
            self.engine.load_model()
            self._is_loaded = True

    def answer_query(
        self,
        query: str,
        use_llama: bool = True,
        max_new_tokens: int = 180,
    ) -> Dict[str, Any]:
        """
        Answers a user question grounded in the current board inspection data.
        Fast-paths common deterministic queries while offering full generative Llama reasoning.
        """
        clean_q = query.strip().lower()
        start_time = time.time()

        # Fast-path 1: Why was this PCB rejected / accepted?
        if "why" in clean_q and ("reject" in clean_q or "accept" in clean_q or "disposition" in clean_q):
            summary = self.report.get("board_summary", {})
            disposition = summary.get("overall_disposition", "UNKNOWN")
            reason = summary.get("disposition_reason", "")
            crit = summary.get("critical_defects_count", 0)
            answer_text = (
                f"Board '{self.report.get('metadata', {}).get('board_id')}' was marked as {disposition}. "
                f"Reason: {reason} "
                f"According to IPC-A-600 Class 2/3, functional circuit defects (such as opens or shorts) "
                f"mandate immediate line quarantine and prevent functional energization."
            )
            return {
                "query": query,
                "answer": answer_text,
                "source": "Grounded Unified Analysis & IPC Standards",
                "latency_seconds": round(time.time() - start_time, 3),
                "engine": "Deterministic Grounded Rule",
            }

        # Fast-path 2: Which defect is the most critical?
        if "which" in clean_q and ("critical" in clean_q or "worst" in clean_q or "priority" in clean_q):
            defects = self.report.get("defects", [])
            if defects:
                top = defects[0]
                did = top.get("defect_id")
                cname = top.get("class_name", "").upper()
                score = top.get("unified_score", {}).get("score")
                prio = top.get("unified_score", {}).get("priority_level")
                ceri_w = top.get("ceri", {}).get("trace_width_reduction_pct")
                ceri_c = top.get("ceri", {}).get("clearance_intrusion_pct")
                answer_text = (
                    f"Defect #{did} ({cname}) is the most critical anomaly on this board with a Unified Risk Score of "
                    f"{score}/100 ({prio}). CERI analysis confirms trace width reduction of {ceri_w}% and clearance "
                    f"intrusion of {ceri_c}%, posing the highest immediate threat to board functionality."
                )
            else:
                answer_text = "No defects were detected on this board."
            return {
                "query": query,
                "answer": answer_text,
                "source": "Grounded Defect Ranking Matrix",
                "latency_seconds": round(time.time() - start_time, 3),
                "engine": "Deterministic Grounded Rule",
            }

        # Fast-path 3: Corrective action for a specific defect (e.g. defect #2)
        import re
        match_defect = re.search(r"defect\s*#?\s*(\d+)", clean_q)
        if match_defect and ("correct" in clean_q or "action" in clean_q or "rework" in clean_q or "fix" in clean_q):
            target_id = int(match_defect.group(1))
            matched_defect = None
            for d in self.report.get("defects", []):
                if d.get("defect_id") == target_id:
                    matched_defect = d
                    break
            if matched_defect:
                # Find matching recommendation in intelligence
                action_text = None
                for act in self.intelligence.get("corrective_action_recommendations", []):
                    if act.get("defect_id") == target_id:
                        action_text = act.get("recommended_action")
                        verif = "; ".join(act.get("verification_procedure", []))
                        break
                if not action_text:
                    action_text = f"Perform localized microscopic review and IPC Class 2 rework for {matched_defect.get('class_name')}."
                    verif = "2-point DMM continuity or isolation measurement."
                answer_text = (
                    f"For Defect #{target_id} ({matched_defect.get('class_name').upper()}): "
                    f"Recommended Corrective Action: {action_text} "
                    f"Verification: {verif}"
                )
                return {
                    "query": query,
                    "answer": answer_text,
                    "source": "Grounded Rework Execution Protocol",
                    "latency_seconds": round(time.time() - start_time, 3),
                    "engine": "Deterministic Grounded Rule",
                }

        # Fast-path 4: Summarize the board inspection
        if "summar" in clean_q:
            summary = self.report.get("board_summary", {})
            total = summary.get("total_defects", 0)
            crit = summary.get("critical_defects_count", 0)
            disp = summary.get("overall_disposition", "UNKNOWN")
            breakdown = summary.get("priority_breakdown", {})
            p1 = breakdown.get("P1_CRITICAL", 0)
            p2 = breakdown.get("P2_HIGH", 0)
            answer_text = (
                f"Board Inspection Summary for {self.report.get('metadata', {}).get('board_id')}: "
                f"Overall Disposition is {disp}. Total of {total} defects detected, comprising {p1} Critical (P1) and "
                f"{p2} High-Risk (P2) defects. Primary failure modes involve conductor continuity interruptions and "
                f"clearance encroachments violating IPC-A-600 Class 2/3 limits."
            )
            return {
                "query": query,
                "answer": answer_text,
                "source": "Board Summary Matrix",
                "latency_seconds": round(time.time() - start_time, 3),
                "engine": "Deterministic Grounded Rule",
            }

        # Fast-path 5: Potential electrical consequences of short / open / defects
        if "consequence" in clean_q or "electrical" in clean_q or "impact" in clean_q:
            crit_defects = [
                d for d in self.report.get("defects", [])
                if d.get("unified_score", {}).get("priority_level") in ("P1_CRITICAL", "P2_HIGH")
            ]
            parts = []
            for d in crit_defects[:3]:
                cname = d.get("class_name", "").upper()
                did = d.get("defect_id")
                ceia = d.get("ceia", {})
                si = ceia.get("signal_integrity_risk", "LOW")
                th = ceia.get("thermal_dissipation_risk", "LOW")
                j_str = ceia.get("current_density_str", f"{ceia.get('current_density_multiplier', 1.0)}x")
                if "SHORT" in cname:
                    parts.append(f"Defect #{did} (SHORT): Severe surge current density ({j_str}) across bridged conductors, risking power rail shutdown or thermal trace vaporization.")
                elif "OPEN" in cname:
                    parts.append(f"Defect #{did} (OPEN): Complete signal loss and zero current flow (J = 0.0 A·m⁻², G=0.0), causing floating logic input and total circuit inoperability.")
                elif "MOUSEBITE" in cname:
                    parts.append(f"Defect #{did} (MOUSEBITE): Localized current density crowds to {j_str}, creating severe Joule heating hotspots and thermal fatigue vulnerability.")
                elif "SPUR" in cname:
                    parts.append(f"Defect #{did} (SPUR): Dielectric clearance reduction with {si} signal integrity risk, susceptible to capacitive crosstalk and dielectric breakdown.")
            
            consequence_str = " ".join(parts) if parts else "Minor localized impedance shifts within allowable tolerance."
            answer_text = (
                f"Potential Electrical Consequences (CEIA Proxies): {consequence_str} "
                "[Note: Values are counterfactual geometric proxies derived from optical layout; not physical bench measurements.]"
            )
            return {
                "query": query,
                "answer": answer_text,
                "source": "Grounded CEIA Electrical Proxy Matrix",
                "latency_seconds": round(time.time() - start_time, 3),
                "engine": "Deterministic Grounded Rule",
            }

        # Open-ended questions -> ExecuTorch Llama generation
        if use_llama:
            prompt = build_engineer_qa_prompt(query, self.report, self.intelligence)
            try:
                gen_res = self.engine.generate(
                    prompt=prompt,
                    max_new_tokens=max_new_tokens,
                    temperature=0.2,
                    top_p=0.9,
                )
                raw_ans = gen_res.get("text", "").strip()
                # Clean up any residual prompt tokens or fences
                if "<|eot_id|>" in raw_ans:
                    raw_ans = raw_ans.split("<|eot_id|>")[0].strip()
                return {
                    "query": query,
                    "answer": raw_ans,
                    "source": "ExecuTorch Llama 3.2 1B Grounded Reasoning",
                    "latency_seconds": gen_res.get("latency_seconds", 0.0),
                    "tokens_per_second": gen_res.get("tokens_per_second", 0.0),
                    "engine": "ExecuTorch Llama-3.2-1B-Instruct",
                }
            except Exception as e:
                logger.error(f"Llama QA generation error: {e}")

        # Fallback general answer
        return {
            "query": query,
            "answer": (
                f"Analysis for Board '{self.report.get('metadata', {}).get('board_id')}': "
                f"Status: {self.report.get('board_summary', {}).get('overall_disposition')}. "
                f"The board has {len(self.report.get('defects', []))} detected defects. "
                "Consult the Engineering Intelligence Dashboard for full CERI and CEIA proxy details."
            ),
            "source": "Fallback QA Handler",
            "latency_seconds": round(time.time() - start_time, 3),
            "engine": "deterministic_fallback",
        }


def run_interactive_qa_session(report_path: Optional[str] = None):
    """Runs interactive terminal Q&A session with the engineer."""
    from llama_advisory.engineering_intelligence import EngineeringIntelligenceEngine

    rep = load_unified_report_from_file_or_detections(report_path)
    engine = EngineeringIntelligenceEngine()
    intel = engine.analyze_board(rep, use_llama=False)  # instant initialization for QA

    qa = EngineerQAInterface(rep, intel, engine.engine)
    qa.initialize()

    board_id = rep.get("metadata", {}).get("board_id")
    disposition = rep.get("board_summary", {}).get("overall_disposition")

    print("\n" + "=" * 74)
    print("  🔬 RGPIS-HDE CONTEXTUAL PCB ENGINEER Q&A INTERFACE")
    print("  Powered by Meta Llama 3.2 on PyTorch ExecuTorch (XNNPACK CPU)")
    print("=" * 74)
    print(f"  Active Board  : {board_id}")
    print(f"  Disposition   : {disposition}")
    print(f"  Total Defects : {len(rep.get('defects', []))}")
    print("  IPC Standard  : IPC-A-600 / IPC-6012 Class 2/3")
    print("─" * 74)
    print("  Sample Questions:")
    print("  1. Why was this PCB rejected?")
    print("  2. Which defect is the most critical?")
    print("  3. What corrective action is recommended for defect #2?")
    print("  4. What are the potential consequences of the detected short?")
    print("  5. Summarize the board inspection.")
    print("  Type 'exit' or 'quit' to end the session.")
    print("─" * 74 + "\n")

    while True:
        try:
            query = input("Engineer Q: ").strip()
            if not query:
                continue
            if query.lower() in ("exit", "quit", "q"):
                print("Ending Engineer Q&A session. Goodbye.")
                break

            res = qa.answer_query(query, use_llama=True)
            print("\n" + "─" * 74)
            print(f"Intelligence Answer:\n{res['answer']}")
            print(f"\n[Engine: {res['engine']} | Latency: {res['latency_seconds']}s]")
            print("─" * 74 + "\n")

        except (KeyboardInterrupt, EOFError):
            print("\nSession terminated.")
            break


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RGPIS-HDE Engineer Q&A Interface")
    parser.add_argument("--query", type=str, default=None, help="Direct question to answer")
    parser.add_argument("--file", type=str, default=None, help="Path to unified_report.json or detections.json")
    args = parser.parse_args()

    if args.query:
        rep = load_unified_report_from_file_or_detections(args.file)
        qa = EngineerQAInterface(rep)
        ans = qa.answer_query(args.query, use_llama=True)
        print("\nQ:", args.query)
        print("A:", ans["answer"])
        print(f"(Engine: {ans['engine']}, Latency: {ans['latency_seconds']}s)")
    else:
        run_interactive_qa_session(args.file)
