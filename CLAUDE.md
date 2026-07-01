# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

尽可能使用中文来回答问题。

## 项目概述

🍅 番茄钟 — 一个暗色主题的番茄工作法计时器，提供 Web 版和桌面版两种实现。

## 运行方式

```bash
# Web 版：直接用浏览器打开
start pomodoro.html

# 桌面版（Python tkinter）
python pomodoro_app.py

# 桌面版可选依赖（启用系统托盘）
pip install pystray pillow
```

## 架构

两个文件是**独立实现**，共享同一套设计语言（配色、模式结构、UI 布局），不共享代码：

| | `pomodoro.html` | `pomodoro_app.py` |
|---|---|---|
| UI | HTML/CSS + SVG 圆环 | tkinter + Canvas 圆环 |
| 音频 | Web Audio API | `winsound.Beep` |
| 持久化 | `localStorage` | `pomodoro_config.json` |
| 通知 | Browser Notification API | 窗口内 toast + 托盘菜单 |
| 托盘 | — | `pystray` + `Pillow` |

### 共享的设计常量

- **配色** `COLORS`：暗色背景 `#1a1a2e` / `#16213e`，三种模式各有 accent 色（红/绿/蓝）
- **三种模式** `work`（25分钟）、`shortBreak`（5分钟）、`longBreak`（15分钟）— 可通过设置面板自定义
- **自动切换逻辑**：完成一个工作段后自动进入休息；每 4 个番茄自动切到长休息
- **键盘快捷键**：`Space` 开始/暂停、`R` 重置、`1/2/3` 切换模式

### Python 版关键依赖

- 标准库：`tkinter`、`json`、`winsound`、`threading`、`math`
- 可选：`pystray`（系统托盘，需在后台线程运行）、`Pillow`（绘制托盘图标）

### 数据持久化

- Python 版：`pomodoro_config.json`（与脚本同目录），字段为 `durations`、`auto_switch`、`sessions`、`date`，按天重置番茄计数
- Web 版：`localStorage` 键 `pomodoro-durations` 和 `pomodoro-autoSwitch`，番茄计数不跨 session 持久化
