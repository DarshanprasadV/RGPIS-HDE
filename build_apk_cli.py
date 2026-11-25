#!/usr/bin/env python3
"""
build_apk_cli.py - Automated CLI Android APK Builder for RGPIS-HDE
Downloads minimal portable toolchain (JDK 17, Android SDK cmdline-tools, Gradle)
into ~/.android-cli-tools and compiles mobile_app into an offline APK.
"""

import os
import sys
import shutil
import subprocess
import urllib.request
import zipfile
import tarfile
from pathlib import Path

TOOLCHAIN_DIR = Path.home() / ".android-cli-tools"
JDK_DIR = TOOLCHAIN_DIR / "jdk17"
SDK_DIR = TOOLCHAIN_DIR / "sdk"
GRADLE_DIR = TOOLCHAIN_DIR / "gradle"
PROJECT_ROOT = Path(__file__).resolve().parent
MOBILE_APP_DIR = PROJECT_ROOT / "mobile_app"
OUTPUT_APK = PROJECT_ROOT / "outputs" / "RGPIS-HDE-inspector.apk"

JDK_URL = "https://api.adoptium.net/v3/binary/latest/17/ga/mac/aarch64/jdk/hotspot/normal/eclipse"
CMDLINE_TOOLS_URL = "https://dl.google.com/android/repository/commandlinetools-mac-11076708_latest.zip"
GRADLE_URL = "https://services.gradle.org/distributions/gradle-8.9-bin.zip"


def download_file(url: str, dest: Path, desc: str):
    if dest.exists() and dest.stat().st_size > 1000:
        print(f"  [CACHE] {desc} already downloaded ({dest.stat().st_size // (1024*1024)} MB).")
        return
    print(f"  [DOWNLOAD] Downloading {desc}...")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp, open(dest, "wb") as out:
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        while True:
            chunk = resp.read(1024 * 512)
            if not chunk:
                break
            out.write(chunk)
            downloaded += len(chunk)
            if total > 0:
                pct = (downloaded / total) * 100
                print(f"\r    {pct:.1f}% ({downloaded // (1024*1024)} MB / {total // (1024*1024)} MB)", end="", flush=True)
        print()
    print(f"  [DONE] {desc} saved to {dest}")


def setup_jdk():
    # Find java binary if already extracted
    java_bin = None
    for p in JDK_DIR.glob("**/bin/java"):
        if p.is_file() and os.access(p, os.X_OK):
            java_bin = p
            break
    if java_bin:
        java_home = java_bin.parent.parent
        if (java_home / "Contents" / "Home").exists():
            java_home = java_home / "Contents" / "Home"
        print(f"  [JDK] Found existing JDK 17 at: {java_home}")
        return java_home

    tar_path = TOOLCHAIN_DIR / "jdk17.tar.gz"
    download_file(JDK_URL, tar_path, "Adoptium OpenJDK 17 (arm64)")
    print("  [EXTRACT] Extracting JDK 17...")
    JDK_DIR.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_path, "r:gz") as tar:
        tar.extractall(JDK_DIR)
    
    for p in JDK_DIR.glob("**/bin/java"):
        if p.is_file() and os.access(p, os.X_OK):
            java_home = p.parent.parent
            if (java_home / "Contents" / "Home").exists():
                java_home = java_home / "Contents" / "Home"
            print(f"  [JDK] Successfully configured JDK 17: {java_home}")
            return java_home
    raise RuntimeError("Could not find java binary in extracted JDK")


def setup_cmdline_tools():
    cmdline_latest = SDK_DIR / "cmdline-tools" / "latest" / "bin" / "sdkmanager"
    if cmdline_latest.exists() and os.access(cmdline_latest, os.X_OK):
        print(f"  [SDK] Found existing sdkmanager at: {cmdline_latest}")
        return cmdline_latest

    zip_path = TOOLCHAIN_DIR / "cmdline-tools.zip"
    download_file(CMDLINE_TOOLS_URL, zip_path, "Android Command-line Tools")
    print("  [EXTRACT] Extracting Android cmdline-tools...")
    temp_extract = TOOLCHAIN_DIR / "temp_cmdline"
    shutil.rmtree(temp_extract, ignore_errors=True)
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(temp_extract)

    # Standard SDK layout requires: <sdk>/cmdline-tools/latest/...
    latest_dir = SDK_DIR / "cmdline-tools" / "latest"
    latest_dir.mkdir(parents=True, exist_ok=True)
    src_dir = temp_extract / "cmdline-tools"
    for item in src_dir.iterdir():
        dest = latest_dir / item.name
        if dest.exists():
            if dest.is_dir():
                shutil.rmtree(dest)
            else:
                dest.unlink()
        shutil.move(str(item), str(dest))
    shutil.rmtree(temp_extract, ignore_errors=True)
    print(f"  [SDK] Installed cmdline-tools to {latest_dir}")
    return latest_dir / "bin" / "sdkmanager"


