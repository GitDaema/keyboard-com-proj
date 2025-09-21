# sim/cpu.py
from typing import Dict, Any, List, Tuple
from sim.pc import PC
from sim.ir import IR
from sim.data_memory import DataMemory
from sim.program_memory import ProgramMemory
from sim.parser import parse_line

"""
# =========================
# CPU/Parser 명령어 정리 (쉬운 설명)
# =========================
#
# ■ 기본 규칙
# - 모든 계산은 8비트(0~255) 안에서만 동작.
# - 플래그란? 계산 결과에 따라 상태를 기록하는 값들.
#     Z (Zero)     : 결과가 0이면 1
#     N (Negative) : 결과가 음수처럼 보이면(맨 앞 비트가 1) 1
#     C (Carry)    : 덧셈에서는 자리올림, 뺄셈에서는 빌림이 없을 때 1
# - PC는 "다음 명령어 위치". 보통 한 칸씩 증가하지만,
#   점프/분기(JMP, BEQ 등)가 실행되면 직접 바뀜.
# - #기호(#10, #0x1F, #0b1010)는 '즉시 값'(바로 쓰는 숫자).
#
# ■ 기본 명령어
# - NOP
#   아무 것도 하지 않음.
#
# - LABEL name:
#   라벨(이름표) 정의. 점프할 때 목적지가 됨.
#
# - HALT
#   프로그램 정지.
#
# - PRINT x
#   변수 x의 값을 화면에 보여줌.
#
# ■ 값 넣기 / 더하기
# - MOVI dst, #imm
#   dst 변수에 숫자 imm을 직접 넣음.
#   예: MOVI a, #10 → a=10
#
# - MOV dst, src
#   src 변수의 값을 dst에 복사.
#   예: MOV b, a → b=a
#
# - ADDI dst, #imm
#   dst에 숫자 imm을 더함.
#   예: ADDI a, #1 → a=a+1 (255 넘으면 0부터 다시 시작)
#
# - ADD dst, src
#   dst에 src 값을 더함.
#   예: ADD a, b → a=a+b
#
# ■ 빼기 (플래그도 갱신됨)
# - SUBI dst, #imm
#   dst에서 imm을 뺌. 결과와 함께 Z/N/C 갱신.
#   예: a=5일 때 SUBI a, #9 → 결과=252, Z=0, N=1, C=0
#
# - SUB dst, src
#   dst에서 src 값을 뺌. Z/N/C 갱신.
#
# ■ 비트 연산 (0과 1을 직접 다룸)
# - AND dst, src
#   dst = dst AND src
#   두 값의 비트가 모두 1일 때만 1.
#
# - OR dst, src
#   dst = dst OR src
#   둘 중 하나라도 1이면 1.
#
# - XOR dst, src
#   dst = dst XOR src
#   두 비트가 다를 때만 1.
#
# ■ 시프트 (비트를 왼쪽/오른쪽으로 밀기)
# - SHL dst
#   dst를 왼쪽으로 한 칸 밀기. 
#   맨 왼쪽에서 밀려나간 비트는 C 플래그로 저장.
#
# - SHR dst
#   dst를 오른쪽으로 한 칸 밀기.
#   맨 오른쪽에서 밀려나간 비트는 C 플래그로 저장.
#
# ■ 비교 / 분기
# - CMP a, b
#   a-b 계산만 하고 결과는 버림. 대신 Z/N/C 플래그만 갱신.
#
# - CMPI a, #imm
#   a-imm 계산만 하고 결과는 버림. 플래그 갱신.
#
# - JMP label
#   label 위치로 무조건 이동.
#
# - BEQ label
#   Z=1(결과가 0일 때)이면 label로 이동.
#
# - BNE label
#   Z=0(결과가 0이 아닐 때)이면 이동.
#
# - BCC label
#   C=0(자리올림 없음/뺄셈에서 빌림 발생)일 때 이동.
#
# - BCS label
#   C=1(자리올림 있음/뺄셈에서 빌림 없음)일 때 이동.
#
# - BMI label
#   N=1(음수 결과)일 때 이동.
#
# - BPL label
#   N=0(양수 결과)일 때 이동.
"""

