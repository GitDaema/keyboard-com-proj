from typing import List, Tuple, Any

Op = Tuple[str, tuple[Any, ...]]

def parse_line(line: str) -> List[Op]:
    s = line.strip()
    if not s or s.startswith("#"):
        return [("NOP", ())]

    # 라벨: "name:" (콜론이 맨 끝에 하나만 있는 경우)
    if s.endswith(":") and (":" not in s[:-1]):
        name = s[:-1].strip()
        return [("LABEL", (name,))] if name else [("NOP", ())]

    up = s.upper()

    # 단일 토큰류
    if up == "HALT":
        return [("HALT", ())]
    if up == "NOP":
        return [("NOP", ())]
    if up == "ADD8":
        return [("ADD8", ())]
    if up == "SUB8":
        return [("SUB8", ())]
    if up == "PRINT_RES":         # ← 추가
        return [("PRINT_RES", ())]

    # --- PRINT 확장: "PRINT a + b"도 비트 경유 + PRINT_RES 로 ---
    if up.startswith("PRINT "):
        expr = s[6:].strip()
        # 1) 덧셈 표현식: UNPACK/LOAD → ADD8 → (RES에 결과) → PRINT_RES
        if "+" in expr:
            a, b = [t.strip() for t in expr.split("+", 1)]
            ops: List[Op] = []

            def emit_load_into(group: str, token: str):
                if _is_int_literal(token):
                    ops.append(("LOADI8_BITS", (group, _parse_int(token))))
                else:
                    ops.append(("UNPACK1" if group=="SRC1" else "UNPACK2", (token,)))

            emit_load_into("SRC1", a)
            emit_load_into("SRC2", b)
            ops.append(("ADD8", ()))
            # tmp 변수 없이 RES에서 직접 출력
            ops.append(("PRINT_RES", ()))
            return ops

        # 2) 단일 변수/리터럴: RES에 적재해놓고 바로 출력
        ops: List[Op] = []
        if _is_int_literal(expr):
            ops.append(("LOADI8_BITS", ("SRC1", _parse_int(expr))))
            ops.append(("COPYBITS", ("RES", "SRC1")))
        else:
            ops.append(("UNPACK1", (expr,)))
            ops.append(("COPYBITS", ("RES", "SRC1")))
        ops.append(("PRINT_RES", ()))
        return ops

    # --- 분기/점프/비교 ---
    if up.startswith("JMP "):
        label = s[4:].strip()
        return [("JMP", (label,))]
    if up.startswith("BEQ "):
        label = s[4:].strip()
        return [("BEQ", (label,))]
    if up.startswith("BNE "):
        label = s[4:].strip()
        return [("BNE", (label,))]
    # V(overflow) 기반 분기 (신규)
    if up.startswith("BVC "):
        label = s[4:].strip()
        return [("BVC", (label,))]
    if up.startswith("BVS "):
        label = s[4:].strip()
        return [("BVS", (label,))]
    # 하위 호환: C기반 표기(BCC/BCS)를 V로 해석
    if up.startswith("BCC "):
        label = s[4:].strip()
        return [("BCC", (label,))]
    if up.startswith("BCS "):
        label = s[4:].strip()
        return [("BCS", (label,))]
    if up.startswith("BMI "):
        label = s[4:].strip()
        return [("BMI", (label,))]
    if up.startswith("BPL "):
        label = s[4:].strip()
        return [("BPL", (label,))]

    # CMP/CMPI: 두 번째 피연산자가 '#'면 CMPI
    if up.startswith("CMP "):
        a, b = _split2(s[4:])
        if b.startswith("#"):
            return [("CMPI", (a, _parse_int(b[1:])))]
        return [("CMP", (a, b))]
    if up.startswith("CMPI "):
        a, imm = _split2(s[5:])
        imm = imm.strip()
        if imm.startswith("#"):
            return [("CMPI", (a, _parse_int(imm[1:])))]
        return [("CMPI", (a, _parse_int(imm)))]

    # --- 저수준: MOV/ADD/ADDI/SUB/SUBI/비트/시프트 ---

    # MOV/MOVI: 두 번째가 즉시이면 MOVI
    if up.startswith("MOV "):
        dst, src = _split2(s[4:])
        if src.startswith("#"):
            return [("MOVI", (dst, _parse_int(src[1:])))]
        return [("MOV", (dst, src))]

    # ADD/ADDI
    if up.startswith("ADD "):
        dst, src = _split2(s[4:])
        if src.startswith("#"):
            return [("ADDI", (dst, _parse_int(src[1:])))]
        return [("ADD", (dst, src))]
    if up.startswith("ADDI "):
        dst, imm = _split2(s[5:])
        imm = imm.strip()
        if imm.startswith("#"):
            return [("ADDI", (dst, _parse_int(imm[1:])))]
        return [("ADDI", (dst, _parse_int(imm)))]

    # SUB/SUBI
    if up.startswith("SUB "):
        dst, src = _split2(s[4:])
        if src.startswith("#"):
            return [("SUBI", (dst, _parse_int(src[1:])))]
        return [("SUB", (dst, src))]
    if up.startswith("SUBI "):
        dst, imm = _split2(s[5:])
        imm = imm.strip()
        if imm.startswith("#"):
            return [("SUBI", (dst, _parse_int(imm[1:])))]
        return [("SUBI", (dst, _parse_int(imm)))]

    # 비트 연산
    if up.startswith("AND "):
        dst, src = _split2(s[4:])
        return [("AND", (dst, src))]
    if up.startswith("OR "):
        dst, src = _split2(s[3:])
        return [("OR", (dst, src))]
    if up.startswith("XOR "):
        dst, src = _split2(s[4:])
        return [("XOR", (dst, src))]

    # 시프트(단항) - SHR는 산술 시프트로 동작(부호 유지)
    if up.startswith("SHL "):
        dst = s[4:].strip()
        return [("SHL", (dst,))]
    if up.startswith("SHR "):
        dst = s[4:].strip()
        return [("SHR", (dst,))]
    
    # --- 비트 전용 마이크로옵 ---
    # UNPACK1 var  → var 값을 SRC1 8비트로
    # UNPACK2 var  → var 값을 SRC2 8비트로
    # UNPACK var, SRC1|SRC2
    if up.startswith("UNPACK1 "):
        var = s[len("UNPACK1 "):].strip()
        return [("UNPACK1", (var,))]
    if up.startswith("UNPACK2 "):
        var = s[len("UNPACK2 "):].strip()
        return [("UNPACK2", (var,))]
    if up.startswith("UNPACK "):
        a, b = _split2(s[len("UNPACK "):])
        return [("UNPACK", (a, b.upper()))]  # "SRC1"|"SRC2"

    # LOADI8_BITS group, #imm
    if up.startswith("LOADI8_BITS "):
        grp, imm = _split2(s[len("LOADI8_BITS "):])
        imm = imm.strip()
        if imm.startswith("#"):
            return [("LOADI8_BITS", (grp.upper(), _parse_int(imm[1:])))]
        return [("LOADI8_BITS", (grp.upper(), _parse_int(imm)))]

    # CLEARBITS group
    if up.startswith("CLEARBITS "):
        grp = s[len("CLEARBITS "):].strip().upper()
        return [("CLEARBITS", (grp,))]

    # COPYBITS dst, src  (예: COPYBITS RES, SRC1)
    if up.startswith("COPYBITS "):
        dst, src = _split2(s[len("COPYBITS "):])
        return [("COPYBITS", (dst.upper(), src.upper()))]

    # PACK var   (RES 비트 → var에 패킹)
    if up.startswith("PACK "):
        var = s[len("PACK "):].strip()
        return [("PACK", (var,))]

    # --- 고수준 대입식(=)을 비트 마이크로옵으로 내림 ---
    if "=" in s:
        left, right = [t.strip() for t in s.split("=", 1)]
        ops: List[Op] = []

        def emit_load_into(group: str, token: str):
            """group: 'SRC1'|'SRC2'에 token(변수 또는 리터럴)을 적재"""
            if _is_int_literal(token):
                ops.append(("LOADI8_BITS", (group, _parse_int(token))))
            else:
                if group == "SRC1":
                    ops.append(("UNPACK1", (token,)))
                else:
                    ops.append(("UNPACK2", (token,)))

        # 덧셈 대입: x = a + b
        if "+" in right:
            a, b = [t.strip() for t in right.split("+", 1)]
            if a != "":                  # ← a가 비어있지 않을 때만 이항 인식
                emit_load_into("SRC1", a)
                emit_load_into("SRC2", b)
                ops.append(("ADD8", ()))
                ops.append(("PACK", (left,)))
                return ops

        # 뺄셈 대입(선택): x = a - b  → 마이크로옵으로 내려 쓰고 싶다면 여기에 추가
        if "-" in right:
            a, b = [t.strip() for t in right.split("-", 1)]
            if a != "":                  # ← a가 비어있지 않을 때만 이항 인식
                emit_load_into("SRC1", a)
                emit_load_into("SRC2", b)
                ops.append(("SUB8", ()))
                ops.append(("PACK", (left,)))
                return ops

        # 단순 대입: x = y  또는 x = 5
        emit_load_into("SRC1", right)
        ops.append(("COPYBITS", ("RES", "SRC1")))  # RES ← SRC1
        ops.append(("PACK", (left,)))             # RES 패킹 → x
        return ops

    return [("NOP", ())]

# ---------------- helpers ----------------
def _split2(body: str) -> tuple[str, str]:
    parts = [t.strip() for t in body.split(",", 1)]
    if len(parts) != 2:
        return (body.strip(), "")
    return parts[0], parts[1]

def _is_int_literal(s: str) -> bool:
    try:
        int(s, 0)
        return True
    except:
        return False

def _parse_int(s: str) -> int:
    return int(s, 0)
