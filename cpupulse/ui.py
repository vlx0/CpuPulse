"""CpuPulse GUI."""

from __future__ import annotations

import ctypes
import tkinter as tk

from . import __version__
from .cpu import CpuSampler
from .instance import WINDOW_TITLE

BG = "#111111"
FG = "#ffffff"
MUTED = "#999999"
CARD = "#1a1a1a"
BAR = "#333333"
ACCENT = "#93c5fd"
OK = "#86efac"
WARN = "#fca5a5"


def _bar_color(pct: float) -> str:
    if pct >= 90:
        return WARN
    if pct >= 70:
        return "#fde68a"
    return OK


class CpuPulseApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(WINDOW_TITLE)
        self.geometry("560x560")
        self.minsize(480, 480)
        self.configure(bg=BG)
        self._samp = CpuSampler()
        self._hist: list[float] = []

        pad = tk.Frame(self, bg=BG)
        pad.pack(fill="both", expand=True, padx=22, pady=16)

        head = tk.Frame(pad, bg=BG)
        head.pack(fill="x")
        tk.Label(head, text="CpuPulse", bg=BG, fg=FG, font=("Segoe UI Semibold", 20)).pack(side="left")
        tk.Label(
            head, text="неделя 9 · мониторинг · день 57", bg=BG, fg=MUTED, font=("Segoe UI", 9)
        ).pack(side="right", pady=(8, 0))

        self._hint = tk.Label(
            pad,
            text=self._samp.name,
            bg=BG, fg=MUTED, font=("Segoe UI", 9), wraplength=500, justify="left",
        )
        self._hint.pack(anchor="w", pady=(6, 8))

        self._now = tk.Label(pad, text="— %", bg=BG, fg=ACCENT, font=("Segoe UI Semibold", 28))
        self._now.pack(anchor="w")
        self._sub = tk.Label(pad, text="", bg=BG, fg=MUTED, font=("Segoe UI", 9))
        self._sub.pack(anchor="w", pady=(0, 8))

        self._spark = tk.Canvas(pad, height=44, bg=CARD, highlightthickness=0)
        self._spark.pack(fill="x", pady=(0, 12))

        self._cores = tk.Canvas(pad, height=72, bg=BG, highlightthickness=0)
        self._cores.pack(fill="x")

        tk.Label(pad, text="кто грузит", bg=BG, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", pady=(14, 4))
        self._rows = tk.Frame(pad, bg=BG)
        self._rows.pack(fill="both", expand=True)

        foot = tk.Frame(pad, bg=BG)
        foot.pack(fill="x", side="bottom", pady=(8, 0))
        tk.Label(foot, text=f"v{__version__} · darkshade", bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(side="right")

        self.bind("<Configure>", self._on_resize)
        self.after(20, self._place)
        self.after(400, self._tick)

    def _on_resize(self, event: tk.Event) -> None:
        if event.widget is not self:
            return
        self._hint.configure(wraplength=max(360, event.width - 48))

    def _place(self) -> None:
        self.update_idletasks()
        w, h = self.winfo_width() or 560, self.winfo_height() or 560
        sw = ctypes.windll.user32.GetSystemMetrics(0)
        sh = ctypes.windll.user32.GetSystemMetrics(1)
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 6}")

    def _draw_spark(self) -> None:
        c = self._spark
        c.delete("all")
        w = max(40, c.winfo_width())
        h = 44
        n = len(self._hist)
        if n < 2:
            return
        step = w / max(1, n)
        for i, v in enumerate(self._hist):
            x0 = i * step
            bh = max(1, int(h * v / 100.0))
            c.create_rectangle(x0, h - bh, x0 + step - 1, h, fill=_bar_color(v), outline="")

    def _tick(self) -> None:
        try:
            snap = self._samp.tick()
        except Exception:
            self.after(1000, self._tick)
            return
        self._hist.append(snap.total_pct)
        self._hist = self._hist[-60:]
        self._now.configure(text=f"{snap.total_pct:.0f} %", fg=_bar_color(snap.total_pct))
        self._sub.configure(text=f"{snap.nproc} логических ядер")
        self._draw_spark()

        cv = self._cores
        cv.delete("all")
        cores = snap.cores
        if cores:
            cols = min(10, len(cores))
            rows = (len(cores) + cols - 1) // cols
            w = max(40, cv.winfo_width())
            cell_w = w / cols
            cell_h = 14
            cv.configure(height=max(28, rows * cell_h + 4))
            for i, pct in enumerate(cores):
                r, col = divmod(i, cols)
                x0 = col * cell_w + 2
                y0 = r * cell_h + 2
                bw = max(2, (cell_w - 6) * pct / 100.0)
                cv.create_rectangle(x0, y0, x0 + cell_w - 6, y0 + 10, fill=BAR, outline="")
                cv.create_rectangle(x0, y0, x0 + bw, y0 + 10, fill=_bar_color(pct), outline="")

        for w in self._rows.winfo_children():
            w.destroy()
        if not snap.top:
            tk.Label(self._rows, text="нет данных по процессам", bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w")
        for name, pid, pct in snap.top:
            line = tk.Frame(self._rows, bg=BG)
            line.pack(fill="x", pady=1)
            tk.Label(line, text=f"{pct:5.1f}%", width=8, anchor="e", bg=BG, fg=_bar_color(pct), font=("Consolas", 10)).pack(
                side="left"
            )
            tk.Label(line, text=f"{name}  ·  {pid}", bg=BG, fg=FG, font=("Segoe UI", 9), anchor="w").pack(
                side="left", fill="x", expand=True, padx=8
            )

        self.after(750, self._tick)


def run() -> None:
    CpuPulseApp().mainloop()
