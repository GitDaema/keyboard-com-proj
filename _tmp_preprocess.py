import sys, os
sys.path.insert(0, os.path.join(os.getcwd(), 'src'))
from sim.parser import preprocess_program
prog = [
    "start:",
    "a = -7",
    "x = 5",
    "s = 0",
    "IF a < #0 THEN",
    "    a = 0 - a",
    "END",
    "IF a == x THEN",
    "    d = 1",
    "ELSE",
    "    d = 0",
    "END",
    "loop:",
    "CMPI a, #0",
    "BEQ done",
    "a = a - 1",
    "JMP loop",
    "done:",
    "HALT",
]
exp = preprocess_program(prog)
for i, line in enumerate(exp):
    print(f"{i:02d}: {line}")
