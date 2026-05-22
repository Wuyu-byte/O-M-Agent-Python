"""实验室运维工具 - 迁移自 Go 版的本地实验环境能力。"""

from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from langchain_core.tools import tool
from loguru import logger

from app.config import config


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _run_command(args: list[str], timeout: float) -> tuple[str, str, int]:
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
        return completed.stdout, completed.stderr, completed.returncode
    except FileNotFoundError:
        return "", f"command not found: {args[0]}", 127
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return stdout, stderr or f"command timed out after {timeout}s", 124


@tool
def query_gpu_status() -> str:
    """查询本机 NVIDIA GPU 状态。

    适用场景：用户需要检查实验室 GPU 型号、显存占用、利用率、温度，或希望推荐空闲 GPU。
    这是只读工具，依赖本机 `nvidia-smi`。
    """
    stdout, stderr, code = _run_command(
        [
            "nvidia-smi",
            "--query-gpu=index,name,memory.used,memory.total,utilization.gpu,temperature.gpu",
            "--format=csv,noheader,nounits",
        ],
        timeout=8,
    )
    if code != 0:
        return _json(
            {
                "success": False,
                "message": "nvidia-smi 不可用，或当前机器没有可见的 NVIDIA GPU",
                "raw": (stdout or stderr).strip(),
            }
        )

    gpus: list[dict[str, Any]] = []
    for row in csv.reader(stdout.splitlines(), skipinitialspace=True):
        if len(row) < 6:
            continue
        try:
            used = int(row[2].strip())
            total = int(row[3].strip())
            available = max(total - used, 0)
        except ValueError:
            available = None
        gpus.append(
            {
                "index": row[0].strip(),
                "name": row[1].strip(),
                "memory_used_mb": row[2].strip(),
                "memory_total_mb": row[3].strip(),
                "utilization_gpu_percent": row[4].strip(),
                "temperature_c": row[5].strip(),
                "available_memory_mb": available,
            }
        )

    return _json({"success": True, "gpus": gpus, "message": f"found {len(gpus)} GPU(s)"})


@tool
def query_python_env() -> str:
    """检查当前 Python 实验环境。

    返回 Python 版本、解释器路径、PyTorch 版本、CUDA 版本和 torch.cuda 是否可用。
    这是只读工具，用于定位训练/推理环境问题。
    """
    python_cmd = sys.executable or shutil.which("python") or shutil.which("python3")
    if not python_cmd:
        return _json({"success": False, "message": "未在 PATH 中找到 Python 解释器"})

    version_out, version_err, _ = _run_command([python_cmd, "--version"], timeout=5)
    probe = (
        "import json\n"
        "result={}\n"
        "try:\n"
        "    import torch\n"
        "    result['torch_version']=torch.__version__\n"
        "    result['torch_cuda']=str(torch.version.cuda)\n"
        "    result['cuda_available']=str(torch.cuda.is_available())\n"
        "except Exception as e:\n"
        "    result['torch_error']=str(e)\n"
        "print(json.dumps(result, ensure_ascii=False))\n"
    )
    torch_out, torch_err, _ = _run_command([python_cmd, "-c", probe], timeout=12)

    result: dict[str, Any] = {
        "success": True,
        "python_command": python_cmd,
        "python_version": (version_out or version_err).strip(),
        "message": "python environment inspected",
        "raw": (torch_out or torch_err).strip(),
    }
    try:
        torch_info = json.loads(torch_out.strip() or "{}")
        result.update(
            {
                "torch_version": torch_info.get("torch_version", ""),
                "torch_cuda": torch_info.get("torch_cuda", ""),
                "cuda_available": torch_info.get("cuda_available", ""),
            }
        )
        if torch_info.get("torch_error"):
            result["message"] = "Python 可用，但 PyTorch 无法导入"
            result["torch_error"] = torch_info["torch_error"]
    except json.JSONDecodeError:
        result["message"] = "Python 可用，但 PyTorch 探测输出无法解析"

    return _json(result)


def _resolve_lab_log_path(input_path: str) -> Path:
    base = Path(config.lab_log_dir).expanduser().resolve()
    candidate = Path(input_path).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    resolved = candidate.resolve()
    try:
        common = os.path.commonpath([str(base), str(resolved)])
    except ValueError as exc:
        raise ValueError(f"日志路径必须位于 lab_log_dir 内: {base}") from exc
    if common != str(base):
        raise ValueError(f"日志路径必须位于 lab_log_dir 内: {base}")
    return resolved


def _tail_file(path: Path, tail_lines: int) -> str:
    lines: list[str] = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            lines.append(line.rstrip("\n"))
            if len(lines) > tail_lines:
                lines = lines[-tail_lines:]
    return "\n".join(lines)


def _detect_log_problems(content: str) -> list[str]:
    checks = [
        ("cuda out of memory", "CUDA_OUT_OF_MEMORY"),
        ("outofmemoryerror", "OUT_OF_MEMORY"),
        ("modulenotfounderror", "MISSING_PYTHON_PACKAGE"),
        ("importerror", "IMPORT_ERROR"),
        ("filenotfounderror", "FILE_NOT_FOUND"),
        ("no such file or directory", "FILE_NOT_FOUND"),
        ("permission denied", "PERMISSION_DENIED"),
        ("no space left on device", "DISK_FULL"),
        ("cuda error", "CUDA_ERROR"),
        ("driver version is insufficient", "CUDA_DRIVER_MISMATCH"),
        ("address already in use", "PORT_IN_USE"),
    ]
    lower = content.lower()
    problems: list[str] = []
    seen: set[str] = set()
    for needle, label in checks:
        if needle in lower and label not in seen:
            seen.add(label)
            problems.append(label)
    return problems


@tool
def read_lab_log(path: str, tail_lines: int = 200) -> str:
    """读取实验或训练日志末尾内容并检测常见错误。

    Args:
        path: 日志路径。相对路径会解析到配置项 `lab_log_dir` 下；绝对路径也必须位于该目录内。
        tail_lines: 读取末尾行数，默认 200，最大 1000。
    """
    if not path or not path.strip():
        return _json({"success": False, "message": "path is required"})
    try:
        log_path = _resolve_lab_log_path(path.strip())
        safe_tail_lines = min(max(int(tail_lines or 200), 1), 1000)
        content = _tail_file(log_path, safe_tail_lines)
        return _json(
            {
                "success": True,
                "path": str(log_path),
                "tail_lines": safe_tail_lines,
                "content": content,
                "detected_problems": _detect_log_problems(content),
                "message": "log file read successfully",
            }
        )
    except Exception as e:
        logger.warning("读取实验日志失败: {}", e)
        return _json({"success": False, "message": str(e)})
