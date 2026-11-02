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
APP_VERSION = "1.1.0"

NUMERIC_OPERATORS = ("ge", "le", "gt", "lt", "eq", "ne")
CATEGORICAL_OPERATORS = ("eq", "ne")
OPERATOR_SYMBOLS = {
    "eq": "=",
    "ne": "≠",
    "gt": ">",
    "ge": "≥",
    "lt": "<",
    "le": "≤",
}


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


def new_knowledge_base(domain: str = "Domain baru", default_conclusion: str = "Kesimpulan default belum diisi.") -> dict[str, Any]:
    """Return a blank knowledge base with a single default root rule (t -> kesimpulan default)."""
    return {
        "version": 1,
        "domain": domain.strip() or "Domain baru",
        "attributes": [],
        "root": {
            "id": "R0",
            "condition": {"attribute": None, "operator": "always", "value": True},
            "conclusion": default_conclusion.strip() or "Kesimpulan default belum diisi.",
            "key_case": None,
            "true_child": None,
            "false_child": None,
        },
    }


def _format_value(value: Any) -> str:
    if isinstance(value, float) and not isinstance(value, bool) and math.isfinite(value):
        return f"{value:g}"
    return str(value)


def condition_text(condition: dict[str, Any]) -> str:
    op = condition.get("operator", "always")
    if op == "always":
        return "SELALU BENAR (t)"
    if op == "and":
        parts = []
        for sub in condition.get("conditions", []):
            text = condition_text(sub)
            parts.append(f"({text})" if sub.get("operator") == "and" else text)
        return " DAN ".join(parts) if parts else "—"
    attr = condition.get("attribute", "?")
    value = _format_value(condition.get("value"))
    return f"{attr} {OPERATOR_SYMBOLS.get(op, op)} {value}"


def combine_conditions(conditions: list[dict[str, Any]]) -> dict[str, Any]:
    """Gabungkan satu atau beberapa kondisi atomik menjadi satu kondisi (atomik atau konjungsi DAN)."""
    flattened: list[dict[str, Any]] = []
    for cond in conditions:
        if cond.get("operator") == "and":
            flattened.extend(cond.get("conditions", []))
        else:
            flattened.append(cond)
    if not flattened:
        raise ValueError("Pilih minimal satu kondisi pembeda.")
    unique: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for cond in flattened:
        key = json.dumps(cond, sort_keys=True, ensure_ascii=False)
        if key not in seen_keys:
            seen_keys.add(key)
            unique.append(deepcopy(cond))
    if len(unique) == 1:
        return unique[0]
    return {"operator": "and", "conditions": unique}


def _is_number(val: Any) -> bool:
    return isinstance(val, (int, float)) and not isinstance(val, bool)


def evaluate_condition(condition: dict[str, Any], case: Optional[dict[str, Any]]) -> bool:
    op = condition.get("operator", "always")
    if op == "always":
        return True
    if not case:
        return False
    if op == "and":
        sub_conditions = condition.get("conditions") or []
        return bool(sub_conditions) and all(evaluate_condition(sub, case) for sub in sub_conditions)
    attr = condition.get("attribute")
    if attr not in case:
        return False
    actual = case[attr]
    expected = condition.get("value")
    if op in {"eq", "ne"}:
        if _is_number(actual) or _is_number(expected):
            try:
                a_num, b_num = float(actual), float(expected)
                if math.isfinite(a_num) and math.isfinite(b_num):
                    matched = a_num == b_num
                    return matched if op == "eq" else not matched
            except (TypeError, ValueError):
                pass
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
    """Telusuri binary tree RDR dan kembalikan kesimpulan terakhir yang kondisinya terpenuhi.

    - Kondisi terpenuhi (True): kesimpulan node ini menganulir kesimpulan aktif sebelumnya,
      lalu penelusuran berlanjut ke anak kanan (true_child / perkecualian).
    - Kondisi tidak terpenuhi (False): kesimpulan aktif sebelumnya tetap berlaku,
      lalu penelusuran berlanjut ke anak kiri (false_child).
    - Penelusuran berhenti saat cabang anak yang dituju masih kosong (None).
    """
    current = root
    active_node: Optional[dict[str, Any]] = None
    trace: list[dict[str, Any]] = []
    frontier_node = root
    frontier_side = "true_child"
    while current is not None:
        prev_active_id = active_node["id"] if active_node is not None else None
        matched = evaluate_condition(current["condition"], case)
        side = "true_child" if matched else "false_child"
        if matched:
            active_node = current
        current_active_id = active_node["id"] if active_node is not None else root["id"]
        trace.append({
            "node_id": current["id"],
            "condition": condition_text(current["condition"]),
            "matched": matched,
            "branch": "KANAN / TRUE" if matched else "KIRI / FALSE",
            "activated": matched,
            "previous_node_id": prev_active_id,
            "active_node_id": current_active_id,
            "conclusion": current.get("conclusion", ""),
        })
        child = current.get(side)
        if child is None:
            frontier_node = current
            frontier_side = side
            break
        current = child
    if active_node is None:
        # Kondisi root selalu t (benar); fallback defensif bila struktur dibuat manual.
        active_node = root
    return {
        "conclusion": active_node.get("conclusion", ""),
        "result_node_id": active_node["id"],
        "result_node": active_node,
        "trace": trace,
        "frontier_node_id": frontier_node["id"],
        "frontier_side": frontier_side,
    }


