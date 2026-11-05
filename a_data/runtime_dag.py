"""多关系 DAG 对象求值器（扩展层，不改动 runtime.py）。

设计原则：
1. **零侵入**：不修改 a_data/runtime.py。现有 3960 个单关系对象继续用原求值器。
2. **兼容单关系**：单超边对象走完全相同的语义，可与 runtime 逐位比对。
3. **按拓扑序执行**：每个对象的 edges 必须构成 DAG，按入度剥离求值。
4. **中间变量**：边产出节点若是后续边的输入，自动成为中间变量，不需额外字段。

对象约定（与 T01-schema 完全一致，不新增必填字段）：
    edges[i] = {edge_id, edge_type, input_nodes[], output_nodes[], roles{}, function}
        —— function 挂在**边**上（方案 C），这是多关系唯一必要的表达方式。
    function（顶层）：可选，若存在则必须是整图的数学等价单式展开，
        用于与旧代码/旧口径交叉核验。
    controllable_inputs / baseline / input_scales / legal_domain / intervention_bounds
        只覆盖**外部输入**；中间变量不进这些字段。

求值语义：
    按拓扑序逐边求值。每条边用 edge["function"] 计算，输入取自
    「外部输入值 + 已完成边的产出值」。最终输出 = designated_outputs[0]。
"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "a_data"))

import runtime  # noqa: E402  复用其 AST 求值与合法域检查


class DAGError(ValueError):
    """对象结构不构成合法可执行 DAG。"""


def edge_function(edge):
    """取一条边的函数表达式。支持两种写法：
    - edge["function"]（推荐，多关系必须）
    - 单超边对象回退到 obj["function"]（由调用方处理）
    """
    f = edge.get("function")
    if not f:
        raise DAGError(f"边 {edge.get('edge_id')} 缺少 function")
    return f


def topological_order(obj):
    """按入度剥离求拓扑序，返回 edge_id 列表。

    外部输入 = 出现在 input_nodes 但从未被任何边产出的节点。
    中间变量 = 既被某条边产出、又被另一条边消费。
    """
    edges = obj["edges"]
    if not edges:
        raise DAGError("对象没有超边")

    produced_by = {}          # node -> edge_id（最后产出它的边）
    for e in edges:
        for n in e["output_nodes"]:
            if n in produced_by:
                raise DAGError(f"节点 {n} 被多条边重复产出：{produced_by[n]} 与 {e['edge_id']}")
            produced_by[n] = e["edge_id"]

    by_id = {e["edge_id"]: e for e in edges}
    remaining = [e["edge_id"] for e in edges]
    # 初始就绪值只能是「外部输入」= 可控输入中**未被任何边产出**的那些。
    # 踩过两次：①直接放全部 controllable_inputs ④环 a<->b 中 a 既是可控输入
    # 又被 e2 产出，于是 e1 被误判就绪、环检测失效。必须减掉 produced_by。
    external = set(obj.get("controllable_inputs", [])) - set(produced_by)
    unknown = set()
    for e in edges:
        for n in e["input_nodes"]:
            if n not in produced_by and n not in external:
                unknown.add(n)
    if unknown:
        raise DAGError(f"存在既非外部输入、又无来源的悬空节点：{sorted(unknown)}")
    ready_vals = set(external)

    order = []
    while remaining:
        ready = [eid for eid in remaining
                 if all(n in ready_vals for n in by_id[eid]["input_nodes"])]
        if not ready:
            raise DAGError(f"存在环或悬空输入，无法拓扑排序：剩余 {remaining}")
        for eid in ready:
            order.append(eid)
            ready_vals.update(by_id[eid]["output_nodes"])
            remaining.remove(eid)
    return order


def dependency_depth(obj):
    """最大依赖深度 = 拓扑执行的轮数。

    直接用 topological_order 的分层结果，避免两份逻辑分叉。
    """
    edges = obj["edges"]
    if not edges:
        return 0
    produced_by = {}
    for e in edges:
        for n in e["output_nodes"]:
            produced_by[n] = e["edge_id"]
    by_id = {e["edge_id"]: e for e in edges}
    ready_vals = set(obj.get("controllable_inputs", [])) - set(produced_by)
    remaining = [e["edge_id"] for e in edges]
    depth = 0
    while remaining:
        ready = [eid for eid in remaining
                 if all(n in ready_vals for n in by_id[eid]["input_nodes"])]
        if not ready:
            raise DAGError("存在环或悬空输入，无法确定深度")
        for eid in ready:
            ready_vals.update(by_id[eid]["output_nodes"])
            remaining.remove(eid)
        depth += 1
    return depth


def shared_nodes(obj):
    """返回被多条边消费的节点 -> 消费它的边数（S3 的判定依据）。"""
    count = {}
    for e in obj["edges"]:
        for n in e["input_nodes"]:
            count[n] = count.get(n, 0) + 1
    return {n: c for n, c in count.items() if c > 1}


def intermediate_variables(obj):
    """既被某条边产出、又被另一条边消费的节点集合。"""
    produced, consumed = set(), set()
    for e in obj["edges"]:
        produced.update(e["output_nodes"])
        consumed.update(e["input_nodes"])
    return produced & consumed


def check_legal_inputs(obj, inputs):
    """只校验外部输入的合法域；中间变量由函数决定。"""
    if set(inputs) != set(obj["controllable_inputs"]):
        raise ValueError("输入 ID 必须与 controllable_inputs 完全一致，"
                         f"得到 {sorted(inputs)} vs {sorted(obj['controllable_inputs'])}")
    for nid, value in inputs.items():
        lo, hi = obj["legal_domain"][nid]
        lo = -math.inf if lo is None else lo
        hi = math.inf if hi is None else hi
        if not math.isfinite(value) or not lo - 1e-12 <= value <= hi + 1e-12:
            raise ValueError(f"输入超出合法域：{nid}={value} 不在 [{lo}, {hi}]")


def evaluate_dag(obj, inputs, trace=False):
    """按拓扑序求值整个 DAG。

    inputs: {外部输入节点ID: 值}
    trace: True 时同时返回逐边求值轨迹（供 C 侧核对/缓存记录）
    返回 {输出节点ID: 值}；trace=True 时返回 (values, trace_list)
    """
    check_legal_inputs(obj, inputs)
    values = dict(inputs)
    by_id = {e["edge_id"]: e for e in obj["edges"]}
    order = topological_order(obj)
    trace_rows = []

    for eid in order:
        e = by_id[eid]
        expr = edge_function(e)
        local = {n: values[n] for n in e["input_nodes"]}
        out = runtime.expression_value(expr, local)
        if not math.isfinite(out):
            raise ValueError(f"边 {eid} 输出非有限值")
        # 每条边当前只允许单输出（第一批约束）
        if len(e["output_nodes"]) != 1:
            raise DAGError(f"边 {eid} 有 {len(e['output_nodes'])} 个输出，第一批只支持单输出")
        values[e["output_nodes"][0]] = out
        if trace:
            trace_rows.append(dict(edge_id=eid, expr=expr,
                                   inputs={k: local[k] for k in e["input_nodes"]},
                                   output_node=e["output_nodes"][0], output=out))

    out_id = obj["designated_outputs"][0]
    if out_id not in values:
        raise DAGError(f"指定输出 {out_id} 未被任何边产出")
    result = {out_id: values[out_id]}
    return (result, trace_rows) if trace else result


def intervene(obj, u_by_node):
    """无量纲扰动 -> 实际输入值，语义与 runtime.intervene 完全一致。"""
    if set(u_by_node) != set(obj["controllable_inputs"]):
        raise ValueError("无量纲扰动必须覆盖全部外部输入")
    inputs = {}
    for i, nid in enumerate(obj["controllable_inputs"]):
        u = u_by_node[nid]
        lo, hi = obj["intervention_bounds"][nid]
        if not math.isfinite(u) or not lo - 1e-12 <= u <= hi + 1e-12:
            raise ValueError(f"扰动超出范围：{nid}={u}")
        inputs[nid] = obj["baseline"][i] + obj["input_scales"][i] * u
    return inputs


def normalized_response(obj, u_by_node, trace=False):
    """最终输出相对基准的归一化响应（与 runtime 口径一致）。"""
    out_id = obj["designated_outputs"][0]
    if trace:
        out, tr = evaluate_dag(obj, intervene(obj, u_by_node), trace=True)
        return {out_id: (out[out_id] - obj["baseline_output"]) / obj["output_scale"]}, tr
    out = evaluate_dag(obj, intervene(obj, u_by_node))
    return {out_id: (out[out_id] - obj["baseline_output"]) / obj["output_scale"]}


# ------------------------------------------------------------------
# 自检：单超边对象必须与 runtime 逐位一致
# ------------------------------------------------------------------
def selftest():
    """用真实单关系对象验证：本求值器与原 runtime 结果完全一致。"""
    import json
    import glob
    ok = 0
    checked = 0
    pats = []
    for ds in ("multiplicative_growth", "linear_drive_resistance", "saturation_response"):
        pats += sorted(glob.glob(str(ROOT / f"cases/{ds}/group_tr_*/data/input/objects/obj_*_tgt.json")))[:5]
    for f in pats:
        o = json.load(open(f, encoding="utf-8"))
        # 单超边对象：把顶层 function 搬到边上，语义应完全等价
        o2 = dict(o)
        o2["edges"] = [dict(e, function=o["function"]) for e in o["edges"]]
        for combo in [(-0.2, 0.2), (0.0, 0.0), (0.1, -0.1)]:
            u = dict(zip(o["controllable_inputs"],
                         combo[:len(o["controllable_inputs"])]))
            a = runtime.normalized_response(o, u)[o["designated_outputs"][0]]
            b = normalized_response(o2, u)[o["designated_outputs"][0]]
            checked += 1
            if abs(a - b) < 1e-14:
                ok += 1
            else:
                print(f"  不一致 {f} u={u}: runtime={a} dag={b}")
    print(f"自检：{ok}/{checked} 与 runtime 一致")
    assert ok == checked, "单超边语义与 runtime 不一致"
    return ok, checked


if __name__ == "__main__":
    selftest()
