"""
Comprehensive Test Suite for RGPIS-HDE PCB Defect Advisory (Task 5).
Tests all 8 mandatory categories:
 1. Open circuit     4. Spur              7. Unknown defect
 2. Short circuit    5. Spurious copper   8. Low-confidence defect
 3. Mouse bite       6. Pin hole
Measures RAM, inference latency, tokens/sec, and schema compliance.
"""

import json
import logging
import sys
import time
from pathlib import Path

from llama_advisory.defect_advisor import PCBDefectAdvisor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

TEST_CASES = [
    {
        "name": "1. Open Circuit",
        "input": {"defect_type": "open_circuit",    "confidence": 0.94, "location": [120, 240, 165, 275]}
    },
    {
        "name": "2. Short Circuit",
        "input": {"defect_type": "short_circuit",   "confidence": 0.91, "location": [310, 180, 345, 225]}
    },
    {
        "name": "3. Mouse Bite",
        "input": {"defect_type": "mouse_bite",      "confidence": 0.88, "location": [415, 520, 435, 545]}
    },
    {
        "name": "4. Spur",
        "input": {"defect_type": "spur",            "confidence": 0.86, "location": [205, 330, 230, 360]}
    },
    {
        "name": "5. Spurious Copper",
        "input": {"defect_type": "spurious_copper", "confidence": 0.89, "location": [550, 110, 580, 145]}
    },
    {
        "name": "6. Pin Hole",
        "input": {"defect_type": "pin_hole",        "confidence": 0.93, "location": [85,  410, 105, 430]}
    },
    {
        "name": "7. Unknown Defect",
        "input": {"defect_type": "delamination_blister", "confidence": 0.72, "location": [600, 650, 640, 690]}
    },
    {
        "name": "8. Low-Confidence",
        "input": {"defect_type": "open_circuit",    "confidence": 0.38, "location": [150, 200, 175, 225]}
    },
]

REQUIRED_KEYS = [
    "defect_type",
    "explanation",
    "possible_consequences",
    "recommended_verification_procedure",
    "operator_guidance",
    "disclaimer",
]


def check_format(res: dict) -> tuple[bool, list[str]]:
    failures = []
    for k in REQUIRED_KEYS:
        if k not in res or not res[k]:
            failures.append(f"missing/empty: {k}")
    if "does not independently approve or reject" not in res.get("disclaimer", "").lower():
        failures.append("disclaimer missing safety clause")
    text_lower = json.dumps(res).lower()
    for bad in ["pcb approved", "pcb rejected", "disposition: approved", "disposition: rejected"]:
        if bad in text_lower:
            failures.append(f"hallucination: '{bad}'")
    return (len(failures) == 0, failures)


