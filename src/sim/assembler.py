from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional

from sim.parser import preprocess_program
from utils.keyboard_presets import VAR_TO_ID


# 4-bit opcode map (execution encoding)
OPCODES: Dict[str, int] = {
    "NOP": 0x0, "HALT": 0x1,
    "MOV": 0x2, "MOVI": 0x3,
    "ADD": 0x4, "ADDI": 0x5,
    "SUB": 0x6, "SUBI": 0x7,
    "AND": 0x8, "OR": 0x9, "XOR": 0xA,
    # SHIFT group: ARG bit0 selects direction (0:SHL, 1:SHR)
    "SHIFT": 0xB,
    # New unary negation
    "NEG": 0xC,
    "CMP": 0xD, "CMPI": 0xD,
    "JMP": 0xE,
    "BR":  0xF,  # Conditional branches (cond in DST)
    # Prefix/extension (shares 0x0 with NOP, distinguished by DST!=0)
    "EXT": 0x0,
}

# Branch condition nibble encoding (in DST)
BR_COND: Dict[str, int] = {
    "BEQ": 0x0, "BNE": 0x1,  # Z==1 / Z==0
    "BPL": 0x2, "BMI": 0x3,  # N==0 / N==1
    "BVC": 0x4, "BVS": 0x5,  # V==0 / V==1
    "BCC": 0x6, "BCS": 0x7,  # alias to V (legacy carry mapping)
}


@dataclass
class AsmInsn:
    op4: int
    dst4: int
    arg8: int
    text: str

# EXT type codes encoded in DST nibble when op4==EXT
EXT_TYPE_IMM = 0xE  # immediate payload in ARG8


def _is_label_line(s: str) -> Optional[str]:
    t = s.strip()
    if t.endswith(":") and (":" not in t[:-1]):
        name = t[:-1].strip()
        return name or None
    return None


def _is_int_literal(tok: str) -> bool:
    try:
        int(tok.strip().lstrip('#'), 0)
        return True
    except Exception:
        return False


def _to_int(tok: str) -> int:
    t = tok.strip()
    if t.startswith('#'):
        t = t[1:]
    return int(t, 0)


def _var_id(name: str) -> int:
    return int(VAR_TO_ID.get(name.strip().lower(), 0)) & 0xF


def _split2(csv: str) -> Tuple[str, str]:
    parts = [t.strip() for t in csv.split(',', 1)]
    if len(parts) != 2:
        return (csv.strip(), "")
    return parts[0], parts[1]


def _emit(debug: bool, out: List[AsmInsn], op: str, dst: int, arg: int, text: str):
    op4 = OPCODES[op]
    insn = AsmInsn(op4=op4, dst4=dst & 0xF, arg8=arg & 0xFF, text=text)
    out.append(insn)
    if debug:
        idx = len(out) - 1  # PC address for this instruction
        print(f"[ASM {idx:02d}] emit {text:<24} -> op={op4:X} dst={dst & 0xF:X} arg={arg & 0xFF:02X}")


