#!/usr/bin/env python3
"""install: set up the Wandering Sword companion mod (Windows, or WSL with the game on the Windows side).

  install.py     back up saves, install UE4SS if it is missing, copy the WsCompanion mod and enable it

Run it with the game closed. It writes only to the game's Binaries/Win64 (dwmapi.dll, ue4ss/) and to the
save backup folder. Uninstall: delete ue4ss/Mods/WsCompanion (or dwmapi.dll + ue4ss/ to remove UE4SS too).
"""
import hashlib, io, json, os, re, shutil, subprocess, sys, time, urllib.request, zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
from common import GAME, HOME, game_dir

# ===== CONFIG =====
UE4SS_RELEASE = "https://api.github.com/repos/UE4SS-RE/RE-UE4SS/releases/tags/experimental-latest"
UE4SS_ASSET = r"^UE4SS_v[\d.]+-\d+-g[0-9a-f]+\.zip$"   # tested with UE4SS_v3.0.1-1148
GAME_EXE = "JH-Win64-Shipping.exe"
# ==================

MOD = Path(__file__).resolve().parent / "mod" / "WsCompanion"
WSL = os.name != "nt" and Path("/mnt/c/Windows").is_dir()


def windows(cmd):
    """Run a Windows command (directly, or through WSL interop) and return its output."""
    exe = cmd[0] + ".exe" if WSL else cmd[0]
    return subprocess.run([exe] + cmd[1:], capture_output=True, text=True, errors="replace").stdout.strip()


def local_appdata():
    if os.name == "nt":
        return Path(os.environ["LOCALAPPDATA"])
    if WSL:
        p = windows(["cmd", "/c", "echo %LOCALAPPDATA%"])
        return Path(subprocess.run(["wslpath", "-u", p], capture_output=True, text=True).stdout.strip())
    return None


def backup_saves():
    app = local_appdata()
    saved = app / "Wandering_Sword" / "Saved" if app else None
    folders = sorted(saved.glob("*/SaveGames")) if saved and saved.is_dir() else []
    if not folders:
        print("没找到存档，跳过备份。")
        return
    dest = HOME / GAME / "save-backups" / time.strftime("%Y%m%d-%H%M%S")
    for f in folders:
        shutil.copytree(f, dest / f.parent.name / "SaveGames")
    print(f"存档已备份到 {dest}")


def install_ue4ss(win64):
    if (win64 / "ue4ss" / "UE4SS.dll").exists() and (win64 / "dwmapi.dll").exists():
        print("UE4SS 已安装。")
        return
    if (win64 / "dwmapi.dll").exists():
        sys.exit("Binaries/Win64 里已经有别的 dwmapi.dll（可能是其他 mod 加载器），不覆盖。请手动处理后再运行。")
    release = json.load(urllib.request.urlopen(UE4SS_RELEASE, timeout=60))
    asset = next((a for a in release["assets"] if re.match(UE4SS_ASSET, a["name"])), None)
    if not asset:
        sys.exit("UE4SS 发布页上没找到安装包，请手动安装：https://github.com/UE4SS-RE/RE-UE4SS/releases")
    print(f"下载 {asset['name']}")
    data = urllib.request.urlopen(asset["browser_download_url"], timeout=300).read()
    digest = asset.get("digest") or ""
    if digest.startswith("sha256:") and hashlib.sha256(data).hexdigest() != digest[7:]:
        sys.exit("UE4SS 下载内容的 SHA-256 和发布页不一致，已停止。")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        z.extractall(win64)
    print(f"UE4SS 已安装到 {win64}")


def main():
    if os.name != "nt" and not WSL:
        sys.exit("目前只支持 Windows（或在 WSL 里装 Windows 版游戏）。")
    if GAME_EXE.lower() in windows(["tasklist", "/FI", f"IMAGENAME eq {GAME_EXE}"]).lower():
        sys.exit("游戏正在运行，先正常退出游戏再安装。")
    win64 = game_dir() / "Wandering_Sword" / "Binaries" / "Win64"
    backup_saves()
    install_ue4ss(win64)
    dest = win64 / "ue4ss" / "Mods" / "WsCompanion"
    shutil.rmtree(dest / "Scripts", ignore_errors=True)
    shutil.copytree(MOD, dest, dirs_exist_ok=True)
    (dest / "enabled.txt").touch()
    print(f"WsCompanion 已装到 {dest}")
    print("完成。启动游戏、读档，按 F8 问百晓生。")


if __name__ == "__main__":
    main()
