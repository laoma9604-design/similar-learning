"""MRED 正式库生成器 —— 对象构造与三类干扰源构造。

只负责「造对象」，不落盘。所有数值都经 runtime.py 实跑验算，验不过直接抛异常。

关键约定（与 data/MRED域对规格.md、T01-schema.json 一致）：
1. baseline / input_scales 是「按 controllable_inputs 顺序」的列表 —— 最容易错的地方
2. 函数字符串用节点 ID；饱和类 R_max、K 是内联常量，不是节点
3. 饱和类 input0 必须 = K（半饱和点约束），两域相对 K 位置相同
4. 三类干扰：结构错误（换角色/换端点）、结构同响应错（改函数）、局部扰动（局部大偏差）
"""
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "a_data"))

import runtime  # noqa: E402

# ============================================================
# 每类关系的角色与输入约定
# ============================================================
ROLE_SPEC = {
    "multiplicative_growth": dict(
        roles=["current", "ratio", "next"],
        input_roles=["current", "ratio"],
        output_role="next",
        bounds=[-0.2, 0.2],
    ),
    "linear_drive_resistance": dict(
        roles=["driver", "resistance", "response"],
        input_roles=["driver", "resistance"],
        output_role="response",
        bounds=[-0.2, 0.2],
    ),
    "saturation_response": dict(
        roles=["input", "response"],
        input_roles=["input"],
        output_role="response",
        bounds=[-0.8, 1.0],   # 放宽：饱和反例只在进入饱和区才暴露
    ),
}

NODE_ID_POOL = ["a1", "a2", "a3", "a4", "a5", "b1", "b2", "b3", "b4", "b5"]


# ============================================================
# 函数构造与求值
# ============================================================
def build_function(relation_type, role_to_node, constants=None):
    r = role_to_node
    if relation_type == "multiplicative_growth":
        return f"{r['current']} * (1 + {r['ratio']})"
    if relation_type == "linear_drive_resistance":
        return f"{r['driver']} / {r['resistance']}"
    if relation_type == "saturation_response":
        return f"{constants['R_max']} * {r['input']} / ({constants['K']} + {r['input']})"
    raise ValueError("unknown relation_type: " + relation_type)


def _eval(function, values):
    return runtime.expression_value(function, values)


# ============================================================
# 真实域对象构造
# ============================================================
def make_object(object_id, relation_type, spec_domain, seed=None):
    """spec_domain: mred_domains 里的源/目标域描述（含 baseline 与展示名）。

    seed=None -> 节点 ID 用角色名（模板/可读）；seed 给定 -> 随机 ID（打乱顺序）。
    """
    s = ROLE_SPEC[relation_type]
    roles = s["roles"]

    if seed is None:
        role_to_node = {role: role for role in roles}
    else:
        rng = random.Random(seed)
        picked = rng.sample(NODE_ID_POOL, len(roles))
        role_to_node = {role: picked[i] for i, role in enumerate(roles)}

    baseline_by_role = dict(spec_domain["baseline"])
    constants = {k: spec_domain[k] for k in ("R_max", "K") if k in spec_domain}
    function = build_function(relation_type, role_to_node, constants)

    input_nodes = [role_to_node[r] for r in s["input_roles"]]
    output_nodes = [role_to_node[s["output_role"]]]
    baseline_list = [baseline_by_role[r] for r in s["input_roles"]]

    values = {role_to_node[r]: baseline_by_role[r] for r in s["input_roles"]}
    baseline_output = _eval(function, values)
    if not math.isfinite(baseline_output):
        raise ValueError(f"{object_id}: baseline_output 非有限值")

    legal_domain, intervention_bounds = {}, {}
    for r in s["input_roles"]:
        nid = role_to_node[r]
        if relation_type == "multiplicative_growth":
            legal_domain[nid] = [0, None] if r == "current" else [0, 1]
        else:
            legal_domain[nid] = [1e-6, None]
        intervention_bounds[nid] = list(s["bounds"])

    nodes = [dict(node_id=role_to_node[r], label=spec_domain["names"][r], type="positive_scalar")
             for r in roles]

    obj = {
        "object_id": object_id,
        "object_kind": "mechanistic",
        "relation_type": relation_type,
        "split": None,
        "label": spec_domain["object_label"],
        "nodes": nodes,
        "edges": [dict(
            edge_id="r1",
            edge_type=relation_type,
            input_nodes=input_nodes,
            output_nodes=output_nodes,
            roles={role_to_node[r]: r for r in roles},
        )],
        "function": function,
        "controllable_inputs": input_nodes,
        "designated_outputs": output_nodes,
        "baseline": baseline_list,
        "input_scales": list(baseline_list),  # 尺度规则：input_scales = baseline 本身
        "baseline_output": baseline_output,
        "output_scale": baseline_output,      # 尺度规则：output_scale = baseline_output
        "legal_domain": legal_domain,
        "intervention_bounds": intervention_bounds,
        "provenance": {"dataset": "mred", "original_id": None, "structure_source": "provided"},
    }
    # 饱和类的内联常量记录下来，供干扰源构造重建函数用（不落盘，落盘前会剔除）
    if relation_type == "saturation_response":
        obj["_R_max"] = spec_domain["R_max"]
        obj["_K"] = spec_domain["K"]
    return obj, role_to_node


