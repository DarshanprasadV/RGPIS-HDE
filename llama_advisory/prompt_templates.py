"""
Industrial prompt builder and output validator for RGPIS-HDE PCB Defect Advisory.
Uses official Llama 3.2 Chat Template and IPC-A-600 grounded knowledge base.
Provides prompt templates and validators for:
1. Individual Defect Advisory
2. Board-Level Intelligence
3. Process Intelligence
4. Engineer Q&A
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

RULES_PATH = Path(__file__).parent / "knowledge_base" / "deeppcb_rules.json"


def load_knowledge_base() -> Dict[str, Any]:
    with open(RULES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ==============================================================================
# 1. Individual Defect Prompt & Validator
# ==============================================================================

def build_llama_prompt(defect_input: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """
    Constructs an evidence-grounded prompt using Llama 3.2 Instruct chat template.
    Returns (formatted_prompt_string, reference_context).
    """
    kb = load_knowledge_base()
    defect_type = str(defect_input.get("defect_type", defect_input.get("class_name", "unknown"))).lower().strip()
    
    # Map common aliases
    alias_map = {
        "open": "open_circuit",
        "short": "short_circuit",
        "mousebite": "mouse_bite",
        "spur": "spur",
        "copper": "spurious_copper",
        "pin-hole": "pin_hole",
        "pinhole": "pin_hole",
    }
    canonical_type = alias_map.get(defect_type, defect_type)

    confidence = float(defect_input.get("confidence", 0.0))
    location = defect_input.get("location", defect_input.get("bbox", [0, 0, 0, 0]))
    ceri = defect_input.get("ceri", {})
    ceia = defect_input.get("ceia", {})
    
    reference = kb.get("defects", {}).get(canonical_type)
    
    is_low_confidence = confidence < kb.get("confidence_threshold", 0.50)
    is_unknown = reference is None

    system_instruction = (
        "You are an Industrial PCB Defect Advisor for RGPIS-HDE.\n"
        "Generate a complete JSON advisory report based strictly on the provided IPC reference and CERI/CEIA metrics.\n"
        "CEIA electrical metrics are geometric proxies, not bench measurements. Never approve or reject PCBs. Output ONLY valid JSON."
    )

    if is_unknown or is_low_confidence:
        ref_text = (
            f"Defect '{defect_type}' is unverified or confidence ({confidence:.2f}) is below 0.50. "
            "Manual visual and physical inspection under optical microscope is mandatory before any action."
        )
        explanation_default = f"Detection of {defect_type} requires manual verification due to low confidence or uncatalogued defect category."
        consequence_default = ["Unverified anomaly may compromise board electrical operation."]
        verify_default = ["Perform 100% manual optical inspection under stereomicroscope against Gerber reference."]
        guidance_default = "Quarantine PCB. Flag for manual QA inspection. Do not route to functional testing."
        warning_str = f"Low detection confidence ({confidence:.2f}). Manual inspection required."
    else:
        ref_text = (
            f"Type: {reference['display_name']}\n"
            f"Definition: {reference['definition']}\n"
            f"Consequences: {'; '.join(reference['possible_consequences'])}\n"
            f"Verification: {'; '.join(reference['recommended_verification_procedure'])}\n"
            f"Guidance: {reference['operator_guidance']}"
        )
        explanation_default = reference["definition"]
        consequence_default = reference["possible_consequences"]
        verify_default = reference["recommended_verification_procedure"]
        guidance_default = reference["operator_guidance"]
        warning_str = "null" if confidence >= 0.80 else f"Moderate confidence ({confidence:.2f}). Verify visually."

    # Incorporate CERI & CEIA proxy info if available
    ceri_ceia_str = ""
    if ceri or ceia:
        ceri_ceia_str = (
            f"\nCERI Geometric Risk: trace width reduction = {ceri.get('trace_width_reduction_pct', 'N/A')}%, "
            f"clearance intrusion = {ceri.get('clearance_intrusion_pct', 'N/A')}%\n"
            f"CEIA Electrical Proxy: current density J = {ceia.get('current_density_str', str(ceia.get('current_density_multiplier', 'N/A')) + 'x')}, "
            f"signal integrity risk = {ceia.get('signal_integrity_risk', 'N/A')}"
        )

    user_content = (
        f"Defect Detection Data:\n"
        f"- Defect: {canonical_type}\n"
        f"- Confidence: {confidence}\n"
        f"- Location: {location}"
        f"{ceri_ceia_str}\n\n"
        f"IPC Reference Information:\n"
        f"{ref_text}\n\n"
        "Generate the advisory JSON with keys: defect_type, confidence, location, explanation, possible_consequences, recommended_verification_procedure, operator_guidance, uncertainty_warning, disclaimer."
    )

    formatted_prompt = (
        "<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n"
        f"{system_instruction}<|eot_id|>"
        "<|start_header_id|>user<|end_header_id|>\n\n"
        f"{user_content}<|eot_id|>"
        "<|start_header_id|>assistant<|end_header_id|>\n\n"
        f'{{\n  "defect_type": "{canonical_type}",\n  "confidence": {confidence},\n  "location": {location},\n  "explanation": "'
    )

    return formatted_prompt, {
        "defect_type": canonical_type,
        "is_low_confidence": is_low_confidence,
        "is_unknown": is_unknown,
        "default_explanation": explanation_default,
        "default_consequences": consequence_default,
        "default_verify": verify_default,
        "default_guidance": guidance_default,
        "default_warning": warning_str
    }


def validate_advisory_output(raw_output: str, original_input: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], Optional[str]]:
    """
    Validates model generation against required schema and hallucination checks.
    Returns (is_valid, parsed_dict_or_fallback, error_message).
    """
    try:
        clean_text = raw_output.strip()
        if "```json" in clean_text:
            clean_text = clean_text.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_text:
            clean_text = clean_text.split("```")[1].split("```")[0].strip()
        
        first_brace = clean_text.find("{")
        last_brace = clean_text.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            clean_text = clean_text[first_brace:last_brace + 1]
        elif first_brace != -1:
            clean_text = clean_text[first_brace:]

        if clean_text.count('"') % 2 != 0:
            clean_text += '"'
        if not clean_text.endswith("}"):
            clean_text += "\n}"

        data = json.loads(clean_text)

        required_keys = [
            "defect_type",
            "explanation",
            "possible_consequences",
            "recommended_verification_procedure",
            "operator_guidance",
            "disclaimer"
        ]

        for k in required_keys:
            if k not in data or data[k] is None or data[k] == "":
                return False, {}, f"Missing or empty required field: {k}"

        if isinstance(data.get("possible_consequences"), str):
            parts = [c.strip() for c in data["possible_consequences"].split(";") if c.strip()]
            data["possible_consequences"] = parts if parts else [data["possible_consequences"]]
        if isinstance(data.get("recommended_verification_procedure"), str):
            parts = [c.strip() for c in data["recommended_verification_procedure"].split(";") if c.strip()]
            data["recommended_verification_procedure"] = parts if parts else [data["recommended_verification_procedure"]]

        # Hallucination check 1: Disallow independent pass/reject decision
        forbidden_approval_terms = [
            "pcb approved",
            "pcb rejected",
            "board approved",
            "board rejected",
            "final disposition: pass",
            "final disposition: fail",
            "disposition: approved"
        ]
        text_lower = clean_text.lower()
        for term in forbidden_approval_terms:
            if term in text_lower:
                return False, {}, f"Safety violation: Model attempted independent board disposition ('{term}')"

        if "does not independently approve or reject" not in text_lower and "operator verification" not in text_lower:
            data["disclaimer"] = "AI advisory guidance only. Operator verification required. System does not independently approve or reject PCBs."

        conf = float(original_input.get("confidence", 0.0))
        if conf < 0.80 and not data.get("uncertainty_warning"):
            data["uncertainty_warning"] = (
                f"Low detection confidence ({conf:.2f}). Manual optical and physical verification is mandatory."
            )

        return True, data, None

    except Exception as e:
        return False, {}, f"JSON Parsing or Schema Error: {str(e)}"


def get_deterministic_fallback(defect_input: Dict[str, Any], failure_reason: str) -> Dict[str, Any]:
    """
    Deterministic safety fallback if Llama fails or produces invalid output.
    Zero-hallucination guaranteed.
    """
    kb = load_knowledge_base()
    defect_type = str(defect_input.get("defect_type", defect_input.get("class_name", "unknown"))).lower().strip()
    alias_map = {
        "open": "open_circuit",
        "short": "short_circuit",
        "mousebite": "mouse_bite",
        "spur": "spur",
        "copper": "spurious_copper",
        "pin-hole": "pin_hole",
        "pinhole": "pin_hole",
    }
    canonical_type = alias_map.get(defect_type, defect_type)

    confidence = float(defect_input.get("confidence", 0.0))
    location = defect_input.get("location", defect_input.get("bbox", [0, 0, 0, 0]))
    reference = kb.get("defects", {}).get(canonical_type)

    if reference:
        return {
            "defect_type": canonical_type,
            "confidence": confidence,
            "location": location,
            "explanation": f"Fallback Advisory: {reference['definition']}",
            "possible_consequences": reference["possible_consequences"],
            "recommended_verification_procedure": reference["recommended_verification_procedure"],
            "operator_guidance": f"AUTOMATED ADVISORY FALLBACK ACTIVATED ({failure_reason}). " + reference["operator_guidance"],
            "uncertainty_warning": f"Advisory generated via deterministic fallback engine due to: {failure_reason}",
            "disclaimer": kb["disclaimer"],
            "engine": "deterministic_fallback"
        }
    else:
        return {
            "defect_type": canonical_type,
            "confidence": confidence,
            "location": location,
            "explanation": f"Uncatalogued defect type '{canonical_type}' detected at coordinates {location}.",
            "possible_consequences": [
                "Unspecified anomaly may compromise signal integrity, power distribution, or manufacturing yield."
            ],
            "recommended_verification_procedure": [
                "Position the PCB under a high-resolution stereomicroscope at the indicated coordinates.",
                "Compare the region directly with Gerber layer artwork and reference golden board.",
                "Consult the quality engineering manager for defect classification."
            ],
            "operator_guidance": "Quarantine the PCB unit and flag for senior QA inspector review. Do not process further.",
            "uncertainty_warning": f"High uncertainty: Defect class '{canonical_type}' is unrecognized. Confidence: {confidence:.2f}.",
            "disclaimer": kb["disclaimer"],
            "engine": "deterministic_fallback"
        }


# ==============================================================================
# 2. Board-Level Intelligence Prompt & Validator
# ==============================================================================

def build_board_intelligence_prompt(report: Dict[str, Any]) -> str:
    """
    Constructs prompt for Board-Level Engineering Intelligence Report.
    """
    meta = report.get("metadata", {})
    summary = report.get("board_summary", {})
    defects = report.get("defects", [])

    board_id = meta.get("board_id", "Unknown-Board")
    disposition = summary.get("overall_disposition", "REVIEW")
    total_defects = summary.get("total_defects", len(defects))
    critical_count = summary.get("critical_defects_count", 0)
    high_count = summary.get("high_risk_count", 0)

    # Defect summary line
    defect_counts = {}
    for d in defects:
        c = d.get("class_name", "unknown")
        defect_counts[c] = defect_counts.get(c, 0) + 1
    defects_str = ", ".join(f"{cnt} {cls}" for cls, cnt in defect_counts.items())

    # Top defects info
    top_defects = defects[:3]
    top_defects_details = []
    for d in top_defects:
        did = d.get("defect_id")
        cname = d.get("class_name")
        prio = d.get("unified_score", {}).get("priority_level", "P2_HIGH")
        ceri_w = d.get("ceri", {}).get("trace_width_reduction_pct", 0)
        ceri_c = d.get("ceri", {}).get("clearance_intrusion_pct", 0)
        top_defects_details.append(
            f"Defect #{did} ({cname}, {prio}): width_reduction={ceri_w}%, clearance_intrusion={ceri_c}%"
        )
    top_str = "\n".join(top_defects_details)

    system_instruction = (
        "You are an Industrial PCB Engineering Intelligence system for RGPIS-HDE.\n"
        "Consume the upstream analyzer results (YOLO, CERI geometric risk, CEIA electrical proxies) "
        "and produce a concise Board-Level Intelligence explanation.\n"
        "Ground your response strictly in the provided data. Do not fabricate measurements.\n"
        "Output ONLY valid JSON with keys: board_condition, acceptance_rationale, major_risks, immediate_priorities."
    )

    user_content = (
        f"Board Inspection Data:\n"
        f"- Board ID: {board_id}\n"
        f"- Overall Pipeline Disposition: {disposition}\n"
        f"- Total Defects: {total_defects} ({defects_str})\n"
        f"- Critical Defects: {critical_count} P1, {high_count} P2\n"
        f"- Defect Breakdown:\n{top_str}\n\n"
        "Explain the engineering consequences:\n"
        "1. board_condition: Assessment status (e.g. CRITICAL_NON_CONFORMING)\n"
        "2. acceptance_rationale: 2-3 sentences explaining why the board is rejected or accepted under IPC-A-600\n"
        "3. major_risks: List 2-3 specific physical/electrical failure risks (e.g. short circuit overcurrent, open trace discontinuity, thermal bottlenecking)\n"
        "4. immediate_priorities: List 2-3 specific defect IDs and actions (e.g. 'Defect #3 (short): excise bridge', 'Defect #4 (open): micro-jumper review')\n\n"
        'Output format:\n{\n  "board_condition": "...",\n  "acceptance_rationale": "...",\n  "major_risks": ["..."],\n  "immediate_priorities": ["..."]\n}'
    )

    formatted_prompt = (
        "<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n"
        f"{system_instruction}<|eot_id|>"
        "<|start_header_id|>user<|end_header_id|>\n\n"
        f"{user_content}<|eot_id|>"
        "<|start_header_id|>assistant<|end_header_id|>\n\n"
        '{\n  "board_condition": "'
    )

    return formatted_prompt


def validate_board_intelligence_output(raw_output: str, report: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], Optional[str]]:
    """Validates generated board-level intelligence JSON."""
    try:
        clean = raw_output.strip()
        if "```json" in clean:
            clean = clean.split("```json")[1].split("```")[0].strip()
        elif "```" in clean:
            clean = clean.split("```")[1].split("```")[0].strip()

        first_brace = clean.find("{")
        last_brace = clean.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            clean = clean[first_brace:last_brace + 1]
        elif first_brace != -1:
            clean = clean[first_brace:]

        if clean.count('"') % 2 != 0:
            clean += '"'
        if not clean.endswith("}"):
            clean += "\n}"

        data = json.loads(clean)
        required = ["board_condition", "acceptance_rationale", "major_risks", "immediate_priorities"]
        for k in required:
            if k not in data or not data[k]:
                return False, {}, f"Missing required board field: {k}"

        if isinstance(data["major_risks"], str):
            data["major_risks"] = [r.strip() for r in data["major_risks"].split(";") if r.strip()]
        elif isinstance(data["major_risks"], list):
            data["major_risks"] = [
                f"{r.get('risk', r.get('description', str(r)))}" if isinstance(r, dict) else str(r)
                for r in data["major_risks"]
            ]

        if isinstance(data["immediate_priorities"], str):
            data["immediate_priorities"] = [p.strip() for p in data["immediate_priorities"].split(";") if p.strip()]
        elif isinstance(data["immediate_priorities"], list):
            data["immediate_priorities"] = [
                f"{p.get('priority', p.get('action', str(p)))}" if isinstance(p, dict) else str(p)
                for p in data["immediate_priorities"]
            ]

        # Check for uninformative generic placeholders
        generic_terms = {"top priority defects", "critical defects", "defects", "none", "high priority"}
        clean_risks = [r for r in data["major_risks"] if r.lower().strip() not in generic_terms and len(r.strip()) > 8]
        if len(clean_risks) < 2:
            fallback_board = get_deterministic_board_fallback(report, "Enriching generic risks with grounded physical criteria")
            data["major_risks"] = fallback_board["major_risks"]
        else:
            data["major_risks"] = clean_risks

        clean_prio = [p for p in data["immediate_priorities"] if p.lower().strip() not in generic_terms and len(p.strip()) > 8]
        if len(clean_prio) < 2:
            fallback_board = get_deterministic_board_fallback(report, "Enriching generic priorities with grounded defect targets")
            data["immediate_priorities"] = fallback_board["immediate_priorities"]
        else:
            data["immediate_priorities"] = clean_prio

        return True, data, None
    except Exception as e:
        return False, {}, f"Board JSON parse error: {str(e)}"


def get_deterministic_board_fallback(report: Dict[str, Any], reason: str) -> Dict[str, Any]:
    """Deterministic board intelligence generator based strictly on IPC standards."""
    summary = report.get("board_summary", {})
    defects = report.get("defects", [])
    disposition = summary.get("overall_disposition", "REJECT")
    p1_count = summary.get("critical_defects_count", 0)
    p2_count = summary.get("high_risk_count", 0)

    classes = [d.get("class_name") for d in defects]
    has_short = any("short" in c for c in classes)
    has_open = any("open" in c for c in classes)
    has_mousebite = any("mousebite" in c for c in classes)
    has_spur = any("spur" in c for c in classes)

    risks = []
    if has_short:
        risks.append("Catastrophic short circuit creates direct low-resistance shunt path risking power rail shutdown or component burnout.")
    if has_open:
        risks.append("Complete trace discontinuity (open circuit) causing total signal loss or floating gate behavior.")
    if has_mousebite:
        risks.append("Trace bottlenecking from mousebites induces localized current crowding and thermal stress hotspots.")
    if has_spur:
        risks.append("Dielectric clearance erosion from copper spurs elevates risk of localized dielectric breakdown or solder bridging.")

    if not risks:
        risks.append("Minor cosmetic anomalies requiring standard optical quality review.")

    priorities = []
    for d in defects[:3]:
        did = d.get("defect_id")
        cname = d.get("class_name")
        prio = d.get("unified_score", {}).get("priority_level")
        priorities.append(f"Defect #{did} ({cname.upper()} - {prio}): Immediate optical isolation and rework evaluation.")

    if disposition == "ACCEPT" or len(defects) == 0:
        cond_str = "CONFORMING_CLASS_3 (0 Defects detected)"
        rationale = (
            "The PCB conforms fully to IPC-A-600 Class 3 acceptance criteria with zero detectable trace anomalies. "
            "Production release approved."
        )
        if not risks:
            risks = ["No operational, dielectric, or thermal reliability risks identified."]
        if not priorities:
            priorities = ["Standard post-inspection cleaning and packaging."]
    else:
        cond_str = (
            f"CRITICAL_NON_CONFORMING ({p1_count} P1 Critical defects detected)"
            if disposition == "REJECT" else
            f"MARGINAL_REVIEW_REQUIRED ({p2_count} High-risk defects requiring review)"
        )

        rationale = (
            f"The PCB was determined as '{disposition}' based on unified scoring where critical functional defects "
            f"violate IPC-A-600 Class 2/3 criteria. Immediate quarantine is mandated."
        )

    return {
        "board_condition": cond_str,
        "acceptance_rationale": rationale,
        "major_risks": risks,
        "immediate_priorities": priorities,
        "engine": "deterministic_fallback",
        "fallback_reason": reason,
    }


# ==============================================================================
# 3. Process Intelligence Prompt & Validator
# ==============================================================================

def build_process_intelligence_prompt(report: Dict[str, Any]) -> str:
    """
    Constructs prompt for manufacturing process intelligence and pattern hypotheses.
    """
    defects = report.get("defects", [])
    defect_counts = {}
    for d in defects:
        c = d.get("class_name", "unknown")
        defect_counts[c] = defect_counts.get(c, 0) + 1

    counts_str = ", ".join(f"{cls}: {cnt}" for cls, cnt in defect_counts.items())

    system_instruction = (
        "You are an Industrial PCB Manufacturing Process Intelligence expert for RGPIS-HDE.\n"
        "Analyze the defect distribution across the board and identify potential fabrication process concerns.\n"
        "Present all conclusions strictly as HYPOTHESES for quality investigation, NOT confirmed root causes.\n"
        "Output ONLY valid JSON with keys: pattern_summary, fab_stage_hypotheses, recommended_investigations."
    )

    user_content = (
        f"Board Defect Distribution:\n"
        f"- Total Defects: {len(defects)}\n"
        f"- Defect Breakdown: {counts_str}\n\n"
        "Formulate process hypotheses regarding:\n"
        "1. Etching line (over-etching vs under-etching balance)\n"
        "2. Photolithography / exposure / mask alignment\n"
        "3. Electroplating bath cleanliness & bubble entrapment\n\n"
        'Output JSON:\n{\n  "pattern_summary": "...",\n  "fab_stage_hypotheses": ["..."],\n  "recommended_investigations": ["..."]\n}'
    )

    formatted_prompt = (
        "<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n"
        f"{system_instruction}<|eot_id|>"
        "<|start_header_id|>user<|end_header_id|>\n\n"
        f"{user_content}<|eot_id|>"
        "<|start_header_id|>assistant<|end_header_id|>\n\n"
        '{\n  "pattern_summary": "'
    )

    return formatted_prompt


def validate_process_intelligence_output(raw_output: str) -> Tuple[bool, Dict[str, Any], Optional[str]]:
    """Validates process intelligence JSON."""
    try:
        clean = raw_output.strip()
        if "```json" in clean:
            clean = clean.split("```json")[1].split("```")[0].strip()
        elif "```" in clean:
            clean = clean.split("```")[1].split("```")[0].strip()

        first_brace = clean.find("{")
        last_brace = clean.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            clean = clean[first_brace:last_brace + 1]
        elif first_brace != -1:
            clean = clean[first_brace:]

        if clean.count('"') % 2 != 0:
            clean += '"'
        if not clean.endswith("}"):
            clean += "\n}"

        data = json.loads(clean)
        required = ["pattern_summary", "fab_stage_hypotheses", "recommended_investigations"]
        for k in required:
            if k not in data or not data[k]:
                return False, {}, f"Missing required process field: {k}"

        if isinstance(data["fab_stage_hypotheses"], str):
            data["fab_stage_hypotheses"] = [h.strip() for h in data["fab_stage_hypotheses"].split(";") if h.strip()]
        elif isinstance(data["fab_stage_hypotheses"], list):
            clean_list = []
            for item in data["fab_stage_hypotheses"]:
                if isinstance(item, dict):
                    stage = item.get("stage", "Fab Process")
                    hyp = item.get("hypothesis", item.get("description", str(item)))
                    clean_list.append(f"{stage}: {hyp}")
                else:
                    clean_list.append(str(item))
            data["fab_stage_hypotheses"] = clean_list

        if isinstance(data["recommended_investigations"], str):
            data["recommended_investigations"] = [i.strip() for i in data["recommended_investigations"].split(";") if i.strip()]
        elif isinstance(data["recommended_investigations"], list):
            clean_inv = []
            for item in data["recommended_investigations"]:
                if isinstance(item, dict):
                    stage = item.get("stage", "")
                    inv = item.get("audit", item.get("investigation", str(item)))
                    clean_inv.append(f"{stage}: {inv}" if stage else inv)
                else:
                    clean_inv.append(str(item))
            data["recommended_investigations"] = clean_inv

        # Check for uninformative generic placeholders
        generic_terms = {"top priority defects", "critical defects", "defects", "none", "high priority"}
        clean_risks = [r for r in data["major_risks"] if r.lower().strip() not in generic_terms and len(r.strip()) > 8]
        if len(clean_risks) < 2:
            fallback_board = get_deterministic_board_fallback(report, "Enriching generic risks with grounded physical criteria")
            data["major_risks"] = fallback_board["major_risks"]
        else:
            data["major_risks"] = clean_risks

        clean_prio = [p for p in data["immediate_priorities"] if p.lower().strip() not in generic_terms and len(p.strip()) > 8]
        if len(clean_prio) < 2:
            fallback_board = get_deterministic_board_fallback(report, "Enriching generic priorities with grounded defect targets")
            data["immediate_priorities"] = fallback_board["immediate_priorities"]
        else:
            data["immediate_priorities"] = clean_prio

        return True, data, None
    except Exception as e:
        return False, {}, f"Process JSON parse error: {str(e)}"


def get_deterministic_process_fallback(report: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic process intelligence generator."""
    defects = report.get("defects", [])
    classes = [d.get("class_name") for d in defects]

    hypotheses = []
    investigations = []

    opens = sum(1 for c in classes if "open" in c)
    mousebites = sum(1 for c in classes if "mousebite" in c)
    shorts = sum(1 for c in classes if "short" in c)
    spurs = sum(1 for c in classes if "spur" in c)
    pinholes = sum(1 for c in classes if "pinhole" in c or "pin-hole" in c)
    coppers = sum(1 for c in classes if "copper" in c)

    if opens > 0 or mousebites > 0:
        hypotheses.append(
            f"HYPOTHESIS (Etching Over-Rate): Co-occurrence of {opens} open(s) and {mousebites} mousebite(s) "
            "suggests potential chemical over-etching, elevated acid bath temperature, or prolonged line dwell time."
        )
        investigations.append("Audit chemical etchant concentration (CuCl2 / H2O2) and monitor conveyor belt feed speed.")

    if shorts > 0 or spurs > 0:
        hypotheses.append(
            f"HYPOTHESIS (Incomplete Etching / Resist Scum): Detection of {shorts} short(s) and {spurs} spur(s) "
            "points to potential localized under-etching, developing spray nozzle pressure drops, or photoresist scumming."
        )
        investigations.append("Inspect developer manifold spray nozzles and verify UV exposure energy calibration.")

    if pinholes > 0:
        hypotheses.append(
            f"HYPOTHESIS (Plating Aeration): {pinholes} pin-hole void(s) detected. Possible hydrogen micro-bubble "
            "entrapment on the copper surface during acid copper electroplating or particulate contamination on phototool."
        )
        investigations.append("Check plating bath agitation air spargers and inspect dry film laminator cleanroom roller filters.")

    if coppers > 0:
        hypotheses.append(
            f"HYPOTHESIS (Resist Stripping Residue): {coppers} spurious copper island(s) indicate incomplete photoresist "
            "stripping or re-deposition of unetched copper flakes in post-etch rinse tanks."
        )
        investigations.append("Inspect stripping chamber fluid filtration and rinse tank cascade replenishment.")

    return {
        "pattern_summary": (
            f"Multivariate defect distribution with {len(defects)} total anomalies spanning both subtractive (trace loss) "
            "and additive (clearance encroachment) mechanisms."
        ),
        "fab_stage_hypotheses": hypotheses,
        "recommended_investigations": investigations,
        "disclaimer": "Hypotheses generated for engineering guidance. Validation via chemical titration and SPC logs is required.",
        "engine": "deterministic_fallback"
    }


