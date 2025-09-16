#!/usr/bin/env bash
set -euo pipefail

echo "=== run_demo_windows.sh: START ==="

# -u 안전을 위한 초기값
PY_DESC=""
PY_BIN=()

# 0) 프로젝트 루트로 이동
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

  # venv 먼저
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
    candidates+=("py3")  # py -3
    candidates+=("py")   # py
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
  echo "        - 패키지 설치:      <venv>/bin/pip 또는 <venv>/Scripts/pip install -r requirements.txt"
  echo "        - 또는 시스템 PATH에 python/python3/py를 추가하세요."
  exit 1
fi

echo "[INFO] PYTHON = ${PY_DESC}"
"${PY_BIN[@]}" --version || { echo "[ERROR] python 실행 불가"; exit 1; }

# (선택) venv 활성화 시도(우리는 PY_BIN으로 실행하므로 실패해도 계속)
if [ -f ".venv/Scripts/activate" ]; then
  # shellcheck disable=SC1091
  source ".venv/Scripts/activate" || true
elif [ -f ".venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source ".venv/bin/activate" || true
fi

# --------------------------------------------------------------------
# 2) OpenRGB 서버 실행(Windows 전용)
#    - 이미 서버(6742)가 떠 있으면 재기동하지 않음
#    - 우리가 띄운 경우에만 PID를 기록해 종료 시 정리
# --------------------------------------------------------------------
to_win_path() {
  local p="$1"
  if command -v wslpath >/dev/null 2>&1; then
    wslpath -w "$p"; return
  fi
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -w "$p"; return
  fi
  printf '%s' "$p" | sed -E 's#^/([a-zA-Z])/#\U\1:/#; s#/#\\#g'
}

echo "[INFO] check OpenRGB server (pre-start)"
SERVER_UP=false
if command -v powershell.exe >/dev/null 2>&1; then
  if powershell.exe -NoLogo -NoProfile -Command \
    "(Test-NetConnection -ComputerName 127.0.0.1 -Port 6742 -WarningAction SilentlyContinue).TcpTestSucceeded" \
    | tr -d '\r' | grep -qi 'True'; then
    SERVER_UP=true
  fi
else
  # bash에서 TCP 오픈 체크(일부 환경에서 미지원일 수 있음)
  if (echo > /dev/tcp/127.0.0.1/6742) >/dev/null 2>&1; then
    SERVER_UP=true
  fi
fi

STARTED_OPENRGB=0
OPENRGB_PID_FILE=".openrgb_server.pid"

OPENRGB_EXE="bin/windows/OpenRGB.exe"
if [ "$SERVER_UP" = false ] && [ -f "$OPENRGB_EXE" ]; then
  abs_exe="$(pwd)/$OPENRGB_EXE"
  win_exe="$(to_win_path "$abs_exe")"
  win_workdir="$(to_win_path "$(pwd)/bin/windows")"

  echo "[INFO] OpenRGB exe (Windows path) = $win_exe"
  echo "[INFO] OpenRGB workdir            = $win_workdir"

  # PassThru로 PID 확보
  OPENRGB_PID=$(
    powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command \
      "\$p = Start-Process -FilePath '$win_exe' -ArgumentList '--server','--startminimized' -WorkingDirectory '$win_workdir' -WindowStyle Minimized -PassThru; \$p.Id" \
      | tr -d '\r'
  )
  if [ -n "${OPENRGB_PID:-}" ]; then
    echo "$OPENRGB_PID" > "$OPENRGB_PID_FILE"
    STARTED_OPENRGB=1
    echo "[INFO] OpenRGB started (pid=$OPENRGB_PID)"
  else
    echo "[WARN] OpenRGB PID를 얻지 못했습니다(이미 실행 중일 수 있음)."
  fi
else
  if [ "$SERVER_UP" = true ]; then
    echo "[INFO] OpenRGB server already running; skip starting."
  else
    echo "[WARN] $OPENRGB_EXE 없음; OpenRGB는 수동 실행 또는 기존 서버 사용."
  fi
fi

# --------------------------------------------------------------------
# 3) 포트 대기(최대 12초)
#    - Windows 파이썬/py를 쓰는 경우 PowerShell로 대기(경로 이슈 회피)
# --------------------------------------------------------------------
echo "[INFO] wait OpenRGB: 127.0.0.1:6742 (최대 12초)"

is_windows_python=false
case "${PY_DESC,,}" in
  *".exe"*|*"py -3"*|*"py"*) is_windows_python=true ;;
esac

if [ "$is_windows_python" = true ]; then
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command \
    "\$i=0; while(\$i -lt 40) { if ((Test-NetConnection -ComputerName 127.0.0.1 -Port 6742 -WarningAction SilentlyContinue).TcpTestSucceeded) { Write-Output '[OK ] OpenRGB server detected.'; exit 0 }; Start-Sleep -Milliseconds 300; \$i++ }; Write-Output '[ERR] port wait failed'; exit 1"
else
  TMPPY="$(mktemp "${TMPDIR:-/tmp}/wait_openrgb_XXXXXX.py")"
  cat >"$TMPPY" <<'PY'
import socket, time, sys
host, port, timeout = "127.0.0.1", 6742, 12
start = time.time()
while True:
    try:
        with socket.create_connection((host, port), timeout=0.5):
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
fi

# --------------------------------------------------------------------
# 4) 컨트롤러 실행(종료코드 캡처 → 우리가 띄운 OpenRGB만 정리)
# --------------------------------------------------------------------
echo "[INFO] run: python main.py"
set +e
"${PY_BIN[@]}" src/main.py
PY_EXIT=$?
set -e
echo "[INFO] controller exit code = ${PY_EXIT}"

# 우리가 띄웠다면 그 인스턴스만 종료
if [ "${STARTED_OPENRGB}" = "1" ] && [ -f "$OPENRGB_PID_FILE" ]; then
  PID_TO_KILL="$(cat "$OPENRGB_PID_FILE" || true)"
  if [ -n "${PID_TO_KILL:-}" ]; then
    echo "[INFO] stopping OpenRGB we started (pid=$PID_TO_KILL)"
    powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command \
      "Try { Stop-Process -Id $PID_TO_KILL -Force -ErrorAction Stop } Catch { }"
  fi
  rm -f "$OPENRGB_PID_FILE"
fi

exit "${PY_EXIT}"