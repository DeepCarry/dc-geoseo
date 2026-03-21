from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass
class CodexStatus:
    installed: bool
    logged_in: bool
    version: str = ""
    check_command: str = ""
    message: str = ""


def _run(cmd: list[str], timeout: int = 8) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def detect_codex() -> CodexStatus:
    exe = shutil.which("codex")
    if not exe:
        return CodexStatus(
            installed=False,
            logged_in=False,
            message="codex CLI not found in PATH.",
        )

    version_out = ""
    try:
        cp = _run(["codex", "--version"])
        version_out = (cp.stdout or cp.stderr).strip().splitlines()[0] if (cp.stdout or cp.stderr) else ""
    except Exception:
        pass

    checks = [
        ["codex", "whoami"],
        ["codex", "auth", "status"],
        ["codex", "login", "--check"],
    ]

    for cmd in checks:
        try:
            cp = _run(cmd)
        except Exception:
            continue

        out = "\n".join([(cp.stdout or ""), (cp.stderr or "")]).lower()
        if cp.returncode == 0:
            if any(k in out for k in ["not logged", "sign in", "login required", "unauthorized", "401"]):
                return CodexStatus(True, False, version_out, " ".join(cmd), "Codex CLI found but not logged in.")
            return CodexStatus(True, True, version_out, " ".join(cmd), "Codex CLI is available and logged in.")

        if any(k in out for k in ["not logged", "sign in", "login", "unauthorized", "401"]):
            return CodexStatus(True, False, version_out, " ".join(cmd), "Codex CLI found but not logged in.")

    return CodexStatus(
        installed=True,
        logged_in=False,
        version=version_out,
        message="Codex CLI found but login status could not be verified. Run `codex login`.",
    )