# ==============================================================================
# 4. Contextual Engineer Q&A Prompt
# ==============================================================================

def build_engineer_qa_prompt(query: str, report: Dict[str, Any], intelligence: Dict[str, Any]) -> str:
    """
    Constructs prompt for contextual Q&A with the engineer.
    """
    meta = report.get("metadata", {})
    summary = report.get("board_summary", {})
    defects = report.get("defects", [])

    board_id = meta.get("board_id", "Board")
    disposition = summary.get("overall_disposition", "UNKNOWN")
    total_defects = summary.get("total_defects", len(defects))

    # Top defects summary
    defect_lines = []
    for d in defects:
        did = d.get("defect_id")
        cname = d.get("class_name")
        prio = d.get("unified_score", {}).get("priority_level")
        score = d.get("unified_score", {}).get("score")
        ceri_w = d.get("ceri", {}).get("trace_width_reduction_pct")
        ceri_c = d.get("ceri", {}).get("clearance_intrusion_pct")
        defect_lines.append(
            f"- Defect #{did}: {cname} (Priority: {prio}, Score: {score}/100, Width Loss: {ceri_w}%, Clearance Red: {ceri_c}%)"
        )
    defects_context = "\n".join(defect_lines)

    board_cond = intelligence.get("board_level", {}).get("board_condition", "")
    rationale = intelligence.get("board_level", {}).get("acceptance_rationale", "")

    system_instruction = (
        "You are the Lead PCB Quality & Reliability Engineer for RGPIS-HDE.\n"
        "Answer the engineer's question precisely, professionally, and grounded strictly in the provided inspection data.\n"
        "CEIA electrical indicators are counterfactual geometric proxies, not physical multimeter measurements. "
        "Do not invent measurements. Answer in 2-4 authoritative sentences."
    )

    user_content = (
        f"Inspection Context for Board '{board_id}':\n"
        f"- Overall Board Disposition: {disposition}\n"
        f"- Board Condition: {board_cond}\n"
        f"- Acceptance/Rejection Rationale: {rationale}\n"
        f"- Total Defects Detected ({total_defects}):\n{defects_context}\n\n"
        f"Engineer's Question: \"{query}\"\n\n"
        "Provide a direct, factual, and concise engineering answer grounded strictly in this board data:"
    )

    formatted_prompt = (
        "<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n"
        f"{system_instruction}<|eot_id|>"
        "<|start_header_id|>user<|end_header_id|>\n\n"
        f"{user_content}<|eot_id|>"
        "<|start_header_id|>assistant<|end_header_id|>\n\n"
    )

    return formatted_prompt
