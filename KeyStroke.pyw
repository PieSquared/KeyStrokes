import sys
import os
import json
import time
import zipfile
import threading

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFontDatabase, QFont, QColor
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGraphicsDropShadowEffect,
    QMenu, QAction, QActionGroup, QFileDialog, QMessageBox
)
from pynput import keyboard, mouse

import glfw
import OpenGL.GL as gl
import imgui
from imgui.integrations.glfw import GlfwRenderer

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
THEMES_DIR = os.path.join(SCRIPT_DIR, "themes")
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")

FALLBACK_THEME_NAME = "default"

#Fallback incase a custom theme doesnt have stuff
DEFAULT_THEME = {
    "name": "Fallback",
    "colors": {
        "bg_idle_top": "rgba(160, 160, 160, 130)",
        "bg_idle_bottom": "rgba(90, 90, 90, 150)",
        "bg_pressed_top": "rgba(50, 50, 50, 200)",
        "bg_pressed_bottom": "rgba(30, 30, 30, 200)",
        "border_idle": "rgba(255, 255, 255, 40)",
        "border_pressed": "rgba(255, 255, 255, 90)",
        "text": "white",
        "shadow": "rgba(0, 0, 0, 130)",
        "glow": "rgba(0, 0, 0, 160)",
    },
    "shape": {
        "key_size": 58,
        "gap": 5,
        "row3_height": 56,
        "row4_height": 28,
        "margin": 22,
        "border_radius": 0,
        "shadow_blur": 14,
        "glow_blur": 20,
    },
    "font": {
        "file": "font.ttf",
        "bold": False,
        "stretch": 100,
        "size_w": 20,
        "size_asd": 18,
        "size_lmb_rmb": 14,
        "size_space": 9,
    },
}


def deep_merge(defaults, overrides):
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


def list_themes():
    themes = []
    if not os.path.isdir(THEMES_DIR):
        return themes
    for entry in sorted(os.listdir(THEMES_DIR)):
        theme_dir = os.path.join(THEMES_DIR, entry)
        json_path = os.path.join(theme_dir, "theme.json")
        if os.path.isdir(theme_dir) and os.path.exists(json_path):
            display_name = entry
            try:
                with open(json_path, "r") as f:
                    display_name = json.load(f).get("name", entry)
            except (json.JSONDecodeError, OSError):
                pass
            themes.append((entry, display_name))
    themes.sort(key=lambda t: t[1].lower())
    return themes


def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_config(data):
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(data, f, indent=4)
        return True
    except OSError:
        return False


def get_active_theme():
    config = load_config()
    name = config.get("theme", FALLBACK_THEME_NAME)
    available = {n for n, _ in list_themes()}
    if name not in available:
        name = FALLBACK_THEME_NAME
    return name


def set_active_theme(name):
    config = load_config()
    config["theme"] = name
    return save_config(config)


ELEMENT_NAMES = ["W", "A", "S", "D", "LMB", "RMB", "SPACE"]


def get_scale():
    config = load_config()
    try:
        scale = float(config.get("scale", 1.0))
    except (TypeError, ValueError):
        scale = 1.0
    return min(max(scale, 0.5), 2.0)


def set_scale(scale):
    config = load_config()
    config["scale"] = scale
    return save_config(config)


def get_hidden_elements():
    config = load_config()
    hidden = config.get("hidden", [])
    if not isinstance(hidden, list):
        return set()
    return {h for h in hidden if h in ELEMENT_NAMES}


def set_hidden_elements(hidden_set):
    config = load_config()
    config["hidden"] = sorted(hidden_set)
    return save_config(config)


def _slugify(text):
    slug = "".join(c if c.isalnum() or c in "-_" else "_" for c in text.lower())
    return slug or "imported_theme"


def import_ks(ks_path):

    if not os.path.exists(ks_path):
        return None, "File not found."
    if not zipfile.is_zipfile(ks_path):
        return None, "Not a valid .ks file (expected a zip-based theme package)."

    base = os.path.splitext(os.path.basename(ks_path))[0]
    slug = _slugify(base)

    dest_dir = os.path.join(THEMES_DIR, slug)
    n = 2
    while os.path.exists(dest_dir):
        dest_dir = os.path.join(THEMES_DIR, f"{slug}_{n}")
        n += 1

    try:
        with zipfile.ZipFile(ks_path, "r") as zf:
            names = zf.namelist()
            if "theme.json" not in names:
                return None, "The .ks file doesn't contain a theme.json."
            os.makedirs(dest_dir, exist_ok=True)
            zf.extractall(dest_dir)
    except (zipfile.BadZipFile, OSError) as e:
        return None, f"Failed to extract: {e}"

    return os.path.basename(dest_dir), None


