import sys
import os
import json
import time
import threading

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFontDatabase, QFont, QColor
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGraphicsDropShadowEffect
)
from pynput import keyboard, mouse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
THEMES_DIR = os.path.join(SCRIPT_DIR, "themes")

#theme folder name
THEME_NAME = "default"

# Fallback values used for anything missing from a theme.json

DEFAULT_THEME = {
    "name": "Fallback",
    "colors": {
        "bg_idle_top": "rgba(160, 160, 160, 130)",
        "bg_idle_bottom": "rgba(90, 90, 90, 150)",
        "bg_pressed_top": "rgba(120, 160, 255, 200)",
        "bg_pressed_bottom": "rgba(70, 105, 235, 200)",
        "border_idle": "rgba(255, 255, 255, 40)",
        "border_pressed": "rgba(255, 255, 255, 110)",
        "text": "white",
        "shadow": "rgba(0, 0, 0, 130)",
        "glow": "rgba(110, 150, 255, 200)",
    },
    "shape": {
        "key_size": 58,
        "gap": 5,
        "row3_height": 56,
        "row4_height": 28,
        "margin": 22,
        "border_radius": 12,
        "shadow_blur": 14,
        "glow_blur": 20,
    },
    "font": {
        "file": "font.ttf",
        "bold": False,
        "stretch": 140,
        "size_w": 20,
        "size_asd": 18,
        "size_lmb_rmb": 14,
        "size_space": 9,
    },
}


def deep_merge(defaults, overrides):
    """Merge a theme.json's contents over DEFAULT_THEME, section by section,
    so a theme only needs to specify the values it wants to change."""
    merged = {}
    for section, value in defaults.items():
        if isinstance(value, dict):
            merged[section] = {**value, **(overrides.get(section) or {})}
        else:
            merged[section] = overrides.get(section, value)
    return merged


def load_theme(name):
    theme_dir = os.path.join(THEMES_DIR, name)
    json_path = os.path.join(theme_dir, "theme.json")

    data = {}
    if os.path.exists(json_path):
        try:
            with open(json_path, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            data = {}

    theme = deep_merge(DEFAULT_THEME, data)
    theme["_dir"] = theme_dir
    return theme


def gradient(top, bottom):
    return f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {top}, stop:1 {bottom})"


class KeystrokesOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Keystrokes Overlay")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.theme = load_theme(THEME_NAME)
        self.pixel_font_family = self.load_theme_font()

        #  geometry thats pulled from the theme 
        shape = self.theme["shape"]
        self.KEY = shape["key_size"]
        self.GAP = shape["gap"]
        self.PANEL_W = self.KEY * 3 + self.GAP * 2
        self.ROW1_H = self.KEY
        self.ROW2_H = self.KEY
        self.ROW3_H = shape["row3_height"]
        self.ROW4_H = shape["row4_height"]
        self.MARGIN = shape["margin"]
        self.BORDER_RADIUS = shape["border_radius"]
        self.SHADOW_BLUR = shape["shadow_blur"]
        self.GLOW_BLUR = shape["glow_blur"]

        self.keys = {"W": False, "A": False, "S": False, "D": False, "SPACE": False}
        self.key_blocks = {}

        self.left_clicks = []
        self.right_clicks = []
        self.drag_position = None

        self.initUI()
        self.start_listeners()

    #  styling functions

    def load_theme_font(self):
        font_path = os.path.join(self.theme["_dir"], self.theme["font"]["file"])
        if os.path.exists(font_path):
            font_id = QFontDatabase.addApplicationFont(font_path)
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                return families[0]
        return "Consolas"

    def font_for(self, size):
        font_cfg = self.theme["font"]
        f = QFont(self.pixel_font_family, size)
        f.setBold(font_cfg["bold"])
        f.setStretch(font_cfg["stretch"])
        return f

    def drop_shadow(self, glow=False):
        colors = self.theme["colors"]
        effect = QGraphicsDropShadowEffect()
        if glow:
            effect.setBlurRadius(self.GLOW_BLUR)
            effect.setXOffset(0)
            effect.setYOffset(0)
            effect.setColor(QColor(colors["glow"]))
        else:
            effect.setBlurRadius(self.SHADOW_BLUR)
            effect.setXOffset(0)
            effect.setYOffset(3)
            effect.setColor(QColor(colors["shadow"]))
        return effect

    def block_style(self, pressed=False):
        c = self.theme["colors"]
        bg = gradient(c["bg_pressed_top"], c["bg_pressed_bottom"]) if pressed \
            else gradient(c["bg_idle_top"], c["bg_idle_bottom"])
        border = c["border_pressed"] if pressed else c["border_idle"]
        return (
            f"background: {bg}; color: {c['text']}; "
            f"border: 1px solid {border}; border-radius: {self.BORDER_RADIUS}px;"
        )

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
        row.setFixedSize(self.PANEL_W, height)
        layout = QHBoxLayout(row)
        layout.setSpacing(self.GAP)
        layout.setContentsMargins(0, 0, 0, 0)
        return row, layout

    #  layout

    def initUI(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(self.GAP)
        main_layout.setContentsMargins(self.MARGIN, self.MARGIN, self.MARGIN, self.MARGIN)

        font_cfg = self.theme["font"]

        
        row1, row1_layout = self.make_row(self.ROW1_H)
        row1_layout.addStretch()
        row1_layout.addWidget(self.make_block(self.KEY, self.KEY, "W", font_size=font_cfg["size_w"], track=True))
        row1_layout.addStretch()
        main_layout.addWidget(row1)

        
        row2, row2_layout = self.make_row(self.ROW2_H)
        for k in ["A", "S", "D"]:
            row2_layout.addWidget(self.make_block(self.KEY, self.KEY, k, font_size=font_cfg["size_asd"], track=True))
        main_layout.addWidget(row2)

        
        row3, row3_layout = self.make_row(self.ROW3_H)
        half = (self.PANEL_W - self.GAP) // 2
        self.lmb_label = self.make_block(half, self.ROW3_H, "LMB", font_size=font_cfg["size_lmb_rmb"], subtext="0 CPS")
        self.rmb_label = self.make_block(half, self.ROW3_H, "RMB", font_size=font_cfg["size_lmb_rmb"], subtext="0 CPS")
        row3_layout.addWidget(self.lmb_label)
        row3_layout.addWidget(self.rmb_label)
        main_layout.addWidget(row3)

        
        self.space_block = self.make_block(self.PANEL_W, self.ROW4_H, font_size=font_cfg["size_space"], track=False)
        self.key_blocks["SPACE"] = self.space_block
        main_layout.addWidget(self.space_block)

        self.setFixedSize(
            self.PANEL_W + self.MARGIN * 2,
            self.ROW1_H + self.GAP + self.ROW2_H + self.GAP + self.ROW3_H + self.GAP + self.ROW4_H + self.MARGIN * 2
        )

        
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(50)

        threading.Thread(target=self.cps_updater, daemon=True).start()

    #  state updates

    def update_ui(self):
        for key, label in self.key_blocks.items():
            pressed = self.keys[key]
            label.setStyleSheet(self.block_style(pressed))
            label.setGraphicsEffect(self.drop_shadow(glow=pressed))

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