def _assemble_line(s: str, out: List[AsmInsn], branch_fixups: List[Tuple[int, str]], labels: Dict[str, int], *, debug: bool) -> None:
    # Handle comment/blank
    up = s.strip()
    if not up or up.startswith('#'):
        _emit(debug, out, "NOP", 0, 0, "NOP")
        return

    # Labels handled in pass that calls us; here we ignore label lines
    if _is_label_line(s):
        return

    # Canonical uppercase for opcode checks
    U = up.upper()

    # Direct ISA forms
    if U == "HALT":
        _emit(debug, out, "HALT", 0, 0, "HALT")
        return
    if U == "NOP":
        _emit(debug, out, "NOP", 0, 0, "NOP")
        return

    # MOV/MOVI
    if U.startswith("MOVI "):
        dst, imm = _split2(up[5:])
        _emit(debug, out, "MOVI", _var_id(dst), _to_int(imm), f"MOVI {dst},{imm}")
        return
    if U.startswith("MOV "):
        dst, src = _split2(up[4:])
        _emit(debug, out, "MOV", _var_id(dst), _var_id(src), f"MOV {dst},{src}")
        return

    # ADD/ADDI
    if U.startswith("ADDI "):
        dst, imm = _split2(up[5:])
        _emit(debug, out, "ADDI", _var_id(dst), _to_int(imm), f"ADDI {dst},{imm}")
        return
    if U.startswith("ADD "):
        dst, src = _split2(up[4:])
        _emit(debug, out, "ADD", _var_id(dst), _var_id(src), f"ADD {dst},{src}")
        return

    # SUB/SUBI
    if U.startswith("SUBI "):
        dst, imm = _split2(up[5:])
        _emit(debug, out, "SUBI", _var_id(dst), _to_int(imm), f"SUBI {dst},{imm}")
        return
    if U.startswith("SUB "):
        dst, src = _split2(up[4:])
        _emit(debug, out, "SUB", _var_id(dst), _var_id(src), f"SUB {dst},{src}")
        return

    # Bitwise
    if U.startswith("AND "):
        dst, src = _split2(up[4:])
        _emit(debug, out, "AND", _var_id(dst), _var_id(src), f"AND {dst},{src}")
        return
    if U.startswith("OR "):
        dst, src = _split2(up[3:])
        _emit(debug, out, "OR", _var_id(dst), _var_id(src), f"OR {dst},{src}")
        return
    if U.startswith("XOR "):
        dst, src = _split2(up[4:])
        _emit(debug, out, "XOR", _var_id(dst), _var_id(src), f"XOR {dst},{src}")
        return

    # Shift
    if U.startswith("SHL "):
        dst = up[4:].strip()
        # SHIFT with arg bit0 = 0 indicates SHL
        _emit(debug, out, "SHIFT", _var_id(dst), 0x00, f"SHL {dst}")
        return
    if U.startswith("SHR "):
        dst = up[4:].strip()
        # SHIFT with arg bit0 = 1 indicates SHR
        _emit(debug, out, "SHIFT", _var_id(dst), 0x01, f"SHR {dst}")
        return

    # CMP/CMPI
    if U.startswith("CMPI "):
        a, imm = _split2(up[5:])
        # Emit EXTI (imm8 payload) followed by CMP (register-form)
        _emit(debug, out, "EXT", EXT_TYPE_IMM, _to_int(imm), f"EXTI #{imm}")
        _emit(debug, out, "CMP", _var_id(a), 0, f"CMP {a},#imm")
        return
    if U.startswith("CMP "):
        a, b = _split2(up[4:])
        _emit(debug, out, "CMP", _var_id(a), _var_id(b), f"CMP {a},{b}")
        return

    # Branches
    for mnem in ("BEQ", "BNE", "BMI", "BPL", "BVS", "BVC", "BCS", "BCC"):
        if U.startswith(mnem + " "):
            label = up[len(mnem)+1:].strip()
            # Placeholder offset; fix in pass 2
            cond = BR_COND[mnem]
            _emit(debug, out, "BR", cond, 0, f"{mnem} {label}")
            branch_fixups.append((len(out) - 1, label))
            return

    if U.startswith("JMP "):
        label = up[4:].strip()
        _emit(debug, out, "JMP", 0, 0, f"JMP {label}")
        branch_fixups.append((len(out) - 1, label))
        return

    # High-level assignment forms
    if "=" in up:
        left, right = [t.strip() for t in up.split('=', 1)]

        # Immediate move: x = imm
        if _is_int_literal(right):
            _emit(debug, out, "MOVI", _var_id(left), _to_int(right), f"MOVI {left},{right}")
            return

        # Addition: x = a + b
        if "+" in right:
            a, b = [t.strip() for t in right.split('+', 1)]
            if left == a and _is_int_literal(b):
                _emit(debug, out, "ADDI", _var_id(left), _to_int(b), f"ADDI {left},{b}")
                return
            if left == b and _is_int_literal(a):
                _emit(debug, out, "ADDI", _var_id(left), _to_int(a), f"ADDI {left},{a}")
                return
            if left == a and not _is_int_literal(b):
                _emit(debug, out, "ADD", _var_id(left), _var_id(b), f"ADD {left},{b}")
                return
            if left == b and not _is_int_literal(a):
                _emit(debug, out, "ADD", _var_id(left), _var_id(a), f"ADD {left},{a}")
                return
            # General case: MOV left,a; ADD left,b/ADDI
            if _is_int_literal(a):
                _emit(debug, out, "MOVI", _var_id(left), _to_int(a), f"MOVI {left},{a}")
            else:
                _emit(debug, out, "MOV", _var_id(left), _var_id(a), f"MOV {left},{a}")
            if _is_int_literal(b):
                _emit(debug, out, "ADDI", _var_id(left), _to_int(b), f"ADDI {left},{b}")
            else:
                _emit(debug, out, "ADD", _var_id(left), _var_id(b), f"ADD {left},{b}")
            return

        # Subtraction: x = a - b
        if "-" in right:
            a, b = [t.strip() for t in right.split('-', 1)]
            # Special case: x = 0 - x  → NEG x
            if left == b and _is_int_literal(a) and _to_int(a) == 0:
                _emit(debug, out, "NEG", _var_id(left), 0, f"NEG {left}")
                return
            if left == a and _is_int_literal(b):
                _emit(debug, out, "SUBI", _var_id(left), _to_int(b), f"SUBI {left},{b}")
                return
            if left == a and not _is_int_literal(b):
                _emit(debug, out, "SUB", _var_id(left), _var_id(b), f"SUB {left},{b}")
                return
            # General: MOV left,a; SUB left,b/ SUBI
            if _is_int_literal(a):
                _emit(debug, out, "MOVI", _var_id(left), _to_int(a), f"MOVI {left},{a}")
            else:
                _emit(debug, out, "MOV", _var_id(left), _var_id(a), f"MOV {left},{a}")
            if _is_int_literal(b):
                _emit(debug, out, "SUBI", _var_id(left), _to_int(b), f"SUBI {left},{b}")
            else:
                _emit(debug, out, "SUB", _var_id(left), _var_id(b), f"SUB {left},{b}")
            return

        # Simple move: x = y
        _emit(debug, out, "MOV", _var_id(left), _var_id(right), f"MOV {left},{right}")
        return

    # Unsupported or comment-like → NOP to keep PC mapping simple
    _emit(debug, out, "NOP", 0, 0, f"NOP ; {s}")


