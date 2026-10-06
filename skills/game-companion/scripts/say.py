#!/usr/bin/env python3
"""say: show a companion reply inside the game through the bridge's reply.txt.

usage: say.py "第一句" ["第二句" ...]   each argument becomes one in-game message; long ones are wrapped.
"""
import os, sys, time
from common import bridge

# ===== CONFIG =====
NAME = "百晓生"
MAX_CHARS = 30   # per in-game message line
MAX_LINES = 4    # more than this and the player stops reading; put the rest in the terminal
# ==================


def wrap(s):
    out = []
    while len(s) > MAX_CHARS:
        cut = max((s.rfind(p, 0, MAX_CHARS) for p in "，。；！？、 "), default=-1)
        cut = cut + 1 if cut >= MAX_CHARS // 2 else MAX_CHARS
        out.append(s[:cut])
        s = s[cut:]
    return out + ([s] if s else [])


def main():
    parts = [p.strip() for p in sys.argv[1:] if p.strip()]
    if not parts:
        print(__doc__)
        return 1
    lines = [l for p in parts for l in wrap(p)]
    if len(lines) > MAX_LINES:
        lines = lines[:MAX_LINES]
        lines[-1] = lines[-1].rstrip("，。；") + "……（详见终端）"
    lines[0] = f"{NAME}：{lines[0]}"
    tmp = bridge() / "reply.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(f"{time.time_ns()}\n" + "\n".join(lines) + "\n")
    os.replace(tmp, tmp.with_name("reply.txt"))
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
