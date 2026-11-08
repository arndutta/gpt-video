"""Find a supported Node installation without changing system configuration."""

import os
from pathlib import Path
import shutil
import subprocess


def node_runtime() -> tuple[Path, Path, str]:
    options = [os.environ.get("NODE_BINARY"), shutil.which("node"),
               "/opt/homebrew/bin/node", "/usr/local/bin/node"]
    for option in dict.fromkeys(value for value in options if value):
        binary = Path(option)
        if not binary.is_file():
            continue
        try:
            version = subprocess.check_output([str(binary), "--version"], text=True, timeout=5).strip()
            major, minor, *_ = [int(value) for value in version.lstrip("v").split(".")]
        except (OSError, ValueError, subprocess.SubprocessError):
            continue
        if not ((major == 20 and minor >= 19) or (major == 22 and minor >= 12) or major > 22):
            continue
        candidates = [binary.parent / "npm", binary.resolve().parent / "npm",
                      binary.parent / "node_modules/npm/bin/npm-cli.js"]
        for candidate in candidates:
            script = candidate.resolve()
            if script.is_file() and script.suffix == ".js":
                return binary, script, version
    raise RuntimeError("Node >=20.19 (22.12+ or newer preferred) and npm are required. "
                       "Install a supported version or set NODE_BINARY to its executable.")
