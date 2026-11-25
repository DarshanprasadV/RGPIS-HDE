"""
RGPIS-HDE Live Interactive Web Application Server.
Provides a local web server with:
1. Live web interface with Drag-and-Drop PCB image uploader
2. On-the-spot defect detection via YOLO26n, trace loss measurement (CERI),
   physical current density (CEIA in A·m⁻²), and Llama engineering intelligence
3. Instant zero-latency switching between pre-analyzed boards
4. Interactive Q&A console
"""

import base64
import http.server
import json
import os
import socketserver
import sys
import time
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from predict import PCBDefectDetector
from llama_advisory.unified_pipeline_bridge import build_unified_report
from llama_advisory.engineering_intelligence import EngineeringIntelligenceEngine
from llama_advisory.inspection_logger import (
    log_inspection,
    get_inspection_history,
    get_inspection_stats,
    clear_inspection_history,
    delete_inspection,
    seed_benchmark_inspections_if_empty,
    CSV_LOG_PATH,
    JSONL_LOG_PATH,
)

INTEL_DIR = PROJECT_ROOT / "outputs" / "intelligence"
DEFAULT_HTML = INTEL_DIR / "deep_12100046_intelligence_dashboard.html"

# Global cached inference engines for sub-second live response
_DETECTOR = None
_INTEL_ENGINE = None


def get_detector() -> PCBDefectDetector:
    global _DETECTOR
    if _DETECTOR is None:
        print("  [INIT] Loading YOLO26n PCB Defect Detector into memory...")
        _DETECTOR = PCBDefectDetector(conf_threshold=0.35)
        print("  [INIT] YOLO26n Detector ready.")
    return _DETECTOR


def get_engine() -> EngineeringIntelligenceEngine:
    global _INTEL_ENGINE
    if _INTEL_ENGINE is None:
        print("  [INIT] Initializing Engineering Intelligence Engine...")
        _INTEL_ENGINE = EngineeringIntelligenceEngine()
        print("  [INIT] Engineering Intelligence Engine ready.")
    return _INTEL_ENGINE


def validate_pcb_domain(img: np.ndarray) -> tuple[bool, str, str]:
    """
    Validates whether an input frame or upload belongs to the PCB domain.
    Rejects human faces/skin, empty backgrounds, and blurry/featureless scenes.
    Distinguishes genuine PCB boards (including copper tracks, gold ENIG, and yellow FR4)
    from human faces or skin by prioritizing geometric circuit trace edge energy.
    
    Returns: (is_pcb: bool, reason_code: str, user_friendly_message: str)
    """
    if img is None or img.size == 0:
        return False, "invalid_image", "Failed to decode camera or upload frame."

    h, w = img.shape[:2]
    total_pixels = h * w

    # 1. Circuit Structure & Trace Edge Energy (Canny)
    # Genuine PCBs feature dense etched copper tracks, solder pads, drill vias, or SMT traces.
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    edge_density = (np.count_nonzero(edges) / total_pixels) * 100.0

    # 2. Scene Contrast / Dynamic Range Check
    std_dev = float(np.std(gray))
    if std_dev < 10.0:
        return False, "low_contrast", (
            f"Scene contrast too low (std={std_dev:.1f}). "
            "Adjust lighting or move the circuit board closer to the camera lens."
        )

    # 3. Biological Skin Tone Detection via combined YCrCb + HSV saturation
    ycrcb = cv2.cvtColor(img, cv2.COLOR_BGR2YCrCb)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    skin_ycrcb = cv2.inRange(ycrcb, np.array([0, 135, 80]), np.array([255, 175, 125]))
    skin_hsv = cv2.inRange(hsv, np.array([0, 30, 30]), np.array([25, 255, 255]))
    skin_mask = cv2.bitwise_and(skin_ycrcb, skin_hsv)

    total_skin_pct = (np.count_nonzero(skin_mask) / total_pixels) * 100.0

    # Optical center inspection zone (inner 60% x 60% of frame)
    cx1, cy1 = int(w * 0.20), int(h * 0.20)
    cx2, cy2 = int(w * 0.80), int(h * 0.80)
    center_patch = skin_mask[cy1:cy2, cx1:cx2]
    center_area = max(1, (cx2 - cx1) * (cy2 - cy1))
    center_skin_pct = (np.count_nonzero(center_patch) / center_area) * 100.0

    # Real human faces or bodies have high skin percentage AND lack circuit track edges (< 1.0%).
    # On real PCBs, warm copper traces, gold plating, and FR4 laminate fall in the YCrCb chrominance range,
    # but exhibit high edge density (typically > 1.0% to 15%). We must NEVER reject real circuit traces!
    if (center_skin_pct > 40.0 or total_skin_pct > 50.0) and edge_density < 1.0:
        return False, "human_subject_detected", (
            f"Human subject or face detected ({center_skin_pct:.1f}% skin signature, {edge_density:.2f}% edge density). "
            "Defect analysis paused. Please align a Printed Circuit Board inside the optical reticle."
        )

    # Minimum circuit trace edge requirement (filters out blank/uniform walls, empty desks, or dark voids)
    if edge_density < 0.25:
        return False, "low_circuit_density", (
            f"Insufficient circuit trace structure detected ({edge_density:.2f}% edge density). "
            "Ensure the PCB is aligned inside the optical reticle under adequate lighting."
        )

    return True, "valid_pcb", f"PCB domain verified (Trace edges: {edge_density:.2f}%, Center skin: {center_skin_pct:.1f}%)"


