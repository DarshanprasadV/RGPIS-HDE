#!/usr/bin/env python3
"""
Builds a standalone macOS Desktop Application bundle: RGPIS-HDE.app
Allows launching the entire PCB Defect Detection & Engineering Intelligence
application with a single double-click in Finder (no terminal required).
"""

import os
import shutil
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parent
APP_NAME = "RGPIS-HDE"
APP_BUNDLE = PROJECT_ROOT / f"{APP_NAME}.app"
CONTENTS_DIR = APP_BUNDLE / "Contents"
MACOS_DIR = CONTENTS_DIR / "MacOS"
RESOURCES_DIR = CONTENTS_DIR / "Resources"


def create_app_icon(icns_path: Path) -> None:
    """Generates a custom PCB-themed macOS .icns application icon."""
    # Render base 1024x1024 icon
    size = 1024
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Rounded square dark-navy background
    margin = 64
    radius = 180
    draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=radius,
        fill=(11, 18, 34, 255),
        outline=(59, 130, 246, 255),
        width=20,
    )

    # Subtle PCB trace lines (emerald/cyan)
    trace_color = (16, 185, 129, 230)
    pad_color = (56, 189, 248, 255)
    defect_color = (239, 68, 68, 255)

    # Draw stylized PCB traces
    draw.line([(200, 320), (420, 320), (540, 440), (800, 440)], fill=trace_color, width=28)
    draw.line([(220, 700), (440, 700), (580, 560), (800, 560)], fill=trace_color, width=28)
    draw.line([(320, 200), (320, 500), (420, 600)], fill=trace_color, width=24)

    # Draw PCB pads (rings)
    for cx, cy in [(200, 320), (800, 440), (220, 700), (800, 560), (320, 200)]:
        draw.ellipse([cx - 42, cy - 42, cx + 42, cy + 42], fill=pad_color)
        draw.ellipse([cx - 18, cy - 18, cx + 18, cy + 18], fill=(11, 18, 34, 255))

    # Draw red AI detection bounding box highlight over center trace
    draw.rounded_rectangle(
        [450, 360, 640, 530],
        radius=16,
        outline=defect_color,
        width=18,
    )
    # Crosshair dot inside detection box
    draw.ellipse([530, 430, 560, 460], fill=defect_color)

    # Save directly as macOS ICNS using Pillow
    img.save(icns_path, format="ICNS")


def build_app() -> None:
    if APP_BUNDLE.exists():
        shutil.rmtree(APP_BUNDLE)

    MACOS_DIR.mkdir(parents=True, exist_ok=True)
    RESOURCES_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Create Info.plist
    info_plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>{APP_NAME}</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundleIdentifier</key>
    <string>com.rgpis.hde.inspector</string>
    <key>CFBundleName</key>
    <string>RGPIS-HDE PCB Inspector</string>
    <key>CFBundleDisplayName</key>
    <string>RGPIS-HDE PCB Inspector</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSMinimumSystemVersion</key>
    <string>12.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
"""
    (CONTENTS_DIR / "Info.plist").write_text(info_plist, encoding="utf-8")

    # 2. Generate AppIcon.icns
    icns_path = RESOURCES_DIR / "AppIcon.icns"
    create_app_icon(icns_path)

    # 3. Create executable launcher script
    launcher_script = f"""#!/bin/bash
# RGPIS-HDE Desktop Application Launcher

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CANDIDATE_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
DEFAULT_ROOT="{PROJECT_ROOT}"

if [ -f "$CANDIDATE_ROOT/llama_advisory/web_app.py" ]; then
    PROJECT_ROOT="$CANDIDATE_ROOT"
else
    PROJECT_ROOT="$DEFAULT_ROOT"
fi

PYTHON_BIN="$PROJECT_ROOT/llama_advisory/venv/bin/python"
APP_SCRIPT="$PROJECT_ROOT/llama_advisory/web_app.py"
LOG_FILE="/tmp/rgpis_hde_app.log"
PORT=5050
URL="http://localhost:$PORT"

if [ ! -x "$PYTHON_BIN" ]; then
    osascript -e 'display alert "RGPIS-HDE Error" message "Python environment not found at '"$PYTHON_BIN"'." as critical'
    exit 1
fi

# Check if server is already running
if ! curl -s "$URL/api/health" >/dev/null 2>&1; then
    osascript -e 'display notification "Starting YOLO26n & Engineering Intelligence Engine..." with title "RGPIS-HDE PCB Inspector"'
    cd "$PROJECT_ROOT" || exit 1
    nohup "$PYTHON_BIN" "$APP_SCRIPT" "$PORT" > "$LOG_FILE" 2>&1 &

    # Wait up to 30 seconds for server to become healthy
    for i in $(seq 1 60); do
        if curl -s "$URL/api/health" >/dev/null 2>&1; then
            break
        fi
        sleep 0.5
    done
fi

if ! curl -s "$URL/api/health" >/dev/null 2>&1; then
    osascript -e 'display alert "RGPIS-HDE Startup Failed" message "Server failed to start. Check logs at /tmp/rgpis_hde_app.log" as critical'
    exit 1
fi

# Launch in standalone Chrome App Window if available, otherwise default browser
if [ -d "/Applications/Google Chrome.app" ]; then
    open -na "Google Chrome" --args --app="$URL" --window-size=1360,900
else
    open "$URL"
fi
"""
    exec_path = MACOS_DIR / APP_NAME
    exec_path.write_text(launcher_script, encoding="utf-8")
    os.chmod(exec_path, 0o755)

    print(f"✅ Successfully built macOS Application: {APP_BUNDLE}")


if __name__ == "__main__":
    build_app()
