"""Setup assistant ("scout"): looks at this machine, the local Ollama server and the dataset, and recommends a
training config for the learnable auditor. Standard library only; never raises; works fully offline.

    python -m auditgym.scout [--explain] [--ollama-url URL]

Contract: docs/TRAINING_API.md section 2. Every probe has a short timeout, so without Ollama the whole call
takes well under a second. The optional LLM explanation (``explain=True``) is an add-on: nothing else depends
on it, and it is ``None`` whenever the local model is missing or fails.
"""
from __future__ import annotations

import ctypes
import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
from typing import Any, Dict, List, Optional

PRESETS = ["mixed", "simple", "interacting"]
PRESET_RU = {"mixed": "смешанные", "simple": "простые", "interacting": "с взаимодействиями"}

# Measured (Nov 21, Linux, Python 3.11, one process): a standard training, 1 920 training episodes plus 16 dev
# checks of 10 episodes, takes 21-23 s, i.e. ~0.011 s per episode. 0.015 leaves room for slower laptops and
# Windows; it is an estimate, shown as such.
SEC_PER_EPISODE = 0.015
DEV_EPISODES = 10
EVAL_EVERY = 2  # learner default

TIERS = {
    "small": {"population": 12, "episodes_per_candidate": 3, "iterations": 24},
    "medium": {"population": 16, "episodes_per_candidate": 4, "iterations": 30},
    "large": {"population": 24, "episodes_per_candidate": 4, "iterations": 30},
}

PROBE_TIMEOUT = 1.0  # seconds, any external program
CHAT_TIMEOUT = 25.0


# ---------------------------------------------------------------- machine

def _run(cmd: List[str], timeout: float = PROBE_TIMEOUT) -> Optional[str]:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip()


def _os_name() -> str:
    system = platform.system() or sys.platform
    try:
        if system == "Windows":
            ver = platform.version()  # "10.0.22631"
            try:
                build = int(ver.split(".")[2])
            except (IndexError, ValueError):
                build = 0
            release = platform.release()
            if release == "10" and build >= 22000:  # Python 3.11 still reports Windows 11 as "10"
                release = "11"
            return f"Windows {release}"
        if system == "Darwin":
            mac = platform.mac_ver()[0]
            return f"macOS {mac}" if mac else "macOS"
        if system == "Linux":
            try:
                pretty = platform.freedesktop_os_release().get("PRETTY_NAME")
            except OSError:
                pretty = None
            return f"Linux {platform.release()}" + (f" ({pretty})" if pretty else "")
        return f"{system} {platform.release()}".strip()
    except Exception:  # noqa: BLE001 - the scout never raises
        return system or "unknown"


def _ram_gb() -> Optional[float]:
    try:
        if sys.platform.startswith("linux"):
            with open("/proc/meminfo", encoding="ascii") as fh:
                for line in fh:
                    if line.startswith("MemTotal:"):
                        return round(int(line.split()[1]) * 1024 / 1e9, 1)  # kB -> GB
            return None
        if sys.platform == "darwin":
            out = _run(["sysctl", "-n", "hw.memsize"], timeout=0.5)
            return round(int(out) / 1e9, 1) if out else None
        if sys.platform == "win32":
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):  # type: ignore[attr-defined]
                return round(stat.ullTotalPhys / 1e9, 1)
            return None
    except Exception:  # noqa: BLE001
        return None
    return None


def _gpus() -> List[Dict[str, Any]]:
    gpus: List[Dict[str, Any]] = []
    try:
        if shutil.which("nvidia-smi"):
            out = _run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"])
            for line in (out or "").splitlines():
                parts = [p.strip() for p in line.split(",")]
                if not parts or not parts[0]:
                    continue
                vram = None
                if len(parts) > 1:
                    num = parts[1].split()[0] if parts[1].split() else ""
                    try:
                        vram = round(float(num) / 1024, 1)  # MiB -> GiB
                    except ValueError:
                        vram = None
                gpus.append({"name": parts[0], "vram_gb": vram})
        if sys.platform == "darwin":
            brand = _run(["sysctl", "-n", "machdep.cpu.brand_string"], timeout=0.5) or ""
            if "Apple" in brand:
                gpus.append({"name": f"{brand} GPU (общая память)", "vram_gb": None})
    except Exception:  # noqa: BLE001
        pass
    return gpus


def machine_info() -> Dict[str, Any]:
    try:
        cpu = os.cpu_count()
    except Exception:  # noqa: BLE001
        cpu = None
    return {"os": _os_name(), "python": platform.python_version(), "cpu_count": cpu, "ram_gb": _ram_gb(),
            "gpu": _gpus()}


# ---------------------------------------------------------------- ollama

