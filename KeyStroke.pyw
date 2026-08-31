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
    QMenu, QAction, QActionGroup, QFileDialog, QMessageBox, QPushButton, QComboBox,
    QCheckBox, QSlider, QScrollArea, QGroupBox, QFormLayout, QColorDialog, QSpinBox,
    QDoubleSpinBox, QDialog, QDialogButtonBox, QGridLayout, QFrame
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

import logging

def _setup_logging():
    log_path = os.path.join(_LAUNCHER_DIR, "keystroke_debug.log")
    try:
        logging.basicConfig(
            filename=log_path,
            filemode="a",
            level=logging.DEBUG,
            format="%(asctime)s [%(levelname)s] %(message)s",
        )
    except OSError:
        log_path = os.path.join(tempfile.gettempdir(), "keystroke_debug.log")
        logging.basicConfig(
            filename=log_path,
            filemode="a",
            level=logging.DEBUG,
            format="%(asctime)s [%(levelname)s] %(message)s",
        )
    logging.info("=== KeyStroke starting ===")
    logging.info(f"dir source: {_DIR_SOURCE}")
    logging.info(f"bundle dir: {_BUNDLE_DIR}")
    logging.info(f"launcher dir: {_LAUNCHER_DIR}")
    return log_path


LOG_PATH = _setup_logging()

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
        logging.debug("All required assets already present, skipping download.")
        return True, None

    logging.info("Required files missing — downloading from GitHub...")
    tmp_dir = tempfile.mkdtemp(prefix="ks_assets_")
    zip_path = os.path.join(tmp_dir, "repo.zip")
    logging.debug(f"Download URL: {_github_zip_url()}")
    logging.debug(f"Temp dir: {tmp_dir}")

    try:
        urllib.request.urlretrieve(_github_zip_url(), zip_path)
        logging.debug("Zip downloaded, extracting...")

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp_dir)

        extracted_root = None
        for entry in os.listdir(tmp_dir):
            full = os.path.join(tmp_dir, entry)
            if os.path.isdir(full) and entry.lower().startswith(GITHUB_REPO.lower()):
                extracted_root = full
                break
        if extracted_root is None:
            logging.error("Downloaded archive had an unexpected layout.")
            return False, "Downloaded archive had an unexpected layout."

        for name in REQUIRED_ASSETS:
            if not _asset_missing(name):
                continue
            src = os.path.join(extracted_root, name)
            if not os.path.exists(src):
                logging.debug(f"Repo has no '{name}', skipping.")
                continue
            logging.debug(f"Copying '{name}' into {SCRIPT_DIR}")
            _merge_copy(src, os.path.join(SCRIPT_DIR, name))

        logging.info("Assets downloaded successfully.")
        return True, None

    except (urllib.error.URLError, urllib.error.HTTPError, zipfile.BadZipFile, OSError) as e:
        logging.exception("Asset download failed")
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
        self._clicks_lock = threading.Lock()
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
        logging.debug(f"apply_theme(name={name!r}, first_run={first_run})")
        if reset_colors:
            clear_active_colors_override()
            clear_active_effects_override()
            clear_active_font_override()

        self.theme_name = name
        self.theme = load_theme(name)
        logging.debug(f"Loaded theme dir: {self.theme.get('_dir')}")

        override = get_active_colors_override()
        if override:
            for key, value in override.items():
                if key in self.theme["colors"]:
                    self.theme["colors"][key] = value

        self.pixel_font_family = self.load_theme_font()
        logging.debug(f"Resolved font family: {self.pixel_font_family}")

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
        self.lmb_label.setWordWrap(False)
        self.rmb_label.setWordWrap(False)
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

        # CPS labels must be updated from the GUI thread.
        with self._clicks_lock:
            left_cps = len(self.left_clicks)
            right_cps = len(self.right_clicks)
        if "LMB" not in self.hidden:
            self.lmb_label.setText(f"LMB\n{left_cps} CPS")
        if "RMB" not in self.hidden:
            self.rmb_label.setText(f"RMB\n{right_cps} CPS")

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
                now = time.time()
                with self._clicks_lock:
                    if button == pmouse.Button.left:
                        self.left_clicks.append(now)
                    elif button == pmouse.Button.right:
                        self.right_clicks.append(now)

        with pmouse.Listener(on_click=on_click) as listener:
            listener.join()

    def cps_updater(self):
        # Kept as a lightweight maintenance thread. Never touches Qt widgets.
        while True:
            now = time.time()
            with self._clicks_lock:
                self.left_clicks = [t for t in self.left_clicks if now - t <= 1.0]
                self.right_clicks = [t for t in self.right_clicks if now - t <= 1.0]
            time.sleep(0.10)

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
        if self.panel is not None:
            self.panel._hotkey_capture_timer.stop()
            self.panel.hide()
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


