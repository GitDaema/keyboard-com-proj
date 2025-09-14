#!/usr/bin/env bash
set -euo pipefail

echo "=== run_demo_windows.sh: START ==="

# 루트로 이동
cd "$(dirname "$0")/.."
echo "[INFO] cwd = $(pwd)"
echo "[INFO] SHELL = ${SHELL:-unknown}"

# 1) venv 활성화 (Windows=Scripts, Linux=bin 둘 다 탐색)
if [ -f ".venv/Scripts/activate" ]; then
  echo "[INFO] activate venv: .venv/Scripts/activate"
  # Git Bash에서도 source 가능
  # shellcheck disable=SC1091
  source ".venv/Scripts/activate"
elif [ -f ".venv/bin/activate" ]; then
  echo "[INFO] activate venv: .venv/bin/activate"
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
else
  echo "[ERROR] .venv 활성화 스크립트를 찾지 못했어요."
  echo "        확인: .venv/Scripts/activate (Windows) 또는 .venv/bin/activate (Linux/WSL)"
  exit 1
fi

python --version || { echo "[ERROR] python 실행 불가"; exit 1; }

# 2) OpenRGB 서버 실행 (Windows 전용, PowerShell 사용)
OPENRGB_EXE="bin/windows/OpenRGB.exe"
if [ -f "$OPENRGB_EXE" ]; then
  abs_exe="$(pwd)/$OPENRGB_EXE"

  # POSIX(/c/...) -> Windows(C:\...) 경로 변환
  to_win_path() {
    if command -v cygpath >/dev/null 2>&1; then
      cygpath -w "$1"
    else
      printf '%s' "$1" | sed -E 's#^/([a-zA-Z])/#\U\1:/#; s#/#\\#g'
    fi
  }

  win_exe="$(to_win_path "$abs_exe")"
  win_workdir="$(to_win_path "$(pwd)/bin/windows")"
  echo "[INFO] OpenRGB exe (Windows path) = $win_exe"
  echo "[INFO] OpenRGB workdir            = $win_workdir"

  # ⚠️ 한 줄로 전달 (줄바꿈 기호 ^ 사용 금지)
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command \
    "Start-Process -FilePath '$win_exe' -ArgumentList '--server','--startminimized' -WorkingDirectory '$win_workdir' -WindowStyle Minimized"

  # 기동 여유
  sleep 0.6
else
  echo "[WARN] $OPENRGB_EXE 파일이 없어요. 건너뜀."
fi

# 3) 포트 대기 (파이썬으로 교체: /dev/tcp 호환성 문제 해결)
echo "[INFO] wait OpenRGB: 127.0.0.1:6742 (최대 12초)"
python - <<'PY'
import socket, time, sys
host, port, timeout = "127.0.0.1", 6742, 12
start = time.time()
while True:
    try:
        with socket.create_connection((host, port), 0.5):
            print("[OK ] OpenRGB server detected.")
            sys.exit(0)
    except OSError:
        if time.time() - start > timeout:
            print("[ERR] port wait failed")
            sys.exit(1)
        time.sleep(0.3)
PY

# 4) 컨트롤러 실행
echo "[INFO] run: python controller/main.py"
exec python controller/main.py
