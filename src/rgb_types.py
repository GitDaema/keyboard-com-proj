from __future__ import annotations

from dataclasses import dataclass


def _clamp8(x: int) -> int:
    try:
        xi = int(x)
    except Exception:
        xi = 0
    if xi < 0:
        return 0
    if xi > 255:
        return 255
    return xi


@dataclass(frozen=True)
class RGBColor:
    """Lightweight RGB color used across the project.

    Compatible replacement for openrgb.utils.RGBColor used previously.
    Values are clamped to 0..255.
    """
    red: int
    green: int
    blue: int

    def __init__(self, red: int, green: int, blue: int) -> None:  # type: ignore[override]
        object.__setattr__(self, "red", _clamp8(red))
        object.__setattr__(self, "green", _clamp8(green))
        object.__setattr__(self, "blue", _clamp8(blue))

    def as_tuple(self) -> tuple[int, int, int]:
        return (self.red, self.green, self.blue)

    def __iter__(self):  # allows tuple(RGBColor(...)) if needed
        yield self.red
        yield self.green
        yield self.blue

    def __repr__(self) -> str:  # pragma: no cover (visual aid only)
        return f"RGBColor({self.red}, {self.green}, {self.blue})"