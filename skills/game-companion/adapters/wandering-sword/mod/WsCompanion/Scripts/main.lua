-- WsCompanion: game-state bridge between Wandering Sword and an AI companion agent (Claude Code / Codex).
-- All files live in this mod folder (paths are relative to Binaries/Win64):
--   state.json    rewritten every POLL_MS while a save is loaded (party, map, money, quests, bag, fight units)
--   events.jsonl  one JSON object per line: loaded, map, fight_start, fight_end, danger, quest_new, quest_end,
--                 party_join, ask, mute
--   reply.txt     written by the agent: line 1 = reply id, every further line is shown in-game as a message
--   ask.txt       same as pressing F8 (lets the agent/tests trigger an ask); deleted after use
--   mute          present = companion only speaks when asked (toggled with F9)
--   autoload.txt  dev only: a save slot number, loaded once from the title screen
local DIR = "ue4ss/Mods/WsCompanion/"
local POLL_MS = 2000
local NAME = "百晓生"

local function log(msg) print(string.format("[WsCompanion] %s\n", msg)) end

-- JSON encoder (A{} marks arrays so empty lists stay [])
local ARR = {}
local function A(t) return setmetatable(t or {}, ARR) end
local ESC = { ['"'] = '\\"', ['\\'] = '\\\\', ['\n'] = '\\n', ['\r'] = '\\r', ['\t'] = '\\t' }
local function enc(v)
    local t = type(v)
    if t == "table" then
        local out = {}
        if getmetatable(v) == ARR then
            for i = 1, #v do out[i] = enc(v[i]) end
            return "[" .. table.concat(out, ",") .. "]"
        end
        for k, x in pairs(v) do out[#out + 1] = enc(tostring(k)) .. ":" .. enc(x) end
        return "{" .. table.concat(out, ",") .. "}"
    elseif t == "string" then
        return '"' .. v:gsub('[%c"\\]', function(c) return ESC[c] or string.format("\\u%04x", c:byte()) end) .. '"'
    elseif t == "number" then
        if v ~= v or v == math.huge or v == -math.huge then return "null" end
        if math.type(v) == "integer" then return tostring(v) end
        return string.format("%.6g", v)
    elseif t == "boolean" then
        return tostring(v)
    end
    return "null"
end

local function readAll(p) local f = io.open(p, "rb"); if not f then return nil end; local s = f:read("a"); f:close(); return s end
local function writeAll(p, s) local f = io.open(p, "wb"); if f then f:write(s); f:close() end end
local function exists(p) local f = io.open(p, "rb"); if f then f:close(); return true end; return false end

local seq = 0
local function emit(ev)
    seq = seq + 1
    ev.t = os.time(); ev.seq = seq
    local f = io.open(DIR .. "events.jsonl", "ab")
    if f then f:write(enc(ev), "\n"); f:close() end
    log("event " .. ev.type)
end

-- game access ----------------------------------------------------------------------------------
local MFL, NFL, QFL
local function try(f) local ok, v = pcall(f); if ok then return v end end
local function valid(o) return o ~= nil and try(function() return o:IsValid() end) == true end
local function str(x) return try(function() return x:ToString() end) end
local function libs()
    local function cdo(p) local o = StaticFindObject(p); if valid(o) then return o end end
    MFL = MFL or cdo("/Script/JH.Default__ManagerFuncLib")
    NFL = NFL or cdo("/Script/JH.Default__NPCFuncLib")
    QFL = QFL or cdo("/Script/JH.Default__QuestFuncLib")
    return MFL and NFL and QFL
end

local function attr(set, name)
    local v = try(function() return set[name].CurrentValue end)
    if type(v) == "number" then return math.floor(v + 0.5) end
end
local function unit(info)
    local u = { id = info.NPCId }
    u.name = str(NFL:GetNPCNameById(u.id))
    local set = info.AttributeSet
    if valid(set) then
        u.lv = attr(set, "Level"); u.hp = attr(set, "Health"); u.hpmax = attr(set, "MaxHealth")
        u.mp = attr(set, "Mana"); u.mpmax = attr(set, "MaxMana")
    end
    return u
end

local function snapshot()
    if not libs() then return nil end
    local tm = MFL:GetTeamManager()
    if not valid(tm) then return nil end
    local s = { party = A(), quests = A(), bag = A() }
    local lineup, seen = {}, {}
    tm.FightTeamInfos:ForEach(function(_, e)
        local info = e:get()
        if valid(info) then lineup[info.NPCId] = true end
    end)
    tm.TeamInfos:ForEach(function(_, e)
        local info = e:get()
        if valid(info) and not seen[info.NPCId] then
            seen[info.NPCId] = true
            local u = unit(info)
            u.lineup = lineup[u.id] == true -- in the battle formation
            s.party[#s.party + 1] = u
        end
    end)
    if #s.party == 0 then return nil end -- title screen: no save loaded
    local world = try(function() return MFL:GetCurrentWorld() end)
    s.map = valid(world) and str(world:GetFName()) or nil
    if s.map == "LV_NewGame" then return nil end -- title map while a save is still loading
    s.map_name = str(NFL:GetNPCLocationMapName(0)) -- unreliable (showed 游仙岛 on 天山之巅); prefer Maps table
    s.fighting = try(function() return MFL:IsFighting() end) == true

    local im = MFL:GetItemManager()
    if valid(im) then
        s.money = try(function() return im:GetMoney() end)
        local bag = {}
        im.BackpackItems:ForEach(function(_, e)
            local it = e:get()
            if valid(it) then bag[it.ItemDefId] = (bag[it.ItemDefId] or 0) + it.Num end
        end)
        for id, n in pairs(bag) do s.bag[#s.bag + 1] = A({ id, n }) end
    end

    local qm = MFL:GetQuestManager()
    if valid(qm) then
        qm.QuestProcesses:ForEach(function(k, v)
            local spec = v:get()
            local def = spec.Def
            if valid(def) and not def.bIsShow then return end -- hidden bookkeeping quests
            local q = { id = k:get(), step = spec.Step }
            if valid(def) then q.name = str(def.QuestName); q.owner = def.OwnerQuestId end
            s.quests[#s.quests + 1] = q
        end)
    end

    if s.fighting then
        local ally = {}
        for _, u in ipairs(s.party) do ally[u.id] = true end
        s.fight = A()
        for _, p in ipairs(FindAllOf("FightNPC") or {}) do
            local info = valid(p) and p.TeamInfo
            if valid(info) then
                local u = unit(info)
                u.ally = ally[u.id] == true
                s.fight[#s.fight + 1] = u
            end
        end
    end
    return s
end

-- event detection (deterministic; the watcher decides which events wake the agent) --------------
local prev, fightAnnounced, warned = nil, false, {}
local function ids(list) local t = {}; for _, x in ipairs(list) do t[x.id] = x end; return t end
local function diff(s)
    if not prev then
        emit({ type = "loaded", map = s.map, map_name = s.map_name })
        prev = s; return
    end
    if s.map ~= prev.map then emit({ type = "map", from = prev.map, to = s.map, map_name = s.map_name }) end

    if s.fighting and not fightAnnounced and s.fight and #s.fight > 0 then
        fightAnnounced, warned = true, {}
        local foes = A()
        for _, u in ipairs(s.fight) do if not u.ally then foes[#foes + 1] = u end end
        emit({ type = "fight_start", foes = foes })
    end
    if s.fighting and s.fight then
        for _, u in ipairs(s.fight) do
            if u.ally and u.hpmax and u.hpmax > 0 and u.hp and u.hp > 0 and u.hp / u.hpmax < 0.3 and not warned[u.id] then
                warned[u.id] = true
                emit({ type = "danger", id = u.id, name = u.name, hp = u.hp, hpmax = u.hpmax })
            end
        end
    end
    if not s.fighting and prev.fighting then
        fightAnnounced = false
        emit({ type = "fight_end" })
    end

    local oldP, newP = ids(prev.party), ids(s.party)
    for id, u in pairs(newP) do if not oldP[id] then emit({ type = "party_join", id = id, name = u.name }) end end

    local oldQ, newQ = ids(prev.quests), ids(s.quests)
    local changes = A()
    for id, q in pairs(newQ) do if not oldQ[id] then changes[#changes + 1] = { type = "quest_new", id = id, name = q.name } end end
    for id, q in pairs(oldQ) do
        if not newQ[id] then
            changes[#changes + 1] = { type = "quest_end", id = id, name = q.name, step = try(function() return QFL:GetQuestStep(id) end) }
        end
    end
    if #changes > 8 then
        emit({ type = "loaded", map = s.map, map_name = s.map_name }) -- another save was loaded
    else
        for _, ev in ipairs(changes) do emit(ev) end
    end
    prev = s
end

-- in-game output ---------------------------------------------------------------------------------
-- The game's global message bar shows one line for ~3 s and overlaps concurrent lines, so lines are
-- queued and released one per GAP_TICKS of the 500 ms loop below.
local GAP_TICKS = 7
local queue, wait = {}, 0
local function show(lines) for _, l in ipairs(lines) do queue[#queue + 1] = l end end
local function showNow(l)
    local sub = FindFirstOf("JHNeoUISubsystem")
    local vm = valid(sub) and try(function() return sub:Debug_GetGlobalMsgModule() end)
    if not valid(vm) then log("global message module not available"); return end
    vm:ShowMessage(FText(l))
end

local lastReply = readAll(DIR .. "reply.txt") -- don't replay an old reply after a restart
local function showReply(r)
    local lines, first = {}, true
    for l in r:gmatch("[^\r\n]+") do
        if first then first = false elseif l:match("%S") then lines[#lines + 1] = l end
    end
    if #lines > 0 then show(lines); log("reply shown (" .. #lines .. " lines)") end
end

local function writeState(s) s.t = os.time(); writeAll(DIR .. "state.json", enc(s)) end

local function ask(source)
    local s = try(snapshot)
    if s then writeState(s) end
    emit({ type = "ask", source = source })
    show({ NAME .. "：容我想想……" })
end

-- loops & keys ------------------------------------------------------------------------------------
local errLogged = false
LoopAsync(POLL_MS, function()
    ExecuteInGameThread(function()
        local ok, s = pcall(snapshot)
        if not ok then
            if not errLogged then log("snapshot error: " .. tostring(s)); errLogged = true end
            return
        end
        if s then writeState(s); diff(s) end
    end)
    return false
end)

LoopAsync(500, function()
    local r = readAll(DIR .. "reply.txt")
    local wantAsk = exists(DIR .. "ask.txt")
    if wantAsk then os.remove(DIR .. "ask.txt") end
    if (r and r ~= lastReply) or wantAsk then
        if r and r ~= lastReply then lastReply = r else r = nil end
        ExecuteInGameThread(function()
            if wantAsk then ask("file") end
            if r then showReply(r) end
        end)
    end
    if wait > 0 then
        wait = wait - 1
    elseif #queue > 0 then
        local l = table.remove(queue, 1)
        wait = GAP_TICKS
        ExecuteInGameThread(function() showNow(l) end)
    end
    return false
end)

RegisterKeyBind(Key.F8, function() ExecuteInGameThread(function() ask("F8") end) end)

RegisterKeyBind(Key.F9, function()
    ExecuteInGameThread(function()
        local muted = exists(DIR .. "mute")
        if muted then os.remove(DIR .. "mute") else writeAll(DIR .. "mute", "") end
        emit({ type = "mute", on = not muted })
        show({ NAME .. (muted and "：有事我会主动提醒你。" or "：好，我先不吭声，有事按 F8 叫我。") })
    end)
end)

-- dev: load a save slot once from the title screen (autoload.txt contains the slot number)
local autoloadDone = false
RegisterLoadMapPostHook(function()
    if autoloadDone then return end
    autoloadDone = true
    local slot = tonumber((readAll(DIR .. "autoload.txt") or ""):match("%d+") or "")
    if not slot then return end
    os.remove(DIR .. "autoload.txt")
    ExecuteWithDelay(8000, function()
        ExecuteInGameThread(function()
            libs()
            local ok, err = pcall(function() MFL:GetSaveManager():LoadSlot(slot) end)
            log("autoload slot " .. slot .. " -> " .. (ok and "ok" or tostring(err)))
        end)
    end)
end)

log("loaded")