# ============================================================
# 正例验证：两域归一化响应必须处处相等（L1010 解析正例响应等价依据）
# ============================================================
def positive_max_deviation(src_obj, tgt_obj, node_map, src_roles, tgt_roles):
    """node_map: 源节点ID -> 目标节点ID。反向用它把目标干预翻回源域。"""
    tgt_to_src = {v: k for k, v in node_map.items()}
    tgt_inputs = tgt_obj["controllable_inputs"]
    max_dev = 0.0
    worst = None

    def dev_at(u_t):
        u_s = {tgt_to_src[n]: u for n, u in u_t.items()}
        rt = runtime.normalized_response(tgt_obj, u_t)[tgt_obj["designated_outputs"][0]]
        rs = runtime.normalized_response(src_obj, u_s)[src_obj["designated_outputs"][0]]
        return abs(rs - rt), rs, rt

    if len(tgt_inputs) == 2:
        lo = tgt_obj["intervention_bounds"][tgt_inputs[0]][0]
        hi = tgt_obj["intervention_bounds"][tgt_inputs[0]][1]
        grid = [lo, lo / 2, 0.0, hi / 2, hi]
        for u1 in grid:
            for u2 in grid:
                u_t = {tgt_inputs[0]: u1, tgt_inputs[1]: u2}
                d, rs, rt = dev_at(u_t)
                if d > max_dev:
                    max_dev, worst = d, (u_t, rs, rt)
    else:
        lo = tgt_obj["intervention_bounds"][tgt_inputs[0]][0]
        hi = tgt_obj["intervention_bounds"][tgt_inputs[0]][1]
        grid = [lo, lo / 2, 0.0, 0.5, 0.75, hi]
        for u in grid:
            u_t = {tgt_inputs[0]: u}
            d, rs, rt = dev_at(u_t)
            if d > max_dev:
                max_dev, worst = d, (u_t, rs, rt)
    return max_dev, worst


# ============================================================
# 干扰源：统一用「单输入合成函数」表达，绕过双输入角色固定的复杂性
# ============================================================
def _pair_input_baseline(pair, relation_type):
    """取该域对源域工作点上「主输入」的 baseline（乘性取 current、线性取 driver、饱和取 input）。"""
    if relation_type == "multiplicative_growth":
        return pair["source"]["baseline"]["current"]
    if relation_type == "linear_drive_resistance":
        return pair["source"]["baseline"]["driver"]
    return pair["source"]["baseline"]["input"]


