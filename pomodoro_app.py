#!/usr/bin/env python3
"""
🍅 桌面番茄钟 — Python + tkinter 原生实现
系统托盘 | 暗色主题 | 圆形进度环 | 音效提醒 | 自动切换
"""

import tkinter as tk
from tkinter import ttk
import json
import os
import sys
import winsound
import threading
import math
from pathlib import Path

# ── 可选依赖：系统托盘 ─────────────────────────────
try:
    from PIL import Image, ImageDraw
    import pystray
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False
    print("[提示] 安装 pystray 和 pillow 以启用系统托盘: pip install pystray pillow")


# ═══════════════════════════════════════════════════
# 配色方案（参考 pomodoro.html 暗色主题）
# ═══════════════════════════════════════════════════
COLORS = {
    'bg':          '#f0f2f5',
    'surface':     '#ffffff',
    'surface2':    '#dce3ea',
    'text':        '#2c3e50',
    'text2':       '#7f8c9b',
    'ring_bg':     '#e8ecf1',
    'work':        '#e74c3c',
    'work_light':  '#c0392b',
    'short_break': '#2ecc71',
    'short_light': '#27ae60',
    'long_break':  '#3498db',
    'long_light':  '#2980b9',
}

MODE_META = {
    'work':       {'accent': COLORS['work'],       'light': COLORS['work_light'],
                   'label': '专注工作', 'icon': '🎯', 'emoji': '🍅'},
    'shortBreak': {'accent': COLORS['short_break'], 'light': COLORS['short_light'],
                   'label': '短休息',   'icon': '☕', 'emoji': '☕'},
    'longBreak':  {'accent': COLORS['long_break'],  'light': COLORS['long_light'],
                   'label': '长休息',   'icon': '🌿', 'emoji': '🌿'},
}

CONFIG_PATH = Path(__file__).parent / 'pomodoro_config.json'


