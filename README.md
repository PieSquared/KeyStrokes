# KeyStrokes

**KeyStrokes** is a highly customizable, lightweight keystrokes overlay written in Python. It is designed for games with no modding capabilities unlike Minecraft, displaying your keyboard and mouse inputs in real time with alot of customization.

> **Note**
> This project is currently written in Python. A standalone compiled release is planned for the future.

---

# Features


## Customization
- Multiple manager
- Theme maker
- Adjustable overlay scaling
- Show or hide individual overlay elements
- Theme editor 
- Import custom fonts
- Settings `ARE` saved

## Theme System
- Import `.ks` theme packages
- Export your own `.ks` themes
- Create fully custom themes within the UI

---

# Planned Features

- Standalone compiled application (Barely any setup)
- Installers maybe

---

# Installation

## 1. Clone the repository

```bash
git clone https://github.com/PieSquared/KeyStrokes.git
cd KeyStrokes
```

## 2. Install Python

Download Python from:

https://www.python.org/downloads/

> Make sure **"Add Python to PATH"** is checked during installation or it wont work.

---

## 3. Run the app

### Windows

Run:

```text
run.bat
```

### Linux / macOS

Run:

```bash
chmod +x pkgs.sh
./run.sh
```

The script will:

- Create a virtual environment 
- Install all required packages
- Launch `KeyStrokes`
- Not break your PC

---

# Themes (for people who wanna make some)

Themes are stored inside the `themes/` directory.

Each theme can define:

- Colors
- Fonts
- Sizes
- Shadows
- Glow
- Border radius
- Layout settings

Themes can either be made by hand with a .json file and font.ttf file (refer to the default theme)

or

Be made fully in the UI and packed as a .ks file in the Advanced options

Themes are packaged as a `.ks` file which is simple just a `.zip` file renamed


---


# AI USE

This project uses AI for things such as bug fixing and organization.