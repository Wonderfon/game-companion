#!/usr/bin/env python3
"""wsq: Wandering Sword lookups for the companion agent. Every answer comes from the game's own tables.

  wsq.py brief            current game state (state.json) resolved into readable Chinese, plus recent events
  wsq.py item  <名字|id>   item info + where to get it (shops, enemy drops, quest rewards)
  wsq.py npc   <名字|id>   NPC info: level, stats, skills, drops, shop, where they walk
  wsq.py quest <名字|id>   quest info: description, who to talk to, requirements, rewards, sub-steps
  wsq.py find  <文字>      search names across items / NPCs / quests / skills / maps
"""
import json, os, re, sys, time
from functools import lru_cache
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))
from common import DATA_DIR, bridge

# ===== CONFIG =====
RECENT_EVENTS = 8
MAX_HITS = 6
# ==================

STEP = {0: "无", 1: "进行中", 2: "失败", 3: "未接", 4: "已完成"}
QUALITY = {"White": "白", "Green": "绿", "Blue": "蓝", "Purple": "紫", "Orange": "橙", "Red": "红", "DarkGold": "暗金", "Gold": "金"}


@lru_cache(None)
def T(name):
    try:
        with open(os.path.join(DATA_DIR, name + ".json"), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        sys.exit(f"没有数据表 {DATA_DIR}/{name}.json：先运行 extract_tables.py。")


def clean(s):
    return re.sub(r"<[^>]*>", "", s).strip() if s else ""


def enum(s):
    return s.split("::")[-1] if isinstance(s, str) else s


def item_name(i):
    r = T("Items").get(str(i))
    return clean(r["Name"]) if r and r.get("Name") else f"物品{i}"


def npc_name(i):
    r = T("NPCs").get(str(i))
    return clean(r["Name"]) if r and r.get("Name") else f"NPC{i}"


def quest_name(i):
    r = T("Quests").get(str(i))
    return clean(r["Name"]) if r and r.get("Name") else f"任务{i}"


def skill_name(i):
    r = T("Skills").get(str(i))
    return clean(r.get("ViewName")) if r and r.get("ViewName") else f"技能{i}"


@lru_cache(None)
def map_names():
    return {r["MapName"]: clean(r.get("ViewName")) or r["MapName"] for r in T("Maps").values()}


def map_view(level):
    return map_names().get(level, level) if level else "?"


def place(level, game_name):
    """Maps table name for the loaded level; the game's own location name is only a fallback (it can be stale)."""
    return map_names().get(level) or game_name or level or "?"


def req_text(r):
    t, i, n = enum(r["Type"]), r.get("Id", 0), r.get("Num", 0)
    n = int(n) if n == int(n) else n
    return {
        "PreQuest": lambda: f"先完成「{quest_name(i)}」",
        "NoQuest": lambda: f"未接「{quest_name(i)}」",
        "Item": lambda: f"持有 {item_name(i)}×{n}",
        "ItemMax": lambda: f"{item_name(i)} 不超过 {n}",
        "Money": lambda: f"银两≥{n}",
        "TeamMember": lambda: f"{npc_name(i)} 在队伍中",
        "Friendliness": lambda: f"与 {npc_name(i)} 好感≥{n}",
        "FriendlinessUp": lambda: f"与 {npc_name(i)} 好感提升 {n}",
        "KillMonster": lambda: f"击败 {npc_name(i)}×{n}",
        "KillMonsterAggre": lambda: f"击败「{clean(T('NPCAggregation').get(str(i), {}).get('GroupName')) or i}」×{n}",
        "HasQuest": lambda: f"已接「{quest_name(i)}」",
    }.get(t, lambda: f"{t}({i},{n})")()


def act_text(a):
    t, i, n = enum(a["Type"]), a.get("Id", 0), a.get("Num", 0)
    n = int(n) if n == int(n) else n
    return {
        "CItem": lambda: f"{'获得' if n > 0 else '失去'} {item_name(i)}×{abs(n)}",
        "CMoney": lambda: f"银两 {'+' if n > 0 else ''}{n}",
        "ATeam": lambda: f"{npc_name(i)} 入队",
        "RTeam": lambda: f"{npc_name(i)} 离队",
        "ASExp": lambda: f"武学经验 +{n}",
        "CGuildHonor": lambda: f"门派声望 {i} {'+' if n > 0 else ''}{n}",
        "ARandItem": lambda: f"随机物品(池{i})×{n}",
        "AJingMaiPoint": lambda: f"经脉点 +{n}",
    }.get(t, lambda: None)()


def acts(lst):
    return [x for x in (act_text(a) for a in lst or []) if x]


# ---------- lookups ----------
def find_rows(table, q, name_key):
    rows = T(table)
    if q.isdigit() and q in rows:
        return [rows[q]]
    hits = [r for r in rows.values() if r.get(name_key) and q in clean(r[name_key])]
    hits.sort(key=lambda r: (clean(r[name_key]) != q, len(clean(r[name_key]))))
    return hits


@lru_cache(None)
def item_sources():
    src = {}
    add = lambda i, s: src.setdefault(i, []).append(s) if s not in src.get(i, []) else None
    pools = T("DropPools")
    for n in T("NPCs").values():
        nm = clean(n.get("Name")) or f"NPC{n['Id']}"
        for i in n.get("SellItems") or []:
            add(i, f"商店：{nm}")
        for d in n.get("DropItems") or []:
            add(d["Id"], f"掉落：{nm}（{d.get('Value', 0):g}%）")
        for p in n.get("DropPools") or []:
            for w in pools.get(str(p["DropPoolId"]), {}).get("DropWeights", []):
                add(w["ItemDefId"], f"掉落池：{nm}")
    for q in T("Quests").values():
        for k, v in q.items():
            if isinstance(v, list) and "Action" in k:
                for a in v:
                    if isinstance(a, dict) and enum(a.get("Type")) == "CItem" and a.get("Num", 0) > 0:
                        add(a["Id"], f"任务奖励：{clean(q.get('Name')) or quest_name(q['QuestId'])}")
    return src


def cmd_item(q):
    hits = find_rows("Items", q, "Name")
    for r in hits[:MAX_HITS]:
        print(f"■ {clean(r['Name'])}（id {r['Id']}）{enum(r['ItemType'])} / {QUALITY.get(enum(r['Quality']), enum(r['Quality']))}品"
              f" / 买 {r['BuyPrice']:g} 卖 {r['SellPrice']:g}")
        if r.get("Description"):
            print("  " + clean(r["Description"]))
        eff = acts(r.get("Actions"))
        if eff:
            print("  效果：" + "；".join(eff))
        src = item_sources().get(r["Id"], [])
        print("  来源：" + ("；".join(src[:12]) + (f" …共{len(src)}处" if len(src) > 12 else "") if src else "表里没查到（可能来自采集/烹饪/炼丹/宝箱/剧情）"))
    if len(hits) > MAX_HITS:
        print(f"…另有 {len(hits) - MAX_HITS} 个同名/相似物品")
    if not hits:
        print("没找到")


def npc_where(n):
    places = set()
    if n.get("WalkLevelName"):
        places.add(map_view(n["WalkLevelName"]))
    for q in T("Quests").values():
        for k in ("RequestNPCLocation", "FinishNPCLocation"):
            for loc in q.get(k) or []:
                if loc.get("NPCId") == n["Id"] and loc.get("MapName"):
                    places.add(map_view(loc["MapName"]))
    return sorted(places)


def cmd_npc(q):
    hits = find_rows("NPCs", q, "Name")
    for n in hits[:MAX_HITS]:
        print(f"■ {clean(n['Name'])}（id {n['Id']}）Lv{n.get('Level', 0):g} 气血{n.get('BaseHp', 0):g} 攻{n.get('BaseAttackPower', 0):g}"
              f" 防{n.get('BaseDefense', 0):g} 闪{n.get('BaseDodge', 0):g} 速{n.get('BaseTurnRate', 0):g}")
        if n.get("Description"):
            print("  " + clean(n["Description"]))
        sk = [f"{skill_name(s['Id'])}{s.get('Value', 0):g}级" for s in n.get("SkillList") or []]
        if sk:
            print("  武学：" + "、".join(sk))
        drops = [f"{item_name(d['Id'])}({d.get('Value', 0):g}%)" for d in n.get("DropItems") or []]
        if n.get("DropPools"):
            drops.append(f"另有 {len(n['DropPools'])} 个随机掉落池")
        if drops:
            print("  掉落：" + "、".join(drops))
        if n.get("SellItems"):
            print("  出售：" + "、".join(item_name(i) for i in n["SellItems"][:20]))
        w = npc_where(n)
        if w:
            print("  出没：" + "、".join(w))
    if len(hits) > MAX_HITS:
        print(f"…另有 {len(hits) - MAX_HITS} 个同名/相似 NPC（同名的往往是不同难度或剧情阶段的版本）")
    if not hits:
        print("没找到")


def quest_detail(r, indent="  "):
    out = []
    if r.get("Descript"):
        out.append(indent + clean(r["Descript"]))
    for k, label in (("RequestNPCIds", "接取"), ("FinishNPCIds", "交付")):
        if r.get(k):
            out.append(indent + f"{label}：" + "、".join(npc_name(i) for i in r[k]))
    locs = {(loc["NPCId"], loc.get("MapName")) for k in ("RequestNPCLocation", "FinishNPCLocation") for loc in r.get(k) or []}
    if locs:
        out.append(indent + "地点：" + "；".join(f"{npc_name(i)}@{map_view(m)}" for i, m in sorted(locs)))
    reqs = [req_text(x) for x in r.get("FinishingRequirements") or []]
    if reqs:
        out.append(indent + "完成条件：" + "；".join(reqs))
    rew = acts(r.get("FinishedActions"))
    if rew:
        out.append(indent + "奖励：" + "；".join(rew))
    return out


def children(qid):
    return [r for r in T("Quests").values() if r.get("OwnerQuestId") == qid and r.get("bIsShow")]


def cmd_quest(q):
    hits = [r for r in find_rows("Quests", q, "Name") if r.get("bIsShow") or q.isdigit()]
    for r in hits[:MAX_HITS]:
        owner = f"（属于「{quest_name(r['OwnerQuestId'])}」）" if r.get("OwnerQuestId") else ""
        print(f"■ {clean(r.get('Name')) or '(无名)'}（id {r['QuestId']}）{enum(r.get('ClassFlag'))}{owner}")
        print("\n".join(quest_detail(r)))
        ch = children(r["QuestId"])
        if ch:
            print("  步骤：" + " → ".join(clean(c["Name"]) for c in ch[:15]) + (" …" if len(ch) > 15 else ""))
    if not hits:
        print("没找到")


def cmd_find(q):
    for table, key, label in (("Items", "Name", "物品"), ("NPCs", "Name", "NPC"), ("Quests", "Name", "任务"),
                              ("Skills", "ViewName", "武学"), ("Maps", "ViewName", "地图")):
        rows = T(table)
        hits = [(k, clean(r[key])) for k, r in rows.items() if r.get(key) and q in clean(r[key])]
        if hits:
            print(f"{label}：" + "、".join(f"{n}({k})" for k, n in hits[:15]) + (f" …共{len(hits)}个" if len(hits) > 15 else ""))


# ---------- brief ----------
def read_state(mod):
    for _ in range(5):  # the mod may be mid-write
        try:
            with open(os.path.join(mod, "state.json"), encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            time.sleep(0.3)
    return None


def bar(u):
    s = f"{u.get('name') or npc_name(u['id'])} Lv{u.get('lv', '?')}"
    if u.get("hpmax"):
        s += f" 气血{u.get('hp')}/{u['hpmax']}"
    if u.get("mpmax"):
        s += f" 内力{u.get('mp')}/{u['mpmax']}"
    return s


def cmd_brief():
    mod = bridge()
    s = read_state(mod)
    if not s:
        print("没有 state.json：游戏没开、mod 没装，或者还停在标题画面。")
        return
    age = int(time.time() - s.get("t", 0))
    muted = os.path.exists(os.path.join(mod, "mute"))
    print(f"[状态] {age} 秒前更新｜地图：{place(s.get('map'), s.get('map_name'))}（{s.get('map')}）｜银两 {s.get('money')}"
          f"｜{'战斗中' if s.get('fighting') else '非战斗'}｜主动提醒：{'关（F9 已静音）' if muted else '开'}")
    if age > 30:
        print("[注意] 状态超过 30 秒没更新：游戏可能已经关了、停在标题画面，或者正在读档。下面是最后一次的状态。")
    party = s.get("party", [])
    lineup = [u for u in party if u.get("lineup")] or party[:1]
    print("[出战] " + "；".join(bar(u) for u in lineup))
    rest = [u.get("name") or npc_name(u["id"]) for u in party if u not in lineup]
    if rest:
        print(f"[其他同伴 {len(rest)} 人] " + "、".join(rest))

    if s.get("fighting") and s.get("fight"):
        print("[战斗]")
        for u in s["fight"]:
            tag = "我方" if u.get("ally") else "敌方"
            line = f"  {tag} {bar(u)}"
            if not u.get("ally"):
                n = T("NPCs").get(str(u["id"]))
                if n:
                    sk = [skill_name(x["Id"]) for x in n.get("SkillList") or []]
                    if sk:
                        line += "｜武学：" + "、".join(sk[:6])
                    drops = [item_name(d["Id"]) for d in n.get("DropItems") or []]
                    if drops:
                        line += "｜掉落：" + "、".join(drops[:6])
            print(line)

    quests = s.get("quests", [])
    active = {q["id"] for q in quests}
    roots = {}
    for q in quests:
        r = T("Quests").get(str(q["id"]))
        root = q["id"]
        while r and r.get("OwnerQuestId") and str(r["OwnerQuestId"]) in T("Quests"):
            root = r["OwnerQuestId"]
            r = T("Quests")[str(root)]
        roots.setdefault(root, []).append(q["id"])
    print(f"[任务] 进行中 {len(quests)} 条")
    for root, qids in sorted(roots.items(), key=lambda kv: (enum(T("Quests").get(str(kv[0]), {}).get("ClassFlag")) != "Primary", kv[0])):
        rr = T("Quests").get(str(root), {})
        print(f"  ◆ {quest_name(root)}" + ("" if root in active else "（总任务）"))
        if rr.get("Descript"):
            print("    " + clean(rr["Descript"]))
        for qid in qids:
            if qid == root:
                continue
            r = T("Quests").get(str(qid), {})
            print(f"    · 当前：{quest_name(qid)}")
            print("\n".join(quest_detail(r, indent="      ")))

    bag = s.get("bag", [])
    print(f"[背包] {len(bag)} 种物品（问具体物品时用 item 查）")

    ev_path = os.path.join(mod, "events.jsonl")
    if os.path.exists(ev_path):
        with open(ev_path, encoding="utf-8") as f:
            lines = f.readlines()[-RECENT_EVENTS:]
        print("[最近事件] " + "；".join(ev_text(json.loads(l)) for l in lines if l.strip()))


def ev_text(e):
    t = e.get("type")
    when = time.strftime("%H:%M", time.localtime(e.get("t", 0)))
    body = {
        "loaded": lambda: f"读档 @{place(e.get('map'), e.get('map_name'))}",
        "map": lambda: f"进入 {place(e.get('to'), e.get('map_name'))}",
        "fight_start": lambda: "开战：" + "、".join(f.get("name") or npc_name(f["id"]) for f in e.get("foes", [])),
        "fight_end": lambda: "战斗结束",
        "danger": lambda: f"{e.get('name')} 气血危险 {e.get('hp')}/{e.get('hpmax')}",
        "quest_new": lambda: f"新任务「{clean(e.get('name')) or quest_name(e['id'])}」",
        "quest_end": lambda: f"任务「{clean(e.get('name')) or quest_name(e['id'])}」{STEP.get(e.get('step'), '结束')}",
        "party_join": lambda: f"{e.get('name')} 入队",
        "ask": lambda: "玩家按了 F8 求助",
        "mute": lambda: "静音" if e.get("on") else "取消静音",
    }.get(t, lambda: t)()
    return f"{when} {body}"


if __name__ == "__main__":
    cmds = {"brief": cmd_brief, "item": cmd_item, "npc": cmd_npc, "quest": cmd_quest, "find": cmd_find}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        print(__doc__)
        sys.exit(1)
    if sys.argv[1] == "brief":
        cmd_brief()
    else:
        cmds[sys.argv[1]](" ".join(sys.argv[2:]).strip())
