"""Unit tests for the RDR inference, binary tree maintenance, and exception engine."""
import tempfile
import unittest
from pathlib import Path

from rdr_core import (
    RDREngine,
    build_candidates,
    condition_text,
    evaluate_condition,
    infer_case,
    load_kb,
    make_sample_kb,
    parse_attribute,
    save_kb,
    validate_case,
)


class RDRCoreTests(unittest.TestCase):
    def setUp(self):
        self.kb = make_sample_kb()
        self.attrs = self.kb["attributes"]

    def test_root_default_is_returned(self):
        case = {"anggaran_juta": 10, "penggunaan": "Kuliah", "mobilitas": "Tinggi", "ram_minimum_gb": 8, "preferensi_os": "Bebas"}
        result = infer_case(self.kb["root"], case)
        self.assertEqual(result["result_node_id"], "R0")
        self.assertEqual(result["conclusion"], self.kb["root"]["conclusion"])
        self.assertEqual(result["frontier_side"], "true_child")

    def test_true_child_overrides_parent_conclusion(self):
        root = self.kb["root"]
        root["key_case"] = {"anggaran_juta": 8}
        root["true_child"] = {
            "id": "R1", "condition": {"attribute": "anggaran_juta", "operator": "ge", "value": 15},
            "conclusion": "Laptop performa", "key_case": {"anggaran_juta": 20},
            "true_child": None, "false_child": None,
        }
        result = infer_case(root, {"anggaran_juta": 20})
        self.assertEqual(result["result_node_id"], "R1")
        self.assertEqual(result["conclusion"], "Laptop performa")
        self.assertEqual(result["trace"][-1]["previous_node_id"], "R0")

    def test_key_case_keeps_previous_conclusion_when_exception_condition_is_false(self):
        root = self.kb["root"]
        root["key_case"] = {"anggaran_juta": 8}
        root["true_child"] = {
            "id": "R1", "condition": {"attribute": "anggaran_juta", "operator": "ge", "value": 15},
            "conclusion": "Laptop performa", "key_case": {"anggaran_juta": 20},
            "true_child": None, "false_child": None,
        }
        result = infer_case(root, {"anggaran_juta": 8})
        self.assertEqual(result["result_node_id"], "R0")
        self.assertEqual(result["conclusion"], root["conclusion"])
        self.assertEqual(result["trace"][-1]["branch"], "KIRI / FALSE")

    def test_false_child_is_traversed_without_overriding_previous_conclusion(self):
        root = self.kb["root"]
        root["false_child"] = {
            "id": "R1", "condition": {"attribute": "anggaran_juta", "operator": "le", "value": 5},
            "conclusion": "Laptop hemat", "key_case": {"anggaran_juta": 3},
            "true_child": None, "false_child": None,
        }
        root["true_child"] = {
            "id": "R2", "condition": {"attribute": "penggunaan", "operator": "eq", "value": "Gaming"},
            "conclusion": "Laptop gaming", "key_case": {"penggunaan": "Gaming"},
            "true_child": None,
            "false_child": {
                "id": "R3", "condition": {"attribute": "anggaran_juta", "operator": "ge", "value": 5},
                "conclusion": "Laptop hemat", "key_case": {"anggaran_juta": 3},
                "true_child": None, "false_child": None,
            },
        }
        result = infer_case(root, {"anggaran_juta": 4, "penggunaan": "Kantor"})
        self.assertEqual(result["result_node_id"], "R0")
        self.assertEqual([x["node_id"] for x in result["trace"]], ["R0", "R2", "R3"])
        self.assertEqual(result["frontier_side"], "false_child")

    def test_numeric_candidate_separates_new_and_key_case(self):
        case = {"anggaran_juta": 20, "penggunaan": "Gaming"}
        key = {"anggaran_juta": 10, "penggunaan": "Kuliah"}
        candidates = build_candidates(self.attrs, case, key)
        numeric = next(c for c in candidates if c["condition"]["attribute"] == "anggaran_juta")
        self.assertTrue(evaluate_condition(numeric["condition"], case))
        self.assertFalse(evaluate_condition(numeric["condition"], key))
        self.assertEqual(numeric["condition"]["value"], 15)

    def test_categorical_candidate_separates_new_and_key_case(self):
        case = {"anggaran_juta": 10, "penggunaan": "Gaming"}
        key = {"anggaran_juta": 10, "penggunaan": "Kuliah"}
        candidates = build_candidates(self.attrs, case, key)
        cat = next(c for c in candidates if c["condition"]["attribute"] == "penggunaan")
        self.assertTrue(evaluate_condition(cat["condition"], case))
        self.assertFalse(evaluate_condition(cat["condition"], key))

    def test_no_candidate_when_all_values_equal(self):
        case = {"anggaran_juta": 10, "penggunaan": "Kuliah", "mobilitas": "Tinggi", "ram_minimum_gb": 8, "preferensi_os": "Bebas"}
        self.assertEqual(build_candidates(self.attrs, case, dict(case)), [])

    def test_first_case_can_create_exception_directly_from_default_root(self):
        engine = RDREngine()
        raw = {
            "anggaran_juta": "25",
            "penggunaan": "Gaming",
            "mobilitas": "Rendah",
            "ram_minimum_gb": "16",
            "preferensi_os": "Windows",
        }
        inf = engine.run_consultation(raw, "Budi")
        self.assertEqual(inf["result_node_id"], "R0")
        status, candidates = engine.prepare_exception()
        self.assertEqual(status, "ok")
        self.assertTrue(len(candidates) > 0)
        gaming_idx = next(
            i for i, c in enumerate(candidates)
            if c["condition"] == {"attribute": "penggunaan", "operator": "eq", "value": "Gaming"}
        )
        saved = engine.save_exception(gaming_idx, "Laptop Gaming RTX")
        self.assertEqual(saved["parent_id"], "R0")
        self.assertEqual(saved["side"], "true_child")
        self.assertIsNone(engine.pending)

        # Kasus lain yang tidak memenuhi R1 tetap mendapat kesimpulan default R0.
        other = engine.run_consultation({
            "anggaran_juta": "9",
            "penggunaan": "Kuliah",
            "mobilitas": "Tinggi",
            "ram_minimum_gb": "8",
            "preferensi_os": "Windows",
        })
        self.assertEqual(other["result_node_id"], "R0")

    def test_full_scrdr_lifecycle_preserves_all_cornerstone_cases(self):
        engine = RDREngine()
        engine.new_kb("Rekomendasi Paket Internet", "Paket Reguler 30 Mbps")
        engine.add_attribute(parse_attribute("jumlah_perangkat", "numeric"))
        engine.add_attribute(parse_attribute("aktivitas_utama", "categorical", "Browsing, Streaming, Gaming, Kerja"))

        # Kasus 0: disetujui pakar -> menjadi kasus kunci R0
        c0 = {"jumlah_perangkat": "3", "aktivitas_utama": "Browsing"}
        engine.run_consultation(c0, "Konsumen 0")
        acc = engine.accept_result()
        self.assertEqual(acc["node_id"], "R0")
        self.assertTrue(acc["stored_key_case"])
        self.assertIsNone(engine.pending)

        # Kasus 1: ditolak -> R1 pada R0.true_child (anak kanan)
        c1 = {"jumlah_perangkat": "6", "aktivitas_utama": "Gaming"}
        engine.run_consultation(c1, "Konsumen 1")
        status, cands = engine.prepare_exception()
        self.assertEqual(status, "ok")
        idx_gaming = next(i for i, c in enumerate(cands) if c["condition"] == {"attribute": "aktivitas_utama", "operator": "eq", "value": "Gaming"})
        info1 = engine.save_exception(idx_gaming, "Paket Gamer Low-Latency 100 Mbps")
        self.assertEqual((info1["parent_id"], info1["side"]), ("R0", "true_child"))

        # Kasus 2: R1 salah -> telusur ke kiri (false_child), aktif tetap R0 -> ditolak -> R2 pada R1.false_child
        c2 = {"jumlah_perangkat": "12", "aktivitas_utama": "Kerja"}
        inf2 = engine.run_consultation(c2, "Konsumen 2")
        self.assertEqual(inf2["result_node_id"], "R0")
        self.assertEqual((inf2["frontier_node_id"], inf2["frontier_side"]), ("R1", "false_child"))
        status, cands2 = engine.prepare_exception()
        self.assertEqual(status, "ok")
        idx_dev = next(i for i, c in enumerate(cands2) if c["condition"]["attribute"] == "jumlah_perangkat")
        info2 = engine.save_exception(idx_dev, "Paket Keluarga / SOHO 150 Mbps")
        self.assertEqual((info2["parent_id"], info2["side"]), ("R1", "false_child"))

        # Kasus 3: R1 benar -> telusur ke kanan (true_child), aktif R1 -> ditolak -> R3 menganulir R1 pada R1.true_child
        c3 = {"jumlah_perangkat": "15", "aktivitas_utama": "Gaming"}
        inf3 = engine.run_consultation(c3, "Konsumen 3")
        self.assertEqual(inf3["result_node_id"], "R1")
        self.assertEqual((inf3["frontier_node_id"], inf3["frontier_side"]), ("R1", "true_child"))
        status, cands3 = engine.prepare_exception()
        self.assertEqual(status, "ok")
        idx_pro = next(i for i, c in enumerate(cands3) if c["condition"]["attribute"] == "jumlah_perangkat")
        info3 = engine.save_exception(idx_pro, "Paket Pro eSports 300 Mbps")
        self.assertEqual((info3["parent_id"], info3["side"]), ("R1", "true_child"))

        # Verifikasi seluruh kasus sebelumnya tetap menghasilkan kesimpulan yang benar!
        self.assertEqual(engine.run_consultation(c0)["conclusion"], "Paket Reguler 30 Mbps")
        self.assertEqual(engine.run_consultation(c1)["conclusion"], "Paket Gamer Low-Latency 100 Mbps")
        self.assertEqual(engine.run_consultation(c2)["conclusion"], "Paket Keluarga / SOHO 150 Mbps")
        self.assertEqual(engine.run_consultation(c3)["conclusion"], "Paket Pro eSports 300 Mbps")

    def test_conjunctive_conditions_and_custom_threshold_and_json_roundtrip(self):
        engine = RDREngine()
        engine.run_consultation({
            "anggaran_juta": "8", "penggunaan": "Kuliah", "mobilitas": "Tinggi",
            "ram_minimum_gb": "8", "preferensi_os": "Windows",
        })
        engine.accept_result()

        engine.run_consultation({
            "anggaran_juta": "25", "penggunaan": "Desain", "mobilitas": "Sedang",
            "ram_minimum_gb": "32", "preferensi_os": "macOS",
        })
        engine.prepare_exception()

        # Ambang kustom yang juga dipenuhi kasus kunci (8 >= 5) harus ditolak.
        with self.assertRaises(ValueError):
            engine.add_custom_candidate("anggaran_juta", "ge", "5")
        # Ambang kustom yang tidak dipenuhi kasus baru (25 >= 30) harus ditolak.
        with self.assertRaises(ValueError):
            engine.add_custom_candidate("anggaran_juta", "ge", "30")

        # Ambang kustom valid (25 >= 20, sedangkan kasus kunci 8 < 20).
        custom = engine.add_custom_candidate("anggaran_juta", "ge", "20")
        custom_idx = engine.candidates.index(custom)
        os_idx = next(
            i for i, c in enumerate(engine.candidates)
            if c["condition"] == {"attribute": "preferensi_os", "operator": "eq", "value": "macOS"}
        )
        saved = engine.save_exception([os_idx, custom_idx], "MacBook Pro 14 M-Pro")
        self.assertEqual(saved["node"]["condition"]["operator"], "and")
        self.assertIn("DAN", condition_text(saved["node"]["condition"]))

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "kb_test.json"
            save_kb(engine.kb, path)
            reloaded = load_kb(path)
            res = infer_case(reloaded["root"], {
                "anggaran_juta": 22, "penggunaan": "Desain", "mobilitas": "Sedang",
                "ram_minimum_gb": 16, "preferensi_os": "macOS",
            })
            self.assertEqual(res["conclusion"], "MacBook Pro 14 M-Pro")

    def test_numeric_eq_handles_float_vs_int(self):
        cond = {"attribute": "anggaran_juta", "operator": "eq", "value": 10}
        self.assertTrue(evaluate_condition(cond, {"anggaran_juta": 10.0}))
        self.assertFalse(evaluate_condition({"attribute": "anggaran_juta", "operator": "ne", "value": 10}, {"anggaran_juta": 10.0}))

    def test_categorical_choices_validation_and_normalization(self):
        case, errors = validate_case(self.attrs, {
            "anggaran_juta": "12,5",
            "penggunaan": "gaming",
            "mobilitas": "tinggi",
            "ram_minimum_gb": "16",
            "preferensi_os": "linux",
        })
        self.assertEqual(errors, [])
        self.assertEqual(case["anggaran_juta"], 12.5)
        self.assertEqual(case["penggunaan"], "Gaming")
        self.assertEqual(case["preferensi_os"], "Linux")

        _, bad_errors = validate_case(self.attrs, {
            "anggaran_juta": "12",
            "penggunaan": "Memasak",
            "mobilitas": "Tinggi",
            "ram_minimum_gb": "8",
            "preferensi_os": "Windows",
        })
        self.assertEqual(len(bad_errors), 1)

    def test_newly_added_attribute_can_separate_previously_identical_key_case(self):
        engine = RDREngine()
        base_raw = {
            "anggaran_juta": "10", "penggunaan": "Kantor", "mobilitas": "Tinggi",
            "ram_minimum_gb": "8", "preferensi_os": "Windows",
        }
        engine.run_consultation(base_raw)
        engine.accept_result()

        # Tambahkan atribut baru untuk membedakan kebutuhan layar sentuh
        engine.add_attribute(parse_attribute("layar_sentuh", "categorical", "Ya, Tidak"))
        new_raw = dict(base_raw, layar_sentuh="Ya")
        engine.run_consultation(new_raw)
        status, cands = engine.prepare_exception()
        self.assertEqual(status, "ok")
        self.assertTrue(any(c["condition"]["attribute"] == "layar_sentuh" for c in cands))


if __name__ == "__main__":
    unittest.main(verbosity=2)
