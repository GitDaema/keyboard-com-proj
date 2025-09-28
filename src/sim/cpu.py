# sim/cpu.py
from typing import Dict, Any, List, Tuple

from utils.keyboard_presets import FLAG_LABELS, BINARY_COLORS
from utils.stage_indicator import post_stage, clear_stages
from utils.ir_indicator import update_from_decoded, clear_ir, encode_from_source_line_fixed, set_ir, read_ir
from utils.run_pause_indicator import run_on, run_off
from utils.pc_indicator import update_pc, clear_pc

from sim.pc import PC
from sim.ir import IR
from sim.data_memory_rgb_visual import DataMemoryRGBVisual
from sim.program_memory import ProgramMemory
from sim.parser import parse_line, preprocess_program
from sim.assembler import assemble_program, AsmInsn, OPCODES, BR_COND, EXT_TYPE_IMM

from utils.bit_lut import (
    add8_via_lut, sub8_via_lut, and8_via_lut, or8_via_lut, xor8_via_lut,
    shl8_via_lut, shr8_via_lut
)
from utils.keyboard_presets import SRC1, SRC2, RES


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

class CPU:
    def __init__(self, *, debug: bool = False, mem=None, interactive: bool = False, use_isa: bool = True) -> None:
        self.pc = PC()
        self.ir = IR()
        self.mem = mem if mem is not None else DataMemoryRGBVisual(binary_labels=BINARY_COLORS)
        self.prog = ProgramMemory()
        self.halted = False
        self.debug = debug

        # 플래그: Zero / Negative / oVerflow / Carry
        self.flags: Dict[str, int] = {"Z": 0, "N": 0, "V": 0, "C": 0}
        self._pc_overridden: bool = False

        self.interactive = interactive                         # ← 스텝 실행 플래그
        self._continue_run = False                             # ← 'c' 입력 시 계속 진행
        self.use_isa = use_isa                                 # ← ISA 모드 사용 여부

        # ISA instruction stream (when use_isa=True)
        self._isa: list[AsmInsn] = []

    # ---------- 외부 API ----------
    def load_program(self, lines: List[str], *, debug: bool | None = None) -> None:
        dbg = self.debug if debug is None else bool(debug)
        if self.use_isa:
            # Assemble into ISA stream (2-byte per insn)
            try:
                self._isa = assemble_program(lines, debug=dbg)
            except Exception as ex:
                print(f"[ASM] Error: {ex}. Falling back to raw lines.")
                self._isa = []
        else:
            try:
                expanded = preprocess_program(lines)
            except Exception:
                expanded = lines
            self.prog.load_program(expanded)
        self.pc.reset()
        self.halted = False
        self.ir.clear()
        self.flags["Z"] = 0
        self.flags["N"] = 0
        self.flags["V"] = 0
        self.flags["C"] = 0

        # 초기 플래그 상태를 LED에 1회 반영(Off 상태라도 바로 보이게)
        try:
            self._sync_flag_leds()
        except Exception:
            pass

        # Clear control-stage indicators at program load
        try:
            clear_stages()
        except Exception:
            pass

        # Clear IR visualization
        try:
            clear_ir()
        except Exception:
            pass

        self._continue_run = False

        # Initialize PC indicator to OFF (dark gray)
        try:
            clear_pc()
        except Exception:
            pass

    def step(self) -> bool:
        if self.halted:
            self._on_halt()
            return False

        if self.use_isa:
            return self._step_isa()
        else:
            return self._step_micro()

    def _step_micro(self) -> bool:
        # Original micro-op per line execution (legacy)
        # Capture PC at the start of the step for accurate logging
        start_pc = self.pc.value
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
            try:
                post_stage("FETCH")
            except Exception:
                pass
            self.ir.decoded = (op, args)
            self._on_decode((op, args))
            self._println(
                f"PC:{self.pc.value:02d} | OP:{op:<4} | ARGS:{args} "
                f"| Z:{self.flags['Z']} N:{self.flags['N']} V:{self.flags['V']}"
            )
            changes = self._exec_one(op, args)
            self._on_writeback(changes)
            self._sync_flag_leds()
            self._maybe_pause()
            if self.halted or self._pc_overridden:
                break
        if not self._pc_overridden:
            self.pc.increment(1)
            self._on_pc_advance(start_pc, self.pc.value)
        else:
            self._on_pc_advance(start_pc, self.pc.value)
        self.ir.clear()
        return not self.halted

    def _step_isa(self) -> bool:
        start_pc = self.pc.value
        if start_pc < 0 or start_pc >= len(self._isa):
            self.halted = True
            self._on_halt()
            return False
        cur_pc = start_pc
        ext_imm_pending = False
        ext_imm_val = 0
        # Consume any prefix frames (e.g., EXTI) before executing the real op
        while True:
            insn = self._isa[cur_pc]
            # FETCH stage + IR update (write)
            try:
                post_stage("FETCH")
            except Exception:
                pass
            try:
                update_pc(cur_pc)
            except Exception:
                pass
            try:
                set_ir(insn.op4, insn.dst4, insn.arg8)
            except Exception:
                pass
            self._println(f"[FETCH] PC={cur_pc:02d}  insn='{insn.text}' | op={insn.op4:X} dst={insn.dst4:X} arg={insn.arg8:02X}")

            # DECODE stage (read IR back)
            try:
                post_stage("DECODE")
            except Exception:
                pass
            op4, dst4, arg8 = read_ir(samples=3, use_calibration=True, debug=False)
            self._println(f"[DECODE] op={op4:X} dst={dst4:X} arg={arg8:02X}")

            # EXT prefix: op nibble matches NOP but with DST marking type
            if op4 == OPCODES.get("EXT", 0x0) and (dst4 & 0xF) == (EXT_TYPE_IMM & 0xF):
                # Latch immediate for next op
                ext_imm_pending = True
                ext_imm_val = int(arg8 if arg8 < 128 else arg8 - 256)
                self._on_execute(f"EXTI #{ext_imm_val}")
                # WRITEBACK (no changes)
                try:
                    post_stage("WRITEBACK")
                except Exception:
                    pass
                self._println("[WB]     (no changes)")
                cur_pc += 1
                continue
            break

        # EXECUTE
        taken = False
        next_pc = cur_pc + 1
        ch: Dict[str, int] = {}
        try:
            post_stage("EXECUTE")
        except Exception:
            pass

        def var_name(v4: int) -> str:
            from utils.keyboard_presets import ID_TO_VAR
            return ID_TO_VAR.get(int(v4) & 0xF, 'q')

        # Helper: write group from signed int
        def _write_u8_to_group(grp: str, u8: int):
            labels = self._group_labels(grp)
            u8 &= 0xFF
            width = len(labels)
            for i in range(width):
                bit = (u8 >> i) & 1
                lab = labels[width - 1 - i]
                self.mem.set(lab, bit)

        def _read_res_s8() -> int:
            u8 = self._read_u8_from_group("RES")
            return u8 if u8 < 128 else u8 - 256

        # Execute by opcode
        if op4 == OPCODES["NOP"]:
            self._on_execute("NOP (ISA)")
        elif op4 == OPCODES["HALT"]:
            self._on_execute("HALT (ISA)")
            self.halted = True
        elif op4 == OPCODES["MOVI"]:
            dst = var_name(dst4)
            imm = int(arg8 if arg8 < 128 else arg8 - 256)
            _write_u8_to_group("SRC1", arg8)
            self._on_execute(f"MOVI {dst}, #{imm}")
            # COPY → PACK
            ch = {}
            # Directly set via PACK pipeline
            self._clear_group("RES")
            self._write_u8_to_group("RES", arg8)
            v = _read_res_s8()
            self.mem.set(dst, v)
            ch[dst] = v
        elif op4 == OPCODES["MOV"]:
            dst = var_name(dst4)
            src = var_name(arg8 & 0xF)
            v = self.mem.get(src)
            self._on_execute(f"MOV {dst},{src} ; {dst}={v}")
            self.mem.set(dst, v)
            ch = {dst: v}
        elif op4 in (OPCODES["ADD"], OPCODES["ADDI"], OPCODES["SUB"], OPCODES["SUBI"], OPCODES["AND"], OPCODES["OR"], OPCODES["XOR"], OPCODES["CMP"], OPCODES["SHIFT"], OPCODES["NEG"]):
            # Map to existing micro-ops via groups/LUTs
            # Prepare operands into groups as needed
            is_cmpi = (op4 == OPCODES["CMP"]) and ext_imm_pending
            if (op4 in (OPCODES["ADDI"], OPCODES["SUBI"])) or is_cmpi:
                dst = var_name(dst4)
                a = self.mem.get(dst)
                b = int(ext_imm_val if is_cmpi else (arg8 if arg8 < 128 else arg8 - 256))
                self._write_u8_to_group("SRC1", _to_u8(a))
                self._write_u8_to_group("SRC2", _to_u8(b))
            elif op4 in (OPCODES["SHIFT"],):
                dst = var_name(dst4)
                a = self.mem.get(dst)
                self._write_u8_to_group("SRC1", _to_u8(a))
            elif op4 == OPCODES["NEG"]:
                dst = var_name(dst4)
                a = self.mem.get(dst)
                # Prepare groups for 0 - a
                self._write_u8_to_group("SRC1", 0)
                self._write_u8_to_group("SRC2", _to_u8(a))
            else:
                dst = var_name(dst4)
                src = var_name(arg8 & 0xF)
                a = self.mem.get(dst)
                b = self.mem.get(src)
                self._write_u8_to_group("SRC1", _to_u8(a))
                self._write_u8_to_group("SRC2", _to_u8(b))

            # Execute using existing helpers
            if op4 == OPCODES["ADDI"]:
                add8_via_lut(self.mem, src1=SRC1, src2=SRC2, dst=RES, lsb_first=False)
                res_u8 = self._read_u8_from_group("RES")
                v = res_u8 if res_u8 < 128 else res_u8 - 256
                self.mem.set(dst, v)
                inputs_same_sign = _sign_bit(a) == _sign_bit(b)
                self.flags["V"] = 1 if inputs_same_sign and (_sign_bit(a) != _sign_bit(v)) else 0
                self.flags["C"] = 1 if (_to_u8(a) + _to_u8(b)) > 0xFF else 0
                _set_zn_from_val(self.flags, v)
                self._on_execute(f"ADDI {dst}, #{b}")
                ch = {dst: v}
            elif op4 == OPCODES["ADD"]:
                add8_via_lut(self.mem, src1=SRC1, src2=SRC2, dst=RES, lsb_first=False)
                res_u8 = self._read_u8_from_group("RES")
                v = res_u8 if res_u8 < 128 else res_u8 - 256
                self.mem.set(dst, v)
                inputs_same_sign = _sign_bit(a) == _sign_bit(b)
                self.flags["V"] = 1 if inputs_same_sign and (_sign_bit(a) != _sign_bit(v)) else 0
                self.flags["C"] = 1 if (_to_u8(a) + _to_u8(b)) > 0xFF else 0
                _set_zn_from_val(self.flags, v)
                self._on_execute(f"ADD {dst}, {src}")
                ch = {dst: v}
            elif op4 == OPCODES["SUBI"]:
                sub8_via_lut(self.mem, src1=SRC1, src2=SRC2, dst=RES, lsb_first=False)
                res_u8 = self._read_u8_from_group("RES")
                v = res_u8 if res_u8 < 128 else res_u8 - 256
                self.mem.set(dst, v)
                inputs_diff_sign = _sign_bit(a) != _sign_bit(b)
                self.flags["V"] = 1 if inputs_diff_sign and (_sign_bit(a) != _sign_bit(v)) else 0
                self.flags["C"] = 1 if _to_u8(a) >= _to_u8(b) else 0
                _set_zn_from_val(self.flags, v)
                self._on_execute(f"SUBI {dst}, #{b}")
                ch = {dst: v}
            elif op4 == OPCODES["SUB"]:
                sub8_via_lut(self.mem, src1=SRC1, src2=SRC2, dst=RES, lsb_first=False)
                res_u8 = self._read_u8_from_group("RES")
                v = res_u8 if res_u8 < 128 else res_u8 - 256
                self.mem.set(dst, v)
                inputs_diff_sign = _sign_bit(a) != _sign_bit(b)
                self.flags["V"] = 1 if inputs_diff_sign and (_sign_bit(a) != _sign_bit(v)) else 0
                self.flags["C"] = 1 if _to_u8(a) >= _to_u8(b) else 0
                _set_zn_from_val(self.flags, v)
                self._on_execute(f"SUB {dst}, {src}")
                ch = {dst: v}
            elif op4 in (OPCODES["AND"], OPCODES["OR"], OPCODES["XOR"]):
                lut = {OPCODES["AND"]: and8_via_lut, OPCODES["OR"]: or8_via_lut, OPCODES["XOR"]: xor8_via_lut}[op4]
                lut(self.mem, src1=SRC1, src2=SRC2, dst=RES, lsb_first=False)
                res_u8 = self._read_u8_from_group("RES")
                v = res_u8 if res_u8 < 128 else res_u8 - 256
                self.mem.set(dst, v)
                self.flags["V"] = 0
                _set_zn_from_val(self.flags, v)
                name = {OPCODES["AND"]:"AND", OPCODES["OR"]:"OR", OPCODES["XOR"]:"XOR"}[op4]
                self._on_execute(f"{name} {dst}, {src}")
                ch = {dst: v}
            elif op4 == OPCODES["CMP"] and not is_cmpi:
                sub8_via_lut(self.mem, src1=SRC1, src2=SRC2, dst=RES, lsb_first=False)
                res_u8 = self._read_u8_from_group("RES")
                v = res_u8 if res_u8 < 128 else res_u8 - 256
                inputs_diff_sign = _sign_bit(a) != _sign_bit(b)
                self.flags["V"] = 1 if inputs_diff_sign and (_sign_bit(a) != _sign_bit(v)) else 0
                self.flags["C"] = 1 if _to_u8(a) >= _to_u8(b) else 0
                _set_zn_from_val(self.flags, v)
                self._on_execute(f"CMP {dst}, {src}")
            elif op4 == OPCODES["CMP"] and is_cmpi:
                sub8_via_lut(self.mem, src1=SRC1, src2=SRC2, dst=RES, lsb_first=False)
                res_u8 = self._read_u8_from_group("RES")
                v = res_u8 if res_u8 < 128 else res_u8 - 256
                inputs_diff_sign = _sign_bit(a) != _sign_bit(b)
                self.flags["V"] = 1 if inputs_diff_sign and (_sign_bit(a) != _sign_bit(v)) else 0
                self.flags["C"] = 1 if _to_u8(a) >= _to_u8(b) else 0
                _set_zn_from_val(self.flags, v)
                self._on_execute(f"CMPI {dst}, #{b}")
            elif op4 == OPCODES["SHIFT"]:
                # ARG bit0 decides direction
                if (arg8 & 0x01) == 0:
                    # SHL
                    shl8_via_lut(self.mem, src=SRC1, dst=RES, lsb_first=False)
                    res_u8 = self._read_u8_from_group("RES")
                    v = res_u8 if res_u8 < 128 else res_u8 - 256
                    self.flags["C"] = 1 if (_to_u8(a) & 0x80) else 0
                    ov = 1 if (_sign_bit(a) != _sign_bit(v)) else 0
                    self.mem.set(dst, v)
                    self.flags["V"] = ov
                    _set_zn_from_val(self.flags, v)
                    self._on_execute(f"SHL {dst}")
                    ch = {dst: v}
                else:
                    # SHR
                    shr8_via_lut(self.mem, src=SRC1, dst=RES, lsb_first=False)
                    res_u8 = self._read_u8_from_group("RES")
                    v = res_u8 if res_u8 < 128 else res_u8 - 256
                    self.mem.set(dst, v)
                    self.flags["C"] = 1 if (_to_u8(a) & 0x01) else 0
                    self.flags["V"] = 0
                    _set_zn_from_val(self.flags, v)
                    self._on_execute(f"SHR {dst}")
                    ch = {dst: v}
            elif op4 == OPCODES["NEG"]:
                # Perform 0 - a via LUT
                sub8_via_lut(self.mem, src1=SRC1, src2=SRC2, dst=RES, lsb_first=False)
                res_u8 = self._read_u8_from_group("RES")
                v = res_u8 if res_u8 < 128 else res_u8 - 256
                self.mem.set(dst, v)
                # Flags like SUB with a=0, b=a
                inputs_diff_sign = _sign_bit(0) != _sign_bit(a)
                self.flags["V"] = 1 if inputs_diff_sign and (_sign_bit(0) != _sign_bit(v)) else 0
                self.flags["C"] = 1 if _to_u8(0) >= _to_u8(a) else 0
                _set_zn_from_val(self.flags, v)
                self._on_execute(f"NEG {dst}")
                ch = {dst: v}
        elif op4 == OPCODES["JMP"] or op4 == OPCODES["BR"]:
            # Relative jump/branch; arg8 is signed offset
            rel = int(arg8 if arg8 < 128 else arg8 - 256)
            if op4 == OPCODES["JMP"]:
                taken = True
                next_pc = cur_pc + 1 + rel
                self._on_execute(f"JMP rel {rel:+d} -> {next_pc:02d}")
            else:
                # Evaluate condition from dst4 nibble
                cond_n = int(dst4) & 0xF
                name_by_cond = {v: k for k, v in BR_COND.items()}
                cname = name_by_cond.get(cond_n, "BEQ")
                Z = self.flags.get("Z", 0)
                N = self.flags.get("N", 0)
                V = self.flags.get("V", 0)
                taken = (
                    (cname == "BEQ" and Z == 1) or
                    (cname == "BNE" and Z == 0) or
                    (cname == "BMI" and N == 1) or
                    (cname == "BPL" and N == 0) or
                    (cname == "BVS" and V == 1) or
                    (cname == "BVC" and V == 0) or
                    (cname == "BCS" and V == 1) or
                    (cname == "BCC" and V == 0)
                )
                if taken:
                    next_pc = cur_pc + 1 + rel
                    self._on_execute(f"{cname} taken rel {rel:+d} -> {next_pc:02d}")
                else:
                    self._on_execute(f"{cname} not-taken")
        else:
            self._on_execute(f"(unknown ISA op) {op4:X}")

        # WRITEBACK stage
        try:
            post_stage("WRITEBACK")
        except Exception:
            pass
        if ch:
            self._println(f"[WB]     {', '.join(f'{k}={v:4d}' for k,v in ch.items())}")
        else:
            self._println("[WB]     (no changes)")
        self._sync_flag_leds()
        self._maybe_pause()

        # Advance PC
        old_pc = start_pc
        self.pc.value = next_pc
        self._on_pc_advance(old_pc, self.pc.value)
        if self.halted:
            self._on_halt()
        return not self.halted

    def _maybe_pause(self) -> None:
        """interactive 모드면, 한 연산 끝날 때 사용자 입력 대기.
        [Enter]=한 스텝, 'c'=연속 실행, 'q'=즉시 종료"""
        if not self.interactive:
            return
        if self._continue_run:
            return
        # Entering pause state: turn off stage indicators and show PAUSE
        try:
            clear_stages()
        except Exception:
            pass
        try:
            run_off()
        except Exception:
            pass
        try:
            s = input("[step] Enter=next | c=continue | q=quit > ").strip().lower()
        except EOFError:
            s = ""
        if s == "c":
            self._continue_run = True
            # Resume continuous run: show RUN (on)
            try:
                run_on()
            except Exception:
                pass
        elif s == "q":
            self.halted = True
            # Remain paused on quit
            try:
                run_off()
            except Exception:
                pass
        else:
            # Single-step resume: turn RUN on; next pause will turn it off again
            try:
                run_on()
            except Exception:
                pass

    def _sync_flag_leds(self) -> None:
        """현재 Z/N/V 값을 지정된 키 LED에 반영"""
        if hasattr(self.mem, "set_flag"):
            for k, led in FLAG_LABELS.items():
                self.mem.set_flag(led, bool(self.flags.get(k, 0)))

    def run(self) -> None:
        self._println("\n[RUN] Starting execution...")
        # Show RUN when entering the run loop
        try:
            run_on()
        except Exception:
            pass
        while self.step():
            pass
        # 실행 종료 즉시 단계 표시 소등(WRITEBACK 포함)
        try:
            clear_stages()
        except Exception:
            pass
        self._println("[RUN] Execution finished.\n")
        # Ensure indicator shows PAUSE at the end
        try:
            run_off()
        except Exception:
            pass

    def _group_labels(self, grp: str):
        g = grp.upper()
        if g == "SRC1": return SRC1
        if g == "SRC2": return SRC2
        if g == "RES":  return RES
        raise ValueError(f"unknown bit-group: {grp}")

    def _write_u8_to_group(self, grp: str, u8: int):
        labels = self._group_labels(grp)
        u8 &= 0xFF
        width = len(labels)
        # labels[-1]이 LSB가 되도록 역인덱싱
        for i in range(width):  # i=0..7 -> 비트 i
            bit = (u8 >> i) & 1
            lab = labels[width - 1 - i]
            self.mem.set(lab, bit)

    def _clear_group(self, grp: str):
        for lab in self._group_labels(grp):
            self.mem.set(lab, 0)

    def _read_u8_from_group(self, grp: str) -> int:
        labels = self._group_labels(grp)
        width = len(labels)
        val = 0
        # labels[-1]이 LSB → 역인덱싱으로 읽어서 i번째 비트로
        for i in range(width):  # i=0..7
            lab = labels[width - 1 - i]
            val |= (int(self.mem.get(lab)) & 1) << i
        return val & 0xFF

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
        
        if op == "PRINT_RES":
            u8 = self._read_u8_from_group("RES")
            v  = u8 if u8 < 128 else u8 - 256   # two's complement
            self._on_execute(f"PRINT_RES -> {v}")
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
        
        if op == "UNPACK1":
            (var,) = args
            v = self.mem.get(str(var))         # -128..127
            self._write_u8_to_group("SRC1", v & 0xFF)
            self._on_execute(f"UNPACK1 {var} → SRC1")
            return ch

        if op == "UNPACK2":
            (var,) = args
            v = self.mem.get(str(var))
            self._write_u8_to_group("SRC2", v & 0xFF)
            self._on_execute(f"UNPACK2 {var} → SRC2")
            return ch

        if op == "UNPACK":
            var, grp = args
            v = self.mem.get(str(var))
            self._write_u8_to_group(str(grp), v & 0xFF)
            self._on_execute(f"UNPACK {var} → {grp}")
            return ch

        # LOADI8_BITS
        if op == "LOADI8_BITS":
            grp, imm = args
            self._write_u8_to_group(str(grp), int(imm))
            self._on_execute(f"LOADI8_BITS {grp}, #{int(imm)&0xFF}")
            return ch

        # CLEARBITS
        if op == "CLEARBITS":
            (grp,) = args
            self._clear_group(str(grp))
            self._on_execute(f"CLEARBITS {grp}")
            return ch

        # COPYBITS
        if op == "COPYBITS":
            dst, src = args
            src_labels = self._group_labels(str(src))
            dst_labels = self._group_labels(str(dst))
            
            # 1. Read all bits from source group first
            bits = []
            for label in src_labels:
                bits.append(int(self.mem.get(label)) & 1)

            # 2. Then write all bits to destination group
            for i, label in enumerate(dst_labels):
                self.mem.set(label, bits[i])
            
            self._on_execute(f"COPYBITS {dst}, {src}")
            return ch

        # --- ADD/ADDI (signed: Z/N/V 갱신) ---
        if op == "ADDI":
            dst, imm = args
            dst_name = str(dst)
            a = self.mem.get(dst_name)
            b = int(imm)

            self._write_u8_to_group("SRC1", _to_u8(a))
            self._write_u8_to_group("SRC2", _to_u8(b))
            add8_via_lut(self.mem, src1=SRC1, src2=SRC2, dst=RES, lsb_first=False)

            res_u8 = self._read_u8_from_group("RES")
            v = res_u8 if res_u8 < 128 else res_u8 - 256
            self.mem.set(dst_name, v)

            inputs_same_sign = _sign_bit(a) == _sign_bit(b)
            self.flags["V"] = 1 if inputs_same_sign and (_sign_bit(a) != _sign_bit(v)) else 0
            # Carry: unsigned carry out
            self.flags["C"] = 1 if (_to_u8(a) + _to_u8(b)) > 0xFF else 0
            _set_zn_from_val(self.flags, v)
            self._on_execute(
                f"ADDI {dst}, #{imm} ; via LUT {dst_name}:{a}+{b}->{v} | Z={self.flags['Z']} N={self.flags['N']} V={self.flags['V']}"
            )
            ch[dst_name] = v
            return ch

        if op == "ADD":
            dst, src = args
            dst_name = str(dst)
            src_name = str(src)
            a = self.mem.get(dst_name)
            b = self.mem.get(src_name)

            self._write_u8_to_group("SRC1", _to_u8(a))
            self._write_u8_to_group("SRC2", _to_u8(b))
            add8_via_lut(self.mem, src1=SRC1, src2=SRC2, dst=RES, lsb_first=False)

            res_u8 = self._read_u8_from_group("RES")
            v = res_u8 if res_u8 < 128 else res_u8 - 256
            self.mem.set(dst_name, v)

            inputs_same_sign = _sign_bit(a) == _sign_bit(b)
            self.flags["V"] = 1 if inputs_same_sign and (_sign_bit(a) != _sign_bit(v)) else 0
            # Carry: unsigned carry out
            self.flags["C"] = 1 if (_to_u8(a) + _to_u8(b)) > 0xFF else 0
            _set_zn_from_val(self.flags, v)
            self._on_execute(
                f"ADD  {dst}, {src} ; via LUT {dst_name}:{a}+{b}->{v} | Z={self.flags['Z']} N={self.flags['N']} V={self.flags['V']}"
            )
            ch[dst_name] = v
            return ch

        if op == "ADD8":
            # Perform addition via LUT and update flags like ADD
            a_u8 = self._read_u8_from_group("SRC1")
            b_u8 = self._read_u8_from_group("SRC2")
            add8_via_lut(self.mem, src1=SRC1, src2=SRC2, dst=RES, lsb_first=False)
            res_u8 = self._read_u8_from_group("RES")
            v = res_u8 if res_u8 < 128 else res_u8 - 256
            # Signed overflow: inputs same sign and result sign differs from a
            inputs_same_sign = (1 if (a_u8 & 0x80) else 0) == (1 if (b_u8 & 0x80) else 0)
            self.flags["V"] = 1 if inputs_same_sign and ((1 if (a_u8 & 0x80) else 0) != (1 if (res_u8 & 0x80) else 0)) else 0
            # Unsigned carry out
            self.flags["C"] = 1 if (a_u8 + b_u8) > 0xFF else 0
            _set_zn_from_val(self.flags, v)
            self._on_execute("ADD8 (via LUT) ; RES ← SRC1 + SRC2")
            return ch

        # --- SUB/SUBI (signed: Z/N/V 갱신) ---
        if op == "SUBI":
            dst, imm = args
            dst_name = str(dst)
            a = self.mem.get(dst_name)
            b = int(imm)

            self._write_u8_to_group("SRC1", _to_u8(a))
            self._write_u8_to_group("SRC2", _to_u8(b))
            sub8_via_lut(self.mem, src1=SRC1, src2=SRC2, dst=RES, lsb_first=False)

            res_u8 = self._read_u8_from_group("RES")
            v = res_u8 if res_u8 < 128 else res_u8 - 256
            self.mem.set(dst_name, v)

            inputs_diff_sign = _sign_bit(a) != _sign_bit(b)
            self.flags["V"] = 1 if inputs_diff_sign and (_sign_bit(a) != _sign_bit(v)) else 0
            # Carry as 'no borrow' for subtraction
            self.flags["C"] = 1 if _to_u8(a) >= _to_u8(b) else 0
            _set_zn_from_val(self.flags, v)
            self._on_execute(f"SUBI {dst}, #{imm} ; via LUT {dst_name}:{a}-{b}→{v} | Z={self.flags['Z']} N={self.flags['N']} V={self.flags['V']}")
            ch[dst_name] = v
            return ch

        if op == "SUB":
            dst, src = args
            dst_name = str(dst)
            src_name = str(src)
            a = self.mem.get(dst_name)
            b = self.mem.get(src_name)

            self._write_u8_to_group("SRC1", _to_u8(a))
            self._write_u8_to_group("SRC2", _to_u8(b))
            sub8_via_lut(self.mem, src1=SRC1, src2=SRC2, dst=RES, lsb_first=False)

            res_u8 = self._read_u8_from_group("RES")
            v = res_u8 if res_u8 < 128 else res_u8 - 256
            self.mem.set(dst_name, v)

            inputs_diff_sign = _sign_bit(a) != _sign_bit(b)
            self.flags["V"] = 1 if inputs_diff_sign and (_sign_bit(a) != _sign_bit(v)) else 0
            # Carry as 'no borrow' for subtraction
            self.flags["C"] = 1 if _to_u8(a) >= _to_u8(b) else 0
            _set_zn_from_val(self.flags, v)
            self._on_execute(f"SUB  {dst}, {src} ; via LUT {dst_name}:{a}-{b}→{v} | Z={self.flags['Z']} N={self.flags['N']} V={self.flags['V']}")
            ch[dst_name] = v
            return ch

        if op == "SUB8":
            # Perform subtraction via LUT and update flags like SUB
            a_u8 = self._read_u8_from_group("SRC1")
            b_u8 = self._read_u8_from_group("SRC2")
            sub8_via_lut(self.mem, src1=SRC1, src2=SRC2, dst=RES, lsb_first=False)
            res_u8 = self._read_u8_from_group("RES")
            v = res_u8 if res_u8 < 128 else res_u8 - 256
            # Signed overflow on subtraction: inputs different sign and result sign differs from a
            inputs_diff_sign = ((a_u8 ^ b_u8) & 0x80) != 0
            self.flags["V"] = 1 if inputs_diff_sign and (((a_u8 ^ res_u8) & 0x80) != 0) else 0
            # Carry as 'no borrow'
            self.flags["C"] = 1 if a_u8 >= b_u8 else 0
            _set_zn_from_val(self.flags, v)
            self._on_execute("SUB8 (via LUT) ; RES ← SRC1 - SRC2")
            return ch

        if op == "PACK":
            (var,) = args
            u8 = self._read_u8_from_group("RES")
            v = u8 if u8 < 128 else u8 - 256
            self.mem.set(str(var), v)
            ch[str(var)] = v
            self._on_execute(f"PACK {var} ← RES ({v})")
            return ch

        # --- 비트 연산 (Z/N 갱신, V=0) ---
        if op in ("AND", "OR", "XOR"):
            dst, src = args
            dst_name, src_name = str(dst), str(src)
            a = self.mem.get(dst_name)
            b = self.mem.get(src_name)

            self._write_u8_to_group("SRC1", _to_u8(a))
            self._write_u8_to_group("SRC2", _to_u8(b))

            lut_func = {
                "AND": and8_via_lut, "OR": or8_via_lut, "XOR": xor8_via_lut
            }[op]
            lut_func(self.mem, src1=SRC1, src2=SRC2, dst=RES, lsb_first=False)

            res_u8 = self._read_u8_from_group("RES")
            v = res_u8 if res_u8 < 128 else res_u8 - 256
            self.mem.set(dst_name, v)

            self.flags["V"] = 0
            _set_zn_from_val(self.flags, v)
            op_symbol = {'AND':'&', 'OR':'|', 'XOR':'^'}[op]
            self._on_execute(f"{op:<4} {dst}, {src} ; via LUT {dst_name}:{a}{op_symbol}{b}→{v} | Z={self.flags['Z']} N={self.flags['N']}")
            ch[dst_name] = v
            return ch

        # --- 시프트 ---
        if op == "SHL":
            dst, = args
            dst_name = str(dst)
            a = self.mem.get(dst_name)
            
            self._write_u8_to_group("SRC1", _to_u8(a))
            shl8_via_lut(self.mem, src=SRC1, dst=RES, lsb_first=False)
            
            res_u8 = self._read_u8_from_group("RES")
            v = res_u8 if res_u8 < 128 else res_u8 - 256
            
            # Carry out from MSB before shift
            self.flags["C"] = 1 if (_to_u8(a) & 0x80) else 0
            # SHL overflow: 최상위 비트 변화 여부로 판단
            ov = 1 if (_sign_bit(a) != _sign_bit(v)) else 0
            self.mem.set(dst_name, v)
            self.flags["V"] = ov
            _set_zn_from_val(self.flags, v)
            self._on_execute(f"SHL  {dst} ; via LUT {a:4d}<<1 -> {v:4d} | V={ov} Z={self.flags['Z']} N={self.flags['N']}")
            ch[dst_name] = v
            return ch

        if op == "SHR":
            dst, = args
            dst_name = str(dst)
            a = self.mem.get(dst_name)

            self._write_u8_to_group("SRC1", _to_u8(a))
            shr8_via_lut(self.mem, src=SRC1, dst=RES, lsb_first=False)

            res_u8 = self._read_u8_from_group("RES")
            v = res_u8 if res_u8 < 128 else res_u8 - 256
            self.mem.set(dst_name, v)

            # Carry out from LSB
            self.flags["C"] = 1 if (_to_u8(a) & 0x01) else 0
            self.flags["V"] = 0 # ASR은 오버플로우 없음
            _set_zn_from_val(self.flags, v)
            self._on_execute(f"SHR  {dst} ; via LUT {a:4d}>>1 -> {v:4d} | V=0 Z={self.flags['Z']} N={self.flags['N']}")
            ch[dst_name] = v
            return ch

        # --- 비교/분기 ---
        if op == "CMP" or op == "CMPI":
            a_name, b_arg = args
            a = self.mem.get(str(a_name))
            b = int(b_arg) if op == "CMPI" else self.mem.get(str(b_arg))

            self._write_u8_to_group("SRC1", _to_u8(a))
            self._write_u8_to_group("SRC2", _to_u8(b))
            sub8_via_lut(self.mem, src1=SRC1, src2=SRC2, dst=RES, lsb_first=False)

            res_u8 = self._read_u8_from_group("RES")
            v = res_u8 if res_u8 < 128 else res_u8 - 256

            inputs_diff_sign = _sign_bit(a) != _sign_bit(b)
            self.flags["V"] = 1 if inputs_diff_sign and (_sign_bit(a) != _sign_bit(v)) else 0
            # Carry as 'no borrow' like SUB
            self.flags["C"] = 1 if _to_u8(a) >= _to_u8(b) else 0
            _set_zn_from_val(self.flags, v)
            
            b_str = f"#{b}" if op == "CMPI" else str(b_arg)
            self._on_execute(f"{op:<4} {a_name}, {b_str} ; via LUT ({a}-{b}) → Z={self.flags['Z']} N={self.flags['N']} V={self.flags['V']}")
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
        # Stage: FETCH (비동기 표시)
        try:
            post_stage("FETCH")
        except Exception:
            pass
        # Update PC indicator for current instruction address
        try:
            update_pc(self.pc.value)
        except Exception:
            pass
        # Try to render approximate machine encoding as 2-byte binary (xxxx xxxx xxxx xxxx)
        enc_bits = ""
        try:
            enc = encode_from_source_line_fixed(text)
            if enc is not None:
                op4, dst4, arg8 = enc
                b0 = ((op4 & 0xF) << 4) | (dst4 & 0xF)
                b1 = arg8 & 0xFF
                bits16 = f"{(b0<<8)|b1:016b}"
                grouped = " ".join(bits16[i:i+4] for i in range(0, 16, 4))
                enc_bits = f" | ENC {grouped}"
                # Also set IR visualization here (avoid re-parsing later)
                try:
                    set_ir(op4, dst4, arg8)
                except Exception:
                    pass
        except Exception:
            enc_bits = ""
        self._println(f"[FETCH] PC={self.pc.value:02d}  line='{text}'{enc_bits}")
        # IR already updated above

    def _on_decode(self, decoded: Tuple[str, tuple[Any, ...]]) -> None:
        op, args = decoded
        # Stage: DECODE (비동기 표시)
        try:
            post_stage("DECODE")
        except Exception:
            pass
        self._println(f"[DECODE] {op} {args}")
        # IR는 FETCH 단계에서 고수준 라인 기준으로 이미 표시함

    def _on_execute(self, desc: str) -> None:
        # Stage: EXECUTE (비동기 표시)
        try:
            post_stage("EXECUTE")
        except Exception:
            pass
        self._println(f"[EXEC]   {desc}")

    def _on_writeback(self, changes: Dict[str, int]) -> None:
        if changes:
            ch = ", ".join(f"{k}={v:4d}" for k, v in changes.items())
            # Stage: WRITEBACK (비동기 표시)
            try:
                post_stage("WRITEBACK")
            except Exception:
                pass
            self._println(f"[WB]     {ch}")
        else:
            # Stage: WRITEBACK (비동기 표시: 변경 없어도 동일)
            try:
                post_stage("WRITEBACK")
            except Exception:
                pass
            self._println("[WB]     (no changes)")

    def _on_pc_advance(self, old: int, new: int) -> None:
        self._println(f"[PC]     {old:02d} -> {new:02d}")

    def _on_halt(self) -> None:
        self._println("[HALT]   Program finished or PC out of range.")
        # Clear indicators on halt for a clean stop
        try:
            clear_stages()
        except Exception:
            pass
        # IR off on halt
        try:
            clear_ir()
        except Exception:
            pass
        # Turn off PC indicators on halt
        try:
            clear_pc()
        except Exception:
            pass
        # Ensure PAUSE on HALT
        try:
            run_off()
        except Exception:
            pass

    def _println(self, s: str) -> None:
        if self.debug:
            print(s)
