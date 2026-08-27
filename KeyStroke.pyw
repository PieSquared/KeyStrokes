import sys
import os
import json
import time
import zipfile
import threading
import colorsys
import tempfile
import shutil
import urllib.request
import urllib.error

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFontDatabase, QFont, QColor
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGraphicsDropShadowEffect,
    QMenu, QAction, QActionGroup, QFileDialog, QMessageBox
)
from pynput import keyboard, mouse

def _resolve_dirs():
    onefile_parent = None
    onefile_var = None
    for var in ("NUITKA_ONEFILE_PARENT", "NUITKA_ONEFILE_BINARY"):
        val = os.environ.get(var)
        if val:
            onefile_parent = os.path.dirname(os.path.abspath(val))
            onefile_var = var
            break

    if onefile_parent:
        bundle_dir = os.path.dirname(os.path.abspath(sys.executable))
        launcher_dir = onefile_parent
        return bundle_dir, launcher_dir, f"Nuitka onefile ({onefile_var})"

    if hasattr(sys, "_MEIPASS"):
        bundle_dir = sys._MEIPASS
        launcher_dir = os.path.dirname(os.path.abspath(sys.executable))
        return bundle_dir, launcher_dir, "PyInstaller onefile (sys._MEIPASS)"

    if getattr(sys, "frozen", False) or "__compiled__" in globals():
        base = os.path.dirname(os.path.abspath(sys.executable))
        return base, base, "standalone build (sys.executable)"

    base = os.path.dirname(os.path.abspath(__file__))
    return base, base, "not compiled (__file__)"


_BUNDLE_DIR, _LAUNCHER_DIR, _DIR_SOURCE = _resolve_dirs()

if "PYGLFW_LIBRARY" not in os.environ:
    import glob
    _glfw_pkg_dir = os.path.join(_BUNDLE_DIR, "glfw")
    _candidates = []
    for _pattern in ("libglfw*.so*", "*.dylib", "glfw3.dll"):
        _candidates.extend(glob.glob(os.path.join(_glfw_pkg_dir, _pattern)))
    if _candidates:
        os.environ["PYGLFW_LIBRARY"] = _candidates[0]

import glfw
import OpenGL.GL as gl
import imgui
from imgui.integrations.glfw import GlfwRenderer


def get_base_dir():
    _log_base_dir_debug(_LAUNCHER_DIR, _DIR_SOURCE)
    return _LAUNCHER_DIR


def _log_base_dir_debug(resolved_base, source):
    try:
        import tempfile as _tempfile
        log_path = os.path.join(_tempfile.gettempdir(), "keystrokes_overlay_basedir_debug.log")
        nuitka_vars = {k: v for k, v in os.environ.items() if k.startswith("NUITKA_")}
        with open(log_path, "w") as f:
            f.write(f"resolved SCRIPT_DIR (launcher_dir) = {resolved_base}\n")
            f.write(f"resolved bundle_dir = {_BUNDLE_DIR}\n")
            f.write(f"source used = {source}\n")
            f.write(f"sys.executable = {sys.executable!r}\n")
            f.write(f"sys.argv = {sys.argv!r}\n")
            f.write(f"PYGLFW_LIBRARY = {os.environ.get('PYGLFW_LIBRARY')!r}\n")
            f.write(f"NUITKA_* env vars = {nuitka_vars!r}\n")
    except OSError:
        pass


SCRIPT_DIR = get_base_dir()
THEMES_DIR = os.path.join(SCRIPT_DIR, "themes")
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")

FALLBACK_THEME_NAME = "default"
FALLBACK_FONT_FAMILY = "Consolas"

GITHUB_OWNER = "PieSquared"
GITHUB_REPO = "KeyStrokes"
GITHUB_BRANCH = "main"
REQUIRED_ASSETS = ["themes", "config.json"]


def _github_zip_url():
    return f"https://codeload.github.com/{GITHUB_OWNER}/{GITHUB_REPO}/zip/refs/heads/{GITHUB_BRANCH}"


def _default_theme_present():
    theme_json = os.path.join(THEMES_DIR, FALLBACK_THEME_NAME, "theme.json")
    theme_font = os.path.join(THEMES_DIR, FALLBACK_THEME_NAME, "font.ttf")
    return os.path.exists(theme_json) and os.path.exists(theme_font)


def _asset_missing(name):
    if name == "themes":
        return not _default_theme_present()
    return not os.path.exists(os.path.join(SCRIPT_DIR, name))


def _any_asset_missing():
    return any(_asset_missing(name) for name in REQUIRED_ASSETS)


