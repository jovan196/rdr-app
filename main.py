"""RDR Studio — antarmuka grafis (GUI) untuk sistem rekomendasi RDR.

Seluruh logika inti (inferensi, validasi, update knowledge) berada di
rdr_core.py; modul ini hanya menggambar antarmuka dan memanggil RDREngine.
Run with: python main.py
"""
from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable, Optional

from rdr_core import (
    APP_TITLE,
    APP_VERSION,
    CATEGORICAL_OPERATORS,
    NUMERIC_OPERATORS,
    OPERATOR_SYMBOLS,
    RDREngine,
    attribute_is_referenced,
    condition_text,
    find_node,
    parse_attribute,
)

SYMBOL_TO_OPERATOR = {v: k for k, v in OPERATOR_SYMBOLS.items()}


class AttributeDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, existing: Optional[dict[str, Any]] = None):
        super().__init__(parent)
        self.title("Atribut kasus")
        self.resizable(False, False)
        self.result: Optional[dict[str, Any]] = None
        existing = existing or {"name": "", "type": "categorical", "choices": []}
        self.name_var = tk.StringVar(value=existing.get("name", ""))
        self.type_var = tk.StringVar(value=existing.get("type", "categorical"))
        self.choices_var = tk.StringVar(value=", ".join(existing.get("choices", [])))

        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Nama atribut", style="Field.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 4))
        name_entry = ttk.Entry(body, textvariable=self.name_var, width=38)
        name_entry.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        ttk.Label(body, text="Jenis data", style="Field.TLabel").grid(row=2, column=0, sticky="w", pady=(0, 4))
        kind = ttk.Combobox(body, textvariable=self.type_var, values=["numeric", "categorical"], state="readonly", width=35)
        kind.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        ttk.Label(body, text="Pilihan kategori (opsional untuk kategorikal, pisahkan dengan koma)", style="Field.TLabel").grid(row=4, column=0, sticky="w", pady=(0, 4))
        self.choices_entry = ttk.Entry(body, textvariable=self.choices_var, width=38)
        self.choices_entry.grid(row=5, column=0, sticky="ew")
        ttk.Label(body, text="Contoh: Kantor, Kuliah, Desain, Gaming (kosongkan jika teks bebas)", style="Hint.TLabel").grid(row=6, column=0, sticky="w", pady=(4, 14))
        kind.bind("<<ComboboxSelected>>", self._toggle_choices)
        self._toggle_choices()

        buttons = ttk.Frame(body)
        buttons.grid(row=7, column=0, sticky="e")
        ttk.Button(buttons, text="Batal", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="Simpan", style="Accent.TButton", command=self.save).pack(side="right")
        self.bind("<Return>", lambda _e: self.save())
        self.transient(parent)
        self.grab_set()
        name_entry.focus_set()
        self.wait_visibility()
        self.geometry(f"+{parent.winfo_rootx()+100}+{parent.winfo_rooty()+100}")

    def _toggle_choices(self, _event=None):
        if self.type_var.get() == "numeric":
            self.choices_entry.configure(state="disabled")
        else:
            self.choices_entry.configure(state="normal")

    def save(self):
        try:
            self.result = parse_attribute(self.name_var.get(), self.type_var.get(), self.choices_var.get())
        except ValueError as exc:
            messagebox.showwarning("Validasi", str(exc), parent=self)
            return
        self.destroy()


