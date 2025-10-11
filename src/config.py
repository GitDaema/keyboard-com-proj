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

def _resolve_data_dir(project_root: Path) -> Path:
    """Best-effort resolution of packaged data directory.
    Tries these locations in order:
      1) <project_root>/data
      2) sys._MEIPASS/data (PyInstaller onefile)
      3) <project_root>/_internal/data (some onedir layouts)
      4) repo source fallback: <this_file>/../../data
    Returns the first existing path; falls back to project_root/data.
    """
    candidates = []
    candidates.append(project_root / "data")
    try:
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "data")
    except Exception:
        pass
    candidates.append(project_root / "_internal" / "data")
    try:
        repo_fallback = Path(__file__).resolve().parents[1] / "data"
        candidates.append(repo_fallback)
    except Exception:
        pass
    for p in candidates:
        try:
            if p.exists() and (p / "maps").exists():
                return p
        except Exception:
            pass
    return candidates[0]

DATA_DIR = _resolve_data_dir(PROJECT_ROOT)
MAPS_DIR = DATA_DIR / "maps"