def export_ks(theme_folder, dest_path):

    src_dir = os.path.join(THEMES_DIR, theme_folder)
    if not os.path.isdir(src_dir):
        return False, "Theme folder not found."
    try:
        with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _dirs, files in os.walk(src_dir):
                for fname in files:
                    full = os.path.join(root, fname)
                    arcname = os.path.relpath(full, src_dir)
                    zf.write(full, arcname)
        return True, None
    except OSError as e:
        return False, str(e)


#Actual overlay

class KeystrokesOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Keystrokes Overlay")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)  # interactive by default (unlocked)
        self.setContextMenuPolicy(Qt.DefaultContextMenu)

        self.keys = {"W": False, "A": False, "S": False, "D": False, "SPACE": False}
        self.key_blocks = {}
        self.left_clicks = []
        self.right_clicks = []
        self.drag_position = None
        self.timer = None

        self.panel = None
        self._last_scale_rebuild = 0.0
        self.locked = False
        self._alt_pressed = False
        self._f3_held = False
        self._lock_toggle_pending = False

        self.apply_theme(get_active_theme(), first_run=True)
        self.start_listeners()

    #  theme switching 

    def apply_theme(self, name, first_run=False, persist=True, scale_override=None):
        self.theme_name = name
        self.theme = load_theme(name)
        self.pixel_font_family = self.load_theme_font()

        self.scale = scale_override if scale_override is not None else get_scale()
        self.hidden = get_hidden_elements()

        shape = self.theme["shape"]
        s = self.scale
        self.KEY = round(shape["key_size"] * s)
        self.GAP = round(shape["gap"] * s)
        self.PANEL_W = self.KEY * 3 + self.GAP * 2
        self.ROW1_H = self.KEY
        self.ROW2_H = self.KEY
        self.ROW3_H = round(shape["row3_height"] * s)
        self.ROW4_H = round(shape["row4_height"] * s)
        self.MARGIN = round(shape["margin"] * s)
        self.BORDER_RADIUS = round(shape["border_radius"] * s)
        self.SHADOW_BLUR = round(shape["shadow_blur"] * s)
        self.GLOW_BLUR = round(shape["glow_blur"] * s)

        self.key_blocks = {}

        old_center = self.frameGeometry().center() if not first_run else None

        if not first_run:
            if self.timer:
                self.timer.stop()
            self.clear_ui()

        self.build_ui()

        if old_center is not None:
            new_geo = self.frameGeometry()
            new_geo.moveCenter(old_center)
            self.move(new_geo.topLeft())

        if persist:
            set_active_theme(name)

    def set_scale(self, scale, persist=True):
        scale = min(max(scale, 0.5), 2.0)
        now = time.time()
        if not persist:

            if now - self._last_scale_rebuild < 0.05:
                return
            self._last_scale_rebuild = now
            self.apply_theme(self.theme_name, persist=False, scale_override=scale)
        else:
            # Slider released — persist the exact final value once.
            set_scale(scale)
            self.apply_theme(self.theme_name, persist=True, scale_override=scale)

    def set_hidden(self, hidden_set):
        set_hidden_elements(hidden_set)
        self.apply_theme(self.theme_name)

    def clear_ui(self):
        old_layout = self.layout()
        if old_layout is not None:
            while old_layout.count():
                item = old_layout.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.deleteLater()
           
            QWidget().setLayout(old_layout)

    # theme menu 

    def contextMenuEvent(self, event):
        menu = QMenu(self)

        theme_menu = menu.addMenu("Theme")
        group = QActionGroup(theme_menu)
        group.setExclusive(True)
        for folder_name, display_name in list_themes():
            action = QAction(display_name, theme_menu, checkable=True)
            action.setChecked(folder_name == self.theme_name)
            action.triggered.connect(lambda checked, n=folder_name: self.apply_theme(n))
            group.addAction(action)
            theme_menu.addAction(action)

        menu.addSeparator()
        import_action = QAction("Import .ks Theme...", menu)
        import_action.triggered.connect(self.import_ks_theme)
        menu.addAction(import_action)

        menu.addSeparator()
        exit_action = QAction("Exit", menu)
        exit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(exit_action)

        menu.exec_(event.globalPos())

    def import_ks_theme(self):
        path = pick_ks_file(self)
        if not path:
            return
        folder_name, error = import_ks(path)
        if error:
            QMessageBox.warning(self, "Import failed", error)
        else:
            QMessageBox.information(self, "Theme imported", f"Imported as '{folder_name}'.")
            self.apply_theme(folder_name)

    #  styling helper

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

    def make_block(self, w, h, text="", font_size=14, subtext=None, track=False, visible=True):
        label = QLabel()
        label.setFixedSize(w, h)
        label.setAlignment(Qt.AlignCenter)
        if visible:
            label.setStyleSheet(self.block_style())
            label.setGraphicsEffect(self.drop_shadow())
            label.setFont(self.font_for(font_size))
            label.setText(f"{text}\n{subtext}" if subtext is not None else text)
            if track:
                self.key_blocks[text] = label
        else:
            label.setStyleSheet("background: transparent; border: none;")
        return label

    def make_row(self, height):
        row = QWidget()
        row.setFixedSize(self.PANEL_W, height)
        layout = QHBoxLayout(row)
        layout.setSpacing(self.GAP)
        layout.setContentsMargins(0, 0, 0, 0)
        return row, layout

    #  layout 

    def build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(self.GAP)
        main_layout.setContentsMargins(self.MARGIN, self.MARGIN, self.MARGIN, self.MARGIN)

        font_cfg = self.theme["font"]

        
        row1, row1_layout = self.make_row(self.ROW1_H)
        row1_layout.addStretch()
        row1_layout.addWidget(self.make_block(
            self.KEY, self.KEY, "W", font_size=round(font_cfg["size_w"] * self.scale), track=True, visible="W" not in self.hidden
        ))
        row1_layout.addStretch()
        main_layout.addWidget(row1)

        
        row2, row2_layout = self.make_row(self.ROW2_H)
        for k in ["A", "S", "D"]:
            row2_layout.addWidget(self.make_block(
                self.KEY, self.KEY, k, font_size=round(font_cfg["size_asd"] * self.scale), track=True, visible=k not in self.hidden
            ))
        main_layout.addWidget(row2)

        
        row3, row3_layout = self.make_row(self.ROW3_H)
        half = (self.PANEL_W - self.GAP) // 2
        self.lmb_label = self.make_block(
            half, self.ROW3_H, "LMB", font_size=round(font_cfg["size_lmb_rmb"] * self.scale), subtext="0 CPS",
            visible="LMB" not in self.hidden
        )
        self.rmb_label = self.make_block(
            half, self.ROW3_H, "RMB", font_size=round(font_cfg["size_lmb_rmb"] * self.scale), subtext="0 CPS",
            visible="RMB" not in self.hidden
        )
        row3_layout.addWidget(self.lmb_label)
        row3_layout.addWidget(self.rmb_label)
        main_layout.addWidget(row3)

        
        self.space_block = self.make_block(
            self.PANEL_W, self.ROW4_H, font_size=round(font_cfg["size_space"] * self.scale), visible="SPACE" not in self.hidden
        )
        if "SPACE" not in self.hidden:
            self.key_blocks["SPACE"] = self.space_block
        main_layout.addWidget(self.space_block)

        self.setFixedSize(
            self.PANEL_W + self.MARGIN * 2,
            self.ROW1_H + self.GAP + self.ROW2_H + self.GAP + self.ROW3_H + self.GAP + self.ROW4_H + self.MARGIN * 2
        )

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(50)

    #  state updates 

    def update_ui(self):
        if self._lock_toggle_pending:
            self._lock_toggle_pending = False
            self.apply_lock_toggle()

        for key, label in self.key_blocks.items():
            pressed = self.keys[key]
            label.setStyleSheet(self.block_style(pressed))
            label.setGraphicsEffect(self.drop_shadow(glow=pressed))

    def apply_lock_toggle(self):
        self.locked = not self.locked
        print(f"[hotkey debug] toggle applied, locked={self.locked}, panel={self.panel}")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, self.locked)
        if self.panel is not None:
            self.panel.set_visible(not self.locked)

    def start_listeners(self):
        threading.Thread(target=self.keyboard_listener, daemon=True).start()
        threading.Thread(target=self.mouse_listener, daemon=True).start()
        threading.Thread(target=self.cps_updater, daemon=True).start()

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
                elif key in (pkb.Key.alt_l, pkb.Key.alt_r, pkb.Key.alt):
                    self._alt_pressed = True
                    print("[hotkey debug] alt pressed")
                elif key == pkb.Key.f3:
                    print(f"[hotkey debug] F3 seen, alt_pressed={self._alt_pressed}, already_held={self._f3_held}")
                    if self._alt_pressed and not self._f3_held:
                        self._f3_held = True
                        self._lock_toggle_pending = True
                        print("[hotkey debug] toggle flagged")

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
                elif key in (pkb.Key.alt_l, pkb.Key.alt_r, pkb.Key.alt):
                    self._alt_pressed = False
                elif key == pkb.Key.f3:
                    self._f3_held = False

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

            try:
                if "LMB" not in self.hidden:
                    self.lmb_label.setText(f"LMB\n{len(self.left_clicks)} CPS")
                if "RMB" not in self.hidden:
                    self.rmb_label.setText(f"RMB\n{len(self.right_clicks)} CPS")
            except RuntimeError:
                pass  # labels mid-rebuild during a theme switch, skip this tick
            time.sleep(0.1)

    #  window dragging 

    def mousePressEvent(self, event):
        if self.locked:
            return
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.locked:
            return
        if event.buttons() == Qt.LeftButton and self.drag_position:
            self.move(event.globalPos() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.drag_position = None
        event.accept()

    def closeEvent(self, event):
        QApplication.instance().quit()
        event.accept()

    def run(self):
        self.show()


def pick_ks_file(parent=None):
    path, _ = QFileDialog.getOpenFileName(
        parent, "Import .ks Theme", "", "Keystrokes theme (*.ks);;All files (*)"
    )
    return path

#ImGui panel for settings

class ImGuiThemePanel:
    def __init__(self, on_theme_applied=None, on_scale_changed=None, on_hidden_changed=None):
        self.on_theme_applied = on_theme_applied
        self.on_scale_changed = on_scale_changed
        self.on_hidden_changed = on_hidden_changed
        self.status = ""
        self.themes = []
        self.selected_index = 0
        self.scale = get_scale()
        self.hidden = get_hidden_elements()
        self.closed = False
        self.dragging = False
        self.drag_start_cursor = (0, 0)
        self.drag_start_window_pos = (0, 0)

        if not glfw.init():
            raise RuntimeError("Could not initialize GLFW")

        glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
        glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
        glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
        glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, gl.GL_TRUE)
        glfw.window_hint(glfw.DECORATED, False)
        glfw.window_hint(glfw.FLOATING, True)
        glfw.window_hint(glfw.RESIZABLE, False)
        glfw.window_hint(glfw.TRANSPARENT_FRAMEBUFFER, True)

        self.window = glfw.create_window(320, 420, "Keystrokes Theme Manager", None, None)
        if not self.window:
            glfw.terminate()
            raise RuntimeError("Could not create GLFW window")

        glfw.make_context_current(self.window)
        glfw.swap_interval(1)

        imgui.create_context()
        self.impl = GlfwRenderer(self.window)

        style = imgui.get_style()
        style.window_rounding = 0
        style.window_border_size = 1
        style.colors[imgui.COLOR_WINDOW_BACKGROUND] = (0.08, 0.08, 0.10, 0.96)

        self.refresh_themes()
        self.visible = True

    def set_visible(self, visible):
        self.visible = visible
        if visible:
            glfw.show_window(self.window)
        else:
            glfw.hide_window(self.window)

    def _cursor_screen_pos(self):

        wx, wy = glfw.get_window_pos(self.window)
        mx, my = imgui.get_io().mouse_pos
        return (wx + mx, wy + my)

    def refresh_themes(self):
        self.themes = list_themes()
        active = get_active_theme()
        folder_names = [name for name, _ in self.themes]
        self.selected_index = folder_names.index(active) if active in folder_names else 0

    def tick(self):
        if self.closed or glfw.window_should_close(self.window):
            self.shutdown()
            return False

        glfw.poll_events()

        if not self.visible:
            return True

        self.impl.process_inputs()
        imgui.new_frame()

        panel_w, panel_h = glfw.get_window_size(self.window)
        imgui.set_next_window_position(0, 0)
        imgui.set_next_window_size(panel_w, panel_h)
        imgui.begin(
            "##panel",
            flags=imgui.WINDOW_NO_TITLE_BAR | imgui.WINDOW_NO_RESIZE
            | imgui.WINDOW_NO_MOVE | imgui.WINDOW_NO_COLLAPSE
        )

        button_w = 20
        spacing = imgui.get_style().item_spacing[0]
        avail_w = imgui.get_content_region_available_width()
        drag_w = max(avail_w - button_w - spacing, 0)
        imgui.invisible_button("##drag_handle", drag_w, 20)
        if imgui.is_item_activated():
            self.dragging = True
            self.drag_start_cursor = self._cursor_screen_pos()
            self.drag_start_window_pos = glfw.get_window_pos(self.window)
        if self.dragging and imgui.is_mouse_down(0):
            cur = self._cursor_screen_pos()
            dx = cur[0] - self.drag_start_cursor[0]
            dy = cur[1] - self.drag_start_cursor[1]
            new_x = self.drag_start_window_pos[0] + dx
            new_y = self.drag_start_window_pos[1] + dy
            glfw.set_window_pos(self.window, int(new_x), int(new_y))
        else:
            self.dragging = False
        imgui.same_line()
        if imgui.button("x", width=button_w, height=20):
            glfw.set_window_should_close(self.window, True)

        imgui.separator()

        imgui.text("Theme:")
        display_names = [display for _, display in self.themes]
        if display_names:
            changed, new_index = imgui.combo("##theme_combo", self.selected_index, display_names)
            if changed:
                self.selected_index = new_index
        else:
            imgui.text_colored("No themes found in the themes/ folder.", 1.0, 0.4, 0.4)

        imgui.spacing()
        if imgui.button("Apply Theme") and display_names:
            folder_name, display_name = self.themes[self.selected_index]
            set_active_theme(folder_name)
            self.status = f"Applied '{display_name}'."
            if self.on_theme_applied:
                self.on_theme_applied(folder_name)

        imgui.spacing()
        imgui.separator()
        imgui.spacing()

        if imgui.button("Import .ks Theme..."):
            path = pick_ks_file()
            if path:
                folder_name, error = import_ks(path)
                if error:
                    self.status = f"Import failed: {error}"
                else:
                    self.status = f"Imported as '{folder_name}'."
                    self.refresh_themes()
                    if self.on_theme_applied:
                        set_active_theme(folder_name)
                        self.on_theme_applied(folder_name)

        imgui.spacing()
        imgui.separator()
        imgui.spacing()

        imgui.text("Overlay Size:")
        changed, new_scale = imgui.slider_float("##scale", self.scale, 0.5, 2.0, "%.2fx")
        if changed:
            self.scale = new_scale
            if self.on_scale_changed:
                self.on_scale_changed(self.scale, False)  # live, throttled, not persisted
        if imgui.is_item_deactivated_after_edit():
            # Slider released — apply + persist the exact final value once,
            # bypassing the throttle so it can't be dropped.
            if self.on_scale_changed:
                self.on_scale_changed(self.scale, True)

        imgui.spacing()
        imgui.text("Show elements:")
        columns = 3  # how many checkboxes per row
        for i, element in enumerate(ELEMENT_NAMES):
            checked = element not in self.hidden
            changed, checked = imgui.checkbox(element, checked)
            if changed:
                if checked:
                    self.hidden.discard(element)
                else:
                    self.hidden.add(element)
                set_hidden_elements(self.hidden)
                if self.on_hidden_changed:
                    self.on_hidden_changed(self.hidden)

            is_last = (i == len(ELEMENT_NAMES) - 1)
            is_row_end = ((i + 1) % columns == 0)
            if not is_last and not is_row_end:
                imgui.same_line()

        imgui.spacing()
        imgui.set_window_font_scale(0.8)
        imgui.text_colored("Alt+F3 to hide", 0.6, 0.6, 0.6)
        imgui.set_window_font_scale(1.0)

        if self.status:
            imgui.spacing()
            imgui.separator()
            imgui.text_wrapped(self.status)

        imgui.end()

        gl.glClearColor(0.0, 0.0, 0.0, 0.0)
        gl.glClear(gl.GL_COLOR_BUFFER_BIT)
        imgui.render()
        self.impl.render(imgui.get_draw_data())
        glfw.swap_buffers(self.window)
        return True

    def shutdown(self):
        if self.closed:
            return
        self.closed = True
        self.impl.shutdown()
        glfw.terminate()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    overlay = KeystrokesOverlay()
    overlay.run()

    panel = ImGuiThemePanel(
        on_theme_applied=overlay.apply_theme,
        on_scale_changed=overlay.set_scale,
        on_hidden_changed=overlay.set_hidden,
    )
    overlay.panel = panel

    imgui_timer = QTimer()

    def imgui_tick():
        if not panel.tick():
            imgui_timer.stop()
            app.quit()

    imgui_timer.timeout.connect(imgui_tick)
    imgui_timer.start(16)  

    def on_about_to_quit():
        panel.shutdown()

    app.aboutToQuit.connect(on_about_to_quit)

    sys.exit(app.exec_())