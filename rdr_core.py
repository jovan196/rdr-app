"""Inti aplikasi Ripple Down Rules (RDR) — bebas antarmuka.

Modul ini tidak mengimpor Tkinter sehingga dapat dipakai oleh GUI (main.py)
maupun CLI (cli.py). Semua kesalahan validasi dilaporkan sebagai ValueError
dengan pesan berbahasa Indonesia yang dapat langsung ditampilkan antarmuka.
"""
from __future__ import annotations

import json
import math
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
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


def new_knowledge_base() -> dict[str, Any]:
    """Return a blank knowledge base with a single default root rule."""
    return {
        "version": 1,
        "domain": "Domain baru",
        "attributes": [],
        "root": {
            "id": "R0", "condition": {"attribute": None, "operator": "always", "value": True},
            "conclusion": "Kesimpulan default belum diisi.", "key_case": None,
            "true_child": None, "false_child": None,
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


def parse_attribute(name: str, kind: str, choices_text: str = "") -> dict[str, Any]:
    """Validate raw attribute input and return a normalized attribute definition."""
    name = name.strip()
    kind = kind.strip()
    if not name:
        raise ValueError("Nama atribut wajib diisi.")
    if any(ch.isspace() for ch in name):
        raise ValueError("Gunakan nama atribut tanpa spasi (contoh: anggaran_juta).")
    if kind not in {"numeric", "categorical"}:
        raise ValueError("Jenis data atribut tidak dikenal.")
    choices = [x.strip() for x in choices_text.split(",") if x.strip()] if kind == "categorical" else []
    return {"name": name, "type": kind, "choices": choices}


def attribute_is_referenced(root: dict[str, Any], name: str) -> bool:
    """True jika atribut dipakai oleh kondisi rule atau kasus kunci mana pun."""
    for node in iter_nodes(root):
        if node.get("condition", {}).get("attribute") == name:
            return True
        if name in (node.get("key_case") or {}):
            return True
    return False


def validate_kb(data: Any):
    """Raise ValueError jika struktur knowledge base tidak valid."""
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


def load_kb(path) -> dict[str, Any]:
    """Baca dan validasi knowledge base dari file JSON."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_kb(data)
    data.setdefault("version", 1)
    return data


def save_kb(kb: dict[str, Any], path):
    """Simpan knowledge base ke file JSON (menambahkan stempel saved_at)."""
    payload = deepcopy(kb)
    payload["saved_at"] = datetime.now().isoformat(timespec="seconds")
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


@dataclass
class PendingConsultation:
    case: dict[str, Any]
    customer_name: str
    inference: dict[str, Any]


class RDREngine:
    """Inti aplikasi: menyimpan knowledge base beserta alur konsultasi dan update knowledge.

    Antarmuka (GUI/CLI) cukup memanggil metode kelas ini dan menampilkan hasilnya;
    seluruh keputusan logika RDR terjadi di sini.
    """

    def __init__(self, kb: Optional[dict[str, Any]] = None):
        self.kb = kb if kb is not None else make_sample_kb()
        self.pending: Optional[PendingConsultation] = None
        self.candidates: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Knowledge base
    # ------------------------------------------------------------------
    def new_kb(self):
        self.kb = new_knowledge_base()
        self.reset_consultation()

    def load(self, path):
        self.kb = load_kb(path)
        self.reset_consultation()

    def save(self, path):
        save_kb(self.kb, path)

    def reset_consultation(self):
        self.pending = None
        self.candidates = []

    def apply_settings(self, domain: str, conclusion: str):
        domain = domain.strip()
        conclusion = conclusion.strip()
        if not domain:
            raise ValueError("Nama domain wajib diisi.")
        if not conclusion:
            raise ValueError("Kesimpulan default tidak boleh kosong.")
        self.kb["domain"] = domain
        self.kb["root"]["conclusion"] = conclusion

    # ------------------------------------------------------------------
    # Atribut
    # ------------------------------------------------------------------
    def add_attribute(self, attr: dict[str, Any]):
        if any(a["name"].casefold() == attr["name"].casefold() for a in self.kb["attributes"]):
            raise ValueError("Nama atribut sudah digunakan.")
        self.kb["attributes"].append(attr)

    def update_attribute(self, index: int, attr: dict[str, Any]):
        old = self.kb["attributes"][index]
        if any(i != index and a["name"].casefold() == attr["name"].casefold() for i, a in enumerate(self.kb["attributes"])):
            raise ValueError("Nama atribut sudah digunakan.")
        if attribute_is_referenced(self.kb["root"], old["name"]) and (attr["name"] != old["name"] or attr["type"] != old["type"]):
            raise ValueError(
                "Nama atau jenis atribut tidak dapat diubah karena sudah dipakai oleh kondisi rule "
                "atau kasus kunci. Pilihan kategori masih dapat diperbarui."
            )
        self.kb["attributes"][index] = attr

    def delete_attribute(self, index: int):
        attr = self.kb["attributes"][index]
        if attribute_is_referenced(self.kb["root"], attr["name"]):
            raise ValueError("Atribut ini sudah dipakai oleh rule atau kasus kunci sehingga tidak dapat dihapus.")
        self.kb["attributes"].pop(index)

    # ------------------------------------------------------------------
    # Konsultasi dan update knowledge
    # ------------------------------------------------------------------
    def run_consultation(self, raw_values: dict[str, str], customer_name: str = "") -> dict[str, Any]:
        case, errors = validate_case(self.kb["attributes"], raw_values)
        if errors:
            raise ValueError("\n".join(errors))
        if not self.kb["attributes"]:
            raise ValueError("Tambahkan atribut terlebih dahulu.")
        inference = infer_case(self.kb["root"], case)
        self.pending = PendingConsultation(case=case, customer_name=customer_name.strip(), inference=inference)
        self.candidates = []
        return inference

    def accept_result(self) -> dict[str, Any]:
        """Setujui kesimpulan aktif; simpan kasus sebagai kasus kunci bila rule belum memilikinya."""
        if not self.pending:
            raise ValueError("Belum ada konsultasi yang dapat dievaluasi.")
        node = self.pending.inference["result_node"]
        stored = node.get("key_case") is None
        if stored:
            node["key_case"] = deepcopy(self.pending.case)
        return {"node_id": node["id"], "stored_key_case": stored}

    def prepare_exception(self) -> tuple[str, list[dict[str, Any]]]:
        """Siapkan kandidat kondisi pembeda untuk rule pengecualian.

        Return ("ok", candidates), ("no_key_case", []), atau ("no_candidates", []).
        """
        if not self.pending:
            raise ValueError("Belum ada konsultasi yang dapat dievaluasi.")
        self.candidates = []
        active_node = self.pending.inference["result_node"]
        if active_node.get("key_case") is None:
            return "no_key_case", []
        candidates = build_candidates(self.kb["attributes"], self.pending.case, active_node["key_case"])
        if not candidates:
            return "no_candidates", []
        self.candidates = candidates
        return "ok", candidates

    def save_exception(self, candidate_index: int, conclusion: str) -> dict[str, Any]:
        """Tambahkan rule pengecualian ke pohon dan kembalikan info penempatannya."""
        if not self.pending:
            raise ValueError("Belum ada konsultasi yang dapat dievaluasi.")
        conclusion = conclusion.strip()
        if not conclusion:
            raise ValueError("Masukkan kesimpulan yang diberikan oleh pakar.")
        if candidate_index < 0 or candidate_index >= len(self.candidates):
            raise ValueError("Pilih salah satu kondisi pembeda.")
        inference = self.pending.inference
        parent = find_node(self.kb["root"], inference["frontier_node_id"])
        if parent is None:
            raise ValueError("Node tujuan tidak ditemukan pada pohon rule.")
        side = inference["frontier_side"]
        if parent.get(side) is not None:
            raise ValueError("Cabang tujuan sudah terisi. Jalankan konsultasi ulang sebelum menambah rule.")
        candidate = self.candidates[candidate_index]
        active_node = inference["result_node"]
        # Guardrail: the selected predicate must truly separate the new case from the key case.
        if not evaluate_condition(candidate["condition"], self.pending.case) or evaluate_condition(candidate["condition"], active_node["key_case"]):
            raise ValueError("Kondisi harus benar untuk kasus baru dan salah untuk kasus kunci.")
        new_node = {
            "id": get_next_node_id(self.kb["root"]),
            "condition": deepcopy(candidate["condition"]),
            "conclusion": conclusion,
            "key_case": deepcopy(self.pending.case),
            "true_child": None,
            "false_child": None,
        }
        parent[side] = new_node
        self.candidates = []
        return {
            "node": new_node,
            "parent_id": parent["id"],
            "side": side,
            "active_node_id": active_node["id"],
        }