def _merge_copy(src, dst):
    if os.path.isdir(src):
        os.makedirs(dst, exist_ok=True)
        for entry in os.listdir(src):
            _merge_copy(os.path.join(src, entry), os.path.join(dst, entry))
    elif os.path.isfile(src) and not os.path.exists(dst):
        shutil.copy2(src, dst)


def ensure_assets_downloaded():
    if not _any_asset_missing():
        return True, None

    print("[setup] Required files missing — downloading from GitHub...")
    tmp_dir = tempfile.mkdtemp(prefix="ks_assets_")
    zip_path = os.path.join(tmp_dir, "repo.zip")

    try:
        urllib.request.urlretrieve(_github_zip_url(), zip_path)

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp_dir)

        extracted_root = None
        for entry in os.listdir(tmp_dir):
            full = os.path.join(tmp_dir, entry)
            if os.path.isdir(full) and entry.lower().startswith(GITHUB_REPO.lower()):
                extracted_root = full
                break
        if extracted_root is None:
            return False, "Downloaded archive had an unexpected layout."

        for name in REQUIRED_ASSETS:
            if not _asset_missing(name):
                continue
            src = os.path.join(extracted_root, name)
            if not os.path.exists(src):
                continue  
            _merge_copy(src, os.path.join(SCRIPT_DIR, name))

        print("[setup] Assets downloaded successfully.")
        return True, None

    except (urllib.error.URLError, urllib.error.HTTPError, zipfile.BadZipFile, OSError) as e:
        return False, str(e)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

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


VALID_MODIFIERS = ("alt", "ctrl", "shift")
DEFAULT_HOTKEY_MODIFIERS = ["alt"]
DEFAULT_HOTKEY_KEY = "F3"


def get_hotkey():
    config = load_config()
    hk = config.get("hotkey", {})
    modifiers = hk.get("modifiers", DEFAULT_HOTKEY_MODIFIERS)
    key = hk.get("key", DEFAULT_HOTKEY_KEY)
    if not isinstance(modifiers, list):
        modifiers = list(DEFAULT_HOTKEY_MODIFIERS)
    modifiers = [m for m in modifiers if m in VALID_MODIFIERS]
    if not isinstance(key, str) or not key:
        key = DEFAULT_HOTKEY_KEY
    return frozenset(modifiers), key.upper()


def set_hotkey(modifiers, key):
    config = load_config()
    config["hotkey"] = {"modifiers": sorted(modifiers), "key": key}
    return save_config(config)


def format_hotkey(modifiers, key):
    parts = [m.capitalize() for m in sorted(modifiers)]
    parts.append(key)
    return "+".join(parts)


#  window positions 

def get_overlay_position():
    config = load_config()
    pos = config.get("overlay_pos")
    if isinstance(pos, dict) and "x" in pos and "y" in pos:
        try:
            return int(pos["x"]), int(pos["y"])
        except (TypeError, ValueError):
            return None
    return None


def set_overlay_position(x, y):
    config = load_config()
    config["overlay_pos"] = {"x": int(x), "y": int(y)}
    return save_config(config)


def get_panel_position():
    config = load_config()
    pos = config.get("panel_pos")
    if isinstance(pos, dict) and "x" in pos and "y" in pos:
        try:
            return int(pos["x"]), int(pos["y"])
        except (TypeError, ValueError):
            return None
    return None


def set_panel_position(x, y):
    config = load_config()
    config["panel_pos"] = {"x": int(x), "y": int(y)}
    return save_config(config)


#  RGB rainbow mode 

def get_rgb_mode():
    return bool(load_config().get("rgb_mode", False))


def set_rgb_mode(enabled):
    config = load_config()
    config["rgb_mode"] = enabled
    return save_config(config)


def rgb_hue(offset=0.0, speed=0.15):
    return (time.time() * speed + offset) % 1.0


def hsv_to_rgba01(hue, sat=0.85, val=1.0, alpha=1.0):
    r, g, b = colorsys.hsv_to_rgb(hue, sat, val)
    return (r, g, b, alpha)


def rgba01_to_css(rgba01):
    r, g, b, a = rgba01
    return f"rgba({round(r * 255)}, {round(g * 255)}, {round(b * 255)}, {round(a * 255)})"


def rgba01_to_qcolor(rgba01):
    r, g, b, a = rgba01
    return QColor(round(r * 255), round(g * 255), round(b * 255), round(a * 255))


#active theme color override 


def get_active_colors_override():
    config = load_config()
    override = config.get("active_colors")
    return override if isinstance(override, dict) else None


def set_active_colors_override(colors):
    config = load_config()
    config["active_colors"] = colors
    return save_config(config)


