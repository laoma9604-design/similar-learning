"""一次性生成 group_dev_0004（线性驱动-阻力）与 group_dev_0005（饱和响应）两个机制 dev 组。

用 a_data/runtime.py 实跑验算所有数值（baseline 输出、见证点误差、正例映射一致性），
全部通过才落盘。格式逐字段对照 multiplicative_growth/group_dev_0001。
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "a_data"))
import runtime  # noqa: E402

SCHEMA = "topoadv-schema-0.3.0-draft"
VOCAB = "topoadv-vocab-0.1.0-draft"


def mk_obj(object_id, label, nodes, edge_id, edge_type, input_nodes, output_nodes,
           roles, function, ctrl, outs, baseline, scales, bout, outscale, legal, bounds):
    return {
        "object_id": object_id,
        "object_kind": "mechanistic",
        "relation_type": edge_type,
        "split": "dev",
        "label": label,
        "nodes": [{"node_id": nid, "label": lbl, "type": "positive_scalar"} for nid, lbl in nodes],
        "edges": [{
            "edge_id": edge_id,
            "edge_type": edge_type,
            "input_nodes": input_nodes,
            "output_nodes": output_nodes,
            "roles": {nid: roles[nid] for nid in input_nodes + output_nodes},
        }],
        "function": function,
        "controllable_inputs": ctrl,
        "designated_outputs": outs,
        "baseline": baseline,
        "input_scales": scales,
        "baseline_output": bout,
        "output_scale": outscale,
        "legal_domain": legal,
        "intervention_bounds": bounds,
        "provenance": {"dataset": "mred", "original_id": None, "structure_source": "provided"},
    }


# ============ 线性驱动-阻力 group_dev_0004 ============
lin_roles = {"V": "driver", "R": "resistance", "I": "response"}
lin_wroles = {"dP": "driver", "Rf": "resistance", "Q": "response"}
POS = [1e-6, None]

circuit = mk_obj(
    "obj_circuit", "电路",
    [("V", "电压"), ("R", "电阻"), ("I", "电流")],
    "e_s", "linear_drive_resistance", ["V", "R"], ["I"], lin_roles,
    "V / R", ["V", "R"], ["I"], [10, 2], [10, 2], 5, 5,
    {"V": [1e-6, None], "R": [1e-6, None]}, {"V": [-0.2, 0.2], "R": [-0.2, 0.2]},
)
water_flow = mk_obj(
    "obj_water_flow", "水流",
    [("dP", "压差"), ("Rf", "流阻"), ("Q", "流量")],
    "e_t", "linear_drive_resistance", ["dP", "Rf"], ["Q"], lin_wroles,
    "dP / Rf", ["dP", "Rf"], ["Q"], [8, 4], [8, 4], 2, 2,
    {"dP": [1e-6, None], "Rf": [1e-6, None]}, {"dP": [-0.2, 0.2], "Rf": [-0.2, 0.2]},
)
inv_square = mk_obj(
    "obj_synthetic_inverse_square", "合成反比平方反例",
    [("V", "驱动量"), ("R", "阻力量"), ("I", "响应量")],
    "e_sq", "linear_drive_resistance", ["V", "R"], ["I"], lin_roles,
    "V * 2.0 / (R ** 2.0)", ["V", "R"], ["I"], [10, 2], [10, 2], 5, 5,
    {"V": [1e-6, None], "R": [1e-6, None]}, {"V": [-0.2, 0.2], "R": [-0.2, 0.2]},
)
LIN_NODE_MAP = {"V": "dP", "R": "Rf", "I": "Q"}
LIN_EDGE_MAP = {"e_s": "e_t"}
LIN_ROLES = {
    "driver": {"source": "V", "target": "dP"},
    "resistance": {"source": "R", "target": "Rf"},
    "response": {"source": "I", "target": "Q"},
}
LIN_WITNESS_U = {"dP": 0.0, "Rf": -0.2}  # 目标域节点名

# ============ 饱和响应 group_dev_0005 ============
enz_roles = {"S": "input", "v": "response"}
ads_roles = {"C": "input", "q": "response"}

enzyme = mk_obj(
    "obj_enzyme", "酶反应",
    [("S", "底物浓度"), ("v", "反应速率")],
    "e_s", "saturation_response", ["S"], ["v"], enz_roles,
    "10.0 * S / (1.0 + S)", ["S"], ["v"], [1], [1], 5, 5,
    {"S": [1e-6, None]}, {"S": [-0.8, 1.0]},
)
adsorption = mk_obj(
    "obj_adsorption", "吸附",
    [("C", "平衡浓度"), ("q", "吸附量")],
    "e_t", "saturation_response", ["C"], ["q"], ads_roles,
    "20.0 * C / (2.0 + C)", ["C"], ["q"], [2], [2], 10, 10,
    {"C": [1e-6, None]}, {"C": [-0.8, 1.0]},
)
hill2 = mk_obj(
    "obj_synthetic_hill2", "合成正协同反例",
    [("S", "输入量"), ("v", "响应量")],
    "e_sq", "saturation_response", ["S"], ["v"], enz_roles,
    "10.0 * S ** 2 / (1.0 + S ** 2)", ["S"], ["v"], [1], [1], 5, 5,
    {"S": [1e-6, None]}, {"S": [-0.8, 1.0]},
)
SAT_NODE_MAP = {"S": "C", "v": "q"}
SAT_EDGE_MAP = {"e_s": "e_t"}
SAT_ROLES = {
    "input": {"source": "S", "target": "C"},
    "response": {"source": "v", "target": "q"},
}
SAT_WITNESS_U = {"C": 1.0}  # 目标域节点名


# ============ 验算 ============
def check_baseline(obj):
    inputs = dict(zip(obj["controllable_inputs"], obj["baseline"]))
    out_id = obj["designated_outputs"][0]
    val = runtime.evaluate_object(obj, inputs)[out_id]
    assert math.isclose(val, obj["baseline_output"], abs_tol=1e-9), \
        f"{obj['object_id']}: baseline {val} != {obj['baseline_output']}"
    return val


def compute_witness(target, source, node_map, u_target):
    """u_target 用目标域节点名；source 经 node_map 反查映射。返回见证点全部数字。"""
    inv = {v: k for k, v in node_map.items()}
    u_source = {inv[tn]: u for tn, u in u_target.items()}
    r_t = runtime.normalized_response(target, u_target)
    r_s = runtime.normalized_response(source, u_source)
    tout = target["designated_outputs"][0]
    sout = source["designated_outputs"][0]
    t_out = runtime.evaluate_object(target, runtime.intervene(target, u_target))[tout]
    s_out = runtime.evaluate_object(source, runtime.intervene(source, u_source))[sout]
    err = min(1.0, (r_s[sout] - r_t[tout]) ** 2)
    return {
        "u": u_target,
        "target_output": {tout: round(t_out, 4)},
        "source_output": {sout: round(s_out, 4)},
        "r_target": {tout: round(r_t[tout], 4)},
        "r_source": {sout: round(r_s[sout], 4)},
        "error": round(err, 4),
    }


def scan_positive(target, source, node_map, grid):
    """正例：目标/源在若干干预点下归一化响应必须一致（可视为结构+响应都对齐）。"""
    inv = {v: k for k, v in node_map.items()}
    tout = target["designated_outputs"][0]
    sout = source["designated_outputs"][0]
    maxdiff = 0.0
    for u_target in grid:
        u_source = {inv[tn]: u for tn, u in u_target.items()}
        r_t = runtime.normalized_response(target, u_target)[tout]
        r_s = runtime.normalized_response(source, u_source)[sout]
        maxdiff = max(maxdiff, abs(r_t - r_s))
    return maxdiff


print("== baseline 验算 ==")
for o in (circuit, water_flow, inv_square, enzyme, adsorption, hill2):
    print(f"  {o['object_id']}: {o['function']} -> {check_baseline(o)}")

print("\n== 线性反例见证点 ==")
lin_w = compute_witness(water_flow, inv_square, LIN_NODE_MAP, LIN_WITNESS_U)
print("  ", json.dumps(lin_w, ensure_ascii=False))
assert lin_w["error"] > 0.05, "线性反例误差不足 0.05"

print("\n== 饱和反例见证点 ==")
sat_w = compute_witness(adsorption, hill2, SAT_NODE_MAP, SAT_WITNESS_U)
print("  ", json.dumps(sat_w, ensure_ascii=False))
assert sat_w["error"] > 0.05, "饱和反例误差不足 0.05"

print("\n== 正例映射一致性（归一化响应应完全重合）==")
lin_grid = [
    {"dP": 0.1, "Rf": 0.0}, {"dP": 0.0, "Rf": 0.1},
    {"dP": -0.2, "Rf": 0.2}, {"dP": 0.2, "Rf": -0.2},
]
sat_grid = [{"C": -0.5}, {"C": 0.3}, {"C": 0.8}, {"C": -0.8}]
d_lin = scan_positive(water_flow, circuit, LIN_NODE_MAP, lin_grid)
d_sat = scan_positive(adsorption, enzyme, SAT_NODE_MAP, sat_grid)
print(f"  线性正例最大归一化差 = {d_lin:.2e} (应≈0)")
print(f"  饱和正例最大归一化差 = {d_sat:.2e} (应≈0)")
assert d_lin < 1e-9 and d_sat < 1e-9

print("\n全部验算通过。")


# ============ 落盘 ============
def dump(path, obj):
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_group(concept, group_id, rel_type, target, source, ce,
                node_map, edge_map, roles_map, witness_u, witness, ce_file,
                src_file, tgt_file, src_label, tgt_label, formula_md, readme_head):
    base = f"cases/{concept}/{group_id}"
    # manifest
    dump(f"{base}/manifest.json", {
        "group_id": group_id, "dataset": "mred", "relation_type": rel_type,
        "schema_version": SCHEMA, "vocab_version": VOCAB, "split": "dev",
        "object_ids": [target["object_id"], source["object_id"], ce["object_id"]],
        "task_ids": [f"task_{group_id[6:]}a", f"task_{group_id[6:]}b"],
    })
    dump(f"{base}/manifest.sealed.json", {
        "group_id": group_id,
        "valid_sources": [source["object_id"]],
        "excluded_sources": [ce["object_id"]],
    })
    (ROOT / base / "README.md").write_text(readme_head, encoding="utf-8")
    # relation
    dump(f"{base}/relation/analogy.json", {
        "source": {"object_id": source["object_id"], "label": src_label},
        "target": {"object_id": target["object_id"], "label": tgt_label},
        "relation_type": rel_type, "direction": "source → target",
    })
    dump(f"{base}/relation/node_map.json", node_map)
    dump(f"{base}/relation/edge_map.json", edge_map)
    dump(f"{base}/relation/roles.json", roles_map)
    (ROOT / base / "relation/formula.md").write_text(formula_md, encoding="utf-8")
    # counterexamples
    dump(f"{base}/counterexamples/{ce['object_id']}/counterexample.json", {
        "source_id": ce["object_id"], "target_id": target["object_id"],
        "node_map": node_map, "reason": "结构通过但响应误差超参考容差",
    })
    dump(f"{base}/counterexamples/{ce['object_id']}/witness.json", witness)
    dump(f"{base}/counterexamples/expected.json", {
        "expectation": "reject", "reason": "no_candidate_passed_response_threshold",
    })
    # objects
    dump(f"{base}/data/input/objects/{src_file}", source)
    dump(f"{base}/data/input/objects/{tgt_file}", target)
    dump(f"{base}/data/input/objects/{ce_file}", ce)
    dump(f"{base}/data/input/objects/index.json", {
        "objects": [
            {"object_id": target["object_id"], "file": tgt_file},
            {"object_id": source["object_id"], "file": src_file},
            {"object_id": ce["object_id"], "file": ce_file},
        ],
    })
    # tasks
    tid_a = f"task_{group_id[6:]}a"
    tid_b = f"task_{group_id[6:]}b"
    ctrl_target = target["controllable_inputs"]
    outs_target = target["designated_outputs"]
    bounds_target = target["intervention_bounds"]
    dump(f"{base}/data/input/tasks/positive.json", {
        "task_id": tid_a, "group_id": group_id, "target_id": target["object_id"],
        "source_ids": [source["object_id"], ce["object_id"]],
        "schema_version": SCHEMA, "vocab_version": VOCAB,
        "intervenable_inputs": ctrl_target, "specified_outputs": outs_target,
        "intervention_range": bounds_target,
        "_note": "方法输入不含标签、正确源域或见证点；task_id 不编码正负；正式库每任务 10 个源域，本例精简为 2 个",
    })
    dump(f"{base}/data/input/tasks/negative.json", {
        "task_id": tid_b, "group_id": group_id, "target_id": target["object_id"],
        "source_ids": [ce["object_id"]],
        "schema_version": SCHEMA, "vocab_version": VOCAB,
        "intervenable_inputs": ctrl_target, "specified_outputs": outs_target,
        "intervention_range": bounds_target,
        "_note": "负任务：候选库只含反例源，无有效映射",
    })
    # sealed reference
    err = witness["error"]
    rt = witness["r_target"]
    rs = witness["r_source"]
    u_str = ",".join(f"{k}={v}" for k, v in witness_u.items())
    reason = (f"结构通过但响应误差超参考容差：u=({u_str}) 时源响应 "
              f"{list(rs.values())[0]:.4f} vs 目标 {list(rt.values())[0]:.4f}，误差 {err:.4f} > 0.05")
    dump(f"{base}/sealed/reference.json", {
        tid_a: {
            "task_id": tid_a, "label": "positive",
            "valid": [{
                "source_id": source["object_id"],
                "node_map": node_map,
                "edge_map": edge_map,
            }],
            "exclusions": [],
            "reference_tolerance": {"min_ctc": 0.95, "max_error": 0.05},
            "status": "bijective_confirmed",
        },
        tid_b: {
            "task_id": tid_b, "label": "negative",
            "valid": [],
            "exclusions": [{
                "source_id": ce["object_id"],
                "reason": reason,
                "witness": witness,
            }],
            "reference_tolerance": {"min_ctc": 0.95, "max_error": 0.05},
            "status": "bijective_confirmed",
        },
    })


write_group(
    "linear_drive_resistance", "group_dev_0004", "linear_drive_resistance",
    water_flow, circuit, inv_square,
    LIN_NODE_MAP, LIN_EDGE_MAP, LIN_ROLES, LIN_WITNESS_U, lin_w,
    "inverse_square.json", "circuit.json", "water_flow.json",
    "电路", "水流",
    "源域（电路）：I = V / R\n目标域（水流）：Q = dP / Rf\n\n角色：driver(驱动量) / resistance(阻力量) / response(响应量)\n",
    "group_dev_0004 —— 电路 → 水流（线性驱动-阻力，机制类）\n\n正例源=电路，反例源=合成反比平方反例。映射方向 source→target。\n",
)
write_group(
    "saturation_response", "group_dev_0005", "saturation_response",
    adsorption, enzyme, hill2,
    SAT_NODE_MAP, SAT_EDGE_MAP, SAT_ROLES, SAT_WITNESS_U, sat_w,
    "hill2.json", "enzyme.json", "adsorption.json",
    "酶反应", "吸附",
    "源域（酶反应）：v = R_max * S / (K + S)，R_max=10, K=1\n目标域（吸附）：q = R_max * C / (K + C)，R_max=20, K=2\n\n角色：input(输入量) / response(响应量)；R_max、K 为内联常量，非节点。\n",
    "group_dev_0005 —— 酶反应 → 吸附（饱和响应，机制类）\n\n正例源=酶反应，反例源=合成正协同反例(Hill n=2)。映射方向 source→target。\n",
)

print("\n已写入：")
print("  cases/linear_drive_resistance/group_dev_0004/")
print("  cases/saturation_response/group_dev_0005/")
