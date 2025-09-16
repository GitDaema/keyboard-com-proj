import os
from pathlib import Path

# 프로젝트 루트
PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJECT_ROOT / "data"
MAPS_DIR = DATA_DIR / "maps"