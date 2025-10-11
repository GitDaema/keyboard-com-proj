import os
import sys
from pathlib import Path

# 프로젝트 루트
def _resolve_project_root() -> Path:
    try:
        # Frozen executable (PyInstaller onedir/onefile)
        if getattr(sys, 'frozen', False):
            try:
                # Prefer the directory of the executable for external resources
                return Path(sys.executable).resolve().parent
            except Exception:
                pass
            try:
                # Fallback to MEIPASS (temporary extraction dir)
                _meipass = getattr(sys, '_MEIPASS', None)
                if _meipass:
                    return Path(_meipass).resolve()
            except Exception:
                pass
        # Source checkout
        return Path(__file__).resolve().parents[1]
    except Exception:
        # Last resort: current working directory
        return Path.cwd()

PROJECT_ROOT = _resolve_project_root()

DATA_DIR = PROJECT_ROOT / "data"
MAPS_DIR = DATA_DIR / "maps"
