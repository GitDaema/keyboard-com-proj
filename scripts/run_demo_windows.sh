#!/usr/bin/env bash
set -euo pipefail

echo "=== run_demo_windows.sh: START ==="

# 0) 루트로 이동
cd "$(dirname "$0")/.."
echo "[INFO] cwd = $(pwd)"
echo "[INFO] SHELL = ${SHELL:-unknown}"

# --------------------------------------------------------------------
# 1) Python 해상도: venv 우선, 그 다음 시스템 파이썬 후보 순회
#    - venv의 python을 직접 실행(activate 없이도 OK)
#    - 후보: .venv/Scripts/python.exe, .venv/bin/python
#            python, python3, py -3, py
# --------------------------------------------------------------------
resolve_python() {
  local candidates=()

  # venv 쪽 먼저
  if [ -x ".venv/Scripts/python.exe" ]; then
    candidates+=(".venv/Scripts/python.exe")
  fi
  if [ -x ".venv/bin/python" ]; then
    candidates+=(".venv/bin/python")
  fi

  # 시스템 파이썬들
  if command -v python >/dev/null 2>&1; then
    candidates+=("python")
  fi
  if command -v python3 >/dev/null 2>&1; then
    candidates+=("python3")
  fi
  if command -v py >/dev/null 2>&1; then
    # py -3가 되면 두 단어라 직접 지정 어려움 → wrapper로 처리
    candidates+=("py3")  # 별도 케이스로 취급
    candidates+=("py")   # 백업
  fi

  for c in "${candidates[@]}"; do
    case "$c" in
      py3)
        if py -3 -c "import sys; print(sys.version)" >/dev/null 2>&1; then
          PY_BIN=("py" "-3")
          PY_DESC="py -3"
          return 0
        fi
        ;;
      py)
        if py -c "import sys; print(sys.version)" >/dev/null 2>&1; then
          PY_BIN=("py")
          PY_DESC="py"
          return 0
        fi
        ;;
      *)
        if "$c" -c "import sys; print(sys.version)" >/dev/null 2>&1; then
          PY_BIN=("$c")
          PY_DESC="$c"
          return 0
        fi
        ;;
    esac
  done

  return 1
}

if ! resolve_python; then
  echo "[ERROR] 실행 가능한 Python 인터프리터를 찾지 못했습니다."
  echo "        - .venv 생성/설치:  python -m venv .venv"
  echo "        - 패키지 설치:      <venv>/bin/pip or <venv>/Scripts/pip install -r requirements.txt"
  echo "        - 또는 시스템 PATH에 python/python3/py를 추가하세요."
  exit 1
fi

echo "[INFO] PYTHON = ${PY_DESC}"
"${PY_BIN[@]}" --version || { echo "[ERROR] python 실행 불가"; exit 1; }

# (선택) venv 활성화를 시도하되 실패해도 계속 진행 (우린 PY_BIN으로 실행 가능)
if [ -f ".venv/Scripts/activate" ]; then
  # shellcheck disable=SC1091
  source ".venv/Scripts/activate" || true
elif [ -f ".venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source ".venv/bin/activate" || true
fi

# --------------------------------------------------------------------
# 2) OpenRGB 서버 실행 (Windows 전용, PowerShell 사용)
#    - Git Bash 경로 → Windows 경로 변환
#    - 콘솔 붙지 않도록 Start-Process 사용
# --------------------------------------------------------------------
OPENRGB_EXE="bin/windows/OpenRGB.exe"
if [ -f "$OPENRGB_EXE" ]; then
  abs_exe="$(pwd)/$OPENRGB_EXE"

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

  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command \
    "Start-Process -FilePath '$win_exe' -ArgumentList '--server','--startminimized' -WorkingDirectory '$win_workdir' -WindowStyle Minimized"

  sleep 0.6
else
  echo "[WARN] $OPENRGB_EXE 파일이 없어요. 건너뜀."
fi

# --------------------------------------------------------------------
# 3) 포트 대기 (여기독을 파일로 만들어 어떤 파이썬이든 안전 실행)
# --------------------------------------------------------------------
echo "[INFO] wait OpenRGB: 127.0.0.1:6742 (최대 12초)"

TMPPY="$(mktemp "${TMPDIR:-/tmp}/wait_openrgb_XXXXXX.py")"
cat >"$TMPPY" <<'PY'
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
"${PY_BIN[@]}" "$TMPPY"
rm -f "$TMPPY"

# --------------------------------------------------------------------
# 4) 컨트롤러 실행 (항상 우리가 해상도한 파이썬으로)
# --------------------------------------------------------------------
echo "[INFO] run: python controller/main.py"
exec "${PY_BIN[@]}" controller/main.py