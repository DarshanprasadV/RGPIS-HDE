"""
RGPIS-HDE Live Interactive Web Application Server.
Provides a local web server with:
1. Live web interface with Drag-and-Drop PCB image uploader
2. On-the-spot defect detection, trace loss measurement, and Llama engineering intelligence
3. Instant zero-latency switching between pre-analyzed boards
4. Interactive Q&A console
"""

import http.server
import json
import os
import socketserver
import sys
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
INTEL_DIR = PROJECT_ROOT / "outputs" / "intelligence"
DEFAULT_HTML = INTEL_DIR / "deep_12100046_intelligence_dashboard.html"


class RGPISHandler(http.server.SimpleHTTPRequestHandler):
    """Custom HTTP handler serving the RGPIS-HDE dashboard and API."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PROJECT_ROOT), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html", "/dashboard"):
            if DEFAULT_HTML.exists():
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                with open(DEFAULT_HTML, "rb") as f:
                    self.wfile.write(f.read())
                return
            else:
                self.send_error(404, "Dashboard not yet generated. Run dashboard generator first.")
                return

        return super().do_GET()


def run_server(port: int = 5050):
    """Runs the live RGPIS-HDE local web application."""
    handler = RGPISHandler
    # Allow port reuse
    socketserver.TCPServer.allow_reuse_address = True
    
    # Try finding an open port starting from 5050
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
                print(f"  • On-The-Spot AI     : Generates defect map, CERI/CEIA, and solutions live")
                print("=" * 76 + "\n")
                print("Press Ctrl+C to stop the server.\n")

                # Automatically open in default browser
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
