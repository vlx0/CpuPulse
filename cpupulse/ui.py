"""CpuPulse GUI."""

from __future__ import annotations

import ctypes
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from . import __version__
from . import actions
from .cpu import CpuSampler
from .instance import WINDOW_TITLE
from .settings import INTERVALS, load_interval, load_show_cores, save_interval, save_show_cores

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
        self._proc_sec = load_interval()
        self._show_cores = load_show_cores()
        self._last_cores: list[float] = []
        self._cpu_job: str | None = None
        self._proc_job: str | None = None
        self._proc_busy = False
        self._proc_again = False

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Dark.TCombobox",
            fieldbackground=CARD, background=BAR, foreground=FG, arrowcolor=FG,
            darkcolor=CARD, lightcolor=CARD, bordercolor=BAR,
        )
        style.map(
            "Dark.TCombobox",
            fieldbackground=[("readonly", CARD)],
            foreground=[("readonly", FG)],
            background=[("readonly", BAR)],
        )

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

        cores_row = tk.Frame(pad, bg=BG)
        cores_row.pack(fill="x")
        self._cores = tk.Canvas(cores_row, height=72, bg=BG, highlightthickness=0)
        self._cores.pack(side="left", fill="x", expand=True)
        self._eye = tk.Button(
            cores_row,
            text="👁" if self._show_cores else "◌",
            command=self._toggle_eye,
            bg=BG, fg=MUTED if not self._show_cores else ACCENT,
            relief="flat", bd=0, cursor="hand2", font=("Segoe UI Emoji", 12),
            activebackground=BG, activeforeground=FG, padx=6, pady=0,
        )
        self._eye.pack(side="right", padx=(8, 0), anchor="n")

        who = tk.Frame(pad, bg=BG)
        who.pack(fill="x", pady=(14, 4))
        tk.Label(who, text="кто грузит · % от всего CPU", bg=BG, fg=MUTED, font=("Segoe UI", 8)).pack(side="left")
        labels = [lab for _, lab in INTERVALS]
        self._iv_var = tk.StringVar(value=next((lab for sec, lab in INTERVALS if sec == self._proc_sec), "1 с"))
        self._iv = ttk.Combobox(
            who, textvariable=self._iv_var, values=labels, state="readonly",
            width=6, style="Dark.TCombobox", font=("Segoe UI", 9),
        )
        self._iv.pack(side="right")
        self._iv.bind("<<ComboboxSelected>>", lambda _e: self._on_interval())
        tk.Label(who, text="обновление", bg=BG, fg=MUTED, font=("Segoe UI", 8)).pack(side="right", padx=(0, 6))
        self._rows = tk.Frame(pad, bg=BG)
        self._rows.pack(fill="both", expand=True)

        foot = tk.Frame(pad, bg=BG)
        foot.pack(fill="x", side="bottom", pady=(8, 0))
        tk.Label(foot, text=f"v{__version__} · darkshade", bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(side="right")

        self.bind("<Configure>", self._on_resize)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(20, self._place)
        self._cpu_job = self.after(200, self._tick_cpu)
        self._proc_job = self.after(400, self._tick_proc)

    def _toggle_eye(self) -> None:
        self._show_cores = not self._show_cores
        save_show_cores(self._show_cores)
        self._eye.configure(
            text="👁" if self._show_cores else "◌",
            fg=ACCENT if self._show_cores else MUTED,
        )
        self._draw_cores(self._last_cores)

    def _on_interval(self) -> None:
        lab = self._iv_var.get()
        for sec, name in INTERVALS:
            if name == lab:
                self._proc_sec = sec
                save_interval(sec)
                self._schedule_proc(0)
                return

    def _on_resize(self, event: tk.Event) -> None:
        if event.widget is not self:
            return
        self._hint.configure(wraplength=max(360, event.width - 48))
        self._draw_spark()
        self._draw_cores(self._last_cores)

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

    def _draw_cores(self, cores: list[float]) -> None:
        cv = self._cores
        cv.delete("all")
        if not cores:
            return
        cols = min(10, len(cores))
        rows = (len(cores) + cols - 1) // cols
        show = self._show_cores
        cell_h = 26 if show else 14
        cv.configure(height=max(28, rows * cell_h + 4))
        w = max(40, cv.winfo_width())
        cell_w = w / cols
        for i, pct in enumerate(cores):
            r, col = divmod(i, cols)
            x0 = col * cell_w + 2
            y0 = r * cell_h + 2
            bar_w = cell_w - 6
            bw = max(2, bar_w * pct / 100.0)
            cv.create_rectangle(x0, y0, x0 + bar_w, y0 + 10, fill=BAR, outline="")
            cv.create_rectangle(x0, y0, x0 + bw, y0 + 10, fill=_bar_color(pct), outline="")
            if show:
                cv.create_text(
                    x0 + bar_w / 2, y0 + 18,
                    text=str(i), fill=MUTED, font=("Segoe UI", 8),
                )

    def _alive(self) -> bool:
        try:
            return bool(self.winfo_exists())
        except tk.TclError:
            return False

    def _close(self) -> None:
        for job in (self._cpu_job, self._proc_job):
            if job:
                try:
                    self.after_cancel(job)
                except tk.TclError:
                    pass
        self.destroy()

    def _tick_cpu(self) -> None:
        if not self._alive():
            return
        try:
            snap = self._samp.tick()
        except Exception:
            self._cpu_job = self.after(500, self._tick_cpu)
            return
        self._hist.append(snap.total_pct)
        self._hist = self._hist[-60:]
        self._now.configure(text=f"{snap.total_pct:.0f} %", fg=_bar_color(snap.total_pct))
        self._sub.configure(text=f"{snap.nproc} логических ядер")
        self._draw_spark()
        self._last_cores = snap.cores
        self._draw_cores(snap.cores)
        self._cpu_job = self.after(500, self._tick_cpu)

    def _schedule_proc(self, delay_ms: int | None = None) -> None:
        if self._proc_job:
            try:
                self.after_cancel(self._proc_job)
            except tk.TclError:
                pass
            self._proc_job = None
        ms = int(self._proc_sec * 1000) if delay_ms is None else delay_ms
        self._proc_job = self.after(max(0, ms), self._tick_proc)

    def _tick_proc(self) -> None:
        if not self._alive():
            return
        if self._proc_busy:
            self._proc_again = True
            return
        self._proc_busy = True

        def work() -> None:
            try:
                top = self._samp.sample_top()
            except Exception:
                top = []

            def done() -> None:
                self._proc_busy = False
                if not self._alive():
                    return
                self._render_top(top)
                if self._proc_again:
                    self._proc_again = False
                    self._schedule_proc(0)
                else:
                    self._schedule_proc()

            try:
                self.after(0, done)
            except tk.TclError:
                self._proc_busy = False

        threading.Thread(target=work, daemon=True).start()

    def _render_top(self, top: list[tuple[str, int, float]]) -> None:
        for w in self._rows.winfo_children():
            w.destroy()
        if not top:
            tk.Label(self._rows, text="нет данных по процессам", bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w")
            return
        for name, pid, pct in top:
            line = tk.Frame(self._rows, bg=BG)
            line.pack(fill="x", pady=1)
            tk.Label(line, text=f"{pct:5.1f}%", width=8, anchor="e", bg=BG, fg=_bar_color(pct), font=("Consolas", 10)).pack(
                side="left"
            )
            tk.Label(line, text=f"{name}  ·  {pid}", bg=BG, fg=FG, font=("Segoe UI", 9), anchor="w").pack(
                side="left", fill="x", expand=True, padx=8
            )
            btn = tk.Button(
                line, text="⋯",
                bg=BAR, fg=FG, relief="flat", padx=8, pady=0, cursor="hand2",
                activebackground="#444444", activeforeground=FG, font=("Segoe UI", 10),
            )
            btn.configure(command=lambda n=name, p=pid, b=btn: self._proc_menu(n, p, b))
            btn.pack(side="right")

    def _proc_menu(self, name: str, pid: int, anchor: tk.Widget) -> None:
        menu = tk.Menu(self, tearoff=0, bg=CARD, fg=FG, activebackground="#333333", activeforeground=FG, bd=0)
        menu.add_command(label="Снять процесс", command=lambda: self._kill_one(name, pid))
        menu.add_command(label=f"Снять все «{name}»", command=lambda: self._kill_all(name))
        menu.add_command(label="Открыть папку", command=lambda: self._open_dir(pid))
        try:
            menu.tk_popup(anchor.winfo_rootx() + anchor.winfo_width() - 8, anchor.winfo_rooty() + 20)
        finally:
            menu.grab_release()

    def _refresh_procs(self) -> None:
        self._schedule_proc(0)

    def _kill_one(self, name: str, pid: int) -> None:
        if not messagebox.askyesno("Снять процесс", f"Завершить {name} (PID {pid})?"):
            return
        err = actions.kill_pid(pid, name)
        if err:
            messagebox.showerror("CpuPulse", err)
            return
        self._refresh_procs()

    def _kill_all(self, name: str) -> None:
        n = len(actions.pids_named(name))
        if not messagebox.askyesno("Снять все", f"Завершить все процессы «{name}» ({n} шт.)?"):
            return
        killed, err = actions.kill_named(name)
        if err and killed == 0:
            messagebox.showerror("CpuPulse", err)
            return
        if err:
            messagebox.showwarning("CpuPulse", f"снято {killed}, дальше: {err}")
        self._refresh_procs()

    def _open_dir(self, pid: int) -> None:
        err = actions.open_folder(pid)
        if err:
            messagebox.showerror("CpuPulse", err)


def run() -> None:
    CpuPulseApp().mainloop()