def _opener() -> urllib.request.OpenerDirector:
    # Ollama is local: never route it through an HTTP(S)_PROXY from the environment.
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def ollama_info(url: str, timeout: float) -> Dict[str, Any]:
    try:
        with _opener().open(url.rstrip("/") + "/api/tags", timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        models = []
        for m in data.get("models") or []:
            if not isinstance(m, dict) or not isinstance(m.get("name") or m.get("model"), str):
                continue
            det = m.get("details") if isinstance(m.get("details"), dict) else {}
            size = m.get("size")
            models.append({"name": m.get("name") or m.get("model"),
                           "size_gb": round(size / 1e9, 1) if isinstance(size, (int, float)) and not isinstance(size, bool) else None,
                           "params": det.get("parameter_size") or None,
                           "quant": det.get("quantization_level") or None})
        return {"available": True, "models": models}
    except Exception:  # noqa: BLE001 - offline, refused, timeout, bad JSON: all mean "not available"
        return {"available": False, "models": []}


def _params_billions(p: Any) -> Optional[float]:
    if not isinstance(p, str) or not p:
        return None
    s = p.strip().upper()
    mult = {"B": 1.0, "M": 1e-3, "K": 1e-6, "T": 1e3}.get(s[-1])
    try:
        return float(s[:-1]) * mult if mult else float(s)
    except ValueError:
        return None


def smallest_model(models: List[Dict[str, Any]]) -> Optional[str]:
    """Smallest installed model by size on disk (then parameter count); None if there is none."""
    best, key_best = None, None
    for m in models:
        size = m.get("size_gb")
        params = _params_billions(m.get("params"))
        key = (size if size is not None else float("inf"), params if params is not None else float("inf"), m["name"])
        if key_best is None or key < key_best:
            best, key_best = m["name"], key
    return best


# ---------------------------------------------------------------- dataset

def dataset_info() -> Dict[str, Any]:
    out: Dict[str, Any] = {"train_configs": None, "dev_episodes": None, "presets": list(PRESETS)}
    try:
        from . import harness  # local import: a broken checkout must not break the scout
    except Exception:  # noqa: BLE001
        return out
    for split, key in (("train", "train_configs"), ("dev", "dev_episodes")):
        try:
            out[key] = len(harness.load_split(split))
        except Exception:  # noqa: BLE001
            pass
    return out


# ---------------------------------------------------------------- recommendation

def _ru_plural(n: int, one: str, few: str, many: str) -> str:
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def _tier(cpu: Optional[int], ram: Optional[float]) -> str:
    c = cpu or 1
    if c <= 2 or (ram is not None and ram <= 4):
        return "small"
    if c >= 8 and (ram is None or ram >= 8):
        return "large"
    return "medium"


def estimate_seconds(cfg: Dict[str, Any]) -> int:
    it, pop, epc = cfg["iterations"], cfg["population"], cfg["episodes_per_candidate"]
    evals = len({i for i in range(it) if i % EVAL_EVERY == 0} | {it - 1})
    episodes = it * pop * epc + evals * DEV_EPISODES
    return int(round(episodes * SEC_PER_EPISODE))


def recommend(machine: Dict[str, Any], ollama: Dict[str, Any], dataset: Dict[str, Any]) -> Dict[str, Any]:
    cpu, ram = machine.get("cpu_count"), machine.get("ram_gb")
    tier = _tier(cpu, ram)
    t = TIERS[tier]
    cfg = {"method": "cem", "iterations": t["iterations"], "population": t["population"],
           "episodes_per_candidate": t["episodes_per_candidate"], "dataset": {"preset": "mixed"}}
    est = estimate_seconds(cfg)
    n_eps = cfg["iterations"] * cfg["population"] * cfg["episodes_per_candidate"]
    dev_n = dataset.get("dev_episodes") or DEV_EPISODES
    cpu_txt = f"{cpu} {_ru_plural(cpu, 'ядро', 'ядра', 'ядер')}" if cpu else "число ядер неизвестно"
    ram_txt = f"{ram:g} ГБ ОЗУ" if ram is not None else "объём ОЗУ неизвестен"
    size_txt = {"small": "уменьшенная конфигурация, чтобы не перегружать машину",
                "medium": "стандартная конфигурация",
                "large": "увеличенная популяция — машина позволяет"}[tier]
    llm = smallest_model(ollama.get("models") or []) if ollama.get("available") else None
    reasons = [
        "Обучаем собственного аудитора (CEM) только на CPU: по правилам кейса — без GPU, платных API и сети.",
        f"Машина: {cpu_txt}, {ram_txt} → {size_txt}: популяция {cfg['population']} × "
        f"{cfg['episodes_per_candidate']} {_ru_plural(cfg['episodes_per_candidate'], 'эпизод', 'эпизода', 'эпизодов')} × "
        f"{cfg['iterations']} {_ru_plural(cfg['iterations'], 'итерация', 'итерации', 'итераций')} ≈ "
        f"{n_eps} {_ru_plural(n_eps, 'эпизод', 'эпизода', 'эпизодов')}, "
        f"оценка времени ≈ {est} с (приблизительно).",
        f"Улучшение показываем честно: каждые {EVAL_EVERY} итерации лучшая политика проверяется на {dev_n} "
        "отложенных dev-эпизодах в закрытом режиме, рядом с базовыми политиками.",
        "Набор «смешанные»: все четыре вида ошибок и их взаимодействия, чтобы политика не подстраивалась "
        "под один тип; эпизоды обучения генерируются заново и не совпадают с dev.",
    ]
    if llm:
        reasons.append(f"LLM «{llm}» (самая маленькая из установленных) предлагаем только для оценки на dev, "
                       "не для обучения: обучение весов в кейсе необязательно, и так нет зависимости от GPU.")
    else:
        reasons.append("Ollama не найдена: для обучения она не нужна; LLM-агента можно оценить позже "
                       "(ollama pull qwen2.5:1.5b) — только оценка, без обучения весов.")
    return {"model": "auditor-cem", "config": cfg, "est_seconds": est, "reasons": reasons, "evaluate_llm": llm}


# ---------------------------------------------------------------- optional LLM explanation

def explain_with_llm(url: str, model: str, machine: Dict[str, Any], rec: Dict[str, Any],
                     timeout: float = CHAT_TIMEOUT) -> Optional[str]:
    summary = {"machine": {k: machine.get(k) for k in ("os", "cpu_count", "ram_gb", "gpu")},
               "recommendation": {k: rec.get(k) for k in ("model", "config", "est_seconds", "evaluate_llm")}}
    prompt = ("Объясни простым русским языком в 2–3 предложениях, почему для этой машины рекомендована такая "
              "конфигурация обучения аудитора. Обучение идёт только на CPU, результат проверяется на отложенных "
              "dev-эпизодах; LLM используется только для оценки. Без списков и без markdown.\n"
              + json.dumps(summary, ensure_ascii=False))
    body = {"model": model, "stream": False,
            "messages": [{"role": "system", "content": "Ты кратко и точно объясняешь технические решения."},
                         {"role": "user", "content": prompt}],
            "options": {"temperature": 0.2, "num_predict": 160}}
    try:
        req = urllib.request.Request(url.rstrip("/") + "/api/chat", data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        with _opener().open(req, timeout=timeout) as resp:
            text = json.loads(resp.read().decode("utf-8"))["message"]["content"]
        text = text.strip() if isinstance(text, str) else ""
        return text or None
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------- entry point

def scout(explain: bool = False, ollama_url: str = "http://127.0.0.1:11434", timeout: float = 0.6) -> Dict[str, Any]:
    """Machine + Ollama + dataset summary and a recommended training config (docs/TRAINING_API.md §2)."""
    try:
        machine = machine_info()
    except Exception:  # noqa: BLE001
        machine = {"os": "unknown", "python": platform.python_version(), "cpu_count": None, "ram_gb": None, "gpu": []}
    try:
        ollama = ollama_info(ollama_url, timeout)
    except Exception:  # noqa: BLE001
        ollama = {"available": False, "models": []}
    try:
        dataset = dataset_info()
    except Exception:  # noqa: BLE001
        dataset = {"train_configs": None, "dev_episodes": None, "presets": list(PRESETS)}
    try:
        rec = recommend(machine, ollama, dataset)
    except Exception:  # noqa: BLE001
        cfg = {"method": "cem", **TIERS["medium"], "dataset": {"preset": "mixed"}}
        rec = {"model": "auditor-cem", "config": cfg, "est_seconds": estimate_seconds(cfg),
               "reasons": ["Обучаем аудитора (CEM) только на CPU; проверка — на отложенных dev-эпизодах."],
               "evaluate_llm": None}
    explanation = None
    if explain and rec.get("evaluate_llm"):
        explanation = explain_with_llm(ollama_url, rec["evaluate_llm"], machine, rec)
    return {"machine": machine, "ollama": ollama, "dataset": dataset, "recommendation": rec,
            "explanation": explanation}


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="AuditGym setup assistant")
    ap.add_argument("--explain", action="store_true", help="ask the local Ollama model for a short explanation")
    ap.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    opts = ap.parse_args(argv)
    print(json.dumps(scout(explain=opts.explain, ollama_url=opts.ollama_url), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
