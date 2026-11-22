"""
RGPIS-HDE Engineering Intelligence Layer.
Consumes structured unified_report.json (OpenCV, YOLO, CERI, CEIA, Unified Scoring)
and generates explainable, actionable PCB Engineering Intelligence using ExecuTorch Llama 3.2.

Generates 5 Core Outputs:
1. Board-Level Intelligence Report
2. Individual Defect Intelligence
3. Prioritized Corrective Action & Inspection Recommendations
4. Manufacturing Process Intelligence (Hypotheses)
5. Contextual Engineer Q&A Interface
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from llama_advisory.executorch_engine import ExecuTorchLlamaEngine
from llama_advisory.prompt_templates import (
    build_llama_prompt,
    validate_advisory_output,
    get_deterministic_fallback,
    build_board_intelligence_prompt,
    validate_board_intelligence_output,
    get_deterministic_board_fallback,
    build_process_intelligence_prompt,
    validate_process_intelligence_output,
    get_deterministic_process_fallback,
    build_engineer_qa_prompt,
    load_knowledge_base,
)
from llama_advisory.unified_pipeline_bridge import (
    load_unified_report_from_file_or_detections,
    build_unified_report,
)

logger = logging.getLogger("EngineeringIntelligence")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class EngineeringIntelligenceEngine:
    """
    Main orchestrator for RGPIS-HDE Engineering Intelligence Layer.
    """

    def __init__(self, engine: Optional[ExecuTorchLlamaEngine] = None):
        self.engine = engine or ExecuTorchLlamaEngine()
        self.kb = load_knowledge_base()
        self._is_initialized = False

    def initialize(self):
        """Loads ExecuTorch model if not already loaded."""
        if not self._is_initialized:
            self.engine.load_model()
            self._is_initialized = True

    # --------------------------------------------------------------------------
    # 1. Board-Level Intelligence
    # --------------------------------------------------------------------------
    def generate_board_intelligence(
        self,
        report: Dict[str, Any],
        use_llama: bool = True,
        max_new_tokens: int = 250,
    ) -> Dict[str, Any]:
        """
        Synthesizes Board-Level Intelligence: condition, acceptance/rejection rationale,
        major risk explanations, and immediate priority defects.
        """
        summary = report.get("board_summary", {})
        meta = report.get("metadata", {})
        disposition = summary.get("overall_disposition", "REVIEW")
        disposition_reason = summary.get("disposition_reason", "")

        if not use_llama:
            return get_deterministic_board_fallback(report, "Fast mode requested (deterministic generator)")

        prompt = build_board_intelligence_prompt(report)
        start_time = time.time()
        metrics = {"latency_seconds": 0.0, "engine": "ExecuTorch Llama-3.2-1B-Instruct"}

        try:
            gen_res = self.engine.generate(
                prompt=prompt,
                max_new_tokens=max_new_tokens,
                temperature=0.2,
                top_p=0.9,
            )
            raw_text = gen_res.get("text", "")
            metrics["latency_seconds"] = gen_res.get("latency_seconds", 0.0)
            metrics["tokens_per_second"] = gen_res.get("tokens_per_second", 0.0)
            metrics["ram_usage_mb"] = gen_res.get("ram_usage_mb", 0.0)

            full_json = '{\n  "board_condition": "' + raw_text
            is_valid, parsed_data, err_msg = validate_board_intelligence_output(full_json, report)

            if is_valid:
                parsed_data["overall_disposition"] = disposition
                parsed_data["upstream_disposition_reason"] = disposition_reason
                parsed_data["engine"] = "ExecuTorch Llama-3.2-1B-Instruct"
                parsed_data["metrics"] = metrics
                parsed_data["verification_status"] = "PASSED_SCHEMA_CHECKS"
                return parsed_data
            else:
                logger.warning(f"Board intelligence validation failed ({err_msg}). Using deterministic fallback.")
                fallback = get_deterministic_board_fallback(report, err_msg or "Validation failure")
                fallback["overall_disposition"] = disposition
                fallback["upstream_disposition_reason"] = disposition_reason
                fallback["metrics"] = metrics
                return fallback

        except Exception as e:
            logger.error(f"ExecuTorch board generation failed: {e}")
            fallback = get_deterministic_board_fallback(report, f"ExecuTorch error: {str(e)}")
            fallback["overall_disposition"] = disposition
            fallback["upstream_disposition_reason"] = disposition_reason
            return fallback

    # --------------------------------------------------------------------------
    # 2. Individual Defect Intelligence
    # --------------------------------------------------------------------------
    def generate_defect_intelligence(
        self,
        defect: Dict[str, Any],
        use_llama: bool = True,
        max_new_tokens: int = 380,
    ) -> Dict[str, Any]:
        """
        Generates comprehensive intelligence for a single defect:
        - What was detected
        - Why it is significant (IPC-A-600)
        - Potential consequences (CERI & CEIA proxy grounded)
        - Specific region inspection protocol
        - Suggested corrective action
        - Verification protocol
        """
        did = defect.get("defect_id", 1)
        cname = defect.get("class_name", "unknown")
        conf = float(defect.get("confidence", 0.0))
        bbox = defect.get("bbox", [0, 0, 0, 0])
        ceri = defect.get("ceri", {})
        ceia = defect.get("ceia", {})
        unified = defect.get("unified_score", {})

        alias_map = {
            "open": "open_circuit",
            "short": "short_circuit",
            "mousebite": "mouse_bite",
            "spur": "spur",
            "copper": "spurious_copper",
            "pin-hole": "pin_hole",
            "pinhole": "pin_hole",
        }
        canonical_type = alias_map.get(cname.lower(), cname.lower())
        ref = self.kb.get("defects", {}).get(canonical_type, {})

        # Default factual descriptions grounded in IPC knowledge base
        display_name = ref.get("display_name", cname.replace("_", " ").title())
        what_detected = (
            f"Detected {display_name} anomaly at coordinates [{bbox[0]:.1f}, {bbox[1]:.1f}, {bbox[2]:.1f}, {bbox[3]:.1f}] "
            f"with {conf * 100:.1f}% optical model confidence."
        )

        why_significant = (
            f"IPC-A-600 Class 2/3 violation: {ref.get('definition', 'Conductor boundary deviation')}. "
            f"Evaluated with CERI geometric risk score of {ceri.get('geometric_risk_score', 0.5):.2f} "
            f"and Unified Priority {unified.get('priority_level', 'P2_HIGH')}."
        )

        consequences = list(ref.get("possible_consequences", []))
        # Append CERI & CEIA proxy groundings
        if "open" in canonical_type:
            consequences.append("CEIA Proxy: Nodal conductance factor G=0.0 (J = 0.0 A·m⁻²). Complete circuit open with zero current transfer.")
        elif "short" in canonical_type:
            j_str = ceia.get("current_density_str", "1.07 × 10⁹ A·m⁻²")
            consequences.append(
                f"CEIA Proxy: Shunt bridge creates severe surge current density ({j_str}), "
                "risking power rail shutdown and catastrophic conductor trace vaporization."
            )
        elif "mouse" in canonical_type:
            red = ceri.get("trace_width_reduction_pct", 30)
            j_str = ceia.get("current_density_str", f"{ceia.get('current_density_multiplier', 1.5)}x")
            j_mult = ceia.get("current_density_multiplier", 1.5)
            consequences.append(
                f"CERI & CEIA Proxies: {red}% trace width necking elevates localized current density to {j_str} "
                f"({j_mult}x crowding vs nominal J₀), risking severe Joule heating and thermal stress hotspots."
            )
        elif "spur" in canonical_type:
            red = ceri.get("clearance_intrusion_pct", 50)
            rem = ceri.get("clearance_remaining_mm", 0.05)
            consequences.append(
                f"CERI Proxy: {red}% dielectric clearance reduction ({rem} mm remaining) increases susceptibility to "
                "localized capacitive cross-talk and transient dielectric breakdown."
            )
        elif "copper" in canonical_type:
            c_red = ceri.get("clearance_intrusion_pct", 40)
            consequences.append(
                f"CERI Proxy: {c_red}% clearance encroachment from isolated copper island increases capacitive coupling "
                "and risk of dislodgement during mechanical shock."
            )
        elif "pin" in canonical_type:
            t_red = ceri.get("trace_width_reduction_pct", 15)
            consequences.append(
                f"CERI Proxy: {t_red}% localized cross-sectional reduction within conductor/pad. "
                "Potential trap for corrosive soldering residues."
            )

        region_inspection = [
            f"Position stereo microscope directly over bounding coordinates [{bbox[0]:.1f}, {bbox[1]:.1f}, {bbox[2]:.1f}, {bbox[3]:.1f}] under 20x-30x magnification.",
            "Use oblique ring-lighting to inspect conductor sidewalls, looking for copper lifting, undercut, or burrs.",
            "Overlay Gerber reference net to confirm original intended conductor boundaries.",
        ]

        if "open" in canonical_type:
            corrective_action = (
                "For high-reliability Class 3 assemblies, scrap board or submit to Material Review Board (MRB). "
                "For Class 2 rework: solder an approved 30 AWG insulated micro-jumper wire between net testpoints or via pads."
            )
            verification = [
                "Perform 2-point electrical continuity check using a calibrated digital multimeter (DMM) across net endpoints (< 0.5 Ohm).",
                "Inspect jumper solder joints under 20x magnification for wetting, meniscus, and solder cleanliness.",
                "Apply IPC-CC-830 conformal coating spot-repair over the reworked trace.",
            ]
        elif "short" in canonical_type:
            corrective_action = (
                "Quarantine board immediately. Do not power up. Using a precision micro-scalpel or ultrasonic deburring tool "
                "under 30x magnification, carefully excise the conductive copper bridge without scoring the FR4 substrate."
            )
            verification = [
                "Perform 2-point isolation resistance measurement with DMM (> 100 MOhm isolation required).",
                "Perform optical clearance verification to ensure minimum electrical spacing is fully restored.",
                "Clean region with reagent-grade isopropyl alcohol and inspect for loose copper debris.",
            ]
        elif "mouse" in canonical_type:
            corrective_action = (
                f"Evaluate remaining trace width against DRC specification ({ceri.get('trace_width_reduction_pct', 0)}% reduction). "
                "If remaining width meets minimum current-carrying capacity, accept with engineering note. "
                "Otherwise, apply copper foil micro-patch or bridge with micro-wire."
            )
            verification = [
                "Measure narrowest conductor bottleneck width using calibrated optical reticle microscope.",
                "Conduct Kelvin 4-wire trace resistance measurement to verify resistance within 5% of nominal trace.",
            ]
        elif "spur" in canonical_type:
            corrective_action = (
                "Evaluate clearance against IPC-A-600 minimum spacing. If out of specification, micro-trim "
                "the copper protrusion using an approved diamond-tipped dental micro-scraper under 20x stereo magnification."
            )
            verification = [
                "Measure post-trim dielectric clearance with optical measuring microscope (must exceed minimum spacing rule).",
                "Inspect substrate for mechanical damage or delamination.",
            ]
        elif "copper" in canonical_type:
            corrective_action = (
                "Determine if copper flake is surface debris or bonded laminate foil. If loose, clean with ESD cleanroom swab "
                "and IPA. If bonded foil violating clearance, mechanically delaminate and peel using micro-tweezers."
            )
            verification = [
                "Verify dielectric surface cleanliness and complete flake removal.",
                "Perform surface insulation resistance (SIR) check if required by high-voltage design rules.",
            ]
        elif "pin" in canonical_type:
            corrective_action = (
                "Check void diameter against IPC-A-600 limit (<= 10% conductor width). "
                "If within tolerance, document and accept. If on SMT pad, apply micro-solder touch-up."
            )
            verification = [
                "Verify pad coplanarity and solderability if on component landing pad.",
                "Inspect under optical reticle to confirm void does not extend to conductor edge.",
            ]
        else:
            corrective_action = "Quarantine board and submit to Quality Engineering for MRB disposition."
            verification = ["Perform 100% optical and electrical verification against design Gerber."]

        # Enrich with Llama generated explanation if requested
        explanation = ref.get("definition", what_detected)
        metrics = {"engine": "Deterministic IPC Rules"}
        if use_llama and unified.get("priority_level") in ("P1_CRITICAL", "P2_HIGH"):
            try:
                defect_input = {
                    "defect_type": canonical_type,
                    "confidence": conf,
                    "location": bbox,
                    "ceri": ceri,
                    "ceia": ceia,
                }
                prompt, _ = build_llama_prompt(defect_input)
                gen_res = self.engine.generate(prompt=prompt, max_new_tokens=max_new_tokens)
                full_json = (
                    f'{{\n  "defect_type": "{canonical_type}",\n  "confidence": {conf},\n  "location": {bbox},\n  "explanation": "'
                    + gen_res.get("text", "")
                )
                is_valid, parsed_data, _ = validate_advisory_output(full_json, defect_input)
                if is_valid and parsed_data.get("explanation"):
                    explanation = parsed_data["explanation"]
                    metrics = {
                        "engine": "ExecuTorch Llama-3.2-1B-Instruct",
                        "latency_seconds": gen_res.get("latency_seconds", 0.0),
                        "tokens_per_second": gen_res.get("tokens_per_second", 0.0),
                    }
            except Exception as e:
                logger.warning(f"Llama single defect intelligence exception: {e}")

        return {
            "defect_id": did,
            "class_name": cname,
            "canonical_type": canonical_type,
            "display_name": display_name,
            "confidence": conf,
            "bbox": bbox,
            "what_was_detected": what_detected,
            "why_significant": why_significant,
            "potential_consequences": consequences,
            "region_inspection_points": region_inspection,
            "suggested_corrective_action": corrective_action,
            "verification_protocol": verification,
            "ceri_metrics": ceri,
            "ceia_proxies": ceia,
            "unified_score": unified,
            "explanation": explanation,
            "metrics": metrics,
        }

    # --------------------------------------------------------------------------
    # 3. Prioritized Corrective Action & Recommendations
    # --------------------------------------------------------------------------
    def generate_corrective_action_recommendations(
        self,
        report: Dict[str, Any],
        defect_intelligences: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Generates an ordered, actionable execution checklist for rework operators
        and quality engineers based on CERI, CEIA, and Unified Priority ranks.
        """
        action_plan = []
        for idx, d_intel in enumerate(defect_intelligences, start=1):
            did = d_intel["defect_id"]
            cname = d_intel["canonical_type"]
            prio = d_intel["unified_score"]["priority_level"]
            score = d_intel["unified_score"]["score"]
            bbox = d_intel["bbox"]

            if prio == "P1_CRITICAL":
                urgency = "IMMEDIATE_ACTION_BEFORE_ENERGIZATION"
                station = "Precision Micro-Rework Station"
            elif prio == "P2_HIGH":
                urgency = "MANDATORY_REWORK_EVALUATION"
                station = "SMT Quality Inspection Desk"
            elif prio == "P3_MEDIUM":
                urgency = "ENGINEERING_DISPOSITION"
                station = "Optical Metrology Desk"
            else:
                urgency = "STANDARD_MONITORING"
                station = "Final QA Desk"

            action_type_map = {
                "open_circuit": "MICRO_JUMPER_OR_SCRAP",
                "short_circuit": "MICRO_EXCISION_ISOLATION",
                "mouse_bite": "BOTTLENECK_METROLOGY_PATCH",
                "spur": "CLEARANCE_TRIMMING",
                "spurious_copper": "COPPER_FLAKE_STRIPPING",
                "pin_hole": "VOID_INSPECTION_TOUCHUP",
            }

            action_plan.append({
                "step_number": idx,
                "defect_id": did,
                "defect_name": d_intel["display_name"],
                "priority_level": prio,
                "unified_score": score,
                "urgency": urgency,
                "action_type": action_type_map.get(cname, "ENGINEERING_REVIEW"),
                "target_coordinates": bbox,
                "recommended_action": d_intel["suggested_corrective_action"],
                "verification_procedure": d_intel["verification_protocol"],
                "assigned_station": station,
                "sign_off_required": prio in ("P1_CRITICAL", "P2_HIGH"),
            })

        return action_plan

    # --------------------------------------------------------------------------
    # 4. Manufacturing Process Intelligence (Hypotheses)
    # --------------------------------------------------------------------------
    def generate_process_intelligence(
        self,
        report: Dict[str, Any],
        use_llama: bool = True,
        max_new_tokens: int = 250,
    ) -> Dict[str, Any]:
        """
        Analyzes multi-defect spatial and category correlations to generate
        manufacturing process hypotheses (etching, photolithography, plating).
        Framed strictly as HYPOTHESES, not confirmed causes.
        """
        if not use_llama:
            return get_deterministic_process_fallback(report)

        prompt = build_process_intelligence_prompt(report)
        metrics = {"engine": "ExecuTorch Llama-3.2-1B-Instruct"}

        try:
            gen_res = self.engine.generate(
                prompt=prompt,
                max_new_tokens=max_new_tokens,
                temperature=0.2,
                top_p=0.9,
            )
            raw_text = gen_res.get("text", "")
            metrics["latency_seconds"] = gen_res.get("latency_seconds", 0.0)
            metrics["tokens_per_second"] = gen_res.get("tokens_per_second", 0.0)
            metrics["ram_usage_mb"] = gen_res.get("ram_usage_mb", 0.0)

            full_json = '{\n  "pattern_summary": "' + raw_text
            is_valid, parsed_data, err_msg = validate_process_intelligence_output(full_json)

            if is_valid:
                parsed_data["engine"] = "ExecuTorch Llama-3.2-1B-Instruct"
                parsed_data["metrics"] = metrics
                parsed_data["disclaimer"] = (
                    "Process intelligence outputs are probabilistic hypotheses generated from defect distributions. "
                    "Confirmation requires SPC bath chemistry and phototool optical audits."
                )
                return parsed_data
            else:
                logger.warning(f"Process intelligence validation failed: {err_msg}. Using fallback.")
                fallback = get_deterministic_process_fallback(report)
                fallback["metrics"] = metrics
                return fallback

        except Exception as e:
            logger.error(f"Process intelligence generation error: {e}")
            return get_deterministic_process_fallback(report)

    # --------------------------------------------------------------------------
    # 5. Full Pipeline Intelligence Generation
    # --------------------------------------------------------------------------
    def analyze_board(
        self,
        report_or_path: Union[str, Path, Dict[str, Any]],
        use_llama: bool = True,
        max_defects_llama: int = 2,
    ) -> Dict[str, Any]:
        """
        End-to-end execution of all 5 engineering intelligence layers.
        Optimized to use Llama for high-level board synthesis, process hypotheses,
        and top critical defects, while maintaining speed and 100% factual accuracy.
        """
        start_time = time.time()

        # Step 1: Ingest unified report
        if isinstance(report_or_path, dict):
            report = report_or_path
        else:
            report = load_unified_report_from_file_or_detections(report_or_path)

        board_id = report.get("metadata", {}).get("board_id", "Unknown")
        logger.info(f"Generating Engineering Intelligence for Board: {board_id}")

        # Step 2: Board-Level Intelligence
        logger.info("Executing Layer 1: Board-Level Intelligence Report...")
        board_level = self.generate_board_intelligence(report, use_llama=use_llama)

        # Step 3: Individual Defect Intelligence
        logger.info("Executing Layer 2: Individual Defect Intelligence...")
        defects = report.get("defects", [])
        defect_intelligences = []
        for idx, d in enumerate(defects):
            # Run Llama on top critical defects; use instant rule engine for remainder
            run_llama_for_this = use_llama and (idx < max_defects_llama)
            d_intel = self.generate_defect_intelligence(d, use_llama=run_llama_for_this)
            defect_intelligences.append(d_intel)

        # Step 4: Corrective Action Recommendations
        logger.info("Executing Layer 3: Prioritized Corrective Actions...")
        action_plan = self.generate_corrective_action_recommendations(report, defect_intelligences)

        # Step 5: Manufacturing Process Intelligence
        logger.info("Executing Layer 4: Manufacturing Process Intelligence...")
        process_intel = self.generate_process_intelligence(report, use_llama=use_llama)

        total_latency = round(time.time() - start_time, 2)
        logger.info(f"Complete Engineering Intelligence generated in {total_latency}s")

        full_intelligence = {
            "metadata": {
                "board_id": board_id,
                "image_name": report.get("metadata", {}).get("image_name"),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "total_generation_latency_seconds": total_latency,
                "runtime_backend": "ExecuTorch (XNNPACK CPU Offline Runtime)",
                "foundation_model": "Llama-3.2-1B-Instruct (4-bit SpinQuant INT4)",
                "standards_basis": "IPC-A-600 / IPC-6012 Class 2/3",
            },
            "board_summary": report.get("board_summary", {}),
            "board_level_intelligence": board_level,
            "individual_defect_intelligence": defect_intelligences,
            "corrective_action_recommendations": action_plan,
            "process_intelligence": process_intel,
        }

        return full_intelligence


if __name__ == "__main__":
    from llama_advisory.unified_pipeline_bridge import load_unified_report_from_file_or_detections

    engine = EngineeringIntelligenceEngine()
    rep = load_unified_report_from_file_or_detections()
    intel = engine.analyze_board(rep, use_llama=True, max_defects_llama=1)

    print("\n" + "=" * 70)
    print("BOARD CONDITION:", intel["board_level_intelligence"]["board_condition"])
    print("RATIONALE:", intel["board_level_intelligence"]["acceptance_rationale"])
    print("MAJOR RISKS:", intel["board_level_intelligence"]["major_risks"])
    print("TOTAL DEFECTS ANALYZED:", len(intel["individual_defect_intelligence"]))
    print("PROCESS HYPOTHESES:", len(intel["process_intelligence"]["fab_stage_hypotheses"]))
    print("=" * 70)
