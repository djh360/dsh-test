#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""贪吃蛇 —— 一个只用 Python 标准库（tkinter）实现的小游戏。

运行：
    python snake.py

操作：
    方向键 / WASD   移动
    空格 / P        暂停、继续
    R               重新开始
    回车            开始 / 继续 / 再来一局
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
import tkinter as tk
import tkinter.font as tkfont
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# 尺寸与配色
# ---------------------------------------------------------------------------

COLS, ROWS = 24, 21
CELL = 28
PAD = 24
HEADER_H = 78

BOARD_X, BOARD_Y = PAD, HEADER_H
BOARD_W, BOARD_H = COLS * CELL, ROWS * CELL
WIDTH = BOARD_W + PAD * 2
HEIGHT = BOARD_Y + BOARD_H + 42
FRAME_MS = 16

UP, DOWN, LEFT, RIGHT = (0, -1), (0, 1), (-1, 0), (1, 0)
OPPOSITE = {UP: DOWN, DOWN: UP, LEFT: RIGHT, RIGHT: LEFT}

BG = "#070b14"
HEADER_BG = "#08101d"
PANEL = "#0b1526"
BORDER_SOFT = "#142238"
BOARD_BG = "#09111f"
BOARD_EDGE = "#17344a"
GRID = "#0e1a2c"
GRID_DOT = "#172942"

TEXT = "#edf3ff"
MUTED = "#7b8cab"
MUTED_DIM = "#4c5d7a"

ACCENT = "#3ce6a8"
ACCENT_DARK = "#0d3b31"
ACCENT_SOFT = "#1b7d66"
SNAKE_HEAD = "#63f5bd"
SNAKE_TAIL = "#168d84"
SNAKE_OUTLINE = "#042d29"
SNAKE_HIGHLIGHT = "#b5ffe3"

FOOD = "#ff5d73"
FOOD_LIGHT = "#ff9cac"
FOOD_DARK = "#b81f3e"
GOLD = "#ffc857"

STATE_READY = "ready"
STATE_RUNNING = "running"
STATE_PAUSED = "paused"
STATE_OVER = "over"
STATE_WIN = "win"


# ---------------------------------------------------------------------------
# 纯逻辑：不依赖 tkinter，方便单独自检
# ---------------------------------------------------------------------------


class SnakeModel:
    """棋盘、蛇、食物和计分规则。"""

    def __init__(
        self,
        cols: int = COLS,
        rows: int = ROWS,
        rng: random.Random | None = None,
    ):
        self.cols = cols
        self.rows = rows
        self.rng = rng or random.Random()
        self.reset()

    def reset(self) -> None:
        cx, cy = self.cols // 2, self.rows // 2
        self.snake: list[tuple[int, int]] = [
            (cx, cy),
            (cx - 1, cy),
            (cx - 2, cy),
            (cx - 3, cy),
        ]
        self.direction = RIGHT
        self.pending: list[tuple[int, int]] = []
        self.score = 0
        self.foods = 0
        self.alive = True
        self.won = False
        self.food: tuple[int, int] | None = None
        self._spawn_food()

    @property
    def level(self) -> int:
        return 1 + self.foods // 4

    @property
    def interval(self) -> float:
        """每一步的间隔（秒）。吃得越多，蛇跑得越快。"""
        return max(0.065, 0.145 - self.foods * 0.005)

    def queue_direction(self, direction: tuple[int, int]) -> bool:
        """把方向放进最多两项的输入队列，禁止原地掉头。"""
        if direction not in OPPOSITE:
            return False
        last = self.pending[-1] if self.pending else self.direction
        if direction == last or direction == OPPOSITE[last]:
            return False
        if len(self.pending) >= 2:
            return False
        self.pending.append(direction)
        return True

    def step(self) -> str:
        """走一步，返回 move / eat / dead / win / idle。"""
        if not self.alive:
            return "idle"

        if self.pending:
            self.direction = self.pending.pop(0)

        hx, hy = self.snake[0]
        dx, dy = self.direction
        head = (hx + dx, hy + dy)

        if not (0 <= head[0] < self.cols and 0 <= head[1] < self.rows):
            self.alive = False
            return "dead"

        eating = head == self.food
        # 不吃食物时尾巴会挪走，所以可以进入当前尾巴所在的格子。
        body = self.snake if eating else self.snake[:-1]
        if head in body:
            self.alive = False
            return "dead"

        self.snake.insert(0, head)

        if eating:
            self.score += 10
            self.foods += 1
            if len(self.snake) >= self.cols * self.rows:
                self.alive = False
                self.won = True
                self.food = None
                return "win"
            self._spawn_food()
            return "eat"

        self.snake.pop()
        return "move"

    def _spawn_food(self) -> None:
        occupied = set(self.snake)
        free = [
            (x, y)
            for y in range(self.rows)
            for x in range(self.cols)
            if (x, y) not in occupied
        ]
        self.food = self.rng.choice(free) if free else None


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------


