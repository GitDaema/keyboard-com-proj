# Keyboard COM Project — RGB Keyboard CPU/ISA Visualizer

오픈RGB(OpenRGB)와 `openrgb-python`을 사용해 키보드 RGB를 제어하며, 8비트 연산과 간단한 언어/ISA를 키보드의 LED로 시각화하는 실험용 프로젝트입니다. 키 별 색을 상태 표현에 활용하여 다음을 구현합니다:
- 연산 소스/결과 비트(SRC1/SRC2/RES)
- 플래그(Z/N/V/C)
- 프로그램 카운터(PC)
- 명령어 레지스터(IR: F1~F12)
- 파이프라인 스테이지(FETCH/DECODE/EXECUTE/WRITEBACK)

주요 하드웨어 타깃은 Corsair K70 RGB TKL이며, OpenRGB가 지원하는 다른 키보드도 맵만 맞추면 동작합니다.

참고 문서: `LANGUAGE_SPEC_KO.txt`(언어/파서 개요), `ISA_ENCODING_KO.txt`(ISA 2바이트 인코딩 규칙)

---

## 주요 기능

- OpenRGB 서버(127.0.0.1:6742) 연결 및 안전한 초기화(`src/rgb_controller.py`)
- 라벨 기반 키 매핑(`src/utils/keyboard_map.py` + `data/maps/*_leds.json`)
- 배치 업데이트(깜빡임 최소화), 단일 키 읽기/쓰기 API
- 비트 그룹 표시/읽기(`src/utils/bitgroups.py`), 8비트 값 LUT 시각화/복호(`src/sim/data_memory_rgb_visual.py`)
- 고수준 문장 → 전처리(preprocess) → ISA(2바이트) 어셈블(`src/sim/assembler.py`, `src/sim/parser.py`)
- CPU 실행 루프(ISA/마이크로 모드), IR/PC/Stage/Flags 실시간 표시(`src/sim/cpu.py`)
- IR(F1~F12) 4비트 OP/DST + 8비트 ARG 시각화 및 역복호(`src/utils/ir_indicator.py`)
- PC를 숫자열(1..0)로 2자리 10진수 표시(`src/utils/pc_indicator.py`)
- Stage를 방향키로 표시(`src/utils/stage_indicator.py`), RUN/PAUSE 인디케이터(`src/utils/run_pause_indicator.py`)

---

## 디렉터리 구조

- `src/main.py`: 데모 엔트리. OpenRGB 연결/초기화 → CPU 구성 → 프로그램 로드/실행
- `src/rgb_controller.py`: OpenRGB 연결/해제, direct 모드, 일괄 색 적용, 라벨→인덱스 맵 주입
- `src/sim/`
  - `cpu.py`: CPU, ISA 실행, IR/PC/Stage 갱신, 인터랙티브 실행 지원
  - `assembler.py`: 2바이트 ISA(OP4|DST4, ARG8) 어셈블, BR/JMP/EXTI 등 지원
  - `parser.py`: 고수준 구문 파싱, IF/THEN/ELSE/END 전처리(`preprocess_program`)
  - `program_memory.py`: 레이블 압축 저장(레이블 라인은 주소 소모 X)
  - `data_memory_rgb_visual.py`: 값↔RGB LUT, 비트 플래그 안정 판독
  - `pc.py`, `ir.py`: 단순 상태 보관
- `src/utils/`
  - `keyboard_presets.py`: 키 라벨 프리셋, 비트 그룹(SRC1/SRC2/RES), Flags, PC/IR 색 규칙
  - `keyboard_map.py`: JSON 레이아웃→라벨 매핑(별칭 규칙 포함)
  - `bitgroups.py`, `bit_lut.py`: 비트 표시/연산 보조
  - `ir_indicator.py`, `pc_indicator.py`, `stage_indicator.py`, `run_pause_indicator.py`
  - `export_led_map.py`: 현재 키보드의 LED 맵을 JSON/CSV로 추출
  - `asm_listing.py`: 소스 라인→근사 기계코드 listing 출력
- `data/maps/`: 키보드 LED 맵 JSON/CSV. 기본값: `Corsair K70 RGB TKL_leds.json`
- `scripts/run_demo_windows.sh`: Windows에서 OpenRGB 자동 기동 후 데모 실행
- `requirements.txt`: Python 의존성 목록(현재 `openrgb-python`)

---

## 설치 및 실행