def clear_active_colors_override():
    config = load_config()
    if "active_colors" in config:
        del config["active_colors"]
        return save_config(config)
    return True


def get_active_effects_override():
    config = load_config()
    override = config.get("active_effects")
    return override if isinstance(override, dict) else None


def set_active_effects_override(effects):
    config = load_config()
    config["active_effects"] = effects
    return save_config(config)


def clear_active_effects_override():
    config = load_config()
    if "active_effects" in config:
        del config["active_effects"]
        return save_config(config)
    return True


def get_active_font_override():
    config = load_config()
    override = config.get("active_font")
    if isinstance(override, dict) and isinstance(override.get("path"), str):
        return override["path"]
    return None


def set_active_font_override(path):
    config = load_config()
    config["active_font"] = {"path": path}
    return save_config(config)


def clear_active_font_override():
    config = load_config()
    if "active_font" in config:
        del config["active_font"]
        return save_config(config)
    return True


_fallback_font_family_cache = None


def load_fallback_font_family():

    global _fallback_font_family_cache
    if _fallback_font_family_cache is not None:
        return _fallback_font_family_cache
    default_font_path = os.path.join(THEMES_DIR, FALLBACK_THEME_NAME, "font.ttf")
    family = None
    if os.path.exists(default_font_path):
        font_id = QFontDatabase.addApplicationFont(default_font_path)
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            family = families[0]
    _fallback_font_family_cache = family or FALLBACK_FONT_FAMILY
    return _fallback_font_family_cache


def _slugify(text):
    slug = "".join(c if c.isalnum() or c in "-_" else "_" for c in text.lower())
    return slug or "imported_theme"

 #make sure its actually a file
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


def export_active_ks(colors, shape, font, source_dir, dest_path, display_name):
    tmp_dir = tempfile.mkdtemp(prefix="ks_export_")
    try:
        if os.path.isdir(source_dir):
            for fname in os.listdir(source_dir):
                src = os.path.join(source_dir, fname)
                if os.path.isfile(src):
                    shutil.copy2(src, os.path.join(tmp_dir, fname))

        out = {"name": display_name, "colors": colors, "shape": shape, "font": font}
        with open(os.path.join(tmp_dir, "theme.json"), "w") as f:
            json.dump(out, f, indent=4)

        with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _dirs, files in os.walk(tmp_dir):
                for fname in files:
                    full = os.path.join(root, fname)
                    arcname = os.path.relpath(full, tmp_dir)
                    zf.write(full, arcname)
        return True, None
    except OSError as e:
        return False, str(e)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def parse_color(value):
    if not value:
        return (1.0, 1.0, 1.0, 1.0)
    v = value.strip()
    lower = v.lower()
    try:
        if lower.startswith("rgba"):
            nums = v[v.index("(") + 1:v.index(")")].split(",")
            r, g, b, a = (float(n.strip()) for n in nums)
            return (r / 255.0, g / 255.0, b / 255.0, a / 255.0)
        if lower.startswith("rgb"):
            nums = v[v.index("(") + 1:v.index(")")].split(",")
            r, g, b = (float(n.strip()) for n in nums)
            return (r / 255.0, g / 255.0, b / 255.0, 1.0)
        if v.startswith("#"):
            h = v.lstrip("#")
            if len(h) == 6:
                r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
                return (r / 255.0, g / 255.0, b / 255.0, 1.0)
            if len(h) == 8:
                r, g, b, a = (int(h[i:i + 2], 16) for i in (0, 2, 4, 6))
                return (r / 255.0, g / 255.0, b / 255.0, a / 255.0)
    except (ValueError, IndexError):
        pass
    named = QColor(v)
    if named.isValid():
        return (named.redF(), named.greenF(), named.blueF(), named.alphaF())
    return (1.0, 1.0, 1.0, 1.0)


def format_color(rgba):
    r, g, b, a = rgba
    return f"rgba({round(r * 255)}, {round(g * 255)}, {round(b * 255)}, {round(a * 255)})"


def lighten(rgba, factor):
    r, g, b, a = rgba
    return (min(r * factor, 1.0), min(g * factor, 1.0), min(b * factor, 1.0), a)


def darken(rgba, factor):
    r, g, b, a = rgba
    return (r * factor, g * factor, b * factor, a)



SIMPLE_COLOR_KEYS = ["background", "background_pressed", "border", "text", "glow"]
SIMPLE_COLOR_LABELS = {
    "background": "Background",
    "background_pressed": "Background (Pressed)",
    "border": "Border",
    "text": "Text",
    "glow": "Glow",
}