def assemble_program(lines: List[str], *, debug: bool = False) -> List[AsmInsn]:
    """Assemble high-level program lines into execution ISA (2-byte) list.
    - Preprocess IF/ELSE/END using existing preprocessor.
    - Map labels to instruction indices; branch offsets are PC-relative (signed 8-bit).
    - Expand expressions (x=a+b/x=a-b) to minimal instruction sequences.
    - Returns a flat list of instructions.
    """
    src = preprocess_program(lines)
    out: List[AsmInsn] = []
    labels: Dict[str, int] = {}
    branch_fixups: List[Tuple[int, str]] = []

    # Pass 1: collect labels and emit provisional instructions
    pc = 0
    for raw in src:
        name = _is_label_line(raw)
        if name:
            # Map label to current PC (index in instruction stream)
            labels.setdefault(name, pc)
            if debug:
                print(f"[ASM] label {name} -> {pc}")
            continue
        before = len(out)
        _assemble_line(raw, out, branch_fixups, labels, debug=debug)
        pc += (len(out) - before)

    # Pass 2: resolve branches/JMP
    for idx, label in branch_fixups:
        if label not in labels:
            raise ValueError(f"Undefined label: {label}")
        target = labels[label]
        rel = target - (idx + 1)  # PC-relative to next insn
        if not (-128 <= rel <= 127):
            raise ValueError(f"Branch out of range at {idx}: {label} -> {rel}")
        insn = out[idx]
        if insn.op4 == OPCODES["JMP"]:
            out[idx] = AsmInsn(op4=insn.op4, dst4=0, arg8=rel & 0xFF, text=insn.text)
        elif insn.op4 == OPCODES["BR"]:
            out[idx] = AsmInsn(op4=insn.op4, dst4=insn.dst4, arg8=rel & 0xFF, text=insn.text)
        if debug:
            print(f"[ASM] fixup @{idx}: {insn.text} -> rel={rel}")

    return out


__all__ = [
    "AsmInsn",
    "assemble_program",
    "OPCODES",
    "BR_COND",
    "EXT_TYPE_IMM",
]
