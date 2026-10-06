#!/usr/bin/env python3
"""watch: block until a game event should wake the companion agent, print the events, exit.

  watch.py              wait up to MAX_WAIT_SECONDS (agents with background tasks, e.g. Claude Code)
  watch.py <seconds>    wait at most this long (agents that must run it in the foreground)

The agent replies after it exits and starts it again. The deterministic rules live here (which
events wake, cooldowns, batching, mute), so the model only runs when there is something worth saying.

Output: one JSON event per line (waking events carry "wake": true), then `WAKE <n>` or `TIMEOUT`.
"""
import json, os, sys, time
from common import GAME, HOME, bridge

# ===== CONFIG =====
STATE_FILE = HOME / f"watch-{GAME}.json"  # file offset + last wake per type
WAKE_COOLDOWN = {  # event type -> seconds between wakes; types not listed never wake (they still show up as context)
    "ask": 0, "loaded": 0, "party_join": 0,
    "fight_start": 30, "danger": 20, "quest_new": 15, "quest_end": 15, "map": 120,
}
ALWAYS = {"ask"}          # still wake while muted (F9)
BATCH_SECONDS = 2.5       # after the first waking event, keep collecting this long
POLL_SECONDS = 0.5
MAX_WAIT_SECONDS = 6600   # give up with TIMEOUT before a 2 h background-task limit
MAX_CONTEXT = 20          # at most this many events printed per wake
# ==================

BRIDGE = bridge()
EVENTS = os.path.join(BRIDGE, "events.jsonl")


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(st):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(st, f)


def main():
    max_wait = float(sys.argv[1]) if len(sys.argv) > 1 else MAX_WAIT_SECONDS
    st = load_state()
    size = os.path.getsize(EVENTS) if os.path.exists(EVENTS) else 0
    offset = st.get("offset")
    if offset is None or offset > size:  # first run, or the file was reset: skip history
        offset = size
    last = st.get("last", {})
    start, deadline, got, buf = time.time(), None, [], b""

    while True:
        if os.path.exists(EVENTS) and os.path.getsize(EVENTS) > offset:
            with open(EVENTS, "rb") as f:
                f.seek(offset)
                buf += f.read()
            nl = buf.rfind(b"\n")
            if nl >= 0:
                chunk, buf = buf[:nl + 1], buf[nl + 1:]
                offset += len(chunk)
                muted = os.path.exists(os.path.join(BRIDGE, "mute"))
                for line in chunk.decode("utf-8", "replace").splitlines():
                    try:
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    t = ev.get("type")
                    now = time.time()
                    if (t in WAKE_COOLDOWN and (not muted or t in ALWAYS)
                            and now - last.get(t, 0) >= WAKE_COOLDOWN[t]):
                        ev["wake"] = True
                        last[t] = now
                        deadline = deadline or now + BATCH_SECONDS
                    got.append(ev)
        if deadline and time.time() >= deadline:
            break
        if time.time() - start > max_wait:
            save_state({"offset": offset, "last": last})
            print("TIMEOUT")
            return
        time.sleep(POLL_SECONDS)

    save_state({"offset": offset, "last": last})
    for ev in got[-MAX_CONTEXT:]:
        print(json.dumps(ev, ensure_ascii=False))
    print(f"WAKE {sum(1 for e in got if e.get('wake'))}")


if __name__ == "__main__":
    sys.exit(main())
