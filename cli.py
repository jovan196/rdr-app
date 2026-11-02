"""Antarmuka baris perintah (CLI) untuk RDR Studio.

Seluruh logika ditangani rdr_core.RDREngine; modul ini hanya membaca input
dan menampilkan output. Jalankan dengan:

    python cli.py [berkas_knowledge_base.json]
"""
from __future__ import annotations

import sys
from pathlib import Path

from rdr_core import APP_TITLE, APP_VERSION, RDREngine, condition_text, iter_nodes


def input_case(engine: RDREngine) -> dict[str, str]:
    raw: dict[str, str] = {}
    for attr in engine.kb["attributes"]:
        hint = f" ({', '.join(attr['choices'])})" if attr.get("choices") else ""
        unit = " [numerik]" if attr["type"] == "numeric" else ""
        raw[attr["name"]] = input(f"  {attr['name']}{unit}{hint}: ").strip()
    return raw


def show_inference(inference: dict):
    print(f"\nKesimpulan (dari rule {inference['result_node_id']}):")
    print(f"  {inference['conclusion']}")
    print("\nJejak penelusuran:")
    for step in inference["trace"]:
        mark = "✓" if step["matched"] else "✗"
        print(f"  {mark} {step['node_id']}: {step['condition']} → {step['branch']}")


def cmd_info(engine: RDREngine):
    kb = engine.kb
    rule_count = sum(1 for _ in iter_nodes(kb["root"]))
    print(f"\nDomain        : {kb.get('domain', '-')}")
    print(f"Jumlah atribut: {len(kb['attributes'])}")
    for attr in kb["attributes"]:
        detail = ", ".join(attr.get("choices", [])) or ("angka bebas" if attr["type"] == "numeric" else "teks bebas")
        print(f"  - {attr['name']} ({attr['type']}): {detail}")
    print(f"Jumlah rule   : {rule_count}")


def cmd_consult(engine: RDREngine):
    if not engine.kb["attributes"]:
        print("Knowledge base belum memiliki atribut.")
        return
    name = input("Nama konsumen (opsional): ").strip()
    raw = input_case(engine)
    try:
        inference = engine.run_consultation(raw, name)
    except ValueError as exc:
        print(f"Data kasus belum valid:\n{exc}")
        return
    show_inference(inference)


def cmd_accept(engine: RDREngine):
    try:
        info = engine.accept_result()
    except ValueError as exc:
        print(exc)
        return
    if info["stored_key_case"]:
        print(f"Disetujui. Kasus disimpan sebagai kasus kunci untuk {info['node_id']}.")
    else:
        print(f"Disetujui. Kasus kunci {info['node_id']} yang sudah ada tetap dipakai.")


def cmd_update(engine: RDREngine):
    try:
        status, candidates = engine.prepare_exception()
    except ValueError as exc:
        print(exc)
        return
    if status == "no_key_case":
        node_id = engine.pending.inference["result_node_id"]
        print(f"Rule {node_id} belum memiliki kasus kunci. Setujui satu kasus terlebih dahulu (menu 3).")
        return
    if status == "no_candidates":
        print("Tidak ditemukan kondisi pembeda: nilai kasus baru sama dengan kasus kunci.")
        return
    print("\nKondisi pembeda (benar untuk kasus baru, salah untuk kasus kunci):")
    for i, candidate in enumerate(candidates, 1):
        print(f"  {i}. {candidate['label']}")
    try:
        selected = int(input("Pilih nomor kondisi: ").strip()) - 1
    except ValueError:
        print("Pilihan tidak valid.")
        return
    conclusion = input("Kesimpulan dari pakar: ").strip()
    try:
        info = engine.save_exception(selected, conclusion)
    except ValueError as exc:
        print(f"Gagal menyimpan rule: {exc}")
        return
    side = "KANAN / TRUE" if info["side"] == "true_child" else "KIRI / FALSE"
    node = info["node"]
    print(f"Rule {node['id']} ditambahkan pada cabang {side} dari {info['parent_id']}.")
    print(f"Kondisi: {condition_text(node['condition'])}")


def cmd_tree(engine: RDREngine):
    def walk(node: dict, depth: int, side: str):
        key = "ada" if node.get("key_case") else "—"
        print(f"{'  ' * depth}[{side}] {node['id']} | {condition_text(node['condition'])} | kasus kunci: {key}")
        print(f"{'  ' * depth}    → {node.get('conclusion', '')}")
        if node.get("true_child"):
            walk(node["true_child"], depth + 1, "TRUE")
        if node.get("false_child"):
            walk(node["false_child"], depth + 1, "FALSE")

    walk(engine.kb["root"], 0, "ROOT")


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
  2. Konsultasi
  3. Sesuai (setujui hasil konsultasi terakhir)
  4. UPDATE KNOWLEDGE (buat rule pengecualian)
  5. Tampilkan pohon rule
  6. Simpan knowledge base
  0. Keluar
"""


def main(argv: list[str]) -> int:
    print(f"{APP_TITLE} (CLI) — versi {APP_VERSION}")
    engine = RDREngine()
    current_path: Path | None = None
    if len(argv) > 1:
        try:
            engine.load(argv[1])
            current_path = Path(argv[1])
            print(f"Knowledge base dibuka: {current_path}")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(f"Gagal membuka '{argv[1]}': {exc}")
            print("Memakai knowledge base contoh.")
    actions = {
        "1": lambda: cmd_info(engine),
        "2": lambda: cmd_consult(engine),
        "3": lambda: cmd_accept(engine),
        "4": lambda: cmd_update(engine),
        "5": lambda: cmd_tree(engine),
        "6": lambda: None,
    }
    while True:
        print(MENU)
        choice = input("Pilih perintah: ").strip()
        if choice == "0":
            return 0
        if choice == "6":
            current_path = cmd_save(engine, current_path)
            continue
        action = actions.get(choice)
        if action is None:
            print("Perintah tidak dikenal.")
            continue
        action()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
