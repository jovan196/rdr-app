"""Antarmuka baris perintah (CLI) untuk RDR Studio.

Seluruh logika ditangani rdr_core.RDREngine; modul ini hanya membaca input
dan menampilkan output. Jalankan dengan:

    python cli.py [berkas_knowledge_base.json]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from rdr_core import (
    APP_TITLE,
    APP_VERSION,
    CATEGORICAL_OPERATORS,
    NUMERIC_OPERATORS,
    OPERATOR_SYMBOLS,
    RDREngine,
    condition_text,
    iter_nodes,
    parse_attribute,
)

OP_INPUT_MAP = {
    "=": "eq",
    "==": "eq",
    "eq": "eq",
    "!=": "ne",
    "≠": "ne",
    "ne": "ne",
    ">": "gt",
    "gt": "gt",
    ">=": "ge",
    "≥": "ge",
    "ge": "ge",
    "<": "lt",
    "lt": "lt",
    "<=": "le",
    "≤": "le",
    "le": "le",
}


def input_case(engine: RDREngine) -> dict[str, str]:
    raw: dict[str, str] = {}
    for attr in engine.kb["attributes"]:
        hint = f" ({', '.join(attr['choices'])})" if attr.get("choices") else ""
        unit = " [numerik]" if attr["type"] == "numeric" else " [kategorikal]"
        raw[attr["name"]] = input(f"  {attr['name']}{unit}{hint}: ").strip()
    return raw


def show_inference(inference: dict):
    print(f"\nKesimpulan sistem (terakhir diperoleh dari rule {inference['result_node_id']}):")
    print(f"  {inference['conclusion']}")
    print("\nJejak penelusuran pohon biner:")
    for step in inference["trace"]:
        mark = "✓" if step["matched"] else "✗"
        prev_id = step.get("previous_node_id")
        if step["activated"]:
            note = f"kesimpulan {step['node_id']} aktif (menganulir {prev_id})" if prev_id else f"kesimpulan {step['node_id']} aktif"
        else:
            note = f"kesimpulan {step.get('active_node_id') or prev_id} tetap berlaku"
        print(f"  {mark} {step['node_id']}: {step['condition']} → {step['branch']} ({note})")


def cmd_info(engine: RDREngine):
    kb = engine.kb
    rule_count = sum(1 for _ in iter_nodes(kb["root"]))
    print(f"\nDomain             : {kb.get('domain', '-')}")
    print(f"Kesimpulan default : {kb['root'].get('conclusion', '-')}")
    print(f"Jumlah atribut     : {len(kb['attributes'])}")
    for attr in kb["attributes"]:
        detail = ", ".join(attr.get("choices", [])) or ("angka bebas" if attr["type"] == "numeric" else "teks bebas")
        print(f"  - {attr['name']} ({attr['type']}): {detail}")
    print(f"Jumlah rule        : {rule_count}")


def cmd_accept(engine: RDREngine):
    try:
        info = engine.accept_result()
    except ValueError as exc:
        print(exc)
        return
    consumer = f" untuk {info['customer_name']}" if info["customer_name"] else ""
    print(f"\n✓ Pakar setuju. Rekomendasi diberikan{consumer}:")
    print(f"  {info['conclusion']}")
    if info["stored_key_case"]:
        print(f"  (Kasus ini disimpan sebagai kasus kunci untuk {info['node_id']}.)")
    print("Proses konsultasi selesai.")


def cmd_update(engine: RDREngine):
    try:
        status, _ = engine.prepare_exception()
    except ValueError as exc:
        print(exc)
        return
    active_node = engine.pending.inference["result_node"]  # type: ignore[union-attr]
    if status == "no_candidates":
        print(f"Tidak ditemukan kondisi pembeda: seluruh nilai kasus baru sama dengan kasus kunci {active_node['id']}.")
        return

    key_case = active_node.get("key_case")
    if key_case:
        print(f"\nKasus kunci {active_node['id']} yang akan dianulir: {json.dumps(key_case, ensure_ascii=False)}")
    else:
        print(f"\nKasus kunci {active_node['id']}: (kosong — belum ada kasus yang disetujui pada {active_node['id']})")

    while True:
        print("\nKondisi pembeda (dipenuhi kasus baru & tidak dipenuhi kasus kunci):")
        for i, candidate in enumerate(engine.candidates, 1):
            print(f"  {i}. {candidate['label']}")
        raw_sel = input("Pilih nomor kondisi (pisahkan koma untuk DAN, mis. 1,2; atau ketik 'k' untuk kondisi kustom): ").strip()
        if raw_sel.lower() == "k":
            attr_name = input("  Nama atribut: ").strip()
            attr = next((a for a in engine.kb["attributes"] if a["name"] == attr_name), None)
            if not attr:
                print("  Atribut tidak ditemukan.")
                continue
            ops = NUMERIC_OPERATORS if attr["type"] == "numeric" else CATEGORICAL_OPERATORS
            ops_hint = ", ".join(OPERATOR_SYMBOLS[o] for o in ops)
            raw_op = input(f"  Operator ({ops_hint}): ").strip()
            op_code = OP_INPUT_MAP.get(raw_op.lower(), OP_INPUT_MAP.get(raw_op, ""))
            raw_val = input("  Nilai pembanding: ").strip()
            try:
                cand = engine.add_custom_candidate(attr_name, op_code, raw_val)
                print(f"  + Kondisi ditambahkan: {cand['label']}")
            except ValueError as exc:
                print(f"  Gagal menambah kondisi kustom: {exc}")
            continue
        try:
            indices = [int(part.strip()) - 1 for part in raw_sel.split(",") if part.strip()]
            if not indices:
                raise ValueError
        except ValueError:
            print("Pilihan tidak valid.")
            return
        break

    conclusion = input("Kesimpulan rekomendasi dari pakar: ").strip()
    try:
        info = engine.save_exception(indices, conclusion)
    except ValueError as exc:
        print(f"Gagal menyimpan rule: {exc}")
        return
    side = "KANAN / TRUE (true-child)" if info["side"] == "true_child" else "KIRI / FALSE (false-child)"
    node = info["node"]
    consumer = f" untuk {info['customer_name']}" if info["customer_name"] else ""
    print(f"\n✓ Rule perkecualian {node['id']} ditambahkan pada cabang {side} dari {info['parent_id']}.")
    print(f"  Kondisi   : {condition_text(node['condition'])}")
    print(f"  Rekomendasi{consumer}: {conclusion}")
    print("Proses konsultasi selesai.")


def cmd_consult(engine: RDREngine):
    if not engine.kb["attributes"]:
        print("Knowledge base belum memiliki atribut. Tambahkan atribut terlebih dahulu (menu 4).")
        return
    name = input("Nama konsumen (opsional): ").strip()
    raw = input_case(engine)
    try:
        inference = engine.run_consultation(raw, name)
    except ValueError as exc:
        print(f"Data kasus belum valid:\n{exc}")
        return
    show_inference(inference)
    decision = input("\nApakah pakar setuju dengan kesimpulan tersebut? [y = Setuju / n = Tidak sesuai (buat rule) / Enter = tunda]: ").strip().lower()
    if decision in {"y", "ya", "s", "setuju"}:
        cmd_accept(engine)
    elif decision in {"n", "tidak", "t"}:
        cmd_update(engine)


def cmd_configure_kb(engine: RDREngine):
    print("\nPengaturan Knowledge Base:")
    print("  1. Ubah domain & kesimpulan default (R0)")
    print("  2. Buat KB baru dari awal (1 rule default: t → kesimpulan default)")
    print("  3. Muat ulang contoh domain laptop")
    sub = input("Pilih [1/2/3]: ").strip()
    if sub == "1":
        domain = input(f"Domain [{engine.kb.get('domain', '')}]: ").strip() or engine.kb.get("domain", "")
        conclusion = input("Kesimpulan default R0: ").strip()
        if not conclusion:
            conclusion = engine.kb["root"].get("conclusion", "")
        try:
            engine.apply_settings(domain, conclusion)
            print("Domain dan kesimpulan default berhasil diperbarui.")
        except ValueError as exc:
            print(f"Validasi gagal: {exc}")
    elif sub == "2":
        domain = input("Nama domain masalah baru: ").strip() or "Domain baru"
        conclusion = input("Kesimpulan default (t → kesimpulan default): ").strip() or "Kesimpulan default belum diisi."
        engine.new_kb(domain=domain, default_conclusion=conclusion)
        print("Knowledge base baru dibuat dengan 1 rule awal (R0: t → kesimpulan default).")
    elif sub == "3":
        engine.load_sample_kb()
        print("Contoh domain laptop dimuat.")


def cmd_manage_attributes(engine: RDREngine):
    print("\nKelola Atribut Kasus:")
    for idx, attr in enumerate(engine.kb["attributes"], 1):
        choices = f" [{', '.join(attr['choices'])}]" if attr.get("choices") else ""
        print(f"  {idx}. {attr['name']} ({attr['type']}){choices}")
    print("\n  a. Tambah atribut baru")
    print("  d. Hapus atribut")
    sub = input("Pilih [a/d/Enter untuk batal]: ").strip().lower()
    if sub == "a":
        name = input("  Nama atribut (tanpa spasi): ").strip()
        kind = input("  Jenis data (numeric / categorical): ").strip().lower()
        choices = ""
        if kind == "categorical":
            choices = input("  Pilihan kategori (opsional, pisahkan koma): ").strip()
        try:
            attr = parse_attribute(name, kind, choices)
            engine.add_attribute(attr)
            print(f"  Atribut '{attr['name']}' ditambahkan.")
        except ValueError as exc:
            print(f"  Gagal: {exc}")
    elif sub == "d":
        try:
            idx = int(input("  Nomor atribut yang dihapus: ").strip()) - 1
            if idx < 0 or idx >= len(engine.kb["attributes"]):
                raise ValueError("Nomor atribut di luar jangkauan.")
            removed_name = engine.kb["attributes"][idx]["name"]
            engine.delete_attribute(idx)
            print(f"  Atribut '{removed_name}' dihapus.")
        except ValueError as exc:
            print(f"  Gagal: {exc}")


def cmd_tree(engine: RDREngine):
    def walk(node: dict, depth: int, side: str):
        key = json.dumps(node["key_case"], ensure_ascii=False) if node.get("key_case") else "kosong"
        print(f"{'  ' * depth}[{side}] {node['id']} | Jika: {condition_text(node['condition'])}")
        print(f"{'  ' * depth}    → Kesimpulan : {node.get('conclusion', '')}")
        print(f"{'  ' * depth}      Kasus kunci: {key}")
        if node.get("true_child"):
            walk(node["true_child"], depth + 1, "KANAN / TRUE")
        if node.get("false_child"):
            walk(node["false_child"], depth + 1, "KIRI / FALSE")

    print()
    walk(engine.kb["root"], 0, "ROOT")


def cmd_open(engine: RDREngine, current_path: Path | None) -> Path | None:
    raw = input("Nama file .json yang dibuka: ").strip()
    if not raw:
        return current_path
    try:
        engine.load(raw)
        print(f"Knowledge base dibuka: {raw}")
        return Path(raw)
    except (OSError, json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
        print(f"Gagal membuka '{raw}': {exc}")
        return current_path


def cmd_save(engine: RDREngine, current_path: Path | None) -> Path | None:
    if current_path is None:
        raw = input("Simpan sebagai (nama file .json): ").strip()
        if not raw:
            print("Dibatalkan.")
            return None
        current_path = Path(raw)
    try:
        engine.save(current_path)
    except OSError as exc:
        print(f"Gagal menyimpan: {exc}")
        return current_path
    print(f"Tersimpan: {current_path}")
    return current_path


MENU = """
Perintah:
  1. Info knowledge base
  2. Konsultasi konsumen
  3. Setujui hasil konsultasi aktif (jika ditunda)
  4. Buat rule perkecualian / tidak sesuai (jika ditunda)
  5. Tampilkan pohon biner RDR
  6. Pengaturan domain & kesimpulan default / KB baru
  7. Kelola atribut (numerik & kategorikal)
  8. Buka knowledge base (.json)
  9. Simpan knowledge base (.json)
  0. Keluar
"""


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    print(f"{APP_TITLE} (CLI) — versi {APP_VERSION}")
    engine = RDREngine()
    current_path: Path | None = None
    if len(argv) > 1:
        try:
            engine.load(argv[1])
            current_path = Path(argv[1])
            print(f"Knowledge base dibuka: {current_path}")
        except (OSError, json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
            print(f"Gagal membuka '{argv[1]}': {exc}")
            print("Memakai knowledge base contoh.")
    actions = {
        "1": lambda: cmd_info(engine),
        "2": lambda: cmd_consult(engine),
        "3": lambda: cmd_accept(engine),
        "4": lambda: cmd_update(engine),
        "5": lambda: cmd_tree(engine),
        "6": lambda: cmd_configure_kb(engine),
        "7": lambda: cmd_manage_attributes(engine),
    }
    while True:
        print(MENU)
        choice = input("Pilih perintah: ").strip()
        if choice == "0":
            return 0
        if choice == "8":
            current_path = cmd_open(engine, current_path)
            continue
        if choice == "9":
            current_path = cmd_save(engine, current_path)
            continue
        action = actions.get(choice)
        if action is None:
            print("Perintah tidak dikenal.")
            continue
        action()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
