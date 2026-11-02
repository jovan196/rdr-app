"""Ripple Down Rules (RDR) Expert Recommendation System.

A standard-library-only Tkinter desktop application.
Run with: python main.py
"""
from __future__ import annotations

import json
import math
import tkinter as tk
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any, Optional

APP_TITLE = "RDR Studio — Sistem Rekomendasi Pakar"
APP_VERSION = "1.0.0"


def make_sample_kb() -> dict[str, Any]:
    """Return a ready-to-try sample knowledge base (laptop recommendation domain)."""
    return {
        "version": 1,
        "domain": "Rekomendasi laptop untuk konsumen (contoh; dapat diubah)",
        "attributes": [
            {"name": "anggaran_juta", "type": "numeric", "choices": []},
            {"name": "penggunaan", "type": "categorical", "choices": ["Kantor", "Kuliah", "Desain", "Gaming"]},
            {"name": "mobilitas", "type": "categorical", "choices": ["Tinggi", "Sedang", "Rendah"]},
            {"name": "ram_minimum_gb", "type": "numeric", "choices": []},
            {"name": "preferensi_os", "type": "categorical", "choices": ["Windows", "macOS", "Linux", "Bebas"]},
        ],
        "root": {
            "id": "R0",
            "condition": {"attribute": None, "operator": "always", "value": True},
            "conclusion": (
                "Rekomendasi umum: pilih laptop kelas menengah yang seimbang untuk "
                "aktivitas harian. Sesuaikan prosesor, RAM, layar, dan garansi dengan "
                "kebutuhan serta anggaran konsumen."
            ),
            "key_case": None,
            "true_child": None,
            "false_child": None,
        },
    }


def condition_text(condition: dict[str, Any]) -> str:
    op = condition.get("operator", "always")
    if op == "always":
        return "SELALU BENAR (t)"
    attr = condition.get("attribute", "?")
    value = condition.get("value")
    symbols = {"eq": "=", "ne": "≠", "gt": ">", "ge": "≥", "lt": "<", "le": "≤"}
    return f"{attr} {symbols.get(op, op)} {value}"


def evaluate_condition(condition: dict[str, Any], case: dict[str, Any]) -> bool:
    op = condition.get("operator", "always")
    if op == "always":
        return True
    attr = condition.get("attribute")
    if attr not in case:
        return False
    actual = case[attr]
    expected = condition.get("value")
    if op in {"eq", "ne"}:
        result = str(actual).strip().casefold() == str(expected).strip().casefold()
        return result if op == "eq" else not result
    try:
        a, b = float(actual), float(expected)
    except (TypeError, ValueError):
        return False
    if not (math.isfinite(a) and math.isfinite(b)):
        return False
    if op == "gt":
        return a > b
    if op == "ge":
        return a >= b
    if op == "lt":
        return a < b
    if op == "le":
        return a <= b
    return False


def iter_nodes(node: Optional[dict[str, Any]]):
    if not node:
        return
    yield node
    yield from iter_nodes(node.get("true_child"))
    yield from iter_nodes(node.get("false_child"))


def find_node(root: dict[str, Any], node_id: str) -> Optional[dict[str, Any]]:
    for node in iter_nodes(root):
        if node.get("id") == node_id:
            return node
    return None


def get_next_node_id(root: dict[str, Any]) -> str:
    used = {str(n.get("id", "")) for n in iter_nodes(root)}
    index = 1
    while f"R{index}" in used:
        index += 1
    return f"R{index}"


