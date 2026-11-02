"""Unit tests for the RDR inference and exception-candidate engine."""
import unittest

from rdr_core import build_candidates, evaluate_condition, infer_case, make_sample_kb

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
        # Root is always true, so the false child is not on the path for a normal sample KB.
        # Check false-child traversal on a non-root condition node.
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
