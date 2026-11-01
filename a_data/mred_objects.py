"""MRED 对象构造（v2：公开输入去标识）。

只负责「造对象」，不落盘。所有数值都经 runtime.py 实跑验算，验不过直接抛异常。

v2 相对 v1 的改动（对应 2026-11-01 评审第 3 条「公开输入泄漏标签」）：
1. 有效源与干扰源共用同一节点 ID 池（v1..v9），都由调用方随机分派，
   不再出现「有效源 b*、干扰源 n1/n2」这种按前缀就能区分的情况。
2. 所有候选源的 label 统一为「候选源域」，真实领域名只进封存参考
   与 relation/analogy.json，不再出现在公开的 data/input/objects/*.json。
3. 候选源列表顺序由组哈希打乱，有效源不再固定在首位。
4. 目标域节点 ID 也对齐同一池（目标域不再是 role 名），
   避免「目标用角色名、候选源用随机名」这种结构提示。

关键约定（与 data/MRED域对规格.md、T01-schema.json 一致）：
1. baseline / input_scales 是按 controllable_inputs 顺序的列表
2. 函数字符串用节点 ID；饱和类 R_max、K 是内联常量，不是节点
3. 饱和类 input0 必须 = K（半饱和点约束），两域相对 K 位置相同
"""
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "a_data"))

import runtime  # noqa: E402

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
        bounds=[-0.8, 1.0],
    ),
}

# 与 mred_interference.NODE_ID_POOL 保持一致：有效源、干扰源、目标域共用
NODE_ID_POOL = ["v1", "v2", "v3", "v4", "v5", "v6", "v7", "v8", "v9"]

# 公开数据里所有候选源域统一的占位标签（真实领域名只在封存侧）
PUBLIC_SOURCE_LABEL = "候选源域"
PUBLIC_TARGET_LABEL = "目标域"

# 节点标签：中性、只说明作用，不透露领域，也不透露「这是正确答案」
NEUTRAL_NODE_LABEL = {
    "current": "量 A",
    "ratio": "量 B",
    "next": "量 C",
    "driver": "量 A",
    "resistance": "量 B",
    "response": "量 C",
    "input": "量 A",
}


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


def assign_node_ids(relation_type, seed, pool=None):
    """从统一 ID 池随机分派「角色 -> 节点 ID」。"""
    roles = ROLE_SPEC[relation_type]["roles"]
    rng = random.Random(seed)
    picked = rng.sample(pool or NODE_ID_POOL, len(roles))
    return {role: picked[i] for i, role in enumerate(roles)}


def make_object(object_id, relation_type, spec_domain, role_to_node,
                label=None, public_label=PUBLIC_SOURCE_LABEL):
    """构造一个 mechanistic 对象。

    role_to_node 必须由调用方给出（有效源、干扰源、目标域全部走同一 ID 池）。
    label: 封存侧使用的真实领域名；public_label: 公开数据里写的占位标签。
    返回的对象同时带 public_label 与 _sealed_label，落盘时由写盘函数选择。
    """
    s = ROLE_SPEC[relation_type]
    roles = s["roles"]

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

    # 节点标签也去标识：不写「当前本金」这类领域词，只写中性角色描述
    nodes = [dict(node_id=role_to_node[r], label=NEUTRAL_NODE_LABEL[r],
                  type="positive_scalar") for r in roles]

    obj = {
        "object_id": object_id,
        "object_kind": "mechanistic",
        "relation_type": relation_type,
        "split": None,
        "label": public_label,
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
        "input_scales": list(baseline_list),
        "baseline_output": baseline_output,
        "output_scale": baseline_output,
        "legal_domain": legal_domain,
        "intervention_bounds": intervention_bounds,
        "provenance": {"dataset": "mred", "original_id": None,
                       "structure_source": "provided"},
    }
    if relation_type == "saturation_response":
        obj["_R_max"] = spec_domain["R_max"]
        obj["_K"] = spec_domain["K"]
    # 封存用（落盘前剔除，只写进 sealed/ 与 relation/analogy.json）
    if label is not None:
        obj["_sealed_label"] = label
        obj["_sealed_node_labels"] = {role_to_node[r]: spec_domain["names"][r]
                                     for r in roles}
    return obj, role_to_node


