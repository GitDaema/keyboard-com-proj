# sim/cpu.py
from typing import Dict, Any, List, Tuple

from utils.keyboard_presets import FLAG_LABELS, BINARY_COLORS

from sim.pc import PC
from sim.ir import IR
from sim.data_memory_rgb_visual import DataMemoryRGBVisual
from sim.program_memory import ProgramMemory
from sim.parser import parse_line

"""
# =========================
# CPU/Parser 명령어 정리 (signed 버전)
# =========================
#
# ■ 기본 규칙
# - 모든 계산은 signed 8비트(-128..127)로 동작.
# - 플래그:
#     Z (Zero)      : 결과가 0이면 1
#     N (Negative)  : 결과가 음수(부호비트 1)면 1
#     V (oVerflow)  : signed overflow 발생 시 1 (ADD/SHL/SUB/CMP 등)
# - PC는 "다음 명령어 위치". 보통 한 칸씩 증가하지만,
#   점프/분기(JMP, BEQ 등)가 실행되면 직접 바뀜.
# - 즉시값 표기: #10, #0x1F, #-3 등 모두 허용.
#
# ■ 기본 명령어
# - NOP / LABEL / HALT / PRINT (동일)
#
# ■ 값 넣기 / 더하기 / 빼기
# - MOVI dst, #imm         ; dst ← imm (signed 범위로 래핑 저장)
# - MOV  dst, src          ; dst ← src
# - ADDI dst, #imm         ; dst ← dst + imm (Z/N/V 갱신)
# - ADD  dst, src          ; dst ← dst + src (Z/N/V 갱신)
# - SUBI dst, #imm         ; dst ← dst - imm (Z/N/V 갱신)
# - SUB  dst, src          ; dst ← dst - src (Z/N/V 갱신)
#
# ■ 비트 연산 (Z/N 갱신, V=0)
# - AND/OR/XOR
#
# ■ 시프트
# - SHL dst                ; 산술적 의미의 왼쪽 시프트(최상위 비트 변화로 V 판단)
# - SHR dst                ; 산술 시프트(ASR, 부호 유지). V=0
#
# ■ 비교 / 분기 (signed)
# - CMP a, b               ; a-b의 signed 결과 기반으로 Z/N/V 갱신(결과는 버림)
# - CMPI a, #imm
#
# - JMP label              ; 무조건 분기
# - BEQ/BNE                ; Z=1 / Z=0
# - BMI/BPL                ; N=1 / N=0
# - BVS/BVC                ; V=1 / V=0
#   (하위호환) BCS/BCC     ; V=1 / V=0 로 해석
"""

def _wrap_s8(x: int) -> int:
    return ((int(x) + 128) & 0xFF) - 128

def _to_u8(x: int) -> int:
    return int(x) & 0xFF

def _sign_bit(x: int) -> int:
    return 1 if (_to_u8(x) & 0x80) else 0

def _set_zn_from_val(flags: Dict[str, int], v: int) -> None:
    flags["Z"] = 1 if v == 0 else 0
    flags["N"] = 1 if v < 0 else 0

def _add_s8(a: int, b: int) -> tuple[int, int]:
    """signed 8비트 덧셈: 결과와 overflow(V) 반환"""
    res = _wrap_s8(a + b)
    # overflow 조건: (~(a ^ b) & (a ^ res))의 부호비트가 1
    au, bu, ru = _to_u8(a), _to_u8(b), _to_u8(res)
    v = 1 if (((~(au ^ bu)) & (au ^ ru)) & 0x80) != 0 else 0
    return res, v

def _sub_s8(a: int, b: int) -> tuple[int, int]:
    """signed 8비트 뺄셈: a-b 결과와 overflow(V) 반환"""
    res = _wrap_s8(a - b)
    # overflow 조건: ((a ^ b) & (a ^ res))의 부호비트가 1
    au, bu, ru = _to_u8(a), _to_u8(b), _to_u8(res)
    v = 1 if (((au ^ bu) & (au ^ ru)) & 0x80) != 0 else 0
    return res, v

