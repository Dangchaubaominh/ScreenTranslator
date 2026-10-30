"""Màn hình chọn vùng: hiện ảnh chụp đứng yên của cả màn hình, người dùng kéo chuột khoanh vùng chữ."""

from PIL import Image
from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap, QScreen
from PySide6.QtWidgets import QWidget

MIN_SIZE = 8  # vùng nhỏ hơn (tính theo pixel logic) coi như bấm nhầm
HINT = "Kéo chuột để khoanh vùng chữ  ·  Esc hoặc chuột phải để huỷ"


def to_pixmap(image: Image.Image, dpr: float) -> QPixmap:
    rgb = image.convert("RGB")
    qimage = QImage(rgb.tobytes(), rgb.width, rgb.height, 3 * rgb.width, QImage.Format.Format_RGB888).copy()
    pixmap = QPixmap.fromImage(qimage)
    pixmap.setDevicePixelRatio(dpr)  # ảnh pixel thật hiển thị đúng kích thước logic của màn hình
    return pixmap


class RegionSelector(QWidget):
    selected = Signal(QRect)  # tọa độ logic, đo từ góc trên-trái màn hình
    cancelled = Signal()

    def __init__(self, screen: QScreen, shot: Image.Image):
        super().__init__(
            None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setGeometry(screen.geometry())
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._pixmap = to_pixmap(shot, screen.devicePixelRatio())
        self._start: QPoint | None = None
        self._end: QPoint | None = None
        self._finished = False

    def selection(self) -> QRect | None:
        if self._start is None or self._end is None:
            return None
        # không dùng QRect.normalized(): kéo ngược chiều thì nó hụt mỗi cạnh 1 pixel
        (x1, x2), (y1, y2) = sorted((self._start.x(), self._end.x())), sorted((self._start.y(), self._end.y()))
        return QRect(QPoint(x1, y1), QPoint(x2, y2))

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._pixmap)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 110))
        rect = self.selection()
        if rect is None:
            painter.setPen(QColor(255, 255, 255))
            font = QFont("Segoe UI")
            font.setPixelSize(18)
            painter.setFont(font)
            painter.drawText(self.rect().adjusted(0, 40, 0, 0), Qt.AlignmentFlag.AlignHCenter, HINT)
            return
        painter.setClipRect(rect)
        painter.drawPixmap(0, 0, self._pixmap)  # vùng đang chọn sáng lại
        painter.setClipping(False)
        painter.setPen(QPen(QColor(80, 160, 255), 2))
        painter.drawRect(rect)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self._finish(None)
        elif event.button() == Qt.MouseButton.LeftButton:
            self._start = self._end = event.position().toPoint()
            self.update()

    def mouseMoveEvent(self, event) -> None:
        if self._start is not None:
            self._end = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._start is not None:
            self._end = event.position().toPoint()
            rect = self.selection()
            self._finish(rect if rect.width() >= MIN_SIZE and rect.height() >= MIN_SIZE else None)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._finish(None)

    def closeEvent(self, event) -> None:
        if not self._finished:  # bị đóng từ bên ngoài (Alt+F4…) → coi như huỷ
            self._finished = True
            self.cancelled.emit()
        super().closeEvent(event)

    def _finish(self, rect: QRect | None) -> None:
        self._finished = True
        self.close()
        if rect is None:
            self.cancelled.emit()
        else:
            self.selected.emit(rect)