# ═══════════════════════════════════════════════════
# 主应用类
# ═══════════════════════════════════════════════════
class PomodoroApp:
    def __init__(self):
        # ── 状态变量 ─────────────────────────────
        self.mode = 'work'
        self.durations = {'work': 25, 'shortBreak': 5, 'longBreak': 15}
        self.remaining_sec = 25 * 60
        self.total_sec = 25 * 60
        self.timer_id = None
        self.running = False
        self.sessions = 0            # 今日已完成番茄数
        self.today_str = ''          # 用于判断跨天
        self.auto_switch = False
        self.settings_open = False
        self.always_on_top = False
        self._quitting = False       # 防止重复退出

        # ── 构建 UI ──────────────────────────────
        self.root = tk.Tk()
        self.root.title('🍅 番茄钟')
        self.root.geometry('420x600')
        self.root.minsize(380, 520)
        self.root.configure(bg=COLORS['bg'])

        # 窗口图标（尝试设置）
        try:
            self.root.iconbitmap(default='tomato.ico')
        except Exception:
            pass

        # 居中显示
        self._center_window()

        # 关闭 → 最小化到托盘
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)

        self._build_ui()
        self._bind_keys()

        # ── 加载设置 ─────────────────────────────
        self.load_settings()

        # ── 更新初始显示 ─────────────────────────
        self.update_theme()
        self.update_display()

        # ── 系统托盘 ─────────────────────────────
        self.tray_icon = None
        self.tray_thread = None
        if TRAY_AVAILABLE:
            self._setup_tray()

    # ─────────────────────────────────────────────
    # 窗口辅助
    # ─────────────────────────────────────────────
    def _center_window(self):
        self.root.update_idletasks()
        w, h = 420, 600
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.root.geometry(f'{w}x{h}+{x}+{y}')

    def _on_close(self):
        """关闭窗口 → 隐藏到托盘；若无托盘则直接退出"""
        if TRAY_AVAILABLE and self.tray_icon:
            self.root.withdraw()
        else:
            self.quit_app()

    # ─────────────────────────────────────────────
    # 构建 UI
    # ─────────────────────────────────────────────
    def _build_ui(self):
        bg = COLORS['bg']
        surface = COLORS['surface']

        # 主容器
        self.main_frame = tk.Frame(self.root, bg=surface,
                                   highlightthickness=1,
                                   highlightbackground=COLORS['surface2'])
        self.main_frame.place(relx=0.5, rely=0.5, anchor='center',
                              width=400, height=580)

        # ── Header ───────────────────────────────
        header = tk.Frame(self.main_frame, bg=surface)
        header.pack(fill='x', padx=28, pady=(24, 0))

        title_lbl = tk.Label(header, text='🍅 番茄钟',
                             font=('Microsoft YaHei', 18, 'bold'),
                             fg=COLORS['text'], bg=surface)
        title_lbl.pack(side='left')

        self.session_badge = tk.Label(
            header,
            text='已完成 0 个番茄',
            font=('Microsoft YaHei', 9),
            fg=COLORS['text2'], bg=COLORS['surface2'],
            padx=10, pady=3)
        self.session_badge.pack(side='right')
        # 圆角用 Canvas 模拟更麻烦，先保持方形带 padding

        # ── 模式切换 ─────────────────────────────
        mode_bar = tk.Frame(self.main_frame, bg=COLORS['bg'])
        mode_bar.pack(fill='x', padx=28, pady=(18, 0))
        # 内部 padding
        mode_inner = tk.Frame(mode_bar, bg=COLORS['bg'])
        mode_inner.pack(fill='x', padx=4, pady=4)

        self.mode_btns = {}
        for key in ('work', 'shortBreak', 'longBreak'):
            meta = MODE_META[key]
            btn = tk.Button(
                mode_inner,
                text=f'{meta["icon"]} {meta["label"]}',
                font=('Microsoft YaHei', 10, 'bold'),
                fg=COLORS['text2'], bg=COLORS['bg'],
                activeforeground=COLORS['text'],
                activebackground=COLORS['surface2'],
                relief='flat', bd=0, padx=8, pady=8,
                cursor='hand2',
                command=lambda k=key: self.switch_mode(k),
            )
            btn.pack(side='left', expand=True, fill='x', padx=2)
            self.mode_btns[key] = btn

        # ── 计时器圆形区域 ───────────────────────
        ring_frame = tk.Frame(self.main_frame, bg=surface)
        ring_frame.pack(pady=(20, 10))

        self.ring_size = 260
        self.canvas = tk.Canvas(
            ring_frame,
            width=self.ring_size, height=self.ring_size,
            bg=surface, highlightthickness=0,
        )
        self.canvas.pack()

        # 背景圆环
        cx = cy = self.ring_size // 2
        r = 110
        self.ring_bg_arc = self.canvas.create_arc(
            cx - r, cy - r, cx + r, cy + r,
            start=90, extent=-359.9,
            style='arc',
            outline=COLORS['ring_bg'],
            width=10,
        )

        # 进度圆环
        self.ring_progress = self.canvas.create_arc(
            cx - r, cy - r, cx + r, cy + r,
            start=90, extent=-359.9,
            style='arc',
            outline=COLORS['work'],
            width=10,
        )

        # 中央时间文字
        self.time_text = self.canvas.create_text(
            cx, cy - 8,
            text='25:00',
            font=('Consolas', 42, 'bold'),
            fill=COLORS['text'],
        )

        # 阶段标签
        self.phase_text = self.canvas.create_text(
            cx, cy + 28,
            text='准备工作',
            font=('Microsoft YaHei', 10),
            fill=COLORS['text2'],
        )

        # ── 控制按钮 ─────────────────────────────
        ctrl_frame = tk.Frame(self.main_frame, bg=surface)
        ctrl_frame.pack(pady=(8, 4))

        # 重置
        self.btn_reset = tk.Button(
            ctrl_frame,
            text='↺',
            font=('Segoe UI Symbol', 16),
            fg=COLORS['text2'], bg=COLORS['bg'],
            activeforeground=COLORS['text'],
            activebackground=COLORS['surface2'],
            relief='flat', bd=0, width=3, height=2,
            cursor='hand2',
            command=self.reset_timer,
        )
        self.btn_reset.pack(side='left', padx=8)

        # 开始/暂停 (大圆按钮)
        self.btn_play = tk.Button(
            ctrl_frame,
            text='▶',
            font=('Segoe UI Symbol', 22),
            fg='white', bg=COLORS['work'],
            activeforeground='white', activebackground=COLORS['work_light'],
            relief='flat', bd=0, width=4, height=2,
            cursor='hand2',
            command=self.toggle_timer,
        )
        self.btn_play.pack(side='left', padx=8)

        # 跳过
        self.btn_skip = tk.Button(
            ctrl_frame,
            text='⏭',
            font=('Segoe UI Symbol', 16),
            fg=COLORS['text2'], bg=COLORS['bg'],
            activeforeground=COLORS['text'],
            activebackground=COLORS['surface2'],
            relief='flat', bd=0, width=3, height=2,
            cursor='hand2',
            command=self.skip_session,
        )
        self.btn_skip.pack(side='left', padx=8)

        # ── 设置面板 ─────────────────────────────
        self.btn_settings = tk.Button(
            self.main_frame,
            text='⚙ 自定义时长',
            font=('Microsoft YaHei', 9),
            fg=COLORS['text2'], bg=surface,
            activeforeground=COLORS['text'],
            activebackground=COLORS['bg'],
            relief='flat', bd=0, padx=10, pady=4,
            cursor='hand2',
            command=self._toggle_settings,
        )
        self.btn_settings.pack(pady=(10, 0))

        # 设置面板容器
        self.settings_frame = tk.Frame(self.main_frame, bg=surface)
        # 不立即 pack，toggle 时切换

        self._build_settings_panel()

        # ── 底部 ─────────────────────────────────
        footer = tk.Frame(self.main_frame, bg=surface)
        footer.pack(fill='x', padx=28, pady=(12, 20), side='bottom')

        # 自动切换开关
        auto_frame = tk.Frame(footer, bg=surface, cursor='hand2')
        auto_frame.pack(side='left')
        auto_frame.bind('<Button-1>', lambda e: self._toggle_auto_switch())

        self.auto_canvas = tk.Canvas(
            auto_frame,
            width=40, height=22,
            bg=surface, highlightthickness=0,
        )
        self.auto_canvas.pack(side='left', padx=(0, 8))
        self.auto_canvas.bind('<Button-1>', lambda e: self._toggle_auto_switch())
        # 开关背景
        self.auto_bg_rect = self.auto_canvas.create_rectangle(
            0, 0, 40, 22,
            fill=COLORS['bg'],
            outline='',
        )
        # 开关圆球
        self.auto_knob = self.auto_canvas.create_oval(
            3, 3, 19, 19,
            fill='white',
            outline='',
        )

        auto_lbl = tk.Label(
            auto_frame,
            text='自动切换下一阶段',
            font=('Microsoft YaHei', 9),
            fg=COLORS['text2'], bg=surface,
        )
        auto_lbl.pack(side='left')
        auto_lbl.bind('<Button-1>', lambda e: self._toggle_auto_switch())

        # 快捷键提示
        hint = tk.Label(
            footer,
            text='空格 开始/暂停 · R 重置',
            font=('Microsoft YaHei', 8),
            fg='#555555', bg=surface,
        )
        hint.pack(side='right')

        # ── Toast 提示标签 ───────────────────────
        self.toast_label = tk.Label(
            self.root,
            text='',
            font=('Microsoft YaHei', 10, 'bold'),
            fg=COLORS['work_light'], bg=COLORS['surface2'],
            padx=16, pady=8,
        )
        # 初始隐藏，show_toast 时显示

    def _build_settings_panel(self):
        """构建设置面板内的输入控件"""
        surface = COLORS['surface']
        self.settings_inner = tk.Frame(self.settings_frame, bg=surface)

        self.duration_inputs = {}
        rows = [
            ('work',       '🎯 工作时长',  1, 120),
            ('shortBreak', '☕ 短休息时长', 1, 60),
            ('longBreak',  '🌿 长休息时长', 1, 120),
        ]
        for key, label, vmin, vmax in rows:
            row = tk.Frame(self.settings_inner, bg=surface)
            row.pack(fill='x', pady=4)

            lbl = tk.Label(row, text=label,
                           font=('Microsoft YaHei', 10),
                           fg=COLORS['text2'], bg=surface)
            lbl.pack(side='left')

            input_group = tk.Frame(row, bg=surface)
            input_group.pack(side='right')

            var = tk.StringVar(value=str(self.durations.get(key, 25)))
            entry = tk.Entry(
                input_group,
                textvariable=var,
                font=('Microsoft YaHei', 11, 'bold'),
                fg=COLORS['text'], bg=COLORS['bg'],
                insertbackground=COLORS['text'],
                relief='flat', bd=0,
                width=4, justify='center',
            )
            entry.pack(side='left', ipady=4)
            entry.bind('<FocusOut>', lambda e, k=key: self._apply_duration(k))
            entry.bind('<Return>', lambda e, k=key: self._apply_duration(k))

            unit = tk.Label(input_group, text=' 分钟',
                            font=('Microsoft YaHei', 9),
                            fg=COLORS['text2'], bg=surface)
            unit.pack(side='left')

            self.duration_inputs[key] = {'var': var, 'entry': entry,
                                         'min': vmin, 'max': vmax}

        self.settings_inner.pack(fill='x', padx=28, pady=(4, 12))

    # ─────────────────────────────────────────────
    # 主题更新
    # ─────────────────────────────────────────────
    def update_theme(self):
        meta = MODE_META[self.mode]
        accent = meta['accent']
        light = meta['light']

        # 进度环颜色
        self.canvas.itemconfig(self.ring_progress, outline=accent)
        # 播放按钮颜色
        self.btn_play.configure(bg=accent, activebackground=light)
        # 阶段标签
        self.canvas.itemconfig(self.phase_text, text=meta['label'])
        # 高亮模式按钮
        for key, btn in self.mode_btns.items():
            if key == self.mode:
                btn.configure(fg=light, bg=COLORS['surface2'])
            else:
                btn.configure(fg=COLORS['text2'], bg=COLORS['bg'])

    # ─────────────────────────────────────────────
    # 显示更新
    # ─────────────────────────────────────────────
    def update_display(self):
        m = self.remaining_sec // 60
        s = self.remaining_sec % 60
        time_str = f'{m:02d}:{s:02d}'
        self.canvas.itemconfig(self.time_text, text=time_str)

        # 进度弧
        progress = 1.0 - (self.remaining_sec / self.total_sec)
        extent = -359.9 * (1.0 - progress)  # remaining proportion
        self.canvas.itemconfig(self.ring_progress, extent=extent)

        # 窗口标题
        meta = MODE_META[self.mode]
        self.root.title(f'{time_str} · {meta["label"]} · 🍅 番茄钟')

        # Session 计数
        self.session_badge.configure(
            text=f'已完成 {self.sessions} 个番茄')

    # ─────────────────────────────────────────────
    # 计时器控制
    # ─────────────────────────────────────────────
    def toggle_timer(self):
        if self.running:
            self.pause_timer()
        else:
            self.start_timer()

    def start_timer(self):
        if self.running:
            return
        self.running = True
        self.btn_play.configure(text='⏸')
        meta = MODE_META[self.mode]
        self.canvas.itemconfig(self.phase_text, text=meta['label'])
        self._tick()

    def _tick(self):
        if not self.running:
            return
        if self.remaining_sec <= 0:
            self._complete_session()
            return

        self.remaining_sec -= 1
        self.update_display()
        self.timer_id = self.root.after(1000, self._tick)

    def pause_timer(self):
        if not self.running:
            return
        self.running = False
        if self.timer_id:
            self.root.after_cancel(self.timer_id)
            self.timer_id = None
        self.btn_play.configure(text='▶')
        label = '准备' + MODE_META[self.mode]['label']
        self.canvas.itemconfig(self.phase_text, text=label)

    def reset_timer(self):
        was_running = self.running
        self.pause_timer()
        self.remaining_sec = self.durations[self.mode] * 60
        self.total_sec = self.remaining_sec
        self.canvas.itemconfig(self.ring_progress, extent=-359.9)
        self.update_display()
        label = '准备' + MODE_META[self.mode]['label']
        self.canvas.itemconfig(self.phase_text, text=label)
        self._play_beep(880, 60)
        if was_running:
            self.show_toast('⏮ 已重置')

    def skip_session(self):
        self.pause_timer()
        self.remaining_sec = 0
        self.update_display()
        self._complete_session()

    def switch_mode(self, new_mode):
        if new_mode == self.mode:
            return
        self.pause_timer()
        self.mode = new_mode
        self.remaining_sec = self.durations[self.mode] * 60
        self.total_sec = self.remaining_sec
        self.canvas.itemconfig(self.ring_progress, extent=-359.9)
        self.update_theme()
        self.update_display()
        label = '准备' + MODE_META[self.mode]['label']
        self.canvas.itemconfig(self.phase_text, text=label)
        self._play_beep(880, 60)

    # ─────────────────────────────────────────────
    # 计时完成
    # ─────────────────────────────────────────────
    def _complete_session(self):
        self.pause_timer()
        self.remaining_sec = 0
        self.update_display()
        self._play_complete_sound()

        if self.mode == 'work':
            self.sessions += 1
            self.save_settings()
            self.show_toast(f'🎉 第 {self.sessions} 个番茄完成！')
            self._flash_window()

            # 每 4 个番茄 → 长休息
            if self.sessions % 4 == 0:
                self.show_toast('🌟 已完成 4 个番茄，来次长休息吧！')
                if self.auto_switch:
                    self.switch_mode('longBreak')
            else:
                if self.auto_switch:
                    self.switch_mode('shortBreak')
        else:
            break_type = '短休息' if self.mode == 'shortBreak' else '长休息'
            self.show_toast(f'⏰ {break_type}结束，开始工作吧！')
            if self.auto_switch:
                self.switch_mode('work')

    # ─────────────────────────────────────────────
    # 音效
    # ─────────────────────────────────────────────
    def _play_beep(self, freq, duration_ms):
        """播放单次蜂鸣（Windows winsound）"""
        try:
            winsound.Beep(freq, duration_ms)
        except Exception:
            pass  # 某些系统可能不支持

    def _play_complete_sound(self):
        """完成提示音：上升音阶"""
        notes = [(523, 150), (659, 150), (784, 150), (1047, 350)]
        delay = 0
        for freq, dur in notes:
            self.root.after(delay, lambda f=freq, d=dur: self._play_beep(f, d))
            delay += 130

    # ─────────────────────────────────────────────
    # 桌面通知 / Toast
    # ─────────────────────────────────────────────
    def show_toast(self, msg):
        """在主窗口上方显示短暂提示"""
        self.toast_label.configure(text=msg)
        # 放在主窗口上方居中
        self.root.update_idletasks()
        tw = self.toast_label.winfo_reqwidth()
        # 粗略定位
        self.toast_label.place(relx=0.5, y=12, anchor='n')
        # 自动消失
        self.root.after(2500, lambda: self.toast_label.place_forget())

    def _flash_window(self):
        """窗口闪烁提醒"""
        try:
            self.root.attributes('-topmost', True)
            self.root.update()
            self.root.after(200, lambda: self.root.attributes('-topmost', self.always_on_top))
        except Exception:
            pass

    # ─────────────────────────────────────────────
    # 设置面板
    # ─────────────────────────────────────────────
    def _toggle_settings(self):
        self.settings_open = not self.settings_open
        if self.settings_open:
            # 更新输入框的值
            for key, io in self.duration_inputs.items():
                io['var'].set(str(self.durations.get(key, 25)))
            self.settings_frame.pack(fill='x', padx=28, pady=(0, 0),
                                     before=self.btn_settings)
            self.btn_settings.configure(text='▲ 收起设置')
        else:
            self.settings_frame.pack_forget()
            self.btn_settings.configure(text='⚙ 自定义时长')

    def _apply_duration(self, key):
        io = self.duration_inputs[key]
        try:
            val = int(io['var'].get())
            val = max(io['min'], min(io['max'], val))
            io['var'].set(str(val))
            self.durations[key] = val
            if not self.running and key == self.mode:
                self.remaining_sec = val * 60
                self.total_sec = val * 60
                self.canvas.itemconfig(self.ring_progress, extent=-359.9)
                self.update_display()
            self.save_settings()
        except ValueError:
            io['var'].set(str(self.durations[key]))

    def _toggle_auto_switch(self):
        self.auto_switch = not self.auto_switch
        self._update_auto_switch_ui()
        self.save_settings()
        txt = '已开启自动切换' if self.auto_switch else '已关闭自动切换'
        self.show_toast(txt)
        self._play_beep(880, 60)

    def _update_auto_switch_ui(self):
        if self.auto_switch:
            meta = MODE_META[self.mode]
            self.auto_canvas.itemconfig(self.auto_bg_rect, fill=meta['accent'])
            self.auto_canvas.coords(self.auto_knob, 21, 3, 37, 19)
        else:
            self.auto_canvas.itemconfig(self.auto_bg_rect, fill=COLORS['bg'])
            self.auto_canvas.coords(self.auto_knob, 3, 3, 19, 19)

    # ─────────────────────────────────────────────
    # 键盘快捷键
    # ─────────────────────────────────────────────
    def _bind_keys(self):
        self.root.bind('<space>', lambda e: self.toggle_timer())
        self.root.bind('<KeyPress-r>', lambda e: self.reset_timer())
        self.root.bind('<KeyPress-R>', lambda e: self.reset_timer())
        self.root.bind('<KeyPress-1>', lambda e: self.switch_mode('work'))
        self.root.bind('<KeyPress-2>', lambda e: self.switch_mode('shortBreak'))
        self.root.bind('<KeyPress-3>', lambda e: self.switch_mode('longBreak'))
        # Ctrl+T 切换置顶
        self.root.bind('<Control-t>', lambda e: self._toggle_always_on_top())
        self.root.bind('<Control-T>', lambda e: self._toggle_always_on_top())

    def _toggle_always_on_top(self):
        self.always_on_top = not self.always_on_top
        self.root.attributes('-topmost', self.always_on_top)
        txt = '📌 窗口置顶' if self.always_on_top else '📌 取消置顶'
        self.show_toast(txt)

    # ─────────────────────────────────────────────
    # 数据持久化
    # ─────────────────────────────────────────────
    def _get_today_str(self):
        from datetime import date
        return date.today().isoformat()

    def load_settings(self):
        """从 JSON 文件加载设置"""
        today = self._get_today_str()
        try:
            if CONFIG_PATH.exists():
                data = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
                # 时长设置
                if 'durations' in data:
                    self.durations.update(data['durations'])
                # 自动切换
                if 'auto_switch' in data:
                    self.auto_switch = data['auto_switch']
                # 今日番茄数
                if data.get('date') == today:
                    self.sessions = data.get('sessions', 0)
                else:
                    self.sessions = 0
                self.today_str = today
        except Exception:
            pass

        # 确保当前模式时长正确
        self.remaining_sec = self.durations[self.mode] * 60
        self.total_sec = self.remaining_sec
        self._update_auto_switch_ui()

    def save_settings(self):
        """保存设置到 JSON 文件"""
        today = self._get_today_str()
        data = {
            'durations': self.durations,
            'auto_switch': self.auto_switch,
            'sessions': self.sessions,
            'date': today,
        }
        try:
            CONFIG_PATH.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding='utf-8',
            )
        except Exception:
            pass

    # ─────────────────────────────────────────────
    # 系统托盘
    # ─────────────────────────────────────────────
    def _create_tray_image(self):
        """用 Pillow 绘制番茄图标"""
        size = 64
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # 番茄主体（红色圆）
        draw.ellipse([8, 18, 56, 62], fill='#e74c3c')
        # 高光
        draw.ellipse([18, 24, 30, 36], fill='#ff6b6b')
        # 茎
        draw.rectangle([28, 4, 36, 18], fill='#2ecc71')
        # 叶子
        draw.ellipse([20, 6, 34, 16], fill='#27ae60')
        return img

    def _setup_tray(self):
        """初始化系统托盘图标"""
        if not TRAY_AVAILABLE:
            return

        image = self._create_tray_image()

        # 构建菜单
        menu = pystray.Menu(
            pystray.MenuItem(
                '显示/隐藏窗口',
                self._tray_toggle_window,
                default=True,
            ),
            pystray.MenuItem(
                '▶ 开始 / ⏸ 暂停',
                self._tray_toggle_timer,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                '🎯 工作模式',
                lambda: self._tray_switch_mode('work'),
            ),
            pystray.MenuItem(
                '☕ 短休息',
                lambda: self._tray_switch_mode('shortBreak'),
            ),
            pystray.MenuItem(
                '🌿 长休息',
                lambda: self._tray_switch_mode('longBreak'),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('📌 切换置顶', self._tray_toggle_top),
            pystray.MenuItem('❌ 退出', self._tray_quit),
        )

        self.tray_icon = pystray.Icon(
            'pomodoro',
            image,
            '🍅 番茄钟',
            menu,
        )

        # 在后台线程中运行托盘
        self.tray_thread = threading.Thread(
            target=self.tray_icon.run,
            daemon=True,
        )
        self.tray_thread.start()

    def _tray_toggle_window(self):
        """在 tkinter 主线程中切换窗口显示"""
        self.root.after(0, self._do_toggle_window)

    def _do_toggle_window(self):
        if self.root.state() == 'withdrawn':
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        else:
            self.root.withdraw()

    def _tray_toggle_timer(self):
        self.root.after(0, self.toggle_timer)

    def _tray_switch_mode(self, mode):
        self.root.after(0, lambda: self.switch_mode(mode))
        # 如果窗口隐藏，先显示
        self.root.after(0, self._show_window)

    def _tray_toggle_top(self):
        self.root.after(0, self._toggle_always_on_top)

    def _show_window(self):
        if self.root.state() == 'withdrawn':
            self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _tray_quit(self):
        self.root.after(0, self.quit_app)

    # ─────────────────────────────────────────────
    # 退出
    # ─────────────────────────────────────────────
    def quit_app(self):
        """完整退出应用"""
        if self._quitting:
            return
        self._quitting = True

        self.running = False
        if self.timer_id:
            self.root.after_cancel(self.timer_id)
            self.timer_id = None

        self.save_settings()

        # 停止托盘
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass

        self.root.destroy()

    # ─────────────────────────────────────────────
    # 启动
    # ─────────────────────────────────────────────
    def run(self):
        self.root.mainloop()


# ═══════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════
if __name__ == '__main__':
    app = PomodoroApp()
    app.run()
