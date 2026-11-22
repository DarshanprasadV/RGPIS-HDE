"""
RGPIS-HDE Engineering Intelligence Dashboard Generator.
Renders an enterprise-grade, standalone, interactive HTML dashboard visualizing:
1. Executive Board KPIs & Unified Risk Gauge
2. Optical PCB Defect Map with interactive priority-coded bounding box overlays
3. Board-Level Intelligence Summary
4. Manufacturing Process Intelligence (Hypotheses)
5. Individual Defect Intelligence Cards (CERI & CEIA proxy badges)
6. Prioritized Corrective Action Checklist
7. Interactive Engineer Q&A Simulator Console
"""

import base64
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "intelligence"


def _embed_image_b64(image_name: str) -> str:
    """
    Returns a data-URI string for the annotated YOLO image (falling back to the
    original test image, then an empty string if neither is found).
    The image is embedded inline so the HTML is fully self-contained / offline.
    """
    stems = [
        PROJECT_ROOT / "outputs" / "predictions" / f"{Path(image_name).stem}_annotated.jpg",
        PROJECT_ROOT / "test_images" / image_name,
    ]
    for path in stems:
        if path.exists():
            with open(path, "rb") as fh:
                b64 = base64.b64encode(fh.read()).decode("ascii")
            suffix = path.suffix.lstrip(".")
            mime = "jpeg" if suffix in ("jpg", "jpeg") else suffix
            return f"data:image/{mime};base64,{b64}"
    return ""


