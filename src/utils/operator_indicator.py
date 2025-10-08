from __future__ import annotations

"""
Operator LED indicator (3x3 on PrintScreen..PageDown block)

Numbering (fixed):
  7 8 9   = print_screen, scroll_lock, pause_break
  4 5 6   = insert,       home,        page_up
  1 2 3   = delete,       end,         page_down

Usage:
  from utils.operator_indicator import display_operator
  display_operator("+")

This module only uses rgb_controller public helpers and keeps updates atomic
so it won’t disturb other parts of the system.
"""

from typing import Dict, Iterable, Optional, Set, Tuple

from openrgb.utils import RGBColor

from rgb_controller import set_labels_atomic
import utils.color_presets as cp


# --- Grid mapping: index -> keyboard label ---
IDX_TO_LABEL: Dict[int, str] = {
    1: "delete",
    2: "end",
    3: "page_down",
    4: "insert",
    5: "home",
    6: "page_up",
    7: "print_screen",
    8: "scroll_lock",
    9: "pause_break",
}


# --- Category palette (simple color separation to lower ambiguity) ---
CATEGORY_COLOR: Dict[str, RGBColor] = {
    # Arithmetic
    "arith": cp.BLUE,
    # Comparison
    "cmp": cp.PINK,
    # Bitwise
    "bit": cp.YELLOW,
    # Logical
    "logic": cp.GREEN,
    # Shift/Rotate
    "shift": getattr(cp, "ORANGE_BRIGHT", cp.ORANGE),
}

OFF_COLOR: RGBColor = cp.DARK_GRAY


def _set_grid(lit: Iterable[int], color: RGBColor) -> bool:
    """Apply colors to the 3x3 group in one atomic update.
    - Unlit cells use a dim OFF gray.
    - Lit cells use the provided color.
    """
    lit_set: Set[int] = {int(i) for i in lit}
    label_to_color: Dict[str, RGBColor] = {}
    for idx, lbl in IDX_TO_LABEL.items():
        label_to_color[lbl] = color if idx in lit_set else OFF_COLOR
    return set_labels_atomic(label_to_color)


# --- Shape dictionary: operation token -> (category, lit indices) ---
# Keep shapes simple and static (no blinking) per request.
OP_SHAPES: Dict[str, Tuple[str, Set[int]]] = {}


def _reg(tokens: Iterable[str], category: str, idxs: Iterable[int]) -> None:
    s = set(int(i) for i in idxs)
    for t in tokens:
        OP_SHAPES[t] = (category, s)


# Arithmetic
_reg(["+", "add", "+="], "arith", [2, 4, 5, 6, 8])
_reg(["-", "sub", "-="], "arith", [4, 5, 6])
_reg(["*", "×", "mul", "*="], "arith", [1, 3, 5, 7, 9])
_reg(["/", "÷", "div", "/="], "arith", [1, 5, 9])
_reg(["%", "mod", "%="], "arith", [1, 2, 3, 4, 6, 7, 8, 9])  # ring (center off)

# Assignment / Move
_reg(["=", "mov", "movq", "movi"], "arith", [1, 2, 3, 7, 8, 9])  # reuse arith palette

# Comparison (static, color distinguishes from assignment)
_reg(["<"], "cmp", [3, 5, 7])
_reg([">"], "cmp", [1, 5, 9])
_reg(["==", "eq"], "cmp", [1, 2, 3, 7, 8, 9])
_reg(["!=", "ne"], "cmp", [1, 3, 7, 9])  # X shape; distinct by magenta color
# Add a simple underline/overline to suggest the '=' part without animation
_reg(["<=", "le"], "cmp", [3, 5, 7, 1, 2, 3])   # '<' + bottom row
_reg([">=", "ge"], "cmp", [1, 5, 9, 7, 8, 9])   # '>' + top row

# Bitwise
_reg(["&", "and"], "bit", [1, 4, 8, 6, 3])      # ∧
_reg(["|", "bor"], "bit", [2, 5, 8])            # |
_reg(["^", "xor"], "bit", [1, 3, 7, 9])         # X corners
_reg(["~", "not", "bnot"], "bit", [7, 8, 9])    # overline (NOT)
_reg(["nand"], "bit", [1, 4, 8, 6, 3, 7, 8, 9])  # ∧ + overline
_reg(["nor"], "bit", [2, 5, 7, 8, 9])            # | + overline
_reg(["xnor", "eqv"], "bit", [1, 3, 7, 8, 9])   # X + overline

# Shifts / Rotates
_reg(["<<", "shl"], "shift", [1, 4, 5, 6, 7])
_reg([">>", "shr"], "shift", [3, 4, 5, 6, 9])
_reg(["rol"], "shift", [1, 4, 5, 6, 7, 2, 8])
_reg(["ror"], "shift", [3, 4, 5, 6, 9, 2, 8])

# Logical
_reg(["&&", "land"], "logic", [1, 4, 8, 5, 6, 3])  # thicker ∧
_reg(["||", "lor"], "logic", [2, 5, 8])
_reg(["!", "lnot"], "logic", [8, 5, 2])

# No-op: center dim or fully off. Keep very dim to show reserved area.
_reg(["nop", "none"], "logic", [5])


def display_operator(op: str, *, color_override: Optional[RGBColor] = None) -> bool:
    """Light up the 3x3 block to depict an operator.

    - op: string token, e.g., '+', '==', '<<', '&&', 'mov', 'rol'.
    - color_override: optional RGBColor to force a color.
    Returns True on any update attempt (best-effort).
    """
    key = (op or "").strip().lower()
    cat, idxs = OP_SHAPES.get(key, ("logic", {5}))
    col = color_override or CATEGORY_COLOR.get(cat, cp.WHITE)
    return _set_grid(idxs, col)


__all__ = [
    "display_operator",
    "IDX_TO_LABEL",
    "CATEGORY_COLOR",
]
