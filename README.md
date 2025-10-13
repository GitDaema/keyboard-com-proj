# Keyboard COM Project ??RGB Keyboard CPU/ISA Visualizer

?�픈RGB(OpenRGB)?� `openrgb-python`???�용???�보??RGB�??�어?�며, 8비트 ?�산�?간단???�어/ISA�??�보?�의 LED�??�각?�하???�험???�로?�트?�니?? ??�??�을 ?�태 ?�현???�용?�여 ?�음??구현?�니??
- ?�산 ?�스/결과 비트(SRC1/SRC2/RES)
- ?�래�?Z/N/V/C)
- ?�로그램 카운??PC)
- 명령???��??�터(IR: F1~F12)
- ?�이?�라???�테?��?(FETCH/DECODE/EXECUTE/WRITEBACK)

주요 ?�드?�어 ?�깃�? Corsair K70 RGB TKL?�며, OpenRGB가 지?�하???�른 ?�보?�도 맵만 맞추�??�작?�니??

참고 문서: `LANGUAGE_SPEC_KO.txt`(?�어/?�서 개요), `ISA_ENCODING_KO.txt`(ISA 2바이???�코??규칙)

---

## 주요 기능

- OpenRGB ?�버(127.0.0.1:6742) ?�결 �??�전??초기??`src/rgb_controller.py`)
- ?�벨 기반 ??매핑(`src/utils/keyboard_map.py` + `data/maps/*_leds.json`)
- 배치 ?�데?�트(깜빡??최소??, ?�일 ???�기/?�기 API
- 비트 그룹 ?�시/?�기(`src/utils/bitgroups.py`), 8비트 �?LUT ?�각??복호(`src/sim/data_memory_rgb_visual.py`)
- 고수준 문장 ???�처�?preprocess) ??ISA(2바이?? ?�셈�?`src/sim/assembler.py`, `src/sim/parser.py`)
- CPU ?�행 루프(ISA/마이?�로 모드), IR/PC/Stage/Flags ?�시�??�시(`src/sim/cpu.py`)
- IR(F1~F12) 4비트 OP/DST + 8비트 ARG ?�각??�???��??`src/utils/ir_indicator.py`)
- PC�??�자??1..0)�?2?�리 10진수 ?�시(`src/utils/pc_indicator.py`)
- Stage�?방향?�로 ?�시(`src/utils/stage_indicator.py`), RUN/PAUSE ?�디케?�터(`src/utils/run_pause_indicator.py`)

---

## ?�렉?�리 구조

- `src/main.py`: ?�모 ?�트�? OpenRGB ?�결/초기????CPU 구성 ???�로그램 로드/?�행
- `src/rgb_controller.py`: OpenRGB ?�결/?�제, direct 모드, ?�괄 ???�용, ?�벨?�인?�스 �?주입
- `src/sim/`
  - `cpu.py`: CPU, ISA ?�행, IR/PC/Stage 갱신, ?�터?�티�??�행 지??  - `assembler.py`: 2바이??ISA(OP4|DST4, ARG8) ?�셈�? BR/JMP/EXTI ??지??  - `parser.py`: 고수준 구문 ?�싱, IF/THEN/ELSE/END ?�처�?`preprocess_program`)
  - `program_memory.py`: ?�이�??�축 ?�???�이�??�인?� 주소 ?�모 X)
  - `data_memory_rgb_visual.py`: 값↔RGB LUT, 비트 ?�래�??�정 ?�독
  - `pc.py`, `ir.py`: ?�순 ?�태 보�?
- `src/utils/`
  - `keyboard_presets.py`: ???�벨 ?�리?? 비트 그룹(SRC1/SRC2/RES), Flags, PC/IR ??규칙
  - `keyboard_map.py`: JSON ?�이?�웃?�라�?매핑(별칭 규칙 ?�함)
  - `bitgroups.py`, `bit_lut.py`: 비트 ?�시/?�산 보조
  - `ir_indicator.py`, `pc_indicator.py`, `stage_indicator.py`, `run_pause_indicator.py`
  - `export_led_map.py`: ?�재 ?�보?�의 LED 맵을 JSON/CSV�?추출
  - `asm_listing.py`: ?�스 ?�인?�근??기계코드 listing 출력
- `data/maps/`: ?�보??LED �?JSON/CSV. 기본�? `Corsair K70 RGB TKL_leds.json`
- `scripts/run_demo_windows.sh`: Windows?�서 OpenRGB ?�동 기동 ???�모 ?�행
- `requirements.txt`: Python ?�존??목록(?�재 `openrgb-python`)

---

## ?�치 �??�행

