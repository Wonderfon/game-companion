# 逸剑风云决 (Wandering Sword) 适配器

UE 4.26 单机游戏，Steam appid 1876890。状态桥是一个 UE4SS Lua mod（WsCompanion），查询用的数据表从玩家本机的游戏文件里提取。
游戏目录会在所有 Steam 库里自动查找，找不到时在 `scripts/common.py` 的 CONFIG 里填 `GAME_DIR`。

## 安装（玩家本机，Windows）

1. 征得玩家同意，请玩家正常退出游戏。
2. `python install.py`：备份存档到 `~/.cache/game-companion/wandering-sword/save-backups/`；没有 UE4SS 时从 RE-UE4SS 的 experimental-latest 发布页下载（会核对 SHA-256），解压到 `Binaries\Win64`；把 `mod/WsCompanion` 复制到 `ue4ss\Mods\` 并启用。
   如果 `Binaries\Win64` 里已经有别的 `dwmapi.dll`，脚本会停下来，不覆盖。
3. `python extract_tables.py`：下载 repak（固定版本 v0.2.3，核对 SHA-256），从游戏 pak 里解出 `JH/Tables`，转成 `~/.cache/game-companion/wandering-sword/tables/*.json`。大约 10 秒。游戏更新后重跑一次。
4. 启动游戏、读档，按 F8 试一下。

卸载：删掉 `ue4ss\Mods\WsCompanion`。连 UE4SS 一起删：删掉 `Binaries\Win64\dwmapi.dll` 和 `Binaries\Win64\ue4ss\`。

## 桥接目录

`<游戏目录>\Wandering_Sword\Binaries\Win64\ue4ss\Mods\WsCompanion\`

| 文件 | 谁写 | 内容 |
|---|---|---|
| `state.json` | mod，每 2 秒一次 | `map`（关卡名）、`party`（全部同伴；`lineup=true` 表示在出战阵容里）、`money`、`quests`（只含可见任务，带 `id/name/owner/step`）、`bag`（`[物品id, 数量]`）、`fighting`、`fight`（战斗中双方单位，`ally` 区分敌我） |
| `events.jsonl` | mod | `loaded`、`map`、`fight_start`（带 `foes`）、`fight_end`、`danger`、`quest_new`、`quest_end`（带 `step`：4=完成，2=失败）、`party_join`、`ask`、`mute` |
| `reply.txt` | agent（`scripts/say.py`） | 第 1 行是回复 id，其余每行在游戏里显示成一条消息 |
| `ask.txt` | 任何人 | 相当于按 F8，用完自动删除 |
| `mute` | mod（F9 开关） | 存在时只回应 F8 |
| `autoload.txt` | 开发用 | 写一个存档槽位号，游戏启动到标题画面后自动读这个档，读完删除 |

游戏内按键：**F8** 问百晓生，**F9** 静音或取消静音主动提醒。

## 已验证（2026-10-06，存档 58，天山之巅）

- 状态读取：出战阵容、气血内力、任务及其父任务、银两、背包都正确；读档事件和换图事件都能触发。
- 游戏内显示：调用 `GlobalMessageModuleVM.ShowMessage`，屏幕中央的提示栏，中文正常。一条大约显示 3 秒，同时发多条会叠在一起，所以 mod 会把消息排队，每 3.5 秒放出一条。从写入 reply.txt 到显示出来大约 3 秒。
- F8 求助链路：mod 写 `ask` 事件，`watch.py` 唤醒 agent，agent 调 `say.py` 回复。整轮大约 20 秒。
- `extract_tables.py` 导出的 46 张表和 UAssetAPI 导出的结果逐字段一致（陪玩用到的 7 张都在其中）；跳过的 15 张是界面字体样式表。
- UE4SS 版本：实机验证的是 v3.0.1-1148。`install.py` 下载的是 experimental-latest 当时的版本，写这份文档时是 1160。

## 未验证 / 已知问题

- `fight` 单位的气血是不是实时值（读的是 `TeamInfo.AttributeSet`），以及 `danger` 事件在真实战斗里能不能触发，都还没在实战中测过。
- 主角的 `Level` 属性读出来是 5，和同伴的 35～65 不在一个量级，含义待查。给建议时别拿它比较强弱。
- `map_name`（游戏自己给的地点名）可能过时，所以 brief 优先用 Maps 表里的名字。
- 物品来源只覆盖商店、敌人掉落和任务奖励，采集、烹饪、炼丹、宝箱还没接进来。
- 退出游戏后，`ue4ss\` 里可能多出一个 0 字节的 `crash_*.dmp`。游戏日志显示游戏已经正常退出（`LogExit: Exiting.`），这是 UE4SS 在进程收尾时留下的，不影响存档。
