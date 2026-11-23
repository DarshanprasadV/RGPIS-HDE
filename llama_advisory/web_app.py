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

INTEL_DIR = PROJECT_ROOT / "outputs" / "intelligence"
DEFAULT_HTML = INTEL_DIR / "deep_12100046_intelligence_dashboard.html"

# Global cached inference engines for sub-second live response
_DETECTOR = None
_INTEL_ENGINE = None


def get_detector() -> PCBDefectDetector:
    global _DETECTOR
    if _DETECTOR is None:
        print("  [INIT] Loading YOLO26n PCB Defect Detector into memory...")
        _DETECTOR = PCBDefectDetector()
        print("  [INIT] YOLO26n Detector ready.")
    return _DETECTOR


def get_engine() -> EngineeringIntelligenceEngine:
    global _INTEL_ENGINE
    if _INTEL_ENGINE is None:
        print("  [INIT] Initializing Engineering Intelligence Engine...")
        _INTEL_ENGINE = EngineeringIntelligenceEngine()
        print("  [INIT] Engineering Intelligence Engine ready.")
    return _INTEL_ENGINE


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

        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
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

                data_url = req_data.get("image_b64", "")
                if not data_url.startswith("data:"):
                    data_url = f"data:image/jpeg;base64,{img_data_str}"

                resp = {
                    "status": "success",
                    "board_id": stem,
                    "image_name": filename,
                    "total_defects": total_defects,
                    "intelligence": intel,
                    "image_b64": data_url,
                    "inference_duration_seconds": round(dur, 2),
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