RAW_COLOR_KEYS = [
    "bg_idle_top", "bg_idle_bottom", "bg_pressed_top", "bg_pressed_bottom",
    "border_idle", "border_pressed", "text", "shadow", "glow",
]

EFFECT_RANGES = {
    "border_radius": (0, 30),
    "shadow_blur": (0, 40),
    "glow_blur": (0, 60),
}


def compute_simple_colors(theme_colors):
    def avg(a, b):
        pa, pb = parse_color(a), parse_color(b)
        return tuple((x + y) / 2 for x, y in zip(pa, pb))

    return {
        "background": avg(theme_colors["bg_idle_top"], theme_colors["bg_idle_bottom"]),
        "background_pressed": avg(theme_colors["bg_pressed_top"], theme_colors["bg_pressed_bottom"]),
        "border": parse_color(theme_colors["border_idle"]),
        "text": parse_color(theme_colors["text"]),
        "glow": parse_color(theme_colors["glow"]),
    }


def derive_real_colors(simple_key, rgba):

    if simple_key == "background":
        return {
            "bg_idle_top": format_color(lighten(rgba, 1.3)),
            "bg_idle_bottom": format_color(darken(rgba, 0.7)),
        }
    if simple_key == "background_pressed":
        return {
            "bg_pressed_top": format_color(lighten(rgba, 1.3)),
            "bg_pressed_bottom": format_color(darken(rgba, 0.7)),
        }
    if simple_key == "border":
        r, g, b, a = rgba
        pressed = (min(r * 1.15, 1.0), min(g * 1.15, 1.0), min(b * 1.15, 1.0), min(a * 2.2, 1.0))
        return {
            "border_idle": format_color(rgba),
            "border_pressed": format_color(pressed),
        }
    if simple_key == "text":
        return {"text": format_color(rgba)}
    if simple_key == "glow":
        return {"glow": format_color(rgba)}
    return {}


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
        self.rgb_mode = False
        self._rgb_hue = 0.0

        # Hotkey (lock/hide) state
        self.hotkey_modifiers, self.hotkey_key = get_hotkey()
        self._mods_pressed = set()
        self._hotkey_held = False
        self._capturing_hotkey = False
        self._lock_toggle_pending = False

        self.apply_theme(get_active_theme(), first_run=True)

        # Restore saved window position
        saved_pos = get_overlay_position()
        if saved_pos and self._position_on_screen(*saved_pos):
            self.move(saved_pos[0], saved_pos[1])

        self.start_listeners()

    @staticmethod
    def _position_on_screen(x, y, margin=50):
        for screen in QApplication.screens():
            if screen.geometry().adjusted(-margin, -margin, margin, margin).contains(x, y):
                return True
        return False

    #  theme switching 

    def apply_theme(self, name, first_run=False, persist=True, scale_override=None, reset_colors=False):
        if reset_colors:
            clear_active_colors_override()
            clear_active_effects_override()
            clear_active_font_override()

        self.theme_name = name
        self.theme = load_theme(name)

        override = get_active_colors_override()
        if override:
            for key, value in override.items():
                if key in self.theme["colors"]:
                    self.theme["colors"][key] = value

        self.pixel_font_family = self.load_theme_font()

        self.scale = scale_override if scale_override is not None else get_scale()
        self.hidden = get_hidden_elements()
        self.rgb_mode = get_rgb_mode()

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


        effects_override = get_active_effects_override()
        if effects_override:
            self.BORDER_RADIUS = effects_override.get("border_radius", self.BORDER_RADIUS)
            self.SHADOW_BLUR = effects_override.get("shadow_blur", self.SHADOW_BLUR)
            self.GLOW_BLUR = effects_override.get("glow_blur", self.GLOW_BLUR)

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

    def switch_theme(self, name):
 
        self.apply_theme(name, reset_colors=True)

    def set_scale(self, scale, persist=True):
        scale = min(max(scale, 0.5), 2.0)
        now = time.time()
        if not persist:

            if now - self._last_scale_rebuild < 0.05:
                return
            self._last_scale_rebuild = now
            self.apply_theme(self.theme_name, persist=False, scale_override=scale)
        else:

            set_scale(scale)
            self.apply_theme(self.theme_name, persist=True, scale_override=scale)

    def set_hidden(self, hidden_set):
        set_hidden_elements(hidden_set)
        self.apply_theme(self.theme_name)

    #  hotkey rebinding 

    def start_hotkey_capture(self):
        self._capturing_hotkey = True

    def get_hotkey_state(self):
        return self._capturing_hotkey, format_hotkey(self.hotkey_modifiers, self.hotkey_key)

    #  RGB rainbow mode 

    def get_rgb_mode(self):
        return self.rgb_mode

    def set_rgb_mode(self, enabled):

        self.rgb_mode = enabled
        set_rgb_mode(enabled)

    #  theme colors  

    def get_simple_colors(self):
        return compute_simple_colors(self.theme["colors"])

    def set_simple_color(self, simple_key, rgba, persist=False):
        updates = derive_real_colors(simple_key, rgba)
        for key, value in updates.items():
            self.theme["colors"][key] = value

        if persist:
            override = get_active_colors_override() or {}
            override.update(updates)
            set_active_colors_override(override)

    def get_raw_colors(self):
        return {key: parse_color(self.theme["colors"][key]) for key in RAW_COLOR_KEYS}

    def set_raw_color(self, key, rgba, persist=False):
        self.theme["colors"][key] = format_color(rgba)
        if persist:
            override = get_active_colors_override() or {}
            override[key] = format_color(rgba)
            set_active_colors_override(override)

    def get_effect_values(self):
        return {
            "border_radius": self.BORDER_RADIUS,
            "shadow_blur": self.SHADOW_BLUR,
            "glow_blur": self.GLOW_BLUR,
        }

    def set_effect_value(self, key, value, persist=False):
        value = round(value)
        if key == "border_radius":
            self.BORDER_RADIUS = value
        elif key == "shadow_blur":
            self.SHADOW_BLUR = value
        elif key == "glow_blur":
            self.GLOW_BLUR = value
        if persist:
            override = get_active_effects_override() or {}
            override[key] = value
            set_active_effects_override(override)

    #  font (active them override)

    def import_font(self, path):
        set_active_font_override(path)
        self.apply_theme(self.theme_name, persist=False)

    def reset_colors(self):
        self.apply_theme(self.theme_name, persist=False, reset_colors=True)

    #  export current live theme as .ks 

    def get_export_theme_data(self):
        shape = dict(self.theme["shape"])
        if self.scale:
            shape["border_radius"] = round(self.BORDER_RADIUS / self.scale)
            shape["shadow_blur"] = round(self.SHADOW_BLUR / self.scale)
            shape["glow_blur"] = round(self.GLOW_BLUR / self.scale)
        display_name = self.theme.get("name") or self.theme_name
        return {
            "colors": dict(self.theme["colors"]),
            "shape": shape,
            "font": dict(self.theme["font"]),
            "source_dir": self.theme["_dir"],
            "display_name": display_name,
        }

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
            action.triggered.connect(lambda checked, n=folder_name: self.switch_theme(n))
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
            self.switch_theme(folder_name)

    # styling helper

    def load_theme_font(self):
        # font override (imported)
        override_path = get_active_font_override()
        if override_path and os.path.exists(override_path):
            font_id = QFontDatabase.addApplicationFont(override_path)
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                return families[0]

        #  The current themes own bundled font
        font_path = os.path.join(self.theme["_dir"], self.theme["font"]["file"])
        if os.path.exists(font_path):
            font_id = QFontDatabase.addApplicationFont(font_path)
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                return families[0]