def _blend(color_a: str, color_b: str, t: float) -> str:
    """在两个 #rrggbb 颜色之间线性插值。"""
    t = max(0.0, min(1.0, t))
    a = tuple(int(color_a[i : i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(color_b[i : i + 2], 16) for i in (1, 3, 5))
    mixed = tuple(round(x + (y - x) * t) for x, y in zip(a, b))
    return "#{:02x}{:02x}{:02x}".format(*mixed)


def _rounded_points(x1: float, y1: float, x2: float, y2: float, radius: float,
                    segments: int = 6) -> list[float]:
    """生成顺时针圆角矩形的顶点，用 canvas.create_polygon 绘制。"""
    radius = max(0.0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    if radius == 0:
        return [x1, y1, x2, y1, x2, y2, x1, y2]

    points: list[float] = []
    corners = (
        (x2 - radius, y1 + radius, -90, 0),
        (x2 - radius, y2 - radius, 0, 90),
        (x1 + radius, y2 - radius, 90, 180),
        (x1 + radius, y1 + radius, 180, 270),
    )
    for cx, cy, start, end in corners:
        for i in range(segments + 1):
            angle = math.radians(start + (end - start) * i / segments)
            points.extend((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    return points


def _high_score_path() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base or Path.home()) / "SnakeGame" / "highscore.json"


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float
    size: float
    color: str


# ---------------------------------------------------------------------------
# 界面
# ---------------------------------------------------------------------------


class SnakeApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.model = SnakeModel()
        self.prev_snake = list(self.model.snake)
        self.state = STATE_READY
        self.accum = 0.0
        self.progress = 1.0
        self.particles: list[Particle] = []
        self.last_frame = time.perf_counter()
        self.after_id: str | None = None
        self.best = self._load_best()
        self.new_record = False
        self.particles_rng = random.Random()

        self.ui_font = self._pick_font(
            ("Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC",
             "Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Micro Hei",
             "Segoe UI")
        )

        root.title("贪吃蛇 · Snake")
        root.configure(bg=BG)
        root.resizable(False, False)

        self.canvas = tk.Canvas(
            root,
            width=WIDTH,
            height=HEIGHT,
            bg=BG,
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack()
        self._center_window()

        self.hud_items: dict[str, int] = {}
        self.hud_cache: dict[str, str] = {}

        self._build_static()
        self._build_hud()
        self._bind_events()
        self._refresh_hud(force=True)
        self._render()
        self._redraw_overlay()
        self._set_icon()

        self.after_id = root.after(FRAME_MS, self._frame)
        root.after(80, self.canvas.focus_set)

    # -- 基础设置 ---------------------------------------------------------

    def _pick_font(self, candidates: tuple[str, ...]) -> str:
        try:
            available = {name.casefold(): name for name in tkfont.families(self.root)}
            for name in candidates:
                if name.casefold() in available:
                    return available[name.casefold()]
        except tk.TclError:
            pass
        return tkfont.nametofont("TkDefaultFont").actual("family")

    def _center_window(self) -> None:
        self.root.update_idletasks()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = max(0, (screen_w - WIDTH) // 2)
        y = max(0, (screen_h - HEIGHT) // 3)
        self.root.geometry(f"{WIDTH}x{HEIGHT}+{x}+{y}")

    def _set_icon(self) -> None:
        try:
            icon = tk.PhotoImage(width=32, height=32)
            icon.put(BG, to=(0, 0, 32, 32))
            icon.put(ACCENT, to=(4, 13, 22, 21))
            icon.put(ACCENT, to=(17, 7, 24, 22))
            icon.put(FOOD, to=(24, 11, 29, 16))
            self.root.iconphoto(True, icon)
            self._icon_ref = icon
        except tk.TclError:
            pass

    def _round(self, x1, y1, x2, y2, radius=12, **kwargs):
        points = _rounded_points(x1, y1, x2, y2, radius)
        return self.canvas.create_polygon(points, **kwargs)

    # -- 静态画面 ---------------------------------------------------------

    def _build_static(self) -> None:
        c = self.canvas
        c.create_rectangle(0, 0, WIDTH, HEIGHT, fill=BG, outline="")
        c.create_rectangle(0, 0, WIDTH, HEADER_H - 8, fill=HEADER_BG, outline="")
        c.create_line(0, HEADER_H - 8, WIDTH, HEADER_H - 8, fill="#0c1727", width=1)

        # 标题
        self._round(24, 17, 30, 43, radius=3, fill=ACCENT, outline="")
        c.create_text(40, 8, text="贪吃蛇", anchor="nw", fill=TEXT,
                      font=(self.ui_font, 23, "bold"))
        c.create_text(
            40, 47,
            text="方向键 / WASD 移动   ·   空格 暂停   ·   R 重开",
            anchor="nw", fill=MUTED, font=(self.ui_font, 9),
        )

        # 棋盘：阴影、外框、底色
        self._round(
            BOARD_X - 8, BOARD_Y - 2, BOARD_X + BOARD_W + 8, BOARD_Y + BOARD_H + 10,
            radius=22, fill="#04070d", outline="",
        )
        self._round(
            BOARD_X - 3, BOARD_Y - 3, BOARD_X + BOARD_W + 3, BOARD_Y + BOARD_H + 3,
            radius=18, fill="#0b1c2b", outline="#1a3c48", width=1,
        )
        self._round(
            BOARD_X, BOARD_Y, BOARD_X + BOARD_W, BOARD_Y + BOARD_H,
            radius=15, fill=BOARD_BG, outline=BOARD_EDGE, width=1,
        )

        # 网格只画内部线，避开圆角
        for col in range(1, COLS):
            x = BOARD_X + col * CELL
            c.create_line(x, BOARD_Y + 10, x, BOARD_Y + BOARD_H - 10,
                          fill=GRID, width=1)
        for row in range(1, ROWS):
            y = BOARD_Y + row * CELL
            c.create_line(BOARD_X + 10, y, BOARD_X + BOARD_W - 10, y,
                          fill=GRID, width=1)

        # 稀疏的小亮点，让棋盘不至于太单调
        for col in range(4, COLS, 4):
            for row in range(4, ROWS, 4):
                x = BOARD_X + col * CELL
                y = BOARD_Y + row * CELL
                c.create_oval(x - 1, y - 1, x + 1, y + 1, fill=GRID_DOT, outline="")

        # 四个角落的装饰括号
        inset, arm = 8, 18
        corners = (
            (BOARD_X + inset, BOARD_Y + inset, 1, 1),
            (BOARD_X + BOARD_W - inset, BOARD_Y + inset, -1, 1),
            (BOARD_X + inset, BOARD_Y + BOARD_H - inset, 1, -1),
            (BOARD_X + BOARD_W - inset, BOARD_Y + BOARD_H - inset, -1, -1),
        )
        for x, y, sx, sy in corners:
            c.create_line(x, y + sy * arm, x, y, x + sx * arm, y,
                          fill="#1d514b", width=2, capstyle=tk.ROUND)

        c.create_text(
            WIDTH // 2, HEIGHT - 23,
            text="吃一个 +10 分   ·   速度会越来越快   ·   窗口失焦自动暂停",
            fill=MUTED_DIM, font=(self.ui_font, 8),
        )

    def _build_hud(self) -> None:
        c = self.canvas
        specs = (
            ("score", "分数", TEXT),
            ("best", "最高", GOLD),
            ("level", "等级", ACCENT),
        )
        card_w, card_h, gap = 76, 50, 8
        left = BOARD_X + BOARD_W - (card_w * len(specs) + gap * (len(specs) - 1))
        for index, (key, label, value_color) in enumerate(specs):
            x1 = left + index * (card_w + gap)
            x2 = x1 + card_w
            self._round(x1, 12, x2, 12 + card_h, radius=10,
                        fill=PANEL, outline=BORDER_SOFT, width=1)
            c.create_text(x1 + 10, 20, text=label, anchor="nw",
                          fill=MUTED, font=(self.ui_font, 8))
            self.hud_items[key] = c.create_text(
                x1 + 10, 36, text="0", anchor="nw",
                fill=value_color, font=(self.ui_font, 16, "bold"),
            )

    # -- 事件 -------------------------------------------------------------

    def _bind_events(self) -> None:
        self.root.bind("<KeyPress>", self._on_key)
        self.root.bind("<FocusOut>", self._on_focus_out)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_key(self, event: tk.Event) -> str | None:
        key = event.keysym.lower()
        directions = {
            "left": LEFT, "a": LEFT,
            "right": RIGHT, "d": RIGHT,
            "up": UP, "w": UP,
            "down": DOWN, "s": DOWN,
        }
        if key in directions:
            self._press_direction(directions[key])
            return "break"
        if key in ("space", "p"):
            self._toggle_pause()
            return "break"
        if key == "r":
            self._restart()
            return "break"
        if key in ("return", "kp_enter"):
            self._confirm()
            return "break"
        if key == "escape" and self.state == STATE_RUNNING:
            self._toggle_pause()
            return "break"
        return None

    def _on_focus_out(self, _event: tk.Event) -> None:
        if self.state == STATE_RUNNING:
            self.state = STATE_PAUSED
            self._redraw_overlay()

    def _on_close(self) -> None:
        if self.after_id is not None:
            try:
                self.root.after_cancel(self.after_id)
            except tk.TclError:
                pass
        self._save_best()
        self.root.destroy()

    def _press_direction(self, direction: tuple[int, int]) -> None:
        if self.state in (STATE_OVER, STATE_WIN):
            return
        if self.state == STATE_READY:
            self.state = STATE_RUNNING
            self.last_frame = time.perf_counter()
            self._redraw_overlay()
        elif self.state == STATE_PAUSED:
            self.state = STATE_RUNNING
            self.last_frame = time.perf_counter()
            self._redraw_overlay()
        self.model.queue_direction(direction)

    def _toggle_pause(self) -> None:
        if self.state == STATE_READY:
            self._start()
        elif self.state == STATE_RUNNING:
            self.state = STATE_PAUSED
            self._redraw_overlay()
        elif self.state == STATE_PAUSED:
            self.state = STATE_RUNNING
            self.last_frame = time.perf_counter()
            self._redraw_overlay()
        else:
            self._restart()

    def _confirm(self) -> None:
        if self.state == STATE_READY:
            self._start()
        elif self.state == STATE_PAUSED:
            self.state = STATE_RUNNING
            self.last_frame = time.perf_counter()
            self._redraw_overlay()
        elif self.state in (STATE_OVER, STATE_WIN):
            self._restart()

    def _start(self) -> None:
        self.state = STATE_RUNNING
        self.accum = 0.0
        self.last_frame = time.perf_counter()
        self._redraw_overlay()

    def _restart(self) -> None:
        self.model.reset()
        self.prev_snake = list(self.model.snake)
        self.accum = 0.0
        self.progress = 1.0
        self.particles.clear()
        self.new_record = False
        self.state = STATE_RUNNING
        self.last_frame = time.perf_counter()
        self._refresh_hud(force=True)
        self._redraw_overlay()

    # -- 游戏循环 ---------------------------------------------------------

    def _frame(self) -> None:
        now = time.perf_counter()
        dt = min(0.05, max(0.0, now - self.last_frame))
        self.last_frame = now

        if self.state == STATE_RUNNING:
            self.accum += dt
            guard = 0
            while (
                self.state == STATE_RUNNING
                and self.accum >= self.model.interval
                and guard < 4
            ):
                self.accum -= self.model.interval
                self._advance()
                guard += 1
            if self.state == STATE_RUNNING:
                self.progress = min(1.0, self.accum / max(1e-6, self.model.interval))

        self._update_particles(dt)
        self._render(now)
        self._refresh_hud()
        self.after_id = self.root.after(FRAME_MS, self._frame)

    def _advance(self) -> None:
        self.prev_snake = list(self.model.snake)
        eaten_at = self.model.food
        event = self.model.step()
        self.progress = 0.0

        if event == "eat":
            self._burst(eaten_at)
            if self.model.score > self.best:
                self.best = self.model.score
                self.new_record = True
            self._refresh_hud(force=True)
        elif event == "dead":
            self.state = STATE_OVER
            self.progress = 1.0
            if self.model.score > self.best:
                self.best = self.model.score
                self.new_record = True
            self._save_best()
            self._refresh_hud(force=True)
            self._redraw_overlay()
        elif event == "win":
            self.state = STATE_WIN
            self.progress = 1.0
            if self.model.score > self.best:
                self.best = self.model.score
                self.new_record = True
            self._save_best()
            self._refresh_hud(force=True)
            self._redraw_overlay()

    # -- 绘制 -------------------------------------------------------------

    def _cell_center(self, cell: tuple[int, int]) -> tuple[float, float]:
        x, y = cell
        return BOARD_X + (x + 0.5) * CELL, BOARD_Y + (y + 0.5) * CELL

    def _snake_points(self) -> list[tuple[float, float]]:
        points: list[tuple[float, float]] = []
        current = self.model.snake
        for index, cell in enumerate(current):
            start = self.prev_snake[index] if index < len(self.prev_snake) else cell
            sx, sy = self._cell_center(start)
            ex, ey = self._cell_center(cell)
            points.append(
                (sx + (ex - sx) * self.progress, sy + (ey - sy) * self.progress)
            )
        return points

    def _segment_width(self, index: int, count: int) -> float:
        if count <= 1:
            return CELL * 0.72
        ratio = index / (count - 1)
        return CELL * (0.72 - 0.22 * ratio)

    def _draw_snake(self) -> None:
        c = self.canvas
        points = self._snake_points()
        if not points:
            return
        count = len(points)

        # 先画整条外轮廓，再画彩色内层，转弯处会更圆润。
        for i in range(count - 1):
            x1, y1 = points[i]
            x2, y2 = points[i + 1]
            width = self._segment_width(i, count) + 4
            c.create_line(x1, y1, x2, y2, fill=SNAKE_OUTLINE, width=width,
                          capstyle=tk.ROUND, tags="dynamic")

        for i in range(count - 2, -1, -1):
            x1, y1 = points[i]
            x2, y2 = points[i + 1]
            ratio = i / max(1, count - 1)
            color = _blend(SNAKE_HEAD, SNAKE_TAIL, ratio)
            width = self._segment_width(i, count)
            c.create_line(x1, y1, x2, y2, fill=color, width=width,
                          capstyle=tk.ROUND, tags="dynamic")

        # 身体上淡淡的鳞片高光
        for i in range(2, count, 3):
            x, y = points[i]
            radius = 1.8 if i < count * 0.6 else 1.3
            c.create_oval(x - radius, y - radius - 2, x + radius, y + radius - 2,
                          fill=_blend("#91ffd6", SNAKE_TAIL, i / max(1, count - 1)),
                          outline="", tags="dynamic")

        # 头部
        hx, hy = points[0]
        radius = CELL * 0.46
        c.create_oval(hx - radius + 2, hy - radius + 3, hx + radius + 2, hy + radius + 3,
                      fill="#030907", outline="", tags="dynamic")
        c.create_oval(hx - radius, hy - radius, hx + radius, hy + radius,
                      fill=SNAKE_HEAD, outline=SNAKE_OUTLINE, width=2,
                      tags="dynamic")
        c.create_oval(hx - radius * 0.62, hy - radius * 0.66,
                      hx - radius * 0.12, hy - radius * 0.18,
                      fill=SNAKE_HIGHLIGHT, outline="", tags="dynamic")

        dx, dy = self.model.direction
        px, py = -dy, dx
        eye_forward, eye_side = 4.2, 5.1
        for sign in (-1, 1):
            ex = hx + dx * eye_forward + px * eye_side * sign
            ey = hy + dy * eye_forward + py * eye_side * sign
            c.create_oval(ex - 3.3, ey - 3.3, ex + 3.3, ey + 3.3,
                          fill="#f4fbff", outline="", tags="dynamic")
            c.create_oval(
                ex - 1.6 + dx * 1.1, ey - 1.6 + dy * 1.1,
                ex + 1.6 + dx * 1.1, ey + 1.6 + dy * 1.1,
                fill="#071410", outline="", tags="dynamic",
            )

    def _draw_food(self, now: float) -> None:
        if self.model.food is None:
            return
        c = self.canvas
        cx, cy = self._cell_center(self.model.food)
        pulse = (math.sin(now * 5.0) + 1.0) / 2.0
        glow = 15.0 + pulse * 4.0

        c.create_oval(cx - glow, cy - glow, cx + glow, cy + glow,
                      fill="#1e0a12", outline="", tags="dynamic")
        c.create_oval(cx - 8, cy + 7, cx + 8, cy + 11,
                      fill="#04080d", outline="", tags="dynamic")
        c.create_oval(cx - 9, cy - 8, cx + 9, cy + 9,
                      fill=FOOD_DARK, outline="", tags="dynamic")
        c.create_oval(cx - 8, cy - 9, cx + 8, cy + 7,
                      fill=FOOD, outline=FOOD_LIGHT, width=1, tags="dynamic")
        c.create_oval(cx - 5, cy - 6, cx - 1, cy - 2,
                      fill="#ffc2ca", outline="", tags="dynamic")

        c.create_line(cx, cy - 8, cx + 2, cy - 14,
                      fill="#7b4a32", width=2, capstyle=tk.ROUND, tags="dynamic")
        c.create_polygon(
            cx + 2, cy - 13, cx + 3, cy - 17, cx + 8, cy - 16,
            cx + 7, cy - 12, fill="#49d58a", outline="", tags="dynamic",
        )

    def _burst(self, cell: tuple[int, int] | None) -> None:
        if cell is None:
            return
        cx, cy = self._cell_center(cell)
        colors = (ACCENT, GOLD, FOOD_LIGHT, "#ffffff")
        for _ in range(16):
            angle = self.particles_rng.uniform(0, math.tau)
            speed = self.particles_rng.uniform(35, 145)
            life = self.particles_rng.uniform(0.30, 0.65)
            self.particles.append(
                Particle(
                    x=cx, y=cy,
                    vx=math.cos(angle) * speed,
                    vy=math.sin(angle) * speed - 25,
                    life=life, max_life=life,
                    size=self.particles_rng.uniform(1.4, 3.2),
                    color=self.particles_rng.choice(colors),
                )
            )

    def _update_particles(self, dt: float) -> None:
        alive: list[Particle] = []
        for p in self.particles:
            p.life -= dt
            if p.life <= 0:
                continue
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.vy += 150 * dt
            p.vx *= 0.985
            alive.append(p)
        self.particles = alive

    def _draw_particles(self) -> None:
        for p in self.particles:
            ratio = p.life / p.max_life
            radius = p.size * (0.35 + ratio * 0.65)
            self.canvas.create_oval(
                p.x - radius, p.y - radius, p.x + radius, p.y + radius,
                fill=p.color, outline="", tags="dynamic",
            )

    def _render(self, now: float | None = None) -> None:
        now = now if now is not None else time.perf_counter()
        self.canvas.delete("dynamic")
        self._draw_food(now)
        self._draw_snake()
        self._draw_particles()
        if self.canvas.find_withtag("overlay"):
            self.canvas.tag_raise("overlay")

    def _refresh_hud(self, force: bool = False) -> None:
        values = {
            "score": f"{self.model.score:03d}",
            "best": f"{self.best:03d}",
            "level": f"{self.model.level:02d}",
        }
        for key, value in values.items():
            if force or self.hud_cache.get(key) != value:
                self.hud_cache[key] = value
                self.canvas.itemconfigure(self.hud_items[key], text=value)

    # -- 覆盖层 -----------------------------------------------------------

    def _redraw_overlay(self) -> None:
        c = self.canvas
        c.delete("overlay")
        if self.state == STATE_READY:
            self._overlay_ready()
        elif self.state == STATE_PAUSED:
            self._overlay_paused()
        elif self.state == STATE_OVER:
            self._overlay_over()
        elif self.state == STATE_WIN:
            self._overlay_win()
        if c.find_withtag("overlay"):
            c.tag_raise("overlay")

    def _overlay_base(self, height: int, width: int = 404) -> tuple[float, float]:
        c = self.canvas
        c.create_rectangle(
            BOARD_X + 2, BOARD_Y + 2, BOARD_X + BOARD_W - 2, BOARD_Y + BOARD_H - 2,
            fill="#02060c", outline="", stipple="gray50", tags="overlay",
        )
        cx = BOARD_X + BOARD_W / 2
        top = BOARD_Y + (BOARD_H - height) / 2
        self._round(
            cx - width / 2 + 4, top + 7, cx + width / 2 + 4, top + height + 7,
            radius=18, fill="#03070d", outline="", tags="overlay",
        )
        self._round(
            cx - width / 2, top, cx + width / 2, top + height,
            radius=18, fill="#0a1424", outline="#203a57", width=1, tags="overlay",
        )
        self._round(
            cx - 18, top, cx + 18, top + 3,
            radius=1, fill=ACCENT, outline="", tags="overlay",
        )
        return cx, top

    def _overlay_label(self, cx: float, y: float, text: str,
                       color: str = ACCENT) -> None:
        self.canvas.create_text(
            cx, y, text=text, fill=color,
            font=(self.ui_font, 8, "bold"), tags="overlay",
        )

    def _overlay_title(self, cx: float, y: float, text: str,
                       color: str = TEXT, size: int = 20) -> None:
        self.canvas.create_text(
            cx, y, text=text, fill=color,
            font=(self.ui_font, size, "bold"), tags="overlay",
        )

    def _overlay_sub(self, cx: float, y: float, text: str,
                     color: str = MUTED, size: int = 10) -> None:
        self.canvas.create_text(
            cx, y, text=text, fill=color,
            font=(self.ui_font, size), tags="overlay",
        )

    def _pill(self, cx: float, cy: float, text: str, width: int = 244) -> None:
        height = 38
        self._round(cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2,
                    radius=19, fill=ACCENT_DARK, outline=ACCENT_SOFT, width=1,
                    tags="overlay")
        self.canvas.create_text(
            cx, cy, text=text, fill=ACCENT,
            font=(self.ui_font, 10, "bold"), tags="overlay",
        )

    def _overlay_ready(self) -> None:
        cx, top = self._overlay_base(212)
        self._overlay_label(cx, top + 28, "准 备 就 绪")
        self._overlay_title(cx, top + 55, "开始贪吃蛇")
        self._overlay_sub(cx, top + 88, "吃掉果实，别撞墙，也别咬到自己")
        self._overlay_sub(cx, top + 109, "方向键 / WASD 控制方向", MUTED_DIM, 9)
        self._pill(cx, top + 163, "空格 / 回车 开始游戏")

    def _overlay_paused(self) -> None:
        cx, top = self._overlay_base(180)
        self._overlay_label(cx, top + 27, "PAUSED", GOLD)
        self._overlay_title(cx, top + 55, "已暂停")
        self._overlay_sub(cx, top + 86, "休息一下，蛇可不会自己跑")
        self._pill(cx, top + 132, "空格 / P 继续游戏", 230)

    def _overlay_over(self) -> None:
        cx, top = self._overlay_base(224)
        self._overlay_label(cx, top + 26, "GAME OVER", FOOD)
        self._overlay_title(cx, top + 55, "游戏结束", FOOD)
        self._overlay_sub(
            cx, top + 88,
            f"本局 {self.model.score} 分   ·   最高 {self.best} 分",
            TEXT, 11,
        )
        if self.new_record:
            self._overlay_sub(cx, top + 111, "★  新纪录  ★", GOLD, 10)
        elif self.model.score == 0:
            self._overlay_sub(cx, top + 111, "先吃到一个果实，再挑战纪录", MUTED_DIM, 9)
        elif self.model.score == self.best:
            self._overlay_sub(cx, top + 111, "追平最高纪录了", GOLD, 9)
        else:
            self._overlay_sub(cx, top + 111, "差一点就刷新纪录了", MUTED_DIM, 9)
        self._pill(cx, top + 166, "R / 回车 再来一局")

    def _overlay_win(self) -> None:
        cx, top = self._overlay_base(224)
        self._overlay_label(cx, top + 26, "PERFECT", GOLD)
        self._overlay_title(cx, top + 55, "完美通关！", GOLD)
        self._overlay_sub(cx, top + 88, "整块棋盘都被你填满了", TEXT, 11)
        self._overlay_sub(cx, top + 111, f"最终得分  {self.model.score}", GOLD, 10)
        self._pill(cx, top + 166, "R / 回车 再来一局")

    # -- 最高分 -----------------------------------------------------------

    def _load_best(self) -> int:
        try:
            data = json.loads(_high_score_path().read_text(encoding="utf-8"))
            return max(0, int(data.get("best", 0)))
        except (OSError, ValueError, TypeError):
            return 0

    def _save_best(self) -> None:
        if self.best <= 0:
            return
        try:
            path = _high_score_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({"best": int(self.best)}, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass


# ---------------------------------------------------------------------------
# 自检 / 入口
# ---------------------------------------------------------------------------


def run_checks() -> None:
    rng = random.Random(7)
    game = SnakeModel(cols=12, rows=12, rng=rng)
    assert len(game.snake) == 4
    assert game.food not in game.snake

    # 不能直接 180 度掉头
    assert not game.queue_direction(LEFT)
    assert game.queue_direction(UP)
    assert len(game.pending) == 1
    game.pending.clear()

    # 吃食物：长度 +1、分数 +10、食物重新生成
    game = SnakeModel(cols=12, rows=12, rng=random.Random(9))
    head_x, head_y = game.snake[0]
    game.food = (head_x + 1, head_y)
    event = game.step()
    assert event == "eat", event
    assert len(game.snake) == 5
    assert game.score == 10
    assert game.food not in game.snake

    # 撞墙
    game = SnakeModel(cols=10, rows=10, rng=random.Random(1))
    game.snake = [(9, 5), (8, 5), (7, 5), (6, 5)]
    game.direction = RIGHT
    game.food = (0, 0)
    assert game.step() == "dead"
    assert not game.alive

    # 撞到自己（但不能把“跟着尾巴走”误判为撞到）
    game = SnakeModel(cols=10, rows=10, rng=random.Random(2))
    game.snake = [(3, 3), (3, 4), (2, 4), (2, 3), (2, 2)]
    game.direction = LEFT
    game.food = (9, 9)
    assert game.step() == "dead"

    game = SnakeModel(cols=10, rows=10, rng=random.Random(3))
    game.snake = [(3, 3), (3, 4), (2, 4), (2, 3)]
    game.direction = LEFT
    game.food = (9, 9)
    assert game.step() == "move"
    assert game.snake[0] == (2, 3)

    # 填满棋盘即通关
    game = SnakeModel(cols=2, rows=2, rng=random.Random(5))
    game.snake = [(0, 0), (0, 1), (1, 1)]
    game.direction = RIGHT
    game.food = (1, 0)
    assert game.step() == "win"
    assert game.won and game.food is None

    # 速度会加快，但存在上限
    game = SnakeModel(cols=10, rows=10, rng=random.Random(4))
    assert 0.05 < game.interval < 0.2
    game.foods = 10_000
    assert game.interval == 0.065

    print("逻辑自检通过：移动、转向、进食、撞墙、自撞、通关、速度上限")


def run_gui_smoke() -> int:
    root = tk.Tk()
    root.withdraw()
    app = SnakeApp(root)
    app._save_best = lambda: None  # 冒烟测试不写最高分文件

    # 开始、吃到一个果实
    app._press_direction(UP)
    assert app.state == STATE_RUNNING
    hx, hy = app.model.snake[0]
    app.model.food = (hx, hy - 1)
    app._advance()
    assert app.model.score == 10
    assert len(app.model.snake) == 5

    # 暂停、继续
    app._toggle_pause()
    assert app.state == STATE_PAUSED
    app._toggle_pause()
    assert app.state == STATE_RUNNING

    # 撞墙后显示结束覆盖层
    app.model.snake = [(COLS - 1, 5), (COLS - 2, 5), (COLS - 3, 5), (COLS - 4, 5)]
    app.model.direction = RIGHT
    app.model.food = (0, 0)
    app._advance()
    assert app.state == STATE_OVER
    assert app.canvas.find_withtag("overlay")

    # 重开
    app._restart()
    assert app.state == STATE_RUNNING
    assert app.model.score == 0
    assert not app.canvas.find_withtag("overlay")

    app._render()
    root.update_idletasks()
    root.update()
    print("GUI 冒烟测试通过：开始、进食、暂停、结束覆盖层、重开和绘制正常")
    root.destroy()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="用 tkinter 写的贪吃蛇小游戏")
    parser.add_argument("--check", action="store_true", help="只运行逻辑自检，不打开窗口")
    parser.add_argument("--smoke", action="store_true", help="无界面冒烟测试（开发用）")
    args = parser.parse_args(argv)

    if args.check:
        run_checks()
        return 0
    if args.smoke:
        return run_gui_smoke()

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print(f"无法启动图形界面：{exc}", file=sys.stderr)
        return 1

    SnakeApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
