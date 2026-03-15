"""
gui.py – PyProxy dashboard GUI (embedded into a Toplevel by tray_app.py).
Tabs: Request Log | IP Filter | Domain Filter
"""
from __future__ import annotations

import ipaddress
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable, List, Optional

import yaml

# ── Palette ───────────────────────────────────────────────────────────────────
BG      = "#1e1e2e"
BG2     = "#2a2a3e"
BG3     = "#313145"
ACCENT  = "#7c3aed"
GREEN   = "#22c55e"
RED     = "#ef4444"
BLUE    = "#3b82f6"
TEXT    = "#e2e8f0"
TEXT_DIM= "#94a3b8"
BORDER  = "#3f3f5a"
ROW_OK  = "#1e2e1e"
ROW_BLK = "#2e1e1e"
ROW_ERR = "#2e2a1e"
ROW_ALT = "#252535"
YELLOW  = "#eab308"


# ─────────────────────────────────────────────────────────────────────────────
# Small widgets
# ─────────────────────────────────────────────────────────────────────────────

class StatusPill(tk.Canvas):
    def __init__(self, parent, **kw):
        super().__init__(parent, width=120, height=26,
                         bg=BG2, highlightthickness=0, **kw)
        self._active = False
        self._draw()

    def set_active(self, active: bool):
        if active != self._active:
            self._active = active
            self._draw()

    def _draw(self):
        self.delete("all")
        color = GREEN if self._active else "#4b5563"
        label = "● RUNNING" if self._active else "○ STOPPED"
        self.create_oval(6, 5, 20, 20, fill=color, outline="")
        self.create_text(26, 13, anchor="w", text=label,
                         fill=color, font=("Segoe UI", 9, "bold"))


class StatCard(tk.Frame):
    def __init__(self, parent, label: str, **kw):
        super().__init__(parent, bg=BG3, pady=10, padx=14, relief="flat", **kw)
        self._var = tk.StringVar(value="—")
        tk.Label(self, textvariable=self._var, bg=BG3, fg=TEXT,
                 font=("Segoe UI", 18, "bold")).pack()
        tk.Label(self, text=label, bg=BG3, fg=TEXT_DIM,
                 font=("Segoe UI", 8)).pack()

    def set(self, v: str):
        self._var.set(v)


