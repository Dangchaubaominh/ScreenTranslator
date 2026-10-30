"""Chụp màn hình bằng mss (pixel thật) và đổi tọa độ sang hệ tọa độ logic của Qt."""

from dataclasses import dataclass

import mss
from PIL import Image


@dataclass(frozen=True)
class Monitor:
    left: int
    top: int
    width: int
    height: int  # pixel thật, trong hệ tọa độ màn hình ảo


@dataclass(frozen=True)
class Region:
    """Vùng chữ người dùng đã chọn, tính bằng pixel thật, kèm cách đổi sang tọa độ logic để vẽ overlay."""

    left: int
    top: int
    width: int
    height: int
    monitor: Monitor
    logical_origin: tuple[int, int]  # góc trên-trái của màn hình chứa vùng, theo tọa độ logic của Qt
    dpr: float  # tỉ lệ pixel thật / pixel logic của màn hình đó (125% → 1.25)

    @classmethod
    def from_physical(
        cls, monitor: Monitor, logical_origin: tuple[int, int], dpr: float, left: int, top: int, right: int, bottom: int
    ) -> "Region":
        """Vùng tính bằng pixel thật trên màn hình ảo, cắt cho nằm trong `monitor`."""
        left, top = max(left, monitor.left), max(top, monitor.top)
        right = min(right, monitor.left + monitor.width)
        bottom = min(bottom, monitor.top + monitor.height)
        return cls(left, top, max(0, right - left), max(0, bottom - top), monitor, logical_origin, dpr)

    @classmethod
    def from_selection(
        cls, monitor: Monitor, logical_origin: tuple[int, int], dpr: float, x: int, y: int, w: int, h: int
    ) -> "Region":
        """Vùng chọn (x, y, w, h) tính bằng tọa độ logic, đo từ góc trên-trái màn hình."""
        return cls.from_physical(
            monitor,
            logical_origin,
            dpr,
            monitor.left + round(x * dpr),
            monitor.top + round(y * dpr),
            monitor.left + round((x + w) * dpr),
            monitor.top + round((y + h) * dpr),
        )

    def sub(self, left: int, top: int, right: int, bottom: int) -> "Region":
        """Vùng con; tọa độ tính trong ảnh chụp của vùng này (vd. khung một dòng chữ OCR tìm được)."""
        return Region(
            self.left + left, self.top + top, right - left, bottom - top, self.monitor, self.logical_origin, self.dpr
        )

    def to_logical(self) -> tuple[int, int, int, int]:
        ox, oy = self.logical_origin
        return (
            ox + round((self.left - self.monitor.left) / self.dpr),
            oy + round((self.top - self.monitor.top) / self.dpr),
            round(self.width / self.dpr),
            round(self.height / self.dpr),
        )

    def crop_box(self) -> tuple[int, int, int, int]:
        """Hộp cắt trong ảnh chụp cả màn hình `monitor`."""
        x, y = self.left - self.monitor.left, self.top - self.monitor.top
        return x, y, x + self.width, y + self.height


def monitor_at(x: int, y: int) -> Monitor:
    """Màn hình chứa điểm (x, y) tính bằng pixel thật; không thấy thì lấy màn hình chính."""
    with mss.mss() as sct:
        found = next(
            (
                m
                for m in sct.monitors[1:]
                if m["left"] <= x < m["left"] + m["width"] and m["top"] <= y < m["top"] + m["height"]
            ),
            sct.monitors[1],
        )
    return Monitor(found["left"], found["top"], found["width"], found["height"])


def grab(left: int, top: int, width: int, height: int) -> Image.Image:
    with mss.mss() as sct:
        shot = sct.grab({"left": left, "top": top, "width": width, "height": height})
    return Image.frombytes("RGB", shot.size, shot.rgb)


def grab_monitor(monitor: Monitor) -> Image.Image:
    return grab(monitor.left, monitor.top, monitor.width, monitor.height)


def grab_region(region: Region) -> Image.Image:
    return grab(region.left, region.top, region.width, region.height)