def _normalize_number(num: float) -> int | float:
    return int(num) if num.is_integer() else num


def build_candidates(
    attributes: list[dict[str, Any]],
    case: dict[str, Any],
    key_case: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """Bangun daftar kandidat kondisi yang dipenuhi kasus baru dan tidak dipenuhi kasus kunci.

    Apabila rule yang dianulir belum memiliki kasus kunci spesifik (misalnya rule default R0
    pada kasus pertama, atau atribut baru ditambahkan kemudian), maka kasus kunci untuk atribut
    tersebut dianggap kosong sehingga setiap kondisi yang dipenuhi oleh kasus baru bernilai
    benar pada kasus baru dan salah pada kasus kunci.
    """
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_candidate(condition: dict[str, Any], label: str):
        if not evaluate_condition(condition, case):
            return
        if key_case and evaluate_condition(condition, key_case):
            return
        sig = json.dumps(condition, sort_keys=True, ensure_ascii=False)
        if sig not in seen:
            seen.add(sig)
            candidates.append({"condition": condition, "label": label})

    for attr in attributes:
        name = attr["name"]
        if name not in case:
            continue
        new_value = case[name]
        has_old = bool(key_case) and (name in key_case) and (key_case[name] is not None)

        if not has_old:
            if attr["type"] == "numeric":
                try:
                    new_num = float(new_value)
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(new_num):
                    continue
                clean_new = _normalize_number(new_num)
                add_candidate(
                    {"attribute": name, "operator": "ge", "value": clean_new},
                    f"{name} ≥ {new_num:g} (kasus baru: {new_num:g}; kasus kunci kosong)",
                )
                add_candidate(
                    {"attribute": name, "operator": "le", "value": clean_new},
                    f"{name} ≤ {new_num:g} (kasus baru: {new_num:g}; kasus kunci kosong)",
                )
                add_candidate(
                    {"attribute": name, "operator": "eq", "value": clean_new},
                    f"{name} = {new_num:g} (kasus baru: {new_num:g}; kasus kunci kosong)",
                )
            else:
                text_val = str(new_value)
                add_candidate(
                    {"attribute": name, "operator": "eq", "value": text_val},
                    f'{name} = "{text_val}" (kasus baru: "{text_val}"; kasus kunci kosong)',
                )
            continue

        old_value = key_case[name]  # type: ignore[index]
        if attr["type"] == "numeric":
            try:
                new_num, old_num = float(new_value), float(old_value)
            except (TypeError, ValueError):
                continue
            if not (math.isfinite(new_num) and math.isfinite(old_num)) or new_num == old_num:
                continue
            midpoint = _normalize_number((new_num + old_num) / 2.0)
            clean_new = _normalize_number(new_num)
            clean_old = _normalize_number(old_num)
            if new_num > old_num:
                add_candidate(
                    {"attribute": name, "operator": "ge", "value": midpoint},
                    f"{name} ≥ {midpoint:g} (titik tengah; kasus baru: {new_num:g}, kasus kunci: {old_num:g})",
                )
                add_candidate(
                    {"attribute": name, "operator": "ge", "value": clean_new},
                    f"{name} ≥ {clean_new:g} (minimal nilai kasus baru; kasus kunci: {old_num:g})",
                )
                add_candidate(
                    {"attribute": name, "operator": "gt", "value": clean_old},
                    f"{name} > {clean_old:g} (di atas kasus kunci {old_num:g}; kasus baru: {new_num:g})",
                )
            else:
                add_candidate(
                    {"attribute": name, "operator": "le", "value": midpoint},
                    f"{name} ≤ {midpoint:g} (titik tengah; kasus baru: {new_num:g}, kasus kunci: {old_num:g})",
                )
                add_candidate(
                    {"attribute": name, "operator": "le", "value": clean_new},
                    f"{name} ≤ {clean_new:g} (maksimal nilai kasus baru; kasus kunci: {old_num:g})",
                )
                add_candidate(
                    {"attribute": name, "operator": "lt", "value": clean_old},
                    f"{name} < {clean_old:g} (di bawah kasus kunci {old_num:g}; kasus baru: {new_num:g})",
                )
        else:
            if str(new_value).strip().casefold() == str(old_value).strip().casefold():
                continue
            add_candidate(
                {"attribute": name, "operator": "eq", "value": str(new_value)},
                f'{name} = "{new_value}" (kasus kunci: "{old_value}")',
            )
            add_candidate(
                {"attribute": name, "operator": "ne", "value": str(old_value)},
                f'{name} ≠ "{old_value}" (kasus baru: "{new_value}")',
            )
    return candidates


def make_custom_candidate(
    attributes: list[dict[str, Any]],
    case: dict[str, Any],
    key_case: Optional[dict[str, Any]],
    attr_name: str,
    operator: str,
    raw_value: str,
) -> dict[str, Any]:
    """Buat dan validasi satu kandidat kondisi kustom dari pakar."""
    attr = next((a for a in attributes if a["name"] == attr_name), None)
    if attr is None:
        raise ValueError(f"Atribut '{attr_name}' tidak ditemukan.")
    raw_value = raw_value.strip()
    if not raw_value:
        raise ValueError("Nilai kondisi wajib diisi.")

    if attr["type"] == "numeric":
        if operator not in NUMERIC_OPERATORS:
            raise ValueError("Operator tidak valid untuk atribut numerik.")
        try:
            num = float(raw_value.replace(",", "."))
            if not math.isfinite(num):
                raise ValueError
        except ValueError:
            raise ValueError(f"Nilai untuk atribut numerik '{attr_name}' harus berupa angka yang valid.")
        parsed_val: Any = _normalize_number(num)
    else:
        if operator not in CATEGORICAL_OPERATORS:
            raise ValueError("Atribut kategorikal hanya mendukung operator '=' atau '≠'.")
        choices = attr.get("choices") or []
        if choices:
            matched_choice = next((c for c in choices if c.casefold() == raw_value.casefold()), None)
            if matched_choice is None:
                raise ValueError(f"Nilai '{attr_name}' harus salah satu dari: {', '.join(choices)}.")
            parsed_val = matched_choice
        else:
            parsed_val = raw_value

    condition = {"attribute": attr_name, "operator": operator, "value": parsed_val}
    text = condition_text(condition)
    if not evaluate_condition(condition, case):
        raise ValueError(f"Kondisi '{text}' tidak dipenuhi oleh kasus baru ({attr_name} = {_format_value(case.get(attr_name))}).")
    if key_case and evaluate_condition(condition, key_case):
        raise ValueError(
            f"Kondisi '{text}' juga dipenuhi oleh kasus kunci ({attr_name} = {_format_value(key_case.get(attr_name))}), "
            "sehingga tidak membedakan kasus baru dari kasus kunci."
        )
    old_info = f"kasus kunci: {_format_value(key_case.get(attr_name))}" if (key_case and attr_name in key_case) else "kasus kunci kosong"
    return {
        "condition": condition,
        "label": f"{text} [kustom; kasus baru: {_format_value(case.get(attr_name))}, {old_info}]",
    }


def validate_case(attributes: list[dict[str, Any]], raw_values: dict[str, str]) -> tuple[dict[str, Any], list[str]]:
    case: dict[str, Any] = {}
    errors: list[str] = []
    for attr in attributes:
        name = attr["name"]
        raw = str(raw_values.get(name, "")).strip()
        if not raw:
            errors.append(f"Atribut '{name}' belum diisi.")
            continue
        if attr["type"] == "numeric":
            try:
                value = float(raw.replace(",", "."))
                if not math.isfinite(value):
                    raise ValueError
                case[name] = _normalize_number(value)
            except ValueError:
                errors.append(f"Atribut '{name}' harus berupa angka yang valid.")
        else:
            choices = attr.get("choices") or []
            if choices:
                matched = next((c for c in choices if c.casefold() == raw.casefold()), None)
                if matched is None:
                    errors.append(f"Atribut '{name}' harus memilih salah satu dari: {', '.join(choices)}.")
                    continue
                case[name] = matched
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
    choices: list[str] = []
    if kind == "categorical":
        seen: set[str] = set()
        for item in choices_text.split(","):
            cleaned = item.strip()
            if cleaned and cleaned.casefold() not in seen:
                seen.add(cleaned.casefold())
                choices.append(cleaned)
    return {"name": name, "type": kind, "choices": choices}


def _condition_references_attribute(condition: dict[str, Any], name: str) -> bool:
    if condition.get("operator") == "and":
        return any(_condition_references_attribute(sub, name) for sub in condition.get("conditions", []))
    return condition.get("attribute") == name


def attribute_is_referenced(root: dict[str, Any], name: str) -> bool:
    """True jika atribut dipakai oleh kondisi rule atau kasus kunci mana pun."""
    for node in iter_nodes(root):
        if _condition_references_attribute(node.get("condition", {}), name):
            return True
        if name in (node.get("key_case") or {}):
            return True
    return False


def validate_kb(data: Any):
    """Raise ValueError jika struktur knowledge base tidak valid."""
    if not isinstance(data, dict) or not isinstance(data.get("attributes"), list) or not isinstance(data.get("root"), dict):
        raise ValueError("Struktur utama tidak lengkap")
    if not isinstance(data.get("domain"), str) or not data.get("domain", "").strip():
        raise ValueError("Domain kosong")
    attr_types: dict[str, str] = {}
    seen_folded: set[str] = set()
    for attr in data["attributes"]:
        if not isinstance(attr, dict) or not isinstance(attr.get("name"), str) or not attr["name"].strip():
            raise ValueError("Definisi atribut tidak valid")
        if attr.get("type") not in {"numeric", "categorical"}:
            raise ValueError("Definisi atribut tidak valid")
        choices = attr.setdefault("choices", [])
        if not isinstance(choices, list) or not all(isinstance(c, str) for c in choices):
            raise ValueError(f"Pilihan kategori pada atribut '{attr['name']}' tidak valid")
        folded = attr["name"].casefold()
        if folded in seen_folded:
            raise ValueError("Nama atribut duplikat")
        seen_folded.add(folded)
        attr_types[attr["name"]] = attr["type"]

    seen_ids: set[str] = set()
    allowed_atomic_ops = {"always", "eq", "ne", "gt", "ge", "lt", "le"}

    def validate_condition_obj(condition: Any, node_id: str, allow_always: bool = True):
        if not isinstance(condition, dict):
            raise ValueError(f"Kondisi pada rule {node_id} tidak valid")
        op = condition.get("operator")
        if op == "and":
            subs = condition.get("conditions")
            if not isinstance(subs, list) or not subs:
                raise ValueError(f"Kondisi konjungsi pada {node_id} kosong atau tidak valid")
            for sub in subs:
                validate_condition_obj(sub, node_id, allow_always=False)
            return
        if op not in allowed_atomic_ops or (op == "always" and not allow_always):
            raise ValueError(f"Operator kondisi pada {node_id} tidak dikenal")
        if op != "always":
            attr_name = str(condition.get("attribute", ""))
            attr_type = attr_types.get(attr_name)
            if attr_type is None:
                raise ValueError(f"Atribut '{attr_name}' pada rule {node_id} tidak ditemukan")
            if attr_type == "categorical" and op not in {"eq", "ne"}:
                raise ValueError(f"Operator numerik tidak sesuai untuk atribut kategorikal pada {node_id}")
            if attr_type == "numeric":
                try:
                    number = float(condition.get("value"))
                    if not math.isfinite(number):
                        raise ValueError
                except (TypeError, ValueError):
                    raise ValueError(f"Nilai kondisi numerik pada {node_id} tidak valid")

    def validate_node(node: Any):
        if not isinstance(node, dict):
            raise ValueError("Node rule harus berupa objek")
        node_id = str(node.get("id", ""))
        if not node_id or node_id in seen_ids:
            raise ValueError("ID rule kosong atau duplikat")
        seen_ids.add(node_id)
        if not isinstance(node.get("conclusion"), str) or not node.get("conclusion", "").strip():
            raise ValueError(f"Rule {node_id} tidak valid")
        validate_condition_obj(node.get("condition"), node_id, allow_always=True)
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
        self.last_trace: list[dict[str, Any]] = []
        self.last_result_node_id: Optional[str] = None

    # ------------------------------------------------------------------
    # Knowledge base
    # ------------------------------------------------------------------
    def new_kb(self, domain: str = "Domain baru", default_conclusion: str = "Kesimpulan default belum diisi."):
        self.kb = new_knowledge_base(domain=domain, default_conclusion=default_conclusion)
        self.reset_consultation(clear_highlight=True)

    def load_sample_kb(self):
        self.kb = make_sample_kb()
        self.reset_consultation(clear_highlight=True)

    def load(self, path):
        self.kb = load_kb(path)
        self.reset_consultation(clear_highlight=True)

    def save(self, path):
        save_kb(self.kb, path)

    def reset_consultation(self, clear_highlight: bool = False):
        self.pending = None
        self.candidates = []
        if clear_highlight:
            self.last_trace = []
            self.last_result_node_id = None

    def apply_settings(self, domain: str, conclusion: str):
        domain = domain.strip()
        conclusion = conclusion.strip()
        if not domain:
            raise ValueError("Nama domain wajib diisi.")
        if not conclusion:
            raise ValueError("Kesimpulan default tidak boleh kosong.")
        self.kb["domain"] = domain
        self.kb["root"]["conclusion"] = conclusion
        self.reset_consultation()

    # ------------------------------------------------------------------
    # Atribut
    # ------------------------------------------------------------------
    def add_attribute(self, attr: dict[str, Any]):
        if any(a["name"].casefold() == attr["name"].casefold() for a in self.kb["attributes"]):
            raise ValueError("Nama atribut sudah digunakan.")
        self.kb["attributes"].append(attr)
        self.reset_consultation()

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
        self.reset_consultation()

    def delete_attribute(self, index: int):
        attr = self.kb["attributes"][index]
        if attribute_is_referenced(self.kb["root"], attr["name"]):
            raise ValueError("Atribut ini sudah dipakai oleh rule atau kasus kunci sehingga tidak dapat dihapus.")
        self.kb["attributes"].pop(index)
        self.reset_consultation()

    # ------------------------------------------------------------------
    # Konsultasi dan update knowledge
    # ------------------------------------------------------------------
    def run_consultation(self, raw_values: dict[str, str], customer_name: str = "") -> dict[str, Any]:
        if not self.kb["attributes"]:
            raise ValueError("Tambahkan atribut terlebih dahulu.")
        case, errors = validate_case(self.kb["attributes"], raw_values)
        if errors:
            raise ValueError("\n".join(errors))
        inference = infer_case(self.kb["root"], case)
        self.pending = PendingConsultation(case=case, customer_name=customer_name.strip(), inference=inference)
        self.candidates = []
        self.last_trace = deepcopy(inference["trace"])
        self.last_result_node_id = inference["result_node_id"]
        return inference

    def accept_result(self) -> dict[str, Any]:
        """Pakar menyetujui kesimpulan; berikan hasil ke konsumen dan selesaikan proses.

        Jika rule kesimpulan aktif belum memiliki kasus kunci (mis. R0), kasus ini
        disimpan sebagai kasus kunci acuan rule tersebut.
        """
        if not self.pending:
            raise ValueError("Belum ada konsultasi aktif yang dapat dievaluasi.")
        node = self.pending.inference["result_node"]
        customer_name = self.pending.customer_name
        case_snapshot = deepcopy(self.pending.case)
        stored = node.get("key_case") is None
        if stored:
            node["key_case"] = case_snapshot
        result = {
            "node_id": node["id"],
            "conclusion": node.get("conclusion", ""),
            "customer_name": customer_name,
            "stored_key_case": stored,
        }
        self.reset_consultation()
        return result

    def prepare_exception(self) -> tuple[str, list[dict[str, Any]]]:
        """Siapkan kandidat kondisi pembeda untuk rule perkecualian.

        Return ("ok", candidates) atau ("no_candidates", []).
        """
        if not self.pending:
            raise ValueError("Belum ada konsultasi aktif yang dapat dievaluasi.")
        self.candidates = []
        active_node = self.pending.inference["result_node"]
        key_case = active_node.get("key_case")
        candidates = build_candidates(self.kb["attributes"], self.pending.case, key_case)
        if not candidates:
            return "no_candidates", []
        self.candidates = candidates
        return "ok", candidates

    def add_custom_candidate(self, attr_name: str, operator: str, raw_value: str) -> dict[str, Any]:
        """Tambahkan satu kandidat kondisi kustom yang tervalidasi ke daftar kandidat aktif."""
        if not self.pending:
            raise ValueError("Belum ada konsultasi aktif yang dapat dievaluasi.")
        active_node = self.pending.inference["result_node"]
        candidate = make_custom_candidate(
            self.kb["attributes"],
            self.pending.case,
            active_node.get("key_case"),
            attr_name,
            operator,
            raw_value,
        )
        sig = json.dumps(candidate["condition"], sort_keys=True, ensure_ascii=False)
        for existing in self.candidates:
            if json.dumps(existing["condition"], sort_keys=True, ensure_ascii=False) == sig:
                return existing
        self.candidates.append(candidate)
        return candidate

    def save_exception(self, candidate_indices: int | list[int], conclusion: str) -> dict[str, Any]:
        """Tambahkan rule perkecualian ke binary tree, verifikasi hasilnya, dan selesaikan konsultasi."""
        if not self.pending:
            raise ValueError("Belum ada konsultasi aktif yang dapat dievaluasi.")
        conclusion = conclusion.strip()
        if not conclusion:
            raise ValueError("Masukkan kesimpulan rekomendasi yang diberikan oleh pakar.")

        indices = [candidate_indices] if isinstance(candidate_indices, int) else list(candidate_indices)
        if not indices:
            raise ValueError("Pilih minimal satu kondisi pembeda.")
        for idx in indices:
            if idx < 0 or idx >= len(self.candidates):
                raise ValueError("Pilihan kondisi pembeda tidak valid.")

        combined_condition = combine_conditions([self.candidates[idx]["condition"] for idx in indices])
        inference = self.pending.inference
        parent = find_node(self.kb["root"], inference["frontier_node_id"])
        if parent is None:
            raise ValueError("Node tujuan tidak ditemukan pada pohon rule.")
        side = inference["frontier_side"]
        if parent.get(side) is not None:
            raise ValueError("Cabang tujuan sudah terisi. Jalankan konsultasi ulang sebelum menambah rule.")

        active_node = inference["result_node"]
        key_case = active_node.get("key_case")
        # Invarian RDR: kondisi harus benar pada kasus baru dan salah pada kasus kunci kesimpulan terakhir.
        if not evaluate_condition(combined_condition, self.pending.case):
            raise ValueError("Kondisi rule baru harus dipenuhi oleh kasus baru.")
        if key_case and evaluate_condition(combined_condition, key_case):
            raise ValueError("Kondisi rule baru tidak boleh dipenuhi oleh kasus kunci dari kesimpulan terakhir.")

        new_node = {
            "id": get_next_node_id(self.kb["root"]),
            "condition": combined_condition,
            "conclusion": conclusion,
            "key_case": deepcopy(self.pending.case),
            "true_child": None,
            "false_child": None,
        }
        parent[side] = new_node

        updated_inference = infer_case(self.kb["root"], self.pending.case)
        self.last_trace = deepcopy(updated_inference["trace"])
        self.last_result_node_id = updated_inference["result_node_id"]
        customer_name = self.pending.customer_name
        self.reset_consultation()
        return {
            "node": new_node,
            "parent_id": parent["id"],
            "side": side,
            "active_node_id": active_node["id"],
            "overridden_conclusion": active_node.get("conclusion", ""),
            "customer_name": customer_name,
            "updated_inference": updated_inference,
        }