def _target_response_expr(pair, relation_type):
    """给出目标域归一化响应对 u 的解析式，用输入节点 x 和 baseline 表达。

    返回 (expr_of_x, baseline_in)，expr 已是「输出值」而非归一化值。
    """
    b = _pair_input_baseline(pair, relation_type)
    if relation_type == "multiplicative_growth":
        # next = current*(1+ratio)，仅扰动 current，ratio 固定
        ratio = pair["source"]["baseline"]["ratio"]
        return f"x1 * (1 + {ratio})", b
    if relation_type == "linear_drive_resistance":
        res = pair["source"]["baseline"]["resistance"]
        return f"x1 / {res}", b
    rmax, k = pair["source"]["R_max"], pair["source"]["K"]
    return f"{rmax} * x1 / ({k} + x1)", b


def make_structure_error(pair, relation_type, seed, kind="swap_roles"):
    """结构错误：角色或端点错配，结构层面就不成立。

    做法：源域把「主输入」与「输出」的对齐关系弄反 —— 即让源域的输出节点
    实际由另一个量决定（把响应算成了另一个变量），类型/角色标注照抄目标域，
    但实际函数与标注不符。这属于 tab:mred「交换角色 / 改变输入输出端」。
    """
    b = _pair_input_baseline(pair, relation_type)
    if kind == "swap_roles":
        # 交换：把输出算成「输入本身」（响应=输入，无关系结构）
        func = "x1"
        out_scale_val = b
    elif kind == "swap_endpoints":
        # 端点反接：把输入算成「响应被除回输入」，输出对输入的依赖方向反转
        func = f"({b} * {b}) / (x1 + 1e-9)"
        out_scale_val = _eval(func, {"x1": b})
    else:
        raise ValueError("unknown structure error kind: " + kind)

    bout = _eval(func, {"x1": b})
    return dict(
        object_id=f"obj_inf_struct_{kind}_{seed}",
        object_kind="mechanistic",
        relation_type=relation_type,
        split=None,
        label="结构差异源",
        nodes=[dict(node_id="x1", label="输入量", type="positive_scalar"),
               dict(node_id="y1", label="响应量", type="positive_scalar")],
        edges=[dict(edge_id="r1", edge_type=relation_type,
                    input_nodes=["x1"], output_nodes=["y1"],
                    roles={"x1": ROLE_SPEC[relation_type]["input_roles"][0],
                           "y1": ROLE_SPEC[relation_type]["output_role"]})],
        function=func,
        controllable_inputs=["x1"],
        designated_outputs=["y1"],
        baseline=[b],
        input_scales=[b],
        baseline_output=bout,
        output_scale=out_scale_val if out_scale_val != 0 else 1.0,
        legal_domain={"x1": [1e-6, None]},
        intervention_bounds={"x1": [-0.2, 0.2]},
        provenance={"dataset": "mred", "original_id": None, "structure_source": "provided"},
    ), "structure_error"


def make_response_error(pair, relation_type, seed, kind="power_law"):
    """结构同响应错：类型、角色、端点全对，只有函数形式不同。

    kind: power_law（幂律）/ hill2（协同）/ inverse_square（反比平方）
    """
    expr, b = _target_response_expr(pair, relation_type)
    if kind == "power_law":
        # 目标若线性，改成二次；若乘性/饱和，改成幂次放大
        func = f"(x1 * x1) / {b}"
    elif kind == "hill2":
        rmax = pair["source"].get("R_max") or b
        k = pair["source"].get("K") or b
        func = f"{rmax} * x1 ** 2 / ({k} ** 2 + x1 ** 2)"
    elif kind == "inverse_square":
        func = f"({b} * {b}) / (x1 + 1e-9)"
    else:
        raise ValueError("unknown response error kind: " + kind)

    bout = _eval(func, {"x1": b})
    if not math.isfinite(bout) or bout <= 0:
        raise ValueError(f"响应错误源 baseline_output 非法: {bout}")
    return dict(
        object_id=f"obj_inf_response_{kind}_{seed}",
        object_kind="mechanistic",
        relation_type=relation_type,
        split=None,
        label="响应差异源",
        nodes=[dict(node_id="x1", label="输入量", type="positive_scalar"),
               dict(node_id="y1", label="响应量", type="positive_scalar")],
        edges=[dict(edge_id="r1", edge_type=relation_type,
                    input_nodes=["x1"], output_nodes=["y1"],
                    roles={"x1": ROLE_SPEC[relation_type]["input_roles"][0],
                           "y1": ROLE_SPEC[relation_type]["output_role"]})],
        function=func,
        controllable_inputs=["x1"],
        designated_outputs=["y1"],
        baseline=[b],
        input_scales=[b],
        baseline_output=bout,
        output_scale=bout,
        legal_domain={"x1": [1e-6, None]},
        intervention_bounds={"x1": [-0.2, 0.2]},
        provenance={"dataset": "mred", "original_id": None, "structure_source": "provided"},
    ), "response_error"