def infer_case(root: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    """Traverse the binary rule tree and return the last conclusion whose condition is true.

    A true condition activates that node's conclusion and follows its true-child.
    A false condition preserves the last active conclusion and follows false-child.
    Traversal stops when the selected child does not exist.
    """
    current = root
    active_node: Optional[dict[str, Any]] = None
    trace: list[dict[str, Any]] = []
    frontier_node = root
    frontier_side = "true_child"
    while current is not None:
        matched = evaluate_condition(current["condition"], case)
        side = "true_child" if matched else "false_child"
        if matched:
            active_node = current
        trace.append({
            "node_id": current["id"],
            "condition": condition_text(current["condition"]),
            "matched": matched,
            "branch": "KANAN / TRUE" if matched else "KIRI / FALSE",
            "activated": matched,
            "conclusion": current.get("conclusion", ""),
        })
        child = current.get(side)
        if child is None:
            frontier_node = current
            frontier_side = side
            break
        current = child
    if active_node is None:
        # The seeded root condition is always true; this is a defensive fallback.
        active_node = root
    return {
        "conclusion": active_node.get("conclusion", ""),
        "result_node_id": active_node["id"],
        "result_node": active_node,
        "trace": trace,
        "frontier_node_id": frontier_node["id"],
        "frontier_side": frontier_side,
    }


def build_candidates(attributes: list[dict[str, Any]], case: dict[str, Any], key_case: dict[str, Any]) -> list[dict[str, Any]]:
    """Build predicates true for the new case and false for its prior conclusion's key case."""
    candidates: list[dict[str, Any]] = []
    for attr in attributes:
        name = attr["name"]
        if name not in case or name not in key_case:
            continue
        new_value, old_value = case[name], key_case[name]
        if attr["type"] == "numeric":
            try:
                new_num, old_num = float(new_value), float(old_value)
            except (TypeError, ValueError):
                continue
            if not (math.isfinite(new_num) and math.isfinite(old_num)) or new_num == old_num:
                continue
            midpoint = (new_num + old_num) / 2.0
            if new_num > old_num:
                condition = {"attribute": name, "operator": "ge", "value": midpoint}
                detail = f"{name} ≥ {midpoint:g} (kasus baru: {new_num:g}; kasus kunci: {old_num:g})"
            else:
                condition = {"attribute": name, "operator": "le", "value": midpoint}
                detail = f"{name} ≤ {midpoint:g} (kasus baru: {new_num:g}; kasus kunci: {old_num:g})"
            candidates.append({"condition": condition, "label": detail})
        else:
            if str(new_value).strip().casefold() == str(old_value).strip().casefold():
                continue
            condition = {"attribute": name, "operator": "eq", "value": str(new_value)}
            detail = f'{name} = "{new_value}" (kasus kunci: "{old_value}")'
            candidates.append({"condition": condition, "label": detail})
    return candidates


def validate_case(attributes: list[dict[str, Any]], raw_values: dict[str, str]) -> tuple[dict[str, Any], list[str]]:
    case: dict[str, Any] = {}
    errors: list[str] = []
    for attr in attributes:
        name = attr["name"]
        raw = raw_values.get(name, "").strip()
        if not raw:
            errors.append(f"Atribut '{name}' belum diisi.")
            continue
        if attr["type"] == "numeric":
            try:
                value = float(raw.replace(",", "."))
                if not math.isfinite(value):
                    raise ValueError
                case[name] = value
            except ValueError:
                errors.append(f"Atribut '{name}' harus berupa angka yang valid.")
        else:
            case[name] = raw
    return case, errors


@dataclass
class PendingConsultation:
    case: dict[str, Any]
    customer_name: str
    inference: dict[str, Any]


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
        name_entry = ttk.Entry(body, textvariable=self.name_var, width=36)
        name_entry.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        ttk.Label(body, text="Jenis data", style="Field.TLabel").grid(row=2, column=0, sticky="w", pady=(0, 4))
        kind = ttk.Combobox(body, textvariable=self.type_var, values=["numeric", "categorical"], state="readonly", width=33)
        kind.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        ttk.Label(body, text="Pilihan kategori (opsional, pisahkan dengan koma)", style="Field.TLabel").grid(row=4, column=0, sticky="w", pady=(0, 4))
        ttk.Entry(body, textvariable=self.choices_var, width=36).grid(row=5, column=0, sticky="ew")
        ttk.Label(body, text="Contoh: Kantor, Kuliah, Desain, Gaming", style="Hint.TLabel").grid(row=6, column=0, sticky="w", pady=(4, 14))
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

    def save(self):
        name = self.name_var.get().strip()
        kind = self.type_var.get().strip()
        if not name:
            messagebox.showwarning("Validasi", "Nama atribut wajib diisi.", parent=self)
            return
        if any(ch.isspace() for ch in name):
            messagebox.showwarning("Validasi", "Gunakan nama atribut tanpa spasi (contoh: anggaran_juta).", parent=self)
            return
        choices = [x.strip() for x in self.choices_var.get().split(",") if x.strip()] if kind == "categorical" else []
        self.result = {"name": name, "type": kind, "choices": choices}
        self.destroy()


class RDRApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1280x820")
        self.minsize(1080, 700)
        self.configure(bg="#f3f6fb")
        self.kb = make_sample_kb()
        self.current_path: Optional[Path] = None
        self.pending: Optional[PendingConsultation] = None
        self.case_vars: dict[str, tk.StringVar] = {}
        self.case_widgets: dict[str, ttk.Widget] = {}
        self.candidate_var = tk.IntVar(value=-1)
        self._build_style()
        self._build_menu()
        self._build_shell()
        self.refresh_all()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background="#f3f6fb")
        style.configure("Card.TFrame", background="#ffffff", relief="flat")
        style.configure("TLabel", background="#f3f6fb", foreground="#1f2937", font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"), foreground="#102a43", background="#f3f6fb")
        style.configure("SubTitle.TLabel", font=("Segoe UI", 10), foreground="#627d98", background="#f3f6fb")
        style.configure("CardTitle.TLabel", font=("Segoe UI", 11, "bold"), foreground="#243b53", background="#ffffff")
        style.configure("Field.TLabel", font=("Segoe UI", 9, "bold"), foreground="#486581", background="#ffffff")
        style.configure("Hint.TLabel", font=("Segoe UI", 8), foreground="#829ab1", background="#ffffff")
        style.configure("TButton", font=("Segoe UI", 9), padding=(10, 7))
        style.configure("Accent.TButton", background="#2463eb", foreground="#ffffff", font=("Segoe UI", 9, "bold"))
        style.map("Accent.TButton", background=[("active", "#1748bd"), ("disabled", "#a7b9d5")])
        style.configure("Success.TButton", background="#138a64", foreground="#ffffff", font=("Segoe UI", 9, "bold"))
        style.map("Success.TButton", background=[("active", "#0e6b4e")])
        style.configure("Danger.TButton", foreground="#b42318")
        style.configure("Treeview", rowheight=28, font=("Segoe UI", 9), background="#ffffff", fieldbackground="#ffffff")
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"), background="#eaf0f8", foreground="#334e68")
        style.configure("TNotebook", background="#f3f6fb", borderwidth=0)
        style.configure("TNotebook.Tab", font=("Segoe UI", 9, "bold"), padding=(16, 10))
        style.map("TNotebook.Tab", background=[("selected", "#ffffff")], foreground=[("selected", "#1748bd")])

    def _build_menu(self):
        menu = tk.Menu(self)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="Knowledge Base Baru", command=self.new_kb)
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
        ttk.Label(left, text="Ripple Down Rules • Sistem rekomendasi berbasis pengetahuan pakar", style="SubTitle.TLabel").pack(anchor="w", pady=(2, 0))
        right = ttk.Frame(header)
        right.pack(side="right")
        self.status_var = tk.StringVar(value="Knowledge base contoh siap digunakan")
        ttk.Label(right, textvariable=self.status_var, style="SubTitle.TLabel").pack(anchor="e")
        ttk.Label(right, text=f"Versi {APP_VERSION}", style="Hint.TLabel").pack(anchor="e", pady=(4, 0))

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=24, pady=(0, 16))
        self.consult_tab = ttk.Frame(self.notebook, padding=16)
        self.kb_tab = ttk.Frame(self.notebook, padding=16)
        self.tree_tab = ttk.Frame(self.notebook, padding=16)
        self.help_tab = ttk.Frame(self.notebook, padding=16)
        self.notebook.add(self.consult_tab, text="  Konsultasi  ")
        self.notebook.add(self.kb_tab, text="  Basis Pengetahuan  ")
        self.notebook.add(self.tree_tab, text="  Pohon Rule  ")
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
        ttk.Label(form_card, text="Isi seluruh atribut kasus, lalu jalankan penelusuran rule.", style="Hint.TLabel").pack(anchor="w", pady=(3, 12))
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

        ttk.Label(result_card, text="Hasil penalaran", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(result_card, text="Kesimpulan aktif dan jejak penelusuran pohon RDR.", style="Hint.TLabel").pack(anchor="w", pady=(3, 10))
        self.result_domain_var = tk.StringVar(value="Belum ada konsultasi")
        ttk.Label(result_card, textvariable=self.result_domain_var, style="Field.TLabel").pack(anchor="w", pady=(0, 5))
        self.result_text = tk.Text(result_card, height=6, wrap="word", font=("Segoe UI", 10), bg="#f7f9fc", fg="#243b53", relief="flat", padx=12, pady=10)
        self.result_text.pack(fill="x")
        self.result_text.insert("1.0", "Jalankan konsultasi untuk melihat rekomendasi dari knowledge base.")
        self.result_text.configure(state="disabled")
        ttk.Label(result_card, text="Jejak penelusuran", style="Field.TLabel").pack(anchor="w", pady=(12, 5))
        self.trace_text = tk.Text(result_card, height=8, wrap="word", font=("Consolas", 9), bg="#f7f9fc", fg="#486581", relief="flat", padx=10, pady=8)
        self.trace_text.pack(fill="both", expand=True)
        self.trace_text.insert("1.0", "Belum ada jejak.")
        self.trace_text.configure(state="disabled")

        self.feedback_frame = ttk.Frame(result_card, style="Card.TFrame")
        self.feedback_frame.pack(fill="x", pady=(12, 0))
        ttk.Label(self.feedback_frame, text="Apakah rekomendasi ini sesuai menurut pakar?", style="Field.TLabel").pack(anchor="w", pady=(0, 8))
        buttons = ttk.Frame(self.feedback_frame, style="Card.TFrame")
        buttons.pack(fill="x")
        self.accept_button = ttk.Button(buttons, text="Sesuai", style="Success.TButton", command=self.accept_result, state="disabled")
        self.accept_button.pack(side="left")
        self.reject_button = ttk.Button(buttons, text="Tidak sesuai — buat rule", style="Danger.TButton", command=self.reject_result, state="disabled")
        self.reject_button.pack(side="left", padx=(8, 0))
        self.rule_editor = ttk.Frame(result_card, style="Card.TFrame")
        self.rule_editor.pack(fill="x", pady=(12, 0))

    def _build_kb_tab(self):
        self.kb_tab.columnconfigure(0, weight=1)
        self.kb_tab.rowconfigure(1, weight=1)
        config_card = ttk.Frame(self.kb_tab, style="Card.TFrame", padding=16)
        config_card.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        config_card.columnconfigure(1, weight=1)
        ttk.Label(config_card, text="Pengaturan domain dan kesimpulan default", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        ttk.Label(config_card, text="Domain masalah", style="Field.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=5)
        self.domain_var = tk.StringVar()
        ttk.Entry(config_card, textvariable=self.domain_var).grid(row=1, column=1, sticky="ew", pady=5)
        ttk.Label(config_card, text="Kesimpulan default", style="Field.TLabel").grid(row=2, column=0, sticky="nw", padx=(0, 12), pady=5)
        self.default_text = tk.Text(config_card, height=3, wrap="word", font=("Segoe UI", 9), relief="solid", bd=1)
        self.default_text.grid(row=2, column=1, sticky="ew", pady=5)
        ttk.Button(config_card, text="Terapkan pengaturan", style="Accent.TButton", command=self.apply_kb_settings).grid(row=3, column=1, sticky="e", pady=(8, 0))

        attr_card = ttk.Frame(self.kb_tab, style="Card.TFrame", padding=16)
        attr_card.grid(row=1, column=0, sticky="nsew")
        attr_card.rowconfigure(1, weight=1)
        attr_card.columnconfigure(0, weight=1)
        top = ttk.Frame(attr_card, style="Card.TFrame")
        top.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(top, text="Daftar atribut kasus", style="CardTitle.TLabel").pack(side="left")
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
        ttk.Label(attr_card, text="Catatan: atribut yang sudah dipakai oleh kondisi rule tidak dapat dihapus atau diubah jenis datanya.", style="Hint.TLabel").grid(row=2, column=0, sticky="w", pady=(8, 0))

    def _build_tree_tab(self):
        self.tree_tab.columnconfigure(0, weight=3)
        self.tree_tab.columnconfigure(1, weight=2)
        self.tree_tab.rowconfigure(0, weight=1)
        left = ttk.Frame(self.tree_tab, style="Card.TFrame", padding=14)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        right = ttk.Frame(self.tree_tab, style="Card.TFrame", padding=14)
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        ttk.Label(left, text="Struktur pohon biner RDR", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 10))
        self.rule_tree = ttk.Treeview(left, columns=("condition", "side"), show="tree headings")
        self.rule_tree.heading("#0", text="Rule / kesimpulan")
        self.rule_tree.heading("condition", text="Kondisi")
        self.rule_tree.heading("side", text="Cabang")
        self.rule_tree.column("#0", width=270)
        self.rule_tree.column("condition", width=220)
        self.rule_tree.column("side", width=110, anchor="center")
        self.rule_tree.pack(fill="both", expand=True)
        self.rule_tree.bind("<<TreeviewSelect>>", self.show_selected_rule)
        ttk.Label(right, text="Detail rule", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 10))
        self.rule_detail = tk.Text(right, wrap="word", font=("Segoe UI", 9), bg="#f7f9fc", fg="#334e68", relief="flat", padx=10, pady=10)
        self.rule_detail.pack(fill="both", expand=True)
        self.rule_detail.insert("1.0", "Pilih sebuah rule pada pohon untuk melihat detailnya.")
        self.rule_detail.configure(state="disabled")
        self.tree_summary_var = tk.StringVar(value="1 rule")
        ttk.Label(left, textvariable=self.tree_summary_var, style="Hint.TLabel").pack(anchor="w", pady=(8, 0))

    def _build_help_tab(self):
        help_card = ttk.Frame(self.help_tab, style="Card.TFrame", padding=22)
        help_card.pack(fill="both", expand=True)
        ttk.Label(help_card, text="Cara kerja Ripple Down Rules", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 12))
        content = (
            "1. Knowledge base dimulai dari satu rule default (kondisi t / selalu benar). "
            "Kesimpulan default dapat disesuaikan dengan domain masalah pada tab Basis Pengetahuan.\n\n"
            "2. Saat konsultasi, sistem menelusuri pohon dari root. Jika kondisi sebuah node terpenuhi, "
            "kesimpulan node tersebut menjadi kesimpulan aktif dan penelusuran dilanjutkan ke anak kanan "
            "(true-child). Jika kondisi tidak terpenuhi, kesimpulan aktif sebelumnya dipertahankan dan "
            "penelusuran dilanjutkan ke anak kiri (false-child). Penelusuran berhenti ketika cabang yang "
            "dipilih belum memiliki anak.\n\n"
            "3. Jika pakar menyetujui rekomendasi, kasus dapat disimpan sebagai kasus kunci untuk rule "
            "tersebut (khususnya ketika rule belum memiliki kasus kunci). Kasus kunci menjadi acuan "
            "pembentukan pengecualian berikutnya.\n\n"
            "4. Jika pakar tidak setuju, sistem membandingkan kasus baru dengan kasus kunci dari rule "
            "yang menghasilkan kesimpulan aktif. Sistem mengusulkan kondisi pembeda: atribut kategorikal "
            "menggunakan nilai kasus baru, sedangkan atribut numerik menggunakan titik tengah antara "
            "nilai kasus baru dan kasus kunci. Kondisi yang ditampilkan selalu dirancang benar untuk "
            "kasus baru dan salah untuk kasus kunci.\n\n"
            "5. Pakar memilih salah satu kondisi pembeda dan memasukkan kesimpulan yang benar. Rule baru "
            "ditambahkan pada cabang yang ditempuh kasus baru. Ketika kondisi rule baru terpenuhi, "
            "kesimpulan yang lebih spesifik menggantikan kesimpulan sebelumnya.\n\n"
            "6. Knowledge base dapat disimpan dan dibuka dalam format JSON melalui menu File. Atribut "
            "numerik dan kategorikal dapat ditambah, diedit, atau dihapus (atribut yang sedang dipakai "
            "oleh rule dilindungi agar struktur knowledge base tidak rusak).\n\n"
            "Catatan penting: sebelum pengecualian pertama dibuat, pakar perlu menyetujui setidaknya "
            "satu kasus default agar sistem memiliki kasus kunci pembanding."
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
        self._refresh_rule_tree()
        self._clear_result()

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
                widget = ttk.Combobox(cell, textvariable=var, values=attr["choices"], state="normal")
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
            if len(conclusion) > 48:
                conclusion = conclusion[:45] + "..."
            item_id = node["id"]
            self.rule_tree.insert(parent, "end", iid=item_id, text=f"{item_id} · {conclusion}", values=(condition_text(node["condition"]), side_label), open=True)
            if node.get("true_child"):
                add(node["true_child"], item_id, "KANAN / TRUE")
            if node.get("false_child"):
                add(node["false_child"], item_id, "KIRI / FALSE")
        add(self.kb["root"])
        self.tree_summary_var.set(f"{count} rule • cabang kanan = true-child • cabang kiri = false-child")

    def _clear_result(self):
        self.pending = None
        self.result_domain_var.set("Belum ada konsultasi")
        self._set_text(self.result_text, "Jalankan konsultasi untuk melihat rekomendasi dari knowledge base.")
        self._set_text(self.trace_text, "Belum ada jejak.")
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

    def clear_form(self):
        self.customer_name_var.set("")
        for var in self.case_vars.values():
            var.set("")
        self._clear_result()

    def run_consultation(self):
        raw = {name: var.get() for name, var in self.case_vars.items()}
        case, errors = validate_case(self.kb["attributes"], raw)
        if errors:
            messagebox.showwarning("Data kasus belum valid", "\n".join(errors), parent=self)
            return
        if not self.kb["attributes"]:
            messagebox.showwarning("Atribut kosong", "Tambahkan atribut terlebih dahulu.", parent=self)
            return
        inference = infer_case(self.kb["root"], case)
        self.pending = PendingConsultation(case=case, customer_name=self.customer_name_var.get().strip(), inference=inference)
        self.result_domain_var.set(f"Domain: {self.kb.get('domain', '-') }  |  Rule hasil: {inference['result_node_id']}")
        self._set_text(self.result_text, inference["conclusion"])
        lines = []
        for step in inference["trace"]:
            mark = "✓" if step["matched"] else "✗"
            action = "kesimpulan node aktif" if step["activated"] else "kesimpulan sebelumnya dipertahankan"
            lines.append(f"{mark} {step['node_id']}: {step['condition']}\n   {step['branch']} → {action}")
        lines.append(f"\nKesimpulan akhir berasal dari {inference['result_node_id']}.")
        self._set_text(self.trace_text, "\n".join(lines))
        self.accept_button.configure(state="normal")
        self.reject_button.configure(state="normal")
        for child in self.rule_editor.winfo_children():
            child.destroy()
        self.status_var.set(f"Konsultasi aktif • {len(inference['trace'])} node ditelusuri")

    def accept_result(self):
        if not self.pending:
            return
        node = self.pending.inference["result_node"]
        if node.get("key_case") is None:
            node["key_case"] = deepcopy(self.pending.case)
            message = f"Kasus disetujui dan disimpan sebagai kasus kunci untuk {node['id']}."
        else:
            message = f"Pakar menyetujui kesimpulan dari {node['id']}. Kasus kunci yang sudah ada tetap dipertahankan."
        self._refresh_rule_tree()
        self.accept_button.configure(state="disabled")
        self.reject_button.configure(state="disabled")
        self.status_var.set("Kesimpulan disetujui oleh pakar")
        messagebox.showinfo("Evaluasi pakar", message, parent=self)

    def reject_result(self):
        if not self.pending:
            return
        for child in self.rule_editor.winfo_children():
            child.destroy()
        inference = self.pending.inference
        active_node = inference["result_node"]
        if active_node.get("key_case") is None:
            ttk.Label(self.rule_editor, text="Kasus kunci belum tersedia", style="Field.TLabel").pack(anchor="w")
            ttk.Label(
                self.rule_editor,
                text=(f"Rule {active_node['id']} belum memiliki kasus kunci. Setujui satu kasus yang "
                      "mewakili kesimpulan ini terlebih dahulu. Setelah itu, sistem dapat mencari "
                      "kondisi pembeda untuk membuat pengecualian."),
                style="Hint.TLabel", wraplength=460, justify="left"
            ).pack(anchor="w", pady=(4, 8))
            ttk.Button(self.rule_editor, text="Tutup", command=lambda: [w.destroy() for w in self.rule_editor.winfo_children()]).pack(anchor="e")
            return
        candidates = build_candidates(self.kb["attributes"], self.pending.case, active_node["key_case"])
        if not candidates:
            ttk.Label(self.rule_editor, text="Tidak ditemukan kondisi pembeda", style="Field.TLabel").pack(anchor="w")
            ttk.Label(
                self.rule_editor,
                text="Nilai atribut kasus baru sama dengan kasus kunci, atau tidak ada atribut yang dapat dibandingkan. Tambahkan atribut yang relevan atau periksa kembali data kasus.",
                style="Hint.TLabel", wraplength=460, justify="left"
            ).pack(anchor="w", pady=(4, 8))
            return
        ttk.Label(self.rule_editor, text=f"Buat rule pengecualian untuk {active_node['id']}", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(self.rule_editor, text="Pilih kondisi yang benar untuk kasus baru dan salah untuk kasus kunci:", style="Hint.TLabel").pack(anchor="w", pady=(3, 5))
        self.candidate_var.set(0)
        self.current_candidates = candidates
        for i, candidate in enumerate(candidates):
            rb = ttk.Radiobutton(self.rule_editor, text=candidate["label"], value=i, variable=self.candidate_var)
            rb.pack(anchor="w", pady=2)
        ttk.Label(self.rule_editor, text="Kesimpulan dari pakar", style="Field.TLabel").pack(anchor="w", pady=(8, 4))
        self.expert_conclusion = tk.Text(self.rule_editor, height=3, wrap="word", font=("Segoe UI", 9), relief="solid", bd=1)
        self.expert_conclusion.pack(fill="x")
        self.expert_conclusion.insert("1.0", "")
        ttk.Button(self.rule_editor, text="Simpan rule pengecualian", style="Accent.TButton", command=self.save_exception_rule).pack(anchor="e", pady=(8, 0))

    def save_exception_rule(self):
        if not self.pending:
            return
        conclusion = self.expert_conclusion.get("1.0", "end").strip()
        if not conclusion:
            messagebox.showwarning("Kesimpulan kosong", "Masukkan kesimpulan yang diberikan oleh pakar.", parent=self)
            return
        selected = self.candidate_var.get()
        if selected < 0 or selected >= len(self.current_candidates):
            messagebox.showwarning("Kondisi belum dipilih", "Pilih salah satu kondisi pembeda.", parent=self)
            return
        inference = self.pending.inference
        parent = find_node(self.kb["root"], inference["frontier_node_id"])
        if parent is None:
            messagebox.showerror("Kesalahan", "Node tujuan tidak ditemukan pada pohon rule.", parent=self)
            return
        side = inference["frontier_side"]
        if parent.get(side) is not None:
            messagebox.showerror("Cabang terisi", "Cabang tujuan sudah terisi. Jalankan konsultasi ulang sebelum menambah rule.", parent=self)
            return
        candidate = self.current_candidates[selected]
        # Guardrail: the selected predicate must truly separate the new case from the key case.
        active_node = inference["result_node"]
        if not evaluate_condition(candidate["condition"], self.pending.case) or evaluate_condition(candidate["condition"], active_node["key_case"]):
            messagebox.showerror("Kondisi tidak valid", "Kondisi harus benar untuk kasus baru dan salah untuk kasus kunci.", parent=self)
            return
        new_node = {
            "id": get_next_node_id(self.kb["root"]),
            "condition": deepcopy(candidate["condition"]),
            "conclusion": conclusion,
            "key_case": deepcopy(self.pending.case),
            "true_child": None,
            "false_child": None,
        }
        parent[side] = new_node
        new_id = new_node["id"]
        self._refresh_rule_tree()
        self._set_text(self.result_text, conclusion)
        self.result_domain_var.set(f"Rule baru: {new_id}  |  Pengecualian dari {active_node['id']}")
        self._set_text(
            self.trace_text,
            f"Rule {new_id} berhasil ditambahkan pada cabang {'KANAN / TRUE' if side == 'true_child' else 'KIRI / FALSE'} dari {parent['id']}.\n"
            f"Kondisi: {condition_text(new_node['condition'])}\n"
            f"Kasus baru menjadi kasus kunci rule {new_id}.\n\nJalankan konsultasi kembali untuk menguji rule baru."
        )
        for child in self.rule_editor.winfo_children():
            child.destroy()
        self.accept_button.configure(state="disabled")
        self.reject_button.configure(state="disabled")
        self.status_var.set(f"Rule {new_id} berhasil ditambahkan")
        messagebox.showinfo("Rule ditambahkan", f"Rule pengecualian {new_id} berhasil disimpan ke knowledge base.", parent=self)

    def apply_kb_settings(self):
        domain = self.domain_var.get().strip()
        conclusion = self.default_text.get("1.0", "end").strip()
        if not domain:
            messagebox.showwarning("Validasi", "Nama domain wajib diisi.", parent=self)
            return
        if not conclusion:
            messagebox.showwarning("Validasi", "Kesimpulan default tidak boleh kosong.", parent=self)
            return
        self.kb["domain"] = domain
        self.kb["root"]["conclusion"] = conclusion
        self.status_var.set("Pengaturan knowledge base diterapkan")
        messagebox.showinfo("Tersimpan", "Domain dan kesimpulan default telah diperbarui.", parent=self)
        self._refresh_rule_tree()

    def add_attribute(self):
        dialog = AttributeDialog(self)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        if any(a["name"].casefold() == dialog.result["name"].casefold() for a in self.kb["attributes"]):
            messagebox.showwarning("Nama duplikat", "Nama atribut sudah digunakan.", parent=self)
            return
        self.kb["attributes"].append(dialog.result)
        self._refresh_attributes()
        self._refresh_case_form()

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
        if any(i != index and a["name"].casefold() == dialog.result["name"].casefold() for i, a in enumerate(self.kb["attributes"])):
            messagebox.showwarning("Nama duplikat", "Nama atribut sudah digunakan.", parent=self)
            return
        used = self._attribute_is_referenced(old["name"])
        if used and (dialog.result["name"] != old["name"] or dialog.result["type"] != old["type"]):
            messagebox.showwarning("Atribut sedang digunakan", "Nama atau jenis atribut tidak dapat diubah karena sudah dipakai oleh kondisi rule atau kasus kunci. Pilihan kategori masih dapat diperbarui.", parent=self)
            return
        self.kb["attributes"][index] = dialog.result
        self._refresh_attributes()
        self._refresh_case_form()

    def _attribute_is_referenced(self, name: str) -> bool:
        for node in iter_nodes(self.kb["root"]):
            if node.get("condition", {}).get("attribute") == name:
                return True
            if name in (node.get("key_case") or {}):
                return True
        return False

    def delete_attribute(self):
        selection = self.attr_tree.selection()
        if not selection:
            messagebox.showinfo("Pilih atribut", "Pilih atribut yang ingin dihapus.", parent=self)
            return
        index = int(selection[0])
        attr = self.kb["attributes"][index]
        if self._attribute_is_referenced(attr["name"]):
            messagebox.showwarning("Atribut sedang digunakan", "Atribut ini sudah dipakai oleh rule atau kasus kunci sehingga tidak dapat dihapus.", parent=self)
            return
        if messagebox.askyesno("Hapus atribut", f"Hapus atribut '{attr['name']}'?", parent=self):
            self.kb["attributes"].pop(index)
            self._refresh_attributes()
            self._refresh_case_form()

    def show_selected_rule(self, _event=None):
        selection = self.rule_tree.selection()
        if not selection:
            return
        node = find_node(self.kb["root"], selection[0])
        if not node:
            return
        key_case = node.get("key_case")
        detail = (
            f"ID: {node['id']}\n"
            f"Kondisi: {condition_text(node['condition'])}\n\n"
            f"Kesimpulan:\n{node.get('conclusion', '')}\n\n"
            f"Kasus kunci:\n{json.dumps(key_case, ensure_ascii=False, indent=2) if key_case else 'Belum ditetapkan'}\n\n"
            f"True-child (kanan): {node.get('true_child', {}).get('id') if node.get('true_child') else '—'}\n"
            f"False-child (kiri): {node.get('false_child', {}).get('id') if node.get('false_child') else '—'}"
        )
        self._set_text(self.rule_detail, detail)

    def new_kb(self):
        if not messagebox.askyesno("Knowledge base baru", "Buat knowledge base baru? Perubahan yang belum disimpan akan hilang.", parent=self):
            return
        self.kb = {
            "version": 1,
            "domain": "Domain baru",
            "attributes": [],
            "root": {
                "id": "R0", "condition": {"attribute": None, "operator": "always", "value": True},
                "conclusion": "Kesimpulan default belum diisi.", "key_case": None,
                "true_child": None, "false_child": None,
            },
        }
        self.current_path = None
        self.refresh_all()
        self.status_var.set("Knowledge base baru dibuat")

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
            payload = deepcopy(self.kb)
            payload["saved_at"] = datetime.now().isoformat(timespec="seconds")
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
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
            loaded = json.loads(Path(path).read_text(encoding="utf-8"))
            self._validate_kb(loaded)
            self.kb = loaded
            self.kb.setdefault("version", 1)
            self.current_path = Path(path)
            self.refresh_all()
            self.status_var.set(f"Dibuka: {Path(path).name}")
        except (OSError, json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
            messagebox.showerror("Gagal membuka", f"File bukan knowledge base RDR yang valid.\n\nDetail: {exc}", parent=self)

    @staticmethod
    def _validate_kb(data: Any):
        if not isinstance(data, dict) or not isinstance(data.get("attributes"), list) or not isinstance(data.get("root"), dict):
            raise ValueError("Struktur utama tidak lengkap")
        if not data.get("domain"):
            raise ValueError("Domain kosong")
        attr_types: dict[str, str] = {}
        for attr in data["attributes"]:
            if not isinstance(attr, dict) or not attr.get("name") or attr.get("type") not in {"numeric", "categorical"}:
                raise ValueError("Definisi atribut tidak valid")
            normalized_name = str(attr["name"]).casefold()
            if normalized_name in attr_types:
                raise ValueError("Nama atribut duplikat")
            attr_types[normalized_name] = attr["type"]

        seen_ids: set[str] = set()
        allowed_ops = {"always", "eq", "ne", "gt", "ge", "lt", "le"}

        def validate_node(node: Any):
            if not isinstance(node, dict):
                raise ValueError("Node rule harus berupa objek")
            node_id = str(node.get("id", ""))
            if not node_id or node_id in seen_ids:
                raise ValueError("ID rule kosong atau duplikat")
            seen_ids.add(node_id)
            if not isinstance(node.get("condition"), dict) or not isinstance(node.get("conclusion"), str) or not node.get("conclusion").strip():
                raise ValueError(f"Rule {node_id} tidak valid")
            condition = node["condition"]
            op = condition.get("operator")
            if op not in allowed_ops:
                raise ValueError(f"Operator kondisi pada {node_id} tidak dikenal")
            if op != "always":
                attr_name = str(condition.get("attribute", ""))
                attr_type = attr_types.get(attr_name.casefold())
                if attr_type is None:
                    raise ValueError(f"Atribut pada rule {node_id} tidak ditemukan")
                if attr_type == "categorical" and op not in {"eq", "ne"}:
                    raise ValueError(f"Operator numerik tidak sesuai untuk atribut kategorikal pada {node_id}")
                if attr_type == "numeric" and op in {"eq", "ne", "gt", "ge", "lt", "le"}:
                    try:
                        number = float(condition.get("value"))
                        if not math.isfinite(number):
                            raise ValueError
                    except (TypeError, ValueError):
                        raise ValueError(f"Nilai kondisi numerik pada {node_id} tidak valid")
            key_case = node.get("key_case")
            if key_case is not None and not isinstance(key_case, dict):
                raise ValueError(f"Kasus kunci pada {node_id} tidak valid")
            for child_name in ("true_child", "false_child"):
                child = node.get(child_name)
                if child is not None:
                    validate_node(child)

        validate_node(data["root"])
        if data["root"]["condition"].get("operator") != "always":
            raise ValueError("Kondisi root harus t / selalu benar")

    def show_about(self):
        messagebox.showinfo(
            "Tentang RDR Studio",
            f"{APP_TITLE}\nVersi {APP_VERSION}\n\nAplikasi demonstrasi Ripple Down Rules untuk sistem rekomendasi pakar.\nDibangun dengan Python dan Tkinter tanpa dependensi pihak ketiga.",
            parent=self,
        )

    def on_close(self):
        self.destroy()


def main():
    app = RDRApp()
    app.mainloop()


if __name__ == "__main__":
    main()