class ScrollFrame(ttk.Frame):
    """Frame dengan scroll vertikal (pola standar Canvas + Scrollbar Tkinter)."""

    def __init__(self, parent: tk.Misc):
        super().__init__(parent, style="Card.TFrame")
        self.canvas = tk.Canvas(self, bg="#ffffff", highlightthickness=0, bd=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.inner = ttk.Frame(self.canvas, style="Card.TFrame")
        self._inner_window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.bind_all("<MouseWheel>", self._on_mousewheel, add="+")

    def _on_inner_configure(self, _event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self._inner_window, width=event.width)

    def _on_mousewheel(self, event):
        if not self.winfo_exists():
            return
        widget = self.winfo_containing(event.x_root, event.y_root)
        while widget is not None:
            if widget is self.canvas:
                self.canvas.yview_scroll(int(-event.delta / 120), "units")
                return
            widget = getattr(widget, "master", None)

    def scroll_to_bottom(self):
        self.inner.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.canvas.yview_moveto(1.0)


class BinaryTreeCanvas(ttk.Frame):
    """Visualisasi diagram pohon biner RDR: Kiri = false-child, Kanan = true-child."""

    NODE_W = 186
    NODE_H = 64
    H_GAP = 26
    V_GAP = 72
    EMPTY_BRANCH_OFFSET = 64

    def __init__(self, parent: tk.Misc, on_select: Callable[[str], None]):
        super().__init__(parent, style="Card.TFrame")
        self.on_select = on_select
        self.selected_id: Optional[str] = None
        self._root_data: Optional[dict[str, Any]] = None
        self._trace_ids: set[str] = set()
        self._active_id: Optional[str] = None

        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, bg="#f8fafc", highlightthickness=1, highlightbackground="#e2e8f0")
        self.v_scroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.h_scroll = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.v_scroll.set, xscrollcommand=self.h_scroll.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.v_scroll.grid(row=0, column=1, sticky="ns")
        self.h_scroll.grid(row=1, column=0, sticky="ew")

    def render(
        self,
        root: dict[str, Any],
        trace: Optional[list[dict[str, Any]]] = None,
        active_node_id: Optional[str] = None,
        selected_id: Optional[str] = None,
    ):
        self._root_data = root
        self._trace_ids = {step["node_id"] for step in (trace or [])}
        self._active_id = active_node_id
        if selected_id is not None:
            self.selected_id = selected_id
        self._redraw()

    def set_selected(self, node_id: Optional[str]):
        self.selected_id = node_id
        if self._root_data is not None:
            self._redraw()

    def _measure_widths(self, node: Optional[dict[str, Any]], widths: dict[str, int]) -> int:
        if node is None:
            return 0
        left_child = node.get("false_child")
        right_child = node.get("true_child")
        lw = self._measure_widths(left_child, widths)
        rw = self._measure_widths(right_child, widths)
        if lw == 0 and rw == 0:
            total = self.NODE_W
        elif lw == 0:
            total = self.EMPTY_BRANCH_OFFSET + self.H_GAP + rw
        elif rw == 0:
            total = lw + self.H_GAP + self.EMPTY_BRANCH_OFFSET
        else:
            total = lw + self.H_GAP + rw
        total = max(total, self.NODE_W)
        widths[node["id"]] = total
        return total

    def _assign_positions(
        self,
        node: Optional[dict[str, Any]],
        x_left: float,
        depth: int,
        widths: dict[str, int],
        positions: dict[str, tuple[float, float]],
    ):
        if node is None:
            return
        left_child = node.get("false_child")
        right_child = node.get("true_child")
        lw = widths.get(left_child["id"], 0) if left_child else 0
        rw = widths.get(right_child["id"], 0) if right_child else 0
        y = 36 + depth * (self.NODE_H + self.V_GAP)

        if lw == 0 and rw == 0:
            cx = x_left + widths[node["id"]] / 2.0
        elif lw == 0:
            right_start = x_left + self.EMPTY_BRANCH_OFFSET + self.H_GAP
            self._assign_positions(right_child, right_start, depth + 1, widths, positions)
            rcx, _ = positions[right_child["id"]]  # type: ignore[index]
            cx = max(x_left + self.NODE_W / 2.0, rcx - (self.NODE_W / 2.0 + 18))
        elif rw == 0:
            self._assign_positions(left_child, x_left, depth + 1, widths, positions)
            lcx, _ = positions[left_child["id"]]  # type: ignore[index]
            cx = min(x_left + widths[node["id"]] - self.NODE_W / 2.0, lcx + (self.NODE_W / 2.0 + 18))
        else:
            self._assign_positions(left_child, x_left, depth + 1, widths, positions)
            right_start = x_left + lw + self.H_GAP
            self._assign_positions(right_child, right_start, depth + 1, widths, positions)
            lcx, _ = positions[left_child["id"]]  # type: ignore[index]
            rcx, _ = positions[right_child["id"]]  # type: ignore[index]
            cx = (lcx + rcx) / 2.0

        positions[node["id"]] = (cx, y)

    def _redraw(self):
        self.canvas.delete("all")
        root = self._root_data
        if not root:
            return
        widths: dict[str, int] = {}
        total_w = self._measure_widths(root, widths)
        positions: dict[str, tuple[float, float]] = {}
        margin_x = 32
        self._assign_positions(root, margin_x, 0, widths, positions)

        # Gambar garis cabang terlebih dahulu (Kiri = FALSE, Kanan = TRUE)
        def draw_edges(node: dict[str, Any]):
            cx, top_y = positions[node["id"]]
            start_y = top_y + self.NODE_H
            false_child = node.get("false_child")
            if false_child:
                fcx, fty = positions[false_child["id"]]
                on_path = node["id"] in self._trace_ids and false_child["id"] in self._trace_ids
                color = "#d97706" if on_path else "#94a3b8"
                width = 2.5 if on_path else 1.6
                self.canvas.create_line(cx - 18, start_y, fcx, fty, fill=color, width=width, arrow=tk.LAST)
                mx, my = (cx - 18 + fcx) / 2.0 - 18, (start_y + fty) / 2.0 - 6
                self.canvas.create_text(mx, my, text="KIRI (False)", fill="#b45309", font=("Segoe UI", 8, "bold"))
                draw_edges(false_child)

            true_child = node.get("true_child")
            if true_child:
                tcx, tty = positions[true_child["id"]]
                on_path = node["id"] in self._trace_ids and true_child["id"] in self._trace_ids
                color = "#15803d" if on_path else "#64748b"
                width = 2.5 if on_path else 1.6
                self.canvas.create_line(cx + 18, start_y, tcx, tty, fill=color, width=width, arrow=tk.LAST)
                mx, my = (cx + 18 + tcx) / 2.0 + 22, (start_y + tty) / 2.0 - 6
                self.canvas.create_text(mx, my, text="KANAN (True)", fill="#15803d", font=("Segoe UI", 8, "bold"))
                draw_edges(true_child)

        draw_edges(root)

        # Gambar kotak node
        def draw_nodes(node: dict[str, Any]):
            nid = node["id"]
            cx, top_y = positions[nid]
            x1 = cx - self.NODE_W / 2.0
            y1 = top_y
            x2 = cx + self.NODE_W / 2.0
            y2 = top_y + self.NODE_H

            is_active = nid == self._active_id
            in_trace = nid in self._trace_ids
            is_selected = nid == self.selected_id

            if is_active:
                fill, outline, badge = "#ecfdf5", "#10b981", " ★ AKTIF"
            elif in_trace:
                fill, outline, badge = "#eff6ff", "#3b82f6", " • Ditelusuri"
            else:
                fill, outline, badge = "#ffffff", "#cbd5e1", ""

            border_w = 2.8 if is_selected else (2.2 if (is_active or in_trace) else 1.3)
            if is_selected:
                outline = "#1d4ed8"

            tag = f"node_{nid}"
            self.canvas.create_rectangle(x1, y1, x2, y2, fill=fill, outline=outline, width=border_w, tags=(tag,))
            cond_str = condition_text(node["condition"])
            if len(cond_str) > 25:
                cond_str = cond_str[:23] + "…"
            conc_str = node.get("conclusion", "").replace("\n", " ")
            if len(conc_str) > 26:
                conc_str = conc_str[:24] + "…"

            self.canvas.create_text(
                x1 + 10, y1 + 14, anchor="w",
                text=f"{nid}{badge}", fill="#0f172a", font=("Segoe UI", 9, "bold"), tags=(tag,)
            )
            self.canvas.create_text(
                x1 + 10, y1 + 33, anchor="w",
                text=f"Jika: {cond_str}", fill="#334e68", font=("Segoe UI", 8), tags=(tag,)
            )
            self.canvas.create_text(
                x1 + 10, y1 + 50, anchor="w",
                text=f"→ {conc_str}", fill="#486581", font=("Segoe UI", 8, "italic"), tags=(tag,)
            )
            self.canvas.tag_bind(tag, "<Button-1>", lambda _e, target=nid: self.on_select(target))

            if node.get("false_child"):
                draw_nodes(node["false_child"])
            if node.get("true_child"):
                draw_nodes(node["true_child"])

        draw_nodes(root)
        max_y = max(y for _, y in positions.values()) + self.NODE_H + 36
        self.canvas.configure(scrollregion=(0, 0, total_w + margin_x * 2, max_y))


class RDRApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1320x840")
        self.minsize(1100, 720)
        self.configure(bg="#f3f6fb")
        self.engine = RDREngine()
        self.current_path: Optional[Path] = None
        self.case_vars: dict[str, tk.StringVar] = {}
        self.case_widgets: dict[str, ttk.Widget] = {}
        self.candidate_vars: list[tk.BooleanVar] = []
        self._build_style()
        self._build_menu()
        self._build_shell()
        self.refresh_all()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    @property
    def kb(self) -> dict[str, Any]:
        """Jalan pintas ke knowledge base yang dikelola engine."""
        return self.engine.kb

    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background="#f3f6fb")
        style.configure("Card.TFrame", background="#ffffff", relief="flat")
        style.configure("Subtle.TFrame", background="#f8fafc", relief="solid", borderwidth=1)
        style.configure("TLabel", background="#f3f6fb", foreground="#1f2937", font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"), foreground="#102a43", background="#f3f6fb")
        style.configure("SubTitle.TLabel", font=("Segoe UI", 10), foreground="#627d98", background="#f3f6fb")
        style.configure("CardTitle.TLabel", font=("Segoe UI", 11, "bold"), foreground="#243b53", background="#ffffff")
        style.configure("Field.TLabel", font=("Segoe UI", 9, "bold"), foreground="#486581", background="#ffffff")
        style.configure("Hint.TLabel", font=("Segoe UI", 8), foreground="#627d98", background="#ffffff")
        style.configure("TCheckbutton", background="#ffffff", foreground="#1f2937", font=("Segoe UI", 9))
        style.map("TCheckbutton", background=[("active", "#f1f5f9")])
        style.configure("TButton", font=("Segoe UI", 9), padding=(10, 7))
        style.configure("Accent.TButton", background="#2463eb", foreground="#ffffff", font=("Segoe UI", 9, "bold"))
        style.map("Accent.TButton", background=[("active", "#1748bd"), ("disabled", "#a7b9d5")])
        style.configure("Success.TButton", background="#138a64", foreground="#ffffff", font=("Segoe UI", 9, "bold"))
        style.map("Success.TButton", background=[("active", "#0e6b4e"), ("disabled", "#9bcbb9")])
        style.configure("Danger.TButton", foreground="#b42318", font=("Segoe UI", 9, "bold"))
        style.configure("Treeview", rowheight=26, font=("Segoe UI", 9), background="#ffffff", fieldbackground="#ffffff")
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"), background="#eaf0f8", foreground="#334e68")
        style.configure("TNotebook", background="#f3f6fb", borderwidth=0)
        style.configure("TNotebook.Tab", font=("Segoe UI", 9, "bold"), padding=(16, 10))
        style.map("TNotebook.Tab", background=[("selected", "#ffffff")], foreground=[("selected", "#1748bd")])

    def _build_menu(self):
        menu = tk.Menu(self)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="Knowledge Base Baru (Kosong)", command=self.new_kb)
        file_menu.add_command(label="Muat Contoh Domain Laptop", command=self.reset_sample_kb)
        file_menu.add_separator()
        file_menu.add_command(label="Buka Knowledge Base…", command=self.open_kb, accelerator="Ctrl+O")
        file_menu.add_command(label="Simpan", command=self.save_kb, accelerator="Ctrl+S")
        file_menu.add_command(label="Simpan Sebagai…", command=self.save_kb_as)
        file_menu.add_separator()
        file_menu.add_command(label="Keluar", command=self.on_close)
        menu.add_cascade(label="File", menu=file_menu)
        help_menu = tk.Menu(menu, tearoff=False)
        help_menu.add_command(label="Tentang RDR Studio", command=self.show_about)
        menu.add_cascade(label="Bantuan", menu=help_menu)
        self.config(menu=menu)
        self.bind_all("<Control-o>", lambda _e: self.open_kb())
        self.bind_all("<Control-s>", lambda _e: self.save_kb())

    def _build_shell(self):
        header = ttk.Frame(self, padding=(24, 18, 24, 12))
        header.pack(fill="x")
        left = ttk.Frame(header)
        left.pack(side="left", fill="x", expand=True)
        ttk.Label(left, text="RDR STUDIO", style="Title.TLabel").pack(anchor="w")
        ttk.Label(left, text="Ripple Down Rules • Sistem rekomendasi AI berbasis pengetahuan pakar", style="SubTitle.TLabel").pack(anchor="w", pady=(2, 0))
        right = ttk.Frame(header)
        right.pack(side="right")
        self.status_var = tk.StringVar(value="Knowledge base siap digunakan (1 rule awal: t → kesimpulan default)")
        ttk.Label(right, textvariable=self.status_var, style="SubTitle.TLabel").pack(anchor="e")
        ttk.Label(right, text=f"Versi {APP_VERSION}", style="Hint.TLabel").pack(anchor="e", pady=(4, 0))

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=24, pady=(0, 16))
        self.consult_tab = ttk.Frame(self.notebook, padding=16)
        self.kb_tab = ttk.Frame(self.notebook, padding=16)
        self.tree_tab = ttk.Frame(self.notebook, padding=16)
        self.help_tab = ttk.Frame(self.notebook, padding=16)
        self.notebook.add(self.consult_tab, text="  Konsultasi Konsumen  ")
        self.notebook.add(self.kb_tab, text="  Basis Pengetahuan  ")
        self.notebook.add(self.tree_tab, text="  Pohon Biner RDR  ")
        self.notebook.add(self.help_tab, text="  Panduan  ")
        self._build_consult_tab()
        self._build_kb_tab()
        self._build_tree_tab()
        self._build_help_tab()

    def _build_consult_tab(self):
        self.consult_tab.columnconfigure(0, weight=1)
        self.consult_tab.columnconfigure(1, weight=1)
        self.consult_tab.rowconfigure(0, weight=1)
        form_card = ttk.Frame(self.consult_tab, style="Card.TFrame", padding=16)
        form_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        result_card = ttk.Frame(self.consult_tab, style="Card.TFrame", padding=16)
        result_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        ttk.Label(form_card, text="Data konsumen", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(form_card, text="Isi atribut konsumen (numerik / kategorikal), lalu jalankan penelusuran pohon biner RDR.", style="Hint.TLabel").pack(anchor="w", pady=(3, 12))
        name_row = ttk.Frame(form_card, style="Card.TFrame")
        name_row.pack(fill="x", pady=(0, 10))
        ttk.Label(name_row, text="Nama konsumen (opsional)", style="Field.TLabel").pack(anchor="w", pady=(0, 4))
        self.customer_name_var = tk.StringVar()
        ttk.Entry(name_row, textvariable=self.customer_name_var).pack(fill="x")
        self.attributes_form = ttk.Frame(form_card, style="Card.TFrame")
        self.attributes_form.pack(fill="both", expand=True)
        self.consult_button_row = ttk.Frame(form_card, style="Card.TFrame")
        self.consult_button_row.pack(fill="x", pady=(14, 0))
        ttk.Button(self.consult_button_row, text="Jalankan konsultasi", style="Accent.TButton", command=self.run_consultation).pack(side="left")
        ttk.Button(self.consult_button_row, text="Kosongkan form", command=self.clear_form).pack(side="left", padx=(8, 0))

        self.result_scroll = ScrollFrame(result_card)
        self.result_scroll.pack(fill="both", expand=True)
        result_body = self.result_scroll.inner

        ttk.Label(result_body, text="Hasil rekomendasi & penalaran RDR", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(
            result_body,
            text="Sistem memberikan kesimpulan terakhir yang diperoleh saat menelusuri pohon biner (kesimpulan sebelumnya dianulir).",
            style="Hint.TLabel", wraplength=520, justify="left"
        ).pack(anchor="w", pady=(3, 10))
        self.result_domain_var = tk.StringVar(value="Belum ada konsultasi")
        ttk.Label(result_body, textvariable=self.result_domain_var, style="Field.TLabel").pack(anchor="w", pady=(0, 5))
        self.result_text = tk.Text(result_body, height=4, wrap="word", font=("Segoe UI", 10), bg="#f7f9fc", fg="#243b53", relief="flat", padx=12, pady=10)
        self.result_text.pack(fill="x")
        self.result_text.insert("1.0", "Jalankan konsultasi untuk melihat kesimpulan rekomendasi dari knowledge base.")
        self.result_text.configure(state="disabled")

        ttk.Label(result_body, text="Jejak penelusuran pohon biner (Kanan = True / Perkecualian, Kiri = False)", style="Field.TLabel").pack(anchor="w", pady=(12, 5))
        self.trace_text = tk.Text(result_body, height=6, wrap="word", font=("Consolas", 9), bg="#f7f9fc", fg="#486581", relief="flat", padx=10, pady=8)
        self.trace_text.pack(fill="x", expand=False)
        self.trace_text.insert("1.0", "Belum ada jejak penelusuran.")
        self.trace_text.configure(state="disabled")

        self.feedback_frame = ttk.Frame(result_body, style="Card.TFrame")
        self.feedback_frame.pack(fill="x", pady=(12, 0))
        ttk.Label(self.feedback_frame, text="Evaluasi Pakar", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 3))
        ttk.Label(
            self.feedback_frame,
            text="Jika pakar setuju, rekomendasi diberikan ke konsumen dan proses selesai. Jika tidak sesuai, buat rule perkecualian baru.",
            style="Hint.TLabel", wraplength=520, justify="left"
        ).pack(anchor="w", pady=(0, 8))
        buttons = ttk.Frame(self.feedback_frame, style="Card.TFrame")
        buttons.pack(fill="x")
        self.accept_button = ttk.Button(buttons, text="✓ Pakar Setuju (Selesai)", style="Success.TButton", command=self.accept_result, state="disabled")
        self.accept_button.pack(side="left")
        self.reject_button = ttk.Button(buttons, text="✗ Tidak Sesuai · Buat Rule Perkecualian", style="Danger.TButton", command=self.reject_result, state="disabled")
        self.reject_button.pack(side="left", padx=(8, 0))
        self.rule_editor = ttk.Frame(result_body, style="Card.TFrame")
        self.rule_editor.pack(fill="x", pady=(12, 0))

    def _build_kb_tab(self):
        self.kb_tab.columnconfigure(0, weight=1)
        self.kb_tab.rowconfigure(1, weight=1)
        config_card = ttk.Frame(self.kb_tab, style="Card.TFrame", padding=16)
        config_card.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        config_card.columnconfigure(1, weight=1)
        ttk.Label(config_card, text="Pengaturan domain dan kesimpulan default (Rule awal R0: t → kesimpulan default)", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        ttk.Label(config_card, text="Domain masalah", style="Field.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=5)
        self.domain_var = tk.StringVar()
        ttk.Entry(config_card, textvariable=self.domain_var).grid(row=1, column=1, sticky="ew", pady=5)
        ttk.Label(config_card, text="Kesimpulan default (R0)", style="Field.TLabel").grid(row=2, column=0, sticky="nw", padx=(0, 12), pady=5)
        self.default_text = tk.Text(config_card, height=3, wrap="word", font=("Segoe UI", 9), relief="solid", bd=1)
        self.default_text.grid(row=2, column=1, sticky="ew", pady=5)
        ttk.Button(config_card, text="Terapkan pengaturan", style="Accent.TButton", command=self.apply_kb_settings).grid(row=3, column=1, sticky="e", pady=(8, 0))

        attr_card = ttk.Frame(self.kb_tab, style="Card.TFrame", padding=16)
        attr_card.grid(row=1, column=0, sticky="nsew")
        attr_card.rowconfigure(1, weight=1)
        attr_card.columnconfigure(0, weight=1)
        top = ttk.Frame(attr_card, style="Card.TFrame")
        top.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(top, text="Daftar atribut kasus (numerik & kategorikal)", style="CardTitle.TLabel").pack(side="left")
        actions = ttk.Frame(top, style="Card.TFrame")
        actions.pack(side="right")
        ttk.Button(actions, text="+ Tambah atribut", style="Accent.TButton", command=self.add_attribute).pack(side="left")
        ttk.Button(actions, text="Edit", command=self.edit_attribute).pack(side="left", padx=(6, 0))
        ttk.Button(actions, text="Hapus", style="Danger.TButton", command=self.delete_attribute).pack(side="left", padx=(6, 0))
        self.attr_tree = ttk.Treeview(attr_card, columns=("type", "choices"), show="tree headings", selectmode="browse")
        self.attr_tree.heading("#0", text="Nama atribut")
        self.attr_tree.heading("type", text="Jenis")
        self.attr_tree.heading("choices", text="Pilihan kategori / keterangan")
        self.attr_tree.column("#0", width=230)
        self.attr_tree.column("type", width=130, anchor="center")
        self.attr_tree.column("choices", width=500)
        self.attr_tree.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(attr_card, orient="vertical", command=self.attr_tree.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self.attr_tree.configure(yscrollcommand=scroll.set)
        ttk.Label(attr_card, text="Catatan: atribut yang sudah dipakai oleh kondisi rule atau kasus kunci dilindungi agar pohon tetap konsisten.", style="Hint.TLabel").grid(row=2, column=0, sticky="w", pady=(8, 0))

    def _build_tree_tab(self):
        self.tree_tab.columnconfigure(0, weight=3)
        self.tree_tab.columnconfigure(1, weight=2)
        self.tree_tab.rowconfigure(0, weight=1)
        left = ttk.Frame(self.tree_tab, style="Card.TFrame", padding=14)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.rowconfigure(1, weight=3)
        left.rowconfigure(3, weight=2)
        left.columnconfigure(0, weight=1)

        right = ttk.Frame(self.tree_tab, style="Card.TFrame", padding=14)
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        ttk.Label(
            left,
            text="Diagram Pohon Biner RDR (Anak Kiri = False-Child • Anak Kanan = True-Child / Perkecualian)",
            style="CardTitle.TLabel",
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.tree_canvas = BinaryTreeCanvas(left, on_select=self._on_canvas_select_rule)
        self.tree_canvas.grid(row=1, column=0, sticky="nsew", pady=(0, 12))

        ttk.Label(left, text="Daftar Hirarki Rule", style="Field.TLabel").grid(row=2, column=0, sticky="w", pady=(0, 4))
        tree_table_frame = ttk.Frame(left, style="Card.TFrame")
        tree_table_frame.grid(row=3, column=0, sticky="nsew")
        tree_table_frame.rowconfigure(0, weight=1)
        tree_table_frame.columnconfigure(0, weight=1)
        self.rule_tree = ttk.Treeview(tree_table_frame, columns=("condition", "side"), show="tree headings", height=6)
        self.rule_tree.heading("#0", text="Rule / kesimpulan")
        self.rule_tree.heading("condition", text="Kondisi")
        self.rule_tree.heading("side", text="Posisi Cabang")
        self.rule_tree.column("#0", width=260)
        self.rule_tree.column("condition", width=230)
        self.rule_tree.column("side", width=120, anchor="center")
        self.rule_tree.grid(row=0, column=0, sticky="nsew")
        rt_scroll = ttk.Scrollbar(tree_table_frame, orient="vertical", command=self.rule_tree.yview)
        rt_scroll.grid(row=0, column=1, sticky="ns")
        self.rule_tree.configure(yscrollcommand=rt_scroll.set)
        self.rule_tree.bind("<<TreeviewSelect>>", self.show_selected_rule)

        self.tree_summary_var = tk.StringVar(value="1 rule")
        ttk.Label(left, textvariable=self.tree_summary_var, style="Hint.TLabel").grid(row=4, column=0, sticky="w", pady=(8, 0))

        ttk.Label(right, text="Detail Rule & Kasus Kunci", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 10))
        self.rule_detail = tk.Text(right, wrap="word", font=("Segoe UI", 9), bg="#f7f9fc", fg="#334e68", relief="flat", padx=10, pady=10)
        self.rule_detail.pack(fill="both", expand=True)
        self.rule_detail.insert("1.0", "Klik salah satu kotak node pada diagram atau baris pada tabel untuk melihat detail rule.")
        self.rule_detail.configure(state="disabled")

    def _build_help_tab(self):
        help_card = ttk.Frame(self.help_tab, style="Card.TFrame", padding=22)
        help_card.pack(fill="both", expand=True)
        ttk.Label(help_card, text="Cara Kerja Sistem Pakar Ripple Down Rules (RDR)", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 12))
        content = (
            "1. RULE AWAL DEFAULT (R0):\n"
            "   Knowledge base dimulai hanya dengan satu rule awal pada root: kondisi t (selalu benar) → kesimpulan default. "
            "Domain masalah dan kesimpulan default dapat disesuaikan kapan saja pada tab Basis Pengetahuan.\n\n"
            "2. PENELUSURAN POHON BINER SAAT KONSUMEN DATANG:\n"
            "   • Sistem mengevaluasi kondisi mulai dari root (R0).\n"
            "   • Jika kondisi node TERPENUHI (True), kesimpulan node tersebut dicatat sebagai kesimpulan aktif "
            "(menganulir kesimpulan sebelumnya) dan penelusuran berlanjut ke ANAK KANAN (true-child / perkecualian).\n"
            "   • Jika kondisi node TIDAK TERPENUHI (False), kesimpulan aktif sebelumnya tetap dipertahankan dan "
            "penelusuran berlanjut ke ANAK KIRI (false-child).\n"
            "   • Penelusuran berhenti ketika anak tujuan belum ada; kesimpulan terakhir yang diperoleh menjadi kesimpulan sistem.\n\n"
            "3. JIKA PAKAR SETUJU:\n"
            "   Klik '✓ Pakar Setuju (Selesai)'. Rekomendasi tersebut diberikan kepada konsumen dan proses selesai. "
            "Jika rule kesimpulan aktif belum memiliki kasus kunci (misalnya kasus pertama pada R0), kasus ini disimpan "
            "sebagai kasus kunci rule tersebut.\n\n"
            "4. JIKA PAKAR TIDAK SETUJU (PEMBUATAN RULE PERKECUALIAN):\n"
            "   Klik '✗ Tidak Sesuai · Buat Rule Perkecualian'.\n"
            "   • Sistem menyusun daftar kondisi pembeda yang DIPENUHI oleh kasus baru dan TIDAK DIPENUHI oleh kasus kunci "
            "dari kesimpulan terakhir yang akan dianulir (baik untuk atribut numerik maupun kategorikal).\n"
            "   • Jika R0 belum memiliki kasus kunci spesifik (kasus pertama langsung ditolak), kasus kunci R0 dianggap kosong "
            "sehingga kondisi apa pun yang dipenuhi kasus baru sah digunakan.\n"
            "   • Pakar dapat mencentang satu atau beberapa kondisi sekaligus (digabung dengan konjungsi DAN), atau menambahkan "
            "batas ambang kustom (mis. anggaran_juta ≥ 15) yang otomatis divalidasi terhadap kasus baru dan kasus kunci.\n"
            "   • Pakar mengisi kesimpulan rekomendasi baru, lalu menyimpannya. Rule baru ditempatkan pada cabang kosong tempat "
            "berhentinya penelusuran (true-child kanan atau false-child kiri) dengan kasus baru sebagai kasus kuncinya.\n\n"
            "5. ATRIBUT NUMERIK DAN KATEGORIKAL:\n"
            "   Mendukung atribut numerik (=, ≠, >, ≥, <, ≤) dan kategorikal (=, ≠, baik dengan daftar pilihan kategori maupun teks bebas)."
        )
        text = tk.Text(help_card, wrap="word", font=("Segoe UI", 10), bg="#ffffff", fg="#334e68", relief="flat", padx=0, pady=0)
        text.pack(fill="both", expand=True)
        text.insert("1.0", content)
        text.configure(state="disabled")

    def refresh_all(self):
        self.domain_var.set(self.kb.get("domain", ""))
        self.default_text.configure(state="normal")
        self.default_text.delete("1.0", "end")
        self.default_text.insert("1.0", self.kb["root"].get("conclusion", ""))
        self._refresh_attributes()
        self._refresh_case_form()
        self._clear_result()
        self._refresh_rule_tree()

    def _refresh_attributes(self):
        for item in self.attr_tree.get_children():
            self.attr_tree.delete(item)
        for i, attr in enumerate(self.kb["attributes"]):
            display_type = "Numerik" if attr["type"] == "numeric" else "Kategorikal"
            choices = ", ".join(attr.get("choices", [])) or ("Angka bebas" if attr["type"] == "numeric" else "Teks bebas")
            self.attr_tree.insert("", "end", iid=str(i), text=attr["name"], values=(display_type, choices))

    def _refresh_case_form(self):
        for child in self.attributes_form.winfo_children():
            child.destroy()
        self.case_vars.clear()
        self.case_widgets.clear()
        if not self.kb["attributes"]:
            ttk.Label(self.attributes_form, text="Tambahkan minimal satu atribut pada tab Basis Pengetahuan.", style="Hint.TLabel").grid(row=0, column=0, sticky="w")
            return
        for index, attr in enumerate(self.kb["attributes"]):
            row, col = divmod(index, 2)
            cell = ttk.Frame(self.attributes_form, style="Card.TFrame")
            cell.grid(row=row, column=col, sticky="ew", padx=(0 if col == 0 else 10, 8 if col == 0 else 0), pady=6)
            self.attributes_form.columnconfigure(col, weight=1)
            label = attr["name"] + ("  •  numerik" if attr["type"] == "numeric" else "  •  kategorikal")
            ttk.Label(cell, text=label, style="Field.TLabel").pack(anchor="w", pady=(0, 4))
            var = tk.StringVar()
            self.case_vars[attr["name"]] = var
            if attr["type"] == "categorical" and attr.get("choices"):
                widget = ttk.Combobox(cell, textvariable=var, values=attr["choices"], state="readonly")
            else:
                widget = ttk.Entry(cell, textvariable=var)
            widget.pack(fill="x")
            self.case_widgets[attr["name"]] = widget
        self.attributes_form.rowconfigure((len(self.kb["attributes"]) + 1) // 2, weight=1)

    def _refresh_rule_tree(self):
        for item in self.rule_tree.get_children():
            self.rule_tree.delete(item)
        count = 0

        def add(node: dict[str, Any], parent: str = "", side_label: str = "ROOT"):
            nonlocal count
            count += 1
            conclusion = node.get("conclusion", "").replace("\n", " ")
            if len(conclusion) > 44:
                conclusion = conclusion[:41] + "..."
            item_id = node["id"]
            self.rule_tree.insert(
                parent, "end", iid=item_id,
                text=f"{item_id} · {conclusion}",
                values=(condition_text(node["condition"]), side_label),
                open=True,
            )
            if node.get("false_child"):
                add(node["false_child"], item_id, "KIRI / FALSE")
            if node.get("true_child"):
                add(node["true_child"], item_id, "KANAN / TRUE")

        add(self.kb["root"])
        self.tree_summary_var.set(f"{count} rule • Anak Kiri = false-child (kondisi salah) • Anak Kanan = true-child (kondisi benar / perkecualian)")
        self.tree_canvas.render(
            self.kb["root"],
            trace=self.engine.last_trace,
            active_node_id=self.engine.last_result_node_id,
        )

    def _on_canvas_select_rule(self, node_id: str):
        if self.rule_tree.exists(node_id):
            self.rule_tree.selection_set(node_id)
            self.rule_tree.see(node_id)
        self.tree_canvas.set_selected(node_id)
        self._display_rule_detail(node_id)

    def _clear_result(self):
        self.engine.reset_consultation()
        self.result_domain_var.set("Belum ada konsultasi")
        self._set_text(self.result_text, "Jalankan konsultasi untuk melihat kesimpulan rekomendasi dari knowledge base.")
        self._set_text(self.trace_text, "Belum ada jejak penelusuran.")
        self.accept_button.configure(state="disabled")
        self.reject_button.configure(state="disabled")
        for child in self.rule_editor.winfo_children():
            child.destroy()

    @staticmethod
    def _set_text(widget: tk.Text, content: str):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", content)
        widget.configure(state="disabled")

    @staticmethod
    def _format_trace_lines(inference: dict[str, Any]) -> str:
        lines = []
        for step in inference["trace"]:
            mark = "✓" if step["matched"] else "✗"
            prev_id = step.get("previous_node_id")
            if step["activated"]:
                if prev_id:
                    action = f"kesimpulan {step['node_id']} aktif (menganulir {prev_id})"
                else:
                    action = f"kesimpulan {step['node_id']} aktif"
            else:
                action = f"kesimpulan {step.get('active_node_id') or prev_id} tetap berlaku"
            lines.append(f"{mark} {step['node_id']}: {step['condition']}\n   Cabang {step['branch']} → {action}")
        lines.append(f"\nKesimpulan terakhir yang diperoleh berasal dari {inference['result_node_id']}.")
        return "\n".join(lines)

    def clear_form(self):
        self.customer_name_var.set("")
        for var in self.case_vars.values():
            var.set("")
        self.engine.reset_consultation(clear_highlight=True)
        self._clear_result()
        self._refresh_rule_tree()

    def run_consultation(self):
        if not self.kb["attributes"]:
            messagebox.showwarning("Atribut kosong", "Tambahkan atribut terlebih dahulu pada tab Basis Pengetahuan.", parent=self)
            return
        raw = {name: var.get() for name, var in self.case_vars.items()}
        try:
            inference = self.engine.run_consultation(raw, self.customer_name_var.get())
        except ValueError as exc:
            messagebox.showwarning("Data kasus belum valid", str(exc), parent=self)
            return
        who = f"Konsumen: {self.customer_name_var.get().strip()}  |  " if self.customer_name_var.get().strip() else ""
        self.result_domain_var.set(f"{who}Domain: {self.kb.get('domain', '-')}  |  Rule aktif: {inference['result_node_id']}")
        self._set_text(self.result_text, inference["conclusion"])
        self._set_text(self.trace_text, self._format_trace_lines(inference))
        self.accept_button.configure(state="normal")
        self.reject_button.configure(state="normal")
        for child in self.rule_editor.winfo_children():
            child.destroy()
        self._refresh_rule_tree()
        self.status_var.set(f"Menunggu evaluasi pakar • {len(inference['trace'])} node ditelusuri (kesimpulan {inference['result_node_id']})")

    def accept_result(self):
        if not self.engine.pending:
            return
        info = self.engine.accept_result()
        consumer_label = f" untuk {info['customer_name']}" if info["customer_name"] else ""
        key_note = (
            f"Kasus ini juga disimpan sebagai kasus kunci untuk {info['node_id']}."
            if info["stored_key_case"]
            else f"Kasus kunci {info['node_id']} yang sudah ada tetap dipertahankan."
        )
        self.result_domain_var.set(f"✓ PROSES SELESAI — Rekomendasi disetujui pakar{consumer_label} (Rule {info['node_id']})")
        self._set_text(self.result_text, info["conclusion"])
        for child in self.rule_editor.winfo_children():
            child.destroy()
        self._refresh_rule_tree()
        self.accept_button.configure(state="disabled")
        self.reject_button.configure(state="disabled")
        self.status_var.set(f"Proses selesai • Rekomendasi {info['node_id']} diberikan kepada konsumen")
        messagebox.showinfo(
            "Rekomendasi Diberikan (Proses Selesai)",
            f"Pakar menyetujui kesimpulan dari {info['node_id']}{consumer_label}.\n\n"
            f"Rekomendasi akhir:\n{info['conclusion']}\n\n{key_note}",
            parent=self,
        )

    def reject_result(self):
        if not self.engine.pending:
            return
        for child in self.rule_editor.winfo_children():
            child.destroy()
        active_node = self.engine.pending.inference["result_node"]
        status, candidates = self.engine.prepare_exception()
        if status == "no_candidates":
            ttk.Label(self.rule_editor, text="Tidak ditemukan kondisi pembeda", style="Field.TLabel").pack(anchor="w")
            ttk.Label(
                self.rule_editor,
                text=(
                    f"Seluruh nilai atribut kasus baru identik dengan kasus kunci {active_node['id']}, "
                    "sehingga tidak ada kondisi yang bernilai benar untuk kasus baru sekaligus salah untuk kasus kunci.\n"
                    "Tambahkan atribut pembeda baru pada tab Basis Pengetahuan atau periksa kembali data kasus."
                ),
                style="Hint.TLabel", wraplength=500, justify="left"
            ).pack(anchor="w", pady=(4, 8))
            self.result_scroll.scroll_to_bottom()
            return

        ttk.Separator(self.rule_editor, orient="horizontal").pack(fill="x", pady=(0, 10))
        ttk.Label(
            self.rule_editor,
            text=f"Buat Rule Perkecualian (Menganulir {active_node['id']})",
            style="CardTitle.TLabel",
        ).pack(anchor="w")

        key_case = active_node.get("key_case")
        if key_case:
            key_summary = ", ".join(f"{k}={v}" for k, v in key_case.items())
            key_info = f"Kasus kunci {active_node['id']}: {key_summary}"
        else:
            key_info = f"Kasus kunci {active_node['id']}: (kosong — belum ada kasus yang disetujui pada {active_node['id']})"
        ttk.Label(self.rule_editor, text=key_info, style="Hint.TLabel", wraplength=500, justify="left").pack(anchor="w", pady=(3, 6))

        ttk.Label(
            self.rule_editor,
            text="Pilih satu atau beberapa kondisi (DAN) yang dipenuhi kasus baru dan tidak dipenuhi kasus kunci:",
            style="Field.TLabel", wraplength=500, justify="left",
        ).pack(anchor="w", pady=(2, 4))

        self.candidates_list_frame = ttk.Frame(self.rule_editor, style="Card.TFrame")
        self.candidates_list_frame.pack(fill="x")
        self.candidate_vars = []
        for i, candidate in enumerate(candidates):
            var = tk.BooleanVar(value=(i == 0))
            self.candidate_vars.append(var)
            cb = ttk.Checkbutton(self.candidates_list_frame, text=candidate["label"], variable=var)
            cb.pack(anchor="w", pady=2)

        # Panel tambah kondisi kustom (mis. batas ambang numerik spesifik dari pakar)
        custom_box = ttk.Frame(self.rule_editor, style="Subtle.TFrame", padding=8)
        custom_box.pack(fill="x", pady=(8, 4))
        ttk.Label(custom_box, text="Opsional: tambah kondisi pembeda kustom (mis. ambang numerik pilihan pakar)", style="Hint.TLabel").grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 4))
        attr_names = [a["name"] for a in self.kb["attributes"]]
        self.custom_attr_var = tk.StringVar(value=attr_names[0] if attr_names else "")
        self.custom_op_var = tk.StringVar()
        self.custom_val_var = tk.StringVar()

        attr_cb = ttk.Combobox(custom_box, textvariable=self.custom_attr_var, values=attr_names, state="readonly", width=16)
        attr_cb.grid(row=1, column=0, padx=(0, 6), sticky="ew")
        self.custom_op_cb = ttk.Combobox(custom_box, textvariable=self.custom_op_var, state="readonly", width=6)
        self.custom_op_cb.grid(row=1, column=1, padx=(0, 6))
        self.custom_val_cb = ttk.Combobox(custom_box, textvariable=self.custom_val_var, width=14)
        self.custom_val_cb.grid(row=1, column=2, padx=(0, 6), sticky="ew")
        custom_box.columnconfigure(2, weight=1)
        ttk.Button(custom_box, text="+ Tambah", command=self._add_custom_condition_ui).grid(row=1, column=3)
        attr_cb.bind("<<ComboboxSelected>>", self._sync_custom_condition_controls)
        self._sync_custom_condition_controls()

        ttk.Label(self.rule_editor, text="Kesimpulan rekomendasi dari pakar", style="Field.TLabel").pack(anchor="w", pady=(10, 4))
        self.expert_conclusion = tk.Text(self.rule_editor, height=3, wrap="word", font=("Segoe UI", 9), relief="solid", bd=1)
        self.expert_conclusion.pack(fill="x")
        ttk.Button(
            self.rule_editor,
            text="Simpan Rule Perkecualian & Berikan Rekomendasi",
            style="Accent.TButton",
            command=self.save_exception_rule,
        ).pack(anchor="e", pady=(8, 4))
        self.result_scroll.scroll_to_bottom()

    def _sync_custom_condition_controls(self, _event=None):
        attr_name = self.custom_attr_var.get()
        attr = next((a for a in self.kb["attributes"] if a["name"] == attr_name), None)
        if not attr:
            return
        if attr["type"] == "numeric":
            symbols = [OPERATOR_SYMBOLS[op] for op in NUMERIC_OPERATORS]
            self.custom_op_cb.configure(values=symbols)
            self.custom_op_var.set(symbols[0])
            self.custom_val_cb.configure(values=[], state="normal")
            if self.engine.pending and attr_name in self.engine.pending.case:
                self.custom_val_var.set(str(self.engine.pending.case[attr_name]))
        else:
            symbols = [OPERATOR_SYMBOLS[op] for op in CATEGORICAL_OPERATORS]
            self.custom_op_cb.configure(values=symbols)
            self.custom_op_var.set(symbols[0])
            choices = attr.get("choices") or []
            if choices:
                self.custom_val_cb.configure(values=choices, state="readonly")
            else:
                self.custom_val_cb.configure(values=[], state="normal")
            if self.engine.pending and attr_name in self.engine.pending.case:
                self.custom_val_var.set(str(self.engine.pending.case[attr_name]))

    def _add_custom_condition_ui(self):
        if not self.engine.pending:
            return
        op_code = SYMBOL_TO_OPERATOR.get(self.custom_op_var.get(), "")
        before_len = len(self.engine.candidates)
        try:
            cand = self.engine.add_custom_candidate(
                self.custom_attr_var.get(),
                op_code,
                self.custom_val_var.get(),
            )
        except ValueError as exc:
            messagebox.showwarning("Kondisi kustom tidak valid", str(exc), parent=self)
            return
        if len(self.engine.candidates) > before_len:
            var = tk.BooleanVar(value=True)
            self.candidate_vars.append(var)
            cb = ttk.Checkbutton(self.candidates_list_frame, text=cand["label"], variable=var)
            cb.pack(anchor="w", pady=2)
            self.result_scroll.scroll_to_bottom()
        else:
            idx = self.engine.candidates.index(cand)
            self.candidate_vars[idx].set(True)

    def save_exception_rule(self):
        if not self.engine.pending:
            return
        conclusion = self.expert_conclusion.get("1.0", "end").strip()
        if not conclusion:
            messagebox.showwarning("Kesimpulan kosong", "Masukkan kesimpulan rekomendasi yang diberikan oleh pakar.", parent=self)
            return
        selected_indices = [i for i, var in enumerate(self.candidate_vars) if var.get()]
        if not selected_indices:
            messagebox.showwarning("Kondisi belum dipilih", "Centang minimal satu kondisi pembeda.", parent=self)
            return
        try:
            info = self.engine.save_exception(selected_indices, conclusion)
        except ValueError as exc:
            messagebox.showerror("Kesalahan", str(exc), parent=self)
            return

        new_node = info["node"]
        new_id = new_node["id"]
        side_text = "KANAN / TRUE (true-child)" if info["side"] == "true_child" else "KIRI / FALSE (false-child)"
        consumer_label = f" untuk {info['customer_name']}" if info["customer_name"] else ""

        self._refresh_rule_tree()
        self._set_text(self.result_text, conclusion)
        self.result_domain_var.set(f"✓ RULE BARU {new_id} — Menganulir {info['active_node_id']}{consumer_label}")
        self._set_text(
            self.trace_text,
            f"Rule perkecualian {new_id} ditambahkan pada cabang {side_text} dari {info['parent_id']}.\n"
            f"Kondisi: {condition_text(new_node['condition'])}\n"
            f"Kasus baru disimpan sebagai kasus kunci {new_id}.\n\n"
            f"Jejak verifikasi ulang pada pohon terbaru:\n"
            f"{self._format_trace_lines(info['updated_inference'])}",
        )
        for child in self.rule_editor.winfo_children():
            child.destroy()
        self.accept_button.configure(state="disabled")
        self.reject_button.configure(state="disabled")
        self.status_var.set(f"Rule {new_id} ditambahkan • Rekomendasi diberikan kepada konsumen")
        messagebox.showinfo(
            "Rule Perkecualian Ditambahkan",
            f"Rule {new_id} berhasil ditambahkan pada cabang {side_text} dari {info['parent_id']}.\n\n"
            f"Kondisi: {condition_text(new_node['condition'])}\n"
            f"Rekomendasi akhir{consumer_label}:\n{conclusion}",
            parent=self,
        )

    def apply_kb_settings(self):
        try:
            self.engine.apply_settings(self.domain_var.get(), self.default_text.get("1.0", "end"))
        except ValueError as exc:
            messagebox.showwarning("Validasi", str(exc), parent=self)
            return
        self._clear_result()
        self._refresh_rule_tree()
        self.status_var.set("Pengaturan domain & kesimpulan default diterapkan")
        messagebox.showinfo("Tersimpan", "Domain dan kesimpulan default (R0) telah diperbarui.", parent=self)

    def add_attribute(self):
        dialog = AttributeDialog(self)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        try:
            self.engine.add_attribute(dialog.result)
        except ValueError as exc:
            messagebox.showwarning("Nama duplikat", str(exc), parent=self)
            return
        self._refresh_attributes()
        self._refresh_case_form()
        self._clear_result()

    def edit_attribute(self):
        selection = self.attr_tree.selection()
        if not selection:
            messagebox.showinfo("Pilih atribut", "Pilih atribut yang ingin diedit.", parent=self)
            return
        index = int(selection[0])
        old = self.kb["attributes"][index]
        dialog = AttributeDialog(self, existing=old)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        try:
            self.engine.update_attribute(index, dialog.result)
        except ValueError as exc:
            messagebox.showwarning("Atribut tidak dapat diubah", str(exc), parent=self)
            return
        self._refresh_attributes()
        self._refresh_case_form()
        self._clear_result()

    def delete_attribute(self):
        selection = self.attr_tree.selection()
        if not selection:
            messagebox.showinfo("Pilih atribut", "Pilih atribut yang ingin dihapus.", parent=self)
            return
        index = int(selection[0])
        attr = self.kb["attributes"][index]
        if attribute_is_referenced(self.kb["root"], attr["name"]):
            messagebox.showwarning("Atribut sedang digunakan", "Atribut ini sudah dipakai oleh rule atau kasus kunci sehingga tidak dapat dihapus.", parent=self)
            return
        if messagebox.askyesno("Hapus atribut", f"Hapus atribut '{attr['name']}'?", parent=self):
            self.engine.delete_attribute(index)
            self._refresh_attributes()
            self._refresh_case_form()
            self._clear_result()

    def show_selected_rule(self, _event=None):
        selection = self.rule_tree.selection()
        if not selection:
            return
        node_id = selection[0]
        self.tree_canvas.set_selected(node_id)
        self._display_rule_detail(node_id)

    def _display_rule_detail(self, node_id: str):
        node = find_node(self.kb["root"], node_id)
        if not node:
            return
        key_case = node.get("key_case")
        detail = (
            f"ID Rule: {node['id']}\n"
            f"Kondisi: {condition_text(node['condition'])}\n\n"
            f"Kesimpulan:\n{node.get('conclusion', '')}\n\n"
            f"Kasus kunci:\n{json.dumps(key_case, ensure_ascii=False, indent=2) if key_case else 'Belum ditetapkan (kasus kunci kosong)'}\n\n"
            f"Anak Kanan / True-child (dieksekusi saat kondisi terpenuhi): {node.get('true_child', {}).get('id') if node.get('true_child') else '—'}\n"
            f"Anak Kiri / False-child (dieksekusi saat kondisi tidak terpenuhi): {node.get('false_child', {}).get('id') if node.get('false_child') else '—'}"
        )
        self._set_text(self.rule_detail, detail)

    def new_kb(self):
        if not messagebox.askyesno("Knowledge base baru", "Buat knowledge base baru dari awal (1 rule default R0)? Perubahan yang belum disimpan akan hilang.", parent=self):
            return
        self.engine.new_kb()
        self.current_path = None
        self.refresh_all()
        self.notebook.select(self.kb_tab)
        self.status_var.set("Knowledge base baru dibuat — silakan isi domain, kesimpulan default, dan atribut")

    def reset_sample_kb(self):
        if not messagebox.askyesno("Contoh Domain Laptop", "Muat ulang knowledge base contoh (1 rule awal default)? Perubahan yang belum disimpan akan hilang.", parent=self):
            return
        self.engine.load_sample_kb()
        self.current_path = None
        self.refresh_all()
        self.status_var.set("Knowledge base contoh dimuat")

    def save_kb(self):
        if self.current_path is None:
            return self.save_kb_as()
        return self._write_kb(self.current_path)

    def save_kb_as(self):
        path = filedialog.asksaveasfilename(
            parent=self, title="Simpan knowledge base", defaultextension=".json",
            filetypes=[("RDR Knowledge Base", "*.json"), ("Semua file", "*.*")],
            initialfile="knowledge_base_rdr.json"
        )
        if not path:
            return False
        self.current_path = Path(path)
        return self._write_kb(self.current_path)

    def _write_kb(self, path: Path):
        try:
            self.engine.save(path)
            self.status_var.set(f"Tersimpan: {path.name}")
            messagebox.showinfo("Knowledge base tersimpan", f"File berhasil disimpan:\n{path}", parent=self)
            return True
        except OSError as exc:
            messagebox.showerror("Gagal menyimpan", str(exc), parent=self)
            return False

    def open_kb(self):
        path = filedialog.askopenfilename(
            parent=self, title="Buka knowledge base", filetypes=[("RDR Knowledge Base", "*.json"), ("Semua file", "*.*")]
        )
        if not path:
            return
        try:
            self.engine.load(path)
            self.current_path = Path(path)
            self.refresh_all()
            self.status_var.set(f"Dibuka: {Path(path).name}")
        except (OSError, json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
            messagebox.showerror("Gagal membuka", f"File bukan knowledge base RDR yang valid.\n\nDetail: {exc}", parent=self)

    def show_about(self):
        messagebox.showinfo(
            "Tentang RDR Studio",
            f"{APP_TITLE}\nVersi {APP_VERSION}\n\nSistem rekomendasi AI berbasis Ripple Down Rules (RDR) untuk pakar.\nDibangun dengan Python dan Tkinter tanpa dependensi pihak ketiga.",
            parent=self,
        )

    def on_close(self):
        self.destroy()


def main():
    app = RDRApp()
    app.mainloop()


if __name__ == "__main__":
    main()