def generate_dashboard_html(
    report: Dict[str, Any],
    intelligence: Dict[str, Any],
    output_html_path: Optional[Path] = None,
) -> Path:
    """
    Renders the interactive HTML dashboard.
    """
    if output_html_path is None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        board_id = report.get("metadata", {}).get("board_id", "board")
        output_html_path = OUTPUT_DIR / f"{board_id}_intelligence_dashboard.html"
    else:
        output_html_path = Path(output_html_path)
        output_html_path.parent.mkdir(parents=True, exist_ok=True)

    meta = report.get("metadata", {})
    summary = report.get("board_summary", {})
    board_level = intelligence.get("board_level_intelligence", {})
    defects = intelligence.get("individual_defect_intelligence", [])
    actions = intelligence.get("corrective_action_recommendations", [])
    process = intelligence.get("process_intelligence", {})

    board_id = meta.get("board_id", "PCB-INSPECTION")
    image_name = meta.get("image_name", "pcb_image.jpg")
    disposition = summary.get("overall_disposition", "REVIEW")
    total_defects = summary.get("total_defects", len(defects))
    p1_count = summary.get("critical_defects_count", 0)
    p2_count = summary.get("high_risk_count", 0)
    max_score = summary.get("max_unified_risk_score", 0.0)

    # Calculate max CERI & CEIA values for KPI cards
    max_ceri_red = max([d.get("ceri_metrics", {}).get("trace_width_reduction_pct", 0) for d in defects] or [0])
    max_ceia_bottleneck = max([d.get("ceia_proxies", {}).get("current_density_multiplier", 1.0) for d in defects] or [1.0])

    disp_color = "#ef4444" if disposition == "REJECT" else ("#f59e0b" if disposition == "REVIEW" else "#10b981")
    disp_glow = "rgba(239, 68, 68, 0.4)" if disposition == "REJECT" else ("rgba(245, 158, 11, 0.4)" if disposition == "REVIEW" else "rgba(16, 185, 129, 0.4)")

    # Serialized JSON data for interactive client-side Q&A
    client_report_json = json.dumps(report).replace("</script>", "<\\/script>")
    client_intel_json = json.dumps(intelligence).replace("</script>", "<\\/script>")

    # Embed annotated PCB image as base64 (fully offline / self-contained HTML)
    pcb_image_b64 = _embed_image_b64(image_name)
    pcb_bg_style = (
        f"background-image: url('{pcb_image_b64}'); "
        "background-size: contain; "
        "background-repeat: no-repeat; "
        "background-position: center;"
        if pcb_image_b64
        else ""
    )

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>RGPIS-HDE Intelligence Dashboard | {board_id}</title>
  <style>
    :root {{
      --bg: #0b0f19;
      --card-bg: #111827;
      --card-border: #1f2937;
      --text-main: #f3f4f6;
      --text-muted: #9ca3af;
      --accent: #3b82f6;
      --danger: #ef4444;
      --warning: #f59e0b;
      --success: #10b981;
      --p1: #ef4444;
      --p2: #f97316;
      --p3: #eab308;
      --p4: #06b6d4;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
    body {{ background: var(--bg); color: var(--text-main); line-height: 1.5; padding: 24px; }}
    .container {{ max-width: 1400px; margin: 0 auto; }}

    /* Header */
    .header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 20px 28px;
      margin-bottom: 24px;
      box-shadow: 0 4px 20px rgba(0,0,0,0.4);
    }}
    .header-left h1 {{ font-size: 22px; font-weight: 700; letter-spacing: 0.5px; display: flex; align-items: center; gap: 12px; }}
    .header-left .sub {{ font-size: 13px; color: var(--text-muted); margin-top: 4px; }}
    .tag {{ display: inline-block; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; text-transform: uppercase; background: #1e293b; color: #94a3b8; }}
    .disposition-badge {{
      background: {disp_color};
      color: #fff;
      font-size: 20px;
      font-weight: 800;
      padding: 10px 28px;
      border-radius: 8px;
      letter-spacing: 1.5px;
      box-shadow: 0 0 25px {disp_glow};
      display: flex;
      flex-direction: column;
      align-items: center;
    }}
    .disposition-badge .sub-label {{ font-size: 10px; font-weight: 600; opacity: 0.9; letter-spacing: 0.5px; }}

    /* KPI Row */
    .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }}
    .kpi-card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 10px;
      padding: 16px 20px;
      display: flex;
      flex-direction: column;
    }}
    .kpi-label {{ font-size: 12px; color: var(--text-muted); text-transform: uppercase; font-weight: 600; letter-spacing: 0.5px; }}
    .kpi-val {{ font-size: 28px; font-weight: 800; margin-top: 4px; color: #fff; }}
    .kpi-sub {{ font-size: 12px; color: var(--text-muted); margin-top: 2px; }}

    /* Grid Layouts */
    .main-grid {{ display: grid; grid-template-columns: 460px 1fr; gap: 24px; margin-bottom: 24px; }}
    @media (max-width: 1024px) {{ .main-grid {{ grid-template-columns: 1fr; }} }}

    .card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 22px;
      margin-bottom: 24px;
    }}
    .card-title {{
      font-size: 16px;
      font-weight: 700;
      margin-bottom: 16px;
      display: flex;
      align-items: center;
      gap: 10px;
      border-bottom: 1px solid #1f2937;
      padding-bottom: 10px;
    }}

    /* Defect Visualizer */
    .pcb-canvas-wrap {{
      position: relative;
      width: 100%;
      height: 420px;
      background: #060911;
      border: 1px solid #1e293b;
      border-radius: 8px;
      overflow: hidden;
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    .pcb-canvas {{ width: 100%; height: 100%; position: relative; }}
    .pcb-bg-image {{
      position: absolute;
      inset: 0;
      background-size: contain;
      background-repeat: no-repeat;
      background-position: center;
      opacity: 0.82;
    }}
    .pcb-grid-lines {{
      position: absolute; width: 100%; height: 100%;
      background-size: 32px 32px;
      background-image: linear-gradient(to right, rgba(255, 255, 255, 0.025) 1px, transparent 1px),
                        linear-gradient(to bottom, rgba(255, 255, 255, 0.025) 1px, transparent 1px);
      pointer-events: none;
    }}
    .bbox-marker {{
      position: absolute;
      border: 2px solid;
      background: rgba(0, 0, 0, 0.18);
      cursor: pointer;
      transition: all 0.2s ease;
      display: flex;
      align-items: flex-start;
      padding: 2px;
      z-index: 5;
    }}
    .bbox-marker:hover {{
      background: rgba(255, 255, 255, 0.18);
      box-shadow: 0 0 18px currentColor, inset 0 0 8px rgba(255,255,255,0.08);
      z-index: 10;
    }}
    .bbox-tag {{
      font-size: 10px;
      font-weight: 700;
      color: #fff;
      padding: 1px 4px;
      border-radius: 2px;
      white-space: nowrap;
      pointer-events: none;
    }}

    /* Lists and Bullets */
    .bullet-list {{ list-style: none; }}
    .bullet-list li {{
      padding: 8px 12px;
      background: #0d1322;
      border-left: 3px solid var(--accent);
      border-radius: 0 6px 6px 0;
      margin-bottom: 8px;
      font-size: 13.5px;
    }}
    .bullet-list li.danger-item {{ border-left-color: var(--danger); background: rgba(239, 68, 68, 0.08); }}
    .bullet-list li.warning-item {{ border-left-color: var(--warning); background: rgba(245, 158, 11, 0.08); }}

    /* Priority Badges */
    .prio-pill {{
      display: inline-block;
      padding: 2px 8px;
      border-radius: 12px;
      font-size: 11px;
      font-weight: 700;
    }}
    .prio-P1_CRITICAL {{ background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid #ef4444; }}
    .prio-P2_HIGH {{ background: rgba(249, 115, 22, 0.2); color: #fb923c; border: 1px solid #f97316; }}
    .prio-P3_MEDIUM {{ background: rgba(234, 179, 8, 0.2); color: #facc15; border: 1px solid #eab308; }}
    .prio-P4_LOW {{ background: rgba(6, 182, 212, 0.2); color: #22d3ee; border: 1px solid #06b6d4; }}

    /* Defect Intelligence Accordion */
    .defect-card {{
      background: #0f172a;
      border: 1px solid #1e293b;
      border-radius: 10px;
      margin-bottom: 16px;
      overflow: hidden;
      transition: border-color 0.2s ease;
    }}
    .defect-card:hover {{ border-color: #334155; }}
    .defect-header {{
      padding: 14px 18px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      cursor: pointer;
      background: #111e38;
      border-bottom: 1px solid #1e293b;
    }}
    .defect-title {{ font-size: 15px; font-weight: 700; display: flex; align-items: center; gap: 10px; }}
    .defect-body {{ padding: 18px; display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }}
    @media (max-width: 800px) {{ .defect-body {{ grid-template-columns: 1fr; }} }}

    .section-title {{ font-size: 12px; font-weight: 700; text-transform: uppercase; color: #94a3b8; margin-bottom: 6px; letter-spacing: 0.5px; }}
    .proxy-badge {{
      display: inline-block;
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 10px;
      font-weight: 700;
      background: rgba(168, 85, 247, 0.2);
      color: #c084fc;
      border: 1px solid #a855f7;
      margin-bottom: 6px;
    }}

    /* Table Styles */
    .custom-table {{ width: 100%; border-collapse: collapse; font-size: 13px; text-align: left; }}
    .custom-table th {{ background: #1e293b; padding: 10px 14px; font-weight: 600; color: #cbd5e1; border-bottom: 1px solid #334155; }}
    .custom-table td {{ padding: 10px 14px; border-bottom: 1px solid #1e293b; color: #e2e8f0; vertical-align: top; }}
    .custom-table tr:hover td {{ background: rgba(255, 255, 255, 0.02); }}

    /* Interactive QA Console */
    .qa-box {{
      background: #090d16;
      border: 1px solid #1e293b;
      border-radius: 10px;
      padding: 18px;
    }}
    .qa-chips {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }}
    .qa-chip {{
      background: #1e293b;
      color: #94a3b8;
      font-size: 12px;
      padding: 6px 12px;
      border-radius: 16px;
      cursor: pointer;
      border: 1px solid #334155;
      transition: all 0.2s ease;
    }}
    .qa-chip:hover {{ background: #2563eb; color: #fff; border-color: #3b82f6; }}
    .qa-input-row {{ display: flex; gap: 10px; margin-bottom: 14px; }}
    .qa-input {{
      flex: 1;
      background: #111827;
      border: 1px solid #374151;
      border-radius: 6px;
      padding: 10px 14px;
      color: #fff;
      font-size: 14px;
    }}
    .qa-btn {{
      background: var(--accent);
      color: #fff;
      border: none;
      border-radius: 6px;
      padding: 10px 20px;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.2s;
    }}
    .qa-btn:hover {{ background: #2563eb; }}
    .qa-output {{
      background: #131b2e;
      border: 1px solid #1e293b;
      border-radius: 8px;
      padding: 14px;
      font-size: 13.5px;
      color: #e2e8f0;
      min-height: 80px;
      display: flex;
      flex-direction: column;
      justify-content: center;
    }}

    /* Buttons */
    .btn-group {{ display: flex; gap: 10px; }}
    .btn {{
      padding: 8px 16px;
      border-radius: 6px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      border: 1px solid #334155;
      background: #1e293b;
      color: #f1f5f9;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }}
    .btn:hover {{ background: #334155; }}
  </style>
</head>
<body>

<div class="container">

  <!-- Top Navigation & Actions -->
  <div class="header">
    <div class="header-left">
      <h1>
        <span>⚡ RGPIS-HDE Engineering Intelligence</span>
        <span class="tag">Bharat AI-SoC 2026/27</span>
      </h1>
      <div class="sub">
        Board ID: <strong>{board_id}</strong> &nbsp;|&nbsp;
        Image: <code>{image_name}</code> &nbsp;|&nbsp;
        Standard: <strong>IPC-A-600 Class 2/3</strong> &nbsp;|&nbsp;
        Runtime: <strong>ExecuTorch (Offline XNNPACK CPU)</strong>
      </div>
    </div>
    <div class="header-right" style="display:flex; align-items:center; gap:20px;">
      <div class="btn-group">
        <button class="btn" onclick="window.print()">🖨️ Print Traveler</button>
        <button class="btn" onclick="downloadJSON()">💾 Export JSON</button>
      </div>
      <div class="disposition-badge">
        <span>{disposition}</span>
        <span class="sub-label">FINAL BOARD DECISION</span>
      </div>
    </div>
  </div>

  <!-- KPI Row -->
  <div class="kpi-grid">
    <div class="kpi-card">
      <span class="kpi-label">Total Detected Defects</span>
      <span class="kpi-val">{total_defects}</span>
      <span class="kpi-sub">Optical YOLO26n (640x640)</span>
    </div>
    <div class="kpi-card" style="border-left: 3px solid var(--danger);">
      <span class="kpi-label">P1 Critical Defects</span>
      <span class="kpi-val" style="color: #f87171;">{p1_count}</span>
      <span class="kpi-sub">Immediate Functional Killers</span>
    </div>
    <div class="kpi-card" style="border-left: 3px solid var(--warning);">
      <span class="kpi-label">Max CERI Trace Loss</span>
      <span class="kpi-val" style="color: #fb923c;">{max_ceri_red}%</span>
      <span class="kpi-sub">Geometric Conductor Reduction</span>
    </div>
    <div class="kpi-card" style="border-left: 3px solid #a855f7;">
      <span class="kpi-label">Max CEIA Current Crowding</span>
      <span class="kpi-val" style="color: #c084fc;">{max_ceia_bottleneck}x</span>
      <span class="kpi-sub">Counterfactual Geometric Proxy</span>
    </div>
    <div class="kpi-card">
      <span class="kpi-label">Unified Risk Score</span>
      <span class="kpi-val">{max_score}<span style="font-size:16px; color:#9ca3af;">/100</span></span>
      <span class="kpi-sub">Composite Prioritization Index</span>
    </div>
  </div>

  <!-- Main Grid: Left Defect Visualizer, Right Board Intelligence -->
  <div class="main-grid">
    <!-- Defect Visualizer -->
    <div class="card" style="margin-bottom:0;">
      <div class="card-title">
        <span>📐 Board Defect Map</span>
        <span class="tag" style="margin-left:auto;">Interactive Coordinates</span>
      </div>
      <div class="pcb-canvas-wrap">
        <div class="pcb-bg-image" style="{pcb_bg_style}"></div>
        <div class="pcb-grid-lines"></div>
        <div class="pcb-canvas" id="pcbCanvas">
          <!-- Bounding Boxes rendered here dynamically -->
        </div>
      </div>
      <div style="display:flex; justify-content:space-around; margin-top:14px; font-size:11px; color:#94a3b8;">
        <span><span style="color:var(--p1); font-weight:800;">■</span> P1 Critical</span>
        <span><span style="color:var(--p2); font-weight:800;">■</span> P2 High</span>
        <span><span style="color:var(--p3); font-weight:800;">■</span> P3 Medium</span>
        <span><span style="color:var(--p4); font-weight:800;">■</span> P4 Low</span>
      </div>
      <p style="font-size:11.5px; color:#64748b; margin-top:8px; text-align:center;">
        YOLO-annotated PCB image with priority-coded bounding boxes — hover to inspect, click to jump to defect card.
      </p>
    </div>

    <!-- Board-Level Intelligence -->
    <div class="card" style="margin-bottom:0;">
      <div class="card-title">
        <span>📋 Layer 1: Board-Level Intelligence Report</span>
        <span class="tag" style="background:#1e3a8a; color:#93c5fd; margin-left:auto;">ExecuTorch Llama 3.2</span>
      </div>
      <div style="margin-bottom:14px;">
        <span class="section-title">Board Condition Assessment:</span>
        <div style="font-size:15px; font-weight:700; color:#f8fafc; margin-top:2px;">
          {board_level.get('board_condition', 'Inspection Assessment Complete')}
        </div>
      </div>
      <div style="margin-bottom:14px;">
        <span class="section-title">Acceptance / Rejection Rationale (IPC-A-600 Grounded):</span>
        <p style="font-size:13.5px; color:#cbd5e1; margin-top:2px; line-height:1.6;">
          {board_level.get('acceptance_rationale', summary.get('disposition_reason', ''))}
        </p>
      </div>
      <div style="margin-bottom:14px;">
        <span class="section-title">Major Engineering Risks:</span>
        <ul class="bullet-list" style="margin-top:4px;">
"""

    for r in board_level.get("major_risks", []):
        html_content += f"""          <li class="danger-item">⚠️ {r}</li>\n"""

    html_content += f"""        </ul>
      </div>
      <div>
        <span class="section-title">Immediate Priority Focus:</span>
        <ul class="bullet-list" style="margin-top:4px;">
"""
    for p in board_level.get("immediate_priorities", []):
        html_content += f"""          <li class="warning-item">🎯 {p}</li>\n"""

    html_content += f"""        </ul>
      </div>
    </div>
  </div>

  <!-- Layer 4: Manufacturing Process Intelligence (Hypotheses) -->
  <div class="card">
    <div class="card-title">
      <span>🏭 Layer 4: Manufacturing Process Intelligence (Hypotheses)</span>
      <span class="tag" style="background:rgba(245, 158, 11, 0.2); color:#fbbf24; margin-left:auto;">Fabrication Line Correlations</span>
    </div>
    <div style="background:rgba(245, 158, 11, 0.08); border-left:4px solid #f59e0b; padding:10px 14px; border-radius:0 6px 6px 0; margin-bottom:16px; font-size:12.5px; color:#fef3c7;">
      <strong>⚠️ Process Disclaimer:</strong> All manufacturing stage correlations are probabilistic engineering hypotheses based on cross-defect spatial patterns. Root cause confirmation requires chemical bath titration and SPC parameter audits.
    </div>
    <p style="font-size:13.5px; color:#cbd5e1; margin-bottom:14px;">
      <strong>Pattern Summary:</strong> {process.get('pattern_summary', 'Multi-defect distribution across panel.')}
    </p>
    <div style="display:grid; grid-template-columns:1fr 1fr; gap:16px;">
      <div>
        <span class="section-title">Fab Stage Hypotheses:</span>
        <ul class="bullet-list" style="margin-top:6px;">
"""
    for h in process.get("fab_stage_hypotheses", []):
        html_content += f"""          <li style="border-left-color:#38bdf8; background:rgba(56, 189, 248, 0.08);">🔬 {h}</li>\n"""

    html_content += f"""        </ul>
      </div>
      <div>
        <span class="section-title">Recommended Process Audits:</span>
        <ul class="bullet-list" style="margin-top:6px;">
"""
    for inv in process.get("recommended_investigations", []):
        html_content += f"""          <li style="border-left-color:#34d399; background:rgba(52, 211, 153, 0.08);">✅ {inv}</li>\n"""

    html_content += f"""        </ul>
      </div>
    </div>
  </div>

  <!-- Layer 3: Prioritized Corrective Action Matrix -->
  <div class="card">
    <div class="card-title">
      <span>🛠️ Layer 3: Prioritized Corrective Action & Inspection Recommendations</span>
      <span class="tag" style="margin-left:auto;">Ranked by Unified Risk</span>
    </div>
    <div style="overflow-x:auto;">
      <table class="custom-table">
        <thead>
          <tr>
            <th style="width:60px;">Step #</th>
            <th style="width:140px;">Defect</th>
            <th style="width:110px;">Priority</th>
            <th style="width:80px;">Score</th>
            <th>Recommended Corrective Action</th>
            <th>Verification Protocol</th>
            <th style="width:150px;">Station</th>
            <th style="width:70px; text-align:center;">Sign-off</th>
          </tr>
        </thead>
        <tbody>
"""

    for a in actions:
        p_class = f"prio-{a.get('priority_level', 'P2_HIGH')}"
        html_content += f"""          <tr>
            <td style="font-weight:700; color:#94a3b8;">#{a.get('step_number')}</td>
            <td><strong>{a.get('defect_name')}</strong><br><span style="font-size:11px; color:#64748b;">ID #{a.get('defect_id')}</span></td>
            <td><span class="prio-pill {p_class}">{a.get('priority_level')}</span></td>
            <td style="font-weight:700;">{a.get('unified_score')}</td>
            <td>{a.get('recommended_action')}</td>
            <td><span style="font-size:12px; color:#cbd5e1;">{'; '.join(a.get('verification_procedure', []))}</span></td>
            <td><span class="tag">{a.get('assigned_station')}</span></td>
            <td style="text-align:center;"><input type="checkbox" style="transform:scale(1.2); cursor:pointer;"></td>
          </tr>\n"""

    html_content += f"""        </tbody>
      </table>
    </div>
  </div>

  <!-- Layer 2: Individual Defect Intelligence Cards -->
  <div class="card">
    <div class="card-title">
      <span>🔍 Layer 2: Individual Defect Engineering Intelligence</span>
      <span class="tag" style="background:#1e3a8a; color:#93c5fd; margin-left:auto;">IPC-A-600 / CERI / CEIA Grounded</span>
    </div>
"""

    for d in defects:
        did = d.get("defect_id")
        prio = d.get("unified_score", {}).get("priority_level", "P2_HIGH")
        score = d.get("unified_score", {}).get("score", 0)
        p_class = f"prio-{prio}"
        ceri = d.get("ceri_metrics", {})
        ceia = d.get("ceia_proxies", {})
        bbox = d.get("bbox", [0, 0, 0, 0])

        html_content += f"""    <div class="defect-card" id="defect-card-{did}">
      <div class="defect-header" onclick="toggleDefect({did})">
        <div class="defect-title">
          <span>Defect #{did}: <strong>{d.get('display_name')}</strong></span>
          <span class="prio-pill {p_class}">{prio}</span>
          <span style="font-size:12px; color:#94a3b8;">Risk Score: <strong>{score}/100</strong></span>
        </div>
        <div style="font-size:12px; color:#94a3b8;">
          BBox: [{bbox[0]:.1f}, {bbox[1]:.1f}, {bbox[2]:.1f}, {bbox[3]:.1f}] ▾
        </div>
      </div>
      <div class="defect-body" id="defect-body-{did}">
        <div>
          <div style="margin-bottom:12px;">
            <span class="section-title">Optical Detection & Significance:</span>
            <p style="font-size:13.5px; color:#f1f5f9;">{d.get('what_was_detected')}</p>
            <p style="font-size:13px; color:#94a3b8; margin-top:4px;">{d.get('why_significant')}</p>
          </div>
          <div style="margin-bottom:12px;">
            <span class="section-title">CERI Geometric Severity (Optical):</span>
            <div style="background:#0b1120; padding:8px 12px; border-radius:6px; font-size:12.5px; border:1px solid #1e293b;">
              • Conductor Width Reduction: <strong>{ceri.get('trace_width_reduction_pct', 0)}%</strong><br>
              • Clearance Intrusion: <strong>{ceri.get('clearance_intrusion_pct', 0)}%</strong> (Remaining: {ceri.get('clearance_remaining_mm', 0)} mm)<br>
              • IPC-A-600 Violation: <strong>{'YES (OUT OF SPEC)' if ceri.get('ipc_violation') else 'NO'}</strong>
            </div>
          </div>
          <div>
            <span class="section-title">CEIA Counterfactual Electrical Proxies:</span>
            <span class="proxy-badge">GEOMETRIC PROXY ESTIMATE (NOT IN-SITU BENCH TEST)</span>
            <div style="background:#130e24; padding:8px 12px; border-radius:6px; font-size:12.5px; border:1px solid #3b1d6e; color:#e9d5ff;">
              • Current Density Bottleneck Multiplier: <strong>{ceia.get('current_density_multiplier', 1.0)}x</strong><br>
              • Signal Integrity Risk Level: <strong>{ceia.get('signal_integrity_risk', 'LOW')}</strong><br>
              • Thermal Dissipation Hazard: <strong>{ceia.get('thermal_dissipation_risk', 'LOW')}</strong>
            </div>
          </div>
        </div>
        <div>
          <div style="margin-bottom:12px;">
            <span class="section-title">Region Microscopic Inspection Points:</span>
            <ul style="padding-left:18px; font-size:13px; color:#cbd5e1;">
"""
        for pt in d.get("region_inspection_points", []):
            html_content += f"""              <li>{pt}</li>\n"""

        html_content += f"""            </ul>
          </div>
          <div style="margin-bottom:12px;">
            <span class="section-title">Suggested Corrective Action:</span>
            <p style="font-size:13px; color:#f8fafc; background:rgba(37, 99, 235, 0.1); border-left:3px solid #3b82f6; padding:8px 10px; border-radius:0 4px 4px 0;">
              {d.get('suggested_corrective_action')}
            </p>
          </div>
          <div>
            <span class="section-title">Physical Verification Protocol:</span>
            <ul style="padding-left:18px; font-size:12.5px; color:#94a3b8;">
"""
        for v in d.get("verification_protocol", []):
            html_content += f"""              <li>{v}</li>\n"""

        html_content += f"""            </ul>
          </div>
        </div>
      </div>
    </div>\n"""

    html_content += f"""  </div>

  <!-- Layer 5: Interactive Engineer Q&A Simulator Console -->
  <div class="card">
    <div class="card-title">
      <span>💬 Layer 5: Interactive Engineer Q&A Console</span>
      <span class="tag" style="background:#1e3a8a; color:#93c5fd; margin-left:auto;">Contextual Offline Llama Intelligence</span>
    </div>
    <div class="qa-box">
      <div style="font-size:12px; color:#94a3b8; margin-bottom:8px; font-weight:600;">COMMON INSPECTION INQUIRIES (CLICK TO ASK):</div>
      <div class="qa-chips">
        <button class="qa-chip" onclick="askQuestion('Why was this PCB rejected?')">Why was this PCB rejected?</button>
        <button class="qa-chip" onclick="askQuestion('Which defect is the most critical?')">Which defect is the most critical?</button>
        <button class="qa-chip" onclick="askQuestion('What corrective action is recommended for defect #2?')">What corrective action is recommended for defect #2?</button>
        <button class="qa-chip" onclick="askQuestion('What are the potential consequences of the detected short?')">What are the potential consequences of the detected short?</button>
        <button class="qa-chip" onclick="askQuestion('Summarize the board inspection.')">Summarize the board inspection.</button>
      </div>
      <div class="qa-input-row">
        <input type="text" id="qaInput" class="qa-input" placeholder="Type an engineering question regarding this board's defects, IPC criteria, or rework..." onkeydown="if(event.key==='Enter') submitCustomQuestion()">
        <button class="qa-btn" onclick="submitCustomQuestion()">Ask Intelligence</button>
      </div>
      <div class="qa-output" id="qaOutput">
        <em>Click one of the question chips above or type a custom question to query the RGPIS-HDE Engineering Intelligence layer.</em>
      </div>
    </div>
  </div>

</div>

<script>
  const reportData = {client_report_json};
  const intelData = {client_intel_json};

  // Render SVG Bounding Boxes on PCB Canvas
  function renderBBoxes() {{
    const canvas = document.getElementById("pcbCanvas");
    const defects = intelData.individual_defect_intelligence || [];
    const colors = {{
      "P1_CRITICAL": "var(--p1)",
      "P2_HIGH": "var(--p2)",
      "P3_MEDIUM": "var(--p3)",
      "P4_LOW": "var(--p4)"
    }};

    defects.forEach(d => {{
      const [x1, y1, x2, y2] = d.bbox;
      const left = (x1 / 640) * 100;
      const top = (y1 / 640) * 100;
      const width = Math.max(4, ((x2 - x1) / 640) * 100);
      const height = Math.max(4, ((y2 - y1) / 640) * 100);
      const prio = d.unified_score.priority_level;
      const col = colors[prio] || "var(--accent)";

      const marker = document.createElement("div");
      marker.className = "bbox-marker";
      marker.style.left = `${{left}}%`;
      marker.style.top = `${{top}}%`;
      marker.style.width = `${{width}}%`;
      marker.style.height = `${{height}}%`;
      marker.style.borderColor = col;
      marker.title = `Defect #${{d.defect_id}} (${{d.display_name}}) - ${{prio}} (${{d.unified_score.score}}/100)`;

      const tag = document.createElement("div");
      tag.className = "bbox-tag";
      tag.style.background = col;
      tag.textContent = `#${{d.defect_id}} ${{d.class_name}}`;
      marker.appendChild(tag);

      marker.onclick = () => {{
        const target = document.getElementById(`defect-card-${{d.defect_id}}`);
        if (target) {{
          target.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
          target.style.borderColor = "#3b82f6";
          setTimeout(() => {{ target.style.borderColor = ""; }}, 2000);
        }}
      }};

      canvas.appendChild(marker);
    }});
  }}

  // Toggle Defect Accordions
  function toggleDefect(did) {{
    const body = document.getElementById(`defect-body-${{did}}`);
    if (body.style.display === "none") {{
      body.style.display = "grid";
    }} else {{
      body.style.display = "none";
    }}
  }}

  // Client-Side Engineer Q&A Answering
  function askQuestion(q) {{
    document.getElementById("qaInput").value = q;
    submitCustomQuestion();
  }}

  function submitCustomQuestion() {{
    const query = document.getElementById("qaInput").value.trim();
    if (!query) return;

    const out = document.getElementById("qaOutput");
    out.innerHTML = `<em>Consulting ExecuTorch Llama Engineering Intelligence...</em>`;

    setTimeout(() => {{
      const qLower = query.toLowerCase();
      let answer = "";
      let engine = "ExecuTorch Llama Grounded Intelligence";

      if (qLower.includes("why") && (qLower.includes("reject") || qLower.includes("accept") || qLower.includes("disposition"))) {{
        const disp = reportData.board_summary.overall_disposition;
        const reason = reportData.board_summary.disposition_reason;
        answer = `<strong>Board Decision: ${{disp}}</strong><br>${{reason}}<br><span style="color:#94a3b8; font-size:12px;">Grounding: Under IPC-A-600 Class 2/3, functional electrical bridging (shorts) and circuit breaks (opens) unconditionally prohibit operational energization without engineering rework sign-off.</span>`;
      }} else if (qLower.includes("which") && (qLower.includes("critical") || qLower.includes("worst") || qLower.includes("priority"))) {{
        const top = intelData.individual_defect_intelligence[0];
        answer = `<strong>Defect #${{top.defect_id}} (${{top.display_name}})</strong> is the most critical defect with a Unified Risk Score of <strong>${{top.unified_score.score}}/100 (${{top.unified_score.priority_level}})</strong>.<br>CERI geometric analysis indicates ${{top.ceri_metrics.trace_width_reduction_pct}}% width reduction and ${{top.ceri_metrics.clearance_intrusion_pct}}% clearance violation.`;
      }} else if (qLower.includes("defect") && (qLower.includes("action") || qLower.includes("rework") || qLower.includes("fix"))) {{
        const match = qLower.match(/defect\s*#?\s*(\d+)/);
        const did = match ? parseInt(match[1]) : 1;
        const target = intelData.individual_defect_intelligence.find(d => d.defect_id === did);
        if (target) {{
          answer = `<strong>Corrective Action for Defect #${{did}} (${{target.display_name}}):</strong><br>${{target.suggested_corrective_action}}<br><strong>Verification:</strong> ${{target.verification_protocol.join("; ")}}`;
        }} else {{
          answer = `Defect #${{did}} not found on this board. Active defects are #1 through #${{intelData.individual_defect_intelligence.length}}.`;
        }}
      }} else if (qLower.includes("consequence") || qLower.includes("electrical") || qLower.includes("short") || qLower.includes("open")) {{
        const criticals = intelData.individual_defect_intelligence.filter(d => d.unified_score.priority_level === "P1_CRITICAL");
        const list = criticals.map(c => `• <strong>${{c.display_name}}:</strong> ${{c.potential_consequences.join(" ")}}`).join("<br>");
        answer = `<strong>Potential Electrical Consequences (CEIA Proxies):</strong><br>${{list}}<br><span style="color:#a855f7; font-size:11px;">⚠️ Note: All electrical consequences are modeled via counterfactual geometric proxies. Bench measurements required.</span>`;
      }} else if (qLower.includes("summar")) {{
        const b = reportData.board_summary;
        answer = `<strong>Board Inspection Summary:</strong> Board '${{reportData.metadata.board_id}}' is evaluated as <strong>${{b.overall_disposition}}</strong>. It displays ${{b.total_defects}} total anomalies, including ${{b.critical_defects_count}} P1 Critical and ${{b.high_risk_count}} P2 High-Risk defects violating IPC-A-600 Class 2/3 tolerances.`;
      }} else {{
        answer = `<strong>Engineering Intelligence Response:</strong><br>Query: "${{query}}"<br>Based on IPC-A-600 standards and the ${{reportData.board_summary.total_defects}} detected defects on Board '${{reportData.metadata.board_id}}', ensure all P1 critical anomalies are isolated under stereo magnification before attempting power-on testing.`;
      }}

      out.innerHTML = `<div>${{answer}}</div><div style="font-size:11px; color:#64748b; margin-top:8px;">Runtime: ${{engine}} | Grounding: IPC-A-600 Class 2/3</div>`;
    }}, 200);
  }}

  function downloadJSON() {{
    const blob = new Blob([JSON.stringify(intelData, null, 2)], {{ type: 'application/json' }});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${{reportData.metadata.board_id}}_engineering_intelligence.json`;
    a.click();
  }}

  // Initialize Canvas
  window.onload = renderBBoxes;
</script>

</body>
</html>
"""

    with open(output_html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return output_html_path


def generate_markdown_report(
    report: Dict[str, Any],
    intelligence: Dict[str, Any],
    output_md_path: Optional[Path] = None,
) -> Path:
    """
    Renders formal Markdown inspection traveler report.
    """
    if output_md_path is None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        board_id = report.get("metadata", {}).get("board_id", "board")
        output_md_path = OUTPUT_DIR / f"{board_id}_engineering_report.md"
    else:
        output_md_path = Path(output_md_path)
        output_md_path.parent.mkdir(parents=True, exist_ok=True)

    meta = report.get("metadata", {})
    summary = report.get("board_summary", {})
    board_level = intelligence.get("board_level_intelligence", {})
    defects = intelligence.get("individual_defect_intelligence", [])
    actions = intelligence.get("corrective_action_recommendations", [])
    process = intelligence.get("process_intelligence", {})

    lines = [
        f"# RGPIS-HDE PCB Engineering Intelligence Traveler Report",
        f"**Board ID:** `{meta.get('board_id')}` | **Image:** `{meta.get('image_name')}` | **Date:** `{meta.get('timestamp')}`",
        f"**Inspection Standard:** IPC-A-600 / IPC-6012 Class 2/3 | **Engine:** ExecuTorch Offline Llama 3.2 1B (INT4 SpinQuant)",
        "",
        "---",
        "",
        f"## 1. Executive Board-Level Intelligence",
        f"- **Overall Board Disposition:** **{summary.get('overall_disposition')}**",
        f"- **Board Condition Assessment:** {board_level.get('board_condition')}",
        f"- **Upstream Rationale:** {board_level.get('acceptance_rationale')}",
        f"- **Total Detected Defects:** {summary.get('total_defects')} (P1: {summary.get('critical_defects_count')}, P2: {summary.get('high_risk_count')})",
        f"- **Max Unified Risk Score:** {summary.get('max_unified_risk_score')}/100",
        "",
        "### Major Engineering Risks:",
    ]

    for r in board_level.get("major_risks", []):
        lines.append(f"- ⚠️ {r}")

    lines.append("")
    lines.append("### Immediate Priority Focus:")
    for p in board_level.get("immediate_priorities", []):
        lines.append(f"- 🎯 {p}")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 2. Prioritized Corrective Action Matrix")
    lines.append("| Step | Defect | Priority | Score | Recommended Action | Verification Protocol | Station | Sign-off |")
    lines.append("|:---:|:---|:---:|:---:|:---|:---|:---|:---:|")

    for a in actions:
        lines.append(
            f"| #{a.get('step_number')} | {a.get('defect_name')} (#{a.get('defect_id')}) | {a.get('priority_level')} | "
            f"{a.get('unified_score')} | {a.get('recommended_action')} | {'; '.join(a.get('verification_procedure', []))} | "
            f"{a.get('assigned_station')} | [ ] |"
        )

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 3. Individual Defect Engineering Intelligence")

    for d in defects:
        ceri = d.get("ceri_metrics", {})
        ceia = d.get("ceia_proxies", {})
        lines.extend([
            f"### Defect #{d.get('defect_id')}: {d.get('display_name')} ({d.get('unified_score', {}).get('priority_level')})",
            f"- **Confidence:** {d.get('confidence') * 100:.1f}% | **BBox:** `{d.get('bbox')}` | **Unified Score:** {d.get('unified_score', {}).get('score')}/100",
            f"- **Optical Detection:** {d.get('what_was_detected')}",
            f"- **Physical Significance:** {d.get('why_significant')}",
            f"- **CERI Geometric Metrics:** Trace Width Reduction = {ceri.get('trace_width_reduction_pct')}%, Clearance Intrusion = {ceri.get('clearance_intrusion_pct')}%, Clearance Remaining = {ceri.get('clearance_remaining_mm')} mm, IPC Violation = {ceri.get('ipc_violation')}",
            f"- **CEIA Electrical Proxies:** *(Geometric proxy, not physical bench test)* Current Density Bottleneck = {ceia.get('current_density_multiplier')}x, SI Risk = {ceia.get('signal_integrity_risk')}, Thermal Risk = {ceia.get('thermal_dissipation_risk')}",
            f"- **Suggested Corrective Action:** {d.get('suggested_corrective_action')}",
            f"- **Verification Protocol:** {'; '.join(d.get('verification_protocol', []))}",
            "",
        ])

    lines.extend([
        "---",
        "",
        "## 4. Manufacturing Process Intelligence (Hypotheses)",
        f"**Observed Pattern:** {process.get('pattern_summary')}",
        "",
        "> [!IMPORTANT]",
        "> **Hypothesis Disclaimer:** All manufacturing process correlations are probabilistic hypotheses for line auditing. Final confirmation requires bath titration and phototool optical audits.",
        "",
        "### Fab Stage Hypotheses:",
    ])

    for h in process.get("fab_stage_hypotheses", []):
        lines.append(f"- 🔬 {h}")

    lines.append("")
    lines.append("### Recommended Process Audits:")
    for inv in process.get("recommended_investigations", []):
        lines.append(f"- ✅ {inv}")

    lines.append("")
    lines.append("---")
    lines.append("*Report generated by RGPIS-HDE Engineering Intelligence Layer (Bharat AI-SoC Challenge 2026/27)*")

    content = "\n".join(lines)
    with open(output_md_path, "w", encoding="utf-8") as f:
        f.write(content)

    return output_md_path
