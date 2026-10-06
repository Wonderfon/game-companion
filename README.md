# game-companion

**让你的 Codex / Claude Code / WorkBuddy 变成陪你玩游戏的朋友。**
**Turn your Codex / Claude Code / WorkBuddy into a friend who plays games with you.**

[中文](#中文) · [English](#english)

---

## 中文

你玩单机游戏，它就坐在旁边：知道你在哪张地图、队伍还剩多少血、任务卡在哪一步。
按 **F8** 问它，它直接在游戏画面里回你一句。读档、开战、接任务的时候，它也会主动提醒。
它说的每件事都来自游戏自己的数据表，查不到就直说，不会乱编攻略。

目前支持：**逸剑风云决（Wandering Sword）**，Windows + Steam。

### 安装

**Claude Code**
```
/plugin marketplace add Wonderfon/game-companion
/plugin install game-companion@game-companion
```

**Codex**
```
codex plugin marketplace add Wonderfon/game-companion
codex plugin add game-companion@game-companion
```

**WorkBuddy**（以及其他支持 `SKILL.md` 的 agent）
把仓库里的 `skills/game-companion` 文件夹复制到 `~/.workbuddy/skills/`（Windows：`%USERPROFILE%\.workbuddy\skills\`）。

还需要 Python 3（只用标准库，不用 pip 装任何东西）和 git（Claude Code、Codex 靠它下载插件）。

### 开玩

对你的 agent 说：**"陪我玩逸剑风云决"**。

第一次它会请你先退出游戏，然后帮你装好 mod（装之前会自动备份存档），再从你自己的游戏文件里提取数据表。之后在游戏里：

| 按键 | 作用 |
|---|---|
| F8 | 问百晓生 |
| F9 | 让它安静，只在你按 F8 时开口 |

在终端里直接打字问它也可以。想要剧透就说"直接告诉我"。

### 工作原理

- **mod**：每 2 秒导出一次游戏状态，检测读档、开战、任务这些事件，再把回复显示在游戏里。
- **脚本**：负责查数据表，并判断哪些事件值得开口。冷却和合并都是写死的规则。
- **skill**：教 agent 什么时候说话、怎么说、剧透到什么程度。

模型只负责理解你的问题、组织说法，用的是你已有的订阅，不占本机显卡。

### 说明

- 只适配单机游戏，不碰带反作弊的联网游戏。
- 不分发任何游戏数据。数据表是在你本机、从你自己的游戏里提取的。
- 验证情况：Claude Code 已实机试玩；Codex 已验证能装上插件、调用脚本、等待游戏事件；WorkBuddy 按官方文档适配，还没实测。
- 想加别的游戏：参照 `skills/game-companion/adapters/wandering-sword/` 写一个适配器，欢迎 PR。
- 非官方粉丝项目，与游戏开发商、发行商无关。

---

## English

You play a single-player game; it sits next to you. It knows which map you're on, how much HP your party has left, and which quest step you're stuck on.
Press **F8** to ask, and the answer shows up right on the game screen. It also chimes in on its own when you load a save, start a fight, or pick up a quest.
Everything it says comes from the game's own data tables. When it can't find something, it says so instead of making things up.

Currently supported: **Wandering Sword (逸剑风云决)**, Windows + Steam. The companion speaks Chinese in-game by default; chat with it in English and it will answer in English.

### Install

**Claude Code**
```
/plugin marketplace add Wonderfon/game-companion
/plugin install game-companion@game-companion
```

**Codex**
```
codex plugin marketplace add Wonderfon/game-companion
codex plugin add game-companion@game-companion
```

**WorkBuddy** (and other agents that read `SKILL.md`)
Copy the `skills/game-companion` folder into `~/.workbuddy/skills/` (Windows: `%USERPROFILE%\.workbuddy\skills\`).

You also need Python 3 (standard library only, nothing to pip install) and git (Claude Code and Codex use it to fetch the plugin).

### Play

Tell your agent: **"play Wandering Sword with me"**.

The first time, it asks you to quit the game, installs the mod (backing up your saves first), and extracts the data tables from your own copy of the game. Then, in game:

| Key | What it does |
|---|---|
| F8 | Ask the companion |
| F9 | Quiet mode: it only speaks when you press F8 |

You can also just type to it in the terminal. Say "just tell me" if you want spoilers.

### How it works

- **Mod**: exports the game state every 2 seconds, detects events (save loaded, fight started, quest updated), and shows replies inside the game.
- **Scripts**: look things up in the data tables and decide which events are worth speaking up for, using fixed cooldown and batching rules.
- **Skill**: teaches the agent when to talk, how to talk, and how much to spoil.

The model only reads your question and phrases the answer. It runs on the subscription you already have, so it needs no local GPU.

### Notes

- Single-player games only. Never for online games with anti-cheat.
- No game data is shipped. The tables are extracted on your machine from your own copy of the game.
- Status: played for real with Claude Code. With Codex, plugin install, script calls, and waiting for game events are verified. WorkBuddy support follows its official docs but hasn't been tested yet.
- Want another game? Write an adapter modeled on `skills/game-companion/adapters/wandering-sword/`. PRs welcome.
- Unofficial fan project, not affiliated with the game's developer or publisher.

## License

MIT