def make_local_error(pair, relation_type, seed, amplitude=0.3, center=0.13, width=0.03):
    """局部扰动：结构、角色、端点全对，只在输入域子区间产生大偏差。

    源输出 = 目标输出 + b(u)*output_scale，b 取任务书 L170 双高斯。
    单输出误差 = b(u)^2；稀疏点最大 0.0122 < 0.05，u=0.09 附近超容差。
    """
    base_expr, b = _target_response_expr(pair, relation_type)
    scale = _eval(base_expr, {"x1": b})
    # u = x1/b - 1；把 b(u) 用 x1 表达
    func = (f"{base_expr} + {scale * amplitude} * "
            f"(exp(-(((x1 / {b} - 1) - {center}) / {width}) ** 2) "
            f"- exp(-({center} / {width}) ** 2))")
    bout = _eval(func, {"x1": b})
    return dict(
        object_id=f"obj_inf_local_{seed}",
        object_kind="mechanistic",
        relation_type=relation_type,
        split=None,
        label="局部差异源",
        nodes=[dict(node_id="x1", label="输入量", type="positive_scalar"),
               dict(node_id="y1", label="响应量", type="positive_scalar")],
        edges=[dict(edge_id="r1", edge_type=relation_type,
                    input_nodes=["x1"], output_nodes=["y1"],
                    roles={"x1": ROLE_SPEC[relation_type]["input_roles"][0],
                           "y1": ROLE_SPEC[relation_type]["output_role"]})],
        function=func,
        controllable_inputs=["x1"],
        designated_outputs=["y1"],
        baseline=[b],
        input_scales=[b],
        baseline_output=bout,
        output_scale=scale,
        legal_domain={"x1": [1e-6, None]},
        intervention_bounds={"x1": [-0.2, 0.2]},
        provenance={"dataset": "mred", "original_id": None, "structure_source": "provided"},
    ), "local_perturbation"


# ============================================================
# 干扰定性验证
# ============================================================
def scan_error(src_obj, tgt_obj, relation_type):
    """在单输入扫描点上算最大 min(1,(rs-rt)^2) 与见证点。"""
    b_t = tgt_obj["baseline"][0]
    b_s = src_obj["baseline"][0]
    best = (0.0, None)
    grid = [i / 100 for i in range(-20, 21)]  # u ∈ [-0.2, 0.2] 步长 0.01
    for u in grid:
        try:
            rt = runtime.normalized_response(tgt_obj, {tgt_obj["controllable_inputs"][0]: u})
            rs = runtime.normalized_response(src_obj, {src_obj["controllable_inputs"][0]: u})
        except ValueError:
            continue
        rtv = list(rt.values())[0]
        rsv = list(rs.values())[0]
        err = min(1.0, (rsv - rtv) ** 2)
        if err > best[0]:
            best = (err, (u, rsv, rtv))
    return best


def bump(u, amplitude=0.3, center=0.13, width=0.03):
    """任务书 L170 局部扰动原型（与 verify_cases.py 一致）。"""
    return amplitude * (math.exp(-((u - center) / width) ** 2) - math.exp(-(center / width) ** 2))