class RGPISHandler(http.server.SimpleHTTPRequestHandler):
    """Custom HTTP handler serving the RGPIS-HDE dashboard and API."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PROJECT_ROOT), **kwargs)

    def _set_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self._set_cors_headers()
        self.end_headers()

    def _send_json(self, data: dict, status_code: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._set_cors_headers()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html", "/dashboard"):
            if DEFAULT_HTML.exists():
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self._set_cors_headers()
                self.end_headers()
                with open(DEFAULT_HTML, "rb") as f:
                    self.wfile.write(f.read())
                return
            else:
                self.send_error(404, "Dashboard not yet generated. Run dashboard generator first.")
                return

        if parsed.path == "/api/health":
            self._send_json({"status": "healthy", "service": "RGPIS-HDE Live Intelligence Server"})
            return

        # ----------------------------------------------------------------------
        # Inspection History & Audit Trail Endpoints
        # ----------------------------------------------------------------------
        if parsed.path == "/api/inspections":
            history = get_inspection_history(limit=250)
            stats = get_inspection_stats()
            self._send_json({"status": "success", "history": history, "stats": stats})
            return

        if parsed.path == "/api/inspections/stats":
            stats = get_inspection_stats()
            self._send_json({"status": "success", "stats": stats})
            return

        if parsed.path in ("/api/inspections/export/csv", "/api/inspections/export"):
            q = parsed.query.lower()
            if "format=json" in q or "format=jsonl" in q:
                if JSONL_LOG_PATH.exists():
                    with open(JSONL_LOG_PATH, "rb") as f:
                        data = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/x-jsonlines; charset=utf-8")
                    self.send_header("Content-Disposition", 'attachment; filename="rgpis_inspection_history.jsonl"')
                    self._set_cors_headers()
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
            else:
                if CSV_LOG_PATH.exists():
                    with open(CSV_LOG_PATH, "rb") as f:
                        data = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/csv; charset=utf-8")
                    self.send_header("Content-Disposition", 'attachment; filename="rgpis_inspection_log.csv"')
                    self._set_cors_headers()
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return

        return super().do_GET()

    def do_DELETE(self):
        parsed = urlparse(self.path)
        # e.g. DELETE /api/inspections/INSP-1234
        if parsed.path.startswith("/api/inspections/"):
            target_id = parsed.path.split("/")[-1].strip()
            if target_id and target_id not in ("delete", "clear"):
                success = delete_inspection(target_id)
                new_stats = get_inspection_stats()
                self._send_json({
                    "status": "success" if success else "error",
                    "deleted_id": target_id,
                    "stats": new_stats,
                    "message": f"Record {target_id} deleted."
                })
                return
        self._send_json({"status": "error", "message": "Endpoint not found or invalid ID."}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)

        # Clear all inspection logs
        if parsed.path == "/api/inspections/clear":
            success = clear_inspection_history()
            self._send_json({"status": "success" if success else "error", "message": "Inspection history cleared."})
            return

        # Delete single inspection log entry
        if parsed.path == "/api/inspections/delete":
            try:
                content_len = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_len) if content_len > 0 else b"{}"
                req_data = json.loads(body.decode("utf-8")) if body else {}
                target_id = req_data.get("inspection_id", "").strip()
                if not target_id:
                    self._send_json({"status": "error", "message": "Missing inspection_id parameter."}, 400)
                    return
                success = delete_inspection(target_id)
                new_stats = get_inspection_stats()
                self._send_json({
                    "status": "success" if success else "error",
                    "deleted_id": target_id,
                    "stats": new_stats,
                    "message": f"Inspection log {target_id} deleted successfully." if success else "Failed to delete record."
                })
            except Exception as e:
                self._send_json({"status": "error", "message": str(e)}, 500)
            return

        if parsed.path == "/api/analyze":
            try:
                content_len = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_len)
                req_data = json.loads(body.decode("utf-8"))

                img_data_str = req_data.get("image_b64", "")
                filename = req_data.get("filename", "uploaded_pcb.jpg")
                stem = Path(filename).stem

                if "," in img_data_str:
                    img_data_str = img_data_str.split(",", 1)[1]

                raw_bytes = base64.b64decode(img_data_str)
                nparr = np.frombuffer(raw_bytes, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                if img is None:
                    self._send_json({"status": "error", "message": "Failed to decode image."}, 400)
                    return

                data_url = req_data.get("image_b64", "")
                if not data_url.startswith("data:"):
                    data_url = f"data:image/jpeg;base64,{img_data_str}"

                # 0. Gatekeeper: PCB Domain Validation
                is_pcb, reason_code, domain_msg = validate_pcb_domain(img)
                if not is_pcb:
                    print(f"[LIVE API] Non-PCB input filtered: {reason_code} - {domain_msg}")
                    logged = log_inspection(
                        {},
                        image_name=filename,
                        board_id=stem,
                        mode="LIVE_CAMERA" if ("live" in filename.lower() or "cam" in filename.lower()) else "FILE_UPLOAD",
                        duration_seconds=0.05,
                        status="not_a_pcb",
                    )
                    self._send_json({
                        "status": "not_a_pcb",
                        "reason": reason_code,
                        "message": domain_msg,
                        "board_id": stem,
                        "image_name": filename,
                        "image_b64": data_url,
                        "inspection_id": logged.get("inspection_id"),
                        "logged_record": logged,
                    }, 200)
                    return

                print(f"\n[LIVE API] Received PCB '{filename}' ({img.shape[1]}x{img.shape[0]} px). Running detection...")
                t0 = time.time()

                # 1. Run YOLO Defect Detector
                detector = get_detector()
                det_dict = detector.detect(img)
                det_dict["image_name"] = filename

                # 2. Build Unified Report (CERI trace loss, CEIA current density in A·m⁻², Unified Risk Score)
                rep = build_unified_report(det_dict)
                rep["metadata"]["board_id"] = stem
                rep["metadata"]["image_name"] = filename

                # 3. Generate 5-layer engineering intelligence
                engine = get_engine()
                intel = engine.analyze_board(rep, use_llama=False)
                intel["metadata"]["board_id"] = stem
                intel["metadata"]["image_name"] = filename

                dur = time.time() - t0
                total_defects = intel.get("board_summary", {}).get("total_defects", len(intel.get("individual_defect_intelligence", [])))
                print(f"[LIVE API] Successfully analyzed '{filename}' in {dur:.2f}s — Found {total_defects} defect(s).")

                # 4. Log to persistent audit trail (JSONL + CSV)
                logged = log_inspection(
                    intel,
                    image_name=filename,
                    board_id=stem,
                    mode="LIVE_CAMERA" if ("live" in filename.lower() or "cam" in filename.lower()) else "FILE_UPLOAD",
                    duration_seconds=dur,
                    status="success",
                )

                data_url = req_data.get("image_b64", "")
                if not data_url.startswith("data:"):
                    data_url = f"data:image/jpeg;base64,{img_data_str}"

                resp = {
                    "status": "success",
                    "inspection_id": logged.get("inspection_id"),
                    "board_id": stem,
                    "image_name": filename,
                    "total_defects": total_defects,
                    "intelligence": intel,
                    "image_b64": data_url,
                    "inference_duration_seconds": round(dur, 2),
                    "logged_record": logged,
                }
                self._send_json(resp, 200)
            except Exception as e:
                import traceback
                traceback.print_exc()
                self._send_json({"status": "error", "message": str(e)}, 500)
            return

        return super().do_POST()


def run_server(port: int = 5050):
    """Runs the live RGPIS-HDE local web application."""
    # Pre-warm models so the first user drop is instantaneous
    print("\n" + "=" * 76)
    print("  🚀 PRE-WARMING RGPIS-HDE INFERENCE ENGINE...")
    get_detector()
    get_engine()
    seed_benchmark_inspections_if_empty()
    print("  📋 Inspection Audit Logging System Active (outputs/logs/).")
    print("=" * 76)

    handler = RGPISHandler
    socketserver.TCPServer.allow_reuse_address = True

    for p in range(port, port + 10):
        try:
            with socketserver.TCPServer(("", p), handler) as httpd:
                url = f"http://localhost:{p}"
                print("\n" + "=" * 76)
                print("  🚀 RGPIS-HDE LIVE ENGINEERING INTELLIGENCE WEB APP")
                print("  Bharat AI-SoC Challenge 2026/27 | Interactive Edge Inspection")
                print("=" * 76)
                print(f"  • Web App Running at : {url}")
                print(f"  • Drag & Drop Images : Drop any PCB image directly into the browser")
                print(f"  • On-The-Spot AI     : Live YOLO26n + CERI/CEIA (A·m⁻²) + Llama solutions")
                print("=" * 76 + "\n")
                print("Press Ctrl+C to stop the server.\n")

                try:
                    webbrowser.open(url)
                except Exception:
                    pass

                httpd.serve_forever()
                break
        except OSError:
            continue


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5050
    run_server(port)
