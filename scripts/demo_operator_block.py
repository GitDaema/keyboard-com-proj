"""
Quick demo to visualize operator shapes on the 3x3 block
(PrintScreen..PageDown). Requires OpenRGB server running.

Run:
  python -m scripts.demo_operator_block
"""

import time

from rgb_controller import connect, disconnect, init_all_keys
from utils.operator_indicator import display_operator


OPS = [
    # Arithmetic
    "+", "-", "*", "/", "%",
    "=",
    # Comparison
    "<", ">", "==", "!=", "<=", ">=",
    # Bitwise
    "&", "|", "^", "~", "nand", "nor", "xnor",
    # Shifts/rotates
    "<<", ">>", "rol", "ror",
    # Logical
    "&&", "||", "!",
]


def main() -> None:
    connect()
    try:
        init_all_keys()
        for op in OPS:
            print(f"[DEMO] Showing '{op}' (press Enter to continue)...")
            display_operator(op)
            try:
                input()
            except Exception:
                time.sleep(0.8)
        # Restore
        init_all_keys()
    finally:
        disconnect()


if __name__ == "__main__":
    main()

