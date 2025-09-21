# sim/pc.py
from dataclasses import dataclass

@dataclass
class PC:
    value: int = 0

    def reset(self) -> None:
        self.value = 0

    def increment(self, n: int = 1) -> None:
        self.value += n

    def as_decimal_digits(self) -> tuple[int, int]:
        """10진 PC 표시(십의 자리, 일의 자리) - LED 표시 시 사용"""
        v = max(0, self.value)
        return (v // 10) % 10, v % 10