#load fallback if it aint work
        return load_fallback_font_family()

    def font_for(self, size):
        font_cfg = self.theme["font"]
        f = QFont(self.pixel_font_family, size)
        f.setBold(font_cfg["bold"])
        f.setStretch(font_cfg["stretch"])
        return f

    def drop_shadow(self, glow=False):
        if self.rgb_mode:
            color = rgba01_to_qcolor(hsv_to_rgba01(self._rgb_hue, 1.0, 1.0, 0.85 if glow else 0.55))
        else:
            colors = self.theme["colors"]
            color = QColor(colors["glow"] if glow else colors["shadow"])

        effect = QGraphicsDropShadowEffect()
        if glow:
            effect.setBlurRadius(self.GLOW_BLUR)
            effect.setXOffset(0)
            effect.setYOffset(0)
        else:
            effect.setBlurRadius(self.SHADOW_BLUR)
            effect.setXOffset(0)
            effect.setYOffset(3)
        effect.setColor(color)
        return effect

    def block_style(self, pressed=False):
        if self.rgb_mode:
            hue = self._rgb_hue
            alpha = 0.85 if pressed else 0.75
            top = rgba01_to_css(hsv_to_rgba01(hue, 0.75, 0.95, alpha))
            bottom = rgba01_to_css(hsv_to_rgba01(hue, 0.8, 0.6, alpha))
            border = rgba01_to_css(hsv_to_rgba01(hue, 1.0, 1.0, 0.95))
            bg = gradient(top, bottom)
            text = "white"
        else:
            c = self.theme["colors"]
            bg = gradient(c["bg_pressed_top"], c["bg_pressed_bottom"]) if pressed \
                else gradient(c["bg_idle_top"], c["bg_idle_bottom"])
            border = c["border_pressed"] if pressed else c["border_idle"]
            text = c["text"]
        return (
            f"background: {bg}; color: {text}; "
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

        if self.rgb_mode:

            self._rgb_hue = rgb_hue()

        for key, label in self.key_blocks.items():
            pressed = self.keys[key]
            label.setStyleSheet(self.block_style(pressed))
            label.setGraphicsEffect(self.drop_shadow(glow=pressed))

        if "LMB" not in self.hidden:
            self.lmb_label.setStyleSheet(self.block_style())
            self.lmb_label.setGraphicsEffect(self.drop_shadow())
        if "RMB" not in self.hidden:
            self.rmb_label.setStyleSheet(self.block_style())
            self.rmb_label.setGraphicsEffect(self.drop_shadow())

    def apply_lock_toggle(self):
        self.locked = not self.locked
        self.setAttribute(Qt.WA_TransparentForMouseEvents, self.locked)
        if self.panel is not None:
            self.panel.set_visible(not self.locked)

    def start_listeners(self):
        threading.Thread(target=self.keyboard_listener, daemon=True).start()
        threading.Thread(target=self.mouse_listener, daemon=True).start()
        threading.Thread(target=self.cps_updater, daemon=True).start()

    def keyboard_listener(self):
        from pynput import keyboard as pkb

        modifier_map = {
            pkb.Key.alt_l: "alt", pkb.Key.alt_r: "alt", pkb.Key.alt: "alt",
            pkb.Key.ctrl_l: "ctrl", pkb.Key.ctrl_r: "ctrl", pkb.Key.ctrl: "ctrl",
            pkb.Key.shift_l: "shift", pkb.Key.shift_r: "shift", pkb.Key.shift: "shift",
        }

        def key_display_name(key):
            char = getattr(key, "char", None)
            if char:
                return char.upper()
            name = getattr(key, "name", None)
            if name:
                return name.upper()
            return str(key).upper()

        def on_press(key):
            # WASD tracking
            char = getattr(key, "char", None)
            if char:
                c = char.upper()
                if c in self.keys:
                    self.keys[c] = True

            # Modifier tracking
            mod = modifier_map.get(key)
            if mod:
                self._mods_pressed.add(mod)
                return

            if key == pkb.Key.space:
                self.keys["SPACE"] = True

            name = key_display_name(key)

            if self._capturing_hotkey:
                mods_snapshot = frozenset(self._mods_pressed)
                self.hotkey_modifiers = mods_snapshot
                self.hotkey_key = name
                set_hotkey(sorted(mods_snapshot), name)
                self._capturing_hotkey = False
                return

            if (
                frozenset(self._mods_pressed) == self.hotkey_modifiers
                and name == self.hotkey_key
                and not self._hotkey_held
            ):
                self._hotkey_held = True
                self._lock_toggle_pending = True

        def on_release(key):
            char = getattr(key, "char", None)
            if char:
                c = char.upper()
                if c in self.keys:
                    self.keys[c] = False

            mod = modifier_map.get(key)
            if mod:
                self._mods_pressed.discard(mod)
                return

            if key == pkb.Key.space:
                self.keys["SPACE"] = False

            if key_display_name(key) == self.hotkey_key:
                self._hotkey_held = False

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
                pass
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
        was_dragging = self.drag_position is not None
        self.drag_position = None
        if was_dragging:
            set_overlay_position(self.x(), self.y())
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


def pick_ks_save_file(parent=None, default_name="theme.ks"):
    path, _ = QFileDialog.getSaveFileName(
        parent, "Export .ks Theme", default_name, "Keystrokes theme (*.ks);;All files (*)"
    )
    return path


def pick_font_file(parent=None):
    path, _ = QFileDialog.getOpenFileName(
        parent, "Import Font", "", "Font files (*.ttf *.otf);;All files (*)"
    )
    return path

#ImGui panel for settings

class ImGuiThemePanel:
    def __init__(
        self,
        on_theme_applied=None,
        on_scale_changed=None,
        on_hidden_changed=None,
        on_hotkey_capture_start=None,
        get_hotkey_state=None,
        get_simple_colors=None,
        on_simple_color_changed=None,
        get_raw_colors=None,
        on_raw_color_changed=None,
        get_effect_values=None,
        on_effect_value_changed=None,
        get_rgb_mode=None,
        on_rgb_mode_changed=None,
        on_reset_colors=None,
        get_export_data=None,
        on_import_font=None,
    ):
        self.on_theme_applied = on_theme_applied
        self.on_scale_changed = on_scale_changed
        self.on_hidden_changed = on_hidden_changed
        self.on_hotkey_capture_start = on_hotkey_capture_start
        self.get_hotkey_state = get_hotkey_state
        self.get_simple_colors = get_simple_colors
        self.on_simple_color_changed = on_simple_color_changed
        self.get_raw_colors = get_raw_colors
        self.on_raw_color_changed = on_raw_color_changed
        self.get_effect_values = get_effect_values
        self.on_effect_value_changed = on_effect_value_changed
        self.get_rgb_mode = get_rgb_mode
        self.on_rgb_mode_changed = on_rgb_mode_changed
        self.on_reset_colors = on_reset_colors
        self.get_export_data = get_export_data
        self.on_import_font = on_import_font
        self.status = ""
        self.themes = []
        self.selected_index = 0
        self.scale = get_scale()
        self.hidden = get_hidden_elements()
        self.advanced = False
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

        self.window = glfw.create_window(340, 720, "Keystrokes Theme Manager", None, None)
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
        self._base_window_bg = (0.08, 0.08, 0.10, 0.96)
        self._base_border = tuple(style.colors[imgui.COLOR_BORDER])
        style.colors[imgui.COLOR_WINDOW_BACKGROUND] = self._base_window_bg

        saved_pos = get_panel_position()
        if saved_pos and self._monitor_position_valid(*saved_pos):
            glfw.set_window_pos(self.window, saved_pos[0], saved_pos[1])

        self.refresh_themes()
        self.visible = True

    @staticmethod
    def _monitor_position_valid(x, y, margin=50):
        for monitor in glfw.get_monitors():
            mx, my = glfw.get_monitor_pos(monitor)
            mode = glfw.get_video_mode(monitor)
            w, h = mode.size.width, mode.size.height
            if (mx - margin) <= x <= (mx + w + margin) and (my - margin) <= y <= (my + h + margin):
                return True
        return False

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

        rgb_on = self.get_rgb_mode() if self.get_rgb_mode else False
        style = imgui.get_style()
        if rgb_on:
            hue = rgb_hue()
            style.colors[imgui.COLOR_WINDOW_BACKGROUND] = hsv_to_rgba01(hue, 0.5, 0.22, 0.92)
            style.colors[imgui.COLOR_BORDER] = hsv_to_rgba01((hue + 0.5) % 1.0, 0.8, 1.0, 1.0)
        else:

            style.colors[imgui.COLOR_WINDOW_BACKGROUND] = self._base_window_bg
            style.colors[imgui.COLOR_BORDER] = self._base_border

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
            if self.dragging:
                # Drag ended
                set_panel_position(*glfw.get_window_pos(self.window))
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
            # Slider released 
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

        # Hotkey rebinding
        imgui.spacing()
        imgui.separator()
        imgui.spacing()

        capturing, hotkey_display = (False, "Alt+F3")
        if self.get_hotkey_state:
            capturing, hotkey_display = self.get_hotkey_state()

        imgui.text("Hide Hotkey:")
        imgui.text_colored(hotkey_display, 0.9, 0.9, 0.9)
        imgui.same_line()
        if imgui.button("Rebind##hotkey"):
            if self.on_hotkey_capture_start:
                self.on_hotkey_capture_start()
        if capturing:
            imgui.text_colored("Press a new key combo...", 1.0, 0.85, 0.3)

        # RGB rainbow mode 
        imgui.spacing()
        imgui.separator()
        imgui.spacing()

        changed, rgb_on = imgui.checkbox("RGB Mode (rainbow everything)", rgb_on)
        if changed and self.on_rgb_mode_changed:
            self.on_rgb_mode_changed(rgb_on)

        imgui.spacing()
        imgui.text("Colors:" if not self.advanced else "Colors (Advanced):")
        imgui.same_line()
        if imgui.button("Advanced" if not self.advanced else "Simple"):
            self.advanced = not self.advanced

        if self.advanced:
            imgui.spacing()
            imgui.text_colored("All colors:", 0.75, 0.75, 0.75)
            raw_colors = self.get_raw_colors() if self.get_raw_colors else {}
            for key in RAW_COLOR_KEYS:
                if key not in raw_colors:
                    continue
                rgba = raw_colors[key]
                changed, new_rgba = imgui.color_edit4(
                    f"{key}##raw_{key}", *rgba, flags=imgui.COLOR_EDIT_NO_INPUTS
                )
                if changed and self.on_raw_color_changed:
                    self.on_raw_color_changed(key, new_rgba, False)
                if imgui.is_item_deactivated_after_edit() and self.on_raw_color_changed:
                    self.on_raw_color_changed(key, new_rgba, True)

            imgui.spacing()
            imgui.text_colored("Effects:", 0.75, 0.75, 0.75)
            effects = self.get_effect_values() if self.get_effect_values else {}
            for key, (lo, hi) in EFFECT_RANGES.items():
                if key not in effects:
                    continue
                changed, val = imgui.slider_int(f"{key}##effect_{key}", effects[key], lo, hi)
                if changed and self.on_effect_value_changed:
                    self.on_effect_value_changed(key, val, False)
                if imgui.is_item_deactivated_after_edit() and self.on_effect_value_changed:
                    self.on_effect_value_changed(key, val, True)

            imgui.spacing()
            imgui.text_colored("Font:", 0.75, 0.75, 0.75)
            if imgui.button("Import Font..."):
                path = pick_font_file()
                if path:
                    if self.on_import_font:
                        self.on_import_font(path)
                    self.status = f"Font set from '{os.path.basename(path)}'."

            imgui.spacing()
            if imgui.button("Export as .ks..."):
                data = self.get_export_data() if self.get_export_data else None
                if data:
                    default_name = f"{_slugify(data['display_name'])}.ks"
                    path = pick_ks_save_file(default_name=default_name)
                    if path:
                        ok, error = export_active_ks(
                            data["colors"], data["shape"], data["font"],
                            data["source_dir"], path, data["display_name"],
                        )
                        self.status = f"Export failed: {error}" if error else f"Exported to '{path}'."
        else:
            simple_colors = self.get_simple_colors() if self.get_simple_colors else {}
            for key in SIMPLE_COLOR_KEYS:
                if key not in simple_colors:
                    continue
                rgba = simple_colors[key]
                changed, new_rgba = imgui.color_edit4(
                    f"{SIMPLE_COLOR_LABELS[key]}##{key}", *rgba, flags=imgui.COLOR_EDIT_NO_INPUTS
                )
                if changed and self.on_simple_color_changed:
                    self.on_simple_color_changed(key, new_rgba, False)
                if imgui.is_item_deactivated_after_edit() and self.on_simple_color_changed:
                    self.on_simple_color_changed(key, new_rgba, True)

        imgui.spacing()
        if imgui.button("Reset Colors"):
            if self.on_reset_colors:
                self.on_reset_colors()
                self.status = "Colors, effects, and font reset to theme defaults."

        imgui.spacing()
        imgui.set_window_font_scale(0.8)
        imgui.text_colored(f"{hotkey_display} to hide", 0.6, 0.6, 0.6)
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

    app.setQuitOnLastWindowClosed(False)

    ok, err = ensure_assets_downloaded()
    if not ok:
        QMessageBox.warning(
            None, "Setup",
            "Couldn't download required files from GitHub:\n"
            f"{err}\n\nThe app will still run using built-in fallback styling."
        )

    overlay = KeystrokesOverlay()
    overlay.run()

    panel = None
    try:
        panel = ImGuiThemePanel(
            on_theme_applied=overlay.switch_theme,
            on_scale_changed=overlay.set_scale,
            on_hidden_changed=overlay.set_hidden,
            on_hotkey_capture_start=overlay.start_hotkey_capture,
            get_hotkey_state=overlay.get_hotkey_state,
            get_simple_colors=overlay.get_simple_colors,
            on_simple_color_changed=overlay.set_simple_color,
            get_raw_colors=overlay.get_raw_colors,
            on_raw_color_changed=overlay.set_raw_color,
            get_effect_values=overlay.get_effect_values,
            on_effect_value_changed=overlay.set_effect_value,
            get_rgb_mode=overlay.get_rgb_mode,
            on_rgb_mode_changed=overlay.set_rgb_mode,
            on_reset_colors=overlay.reset_colors,
            get_export_data=overlay.get_export_theme_data,
            on_import_font=overlay.import_font,
        )
    except Exception as e:
        QMessageBox.critical(
            None, "Settings panel failed to start",
            f"{type(e).__name__}: {e}\n\n"
            "The overlay itself will still run — only the settings panel is unavailable."
        )
    overlay.panel = panel

    imgui_timer = QTimer()

    def imgui_tick():
        if panel is not None and not panel.tick():
            imgui_timer.stop()
            app.quit()

    if panel is not None:
        imgui_timer.timeout.connect(imgui_tick)
        imgui_timer.start(16)

    def on_about_to_quit():
        if panel is not None:
            panel.shutdown()

    app.aboutToQuit.connect(on_about_to_quit)

    sys.exit(app.exec_())