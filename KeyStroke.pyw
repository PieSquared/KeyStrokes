import sys
import os
import time
import threading

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFontDatabase, QFont, QColor
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGraphicsDropShadowEffect
)
from pynput import keyboard, mouse

FONT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "PressStart.ttf")

# layout things
KEY = 58
GAP = 5

PANEL_W = KEY * 3 + GAP * 2
ROW2_H = KEY
ROW3_H = 56
ROW4_H = 28
MARGIN = 14                     

BG_IDLE = "rgba(128, 128, 128, 140)"
BG_PRESSED = "rgba(40, 40, 40, 200)"


class KeystrokesOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Keystrokes Overlay")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.pixel_font_family = self.load_pixel_font()

        self.keys = {"W": False, "A": False, "S": False, "D": False, "SPACE": False}
        self.key_blocks = {}

        self.left_clicks = []
        self.right_clicks = []
        self.drag_position = None

        self.initUI()
        self.start_listeners()

    #  styling functions

    def load_pixel_font(self):
        if os.path.exists(FONT_PATH):
            font_id = QFontDatabase.addApplicationFont(FONT_PATH)
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                return families[0]
        return "Consolas"

    def font_for(self, size):
        f = QFont(self.pixel_font_family, size)
        f.setBold(False)
        f.setStretch(140)   # widen the glyphs — VT323 is naturally condensed
        return f

    def drop_shadow(self):
        effect = QGraphicsDropShadowEffect()
        effect.setBlurRadius(0)   # hard edge, pixel-art style
        effect.setXOffset(3)
        effect.setYOffset(3)
        effect.setColor(QColor(0, 0, 0, 150))
        return effect

    def block_style(self, pressed=False):
        bg = BG_PRESSED if pressed else BG_IDLE
        return f"background-color: {bg}; color: {TEXT_IDLE}; border: none;"

    def make_block(self, w, h, text="", font_size=14, subtext=None, track=False):
        label = QLabel()
        label.setFixedSize(w, h)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet(self.block_style())
        label.setGraphicsEffect(self.drop_shadow())
        label.setFont(self.font_for(font_size))
        label.setText(f"{text}\n{subtext}" if subtext is not None else text)
        if track:
            self.key_blocks[text] = label
        return label

    def make_row(self, height):
        row = QWidget()
        row.setFixedSize(PANEL_W, height)
        layout = QHBoxLayout(row)
        layout.setSpacing(GAP)
        layout.setContentsMargins(0, 0, 0, 0)
        return row, layout

    #  layout 

    def initUI(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(GAP)
        main_layout.setContentsMargins(MARGIN, MARGIN, MARGIN, MARGIN)

        # Row 1: W, centered above S
        row1, row1_layout = self.make_row(ROW1_H)
        row1_layout.addStretch()
        row1_layout.addWidget(self.make_block(KEY, KEY, "W", font_size=20, track=True))
        row1_layout.addStretch()
        main_layout.addWidget(row1)

        # Row 2: A S D, equal squares
        row2, row2_layout = self.make_row(ROW2_H)
        for k in ["A", "S", "D"]:
            row2_layout.addWidget(self.make_block(KEY, KEY, k, font_size=18, track=True))
        main_layout.addWidget(row2)

        # Row 3: LMB / RMB
        row3, row3_layout = self.make_row(ROW3_H)
        half = (PANEL_W - GAP) // 2
        self.lmb_label = self.make_block(half, ROW3_H, "LMB", font_size=14, subtext="0 CPS")
        self.rmb_label = self.make_block(half, ROW3_H, "RMB", font_size=14, subtext="0 CPS")
        row3_layout.addWidget(self.lmb_label)
        row3_layout.addWidget(self.rmb_label)
        main_layout.addWidget(row3)

        # Row 4: spacebar, full width
        self.space_block = self.make_block(PANEL_W, ROW4_H, font_size=9, track=False)
        self.key_blocks["SPACE"] = self.space_block
        main_layout.addWidget(self.space_block)

        self.setFixedSize(
            PANEL_W + MARGIN * 2,
            ROW1_H + GAP + ROW2_H + GAP + ROW3_H + GAP + ROW4_H + MARGIN * 2
        )

        # Timer to repaint pressed/idle state
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(50)

        threading.Thread(target=self.cps_updater, daemon=True).start()

    #  state updates 

    def update_ui(self):
        for key, label in self.key_blocks.items():
            label.setStyleSheet(self.block_style(self.keys[key]))

    def start_listeners(self):
        threading.Thread(target=self.keyboard_listener, daemon=True).start()
        threading.Thread(target=self.mouse_listener, daemon=True).start()

    def keyboard_listener(self):
        from pynput import keyboard as pkb

        def on_press(key):
            try:
                k = key.char
                if k:
                    k = k.upper()
                    if k in self.keys:
                        self.keys[k] = True
            except AttributeError:
                if key == pkb.Key.space:
                    self.keys["SPACE"] = True

        def on_release(key):
            try:
                k = key.char
                if k:
                    k = k.upper()
                    if k in self.keys:
                        self.keys[k] = False
            except AttributeError:
                if key == pkb.Key.space:
                    self.keys["SPACE"] = False

        with pkb.Listener(on_press=on_press, on_release=on_release) as listener:
            listener.join()

    def mouse_listener(self):
        from pynput import mouse as pmouse

        def on_click(x, y, button, pressed):
            if pressed:
                if button == pmouse.Button.left:
                    self.left_clicks.append(time.time())
                elif button == pmouse.Button.right:
                    self.right_clicks.append(time.time())

        with pmouse.Listener(on_click=on_click) as listener:
            listener.join()

    def cps_updater(self):
        while True:
            now = time.time()
            self.left_clicks = [t for t in self.left_clicks if now - t <= 1]
            self.right_clicks = [t for t in self.right_clicks if now - t <= 1]

            self.lmb_label.setText(f"LMB\n{len(self.left_clicks)} CPS")
            self.rmb_label.setText(f"RMB\n{len(self.right_clicks)} CPS")
            time.sleep(0.1)

    # window dragging 

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self.drag_position:
            self.move(event.globalPos() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.drag_position = None
        event.accept()

    def run(self):
        self.show()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    overlay = KeystrokesOverlay()
    overlay.run()
    sys.exit(app.exec_())