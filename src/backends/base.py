from __future__ import annotations

from typing import Protocol, Iterable, Tuple, Dict
from rgb_types import RGBColor


class RGBBackend(Protocol):
    def connect(self) -> bool: ...
    def disconnect(self) -> None: ...
    def is_connected(self) -> bool: ...

    def init_all_keys(self, total_leds: int, debug: bool = False) -> bool: ...

    def set_color(self, index: int, color: RGBColor) -> bool: ...

    def set_many(self, indices: Iterable[int], colors: Iterable[RGBColor]) -> bool: ...

    def get_color(self, index: int, fresh: bool = True) -> Tuple[int, int, int]: ...


class NoopBackend:
    """A safe backend that never touches hardware but caches state.
    Useful fallback when HID protocol is not available yet.
    """
    def __init__(self) -> None:
        self._conn = True
        self._cache: Dict[int, Tuple[int, int, int]] = {}

    def connect(self) -> bool:
        self._conn = True
        return True

    def disconnect(self) -> None:
        self._conn = False
        self._cache.clear()

    def is_connected(self) -> bool:
        return self._conn

    def init_all_keys(self, total_leds: int, debug: bool = False) -> bool:
        for i in range(int(total_leds)):
            self._cache[i] = (0, 0, 0)
        return True

    def set_color(self, index: int, color: RGBColor) -> bool:
        self._cache[int(index)] = color.as_tuple()
        return True

    def set_many(self, indices: Iterable[int], colors: Iterable[RGBColor]) -> bool:
        for i, c in zip(indices, colors):
            self._cache[int(i)] = c.as_tuple()
        return True

    def get_color(self, index: int, fresh: bool = True) -> Tuple[int, int, int]:
        return self._cache.get(int(index), (0, 0, 0))