사전 준비
- Python 3.9 이상 권장(타입힌트 사용 및 최신 문법)
- OpenRGB 애플리케이션 설치(서버 모드 사용). iCUE/Razer Synapse 등 벤더 소프트웨어는 종료 필요

의존성 설치
```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt    # Windows
# 또는
.venv/bin/pip install -r requirements.txt        # macOS/Linux
```

실행 방법
- Windows 권장: OpenRGB 자동 기동 + 데모 실행
```bash
./scripts/run_demo_windows.sh
```
- 수동 실행(모든 OS): OpenRGB 서버를 직접 실행한 뒤 파이썬 실행
```bash
# OpenRGB를 --server 로 실행(포트 6742)
python src/main.py
```

참고
- `bin/windows/OpenRGB.exe`를 두면 스크립트가 자동 기동합니다. 없으면 기존 실행 중 서버에 연결합니다.
- 최초 초기화 시 전체 LED를 블랙으로 일괄 적용하여 잔광/깜빡임을 최소화합니다.

---

## 키보드 맵핑(다른 모델 사용)

1) OpenRGB로 현재 키보드 LED 정보를 추출
```bash
python src/utils/export_led_map.py
```
2) 생성된 `data/maps/<모델>_leds.json`을 사용하도록 경로를 지정
- 기본값은 `src/rgb_controller.py` 내 `map_path = MAPS_DIR / "Corsair K70 RGB TKL_leds.json"` 입니다. 사용하는 모델 JSON 파일명으로 변경하세요.
3) 라벨 매칭이 누락되면 경고가 출력됩니다. 필요한 경우 `src/utils/keyboard_map.py`의 `ALIASES`를 보강하거나 JSON의 `name_raw`를 확인해 라벨을 맞춰주세요.

---

## 고수준 언어/ISA 요약

- 값 범위: 8비트 signed(-128..127). 플래그: Z/N/V(+C)
- 고수준: 대입/산술/비트/시프트/레이블/분기 + `IF ... THEN [ELSE] END` 블록
- 전처리(`preprocess_program`)로 블록을 평탄화 후, 어셈블러가 2바이트 ISA로 변환
- ISA 형식: Byte0 = OP4|DST4, Byte1 = ARG8. 분기/점프는 rel8, 즉시 비교(CMPI)는 EXTI 프리픽스 사용
- 자세한 규칙은 `LANGUAGE_SPEC_KO.txt`, `ISA_ENCODING_KO.txt` 참고

---

## 데모 프로그램 수정

- 데모 소스는 `src/main.py` 내 `program` 리스트에 하드코딩되어 있습니다. 예:
```python
program = [
    "start:",
    "a = -7",
    "x = 5",
    "s = 0",
    "s = a",
    "SHL s",
    "SHR s",
    "IF a < #0 THEN",
    "    a = 0 - a",
    "END",
    "IF a == x THEN",
    "    d = 1",
    "ELSE",
    "    d = 0",
    "END",
    "loop:",
    "CMPI a, #5",
    "BEQ done",
    "a = a - 1",
    "JMP loop",
    "done:",
    "HALT",
]
```

---

## 트러블슈팅

- [RuntimeError] 키보드 장치를 찾지 못함: OpenRGB 서버가 켜져 있고, 벤더 소프트웨어(iCUE 등)가 종료되었는지 확인
- Stage 라벨 누락 경고: 사용 중인 맵 JSON에서 방향키(`Up/Down/Left/Right`)의 `name_raw`를 확인하고 `ALIASES`/JSON을 보강
- 색상 초기화/잔광: `init_all_keys()`가 시작/종료 시 두 번 초기화합니다. 그래도 잔광이 있으면 OpenRGB 재시작 권장
- 포트/접속: 기본 `127.0.0.1:6742`. 변경하려면 `src/rgb_controller.py`의 `OpenRGBClient(...)` 설정을 수정

---

## 요구 사항

- Python 3.9+
- OpenRGB + `openrgb-python==0.3.5`
- OpenRGB가 지원하는 RGB 키보드(예: Corsair K70 RGB TKL)

---

## Notes (English)

- This project maps an 8-bit CPU’s state onto RGB keyboard LEDs using OpenRGB.
- The code lives under `src/` (not `controller/` as older docs stated).
- See `LANGUAGE_SPEC_KO.txt` and `ISA_ENCODING_KO.txt` for the language and 2-byte ISA encoding used by the demo CPU.

