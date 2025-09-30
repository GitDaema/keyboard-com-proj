# keyboard_presets
# 키보드 LED 기반 컴퓨터 구조 시뮬레이터용 프리셋
# - LSB = 오른쪽, MSB = 왼쪽
# - 레지스터 = 연산 중 잠깐 들고 있는 작업 공간 (SRC1, SRC2, RES)
# - 메모리 = 변수의 집 (니블 2개, 무지개 16색으로 표현)  # (메모리 니블은 별도 구현과 연동)
# - IR(F1~F12) = 현재 실행 중인 명령어
# - PC(별도 블록) = 명령어 위치

# ---------------------------------------------------------------------
# 레지스터 (작업 공간, 3개)
# ---------------------------------------------------------------------
# 주의: 배열의 '오른쪽 끝 요소'가 LSB가 되도록 배치
SRC1 = ["t", "y", "u", "i", "o", "p", "lbracket", "rbracket"]   # $s1 : 피연산자1, 8비트 (왼→오: MSB..LSB)
SRC2 = ["f", "g", "h", "j", "k", "l", "semicolon", "quote"]     # $s2 : 피연산자2, 8비트 (왼→오: MSB..LSB)
RES  = ["c", "v", "b", "n", "m", "comma", "period", "slash"]     # $r  : 결과 레지스터, 8비트 (왼→오: MSB..LSB)

# ---------------------------------------------------------------------
# 불리언 LED용 온/오프 색 (비트/플래그 공통)
# ---------------------------------------------------------------------
_ON  = (0, 255, 0)     # ON:  초록
_OFF = (120, 0, 0)     # OFF: 어두운 적색

# ---------------------------------------------------------------------
# CPU/메모리에서 불리언 LED로 인식할 키 집합
# (DataMemoryRGBVisual.get/set 이 이 목록에 있는 라벨은 0/1로 다룸)
# - 비트 레지스터(SRC1/SRC2/RES)의 각 라벨은 반드시 여기에 등록되어야 함
# - 이후 FLAG_LABELS(아래)도 병합하여 플래그 LED를 불리언으로 처리
# ---------------------------------------------------------------------
BINARY_COLORS = {}

# 비트 레지스터용 불리언 색 매핑
BINARY_COLORS.update({k: (_ON, _OFF) for k in SRC1})
BINARY_COLORS.update({k: (_ON, _OFF) for k in SRC2})
BINARY_COLORS.update({k: (_ON, _OFF) for k in RES})

# ---------------------------------------------------------------------
# IR (명령어 레지스터)
# ---------------------------------------------------------------------
# 12개 키로 16비트(2바이트) 표현: 4키는 2비트(4색), 8키는 1비트(온/오프)
# - 2비트 키: F1,F2(Opcode 상위/하위 2비트), F3,F4(DST 상위/하위 2비트)
# - 1비트 키: F5~F12 (ARG Byte: b7..b0)
IR12 = ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12"]
IR_OP_2BIT = ["F1", "F2"]         # OP[3:2], OP[1:0]
IR_DST_2BIT = ["F3", "F4"]        # DST[3:2], DST[1:0]
IR_ARG_1BIT = ["F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12"]  # ARG[7]..ARG[0]

# Unified IR mapping (binary OP/DST bits, quaternary ARG pairs)
# - OP bits on F1..F4 (MSB..LSB)
# - DST bits on F5..F8 (MSB..LSB)
# - ARG pairs on F9..F12: ARG[7:6], ARG[5:4], ARG[3:2], ARG[1:0]
IR_OP_1BIT = ["F1", "F2", "F3", "F4"]
IR_DST_1BIT = ["F5", "F6", "F7", "F8"]
IR_ARG_2BIT = ["F9", "F10", "F11", "F12"]

# 역할별 팔레트(가시성 최적화)
# 1비트 모드(온/오프) — 키보드 LED에서 선명하게 보이도록 고채도/고대비 색상 사용
IR_ONOFF = {
    # OP: 시안톤(밝고 차가운 계열) — ARG 4상과 혼동 최소화
    "OP":  ((0, 200, 255), (0, 0, 0)),
    # DST: 앰버/오렌지톤(따뜻한 계열) — OP와 명확히 구분
    "DST": ((255, 140, 0), (0, 0, 0)),
    # ARG/IMM(레거시 1비트 경로용): 고가시성 앰버, OFF는 블랙
    "ARG": ((255, 180, 0), (0, 0, 0)),
}

# 2비트 모드(4색) — 요청에 따라 고정 매핑
#   0 → 빨강, 1 → 초록, 2 → 파랑, 3 → 하양
IR_4STATE = {
    # 일반 4상 팔레트(예비): 강한 원색/보색 위주
    "OP": [
        (255, 64, 64),   # 00 -> Red (밝은 레드)
        (64, 255, 96),   # 01 -> Green (라임 그린)
        (64, 128, 255),  # 10 -> Blue (라이트 블루)
        (255, 255, 64),  # 11 -> Yellow (밝은 옐로)
    ],
    "DST": [
        (255, 64, 64),
        (64, 255, 96),
        (64, 128, 255),
        (255, 255, 64),
    ],
    # ARG 전용 4상 팔레트: 서로 최대한 떨어진 색상군으로 구성
    #  - 00: Red, 01: Amber, 10: Cyan, 11: Violet
    #  키보드 LED에서 색상 분리가 뚜렷하고 난반사가 적게 보이는 값으로 조정
    "ARG": [
        (255, 64, 64),    # 00 -> Red
        (255, 170, 0),    # 01 -> Amber
        (0, 200, 255),    # 10 -> Cyan
        (170, 64, 255),   # 11 -> Violet
    ],
}

