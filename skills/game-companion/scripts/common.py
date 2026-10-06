"""Paths shared by the companion scripts. Standard library only; runs on Windows, WSL and Linux."""
import os, re, sys
from pathlib import Path

# ===== CONFIG =====
GAME_DIR = ""   # game install folder; empty = look for it in every Steam library
# ==================

GAME = "wandering-sword"
STEAM_FOLDER = "Wandering Sword"
BRIDGE_REL = "Wandering_Sword/Binaries/Win64/ue4ss/Mods/WsCompanion"
HOME = Path.home() / ".cache" / "game-companion"   # notes, watcher state, tools, extracted tables
DATA_DIR = HOME / GAME / "tables"


def _win_path(p):
    """A Windows path from libraryfolders.vdf, usable from this OS (WSL: C:\\x -> /mnt/c/x)."""
    if os.name != "nt" and re.match(r"^[A-Za-z]:[\\/]", p):
        return Path(f"/mnt/{p[0].lower()}") / p[3:].replace("\\", "/")
    return Path(p)


def _steam_roots():
    roots = []
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
                roots.append(Path(winreg.QueryValueEx(k, "SteamPath")[0]))
        except OSError:
            pass
        roots.append(Path(r"C:\Program Files (x86)\Steam"))
    else:
        roots += [Path("/mnt/c/Program Files (x86)/Steam"), Path.home() / ".steam/steam", Path.home() / ".local/share/Steam"]
    return [r for r in roots if r.is_dir()]


def find_game():
    if GAME_DIR:
        return Path(GAME_DIR)
    libs = []
    for root in _steam_roots():
        libs.append(root)
        vdf = root / "steamapps" / "libraryfolders.vdf"
        if vdf.exists():
            text = vdf.read_text(encoding="utf-8", errors="replace")
            libs += [_win_path(m.replace("\\\\", "\\")) for m in re.findall(r'"path"\s+"([^"]+)"', text)]
    for lib in libs:
        g = lib / "steamapps" / "common" / STEAM_FOLDER
        if g.is_dir():
            return g
    return None


def game_dir():
    g = find_game()
    if not g:
        sys.exit(f"找不到游戏目录（{STEAM_FOLDER}）。在 scripts/common.py 的 CONFIG 里填 GAME_DIR。")
    return g


def bridge():
    return game_dir() / BRIDGE_REL
