# RGPIS-HDE — Llama Advisory: Edge Deployment Guide

## ExecuTorch Llama 3.2 1B on ARM-based Edge SoCs

**Project:** RGPIS-HDE Industrial PCB Defect Inspection  
**Challenge:** Bharat AI-SoC Challenge 2026/27  
**Runtime:** ExecuTorch 1.6.0 · Llama 3.2 1B Instruct · 4-bit SpinQuant · XNNPACK CPU

---

## 1. Verified Baseline (Apple M1 MacBook Air)

| Metric | Measured Value |
|:---|:---|
| Model load time | ~45–50 s (cold, includes C++ kernel init) |
| Generation speed | ~2.7 tok/s |
| Peak RAM (inference) | ~1,075 MB |
| Model size on disk | 1,032 MB (`.pte`) |
| Tokenizer size | 9.5 MB (`.json`) |
| Python runtime | 3.11 |
| Backend | XNNPACK CPU (ARM NEON) |
| Offline verified | ✅ No network calls during inference |

> [!NOTE]
> The 45-second cold load time is due to `torch.compile` lazy compilation on first run. On dedicated edge hardware with pre-warmed state, this reduces significantly. Warm restarts (keeping process alive) take ~1s.

---

## 2. Edge Hardware Requirements

### Minimum Viable (Llama 3.2 1B SpinQuant INT4)

| Component | Minimum | Recommended |
|:---|:---|:---|
| CPU Architecture | ARMv8.2 (64-bit) | ARMv8.5+ with NEON/SVE |
| RAM | 2 GB LPDDR4 | 4 GB LPDDR4X |
| Flash Storage | 2 GB free | 4 GB free |
| OS | Linux (64-bit, glibc 2.31+) | Debian 11 / Ubuntu 22.04 |
| Python | 3.10–3.12 | 3.11 |

### Competition-Compatible Hardware Options

| Board | CPU | RAM | ExecuTorch Support | Notes |
|:---|:---|:---|:---|:---|
| Raspberry Pi 5 | Cortex-A76 (ARMv8.2) | 4 GB / 8 GB | ✅ Supported (official guide) | Recommended for competition |
| Raspberry Pi 4B | Cortex-A72 (ARMv8) | 4 GB / 8 GB | ✅ Supported | Slower generation ~1 tok/s |
| NVIDIA Jetson Nano | Cortex-A57 + 128 CUDA | 4 GB | ✅ XNNPACK CPU (GPU path needs Vulkan) | Good performance |
| Khadas VIM4 | Cortex-A73 (ARMv8) | 8 GB | ✅ XNNPACK CPU | Bharat SoC-compatible |
| OrangePi 5 Plus | Cortex-A76 (RK3588) | 4–16 GB | ✅ XNNPACK CPU | Competitive board |

> [!IMPORTANT]
> **Raspberry Pi is not mandatory.** Any 64-bit ARM board with ≥2 GB RAM and Linux running glibc ≥2.31 is compatible. Do **not** use 32-bit ARM (armhf) — ExecuTorch requires aarch64 binaries.

---

## 3. Cross-Compilation Instructions (Raspberry Pi / ARM Linux)

### On Your Host Mac (Apple M1):

```bash
# Step 1: Install cross-compilation toolchain
brew install aarch64-unknown-linux-gnu

# Step 2: Clone ExecuTorch source
git clone https://github.com/pytorch/executorch.git
cd executorch
git submodule sync && git submodule update --init

# Step 3: Build for ARM64 target
./build/cmake-linux-arm64.sh

# Step 4: Collect runtime artifacts
ls cmake-out-arm64/examples/models/llama/
# → llama_main (native C++ runner binary)
# → libexecutorch.so
```

### Transfer to Edge Device:

```bash
scp cmake-out-arm64/examples/models/llama/llama_main pi@raspberrypi.local:~/
scp llama_advisory/models/llama_3_2_1b_xnnpack_spinquant.pte pi@raspberrypi.local:~/models/
scp llama_advisory/models/tokenizer.json pi@raspberrypi.local:~/models/
scp llama_advisory/models/params.json pi@raspberrypi.local:~/models/
```

### Run on Edge Device:

```bash
# On Raspberry Pi or ARM board
export LD_LIBRARY_PATH=./lib:$LD_LIBRARY_PATH

./llama_main \
  --pte ./models/llama_3_2_1b_xnnpack_spinquant.pte \
  --tokenizer ./models/tokenizer.json \
  --params ./models/params.json \
  --kv_cache \
  --prompt "Open circuit detected with confidence 0.94. Explain defect and operator action." \
  --max_len 200 \
  --temperature 0.2
```

---

## 4. Python Deployment on Edge (Alternative to C++ Runner)

If the edge board runs Python 3.10–3.12 with pip access:

```bash
# On edge device
pip install executorch torch --index-url https://download.pytorch.org/whl/cpu

# Run advisory
python -m llama_advisory.defect_advisor
```

> [!TIP]
> Pre-download all pip wheels on your Mac and transfer them via `pip download --platform linux_aarch64` for a fully offline setup on the edge device.

---

## 5. Offline Operation Verification

ExecuTorch inference makes **zero network calls** after model loading. Verified by:

1. **Network disabled test** — inference completed successfully with Wi-Fi off on the host Mac.
2. **No cloud API calls** — the entire generation loop runs through `_load_for_executorch()` → C++ kernel → `NativeLlamaRunner.generate()` → local token sampling.
3. **No Hugging Face API** — the `.pte` binary and `tokenizer.json` are fully self-contained static files.

---

## 6. Actual Limitations (Measured, Not Assumed)

| Limitation | Measured / Known | Mitigation |
|:---|:---|:---|
| **Generation speed** | ~2.7 tok/s on M1; ~1 tok/s expected on RPi 4 | Use RPi 5 (A76 cores) for 2–3x speedup |
| **Cold load time** | 45–50s (Python), ~5s (C++ binary) | Use C++ `llama_main` on edge for fast startup |
| **Peak RAM** | ~1,075 MB | Requires ≥2 GB device RAM; 4 GB recommended |
| **Context window** | 512 tokens (configurable) | Sufficient for structured PCB defect prompts |
| **JSON output reliability** | Requires schema validation layer | ✅ Already implemented in `prompt_templates.py` |
| **Model approval decisions** | Explicitly prohibited by safety rules | ✅ Hardcoded safety checks in `defect_advisor.py` |
| **Triton warnings on macOS** | Non-fatal; XNNPACK used instead | No action needed on ARM Linux |
| **No GPU on most edge SoCs** | XNNPACK CPU backend used | Vulkan backend available for Mali/Adreno GPUs |

---

## 7. Bharat AI-SoC Challenge Deployment Checklist

- [ ] Model file `llama_3_2_1b_xnnpack_spinquant.pte` transferred to edge device
- [ ] Tokenizer `tokenizer.json` and `params.json` present alongside model
- [ ] ExecuTorch runtime installed (Python pip or C++ binary)
- [ ] `llama_advisory/` package deployed with all Python modules
- [ ] Network disabled — inference verified offline
- [ ] `defect_advisor.py` runs successfully with all 6 DeepPCB defect classes
- [ ] Output schema validation passing for all test cases
- [ ] Safety disclaimer verified: system does not independently approve/reject PCBs
- [ ] RAM usage within device limits (target ≤ 1.5 GB peak)
- [ ] Generation speed documented and within competition time budget