class CPU:
    def __init__(self, *, debug: bool = False, mem=None, interactive: bool = False) -> None:
        self.pc = PC()
        self.ir = IR()
        self.mem = mem if mem is not None else DataMemoryRGBVisual(binary_labels=BINARY_COLORS)
        self.prog = ProgramMemory()
        self.halted = False
        self.debug = debug

        # 플래그: Zero / Negative / oVerflow
        self.flags: Dict[str, int] = {"Z": 0, "N": 0, "V": 0}
        self._pc_overridden: bool = False

        self.interactive = interactive                         # ← 스텝 실행 플래그
        self._continue_run = False                             # ← 'c' 입력 시 계속 진행

    # ---------- 외부 API ----------
    def load_program(self, lines: List[str]) -> None:
        self.prog.load_program(lines)
        self.pc.reset()
        self.halted = False
        self.ir.clear()
        self.flags["Z"] = 0
        self.flags["N"] = 0
        self.flags["V"] = 0

        # 초기 플래그 상태를 LED에 1회 반영(Off 상태라도 바로 보이게)
        try:
            self._sync_flag_leds()
        except Exception:
            pass

        self._continue_run = False

    def step(self) -> bool:
        if self.halted:
            self._on_halt()
            return False

        line = self.prog.fetch(self.pc.value)
        if line is None:
            self.halted = True
            self._on_halt()
            return False

        self._pc_overridden = False
        self.ir.raw = line
        self._on_fetch(line)

        ops = parse_line(line)
        for op, args in ops:
            self.ir.decoded = (op, args)
            self._on_decode((op, args))
            self._println(
                f"PC:{self.pc.value:02d} | OP:{op:<4} | ARGS:{args} "
                f"| Z:{self.flags['Z']} N:{self.flags['N']} V:{self.flags['V']} "
                f"| b:{getattr(self.mem, 'vars', {}).get('b','N/A')}"
            )
            changes = self._exec_one(op, args)
            self._on_writeback(changes)
            # 플래그 LED 업데이트
            self._sync_flag_leds()
            self._maybe_pause()
            if self.halted or self._pc_overridden:
                break

        old = self.pc.value
        if not self._pc_overridden:
            self.pc.increment(1)
            self._on_pc_advance(old, self.pc.value)
        else:
            self._on_pc_advance(old, self.pc.value)

        self.ir.clear()
        return not self.halted

    def _maybe_pause(self) -> None:
        """interactive 모드면, 한 연산 끝날 때 사용자 입력 대기.
        [Enter]=한 스텝, 'c'=연속 실행, 'q'=즉시 종료"""
        if not self.interactive:
            return
        if self._continue_run:
            return
        try:
            s = input("[step] Enter=next | c=continue | q=quit > ").strip().lower()
        except EOFError:
            s = ""
        if s == "c":
            self._continue_run = True
        elif s == "q":
            self.halted = True

    def _sync_flag_leds(self) -> None:
        """현재 Z/N/V 값을 지정된 키 LED에 반영"""
        if hasattr(self.mem, "set_flag"):
            for k, led in FLAG_LABELS.items():
                self.mem.set_flag(led, bool(self.flags.get(k, 0)))

    def run(self) -> None:
        self._println("\n[RUN] Starting execution...")
        while self.step():
            pass
        self._println("[RUN] Execution finished.\n")

    # ---------- 내부 실행기 ----------
    def _exec_one(self, op: str, args: tuple[Any, ...]) -> Dict[str, int]:
        ch: Dict[str, int] = {}

        # --- NOP/LABEL/HALT/PRINT ---
        if op == "NOP":
            self._on_execute("NOP")
            return ch

        if op == "LABEL":
            name = str(args[0])
            self._on_execute(f"LABEL {name}")
            return ch

        if op == "HALT":
            self._on_execute("HALT")
            self.halted = True
            return ch

        if op == "PRINT":
            var = str(args[0])
            val = self.mem.get(var)
            self._on_execute(f"PRINT {var} -> {val}")
            return ch

        # --- MOV/MOVI ---
        if op == "MOVI":
            dst, imm = args
            self.mem.set(str(dst), int(imm))
            self._on_execute(f"MOVI {dst}, #{imm}")
            ch[str(dst)] = self.mem.get(str(dst))
            return ch

        if op == "MOV":
            dst, src = args
            v = self.mem.get(str(src))
            self.mem.set(str(dst), v)
            self._on_execute(f"MOV  {dst}, {src} ; {dst}={v}")
            ch[str(dst)] = self.mem.get(str(dst))
            return ch

        # --- ADD/ADDI (signed: Z/N/V 갱신) ---
        if op == "ADDI":
            dst, imm = args
            a = self.mem.get(str(dst))
            b = int(imm)
            v, ov = _add_s8(a, b)
            self.mem.set(str(dst), v)
            self.flags["V"] = ov
            _set_zn_from_val(self.flags, v)
            self._on_execute(f"ADDI {dst}, #{imm} ; {dst}:{a}+{b}→{v} | Z={self.flags['Z']} N={self.flags['N']} V={self.flags['V']}")
            ch[str(dst)] = v
            return ch

        if op == "ADD":
            dst, src = args
            a = self.mem.get(str(dst))
            b = self.mem.get(str(src))
            v, ov = _add_s8(a, b)
            self.mem.set(str(dst), v)
            self.flags["V"] = ov
            _set_zn_from_val(self.flags, v)
            self._on_execute(f"ADD  {dst}, {src} ; {dst}:{a}+{b}→{v} | Z={self.flags['Z']} N={self.flags['N']} V={self.flags['V']}")
            ch[str(dst)] = v
            return ch

        # --- SUB/SUBI (signed: Z/N/V 갱신) ---
        if op == "SUBI":
            dst, imm = args
            a = self.mem.get(str(dst))
            b = int(imm)
            v, ov = _sub_s8(a, b)
            self.mem.set(str(dst), v)
            self.flags["V"] = ov
            _set_zn_from_val(self.flags, v)
            self._on_execute(f"SUBI {dst}, #{imm} ; {dst}:{a}-{b}→{v} | Z={self.flags['Z']} N={self.flags['N']} V={self.flags['V']}")
            ch[str(dst)] = v
            return ch

        if op == "SUB":
            dst, src = args
            a = self.mem.get(str(dst))
            b = self.mem.get(str(src))
            v, ov = _sub_s8(a, b)
            self.mem.set(str(dst), v)
            self.flags["V"] = ov
            _set_zn_from_val(self.flags, v)
            self._on_execute(f"SUB  {dst}, {src} ; {dst}:{a}-{b}→{v} | Z={self.flags['Z']} N={self.flags['N']} V={self.flags['V']}")
            ch[str(dst)] = v
            return ch

        # --- 비트 연산 (Z/N 갱신, V=0) ---
        if op == "AND":
            dst, src = args
            a = self.mem.get(str(dst))
            b = self.mem.get(str(src))
            v = _wrap_s8(_to_u8(a) & _to_u8(b))
            self.mem.set(str(dst), v)
            self.flags["V"] = 0
            _set_zn_from_val(self.flags, v)
            self._on_execute(f"AND  {dst}, {src} ; {dst}:{a}&{b}→{v} | Z={self.flags['Z']} N={self.flags['N']}")
            ch[str(dst)] = v
            return ch

        if op == "OR":
            dst, src = args
            a = self.mem.get(str(dst))
            b = self.mem.get(str(src))
            v = _wrap_s8(_to_u8(a) | _to_u8(b))
            self.mem.set(str(dst), v)
            self.flags["V"] = 0
            _set_zn_from_val(self.flags, v)
            self._on_execute(f"OR   {dst}, {src} ; {dst}:{a}|{b}→{v} | Z={self.flags['Z']} N={self.flags['N']}")
            ch[str(dst)] = v
            return ch

        if op == "XOR":
            dst, src = args
            a = self.mem.get(str(dst))
            b = self.mem.get(str(src))
            v = _wrap_s8(_to_u8(a) ^ _to_u8(b))
            self.mem.set(str(dst), v)
            self.flags["V"] = 0
            _set_zn_from_val(self.flags, v)
            self._on_execute(f"XOR  {dst}, {src} ; {dst}:{a}^{b}→{v} | Z={self.flags['Z']} N={self.flags['N']}")
            ch[str(dst)] = v
            return ch

        # --- 시프트 ---
        if op == "SHL":
            dst, = args
            a = self.mem.get(str(dst))
            v = _wrap_s8(a << 1)
            # SHL overflow: 최상위 비트 변화 여부로 판단
            ov = 1 if (_sign_bit(a) != _sign_bit(v)) else 0
            self.mem.set(str(dst), v)
            self.flags["V"] = ov
            _set_zn_from_val(self.flags, v)
            self._on_execute(f"SHL  {dst} ; {a:4d}<<1 -> {v:4d} | V={ov} Z={self.flags['Z']} N={self.flags['N']}")
            ch[str(dst)] = v
            return ch

        if op == "SHR":
            dst, = args
            a = self.mem.get(str(dst))
            # 산술 시프트(ASR): 파이썬의 >> 는 부호 유지됨
            v = _wrap_s8(a >> 1)
            self.mem.set(str(dst), v)
            self.flags["V"] = 0
            _set_zn_from_val(self.flags, v)
            self._on_execute(f"SHR  {dst} ; {a:4d}>>1 -> {v:4d} | V=0 Z={self.flags['Z']} N={self.flags['N']}")
            ch[str(dst)] = v
            return ch

        # --- 비교/분기 ---
        if op == "CMP":
            a, b = args
            va = self.mem.get(str(a))
            vb = self.mem.get(str(b))
            res, ov = _sub_s8(va, vb)
            self.flags["V"] = ov
            _set_zn_from_val(self.flags, res)
            self._on_execute(f"CMP  {a}, {b} ; ({va}-{vb}) → Z={self.flags['Z']} N={self.flags['N']} V={self.flags['V']}")
            return ch

        if op == "CMPI":
            a, imm = args
            va = self.mem.get(str(a))
            vb = int(imm)
            res, ov = _sub_s8(va, vb)
            self.flags["V"] = ov
            _set_zn_from_val(self.flags, res)
            self._on_execute(f"CMPI {a}, #{imm} ; ({va}-{vb}) → Z={self.flags['Z']} N={self.flags['N']} V={self.flags['V']}")
            return ch

        if op == "JMP":
            label = str(args[0])
            addr = self._resolve_label(label)
            if addr is None:
                self._on_execute(f"JMP {label} ; <LABEL NOT FOUND> -> HALT")
                self.halted = True
                return ch
            self.pc.value = addr
            self._pc_overridden = True
            self._on_execute(f"JMP  {label} ; PC←{addr:02d}")
            return ch

        if op == "BEQ":
            label = str(args[0])
            if self.flags.get("Z", 0) == 1:
                addr = self._resolve_label(label)
                if addr is None:
                    self._on_execute(f"BEQ {label} ; <LABEL NOT FOUND> -> HALT")
                    self.halted = True
                    return ch
                self.pc.value = addr
                self._pc_overridden = True
                self._on_execute(f"BEQ  {label} ; Z=1 → PC←{addr:02d}")
            else:
                self._on_execute(f"BEQ  {label} ; Z=0 → no-branch")
            return ch

        if op == "BNE":
            label = str(args[0])
            if self.flags.get("Z", 0) == 0:
                addr = self._resolve_label(label)
                if addr is None:
                    self._on_execute(f"BNE {label} ; <LABEL NOT FOUND> -> HALT")
                    self.halted = True
                    return ch
                self.pc.value = addr
                self._pc_overridden = True
                self._on_execute(f"BNE  {label} ; Z=0 → PC←{addr:02d}")
            else:
                self._on_execute(f"BNE  {label} ; Z=1 → no-branch")
            return ch

        if op == "BMI":
            label = str(args[0])
            if self.flags.get("N", 0) == 1:
                addr = self._resolve_label(label)
                if addr is None:
                    self._on_execute(f"BMI {label} ; <LABEL NOT FOUND> -> HALT")
                    self.halted = True
                    return ch
                self.pc.value = addr
                self._pc_overridden = True
                self._on_execute(f"BMI  {label} ; N=1 → PC←{addr:02d}")
            else:
                self._on_execute(f"BMI  {label} ; N=0 → no-branch")
            return ch

        if op == "BPL":
            label = str(args[0])
            if self.flags.get("N", 0) == 0:
                addr = self._resolve_label(label)
                if addr is None:
                    self._on_execute(f"BPL {label} ; <LABEL NOT FOUND> -> HALT")
                    self.halted = True
                    return ch
                self.pc.value = addr
                self._pc_overridden = True
                self._on_execute(f"BPL  {label} ; N=0 → PC←{addr:02d}")
            else:
                self._on_execute(f"BPL  {label} ; N=1 → no-branch")
            return ch

        # NEW: BVS/BVC
        if op == "BVS":
            label = str(args[0])
            if self.flags.get("V", 0) == 1:
                addr = self._resolve_label(label)
                if addr is None:
                    self._on_execute(f"BVS {label} ; <LABEL NOT FOUND> -> HALT")
                    self.halted = True
                    return ch
                self.pc.value = addr
                self._pc_overridden = True
                self._on_execute(f"BVS  {label} ; V=1 → PC←{addr:02d}")
            else:
                self._on_execute(f"BVS  {label} ; V=0 → no-branch")
            return ch

        if op == "BVC":
            label = str(args[0])
            if self.flags.get("V", 0) == 0:
                addr = self._resolve_label(label)
                if addr is None:
                    self._on_execute(f"BVC {label} ; <LABEL NOT FOUND> -> HALT")
                    self.halted = True
                    return ch
                self.pc.value = addr
                self._pc_overridden = True
                self._on_execute(f"BVC  {label} ; V=0 → PC←{addr:02d}")
            else:
                self._on_execute(f"BVC  {label} ; V=1 → no-branch")
            return ch

        # 하위 호환: BCS/BCC → V 사용
        if op == "BCS":
            label = str(args[0])
            if self.flags.get("V", 0) == 1:
                addr = self._resolve_label(label)
                if addr is None:
                    self._on_execute(f"BCS {label} ; <LABEL NOT FOUND> -> HALT")
                    self.halted = True
                    return ch
                self.pc.value = addr
                self._pc_overridden = True
                self._on_execute(f"BCS  {label} ; (alias V=1) → PC←{addr:02d}")
            else:
                self._on_execute(f"BCS  {label} ; V=0 → no-branch")
            return ch

        if op == "BCC":
            label = str(args[0])
            if self.flags.get("V", 0) == 0:
                addr = self._resolve_label(label)
                if addr is None:
                    self._on_execute(f"BCC {label} ; <LABEL NOT FOUND> -> HALT")
                    self.halted = True
                    return ch
                self.pc.value = addr
                self._pc_overridden = True
                self._on_execute(f"BCC  {label} ; (alias V=0) → PC←{addr:02d}")
            else:
                self._on_execute(f"BCC  {label} ; V=1 → no-branch")
            return ch

        # 정의 안 된 op
        self._on_execute(f"(unknown op) {op} {args}")
        return ch

    def _resolve_label(self, name: str) -> int | None:
        addr = self.prog.get_label_addr(name)
        return addr

    # ---------- 콘솔 훅 ----------
    def _on_fetch(self, text: str) -> None:
        self._println(f"[FETCH] PC={self.pc.value:02d}  line='{text}'")

    def _on_decode(self, decoded: Tuple[str, tuple[Any, ...]]) -> None:
        op, args = decoded
        self._println(f"[DECODE] {op} {args}")

    def _on_execute(self, desc: str) -> None:
        self._println(f"[EXEC]   {desc}")

    def _on_writeback(self, changes: Dict[str, int]) -> None:
        if changes:
            ch = ", ".join(f"{k}={v:4d}" for k, v in changes.items())
            self._println(f"[WB]     {ch}")
        else:
            self._println("[WB]     (no changes)")

    def _on_pc_advance(self, old: int, new: int) -> None:
        self._println(f"[PC]     {old:02d} -> {new:02d}")

    def _on_halt(self) -> None:
        self._println("[HALT]   Program finished or PC out of range.")

    def _println(self, s: str) -> None:
        if self.debug:
            print(s)