class LogTable(tk.Frame):
    COLS   = ("Time", "Protocol", "Method", "Host", "Port", "Status")
    WIDTHS = (70, 65, 55, 280, 50, 65)

    def __init__(self, parent, **kw):
        super().__init__(parent, bg=BG, **kw)
        s = ttk.Style()
        s.theme_use("clam")
        s.configure("Log.Treeview", background=BG2, foreground=TEXT,
                    fieldbackground=BG2, rowheight=22,
                    font=("Consolas", 9), borderwidth=0)
        s.configure("Log.Treeview.Heading", background=BG3, foreground=TEXT_DIM,
                    font=("Segoe UI", 9, "bold"), relief="flat")
        s.map("Log.Treeview", background=[("selected", ACCENT)])

        self._tree = ttk.Treeview(self, columns=self.COLS,
                                  show="headings", style="Log.Treeview",
                                  selectmode="browse")
        for col, w in zip(self.COLS, self.WIDTHS):
            self._tree.heading(col, text=col)
            self._tree.column(col, width=w, minwidth=w, stretch=(col == "Host"))

        self._tree.tag_configure("ok",      background=ROW_OK)
        self._tree.tag_configure("blocked", background=ROW_BLK)
        self._tree.tag_configure("error",   background=ROW_ERR)
        self._tree.tag_configure("alt",     background=ROW_ALT)

        vsb = ttk.Scrollbar(self, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self._seen = 0

    def update_log(self, records: list):
        new = records[self._seen:]
        for rec in new:
            t   = time.strftime("%H:%M:%S", time.localtime(rec.timestamp))
            tag = rec.status.lower() if rec.status.lower() in ("ok","blocked","error") else "alt"
            if tag == "ok" and self._seen % 2 == 0:
                tag = "alt"
            self._tree.insert("", "end",
                               values=(t, rec.protocol, rec.method,
                                       rec.host, rec.port, rec.status),
                               tags=(tag,))
            self._seen += 1
        if new:
            ch = self._tree.get_children()
            if ch:
                self._tree.see(ch[-1])

    def clear(self):
        self._tree.delete(*self._tree.get_children())
        self._seen = 0


# ─────────────────────────────────────────────────────────────────────────────
# Filter editor (IP and Domain tabs)
# ─────────────────────────────────────────────────────────────────────────────

class FilterEditor(tk.Frame):
    def __init__(self, parent, kind: str, config_path: Path,
                 restart_cb: Callable, **kw):
        super().__init__(parent, bg=BG, **kw)
        self._kind        = kind
        self._config_path = config_path
        self._restart_cb  = restart_cb
        self._conn_listbox = None
        self._build()

    def _build(self):
        btn_kw = dict(font=("Segoe UI", 9, "bold"), relief="flat",
                      cursor="hand2", padx=12, pady=4, bd=0)

        # Top row: mode radio + save button
        top = tk.Frame(self, bg=BG, padx=16, pady=10)
        top.pack(fill="x")

        tk.Label(top, text="Mode:", bg=BG, fg=TEXT_DIM,
                 font=("Segoe UI", 9)).pack(side="left")
        self._mode_var = tk.StringVar(value="none")
        for m in ("none", "allowlist", "blocklist"):
            tk.Radiobutton(top, text=m, variable=self._mode_var, value=m,
                           bg=BG, fg=TEXT, selectcolor=BG3,
                           activebackground=BG, activeforeground=TEXT,
                           font=("Segoe UI", 9),
                           command=self._on_mode_change).pack(side="left", padx=8)

        tk.Button(top, text="💾  Save & Restart", bg=ACCENT, fg="white",
                  command=self._save_and_restart, **btn_kw).pack(side="right")

        # Mode description
        self._desc_var = tk.StringVar()
        tk.Label(self, textvariable=self._desc_var, bg=BG, fg=YELLOW,
                 font=("Segoe UI", 8), anchor="w", padx=16).pack(fill="x")

        # Split: left = rule list, right = live connections
        split = tk.Frame(self, bg=BG, padx=16, pady=6)
        split.pack(fill="both", expand=True)
        split.columnconfigure(0, weight=3)
        split.columnconfigure(1, weight=2)
        split.rowconfigure(0, weight=1)

        # ── Left panel ───────────────────────────────────────────────────────
        left = tk.Frame(split, bg=BG2, padx=10, pady=10)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)

        title = "IP / CIDR Rules" if self._kind == "ip" else "Domain / Wildcard Rules"
        hint  = ("e.g.  192.168.1.5   or   10.0.0.0/8"
                 if self._kind == "ip" else
                 "e.g.  ads.example.com   or   *.tracker.net")

        tk.Label(left, text=title, bg=BG2, fg=TEXT,
                 font=("Segoe UI", 10, "bold")).grid(
                 row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        lf = tk.Frame(left, bg=BG2)
        lf.grid(row=1, column=0, columnspan=2, sticky="nsew")
        lf.rowconfigure(0, weight=1)
        lf.columnconfigure(0, weight=1)

        self._listbox = tk.Listbox(lf, bg=BG3, fg=TEXT,
                                   selectbackground=ACCENT,
                                   font=("Consolas", 10), relief="flat",
                                   bd=0, activestyle="none",
                                   highlightthickness=0)
        vsb = tk.Scrollbar(lf, orient="vertical", command=self._listbox.yview,
                           bg=BG3, troughcolor=BG2)
        self._listbox.configure(yscrollcommand=vsb.set)
        self._listbox.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        er = tk.Frame(left, bg=BG2, pady=6)
        er.grid(row=2, column=0, columnspan=2, sticky="ew")
        er.columnconfigure(0, weight=1)

        self._entry_var = tk.StringVar()
        entry = tk.Entry(er, textvariable=self._entry_var,
                         bg=BG3, fg=TEXT, insertbackground=TEXT,
                         font=("Consolas", 10), relief="flat", bd=4)
        entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        entry.bind("<Return>", lambda _: self._add_rule())

        tk.Button(er, text="＋ Add", bg=GREEN, fg="white",
                  command=self._add_rule, **btn_kw).grid(row=0, column=1)

        tk.Label(left, text=hint, bg=BG2, fg=TEXT_DIM,
                 font=("Segoe UI", 7), anchor="w").grid(
                 row=3, column=0, columnspan=2, sticky="w", pady=(0, 4))

        br = tk.Frame(left, bg=BG2)
        br.grid(row=4, column=0, columnspan=2, sticky="ew")
        tk.Button(br, text="✕ Remove selected", bg=RED, fg="white",
                  command=self._remove_selected, **btn_kw).pack(side="left", padx=(0,6))
        tk.Button(br, text="Clear all", bg=BG3, fg=TEXT_DIM,
                  command=self._clear_all, **btn_kw).pack(side="left")

        # ── Right panel ──────────────────────────────────────────────────────
        right = tk.Frame(split, bg=BG2, padx=10, pady=10)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        panel_title = "Connected IPs" if self._kind == "ip" else "Recent Hosts"
        block_label = "🚫  Block selected IP" if self._kind == "ip" else "🚫  Block selected host"
        hint2 = ("Live client IPs.\nSelect + Block to add to list."
                 if self._kind == "ip" else
                 "Hosts from request log.\nSelect + Block to add to list.")
        fg2 = GREEN if self._kind == "ip" else BLUE

        tk.Label(right, text=panel_title, bg=BG2, fg=TEXT,
                 font=("Segoe UI", 10, "bold")).grid(
                 row=0, column=0, sticky="w", pady=(0, 6))

        cf = tk.Frame(right, bg=BG2)
        cf.grid(row=1, column=0, sticky="nsew")
        cf.rowconfigure(0, weight=1)
        cf.columnconfigure(0, weight=1)

        self._conn_listbox = tk.Listbox(cf, bg=BG3, fg=fg2,
                                        selectbackground=ACCENT,
                                        font=("Consolas", 10), relief="flat",
                                        bd=0, activestyle="none",
                                        highlightthickness=0)
        vsb2 = tk.Scrollbar(cf, orient="vertical",
                             command=self._conn_listbox.yview,
                             bg=BG3, troughcolor=BG2)
        self._conn_listbox.configure(yscrollcommand=vsb2.set)
        self._conn_listbox.grid(row=0, column=0, sticky="nsew")
        vsb2.grid(row=0, column=1, sticky="ns")

        tk.Button(right, text=block_label, bg=RED, fg="white",
                  command=self._block_connected,
                  **btn_kw).grid(row=2, column=0, sticky="ew", pady=(6, 0))

        tk.Label(right, text=hint2, bg=BG2, fg=TEXT_DIM,
                 font=("Segoe UI", 7), justify="left").grid(
                 row=3, column=0, sticky="w", pady=(4, 0))

        self._load_from_config()

    # ── Config ───────────────────────────────────────────────────────────────

    def _load_from_config(self):
        try:
            raw = yaml.safe_load(self._config_path.read_text()) or {}
        except Exception:
            raw = {}
        key     = "ip_filter" if self._kind == "ip" else "domain_filter"
        section = raw.get(key, {}) or {}
        mode    = section.get("mode", "none") or "none"
        items   = section.get("list", []) or []
        self._mode_var.set(mode)
        self._update_desc(mode)
        self._listbox.delete(0, "end")
        for item in items:
            self._listbox.insert("end", str(item))

    def _save_to_config(self) -> bool:
        try:
            raw = yaml.safe_load(self._config_path.read_text()) or {}
        except Exception:
            raw = {}
        key = "ip_filter" if self._kind == "ip" else "domain_filter"
        raw.setdefault(key, {})
        raw[key]["mode"] = self._mode_var.get()
        raw[key]["list"] = list(self._listbox.get(0, "end"))
        try:
            self._config_path.write_text(
                yaml.dump(raw, default_flow_style=False, allow_unicode=True))
            return True
        except Exception as e:
            messagebox.showerror("Save failed", str(e))
            return False

    # ── Rules ────────────────────────────────────────────────────────────────

    def _add_rule(self):
        value = self._entry_var.get().strip()
        if not value:
            return
        if self._kind == "ip":
            try:
                ipaddress.ip_network(value, strict=False)
            except ValueError:
                messagebox.showerror("Invalid entry",
                    f"'{value}' is not a valid IP or CIDR.\n\n"
                    "Examples:\n  192.168.1.5\n  10.0.0.0/8")
                return
        if value in list(self._listbox.get(0, "end")):
            messagebox.showinfo("Duplicate", f"'{value}' is already in the list.")
            return
        self._listbox.insert("end", value)
        self._entry_var.set("")

    def _remove_selected(self):
        sel = self._listbox.curselection()
        if not sel:
            messagebox.showinfo("Nothing selected", "Click a rule first.")
            return
        self._listbox.delete(sel[0])

    def _clear_all(self):
        if self._listbox.size() and messagebox.askyesno("Clear all", "Remove all rules?"):
            self._listbox.delete(0, "end")

    def _block_connected(self):
        if self._conn_listbox is None:
            return
        sel = self._conn_listbox.curselection()
        if not sel:
            messagebox.showinfo("Nothing selected",
                                "Select an item from the right panel first.")
            return
        value = self._conn_listbox.get(sel[0]).strip()
        if self._kind == "ip" and ":" in value:
            value = value.split(":")[0]
        if value in list(self._listbox.get(0, "end")):
            messagebox.showinfo("Duplicate", f"'{value}' is already in the list.")
            return
        if self._mode_var.get() == "none":
            self._mode_var.set("blocklist")
            self._update_desc("blocklist")
        self._listbox.insert("end", value)

    # ── Mode ─────────────────────────────────────────────────────────────────

    def _on_mode_change(self):
        self._update_desc(self._mode_var.get())

    def _update_desc(self, mode: str):
        descs = {
            "none":      "⬜  No filtering — all traffic is allowed.",
            "allowlist": "✅  Only listed entries are ALLOWED. Everything else is blocked.",
            "blocklist": "🚫  Listed entries are BLOCKED. Everything else is allowed.",
        }
        self._desc_var.set(descs.get(mode, ""))

    # ── Save & Restart ────────────────────────────────────────────────────────

    def _save_and_restart(self):
        if self._save_to_config():
            threading.Thread(target=self._restart_cb, daemon=True).start()

    # ── Live update ──────────────────────────────────────────────────────────

    def update_connected(self, items: List[str]):
        if self._conn_listbox is None:
            return
        current = set(self._conn_listbox.get(0, "end"))
        new_set = set(items)
        if current != new_set:
            self._conn_listbox.delete(0, "end")
            for item in sorted(new_set):
                self._conn_listbox.insert("end", item)


# ─────────────────────────────────────────────────────────────────────────────
# Main ProxyGUI class
# ─────────────────────────────────────────────────────────────────────────────

class ProxyGUI:
    def __init__(
        self,
        start_cb: Callable,
        stop_cb: Callable,
        is_running_cb: Callable[[], bool],
        get_stats_cb: Callable[[], dict],
        config_path: Path,
        log_path: Path,
    ):
        self._start_cb    = start_cb
        self._stop_cb     = stop_cb
        self._is_running  = is_running_cb
        self._get_stats   = get_stats_cb
        self._config_path = config_path
        self._log_path    = log_path

        self._root: Optional[tk.Misc] = None
        self._running = False

        # sub-widgets set in _build_ui
        self._status_pill   = None
        self._btn_start     = None
        self._btn_stop      = None
        self._btn_restart   = None
        self._cards         = {}
        self._log_table     = None
        self._log_count_var = None
        self._statusbar_var = None
        self._ip_editor     = None
        self._dom_editor    = None

    # ── embed() called by tray_app ────────────────────────────────────────────

    def embed(self, window: tk.Toplevel):
        """Attach all UI into an existing Toplevel. Must be called on main thread."""
        self._root = window
        self._build_ui(window)
        self._running = True
        self._schedule_refresh()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self, root: tk.Misc):
        btn_kw = dict(font=("Segoe UI", 9, "bold"), relief="flat",
                      cursor="hand2", padx=14, pady=5, bd=0)

        # Header
        header = tk.Frame(root, bg=BG2, pady=10, padx=16)
        header.pack(fill="x")
        tk.Label(header, text="PyProxy", bg=BG2, fg=TEXT,
                 font=("Segoe UI", 16, "bold")).pack(side="left")
        tk.Label(header, text="  Dashboard", bg=BG2, fg=TEXT_DIM,
                 font=("Segoe UI", 11)).pack(side="left")
        self._status_pill = StatusPill(header)
        self._status_pill.pack(side="right", padx=4)

        # Control bar
        ctrl = tk.Frame(root, bg=BG, pady=8, padx=16)
        ctrl.pack(fill="x")

        self._btn_start   = tk.Button(ctrl, text="▶  Start",   bg=GREEN,  fg="white", command=self._on_start,   **btn_kw)
        self._btn_stop    = tk.Button(ctrl, text="■  Stop",    bg=RED,    fg="white", command=self._on_stop,    **btn_kw)
        self._btn_restart = tk.Button(ctrl, text="↺  Restart", bg=ACCENT, fg="white", command=self._on_restart, **btn_kw)
        self._btn_start.pack(side="left",   padx=(0, 6))
        self._btn_stop.pack(side="left",    padx=(0, 6))
        self._btn_restart.pack(side="left", padx=(0, 16))

        tk.Button(ctrl, text="⚙  Config", bg=BG3, fg=TEXT,
                  command=self._open_config, **btn_kw).pack(side="left", padx=(0, 6))
        tk.Button(ctrl, text="📄  Log", bg=BG3, fg=TEXT,
                  command=self._open_log, **btn_kw).pack(side="left")
        tk.Button(ctrl, text="🗑  Clear Log", bg=BG3, fg=TEXT_DIM,
                  command=self._clear_log, **btn_kw).pack(side="right")

        # Stat cards
        cf = tk.Frame(root, bg=BG, padx=16)
        cf.pack(fill="x", pady=(0, 8))
        for i, lbl in enumerate(["Uptime","Requests","Blocked","Cache Hits",
                                  "Data Sent","Active Conn","Peak Conn"]):
            c = StatCard(cf, lbl)
            c.grid(row=0, column=i, padx=4, sticky="nsew")
            cf.columnconfigure(i, weight=1)
            self._cards[lbl] = c

        tk.Frame(root, bg=BORDER, height=1).pack(fill="x", padx=16)

        # Notebook
        style = ttk.Style()
        style.configure("Dark.TNotebook",     background=BG, borderwidth=0)
        style.configure("Dark.TNotebook.Tab", background=BG3, foreground=TEXT_DIM,
                        padding=[14, 6], font=("Segoe UI", 9))
        style.map("Dark.TNotebook.Tab",
                  background=[("selected", BG2)],
                  foreground=[("selected", TEXT)])

        nb = ttk.Notebook(root, style="Dark.TNotebook")
        nb.pack(fill="both", expand=True)

        # Tab 1 – Request Log
        log_tab = tk.Frame(nb, bg=BG)
        nb.add(log_tab, text="  📋  Request Log  ")

        lh = tk.Frame(log_tab, bg=BG, padx=16, pady=6)
        lh.pack(fill="x")
        tk.Label(lh, text="Request Log", bg=BG, fg=TEXT_DIM,
                 font=("Segoe UI", 9, "bold")).pack(side="left")
        self._log_count_var = tk.StringVar(value="")
        tk.Label(lh, textvariable=self._log_count_var, bg=BG, fg=TEXT_DIM,
                 font=("Segoe UI", 8)).pack(side="right")

        tf = tk.Frame(log_tab, bg=BG, padx=16, pady=(0, 8))
        tf.pack(fill="both", expand=True)
        self._log_table = LogTable(tf)
        self._log_table.pack(fill="both", expand=True)

        # Tab 2 – IP Filter
        ip_tab = tk.Frame(nb, bg=BG)
        nb.add(ip_tab, text="  🛡  IP Filter  ")
        self._ip_editor = FilterEditor(ip_tab, kind="ip",
                                       config_path=self._config_path,
                                       restart_cb=self._do_restart)
        self._ip_editor.pack(fill="both", expand=True)

        # Tab 3 – Domain Filter
        dom_tab = tk.Frame(nb, bg=BG)
        nb.add(dom_tab, text="  🌐  Domain Filter  ")
        self._dom_editor = FilterEditor(dom_tab, kind="domain",
                                        config_path=self._config_path,
                                        restart_cb=self._do_restart)
        self._dom_editor.pack(fill="both", expand=True)

        # Status bar
        self._statusbar_var = tk.StringVar(value="Ready")
        tk.Label(root, textvariable=self._statusbar_var, bg=BG3, fg=TEXT_DIM,
                 font=("Segoe UI", 8), anchor="w", padx=10, pady=3
                 ).pack(fill="x", side="bottom")

    # ── Refresh ───────────────────────────────────────────────────────────────

    def _schedule_refresh(self):
        if self._running and self._root:
            try:
                if not self._root.winfo_exists():
                    self._running = False
                    return
            except Exception:
                self._running = False
                return
            self._refresh()
            self._root.after(1000, self._schedule_refresh)

    def _refresh(self):
        running = self._is_running()

        self._status_pill.set_active(running)
        self._btn_start.config(  state="disabled" if running else "normal")
        self._btn_stop.config(   state="normal"   if running else "disabled")
        self._btn_restart.config(state="normal"   if running else "disabled")

        snap = self._get_stats()
        self._cards["Uptime"].set(snap["uptime_str"])
        self._cards["Requests"].set(str(snap["total_requests"]))
        self._cards["Blocked"].set(str(snap["blocked_requests"]))
        self._cards["Cache Hits"].set(str(snap["cache_hits"]))
        self._cards["Data Sent"].set(snap["total_bytes_str"])
        self._cards["Active Conn"].set(str(snap["active_connections"]))
        self._cards["Peak Conn"].set(str(snap["peak_connections"]))

        self._log_table.update_log(snap["log"])
        self._log_count_var.set(f"{snap['total_requests']} total requests")

        # Feed live data to filter panels
        hosts = list({r.host for r in snap["log"]})
        if self._ip_editor:
            self._ip_editor.update_connected(hosts)
        if self._dom_editor:
            self._dom_editor.update_connected(hosts)

        try:
            from proxy.config import load_config as _lc
            port  = _lc(str(self._config_path)).server.port
            state = "running" if running else "stopped"
            self._statusbar_var.set(
                f"  Proxy {state}  |  Address: 127.0.0.1:{port}  |  "
                f"Uptime: {snap['uptime_str']}  |  Requests: {snap['total_requests']}"
            )
        except Exception:
            pass

    # ── Handlers ─────────────────────────────────────────────────────────────

    def _on_start(self):
        self._statusbar_var.set("  Starting proxy…")
        threading.Thread(target=self._start_cb, daemon=True).start()

    def _on_stop(self):
        self._statusbar_var.set("  Stopping proxy…")
        threading.Thread(target=self._stop_cb, daemon=True).start()

    def _on_restart(self):
        self._statusbar_var.set("  Restarting…")
        threading.Thread(target=self._do_restart, daemon=True).start()

    def _do_restart(self):
        self._stop_cb()
        time.sleep(0.5)
        self._start_cb()

    def _open_config(self):
        if not self._config_path.exists():
            messagebox.showinfo("Not found", str(self._config_path))
            return
        if sys.platform == "win32":
            os.startfile(str(self._config_path))
        else:
            subprocess.Popen(["xdg-open", str(self._config_path)])

    def _open_log(self):
        if not self._log_path.exists():
            self._log_path.touch()
        if sys.platform == "win32":
            os.startfile(str(self._log_path))
        else:
            subprocess.Popen(["xdg-open", str(self._log_path)])

    def _clear_log(self):
        self._log_table.clear()
        from proxy.stats import STATS
        STATS.reset()