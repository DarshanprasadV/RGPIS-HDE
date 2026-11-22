"""
ExecuTorch Runtime Engine for Llama 3.2 on Edge / Apple Silicon / ARM CPU.
Handles local .pte graph execution, tokenization, KV-caching, and performance metrics.
Zero cloud API dependencies. Runs 100% locally and offline.
"""

import os
import sys
import time
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psutil
import torch

# Ensure local directories are on path
MODULE_DIR = Path(__file__).parent.resolve()
MODELS_DIR = MODULE_DIR / "models"
DEFAULT_PTE = MODELS_DIR / "llama_3_2_1b_xnnpack_spinquant.pte"
DEFAULT_PARAMS = MODELS_DIR / "params.json"
DEFAULT_TOKENIZER = MODELS_DIR / "tokenizer.json"
DEFAULT_TOK_CONFIG = MODELS_DIR / "tokenizer_config.json"

logger = logging.getLogger("ExecuTorchEngine")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class ExecuTorchLlamaEngine:
    """
    Manages ExecuTorch Llama 3.2 local offline inference.
    """

    def __init__(
        self,
        pte_path: Optional[Path] = None,
        params_path: Optional[Path] = None,
        tokenizer_path: Optional[Path] = None,
        tok_config_path: Optional[Path] = None,
        max_seq_len: int = 2048,
        use_kv_cache: bool = True,
    ):
        self.pte_path = Path(pte_path or DEFAULT_PTE)
        self.params_path = Path(params_path or DEFAULT_PARAMS)
        self.tokenizer_path = Path(tokenizer_path or DEFAULT_TOKENIZER)
        self.tok_config_path = Path(tok_config_path or DEFAULT_TOK_CONFIG)
        self.max_seq_len = max_seq_len
        self.use_kv_cache = use_kv_cache
        self.runner = None
        self._is_loaded = False

    def load_model(self) -> bool:
        """
        Loads the .pte binary model and initializes tokenizer and KV-cache in ExecuTorch.
        """
        if not self.pte_path.exists():
            raise FileNotFoundError(f"ExecuTorch model not found at: {self.pte_path}")
        if not self.tokenizer_path.exists():
            raise FileNotFoundError(f"Tokenizer not found at: {self.tokenizer_path}")
        if not self.params_path.exists():
            raise FileNotFoundError(f"Model parameters file not found at: {self.params_path}")

        logger.info(f"Loading ExecuTorch program: {self.pte_path.name}")
        start_time = time.time()

        # Import ExecuTorch native runner components
        from executorch.examples.models.llama.runner.native import NativeLlamaRunner

        class RunnerArgs:
            def __init__(self, pte, params, tokenizer, tokenizer_config, max_len, kv_cache):
                self.pte = str(pte)
                self.params = str(params)
                self.tokenizer = str(tokenizer)
                self.tokenizer_config = str(tokenizer_config) if tokenizer_config else None
                self.max_len = max_len
                self.kv_cache = kv_cache
                self.model = "llama3"
                self.temperature = 0.6

        args = RunnerArgs(
            pte=self.pte_path,
            params=self.params_path,
            tokenizer=self.tokenizer_path,
            tokenizer_config=self.tok_config_path,
            max_len=2048,          # Model supports up to 2048; set hard limit here
            kv_cache=self.use_kv_cache,
        )

        self.runner = NativeLlamaRunner(args)
        load_duration = time.time() - start_time
        self._is_loaded = True
        logger.info(f"Model successfully loaded into ExecuTorch runtime in {load_duration:.2f}s")
        return True

    def generate(
        self,
        prompt: str,
        max_new_tokens: int = 384,
        temperature: float = 0.2,
        top_p: float = 0.9,
    ) -> Dict[str, Any]:
        """
        Executes local forward passes through the ExecuTorch graph.
        Returns generated text, token count, latency, tokens/sec, and RAM usage.
        """
        if not self._is_loaded or self.runner is None:
            self.load_model()

        process = psutil.Process(os.getpid())
        ram_before_mb = process.memory_info().rss / (1024 * 1024)

        logger.info(f"Encoding prompt ({len(prompt)} characters)...")
        prompt_tokens = self.runner.tokenizer.encode(prompt, bos=True, eos=False)
        prompt_len = len(prompt_tokens)

        # Ensure we always have room to generate even if prompt is long
        # ExecuTorch .pte has a hard max context baked in; use 2048 as safe upper bound
        hard_max = 2048
        if prompt_len >= hard_max:
            # Truncate prompt tokens from the front (keep recency), leave room for generation
            keep = hard_max - max_new_tokens - 10
            prompt_tokens = prompt_tokens[prompt_len - keep:]
            prompt_len = len(prompt_tokens)
            logger.warning(f"Prompt truncated to {prompt_len} tokens to fit context window.")
        total_max_len = min(hard_max, prompt_len + max_new_tokens)

        logger.info(f"Starting ExecuTorch inference (prompt: {prompt_len} tokens, max_total: {total_max_len})...")
        start_time = time.time()

        # Execute local autoregressive generation via ExecuTorch
        output_tokens = self.runner.generate(
            prompt_tokens=prompt_tokens,
            max_seq_len=total_max_len,
            temperature=temperature,
            top_p=top_p,
            echo=False,
        )

        total_time = time.time() - start_time
        ram_after_mb = process.memory_info().rss / (1024 * 1024)
        peak_ram_mb = max(ram_before_mb, ram_after_mb)

        generated_token_count = len(output_tokens)
        tok_per_sec = generated_token_count / total_time if total_time > 0 else 0.0

        # Decode tokens to text string
        raw_text = self.runner.tokenizer.decode(output_tokens)

        return {
            "text": raw_text.strip(),
            "prompt_tokens": prompt_len,
            "generated_tokens": generated_token_count,
            "latency_seconds": round(total_time, 3),
            "tokens_per_second": round(tok_per_sec, 2),
            "ram_usage_mb": round(peak_ram_mb, 1),
            "runtime": "ExecuTorch (XNNPACK / CPU)",
            "model": "Llama-3.2-1B-Instruct (4-bit SpinQuant)"
        }
