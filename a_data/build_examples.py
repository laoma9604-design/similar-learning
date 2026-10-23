"""Regenerate T01-examples.json from raw SCAR/SCAN + hand-coded mechanistic case.

Proves the unified format holds real SCAR/SCAN fields without loss, and keeps the
answer out of method input: raw evidence / faithful mappings / explanation live only
in ``adaptations`` (sealed review material), labels and witnesses only in
``reference`` / ``negative_reference_example``.

Stdlib only. Re-run any time to refresh the examples from data/raw/.
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAR_EN = ROOT / "data/raw/scar/release/system_analogy_en.json"
SCAN_CSV = ROOT / "data/raw/scan/data/SCAN_dataset.csv"
SCHEMA = "topoadv-schema-0.3.0-draft"
VOCAB = "topoadv-vocab-0.1.0-draft"


def load_scar():
    return [json.loads(line) for line in SCAR_EN.open(encoding="utf-8") if line.strip()]


def load_scan():
    return list(csv.DictReader(SCAN_CSV.open(encoding="utf-8")))


def mechanistic(bank_like):
    return bank_like


def main():
    scar = load_scar()
    scan = load_scan()

    # ---- mechanistic objects (taskbook sec:case-handoff; numbers match verify_cases.py) ----
    # functions use symbol names + bindings (aligned with a_data/runtime.py evaluate_object)
    bank = {
        "object_id": "obj_bank_compound_interest",
        "object_kind": "mechanistic",
        "label": "银行复利",
        "nodes": [
            {"node_id": "A_t", "label": "当前本金", "type": "positive_scalar"},
            {"node_id": "rate_t", "label": "本期利率", "type": "positive_scalar"},
            {"node_id": "A_next", "label": "下一期余额", "type": "positive_scalar"},
        ],
        "edges": [{
            "edge_id": "e_t", "edge_type": "multiplicative_growth",
            "input_nodes": ["A_t", "rate_t"], "output_nodes": ["A_next"],
            "roles": {"A_t": "current", "rate_t": "ratio", "A_next": "next"},
        }],
        "function": "A_t * (1 + rate_t)",
        "controllable_inputs": ["A_t", "rate_t"],
        "designated_outputs": ["A_next"],
        "baseline": [5000, 0.1],
        "input_scales": [5000, 0.1],
        "baseline_output": 5500,
        "output_scale": 5500,
        "legal_domain": {"A_t": [0, None], "rate_t": [0, 1]},
        "intervention_bounds": {"A_t": [-0.2, 0.2], "rate_t": [-0.2, 0.2]},
        "provenance": {"dataset": "mred", "original_id": None, "structure_source": "provided"},
    }
    bacteria = {
        "object_id": "obj_bacteria_growth",
        "object_kind": "mechanistic",
        "label": "细菌增长",
        "nodes": [
            {"node_id": "N_t", "label": "当前细菌数量", "type": "positive_scalar"},
            {"node_id": "rate_s", "label": "本步增长率", "type": "positive_scalar"},
            {"node_id": "N_next", "label": "下一步数量", "type": "positive_scalar"},
        ],
        "edges": [{
            "edge_id": "e_s", "edge_type": "multiplicative_growth",
            "input_nodes": ["N_t", "rate_s"], "output_nodes": ["N_next"],
            "roles": {"N_t": "current", "rate_s": "ratio", "N_next": "next"},
        }],
        "function": "N_t * (1 + rate_s)",
        "controllable_inputs": ["N_t", "rate_s"],
        "designated_outputs": ["N_next"],
        "baseline": [1000, 0.1],
        "input_scales": [1000, 0.1],
        "baseline_output": 1100,
        "output_scale": 1100,
        "legal_domain": {"N_t": [0, None], "rate_s": [0, 1]},
        "intervention_bounds": {"N_t": [-0.2, 0.2], "rate_s": [-0.2, 0.2]},
        "provenance": {"dataset": "mred", "original_id": None, "structure_source": "provided"},
    }
    square = {
        "object_id": "obj_synthetic_square",
        "object_kind": "mechanistic",
        "label": "合成平方反例",
        "nodes": [
            {"node_id": "N_t", "label": "当前量", "type": "positive_scalar"},
            {"node_id": "rate_s", "label": "变化比例", "type": "positive_scalar"},
            {"node_id": "N_next", "label": "下一步量", "type": "positive_scalar"},
        ],
        "edges": [{
            "edge_id": "e_sq", "edge_type": "multiplicative_growth",
            "input_nodes": ["N_t", "rate_s"], "output_nodes": ["N_next"],
            "roles": {"N_t": "current", "rate_s": "ratio", "N_next": "next"},
        }],
        "function": "N_t**2 / 1000 * (1 + rate_s)",
        "controllable_inputs": ["N_t", "rate_s"],
        "designated_outputs": ["N_next"],
        "baseline": [1000, 0.1],
        "input_scales": [1000, 0.1],
        "baseline_output": 1100,
        "output_scale": 1100,
        "legal_domain": {"N_t": [0, None], "rate_s": [0, 1]},
        "intervention_bounds": {"N_t": [-0.2, 0.2], "rate_s": [-0.2, 0.2]},
        "provenance": {"dataset": "mred", "original_id": None, "structure_source": "provided"},
    }

    # ---- structural objects (SCAR / SCAN) — no answer here, raw goes to adaptations ----
    atom = {
        "object_id": "obj_atom", "object_kind": "structural", "label": "原子结构",
        "nodes": [{"node_id": n, "label": l, "type": "concept"} for n, l in [
            ("nucleus", "原子核"), ("electron", "电子"), ("charge", "电荷"),
            ("attracts", "吸引"), ("revolves", "公转"), ("electromagnetism", "电磁力")]],
        "edges": [],
        "provenance": {"dataset": "scan", "original_id": "atom->solar system", "structure_source": "inferred"},
    }
    solar = {
        "object_id": "obj_solar_system", "object_kind": "structural", "label": "太阳系",
        "nodes": [{"node_id": n, "label": l, "type": "concept"} for n, l in [
            ("sun", "太阳"), ("planet", "行星"), ("mass", "质量"),
            ("attracts", "吸引"), ("revolves", "公转"), ("gravity", "引力")]],
        "edges": [],
        "provenance": {"dataset": "scan", "original_id": "atom->solar system", "structure_source": "inferred"},
    }
    cell = {
        "object_id": "obj_cell", "object_kind": "structural", "label": "细胞",
        "nodes": [{"node_id": n, "label": l, "type": "concept"} for n, l in [
            ("cell_membrane", "细胞膜"), ("nucleus", "细胞核"), ("cell_organelle", "细胞器"),
            ("metabolites", "代谢物"), ("molecular", "分子")]],
        "edges": [],
        "provenance": {"dataset": "scar", "original_id": 55, "structure_source": "inferred"},
    }
    factory = {
        "object_id": "obj_factory", "object_kind": "structural", "label": "工厂",
        "nodes": [{"node_id": n, "label": l, "type": "concept"} for n, l in [
            ("fence", "围墙"), ("headquarters", "总部"), ("machine", "机器"),
            ("raw_material", "原材料"), ("manufactures", "制成品")]],
        "edges": [],
        "provenance": {"dataset": "scar", "original_id": 55, "structure_source": "inferred"},
    }

    # ---- adaptations (sealed review material) ----
    cell_raw = next(x for x in scar if x["id"] == 55)
    atom_rows = [r for r in scan if r["target"] == "atom" and r["source"] == "solar system"]
    # SCAN target=atom / source=solar; our source→target is solar→atom, so flip the pairs.
    scan_faithful = [[r["src_word"], r["targ_word"]] for r in atom_rows]

    adaptations = [
        {
            "adaptation_id": "adapt_scar_0055",
            "dataset": "scar",
            "original_id": "55",
            "source_object_id": "obj_cell",
            "target_object_id": "obj_factory",
            "faithful_mappings": cell_raw["mappings"],
            "explanation": cell_raw["Explanation"],
            "background": {"source": cell_raw["system_a_background"],
                           "target": cell_raw["system_b_background"]},
            "raw": cell_raw,
            "structure_source": "inferred",
            "annotation_status": "to_review",
            "valid_mappings": [],
        },
        {
            "adaptation_id": "adapt_scan_atom_solar",
            "dataset": "scan",
            "original_id": "atom->solar system",
            "source_object_id": "obj_solar_system",
            "target_object_id": "obj_atom",
            "faithful_mappings": scan_faithful,
            "explanation": None,
            "background": None,
            "raw": atom_rows,
            "structure_source": "inferred",
            "annotation_status": "to_review",
            "valid_mappings": [],
        },
    ]

    # ---- task (method input, no label, neutral id) ----
    task = {
        "task_id": "task_dev_0001a",
        "group_id": "group_dev_0001",
        "target_id": "obj_bank_compound_interest",
        "source_ids": ["obj_bacteria_growth", "obj_synthetic_square"],
        "schema_version": SCHEMA,
        "vocab_version": VOCAB,
        "intervenable_inputs": ["A_t", "rate_t"],
        "specified_outputs": ["A_next"],
        "intervention_range": {"A_t": [-0.2, 0.2], "rate_t": [-0.2, 0.2]},
        "_note": "方法输入不含标签、正确源域或见证点；task_id 不编码正负；正式库每任务 10 个源域，本例精简为 2 个",
    }

    # ---- sealed reference (positive) + negative example ----
    reference = {
        "task_id": "task_dev_0001a",
        "label": "positive",
        "valid": [{
            "source_id": "obj_bacteria_growth",
            "node_map": {"N_t": "A_t", "rate_s": "rate_t", "N_next": "A_next"},
            "edge_map": {"e_s": "e_t"},
        }],
        "exclusions": [],
        "reference_tolerance": {"min_ctc": 0.95, "max_error": 0.05},
        "status": "bijective_confirmed",
    }
    negative = {
        "task_id": "task_dev_0001b",
        "label": "negative",
        "valid": [],
        "exclusions": [{
            "source_id": "obj_synthetic_square",
            "reason": "结构通过但响应误差超参考容差：u=(0.2,0) 时源响应 0.44 vs 目标 0.20，误差 0.0576 > 0.05",
            "witness": {
                "u": {"A_t": 0.2, "rate_t": 0.0},
                "target_output": {"A_next": 6600},
                "source_output": {"N_next": 1584},
                "r_target": {"A_next": 0.2},
                "r_source": {"N_next": 0.44},
                "error": 0.0576,
            },
        }],
        "reference_tolerance": {"min_ctc": 0.95, "max_error": 0.05},
        "status": "bijective_confirmed",
    }

    examples = {
        "examples_version": "topoadv-examples-0.3.0-draft",
        "status": "draft-v3，与 T01-schema.json(v0.3.0) / T01-vocabulary.json(v0.1.0) 同版",
        "note": "mechanistic 样例(银行复利/细菌增长/合成平方反例)取自任务书 sec:case-handoff，数值与 verify_cases.py 一致，function/baseline/scales 对齐 case-fixtures.json 写法；structural 样例来自真实 SCAR id=55、SCAN atom→solar system 组。答案隔离：原始映射/解释/背景只在 adaptations，标签/见证点只在 reference，object/task 均不含答案。",
        "objects": [bank, bacteria, square, atom, solar, cell, factory],
        "adaptations": adaptations,
        "task": task,
        "reference": reference,
        "negative_reference_example": negative,
    }

    out = ROOT / "T01-examples.json"
    out.write_text(json.dumps(examples, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