# Native PyQt5 settings panel.
# This replaces the previous ImGui + GLFW + OpenGL implementation.
class ThemePanel(QWidget):
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
        super().__init__()
        self.setWindowTitle("Keystrokes Theme Manager")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setWindowOpacity(0.9)
        self.setFixedWidth(320)
        self.setObjectName("ThemePanel")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("""
            QWidget#ThemePanel {
                background: rgba(15, 16, 19, 250); color: #d6d7db;
                font-family: Segoe UI, Arial, sans-serif; font-size: 11px;
                border: 1px solid #26272c;
            }
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { background: #101114; width: 8px; margin: 0; }
            QScrollBar::handle:vertical { background: #35373d; min-height: 24px; border-radius: 4px; }
            QScrollBar::handle:vertical:hover { background: #46484f; }
            QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
            QLabel#sectionLabel {
                color: #8d9199; font-size: 10px; font-weight: 600;
                letter-spacing: 0.5px; padding-top: 6px;
            }
            QLabel#colorRowLabel { color: #9a9da4; font-size: 11px; }
            QWidget#hsep { background: #3d3f47; border: none; }
            QPushButton, QComboBox {
                background: #202226; color: #dcdde0; border: 1px solid #303236;
                border-radius: 3px; padding: 3px 6px; min-height: 18px;
            }
            QPushButton:hover, QComboBox:hover { background: #26282d; border-color: #43454b; }
            QPushButton:pressed { background: #17181b; }
            QPushButton:focus, QComboBox:focus { border: 1px solid #3a6cc4; }
            QComboBox::drop-down { border: none; width: 18px; }
            QComboBox::down-arrow {
                image: none; width: 0; height: 0;
                border-left: 4px solid transparent; border-right: 4px solid transparent;
                border-top: 5px solid #8d9199; margin-right: 6px;
            }
            QComboBox QAbstractItemView {
                background: #17181b; color: #e6e6e6; border: 1px solid #303236;
                selection-background-color: #3a6cc4; selection-color: white; padding: 2px;
            }
            QCheckBox { spacing: 6px; color: #d2d3d8; padding: 1px 0; }
            QCheckBox::indicator {
                width: 13px; height: 13px; border-radius: 2px;
                border: 1px solid #40434a; background: #17181b;
            }
            QCheckBox::indicator:hover { border-color: #5a5d66; }
            QCheckBox::indicator:checked { background: #3a6cc4; border-color: #3a6cc4; }
            QSlider::groove:horizontal { height: 3px; background: #26272c; border-radius: 1px; }
            QSlider::sub-page:horizontal { background: #3a6cc4; border-radius: 1px; }
            QSlider::handle:horizontal {
                width: 11px; height: 11px; margin: -4px 0;
                background: #dcdde0; border: 1px solid #3a6cc4; border-radius: 5px;
            }
            QSlider::handle:horizontal:hover { background: #ffffff; }
            QLabel#status { color: #7f8790; padding-top: 4px; font-size: 10px; }
            QLabel#hint { color: #6a6d74; font-size: 10px; }
        """)

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

        self.status = QLabel("")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        self.advanced = False
        self._drag_offset = None
        self._color_buttons = {}
        self._effect_sliders = {}
        self._effect_labels = {}
        self._hotkey_capture_timer = QTimer(self)
        self._hotkey_capture_timer.timeout.connect(self.refresh_hotkey)
        self._hotkey_capture_timer.start(100)

        self._build()

        saved_pos = get_panel_position()
        if saved_pos and self._position_valid(*saved_pos):
            self.move(*saved_pos)

    @staticmethod
    def _position_valid(x, y, margin=50):
        for screen in QApplication.screens():
            if screen.geometry().adjusted(-margin, -margin, margin, margin).contains(x, y):
                return True
        return False

    #  flat imgui-style section helpers 

    @staticmethod
    def _section_label(text):
        label = QLabel(text)
        label.setObjectName("sectionLabel")
        return label

    @staticmethod
    def _sep():
        line = QWidget()
        line.setObjectName("hsep")
        line.setFixedHeight(1)
        line.setAttribute(Qt.WA_StyledBackground, True)
        return line

    def _build(self):
        old = self.layout()
        if old:
            while old.count():
                item = old.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            QWidget().setLayout(old)

        root = QVBoxLayout(self)
        root.setContentsMargins(9, 7, 9, 8)
        root.setSpacing(4)

        header = QHBoxLayout()
        title = QLabel("Keystrokes Theme Manager")
        title.setStyleSheet("font-size: 13px; font-weight: 600; color: #f0f0f2;")
        header.addWidget(title)
        header.addStretch()
        close = QPushButton("×")
        close.setFixedSize(20, 20)
        close.setStyleSheet("font-size: 15px; font-weight: 600; padding: 0; color: #b8b9bd;")
        close.clicked.connect(self.close)
        header.addWidget(close)
        root.addLayout(header)
        root.addWidget(self._sep())

        content = QWidget()
        content.setAttribute(Qt.WA_StyledBackground, True)
        content.setStyleSheet("background: transparent;")
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(5)
        root.addWidget(content)

        # Theme
        self.content_layout.addWidget(self._section_label("THEME"))
        self.theme_combo = QComboBox()
        self.refresh_themes()
        self.content_layout.addWidget(self.theme_combo)
        apply_btn = QPushButton("Apply Theme")
        apply_btn.clicked.connect(self.apply_selected_theme)
        self.content_layout.addWidget(apply_btn)
        self.content_layout.addWidget(self._sep())

        import_btn = QPushButton("Import .ks Theme...")
        import_btn.clicked.connect(self.import_ks_theme)
        self.content_layout.addWidget(import_btn)
        self.content_layout.addWidget(self._sep())

        # Overlay size
        self.content_layout.addWidget(self._section_label("OVERLAY SIZE"))
        self.scale_slider = QSlider(Qt.Horizontal)
        self.scale_slider.setRange(50, 200)
        self.scale_slider.setValue(round(get_scale() * 100))
        self.scale_slider.valueChanged.connect(self.scale_changed)
        self.scale_slider.sliderReleased.connect(self.scale_released)
        self.content_layout.addWidget(self.scale_slider)
        self.content_layout.addWidget(self._sep())

        # Elements
        self.content_layout.addWidget(self._section_label("SHOW ELEMENTS"))
        grid = QGridLayout()
        grid.setSpacing(4)
        hidden = get_hidden_elements()
        self.element_checks = {}
        for i, name in enumerate(ELEMENT_NAMES):
            cb = QCheckBox(name)
            cb.setChecked(name not in hidden)
            cb.stateChanged.connect(lambda state, n=name: self.element_changed(n, state))
            self.element_checks[name] = cb
            grid.addWidget(cb, i // 3, i % 3)
        self.content_layout.addLayout(grid)
        self.content_layout.addWidget(self._sep())

        # Hotkey
        self.content_layout.addWidget(self._section_label("HIDE HOTKEY"))
        hl = QHBoxLayout()
        self.hotkey_label = QLabel()
        self.hotkey_label.setStyleSheet("color: #cccccc;")
        hl.addWidget(self.hotkey_label, 1)
        self.rebind_btn = QPushButton("Rebind")
        self.rebind_btn.clicked.connect(self.start_capture)
        hl.addWidget(self.rebind_btn)
        self.content_layout.addLayout(hl)
        self.refresh_hotkey()
        self.content_layout.addWidget(self._sep())

        # RGB
        self.rgb_check = QCheckBox("RGB Mode (rainbow everything)")
        self.rgb_check.setChecked(bool(self.get_rgb_mode() if self.get_rgb_mode else False))
        self.rgb_check.stateChanged.connect(self.rgb_changed)
        self.content_layout.addWidget(self.rgb_check)
        self.content_layout.addWidget(self._sep())

        # Colors
        colors_header = QHBoxLayout()
        self.colors_label = self._section_label("COLORS")
        colors_header.addWidget(self.colors_label)
        colors_header.addStretch()
        self.advanced_btn = QPushButton("Advanced")
        self.advanced_btn.clicked.connect(self.toggle_advanced)
        colors_header.addWidget(self.advanced_btn)
        self.content_layout.addLayout(colors_header)

        self.color_container = QWidget()
        self.color_layout = QVBoxLayout(self.color_container)
        self.color_layout.setContentsMargins(0, 2, 0, 0)
        self.color_layout.setSpacing(4)
        self.content_layout.addWidget(self.color_container)
        self.rebuild_colors()

        self.content_layout.addWidget(self._sep())

        # Actions
        actions = QHBoxLayout()
        actions.setSpacing(5)
        reset = QPushButton("Reset Colors")
        reset.clicked.connect(self.reset_colors)
        actions.addWidget(reset)
        export_btn = QPushButton("Export .ks")
        export_btn.clicked.connect(self.export_theme)
        actions.addWidget(export_btn)
        font_btn = QPushButton("Import Font")
        font_btn.clicked.connect(self.import_font)
        actions.addWidget(font_btn)
        self.content_layout.addLayout(actions)

        self.hint_label = QLabel()
        self.hint_label.setObjectName("hint")
        self.content_layout.addWidget(self.hint_label)
        self._update_hint()

        self.content_layout.addWidget(self.status)

        self.setFixedWidth(320)
        self.adjustSize()

    def _update_hint(self):
        if self.get_hotkey_state:
            _capturing, display = self.get_hotkey_state()
            self.hint_label.setText(f"{display} to hide")

    def refresh_themes(self):
        if not hasattr(self, "theme_combo"):
            return
        current = get_active_theme()
        self.theme_combo.blockSignals(True)
        self.theme_combo.clear()
        for folder, display in list_themes():
            self.theme_combo.addItem(display, folder)
        idx = self.theme_combo.findData(current)
        if idx >= 0:
            self.theme_combo.setCurrentIndex(idx)
        self.theme_combo.blockSignals(False)

    def apply_selected_theme(self):
        name = self.theme_combo.currentData()
        if not name:
            return
        set_active_theme(name)
        self.status.setText(f"Applied '{self.theme_combo.currentText()}'.")
        if self.on_theme_applied:
            self.on_theme_applied(name)
        self.rebuild_colors()
        self.refresh_themes()

    def import_ks_theme(self):
        path = pick_ks_file(self)
        if not path:
            return
        folder, error = import_ks(path)
        if error:
            QMessageBox.warning(self, "Import failed", error)
            return
        self.status.setText(f"Imported as '{folder}'.")
        self.refresh_themes()
        self.theme_combo.setCurrentIndex(self.theme_combo.findData(folder))
        if self.on_theme_applied:
            self.on_theme_applied(folder)
        self.rebuild_colors()

    def scale_changed(self, value):
        if self.on_scale_changed:
            self.on_scale_changed(value / 100.0, False)

    def scale_released(self):
        if self.on_scale_changed:
            self.on_scale_changed(self.scale_slider.value() / 100.0, True)

    def element_changed(self, name, state):
        hidden = {n for n, cb in self.element_checks.items() if not cb.isChecked()}
        set_hidden_elements(hidden)
        if self.on_hidden_changed:
            self.on_hidden_changed(hidden)

    def start_capture(self):
        if self.on_hotkey_capture_start:
            self.on_hotkey_capture_start()
        self.status.setText("Press a new key combination...")
        self.rebind_btn.setText("Listening...")

    def refresh_hotkey(self):
        if not self.get_hotkey_state:
            return
        capturing, display = self.get_hotkey_state()
        self.hotkey_label.setText(display)
        self.rebind_btn.setText("Listening..." if capturing else "Rebind")
        if capturing:
            self.status.setText("Press a new key combination...")
        if hasattr(self, "hint_label"):
            self.hint_label.setText(f"{display} to hide")

    def rgb_changed(self, state):
        enabled = bool(state)
        if self.on_rgb_mode_changed:
            self.on_rgb_mode_changed(enabled)

    def toggle_advanced(self):
        self.advanced = not self.advanced
        self.advanced_btn.setText("Simple" if self.advanced else "Advanced")
        self.colors_label.setText("COLORS (ADVANCED)" if self.advanced else "COLORS")
        self.rebuild_colors()

    def _make_color_row(self, key, label, rgba, advanced):
        row = QHBoxLayout()
        row.setSpacing(6)
        text = QLabel(label)
        text.setObjectName("colorRowLabel")
        row.addWidget(text, 1)
        swatch = QPushButton()
        swatch.setFixedSize(58, 18)
        swatch.clicked.connect(lambda _, k=key: self.pick_color(k, advanced))
        self._color_buttons[(advanced, key)] = swatch
        self._set_swatch_color(swatch, rgba)
        row.addWidget(swatch)
        return row

    @staticmethod
    def _set_swatch_color(btn, rgba):
        c = rgba01_to_qcolor(rgba)
        btn.setStyleSheet(
            f"QPushButton {{ background: {c.name(QColor.HexArgb)}; "
            "border: 1px solid #45484f; border-radius: 3px; }"
            "QPushButton:hover { border: 1px solid #6a6d74; }"
        )

    def rebuild_colors(self):
        if not hasattr(self, "color_layout"):
            return
        while self.color_layout.count():
            item = self.color_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    sub = item.layout().takeAt(0)
                    if sub.widget():
                        sub.widget().deleteLater()
        self._color_buttons.clear()
        self._effect_sliders.clear()
        self._effect_labels.clear()

        if self.advanced:
            colors = self.get_raw_colors() if self.get_raw_colors else {}
            for key in RAW_COLOR_KEYS:
                if key in colors:
                    self.color_layout.addLayout(self._make_color_row(key, key, colors[key], True))

            effects = self.get_effect_values() if self.get_effect_values else {}
            if effects:
                self.color_layout.addWidget(self._section_label("EFFECTS"))
            for key, (lo, hi) in EFFECT_RANGES.items():
                if key not in effects:
                    continue
                label = QLabel(f"{key}: {effects[key]}")
                label.setStyleSheet("color: #b8b9bd;")
                self.color_layout.addWidget(label)
                slider = QSlider(Qt.Horizontal)
                slider.setRange(lo, hi)
                slider.setValue(int(effects[key]))
                slider.valueChanged.connect(lambda v, k=key, lbl=label: self.effect_live(k, v, lbl))
                slider.sliderReleased.connect(lambda k=key, s=slider: self.effect_released(k, s))
                self.color_layout.addWidget(slider)
                self._effect_sliders[key] = slider
                self._effect_labels[key] = label
        else:
            colors = self.get_simple_colors() if self.get_simple_colors else {}
            for key in SIMPLE_COLOR_KEYS:
                if key in colors:
                    self.color_layout.addLayout(
                        self._make_color_row(key, SIMPLE_COLOR_LABELS[key], colors[key], False)
                    )

        QTimer.singleShot(0, self.adjustSize)

    def pick_color(self, key, advanced):
        source = self.get_raw_colors() if advanced else self.get_simple_colors()
        if not source or key not in source:
            return
        initial = rgba01_to_qcolor(source[key])
        color = QColorDialog.getColor(initial, self, "Choose color", QColorDialog.ShowAlphaChannel)
        if not color.isValid():
            return
        rgba = (color.redF(), color.greenF(), color.blueF(), color.alphaF())
        if advanced:
            if self.on_raw_color_changed:
                self.on_raw_color_changed(key, rgba, True)
        else:
            if self.on_simple_color_changed:
                self.on_simple_color_changed(key, rgba, True)
        self.rebuild_colors()

    def effect_live(self, key, value, label):
        label.setText(f"{key}: {value}")
        if self.on_effect_value_changed:
            self.on_effect_value_changed(key, value, False)

    def effect_released(self, key, slider):
        if self.on_effect_value_changed:
            self.on_effect_value_changed(key, slider.value(), True)

    def reset_colors(self):
        if self.on_reset_colors:
            self.on_reset_colors()
            self.status.setText("Colors, effects, and font reset to theme defaults.")
            self.rebuild_colors()

    def import_font(self):
        path = pick_font_file(self)
        if not path:
            return
        if self.on_import_font:
            self.on_import_font(path)
        self.status.setText(f"Font set from '{os.path.basename(path)}'.")

    def export_theme(self):
        data = self.get_export_data() if self.get_export_data else None
        if not data:
            return
        default_name = f"{_slugify(data['display_name'])}.ks"
        path = pick_ks_save_file(self, default_name)
        if not path:
            return
        ok, error = export_active_ks(
            data["colors"], data["shape"], data["font"],
            data["source_dir"], path, data["display_name"]
        )
        self.status.setText(f"Export failed: {error}" if error else f"Exported to '{path}'.")

    def set_visible(self, visible):
        if visible:
            self.show()
            self.raise_()
        else:
            self.hide()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPos() - self._drag_offset)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_offset is not None:
            set_panel_position(self.x(), self.y())
            self._drag_offset = None
        super().mouseReleaseEvent(event)

    def closeEvent(self, event):
        set_panel_position(self.x(), self.y())
        self._hotkey_capture_timer.stop()
        QApplication.instance().quit()
        event.accept()

    def shutdown(self):
        self._hotkey_capture_timer.stop()
        set_panel_position(self.x(), self.y())
        self.hide()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(False)

    try:
        logging.info("Checking required assets...")
        ok, err = ensure_assets_downloaded()
        if not ok:
            logging.warning(f"Asset download failed: {err}")
            QMessageBox.warning(
                None, "Setup",
                "Couldn't download required files from GitHub:\n"
                f"{err}\n\nThe app will still run using built-in fallback styling."
            )

        logging.info("Creating overlay...")
        overlay = KeystrokesOverlay()
        overlay.run()
        logging.info("Overlay created and shown.")

        logging.info("Creating native PyQt5 settings panel...")
        panel = ThemePanel(
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
        overlay.panel = panel
        panel.show()

        def on_about_to_quit():
            try:
                if panel is not None:
                    panel.shutdown()
            except Exception:
                logging.exception("Error shutting down settings panel")
            logging.info("=== KeyStroke exiting normally ===")

        app.aboutToQuit.connect(on_about_to_quit)
        sys.exit(app.exec_())

    except SystemExit:
        raise
    except Exception as e:
        logging.exception("Fatal error during startup")
        try:
            QMessageBox.critical(
                None, "KeyStroke failed to start",
                f"{type(e).__name__}: {e}\n\nSee {LOG_PATH} for full details."
            )
        except Exception:
            pass
        sys.exit(1)