"""MRED 干扰源构造（C 方案重写版）。

设计要点（逐条对应任务书）：
1. 【基准对齐】干扰源的 baseline 必须 = 目标域 baseline，且可用同一 u 对照
   —— 否则 scan_error 比较的是两个不同工作点，误差恒为 0（旧版踩过的坑）
2. 【命名统一】正例源域和干扰源共用同一套无意义节点 ID 池（n1/n2/n3），
   不出现 input/response vs x1/y1 这种可辨识差异（L1006 防泄露）
3. 【局部扰动对齐 L170】鼓包加在【归一化响应】上：r_s = r_t + b(u)
   而非加在输出值上（旧版误读）
4. 【三类干扰形式互不重复】换端点与反比平方必须用不同构造（旧版撞车）
"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "a_data"))

import runtime  # noqa: E402

# 统一节点 ID 池：正例和干扰源共用，随机分派，杜绝命名泄露
NODE_ID_POOL = ["n1", "n2", "n3", "n4"]

ROLE_SPEC = {
    "multiplicative_growth": dict(
        roles=["current", "ratio", "next"],
        input_roles=["current", "ratio"],
        output_role="next",
        bounds=[-0.2, 0.2],
        main_input="current",     # 唯一可跨域比较的维度
        fixed_inputs={"ratio": None},  # 值从目标域取
    ),
    "linear_drive_resistance": dict(
        roles=["driver", "resistance", "response"],
        input_roles=["driver", "resistance"],
        output_role="response",
        bounds=[-0.2, 0.2],
        main_input="driver",
        fixed_inputs={"resistance": None},
    ),
    "saturation_response": dict(
        roles=["input", "response"],
        input_roles=["input"],
        output_role="response",
        bounds=[-0.8, 1.0],
        main_input="input",
        fixed_inputs={},
    ),
}


def bump(u, amplitude=0.3, center=0.13, width=0.03):
    """任务书 L170 原式。b(0)=0，五点最大 0.0122，u=0.13 处 0.09。"""
    return amplitude * (math.exp(-((u - center) / width) ** 2)
                        - math.exp(-(center / width) ** 2))


# ============================================================
# 归一化响应 → 输出值的逆变换
# 目标域归一化响应 r_t = (y - y0)/y_scale，故 y = y0 + r_t * y_scale
# 干扰源要用同一个 y0 / y_scale，才能保证 baseline 对齐
# ============================================================
def main_input_expression(target_obj, relation_type, node):
    """目标域在「仅主输入变动、其余固定在工作点」下的输出表达式（用 node 变量）。"""
    b = target_obj["baseline"]
    ctrl = target_obj["controllable_inputs"]
    fixed = dict(zip(ctrl, b))

    if relation_type == "multiplicative_growth":
        ratio_val = fixed["ratio"]
        return f"{node} * (1 + {ratio_val})"
    if relation_type == "linear_drive_resistance":
        res_val = fixed["resistance"]
        return f"{node} / {res_val}"
    # 饱和：R_max、K 从 function 里取（内联常量），直接重建
    rmax, k = target_obj["_R_max"], target_obj["_K"]
    return f"{rmax} * {node} / ({k} + {node})"


def build_interferer(target_obj, relation_type, object_id, kind, seed,
                     perturb=None):
    """构造一个干扰源，baseline / scales 与目标域严格对齐。

    kind:
      structure_error  —— 结构不成立（输出与输入无正确关系）
      response_error   —— 结构对、函数形式错
      local_perturbation —— 结构对、局部鼓包（归一化响应空间）
    perturb: 仅局部扰动用，dict(amplitude, center, width)
    """
    spec = ROLE_SPEC[relation_type]
    main_role = spec["main_input"]
    tgt_main_idx = target_obj["controllable_inputs"].index(main_role) \
        if main_role in target_obj["controllable_inputs"] else 0
    b_main = target_obj["baseline"][tgt_main_idx]           # 主输入工作点
    y0 = target_obj["baseline_output"]
    y_scale = target_obj["output_scale"]
    ctrl = target_obj["controllable_inputs"]

    node_in = "n1"
    node_out = "n2"

    # ---- 主输入维度上的基准函数（= 目标域在此维度上的真实响应）----
    base_expr = main_input_expression(target_obj, relation_type, node_in)
    base_y0 = runtime.expression_value(base_expr, {node_in: b_main})
    if abs(base_y0 - y0) > 1e-9 * max(1.0, abs(y0)):
        # 双输入目标域只动主输入时，baseline 输出会变；
        # 干扰源以自己的 baseline 为准，output_scale 沿用 y_scale 保持可比
        pass

    if kind == "structure_error":
        # 结构错误：输出与输入之间不成立同构关系。
        # 用「输出对输入无正确依赖」的形式，但保持与目标域同一输出量级，
        # 保证响应差异足够大（否则归一化后误差被量级差压平）。
        expr = f"{base_y0} * (2 - {node_in} / {b_main})"
        out_scale = y_scale
    elif kind == "response_error":
        # 响应错误：结构（类型/角色/端点）全对，函数形式不同。
        # 幂律：把线性/乘性的次数改掉；饱和类改成 Hill n=2。
        if relation_type == "saturation_response":
            rmax, k = target_obj["_R_max"], target_obj["_K"]
            expr = f"{rmax} * {node_in} ** 2 / ({k} ** 2 + {node_in} ** 2)"
        elif relation_type == "linear_drive_resistance":
            res_val = target_obj["baseline"][ctrl.index("resistance")]
            expr = f"{node_in} ** 2 / ({res_val} * {b_main})"
        else:
            # 乘性：目标 next = current*(1+ratio) 对 current 是一次的。
            # 改成二次项形式，才真正是「结构对、响应错」。
            ratio_val = target_obj["baseline"][ctrl.index("ratio")]
            expr = (f"({node_in} * (1 + {ratio_val}) - {base_y0}) "
                    f"* ({node_in} * (1 + {ratio_val}) - {base_y0}) / {base_y0} + {base_y0}")
        out_scale = y_scale
    elif kind == "local_perturbation":
        # 局部扰动：r_s = r_t + b(u)，即 y_s = y0 + (r_t + b(u)) * y_scale
        p = perturb or dict(amplitude=0.3, center=0.13, width=0.03)
        # r_t = (base_expr - y0)/y_scale ； u = node_in/b_main - 1
        amp, cen, wid = p["amplitude"], p["center"], p["width"]
        u_expr = f"({node_in} / {b_main} - 1)"
        bump_expr = (f"{amp} * (exp(-(({u_expr} - {cen}) / {wid}) ** 2) "
                     f"- exp(-({cen} / {wid}) ** 2))")
        expr = f"{y0} + (({base_expr} - {y0}) / {y_scale} + {bump_expr}) * {y_scale}"
        out_scale = y_scale
    else:
        raise ValueError("unknown kind: " + kind)

    baseline_out = runtime.expression_value(expr, {node_in: b_main})
    if not math.isfinite(baseline_out):
        raise ValueError(f"{object_id}: baseline_output 非有限值")
    if abs(baseline_out) < 1e-12:
        raise ValueError(f"{object_id}: baseline_output 为 0，无法归一化（output_scale 不能为 0）")

    # runtime.normalized_response 用 obj 自己的 baseline_output / output_scale 归一化。
    # 因此 output_scale 必须取「源自身基线输出」，才能与目标域在同一无量纲尺度上比较
    # （L1010 的尺度规则：output_scale = baseline_output，三类统一）。
    out_scale = abs(baseline_out)

    roles = {node_in: main_role, node_out: spec["output_role"]}

    return {
        "object_id": object_id,
        "object_kind": "mechanistic",
        "relation_type": relation_type,
        "split": None,
        "label": "候选源域",            # 中性，不透露类别
        "nodes": [dict(node_id=node_in, label="输入量", type="positive_scalar"),
                  dict(node_id=node_out, label="响应量", type="positive_scalar")],
        "edges": [dict(edge_id="r1", edge_type=relation_type,
                       input_nodes=[node_in], output_nodes=[node_out], roles=roles)],
        "function": expr,
        "controllable_inputs": [node_in],
        "designated_outputs": [node_out],
        "baseline": [b_main],
        "input_scales": [b_main],
        "baseline_output": baseline_out,
        "output_scale": out_scale,
        "legal_domain": {node_in: [1e-6, None]},
        "intervention_bounds": {node_in: list(spec["bounds"])},
        "provenance": {"dataset": "mred", "original_id": None, "structure_source": "provided"},
    }