# 변수 → 4비트 ID (IR 표시/간이 어셈 인코딩용)
VAR_TO_ID = {
    "q": 0x0, "w": 0x1, "e": 0x2, "r": 0x3,
    "a": 0x4, "s": 0x5, "d": 0x6,
    "z": 0x7, "x": 0x8,
}

# Reverse mapping (ID -> variable name)
ID_TO_VAR = {v: k for k, v in VAR_TO_ID.items()}

# ---------------------------------------------------------------------
# PC (프로그램 카운터, 10진 표시안)
# ---------------------------------------------------------------------
# 10개의 LED로 0~9까지 표시(십의 자리/일의 자리 등 외부 로직과 결합)
PC = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"]

# ---------------------------------------------------------------------
# CPU 플래그 LED 전용 프리셋
# 왼쪽 하단 키 예시: Z=Left Control, N=Left Windows, V=Left Alt
# (실제 키 라벨은 장치에 맞게 조정 가능)
# ---------------------------------------------------------------------
FLAG_LABELS = {
    "Z": "left_ctrl",  # Zero flag
    "N": "left_win",   # Negative flag
    "V": "left_alt",   # oVerflow flag
}

# 플래그 LED 색상(가독성 좋은 별도 팔레트 사용)
BINARY_COLORS.update({
    "left_ctrl": ((0, 255, 64), (80, 80, 80)),   # Z
    "left_win":  ((0, 128, 255), (80, 80, 80)),  # N
    "left_alt":  ((255, 200, 0), (80, 80, 80)),  # V
})

# 산술 단계 표시용(플래그처럼 사용): Cin/Bin, Sum/Diff, Cout/Bout
# - backslash:  Cin/Bin (시작 캐리/차용)
# - enter:     Sum/Diff (해당 비트의 합/차)
# - right_shift: Cout/Bout (다음 비트로 전달 캐리/차용)
STEP_LABELS = {
    "CIN":  "backslash",
    "SUM":  "enter",
    "COUT": "right_shift",
}

BINARY_COLORS.update({
    STEP_LABELS["CIN"]:  ((255, 255, 0), (60, 60, 60)),   # 노랑
    STEP_LABELS["SUM"]:  ((255, 255, 255), (60, 60, 60)), # 흰색
    STEP_LABELS["COUT"]: ((255, 0, 255), (60, 60, 60)),   # 자홍
})

# 사용자가 변수로 사용한다고 지정한 키 목록
VARIABLE_KEYS = {'q', 'w', 'e', 'r', 'a', 's', 'd', 'z', 'x'}

# ---------------------------------------------------------------------
# Memory/IO Bus control signals mapped to right-hand modifier cluster
#   - ADDR_VALID: right_alt (Cyan)
#   - MEM_RD:     right_fn  (White)
#   - MEM_WR:     menu      (Bright Orange)
#   - ACK/BUSY:   right_ctrl(Purple)
# These act as real handshake lines (read/written) via utils/bus.py
# ---------------------------------------------------------------------
BUS_ADDR_VALID = "right_alt"
BUS_RD         = "right_fn"
BUS_WR         = "menu"
BUS_ACK        = "right_ctrl"

# Visual encoding for the bus control lines (ON, OFF)
BINARY_COLORS.update({
    BUS_ADDR_VALID: ((0, 255, 255), (60, 60, 60)),   # Cyan / Dark Gray
    BUS_RD:         ((255, 255, 255), (60, 60, 60)), # White / Dark Gray
    BUS_WR:         ((255, 210, 20), (60, 60, 60)),  # Bright Orange / Dark Gray
    BUS_ACK:        ((170, 0, 170),  (60, 60, 60)),  # Purple / Dark Gray
})

# ---------------------------------------------------------------------
# RUN/PAUSE indicator (single key + adjustable colors)
# ---------------------------------------------------------------------
# 표시 전용 키: CPU가 실행 중이면 ON, 대기/정지면 OFF
# - 라벨/색은 장치/테마에 맞춰 조정 가능
RUN_PAUSE_LABEL = "grave"
RUN_PAUSE_ON  = (0, 255, 0)  # Green
RUN_PAUSE_OFF = (0,   0, 0)  # Black

# ---------------------------------------------------------------------
# Control-plane key labels (used as input switches via LED readback)
#   - ESC: Emergency Halt / Reset
#   - TAB: Step mode selector (continuous / instruction-step / micro-step)
#   - CAPS_LOCK: Trace gate / marker
#   - LEFT_SHIFT: Overlay/Service selector
# These are labels resolved by keyboard_map.ALIAS and exist in the map JSON.
# ---------------------------------------------------------------------
KEY_ESC_LABEL       = "esc"
KEY_TAB_LABEL       = "tab"
KEY_CAPS_LABEL      = "caps_lock"
KEY_LSHIFT_LABEL    = "left_shift"

# ---------------------------------------------------------------------
# Carry Flag (C) persistent indicator
# ---------------------------------------------------------------------
# 백스페이스바 LED를 상주 Carry 플래그로 사용
CARRY_FLAG_LABEL = "backspace"
CARRY_ON  = (255, 64, 64)   # 밝은 레드
CARRY_OFF = (80, 80, 80)    # 소등(회색)

# 플래그 매핑에 C 추가
FLAG_LABELS.update({
    "C": CARRY_FLAG_LABEL,
})

# C 플래그 LED 색상 등록
BINARY_COLORS.update({
    CARRY_FLAG_LABEL: (CARRY_ON, CARRY_OFF),
})