def setup_gradle():
    for p in GRADLE_DIR.glob("**/bin/gradle"):
        if p.is_file() and os.access(p, os.X_OK):
            print(f"  [GRADLE] Found existing Gradle binary at: {p}")
            return p

    zip_path = TOOLCHAIN_DIR / "gradle.zip"
    download_file(GRADLE_URL, zip_path, "Gradle 8.9")
    print("  [EXTRACT] Extracting Gradle...")
    GRADLE_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(GRADLE_DIR)

    for p in GRADLE_DIR.glob("**/bin/gradle"):
        if p.is_file() and os.access(p, os.X_OK):
            print(f"  [GRADLE] Successfully installed Gradle at: {p}")
            return p
    raise RuntimeError("Could not find gradle binary in extracted Gradle")


def install_android_packages(sdkmanager: Path, java_home: Path):
    env = os.environ.copy()
    env["JAVA_HOME"] = str(java_home)
    env["ANDROID_HOME"] = str(SDK_DIR)
    env["PATH"] = f"{java_home}/bin:{env.get('PATH', '')}"

    # Auto-accept licenses
    print("  [SDK] Accepting Android SDK licenses...")
    p = subprocess.Popen(
        [str(sdkmanager), "--licenses", f"--sdk_root={SDK_DIR}"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
        text=True,
    )
    p.communicate(input="y\n" * 20)

    # Check if platform-34 is already installed
    plat_34 = SDK_DIR / "platforms" / "android-34"
    build_tools = SDK_DIR / "build-tools" / "34.0.0"
    if not (plat_34.exists() and build_tools.exists()):
        print("  [SDK] Installing Android Platform 34 and Build-Tools 34.0.0...")
        cmd = [
            str(sdkmanager),
            f"--sdk_root={SDK_DIR}",
            "platforms;android-34",
            "build-tools;34.0.0",
            "platform-tools",
        ]
        res = subprocess.run(cmd, env=env, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"sdkmanager failed with code {res.returncode}")
    else:
        print("  [SDK] Android Platform 34 & Build-tools 34.0.0 already present.")


def build_apk(gradle_bin: Path, java_home: Path):
    env = os.environ.copy()
    env["JAVA_HOME"] = str(java_home)
    env["ANDROID_HOME"] = str(SDK_DIR)
    env["PATH"] = f"{java_home}/bin:{env.get('PATH', '')}"

    # Write local.properties for the Android project
    local_props = MOBILE_APP_DIR / "local.properties"
    local_props.write_text(f"sdk.dir={SDK_DIR}\n", encoding="utf-8")

    # Ensure compileSdk and targetSdk are 34 for maximum compatibility
    app_build_gradle = MOBILE_APP_DIR / "app" / "build.gradle.kts"
    content = app_build_gradle.read_text(encoding="utf-8")
    content = content.replace("compileSdk = 35", "compileSdk = 34")
    content = content.replace("targetSdk = 35", "targetSdk = 34")
    app_build_gradle.write_text(content, encoding="utf-8")

    print("\n  [BUILD] Compiling Android APK with Gradle (assembleDebug)...")
    cmd = [str(gradle_bin), "assembleDebug", "--no-daemon", "--stacktrace"]
    res = subprocess.run(cmd, cwd=str(MOBILE_APP_DIR), env=env)
    if res.returncode != 0:
        raise RuntimeError(f"Gradle build failed with exit code {res.returncode}")

    # Locate generated APK
    apk_candidates = list(MOBILE_APP_DIR.glob("app/build/outputs/apk/debug/*.apk"))
    if not apk_candidates:
        raise FileNotFoundError("Could not find generated APK in app/build/outputs/apk/debug/")

    built_apk = apk_candidates[0]
    OUTPUT_APK.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(built_apk, OUTPUT_APK)
    size_mb = OUTPUT_APK.stat().st_size / (1024 * 1024)
    print(f"\n🎉 [SUCCESS] APK compiled successfully!")
    print(f"📦 APK Location: {OUTPUT_APK} ({size_mb:.2f} MB)")


def main():
    TOOLCHAIN_DIR.mkdir(parents=True, exist_ok=True)
    print("=== RGPIS-HDE Android Mobile APK Automated Builder ===")
    java_home = setup_jdk()
    sdkmanager = setup_cmdline_tools()
    gradle_bin = setup_gradle()
    install_android_packages(sdkmanager, java_home)
    build_apk(gradle_bin, java_home)


if __name__ == "__main__":
    main()