def positive_max_deviation(src_obj, tgt_obj, node_map):
    """正例响应等价性：二维 u 网格逐点比对，两域归一化响应必须相等。"""
    tgt_to_src = {v: k for k, v in node_map.items()}
    tgt_inputs = tgt_obj["controllable_inputs"]
    max_dev = 0.0
    worst = None

    def dev_at(u_t):
        u_s = {tgt_to_src[n]: u for n, u in u_t.items()}
        rt = runtime.normalized_response(tgt_obj, u_t)[tgt_obj["designated_outputs"][0]]
        rs = runtime.normalized_response(src_obj, u_s)[src_obj["designated_outputs"][0]]
        return abs(rs - rt), rs, rt

    grids = []
    for nid in tgt_inputs:
        lo, hi = tgt_obj["intervention_bounds"][nid]
        grids.append([lo, lo / 2, 0.0, hi / 2, hi])

    # 所有输入维度的笛卡尔积，一维和二维统一处理（第一版二维只做了 5x5 且漏了
    # 非主输入维度的边界组合，这里显式覆盖全组合）
    import itertools
    for combo in itertools.product(*grids):
        u_t = dict(zip(tgt_inputs, combo))
        d, rs, rt = dev_at(u_t)
        if d > max_dev:
            max_dev, worst = d, (u_t, rs, rt)
    return max_dev, worst


def scan_error(src_obj, tgt_obj, u_grid):
    """在给定 u 网格上算 max min(1,(rs-rt)^2) 与见证点。

    u_grid: list[dict(源节点ID -> u)]，调用方负责把目标维度映射到源维度。
    """
    best = (0.0, None)
    for u_s, u_t in u_grid:
        try:
            rt = list(runtime.normalized_response(tgt_obj, u_t).values())[0]
            rs = list(runtime.normalized_response(src_obj, u_s).values())[0]
        except ValueError:
            continue
        err = min(1.0, (rs - rt) ** 2)
        if err > best[0]:
            best = (err, dict(u_target=u_t, u_source=u_s, r_target=rt, r_source=rs))
    return best


def bump(u, amplitude=0.3, center=0.13, width=0.03):
    """任务书 L172 局部扰动原型（与 verify_cases.py 一致）。"""
    return amplitude * (math.exp(-((u - center) / width) ** 2)
                        - math.exp(-(center / width) ** 2))


# ============================================================
# 允许映射空间的枚举（任务书 L1008「小图可枚举类型兼容的一一映射」）
# ============================================================
def enumerate_allowed_mappings(src_obj, tgt_obj):
    """枚举全部「类型兼容」的节点双射 × 超边双射（L1008 小图枚举）。

    任务书 L1008 要求负任务核验整个候选库，且「不能只证明预期映射失败」。
    本库规模下可以完全枚举：
      - 节点映射：所有双射中满足 类型相等 的那些
        （本库节点全是 positive_scalar，所以 3 节点 = 3! = 6 个，饱和类 2 节点 = 2 个）
      - 超边映射：超边数相等，唯一

    注意：这里只按「类型」过滤（与任务书 L1008 的「类型兼容的一一映射」一致），
    角色/端点/双射等其余条件在 check_structure_condition 里逐项判定。
    也就是说，枚举出来的是**待检候选**，不是「已知合法」的映射；
    每个候选都必须真的跑一遍结构检查和响应检验，不能因为没有角色对齐就直接判失败
    （v2 早期版本就是这么做的，会把「未验证」写成「已验证」）。
    实测：本库所有源域的最优映射误差 ≥ 0.49，远超 0.05 容差，
    因此不存在「非角色对齐但实际有效」的映射；这一探测见 data/MRED数据说明.md 第七节。

    返回 list[(fV, fE)]，fV: 源节点->目标节点，fE: 源超边->目标超边。
    """
    import itertools
    snodes = [n["node_id"] for n in src_obj["nodes"]]
    tnodes = [n["node_id"] for n in tgt_obj["nodes"]]
    stype = {n["node_id"]: n["type"] for n in src_obj["nodes"]}
    ttype = {n["node_id"]: n["type"] for n in tgt_obj["nodes"]}
    if len(snodes) != len(tnodes):
        return []
    out = []
    for perm in itertools.permutations(tnodes):
        fV = dict(zip(snodes, perm))
        if any(stype[v] != ttype[fV[v]] for v in snodes):
            continue
        out.append((fV, {"r1": "r1"}))
    return out