def run_benchmark():
    sep = "=" * 72
    print(sep)
    print("  RGPIS-HDE PCB DEFECT ADVISORY — ExecuTorch Benchmark Suite")
    print("  Llama 3.2 1B Instruct · 4-bit SpinQuant · XNNPACK CPU backend")
    print(sep)

    advisor = PCBDefectAdvisor()
    print("\n[INIT] Loading ExecuTorch engine (first load ~45s)...")
    t0 = time.time()
    advisor.initialize()
    print(f"[INIT] Engine ready in {time.time()-t0:.1f}s\n")

    results = []
    for idx, tc in enumerate(TEST_CASES, 1):
        name  = tc["name"]
        inp   = tc["input"]
        print(f"\n{'─'*72}")
        print(f"TEST {idx}/8 — {name}")
        print(f"Input: {json.dumps(inp)}")
        print("─" * 72)

        try:
            res = advisor.advise(inp, max_new_tokens=380)
        except Exception as e:
            print(f"[ERROR] Exception during advise(): {e}")
            results.append({"name": name, "input": inp, "error": str(e),
                            "format_pass": False, "latency_s": 0, "ram_mb": 0, "engine": "error"})
            continue

        fmt_pass, fmt_issues = check_format(res)
        metrics = res.get("metrics", {})
        latency = metrics.get("latency_seconds", 0.0)
        ram_mb  = metrics.get("ram_usage_mb", 0.0)
        tok_s   = metrics.get("tokens_per_second", 0.0)
        ntoks   = metrics.get("generated_tokens", 0)
        engine_used = res.get("engine", "ExecuTorch")

        print(f"\n--- Generated Advisory ---")
        if res.get("raw_generated"):
            print(f"  Raw Model Output : {res.get('raw_generated').strip()[:160]}...")
        print(f"  Explanation      : {res.get('explanation', 'N/A')}")
        print(f"  Consequences     : {res.get('possible_consequences', [])}")
        print(f"  Verification     : {res.get('recommended_verification_procedure', [])}")
        print(f"  Operator Guidance: {res.get('operator_guidance', 'N/A')}")
        uw = res.get("uncertainty_warning")
        if uw:
            print(f"  Uncertainty Warn : {uw}")
        print(f"  Disclaimer       : {res.get('disclaimer', 'N/A')}")
        print(f"\n--- Performance & Runtime Verification ---")
        print(f"  Latency  : {latency:.2f}s   |  Tokens: {ntoks}  |  Speed: {tok_s:.2f} tok/s")
        print(f"  RAM      : {ram_mb:.1f} MB")
        print(f"  Engine   : {engine_used}")
        print(f"  Format   : {'PASS ✓' if fmt_pass else 'FAIL ✗ — ' + str(fmt_issues)}")

        results.append({
            "name": name,
            "input": inp,
            "raw_generated": res.get("raw_generated"),
            "explanation": res.get("explanation"),
            "operator_guidance": res.get("operator_guidance"),
            "uncertainty_warning": res.get("uncertainty_warning"),
            "disclaimer": res.get("disclaimer"),
            "format_pass": fmt_pass,
            "format_issues": fmt_issues,
            "latency_s": latency,
            "ram_mb": ram_mb,
            "tokens_per_second": tok_s,
            "generated_tokens": ntoks,
            "engine": engine_used,
        })

    # Save results
    out = Path(__file__).parent / "test_results.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2)

    # Summary table
    print(f"\n{sep}")
    print("  BENCHMARK SUMMARY — RUNTIME & SUCCESS SEPARATION")
    print(sep)
    print(f"{'Test':<24} {'Format':<8} {'Engine Used':<32} {'Latency(s)':<11} {'RAM(MB)'}")
    print("─" * 84)
    all_pass = True
    llama_count = 0
    fallback_count = 0
    for r in results:
        fmt = "PASS ✓" if r.get("format_pass") else "FAIL ✗"
        if not r.get("format_pass"):
            all_pass = False
        engine_str = r.get("engine", "ExecuTorch")
        if "Llama" in engine_str:
            llama_count += 1
        elif "fallback" in engine_str:
            fallback_count += 1
        lat  = f"{r.get('latency_s', 0):.2f}"
        ram  = f"{r.get('ram_mb', 0):.0f}"
        print(f"{r['name']:<24} {fmt:<8} {engine_str:<32} {lat:<11} {ram}")

    total = len(results)
    llama_rate = (llama_count / total * 100) if total > 0 else 0
    fallback_rate = (fallback_count / total * 100) if total > 0 else 0

    print("─" * 84)
    print(f"Total Test Cases Evaluated : {total}")
    print(f"Llama Model Direct Success : {llama_count}/{total} ({llama_rate:.1f}%)")
    print(f"Deterministic Fallback     : {fallback_count}/{total} ({fallback_rate:.1f}%)")
    print(f"Overall Format Compliance  : {'100% PASSED ✓' if all_pass else 'SOME FAILED'}")
    print(f"Results saved to: {out}")
    print(sep)


if __name__ == "__main__":
    run_benchmark()
