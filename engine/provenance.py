# -*- coding: utf-8 -*-
"""Provenance 采集（设计文档 §35）：现在做成本最低，模型变多后再补非常麻烦。"""
import hashlib
import os
import platform
import subprocess
from typing import Any, Dict


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return "not-a-git-repo"


def _torch_version() -> str:
    try:
        import torch  # noqa: F401
        return torch.__version__
    except Exception:
        return "not-installed"


def _file_hash(path: str) -> str:
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:16]
    except Exception:
        return "unknown"


def collect_provenance(
    config_path: str,
    config: Dict[str, Any],
    red_agent,
    target,
    judge,
    evaluator,
) -> Dict[str, Any]:
    return {
        "git_commit": _git_commit(),
        "config_path": config_path,
        "config_hash": _file_hash(config_path),
        "python_version": platform.python_version(),
        "torch_version": _torch_version(),
        "cuda_version": "n/a",
        "red_backend": {
            "backend": getattr(red_agent, "name", "unknown"),
            "template_version": getattr(red_agent, "template_version", "n/a"),
        },
        "target_backend": {
            "backend": getattr(target, "name", "unknown"),
            "model": getattr(target, "model_name", "unknown"),
        },
        "judge_backend": {
            "backend": getattr(judge, "name", "unknown"),
            "version": getattr(judge, "version", "unknown"),
        },
        "evaluator_backend": {
            "backend": getattr(evaluator, "name", "unknown"),
            "version": getattr(evaluator, "version", "unknown"),
        },
        "prompt_template_versions": {
            "red": getattr(red_agent, "template_version", "unknown"),
        },
        "seed": (config.get("experiment", {}) or {}).get("seed", 42),
    }