?�전 준�?- Python 3.9 ?�상 권장(?�?�힌???�용 �?최신 문법)
- OpenRGB ?�플리�??�션 ?�치(?�버 모드 ?�용). iCUE/Razer Synapse ??벤더 ?�프?�웨?�는 종료 ?�요

?�존???�치
```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt    # Windows
# ?�는
.venv/bin/pip install -r requirements.txt        # macOS/Linux
```

?�행 방법
- Windows 권장: OpenRGB ?�동 기동 + ?�모 ?�행
```bash
./scripts/run_demo_windows.sh
```
- ?�동 ?�행(모든 OS): OpenRGB ?�버�?직접 ?�행?????�이???�행
```bash
# OpenRGB�?--server �??�행(?�트 6742)
python src/main.py
```

참고
- `bin/windows/OpenRGB.exe`�??�면 ?�크립트가 ?�동 기동?�니?? ?�으�?기존 ?�행 �??�버???�결?�니??
- 최초 초기?????�체 LED�?블랙?�로 ?�괄 ?�용?�여 ?�광/깜빡?�을 최소?�합?�다.

---

## ?�보??맵핑(?�른 모델 ?�용)

1) OpenRGB�??�재 ?�보??LED ?�보�?추출
```bash
python src/utils/export_led_map.py
```
2) ?�성??`data/maps/<모델>_leds.json`???�용?�도�?경로�?지??- 기본값�? `src/rgb_controller.py` ??`map_path = MAPS_DIR / "Corsair K70 RGB TKL_leds.json"` ?�니?? ?�용?�는 모델 JSON ?�일명으�?변경하?�요.
3) ?�벨 매칭???�락?�면 경고가 출력?�니?? ?�요??경우 `src/utils/keyboard_map.py`??`ALIASES`�?보강?�거??JSON??`name_raw`�??�인???�벨??맞춰주세??

---

## 고수준 ?�어/ISA ?�약

- �?범위: 8비트 signed(-128..127). ?�래�? Z/N/V(+C)
- 고수준: ?�???�술/비트/?�프???�이�?분기 + `IF ... THEN [ELSE] END` 블록
- ?�처�?`preprocess_program`)�?블록???�탄???? ?�셈블러가 2바이??ISA�?변??- ISA ?�식: Byte0 = OP4|DST4, Byte1 = ARG8. 분기/?�프??rel8, 즉시 비교(CMPI)??EXTI ?�리?�스 ?�용
- ?�세??규칙?� `LANGUAGE_SPEC_KO.txt`, `ISA_ENCODING_KO.txt` 참고

---

## ?�모 ?�로그램 ?�정

- ?�모 ?�스??`src/main.py` ??`program` 리스?�에 ?�드코딩?�어 ?�습?�다. ??
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

## ?�러블슈??
- [RuntimeError] ?�보???�치�?찾�? 못함: OpenRGB ?�버가 켜져 ?�고, 벤더 ?�프?�웨??iCUE ??가 종료?�었?��? ?�인
- Stage ?�벨 ?�락 경고: ?�용 중인 �?JSON?�서 방향??`Up/Down/Left/Right`)??`name_raw`�??�인?�고 `ALIASES`/JSON??보강
- ?�상 초기???�광: `init_all_keys()`가 ?�작/종료 ????�?초기?�합?�다. 그래???�광???�으�?OpenRGB ?�시??권장
- ?�트/?�속: 기본 `127.0.0.1:6742`. 변경하?�면 `src/rgb_controller.py`??`OpenRGBClient(...)` ?�정???�정

---

## ?�구 ?�항

- Python 3.9+
- OpenRGB + `openrgb-python==0.3.5`
- OpenRGB가 지?�하??RGB ?�보???? Corsair K70 RGB TKL)

---

## Notes (English)

- This project maps an 8-bit CPU?�s state onto RGB keyboard LEDs using OpenRGB.
- The code lives under `src/` (not `controller/` as older docs stated).
- See `LANGUAGE_SPEC_KO.txt` and `ISA_ENCODING_KO.txt` for the language and 2-byte ISA encoding used by the demo CPU.


## Direct HID Backend (No OpenRGB)

- OpenRGB is no longer required to run the project. The default backend talks directly to the keyboard via HID (Windows-first; macOS possible later).
- Requirements: Python 3.9+, `hidapi` (PyPI). Install with: `pip install -r requirements.txt`.
- Supported model (initial): Corsair K70 RGB TKL.
- No USB driver replacement is needed (uses HID). Vendor services (e.g., iCUE) may still interfere; close them if access fails.

Run
- `python src/main.py`
- Optional: set `RGB_BACKEND=hid` (default). Use `RGB_ATOMIC_DEBUG=1` for verbose LED batch logs.