def check_structure_condition(src_obj, tgt_obj, fV, fE):
    """按式(eq:structure) 逐项检查一个具体映射。返回 (是否通过, 失败项列表)。

    检查项与 L1034 的统一清单对应：
      节点双射 / 超边双射 / 每节点类型 / 每超边类型 / 输入集合 / 输出集合 /
      每节点-超边角色

    另外加一项「端点标注与实际依赖一致」：任务书 L1000 把「改变输入输出端」
    列为结构错误的构造方式，而纯标注比对看不出这种错（标注照抄目标域就能过），
    所以用数值探测确认每个被标注为输入的节点确实影响输出。
    """
    fails = []
    snodes = [n["node_id"] for n in src_obj["nodes"]]
    tnodes = [n["node_id"] for n in tgt_obj["nodes"]]
    if set(fV) != set(snodes) or set(fV.values()) != set(tnodes) \
            or len(set(fV.values())) != len(fV):
        fails.append("节点双射")
    se_by_id = {e["edge_id"]: e for e in src_obj["edges"]}
    te_by_id = {e["edge_id"]: e for e in tgt_obj["edges"]}
    if set(fE) != set(se_by_id) or set(fE.values()) != set(te_by_id) \
            or len(set(fE.values())) != len(fE):
        fails.append("超边双射")
    snode_t = {n["node_id"]: n["type"] for n in src_obj["nodes"]}
    tnode_t = {n["node_id"]: n["type"] for n in tgt_obj["nodes"]}
    for v in snodes:
        w = fV.get(v)
        if w is None or snode_t[v] != tnode_t[w]:
            fails.append(f"节点类型:{v}")
    for a, e_s in se_by_id.items():
        e_t = te_by_id.get(fE.get(a))
        if e_t is None:
            fails.append(f"超边:{a}")
            continue
        if e_s["edge_type"] != e_t["edge_type"]:
            fails.append(f"超边类型:{a}")
        if [fV.get(v) for v in e_s["input_nodes"]] != e_t["input_nodes"]:
            fails.append(f"输入集合:{a}")
        if [fV.get(v) for v in e_s["output_nodes"]] != e_t["output_nodes"]:
            fails.append(f"输出集合:{a}")
        for v in snodes:
            if v in e_s["roles"]:
                if e_s["roles"][v] != e_t["roles"].get(fV.get(v)):
                    fails.append(f"角色:{v}")
    # 端点标注与实际依赖是否一致（L1000 的「改变输入输出端」）
    ok_dep, dead = structural_claim_ok(src_obj)
    if not ok_dep:
        for v in dead:
            fails.append(f"输入端点无效:{v}")
    return (len(fails) == 0), fails


def structural_claim_ok(obj, rel_tol=1e-9):
    """数值探测「超边端点标注是否与函数实际依赖一致」。

    对每个被标注为输入端的节点：把它的实际值从 baseline 改动 +10%，
    输出必须随之变化。若输出完全不变，说明这个节点实际上不是输入，
    端点/角色标注与函数不符 —— 这就是任务书 L1000 的「改变输入输出端」。

    返回 (是否一致, 不被实际依赖的节点列表)
    """
    out_id = obj["designated_outputs"][0]
    base = dict(zip(obj["controllable_inputs"], obj["baseline"]))
    y0 = runtime.evaluate_object(obj, base)[out_id]
    dead = []
    for nid in obj["controllable_inputs"]:
        probe = dict(base)
        probe[nid] = base[nid] * 1.1
        y1 = runtime.evaluate_object(obj, probe)[out_id]
        if abs(y1 - y0) <= rel_tol * max(1.0, abs(y0)):
            dead.append(nid)
    return (len(dead) == 0), dead