class CPU:
    def __init__(self, *, debug: bool = False) -> None:
        self.pc = PC()
        self.ir = IR()
        self.mem = DataMemory()
        self.prog = ProgramMemory()
        self.halted = False
        self.debug = debug

        # 플래그: Zero / Negative / Carry(=no-borrow)
        self.flags: Dict[str, int] = {"Z": 0, "N": 0, "C": 1}
        self._pc_overridden: bool = False

    # ---------- 외부 API ----------
    def load_program(self, lines: List[str]) -> None:
        self.prog.load_program(lines)
        self.pc.reset()
        self.halted = False
        self.ir.clear()
        self.flags["Z"] = 0
        self.flags["N"] = 0
        self.flags["C"] = 1

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
                f"| Z:{self.flags['Z']} N:{self.flags['N']} C:{self.flags['C']} "
                f"| b:{self.mem.vars.get('b','N/A')}"
            )
            changes = self._exec_one(op, args)
            self._on_writeback(changes)
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

    def run(self) -> None:
        self._println("\n[RUN] Starting execution...")
        while self.step():
            pass
        self._println("[RUN] Execution finished.\n")

    # ---------- 플래그 유틸 ----------
    def _set_zn_from_val(self, v: int) -> None:
        v &= 0xFF
        self.flags["Z"] = 1 if v == 0 else 0
        self.flags["N"] = 1 if (v & 0x80) != 0 else 0

    def _sub_and_set_flags(self, a: int, b: int) -> int:
        """8비트 뺄셈 결과와 Z/N/C 설정. C=1이면 borrow 없음, C=0이면 borrow 발생."""
        raw = a - b
        res = raw & 0xFF
        borrow = 1 if raw < 0 else 0
        self.flags["C"] = 0 if borrow else 1
        self._set_zn_from_val(res)
        return res

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

        # --- MOV/MOVI/ADD/ADDI (기존) ---
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

        if op == "ADDI":
            dst, imm = args
            v_before = self.mem.get(str(dst))
            v = (v_before + int(imm)) & 0xFF
            self.mem.set(str(dst), v)
            self._on_execute(f"ADDI {dst}, #{imm} ; {dst}:{v_before}→{v}")
            ch[str(dst)] = v
            # (선택) ADD는 기존 호환을 위해 Z/N/C 갱신 생략 유지
            return ch

        if op == "ADD":
            dst, src = args
            a = self.mem.get(str(dst))
            b = self.mem.get(str(src))
            v = (a + b) & 0xFF
            self.mem.set(str(dst), v)
            self._on_execute(f"ADD  {dst}, {src} ; {dst}:{a}+{b}→{v}")
            ch[str(dst)] = v
            # (선택) ADD도 기존 호환을 위해 Z/N/C 갱신 생략
            return ch

        # --- NEW: SUB/SUBI ---
        if op == "SUBI":
            dst, imm = args
            a = self.mem.get(str(dst))
            b = int(imm) & 0xFF
            v = self._sub_and_set_flags(a, b)
            self.mem.set(str(dst), v)
            self._on_execute(f"SUBI {dst}, #{imm} ; {dst}:{a}-{b}→{v} | Z={self.flags['Z']} N={self.flags['N']} C={self.flags['C']}")
            ch[str(dst)] = v
            return ch

        if op == "SUB":
            dst, src = args
            a = self.mem.get(str(dst))
            b = self.mem.get(str(src))
            v = self._sub_and_set_flags(a, b)
            self.mem.set(str(dst), v)
            self._on_execute(f"SUB  {dst}, {src} ; {dst}:{a}-{b}→{v} | Z={self.flags['Z']} N={self.flags['N']} C={self.flags['C']}")
            ch[str(dst)] = v
            return ch

        # --- NEW: 비트/시프트 ---
        if op == "AND":
            dst, src = args
            a = self.mem.get(str(dst))
            b = self.mem.get(str(src))
            v = (a & b) & 0xFF
            self.mem.set(str(dst), v)
            self.flags["C"] = 0
            self._set_zn_from_val(v)
            self._on_execute(f"AND  {dst}, {src} ; {dst}:{a}&{b}→{v} | Z={self.flags['Z']} N={self.flags['N']}")
            ch[str(dst)] = v
            return ch

        if op == "OR":
            dst, src = args
            a = self.mem.get(str(dst))
            b = self.mem.get(str(src))
            v = (a | b) & 0xFF
            self.mem.set(str(dst), v)
            self.flags["C"] = 0
            self._set_zn_from_val(v)
            self._on_execute(f"OR   {dst}, {src} ; {dst}:{a}|{b}→{v} | Z={self.flags['Z']} N={self.flags['N']}")
            ch[str(dst)] = v
            return ch

        if op == "XOR":
            dst, src = args
            a = self.mem.get(str(dst))
            b = self.mem.get(str(src))
            v = (a ^ b) & 0xFF
            self.mem.set(str(dst), v)
            self.flags["C"] = 0
            self._set_zn_from_val(v)
            self._on_execute(f"XOR  {dst}, {src} ; {dst}:{a}^{b}→{v} | Z={self.flags['Z']} N={self.flags['N']}")
            ch[str(dst)] = v
            return ch

        if op == "SHL":
            dst, = args
            a = self.mem.get(str(dst))
            cout = 1 if (a & 0x80) != 0 else 0
            v = (a << 1) & 0xFF
            self.mem.set(str(dst), v)
            self.flags["C"] = cout
            self._set_zn_from_val(v)
            self._on_execute(f"SHL  {dst} ; {a:08b}<<1 -> {v:08b} | C={cout} Z={self.flags['Z']} N={self.flags['N']}")
            ch[str(dst)] = v
            return ch

        if op == "SHR":
            dst, = args
            a = self.mem.get(str(dst))
            cout = a & 1
            v = (a >> 1) & 0xFF
            self.mem.set(str(dst), v)
            self.flags["C"] = cout
            self._set_zn_from_val(v)
            self._on_execute(f"SHR  {dst} ; {a:08b}>>1 -> {v:08b} | C={cout} Z={self.flags['Z']} N={self.flags['N']}")
            ch[str(dst)] = v
            return ch

        # --- 비교/분기 ---
        if op == "CMP":
            a, b = args
            va = self.mem.get(str(a))
            vb = self.mem.get(str(b))
            _ = self._sub_and_set_flags(va, vb)
            self._on_execute(f"CMP  {a}, {b} ; ({va}-{vb}) → Z={self.flags['Z']} N={self.flags['N']} C={self.flags['C']}")
            return ch

        if op == "CMPI":
            a, imm = args
            va = self.mem.get(str(a))
            vb = int(imm) & 0xFF
            _ = self._sub_and_set_flags(va, vb)
            self._on_execute(f"CMPI {a}, #{imm} ; ({va}-{vb}) → Z={self.flags['Z']} N={self.flags['N']} C={self.flags['C']}")
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

        # NEW: BCC/BCS/BMI/BPL
        if op == "BCC":
            label = str(args[0])
            if self.flags.get("C", 0) == 0:
                addr = self._resolve_label(label)
                if addr is None:
                    self._on_execute(f"BCC {label} ; <LABEL NOT FOUND> -> HALT")
                    self.halted = True
                    return ch
                self.pc.value = addr
                self._pc_overridden = True
                self._on_execute(f"BCC  {label} ; C=0 → PC←{addr:02d}")
            else:
                self._on_execute(f"BCC  {label} ; C=1 → no-branch")
            return ch

        if op == "BCS":
            label = str(args[0])
            if self.flags.get("C", 0) == 1:
                addr = self._resolve_label(label)
                if addr is None:
                    self._on_execute(f"BCS {label} ; <LABEL NOT FOUND> -> HALT")
                    self.halted = True
                    return ch
                self.pc.value = addr
                self._pc_overridden = True
                self._on_execute(f"BCS  {label} ; C=1 → PC←{addr:02d}")
            else:
                self._on_execute(f"BCS  {label} ; C=0 → no-branch")
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
            ch = ", ".join(f"{k}={v:3d}" for k, v in changes.items())
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
