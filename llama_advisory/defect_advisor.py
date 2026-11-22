"""
Industrial Defect Advisory System for RGPIS-HDE PCB Inspection.
Combines ExecuTorch offline Llama 3.2 engine, IPC-A-600 grounded knowledge base,
output schema validation, and deterministic safety fallback.
"""

import json
import logging
import time
from typing import Any, Dict, Optional, Tuple

from llama_advisory.executorch_engine import ExecuTorchLlamaEngine
from llama_advisory.prompt_templates import (
    build_llama_prompt,
    validate_advisory_output,
    get_deterministic_fallback,
    load_knowledge_base,
)

logger = logging.getLogger("PCBDefectAdvisor")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class PCBDefectAdvisor:
    """
    Main defect advisory controller.
    """

    def __init__(self, engine: Optional[ExecuTorchLlamaEngine] = None):
        self.engine = engine or ExecuTorchLlamaEngine()
        self.kb = load_knowledge_base()

    def initialize(self):
        """Loads the ExecuTorch engine."""
        self.engine.load_model()

    def advise(self, defect_input: Dict[str, Any], max_new_tokens: int = 380) -> Dict[str, Any]:
        """
        Processes a single defect detection and generates an evidence-grounded advisory report.
        """
        defect_type = str(defect_input.get("defect_type", "unknown")).lower().strip()
        confidence = float(defect_input.get("confidence", 0.0))
        location = defect_input.get("location", [0, 0, 0, 0])

        start_time = time.time()

        # Step 1: Check low-confidence edge case (< threshold)
        threshold = self.kb.get("confidence_threshold", 0.50)
        is_low_conf = confidence < threshold
        is_uncatalogued = defect_type not in self.kb.get("defects", {})

        # Step 2: Build prompt with IPC-A-600 reference
        prompt, ref_context = build_llama_prompt(defect_input)

        raw_generated = ""
        full_json_candidate = ""
        inference_metrics = {
            "latency_seconds": 0.0,
            "tokens_per_second": 0.0,
            "ram_usage_mb": 0.0,
            "generated_tokens": 0,
            "engine": "ExecuTorch (XNNPACK / CPU)",
        }

        # Step 3: Run ExecuTorch inference
        try:
            gen_res = self.engine.generate(
                prompt=prompt,
                max_new_tokens=max_new_tokens,
                temperature=0.2,  # Low temperature for deterministic factual extraction
                top_p=0.9,
            )
            raw_generated = gen_res.get("text", "")
            
            # Reconstruct complete JSON from assistant prefix
            prefix = f'{{\n  "defect_type": "{defect_type}",\n  "confidence": {confidence},\n  "location": {location},\n  "explanation": "'
            if raw_generated and not raw_generated.strip().startswith("{"):
                full_json_candidate = prefix + raw_generated
            else:
                full_json_candidate = raw_generated

            inference_metrics["latency_seconds"] = gen_res.get("latency_seconds", 0.0)
            inference_metrics["tokens_per_second"] = gen_res.get("tokens_per_second", 0.0)
            inference_metrics["ram_usage_mb"] = gen_res.get("ram_usage_mb", 0.0)
            inference_metrics["generated_tokens"] = gen_res.get("generated_tokens", 0)
        except Exception as e:
            logger.error(f"ExecuTorch inference exception: {e}")
            fallback_res = get_deterministic_fallback(defect_input, f"ExecuTorch runtime error: {str(e)}")
            fallback_res["metrics"] = inference_metrics
            fallback_res["metrics"]["latency_seconds"] = round(time.time() - start_time, 3)
            fallback_res["engine"] = "deterministic_fallback"
            return fallback_res

        # Step 4: Validate output and check hallucinations
        is_valid, parsed_data, err_msg = validate_advisory_output(full_json_candidate, defect_input)

        if not is_valid:
            logger.warning(f"Validation failed: {err_msg}. Triggering deterministic fallback.")
            fallback_res = get_deterministic_fallback(defect_input, err_msg or "Validation failed")
            fallback_res["raw_generated"] = raw_generated
            fallback_res["full_json_candidate"] = full_json_candidate
            fallback_res["metrics"] = inference_metrics
            fallback_res["engine"] = "deterministic_fallback"
            return fallback_res

        # Step 5: Format final verified output
        parsed_data["engine"] = "ExecuTorch Llama-3.2-1B-Instruct"
        parsed_data["metrics"] = inference_metrics
        parsed_data["raw_generated"] = raw_generated
        parsed_data["verification_status"] = "PASSED_SCHEMA_AND_GROUNDING_CHECKS"

        return parsed_data
