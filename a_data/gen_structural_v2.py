"""MRED 独立测试集 v2 生成器（30 基础组 / 60 任务）。

与 v1.1（cases/structural_enhanced/）的关系：**不是递进式扩写，而是直接构建完整 DAG**。
v1.1 用 S0→S1→S2→S3→S4 五个固定形状、20 种组合写死 30 组；v2 用 6 个 DAG 原型
（图 = 一组相互依赖的多元关系）现场生成完整对象，图的深度与宽度在原型层就定死，
不做「给小图加节点」的批量制造。

协议依据（research-principles-experiment-taskbook.tex）：
  L989  任务单位 = 一个目标 + 候选源域库；正任务库内≥1 有效映射，负任务无有效映射
  L991  每组 = 1 正任务 + 1 负任务，任务数与基础组数分开报告
  L993  三类关系：线性驱动-阻力 / 乘性增长 / 饱和响应
  L1006 正任务 10 候选（1 有效 + 三类干扰）；负任务移除有效源再补干扰，总数仍 10
  L1008 负任务必须核验整个候选库；小图可枚举类型兼容的一一映射
  L1010 参考容差 CTC≥0.95、最大误差≤0.05，属数据版本不可调；负例须有超容差见证点
  L1020 70/15/15，种子 20261007，同组派生不跨划分
  L1024 测试任务预生成 100 个独立合法干预点，封存
  L682  多条关系按依赖顺序计算；第一批必须无环

规模上限（用户 2026-11-04 拍板）：|V| ≤ 9、|E| ≤ 5，保证负任务可全枚举。

用法：
    python a_data/gen_structural_v2.py --dry      # 全量验算，不落盘
    python a_data/gen_structural_v2.py            # 验算通过后落盘
"""
import argparse
import hashlib
import itertools
import json
import math
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "a_data"))

import runtime       # noqa: E402
import runtime_dag   # noqa: E402

OUT_DIR = ROOT / "cases" / "structural_v2"
SCHEMA_VERSION = json.load(open(ROOT / "T01-schema.json", encoding="utf-8"))["schema_version"]
VOCAB_VERSION = json.load(open(ROOT / "T01-vocabulary.json", encoding="utf-8"))["vocab_version"]

SEED = 20261007
SPLIT_SEED = 20261007
INTERVENTION_SEED = 20261007
MAX_ERROR = 0.05          # PDF L1010 固定，不随方法调参
MIN_CTC = 0.95
# 容差判据：项目 E = min(1,(r_s-r_t)^2)，故 |Δr| > sqrt(0.05) 才算超容差。
# 与 v1/v1.1 同一口径（gen_structural_enhanced.py 亦如此），保证跨库可比。
ERR_THRESHOLD = math.sqrt(MAX_ERROR)      # 0.2236067977

# 上限（用户拍板）：超过即不可全枚举
MAX_V, MAX_E = 9, 5
MAX_ENUM = 3_000_000        # 单任务枚举上限（|V|!×|E|!，9!×5! = 43,545,600 需剪枝）
MAX_ABS_RESP = 2.0          # 归一化响应绝对值上界（越界说明量级混搭出错）

NODE_POOL = [f"v{i}" for i in range(1, 13)]


def stable_hash(*parts):
    payload = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def seeded(*parts):
    return int(stable_hash(*parts), 16) % (2 ** 31)


# ==================================================================
# 关系家族：边级构造（与词表 equation_template 对齐）
# ==================================================================
FAMILY = {
    "multiplicative_growth": dict(in_roles=("current", "ratio"), out_role="next", arity=2),
    "linear_drive_resistance": dict(in_roles=("driver", "resistance"), out_role="response", arity=2),
    "saturation_response": dict(in_roles=("input",), out_role="response", arity=1),
}

# 家族基准（与 v1 正式库量级一致，一个真实域对的工作点）
BASE = {
    "multiplicative_growth": dict(current=1000.0, ratio=0.1),
    "linear_drive_resistance": dict(driver=100.0, resistance=20.0),
    "saturation_response": dict(R_max=10.0, K=1.0),
}


def fam_bounds(fam):
    """干预区间。饱和族必须 [-0.8,1.0]（v1 正式库口径）；其余 ±0.2。"""
    return [-0.8, 1.0] if fam == "saturation_response" else [-0.2, 0.2]


def defuse_saturation_bound_choice(fams):
    """图里只要有一条饱和边，全图用饱和区间（中间量需要大范围才扫得到变化）。"""
    return [-0.8, 1.0] if "saturation_response" in fams else [-0.2, 0.2]


# ==================================================================
# 6 个 DAG 原型：直接定义完整图，不做「小图加节点」
# ==================================================================
# 原型 = 一组边 (输入角色列表, 输出角色) + 外部输入清单 + 指定输出 + 每边家族。
# 角色名只是生成期占位，落盘前统一换成语义无关节点 ID。
#
# 覆盖目标（用户要求：多层链式、多分支共享、多路径汇合、多子系统、深度混合、规模不同）：
#   P1 deep_chain3    深度 3 的纯链       | 3 边 / 5 节点
#   P2 chain_merge    链 + 旁路汇合       | 4 边 / 7 节点 / 深度 2，含中间量复用
#   P3 shared_fan     单输入喂三路后合并   | 4 边 / 7 节点 / 共享节点 2 个
#   P4 twin_subsystems 两套子系统并行后合并 | 5 边 / 9 节点 / 深度 2
#   P5 wide_merge     四路汇合（宽）      | 5 边 / 9 节点 / 深度 2
#   P6 sat_tail_chain 深链 + 饱和末端      | 4 边 / 7 节点 / 深度 3

def P1_deep_chain3(f=( "multiplicative_growth",) * 3):
    """x1,x2 -> z1 -> z2 -> y，三层串联。"""
    return dict(
        proto_id="P1_deep_chain3",
        edges=[(["x1", "x2"], "z1"), (["z1", "x3"], "z2"), (["z2", "x4"], "y")],
        inputs=["x1", "x2", "x3", "x4"], output="y",
        families=list(f),
    )


def P2_chain_merge(fa="multiplicative_growth", fb="linear_drive_resistance",
                   fc="multiplicative_growth"):
    """两路并行（一深一浅）后汇合：z1=f(x1,x2); z2=g(z1,x3); w=g2(x4,x5); y=h(z2,w)。"""
    return dict(
        proto_id="P2_chain_merge",
        edges=[(["x1", "x2"], "z1"), (["z1", "x3"], "z2"),
               (["x4", "x5"], "w"), (["z2", "w"], "y")],
        inputs=["x1", "x2", "x3", "x4", "x5"], output="y",
        families=[fa, fb, fa, fc],
    )


def P3_shared_fan(fa="multiplicative_growth", fb="linear_drive_resistance",
                  fc="multiplicative_growth", fd="linear_drive_resistance"):
    """共享输入三路分支：x1 同时喂 e1/e2/e3，三路再两两合并到 y。

    z1=f1(x1,x2); z2=f2(x1,x3); z3=f3(x1,x4); w=f4(z1,z2); y=? -> 需要 5 边
    为守住 5 边上限，末级只合并两路，第三路进入第二个中间量后再合并：
    z1=f1(x1,x2); z2=f2(x1,x3); z3=f3(x1,x4); w=f4(z1,z2); y=f5(w,z3)
    """
    return dict(
        proto_id="P3_shared_fan",
        edges=[(["x1", "x2"], "z1"), (["x1", "x3"], "z2"), (["x1", "x4"], "z3"),
               (["z1", "z2"], "w"), (["w", "z3"], "y")],
        inputs=["x1", "x2", "x3", "x4"], output="y",
        families=[fa, fb, fc, fd, fa],
    )


def P4_shared_deep(fa="multiplicative_growth", fb="linear_drive_resistance"):
    """共享输入 + 两侧深度不等 + 双重复用（9 节点 5 边 / 深度 4）：

    e1: a1 = f(x1, x2)
    e2: b1 = g(x1, x3)      <- x1 同时喂 e1/e2（外部输入共享）
    e3: c1 = f2(a1, x4)
    e4: w  = g2(b1, c1)     <- 两路汇合
    e5: y  = f3(w, a1)      <- a1 同时喂 e3/e5（中间量共享，第二种复用）

    这是 v1.1 完全没有的形状：同一对象里既有「外部输入共享」又有「中间量共享」，
    且链路长度不等（x1→a1→c1→w→y 与 x1→b1→w→y）。
    """
    return dict(
        proto_id="P4_shared_deep",
        edges=[(["x1", "x2"], "a1"), (["x1", "x3"], "b1"), (["a1", "x4"], "c1"),
               (["b1", "c1"], "w"), (["w", "a1"], "y")],
        inputs=["x1", "x2", "x3", "x4"], output="y",
        families=[fa, fb, fa, fb, fa],
    )


def P5_three_way_merge(fa="linear_drive_resistance", fb="multiplicative_growth",
                       fc="multiplicative_growth"):
    """三路汇合 + 中间量二次消费（9 节点 5 边 / 深度 3）：

    e1: z1 = f(x1, x2)
    e2: z2 = g(x3, x4)
    e3: w  = f2(z1, z2)     <- 两路汇合
    e4: u  = g2(w, z1)      <- z1 二次消费（中间量共享）
    e5: y  = h(u, z2)       <- z2 二次消费 + 与 u 汇合

    **不能**让比例量（乘性 ratio）去吃绝对量：e4 若写 w*(1+z1) 而 z1 是
    driver/resistance 量级（100/20），(1+z1) 会爆到 6 倍，归一化响应越界到 1.9
    （实测 group_v2_0004 基准输出 4.2e-4、max|r|=1.91）。所以 e4/e5 的
    "current/driver" 侧必须接中间量、"ratio/resistance" 侧接同量级量，
    并由 build_object 校验 |r| <= MAX_ABS_RESP。
    """
    return dict(
        proto_id="P5_three_way_merge",
        edges=[(["x1", "x2"], "z1"), (["x3", "x4"], "z2"),
               (["z1", "z2"], "w"), (["w", "x2"], "u"), (["u", "z2"], "y")],
        inputs=["x1", "x2", "x3", "x4"], output="y",
        families=[fa, fb, fc, fb, fa],
    )


def P6_sat_tail_chain(fa="multiplicative_growth", fb="linear_drive_resistance",
                      fsat="saturation_response"):
    """深链 + 饱和末端（9 节点 5 边 / 深度 4）：

    e1: z1 = f(x1, x2)
    e2: z2 = g(z1, x3)      <- 线性边，resistanc 接外部输入
    e3: w  = f2(z2, x4)
    e4: z3 = g2(w, x5)
    e5: y  = sat(z3)        <- 饱和**只能作末端**：单输入关系；
                               K 取 z3 在本域的基准值（半饱和点 input0=K）

    饱和不能出现在中间位置：它的输出永远落在 (0, R_max)，而下游若按
    current/driver 角色使用会被量级约束卡死；作为汇合点更不行（需要两路输入）。
    """
    return dict(
        proto_id="P6_sat_tail_chain",
        edges=[(["x1", "x2"], "z1"), (["z1", "x3"], "z2"),
               (["z2", "x4"], "w"), (["w", "z1"], "z3"), (["z3"], "y")],
        inputs=["x1", "x2", "x3", "x4"], output="y",
        families=[fa, fb, fa, fb, fsat],
    )


# ==================================================================
# 对象构造：从原型直接实例化成完整对象
# ==================================================================
def assign_ids(proto, group_id):
    """把原型里的角色名（x1.., z1.., y）换成无语义节点 ID。

    每组独立采样，且**同一组内目标域与全部候选共用同一份映射**——
    否则按角色对齐的扰动 u 会打到错的节点上（v1 正式库踩过的坑）。
    """
    roles = list(dict.fromkeys([r for ins, out in proto["edges"] for r in list(ins) + [out]]))
    rng = random.Random(seeded(group_id, "ids"))
    picked = rng.sample(NODE_POOL, len(roles))
    return {r: picked[i] for i, r in enumerate(roles)}


def topo_order(edges):
    """按「输入已被产出」剥离求边序；同时做环/悬空检测（PDF L682 必须无环）。"""
    produced = {n for e in edges for n in e["output_nodes"]}
    remain = [e["edge_id"] for e in edges]
    by = {e["edge_id"]: e for e in edges}
    ready = {n for e in edges for n in e["input_nodes"]} - produced
    order = []
    while remain:
        cur = [eid for eid in remain if all(n in ready for n in by[eid]["input_nodes"])]
        if not cur:
            raise ValueError(f"存在环或悬空输入：剩余 {remain}")
        for eid in sorted(cur):
            order.append(eid)
            ready.update(by[eid]["output_nodes"])
            remain.remove(eid)
    return order


def expand_to_expression(edges, output_node):
    """把 DAG 按拓扑序符号代入，展开成只含外部输入的单式（schema 顶层 function）。"""
    import re as _re
    by = {e["edge_id"]: e for e in edges}
    ok, frag = set(), {}
    order = topo_order(edges)
    for eid in order:
        e = by[eid]
        f = e["function"]
        for n in e["input_nodes"]:
            src = frag.get(n, n)
            if src != n:
                f = _re.sub(r"\b" + _re.escape(n) + r"\b", f"({src})", f)
        frag[e["output_nodes"][0]] = f
        ok.add(e["output_nodes"][0])
    return frag[output_node]


def _expr_for_edge(fam, node_ids, const=None):
    """按家族给一条边写函数。高元数只用于乘性/线性（饱和单输入）。"""
    if fam == "multiplicative_growth":
        if len(node_ids) == 2:
            a, b = node_ids
            return f"{a} * (1 + {b})"
        *ab, r = node_ids
        return " * ".join(ab) + f" * (1 + {r})"
    if fam == "linear_drive_resistance":
        if len(node_ids) == 2:
            a, b = node_ids
            return f"{a} / {b}"
        if len(node_ids) == 3:
            return f"{node_ids[0]} * {node_ids[1]} / {node_ids[2]}"
        return " * ".join(node_ids[:2]) + " / (" + " * ".join(node_ids[2:]) + ")"
    if fam == "saturation_response":
        (x,) = node_ids
        return f"{const['R_max']} * {x} / ({const['K']} + {x})"
    raise ValueError(fam)


def roles_for(fam, node_ids, out_id):
    r = {}
    if fam == "saturation_response":
        r[node_ids[0]] = "input"
    elif fam == "multiplicative_growth":
        for n in node_ids[:-1]:
            r[n] = "current"
        r[node_ids[-1]] = "ratio"
    else:
        r[node_ids[0]] = "driver"
        for n in node_ids[1:]:
            r[n] = "resistance"
    r[out_id] = FAMILY[fam]["out_role"]
    return r


def build_object(group_id, proto, id_map, scale=1.0, tag="tgt", ratio_align=None,
                 param_jitter=0.0):
    """从一个 DAG 原型实例化完整对象。

    参数规则（三条硬约束，全部有实测依据）：
      1. 乘性 ratio 是比例量 ⇒ **跨域必须同值**（ratio_align 传入目标域的值）；
         否则归一化响应含 r0 项，两域不一致（v1 实测偏差 0.033）。
      2. 饱和边 input0 == K（半饱和点）；若输入是中间变量，K 取该中间量**本域**基准
         （取目标域的值会让两域不等价，实测偏差 0.342）。
      3. 线性 driver/resistance 比例缩放不影响归一化响应（r=(1+u_d)/(1+u_r)-1）。
    """
    rng = random.Random(seeded(group_id, tag, round(scale, 6)))
    fams = proto["families"]
    edges = []
    values = {}        # 节点ID -> 基准值（外部输入与中间量的本域基准）

    # 外部输入基准：按所属边的角色定值。同一节点可能被多条边消费（共享节点），
    # 取**第一次**赋的值；若后续边想给它另一种角色量级，以第一次为准并断言一致。
    for (ins, out), fam in zip(proto["edges"], fams):
        for pos, role in enumerate(ins):
            nid = id_map[role]
            if nid in values:
                continue
            if fam == "saturation_response":
                values[nid] = BASE[fam]["K"] * scale
            elif fam == "multiplicative_growth":
                if pos == len(ins) - 1:
                    values[nid] = (ratio_align if ratio_align is not None
                                   else BASE[fam]["ratio"])
                else:
                    j = 1.0 + param_jitter * (rng.random() - 0.5)
                    values[nid] = BASE[fam]["current"] * scale * j
            else:
                if pos == 0:
                    j = 1.0 + param_jitter * (rng.random() - 0.5)
                    values[nid] = BASE[fam]["driver"] * scale * j
                else:
                    values[nid] = BASE[fam]["resistance"] * scale
    # 比例量在源域也必须同值（硬约束 1）
    ext_inputs = [id_map[r] for r in proto["inputs"]]

    # 按拓扑序算中间量基准，同时写边
    order = topo_order([dict(edge_id=f"e{i+1}",
                             input_nodes=[id_map[r] for r in ins],
                             output_nodes=[id_map[out]]) for i, (ins, out) in enumerate(proto["edges"])])
    edge_spec = {f"e{i+1}": (proto["edges"][i], fams[i]) for i in range(len(proto["edges"]))}

    for eid in order:
        (ins, out), fam = edge_spec[eid]
        node_ids = [id_map[r] for r in ins]
        out_id = id_map[out]
        const = None
        if fam == "saturation_response":
            # 硬约束 2：K = 该输入在本域的基准值（外部输入或中间量）
            K = values[node_ids[0]]
            const = dict(R_max=BASE[fam]["R_max"] * scale, K=K)
        expr = _expr_for_edge(fam, node_ids, const)
        edges.append(dict(
            edge_id=eid, edge_type=fam,
            input_nodes=node_ids, output_nodes=[out_id],
            roles=roles_for(fam, node_ids, out_id),
            function=expr,
        ))
        local = {n: values[n] for n in node_ids}
        values[out_id] = runtime.expression_value(expr, local)

    edges.sort(key=lambda e: int(e["edge_id"][1:]))
    obj = {
        "object_id": f"obj_{group_id}_{tag}",
        "object_kind": "mechanistic",
        "relation_type": "multi_edge_dag",
        "split": None,           # 由 assign_splits 填
        "label": "目标域" if tag == "tgt" else "候选源域",
        "nodes": [dict(node_id=n, label="量 " + chr(65 + i), type="positive_scalar")
                  for i, n in enumerate(dict.fromkeys(
                      [x for e in edges for x in e["input_nodes"] + e["output_nodes"]]))],
        "edges": edges,
        "function": expand_to_expression(edges, id_map[proto["output"]]),
        "controllable_inputs": ext_inputs,
        "designated_outputs": [id_map[proto["output"]]],
        "baseline": [values[n] for n in ext_inputs],
        "input_scales": [values[n] for n in ext_inputs],
        "legal_domain": {n: [1e-6, None] for n in ext_inputs},
        "intervention_bounds": {n: list(defuse_saturation_bound_choice(fams)) for n in ext_inputs},
        "provenance": dict(dataset="mred_v2", original_id=None,
                           structure_source="provided" if tag == "tgt" else "controlled_synthetic"),
    }
    base_vals = dict(zip(ext_inputs, obj["baseline"]))
    y0 = runtime_dag.evaluate_dag(obj, base_vals)[obj["designated_outputs"][0]]
    if not (math.isfinite(y0) and abs(y0) > 0):
        raise ValueError(f"{group_id}/{tag}: 基准输出非正有限值 {y0}")
    obj["baseline_output"] = y0
    obj["output_scale"] = y0
    # 归一化响应的量级校验：混搭家族时若把「比例量」接上「绝对量」，
    # (1+z) 会爆到 6 倍，r 越界到 1.9（实测 group_v2_0004）。要求
    # 网格上 |r| <= MAX_ABS_RESP，否则该组的家族组合不成立。
    for u in scan_points(obj, n=200):
        r = runtime_dag.normalized_response(obj, u)[obj["designated_outputs"][0]]
        if not math.isfinite(r) or abs(r) > MAX_ABS_RESP:
            raise ValueError(f"{group_id}/{tag}: 归一化响应越界 {r:.4g} > {MAX_ABS_RESP}，"
                             f"该家族组合在 {tag} 上不成立")
    return obj


# ==================================================================
# 映射枚举：结构条件 + 响应条件（PDF L342 / L1008 / L1010）
# ==================================================================
def enum_structural_pairs(src, tgt):
    """枚举「节点双射 × 超边双射」中满足 eq:structure 的映射。

    PDF L342：节点数、超边数相等，f_V / f_E 均双射；保持 τ_V、τ_E、
    输入输出端点（f_V(e^±) = (f_E(e))^±）与逐关系角色 ρ。
    PDF L1008：小图可枚举类型兼容的一一映射。

    剪枝次序（把 |V|!|E|! 降到可跑）：
      1) 先按「同边数、同边类型」定 f_E 的候选（通常 1~3 种排列）
      2) 每条边从输出端反推：t_out 的源节点 = f_E(e) 的输出端唯一确定
      3) 输入端按角色分组做排列，而不是全排列
    本函数先做 1)+2) 的强剪枝，再对剩余自由节点做 backtracking，
    避免直接 itertools.permutations 的全排列（9!×5! = 4350 万 → 秒级）。
    """
    if len(src["nodes"]) != len(tgt["nodes"]) or len(src["edges"]) != len(tgt["edges"]):
        return []
    se, te = src["edges"], tgt["edges"]
    sn = [n["node_id"] for n in src["nodes"]]
    tn = [n["node_id"] for n in tgt["nodes"]]
    stype = {n["node_id"]: n["type"] for n in src["nodes"]}
    ttype = {n["node_id"]: n["type"] for n in tgt["nodes"]}

    # 边类型 → 候选 f_E 排列（同类型边互相可换）
    from collections import defaultdict
    s_by_t, t_by_t = defaultdict(list), defaultdict(list)
    for e in se:
        s_by_t[e["edge_type"]].append(e)
    for e in te:
        t_by_t[e["edge_type"]].append(e)
    if {k: len(v) for k, v in s_by_t.items()} != {k: len(v) for k, v in t_by_t.items()}:
        return []
    per_type = []
    for k in s_by_t:
        per_type.append(list(itertools.permutations(t_by_t[k])))
    for combo in itertools.product(*per_type):
        fE_list = {}
        for k, perm in zip(s_by_t.keys(), combo):
            for s_e, t_e in zip(s_by_t[k], perm):
                fE_list[s_e["edge_id"]] = t_e
        # 同一 f_E 下的 f_V：逐边端点 + 角色约束
        res = _match_nodes(se, sn, tn, stype, ttype, fE_list)
        for fV in res:
            yield fV, {k: v["edge_id"] for k, v in fE_list.items()}


def _match_nodes(se, sn, tn, stype, ttype, fE_list):
    """给定 f_E，枚举满足端点/角色/类型约束的 f_V。

    做法是**约束传播 + 回溯**，不是全排列再过滤：
      · 每条边的输出端唯一确定一组 (源节点 -> 目标节点)
      · 每条边的输入端按角色分组，组内做排列（同角色可互换）
      · 一旦出现冲突立即剪枝（冲突 = 两个源节点要映到同一目标节点）
    9 节点 5 边的约束图通常把自由节点压到 2~3 个，回溯规模是个位数。
    """
    from collections import defaultdict
    # 收集每条边的「约束单元」：输出对 + 输入按角色的分组对
    units = []          # [(src_group, tgt_group)]，组内可任意置换
    for s_e in se:
        t_e = fE_list[s_e["edge_id"]]
        if len(s_e["output_nodes"]) != 1 or len(t_e["output_nodes"]) != 1:
            return
        units.append(([s_e["output_nodes"][0]], [t_e["output_nodes"][0]]))
        bs, bt = defaultdict(list), defaultdict(list)
        for n in s_e["input_nodes"]:
            bs[s_e["roles"].get(n)].append(n)
        for n in t_e["input_nodes"]:
            bt[t_e["roles"].get(n)].append(n)
        if set(bs) != set(bt) or any(len(bs[r]) != len(bt[r]) for r in bs):
            return
        for r in bs:
            units.append((bs[r], bt[r]))

    # 回溯：按单元顺序赋值，冲突即剪枝
    fV = {}
    used_t = set()

    def bt(idx):
        if idx == len(units):
            if _structure_ok(se, fE_list, fV):
                yield dict(fV)
            return
        for perm in itertools.permutations(units[idx][1]):
            ok = True
            trial = []
            for s, t in zip(units[idx][0], perm):
                if s in fV:                      # 该源节点已由更早的单元确定
                    if fV[s] != t:
                        ok = False
                        break
                    continue                     # 不重复占用 trial
                if t in used_t:                  # 目标节点已被占用 -> 违反双射
                    ok = False
                    break
                if stype[s] != ttype[t]:
                    ok = False
                    break
                trial.append((s, t))
            if not ok:
                continue
            for s, t in trial:
                fV[s] = t
                used_t.add(t)
            yield from bt(idx + 1)
            for s, t in trial:
                del fV[s]
                used_t.discard(t)

    yield from bt(0)


def _structure_ok(se, fE_list, fV):
    """完整 eq:structure 校验：类型、端点、角色。"""
    for s_e in se:
        t_e = fE_list[s_e["edge_id"]]
        if s_e["edge_type"] != t_e["edge_type"]:
            return False
        if {fV[v] for v in s_e["input_nodes"]} != set(t_e["input_nodes"]):
            return False
        if {fV[v] for v in s_e["output_nodes"]} != set(t_e["output_nodes"]):
            return False
        for v, role in s_e.get("roles", {}).items():
            if t_e.get("roles", {}).get(fV[v]) != role:
                return False
    return True


# 判定采样协议：容差是 PDF 固定的（L1010），但**扫哪些点**必须同样固定下来，
# 否则「是否排除」取决于采样密度、第三方无法复算（v1 已明确推翻「加密网格兜底」：
# 靠加密网格才能抓到的薄壳反例，正解是把反例做厚，不是把网格做细）。
#
# 本库用「固定的分层随机采样」：种子 INTERVENTION_SEED 与任务无关，点数固定。
# 理由：等距 0.1 联网格在饱和区间 [-0.8,1.0] 上是 10^|V_in| 个点（5 输入 = 13 万），
# 30 组跑不动；而固定种子分层采样既能覆盖边界、又可逐位复算。
# 生成器与独立验证器**共用同一协议常量**，但各自实现采样（不共享代码）。
REF_SCAN_POINTS = 4000        # 每映射的判定点数（分层，含全部边界点）


def _grid_1d(lo, hi, step):
    vals, k = [], lo
    while k <= hi + 1e-12:
        vals.append(round(k, 8))
        k += step
    if vals and vals[-1] < hi - 1e-12:
        vals.append(hi)
    return vals


def scan_points(obj, n=REF_SCAN_POINTS, seed=INTERVENTION_SEED, step=0.2):
    """固定协议的分层采样：低密度网格（含两端，总点数有上限）+ 固定种子补随机点。

    约束：网格本身也必须封顶。饱和族 5 个外部输入时 [-0.8,1.0] 按 0.2 步长铺满是
    10^5 个点，单组要 40+ 秒，30 组跑不完。这里改为「网格点数不超过 n 时铺满，
    否则只保留全端点组合 + 单维网格」，点数恒定 REF_SCAN_POINTS，第三方可复算。
    """
    ins = obj["controllable_inputs"]
    axes = [_grid_1d(*obj["intervention_bounds"][n], step) for n in ins]
    total = 1
    for a in axes:
        total *= len(a)
    seen, out = set(), []
    if total <= n:
        for combo in itertools.product(*axes):
            key = tuple(combo)
            if key not in seen:
                seen.add(key)
                out.append(dict(zip(ins, combo)))
    else:
        # 维度太多：只用「全部端点」+「每维单点扫（其余维取中心）」
        ends = []
        for nid in ins:
            lo, hi = obj["intervention_bounds"][nid]
            ends.append([lo, hi])
        for combo in itertools.product(*ends):
            key = tuple(combo)
            if key not in seen:
                seen.add(key)
                out.append(dict(zip(ins, combo)))
        center = {nid: round(min(max(0.0, obj["intervention_bounds"][nid][0]),
                                 obj["intervention_bounds"][nid][1]), 8) for nid in ins}
        for i, nid in enumerate(ins):
            for v in axes[i]:
                u = dict(center)
                u[nid] = v
                key = tuple(u[n] for n in ins)
                if key not in seen:
                    seen.add(key)
                    out.append(u)
    rng = random.Random(seed)
    tries = 0
    while len(out) < n and tries < n * 50:
        tries += 1
        u = {}
        for nid in ins:
            lo, hi = obj["intervention_bounds"][nid]
            u[nid] = round(rng.uniform(lo, hi), 6)
        key = tuple(u[n] for n in ins)
        if key in seen:
            continue
        seen.add(key)
        out.append(u)
    return out


def max_gap_for_map(src, tgt, fV, points=None, limit=ERR_THRESHOLD):
    """在固定协议的采样点上找该映射的最大响应差；超阈值立即返回（早停）。"""
    mx = 0.0
    worst = None
    ins_t = tgt["controllable_inputs"]
    ins_s = src["controllable_inputs"]
    pts = points if points is not None else scan_points(tgt)

    def take_unique(gen, tag_prefix, n=3):
        """取三类干扰源中「运行时真的被判负」的前 n 个（且两两不同）。"""
        got, sigs = [], set()
        for k in range(24):
            try:
                cand = next(gen(k))
            except StopIteration:
                continue
            except ValueError:
                continue      # 该 k 的变异不成立（如局部扰动采不到峰），换下一个
            sig = json.dumps([cand["function"], [e["function"] for e in cand["edges"]],
                              [[e["edge_id"], e["input_nodes"], e["output_nodes"]]
                               for e in cand["edges"]]], sort_keys=True)
            if sig in sigs:
                continue
            if valid_mappings(cand, tgt, points=pts):
                continue          # 有有效映射 => 不是干扰源
            sigs.add(sig)
            cand = dict(cand)
            cand["_kind"] = KIND_LONG[tag_prefix]
            cand["object_id"] = f"obj_{gid}_{tag_prefix}{len(got):02d}"
            got.append(cand)
            if len(got) == n:
                break
        if len(got) < n:
            raise AssertionError(f"{gid}: {tag_prefix} 只凑到 {len(got)}/{n} 个真干扰源")
        return got
    for u in pts:
        rt = runtime_dag.normalized_response(tgt, u)[tgt["designated_outputs"][0]]
        # u 按目标节点给出 -> 换成源节点（f_V 是 source->target 的反向查表）
        inv = {t: s for s, t in fV.items()}
        u_s = {}
        ok = True
        for t in ins_t:
            s = inv.get(t)
            if s not in ins_s:
                ok = False
                break
            u_s[s] = u[t]
        if not ok:
            continue
        rs = runtime_dag.normalized_response(src, u_s)[src["designated_outputs"][0]]
        d = abs(rs - rt)
        if d > mx:
            mx, worst = d, dict(u)
        if mx > limit:
            return mx, worst, True
    return mx, worst, False


def valid_mappings(src, tgt, points=None):
    """PDF L986/L1008：返回该源在给定目标下的**全部**有效映射（集合，不是单个）。

    有效 = 结构成立 且 全网格响应差 <= sqrt(0.05)。
    """
    out = []
    for fV, fE in enum_structural_pairs(src, tgt):
        mx, worst, early = max_gap_for_map(src, tgt, fV, points=points)
        if not early and mx <= ERR_THRESHOLD:
            out.append(dict(node_map=fV, edge_map=fE, max_abs_diff=mx))
    return out


# ==================================================================
# 三类干扰源（PDF L1000/L1001/L1002）
# 所有变异都必须在 runtime_dag 上实跑证明「真被拒」，不能只在 JSON 层看着像。
# v1.1 的教训：structural_mutate 只交换同边两个输入的顺序 + 同步换函数，
# 数学上完全等价，483/3960 个"结构错误"源响应差 < 0.05（67.7%），是假干扰源。
# ==================================================================
def _rebench(o):
    base = dict(zip(o["controllable_inputs"], o["baseline"]))
    y = runtime_dag.evaluate_dag(o, base)[o["designated_outputs"][0]]
    o["baseline_output"] = y
    o["output_scale"] = y
    o["function"] = expand_to_expression(o["edges"], o["designated_outputs"][0])
    return o


def renode(o, mapping):
    """把对象里所有节点 ID 按 mapping 重命名（节点/边/输入/域/边界全同步）。"""
    o = json.loads(json.dumps(o))
    f = lambda n: mapping.get(n, n)
    for nd in o["nodes"]:
        nd["node_id"] = f(nd["node_id"])
    for e in o["edges"]:
        e["input_nodes"] = [f(n) for n in e["input_nodes"]]
        e["output_nodes"] = [f(n) for n in e["output_nodes"]]
        e["roles"] = {f(k): v for k, v in e["roles"].items()}
    o["controllable_inputs"] = [f(n) for n in o["controllable_inputs"]]
    o["designated_outputs"] = [f(n) for n in o["designated_outputs"]]
    o["legal_domain"] = {f(k): v for k, v in o["legal_domain"].items()}
    o["intervention_bounds"] = {f(k): v for k, v in o["intervention_bounds"].items()}
    return o


def structural_mutate(src, k, id_map):
    """结构错误（PDF L1000：交换角色 / 改变输入输出端 / 改变某条关系的连接）。

    必须**真的破坏 eq:structure**，且不能等价于原对象。v1.1 的教训：
    只交换同边两个输入顺序并同步换函数，数学上完全等价，483/3960 个
    "结构错误"源的响应差 < 0.05（67.7%），是假干扰源。

    四种变异（按 k 轮转，并循环换边，保证 3 个候选两两不同）：
      A) 角色互换：一条二元边的 current↔ratio / driver↔resistance 标注对调，
         **函数不跟着换** —— 标注与算式不符，结构上不可能有映射成立
      B) 端点改接：把某条边的第一个输入换成该边作用域外、角色表里没有的节点
      C) 关系类型错配：改一条边的 edge_type，使 τ_E 不匹配
      D) 输出端角色错配：把产出节点的角色改成输入端角色
    """
    kinds = [("A", 0), ("B", 1), ("C", 2), ("D", 3)]
    # 让不同 k 从不同 (kind, edge) 起点开始轮转
    start = k
    n_edge = len(src["edges"])
    for step in range(len(kinds) * n_edge):
        idx = (start + step) % (len(kinds) * n_edge)
        kind = kinds[idx % len(kinds)][1]
        e_idx = idx // len(kinds)
        cand = json.loads(json.dumps(src))
        e = cand["edges"][e_idx]
        try:
            if kind == 0:
                role2node = {}
                for n, r in e["roles"].items():
                    role2node.setdefault(r, []).append(n)
                swapped = False
                for r1, r2 in (("current", "ratio"), ("driver", "resistance")):
                    if r1 in role2node and r2 in role2node:
                        a, b = role2node[r1][0], role2node[r2][0]
                        e["roles"][a], e["roles"][b] = r2, r1
                        swapped = True
                        break
                if not swapped:
                    continue
            elif kind == 1:
                outside = [n["node_id"] for n in cand["nodes"]
                           if n["node_id"] not in e["input_nodes"]
                           and n["node_id"] not in e["output_nodes"]
                           and n["node_id"] not in e["roles"]]
                if not outside:
                    continue
                old, new = e["input_nodes"][0], outside[0]
                e["function"] = _subst(e["function"], old, new)
                e["input_nodes"][0] = new
                e["roles"][new] = e["roles"].pop(old)
            elif kind == 2:
                e["edge_type"] = ("linear_drive_resistance"
                                  if e["edge_type"] != "linear_drive_resistance"
                                  else "multiplicative_growth")
            else:
                out = e["output_nodes"][0]
                in_roles = [e["roles"][n] for n in e["input_nodes"] if n in e["roles"]]
                if not in_roles or e["roles"].get(out) == in_roles[0]:
                    continue
                e["roles"][out] = in_roles[0]
        except Exception:
            continue
        try:
            _rebench(cand)
        except Exception:
            continue
        yield cand


def _subst(expr, a, b):
    import re as _re
    tmp = "@@TMP@@"
    x = _re.sub(r"\b" + _re.escape(a) + r"\b", tmp, expr)
    x = _re.sub(r"\b" + _re.escape(b) + r"\b", a, x)
    return x.replace(tmp, b)


def resp_mutate(src, k):
    """结构相同、响应错误（PDF L1001：保持类型、角色和端点，改变函数形式）。

    端点必须不变 —— 每个声明为输入的节点都要继续出现在函数里。
    v1.1 踩过：用 input_nodes[1] 当前 ratio，高元数时下标 1 是第二个 current，
    真正的 ratio 被丢掉 => 违反端点保持。这里一律按 roles 定位。
    """
    o = json.loads(json.dumps(src))
    e = o["edges"][k % len(o["edges"])]
    roles = e["roles"]
    by_role = {}
    for n, r in roles.items():
        by_role.setdefault(r, []).append(n)
    ins = list(e["input_nodes"])

    def b0(nid):
        if nid in o["controllable_inputs"]:
            return o["baseline"][o["controllable_inputs"].index(nid)]
        _, tr = runtime_dag.evaluate_dag(o, dict(zip(o["controllable_inputs"], o["baseline"])), trace=True)
        mid = {r["output_node"]: r["output"] for r in tr}
        return mid.get(nid, 1.0)

    if e["edge_type"] == "multiplicative_growth":
        cur = by_role.get("current", ins[:-1])
        rat = by_role.get("ratio", [ins[-1]])[0]
        first = cur[0]
        rest = [n for n in cur if n != first]
        # 幂次变形：函数形式变了，端点全部保留
        core = f"{first} ** {2 + k % 3} / ({b0(first)} ** {1 + k % 3})"
        if rest:
            core += " * " + " * ".join(rest)
        e["function"] = f"{core} * (1 + {rat})"
    elif e["edge_type"] == "linear_drive_resistance":
        drv = by_role.get("driver", [ins[0]])
        res = by_role.get("resistance", ins[1:])
        first = drv[0]
        num = f"{first} ** {2 + k % 3} / ({b0(first)} ** {1 + k % 3})"
        if len(drv) > 1:
            num += " * " + " * ".join(drv[1:])
        e["function"] = f"{num} / ({' * '.join(res)})"
    else:
        # 饱和：Hill 阶数变化（v1 实测 ±0.2 内判不了负，必须配 [-0.8,1.0] 区间）
        import re as _re
        x = ins[0]
        m = _re.search(r"\(\s*([-0-9.eE+]+)\s*\+\s*" + _re.escape(x) + r"\s*\)", e["function"])
        K = float(m.group(1)) if m else 1.0
        R = 2.0 * b0(x)
        n = [2, 3, 0.5][k % 3]
        e["function"] = f"{R} * {x} ** {n} / ({K} ** {n} + {x} ** {n})"
    return _rebench(o)


def _amp_gain(o, host_id, x):
    """实测「鼓包挂在 host_id 上」时，x 的相对扰动传到最终输出的增益。

    做法：在 x 的一个 δ 相对扰动下，比较有/无鼓包两版输出的相对变化，
    即 gain = d(normalized_response)/d(delta)。用它挑承载边，而不是猜拓扑。
    """
    base = dict(zip(o["controllable_inputs"], o["baseline"]))
    x0 = base[x]
    eps = 0.03
    u = dict(zip(o["controllable_inputs"], [0.0] * len(o["controllable_inputs"])))
    u[x] = eps
    r0 = runtime_dag.normalized_response(o, dict(zip(o["controllable_inputs"],
                                                     [0.0] * len(o["controllable_inputs"]))))[o["designated_outputs"][0]]
    r1 = runtime_dag.normalized_response(o, u)[o["designated_outputs"][0]]
    return abs(r1 - r0) / eps


def local_mutate(src, k):
    """局部扰动容易通过（PDF L1002：在输入域某个子区间产生较大响应差异）。

    五条硬约束，每条都是本轮实测打出来的：
      1. 自变量必须是该边函数里**直接出现**的外部输入（中间变量做自变量时，
         采样点由外部 u 间接决定，鼓包常落在网格之间）；
      2. 鼓包必须乘在**响应相对量**上 out*(1+bump)，加在上游边会被下游按比例压缩；
      3. 鼓包中心必须落在干预区间内且贴近采样网格（中心放在 u=cen 而自变量是
         绝对量时，鼓包落在 x0*(1+cen)，几乎贴边界，采不到峰）；
      4. 宽度要覆盖最近采样间隔，否则薄壳反例要靠加密网格才抓得到；
      5. **承载边要按「到输出的传递增益」选**，不能只看是不是外部输入：
         P4 的 v2 同时出现在 e1（分子）与 e2（分母），而 e5=v3/v5 又把
         e1 的鼓包除掉了 —— 实测 Δr 只有 0.0002（被完全抵消）。
         做法：对每个候选承载边实测增益，取增益最大的那条。
    """
    PRESETS = [(0.45, 0.10, 0.10), (0.40, 0.06, 0.08), (0.50, 0.16, 0.12),
               (0.55, 0.12, 0.10), (0.42, 0.08, 0.09), (0.48, 0.14, 0.11)]
    ins_set = set(src["controllable_inputs"])

    # 候选承载边 = 函数里直接含外部输入的边
    cands = []
    for e in src["edges"]:
        for n in e["input_nodes"]:
            if n in ins_set and re.search(r"\b" + re.escape(n) + r"\b", e["function"]):
                cands.append((e["edge_id"], n))
    if not cands:
        raise ValueError(f"{src['object_id']}: 没有含外部输入的边")

    # 末端是饱和边时，上游扰动会被 (K+z) 分母压平（实测 P6 只有 0.09~0.17 < 0.2236）。
    # 此时只能把鼓包包在**末端边之内**：sat(z) * (1+bump)。
    # 该边没有外部输入直接出现，自变量取「离它最近的可观测外部输入」（沿上游回溯）。
    out_id0 = src["designated_outputs"][0]
    out_edge0 = next(e for e in src["edges"] if out_id0 in e["output_nodes"])
    if out_edge0["edge_type"] == "saturation_response":
        producer = {n: e for e in src["edges"] for n in e["output_nodes"]}
        frontier, seen, xf = list(out_edge0["input_nodes"]), set(), None
        while frontier and xf is None:
            n = frontier.pop(0)
            if n in ins_set:
                xf = n
                break
            if n in producer and n not in seen:
                seen.add(n)
                frontier += list(producer[n]["input_nodes"])
        if xf is None:
            raise ValueError(f"{src['object_id']}: 饱和末端上游找不到可观测外部输入")
        cands = [(out_edge0["edge_id"], xf)]

    # 按实测增益排序（增益大的才是好承载边）
    gains = {p: _amp_gain(src, p[0], p[1]) for p in cands}
    scored = sorted(cands, key=lambda p: -gains[p])
    gmax = gains[scored[0]]
    good = [p for p in scored if gains[p] >= 0.5 * gmax] if gmax > 0 else scored
    # 只在 good 里轮换会重复：P4 的 e1/e2 增益相近但 e1 的鼓包被 e5=v3/v5 抵消，
    # 实际 Δr 只有 0.0002。⇒ good 里要靠**实测 Δr** 二次筛选，而不是靠增益排序。
    # k 解释成 (承载边, 预设) 的联合序号：保证不同 k 产出不同的组合，
    # 而不是在 good 里循环回同一组边
    ci_ = k % (len(good) * len(PRESETS))
    host_id, x = good[ci_ // len(PRESETS)]
    amp, cen, wid = PRESETS[ci_ % len(PRESETS)]

    o = json.loads(json.dumps(src))
    out_id = o["designated_outputs"][0]
    host = next(e for e in o["edges"] if e["edge_id"] == host_id)
    lo, hi = o["intervention_bounds"][x]
    u_c = min(max(cen, lo + 0.6 * wid), hi - 0.6 * wid)
    x0 = o["baseline"][o["controllable_inputs"].index(x)]
    if abs(x0) < 1e-12:
        x0 = 1.0
    bump = (f"{amp} * (exp(-(((({x} - {x0}) / {x0}) - {u_c}) / {wid}) ** 2) "
            f"- exp(-(({u_c}) / {wid}) ** 2))")
    host["function"] = f"({host['function']}) * (1 + {bump})"
    # 若承载边函数里没有 x 这个节点（饱和末端：只吃中间变量），
    # 必须把 x 加成该边的显式输入节点，否则求值器找不到变量（实测 KeyError）。
    if x not in host["input_nodes"]:
        host["input_nodes"].append(x)
        host["roles"][x] = "input" if host["edge_type"] == "saturation_response" else "ratio"
    y = runtime_dag.evaluate_dag(o, dict(zip(o["controllable_inputs"], o["baseline"])))[out_id]
    if not math.isfinite(y) or y == 0:
        raise ValueError(f"{o['object_id']}: 局部扰动后基准输出非法 {y}")
    o["baseline_output"] = y
    o["output_scale"] = y
    o["function"] = expand_to_expression(o["edges"], out_id)
    # 自检：鼓包必须在协议采样点上真的产生超容差差异，否则这不是干扰源
    # （P4 的 e1 承载位实测 Δr=0.0002：鼓包在分子，被 e5=v3/v5 除掉了）
    pts = scan_points(o, n=800)
    mx = 0.0
    for u in pts:
        d = abs(runtime_dag.normalized_response(o, u)[out_id] -
                runtime_dag.normalized_response(src, u)[out_id])
        if d > mx:
            mx = d
            if mx > ERR_THRESHOLD:
                break
    if mx <= ERR_THRESHOLD:
        raise ValueError(f"{src['object_id']}: 局部扰动 Δr={mx:.4f} 未超容差（承载边 {host_id} 无效）")
    return o


# ==================================================================
# 组装：30 组的原型/家族调度
# ==================================================================
# 6 个原型 × 5 个家族组合 = 30 组。家族组合按 L993 三类关系的合法搭配：
#   乘性 M / 线性 L / 饱和 S(只能作末端)
# 每种组合在不同原型上出现，避免「一族一形状」（v1.1 结构×家族矩阵 14/15 非空，
# 但饱和族只出现在 2 个形状里；v2 让饱和族在 3 个原型上以末端身份出现）。
FAM_COMBOS = [
    ("M-L-M", ["multiplicative_growth", "linear_drive_resistance", "multiplicative_growth"]),
    ("L-M-L", ["linear_drive_resistance", "multiplicative_growth", "linear_drive_resistance"]),
    ("M-M-L", ["multiplicative_growth", "multiplicative_growth", "linear_drive_resistance"]),
    ("L-L-M", ["linear_drive_resistance", "linear_drive_resistance", "multiplicative_growth"]),
    ("M-...-S", None),   # 饱和末端，按原型长度展开
]


def proto_families(proto, combo_name, combo, ups=None):
    """把家族组合按原型边数展开；饱和组合强制放在末端。"""
    n = len(proto["edges"])
    if combo is None:      # 饱和末端
        base = ups or ["multiplicative_growth", "linear_drive_resistance"]
        fams = [base[i % len(base)] for i in range(n - 1)] + ["saturation_response"]
        return fams
    return [combo[i % len(combo)] for i in range(n)]


def make_proto(idx, proto_fn, combo_name, combo, ups=None):
    """按 (原型, 家族组合) 实例化一个 proto 定义。

    P6 的骨架末端是饱和边（单输入）。若本组家族组合不含饱和，
    把末端边改成两输入的线性边并补一个外部输入 x5，保持 5 边 / 9 节点不变：
      e5: y = linear(z3, x5)   -> 节点 z3, y, x5 已在图内，V 不变
    """
    p = proto_fn()
    p["families"] = proto_families(p, combo_name, combo, ups)
    # 末端边与家族必须「阶数一致」：
    #   饱和是单输入 ⇒ 末端边只能接 1 个节点
    #   乘性/线性是两输入 ⇒ 末端边必须接 2 个节点
    # 两种方向都要修，且修完重算外部输入清单（被移出的输入不再被任何边消费）。
    last_ins, last_out = p["edges"][-1]
    if p["families"][-1] == "saturation_response" and len(last_ins) != 1:
        p["edges"] = p["edges"][:-1] + [([last_ins[0]], last_out)]
    elif (p["families"][-1] != "saturation_response" and len(last_ins) != 2):
        # P6 骨架末端是 sat(z3)；改成二元边时补一个尚未使用的 x5
        pool = ["x5", "x6", "x7"]
        used = {n for ins, o in p["edges"][:-1] for n in ins}
        extra = next(x for x in pool if x not in used and x not in p["inputs"])
        p["edges"] = p["edges"][:-1] + [([last_ins[0], extra], last_out)]
    used = {n for ins, o in p["edges"] for n in ins}
    p["inputs"] = [n for n in (p["inputs"] + ["x5", "x6", "x7"]) if n in used]
    # 保持原输入顺序：按 x1..xN 排序
    p["inputs"] = sorted(set(p["inputs"]), key=lambda t: int(t[1:]))
    return p


PROTOS = [
    ("P1_deep_chain3", P1_deep_chain3),
    ("P2_chain_merge", P2_chain_merge),
    ("P3_shared_fan", P3_shared_fan),
    ("P4_shared_deep", P4_shared_deep),
    ("P5_three_way_merge", P5_three_way_merge),
    ("P6_sat_tail_chain", P6_sat_tail_chain),
]


def group_plan():
    """30 组 = 6 原型 × 5 家族组合，但**按原型结构能力分配**，不是硬凑方阵：

    P6_sat_tail_chain 的骨架就是「深链 + 饱和末端」，它的末端边天然是单输入；
    若把非饱和组合塞进去，末端要补成两输入 3 节点，节点数涨到 10，超出 9 上限。
    ⇒ P6 只承担饱和末端组合（它是 6 个原型里深度最大的，饱和末端只在这里试）。

    配额：
      P1_deep_chain3     5 组（4 个二元组合 + 1 个饱和末端；末端降级为单输入、V=6）
      P2_chain_merge     5 组（4 + 1 饱和末端）
      P3_shared_fan      5 组（4 + 1）
      P4_shared_deep     5 组（4 + 1）
      P5_three_way_merge 5 组（4 + 1）
      P6_sat_tail_chain  5 组（饱和末端 × 5 种混合，用不同家族搭配末端上游）
    合计 30，其中饱和末端 6 组（每个原型各有 1 组），其余 24 组为二元组合。
    """
    combos = [d for d in FAM_COMBOS]
    out = []
    for pname, pfn in PROTOS:
        if pname == "P6_sat_tail_chain":
            # 5 组都用饱和末端，但上游家族交替，产生不同机制组合
            ups = [
                ["multiplicative_growth", "linear_drive_resistance"],
                ["linear_drive_resistance", "multiplicative_growth"],
                ["multiplicative_growth", "multiplicative_growth"],
                ["linear_drive_resistance", "linear_drive_resistance"],
                ["multiplicative_growth", "linear_drive_resistance"],
            ]
            for ui, up in enumerate(ups):
                out.append(dict(proto_name=pname, proto_fn=pfn,
                                combo_name=f"S{ui}", combo=None, ups=up))
            continue
        for cname, combo in combos:
            out.append(dict(proto_name=pname, proto_fn=pfn,
                            combo_name=cname, combo=combo, ups=None))
    # 交错：按 (组合序, 原型序) 排，避免同原型连号
    order_c = [c[0] for c in FAM_COMBOS]
    out.sort(key=lambda d: (order_c.index(d["combo_name"]) if d["combo_name"] in order_c else 4,
                            [p[0] for p in PROTOS].index(d["proto_name"])))
    return out


def scale_pool(i):
    """源域参数倍率池：必须是真实可见量级（10 倍以内），不是任意数。"""
    return [1.7, 2.5, 0.6, 3.4, 1.25, 0.8, 2.0][i % 7]


def build_groups():
    """构造 30 个基础组：目标域 + 参数不同的同构有效源域。"""
    groups = []
    for gi, plan in enumerate(group_plan()):
        gid = f"group_v2_{gi:04d}"
        proto = make_proto(gi, plan["proto_fn"], plan["combo_name"], plan["combo"],
                           plan.get("ups"))
        im = assign_ids(proto, gid)
        ratio0 = BASE["multiplicative_growth"]["ratio"]
        tgt = build_object(gid, proto, im, scale=1.0, tag="tgt")
        src = build_object(gid, proto, im, scale=scale_pool(gi), tag="src",
                           ratio_align=ratio0, param_jitter=0.12)
        # 有效源必须至少保留一个有效映射（同构 + 参数不同即成立，但要求实测）
        groups.append(dict(group_id=gid, proto=proto, id_map=im, tgt=tgt, src=src,
                           proto_name=plan["proto_name"], combo_name=plan["combo_name"]))
    return groups


def full_pool_check(pool, tgt, points, label=""):
    """PDF L1008 全库排除：对池里**每个**源对象枚举全部允许映射并逐一验证响应。

    这是「不能只验证预先指定的错误候选」的落地——枚举范围是整个
    (节点双射 × 超边双射) 空间，不是我们以为的那个错误映射。
    返回 {object_id: [有效映射...]}；非空即该对象其实可用（会污染负任务）。
    """
    out = {}
    for o in pool:
        vs = valid_mappings(o, tgt, points=points)
        if vs:
            out[o["object_id"]] = vs
    return out


def build_candidates(g, points=None, verbose=False):
    """构造一组 10 个候选并核验正负任务（PDF L1006/L1008）。

    正任务池 = 1 有效源 + 3 结构错误 + 3 响应错误 + 3 局部扰动
    负任务池 = 上述 9 个干扰源 + 1 个额外的响应错误（总数仍为 10）
    """
    gid, tgt, src = g["group_id"], g["tgt"], g["src"]
    pts = points if points is not None else scan_points(tgt)

    def take_unique(gen, kind, prefix, n=3):
        """挑出运行时真的被判负的干扰源，且两两不同（按函数/拓扑签名去重）。"""
        got, sigs = [], set()
        for k in range(24):
            try:
                cand = next(gen(k))
            except StopIteration:
                continue
            except ValueError:
                continue      # 该 k 的变异不成立（如局部扰动采不到峰），换下一个
            sig = json.dumps([cand["function"],
                              [e["function"] for e in cand["edges"]],
                              [[e["edge_id"], e["input_nodes"], e["output_nodes"]]
                               for e in cand["edges"]]], sort_keys=True)
            if sig in sigs:
                continue
            if valid_mappings(cand, tgt, points=pts):
                continue          # 有有效映射 => 不是干扰源
            sigs.add(sig)
            cand = dict(cand)
            cand["_kind"] = kind
            cand["object_id"] = f"obj_{gid}_{prefix}{len(got):02d}"
            got.append(cand)
            if len(got) == n:
                break
        if len(got) < n:
            raise AssertionError(f"{gid}: {kind} 只凑到 {len(got)}/{n} 个真干扰源")
        return got

    struct3 = take_unique(lambda k: structural_mutate(src, k, g["id_map"]),
                          "structure_error", "s")
    resp3 = take_unique(lambda k: iter([resp_mutate(src, k)]), "response_error", "r")
    loc3 = take_unique(lambda k: iter([local_mutate(src, k)]), "local_perturbation", "l")

    # 第 10 个：负任务专用，再一个响应错误（与 resp3 不同的边/族）
    extra = None
    for k in range(3, 12):
        c = resp_mutate(src, k)
        if not valid_mappings(c, tgt, points=pts):
            c = dict(c)
            c["_kind"] = "response_error"
            c["object_id"] = f"obj_{gid}_x00"
            extra = c
            break
    if extra is None:
        # 响应族用尽时退回结构错误（仍必须是运行时真判负的）
        for k in range(3, 10):
            try:
                c = next(structural_mutate(src, k, g["id_map"]))
            except StopIteration:
                continue
            if not valid_mappings(c, tgt, points=pts):
                c = dict(c)
                c["_kind"] = "structure_error"
                c["object_id"] = f"obj_{gid}_x00"
                extra = c
                break
    assert extra is not None, f"{gid} 负任务凑不到第 10 个干扰源"

    # 有效源：同构 + 参数不同，必须实测存在有效映射（PDF L986 存集合）
    valid_src = json.loads(json.dumps(src))
    valid_src["object_id"] = f"obj_{gid}_src"
    valid_src["_kind"] = "valid"
    valid_maps = valid_mappings(valid_src, tgt, points=pts)
    assert valid_maps, f"{gid} 有效源没有任何有效映射"

    pos_pool = [valid_src] + struct3 + resp3 + loc3
    neg_pool = struct3 + resp3 + loc3 + [extra]
    assert len(pos_pool) == 10 and len(neg_pool) == 10, (len(pos_pool), len(neg_pool))
    if verbose:
        print(f"  {gid} 正池 {len(pos_pool)} 负池 {len(neg_pool)} 有效映射 {len(valid_maps)}")
    return dict(pos=pos_pool, neg=neg_pool, valid_maps=valid_maps)



def G_struct_gen(src, k, id_map):
    """structural_mutate 的生成器包装（逐个尝试三种变异直到运行时真判负）。"""
    return structural_mutate(src, k, id_map)


# ==================================================================
# 划分（PDF L1020：70/15/15，种子 20261007，同组派生不跨划分）
# ==================================================================
def assign_splits(groups):
    """按基础组划分：一组 = 目标 + 全部候选 + 两个任务，整体不可分。"""
    ids = [g["group_id"] for g in groups]
    rng = random.Random(SPLIT_SEED)
    order = ids[:]
    rng.shuffle(order)
    n = len(order)
    n_tr = round(0.70 * n)
    n_va = round(0.15 * n)
    tr, va = order[:n_tr], order[n_tr:n_tr + n_va]
    te = order[n_tr + n_va:]
    mp = {}
    for gid in tr:
        mp[gid] = "train"
    for gid in va:
        mp[gid] = "val"
    for gid in te:
        mp[gid] = "test"
    return mp, dict(train=len(tr), val=len(va), test=len(te))


# ==================================================================
# 封存干预点（PDF L1024：每个测试任务 100 个独立合法干预点）
# ==================================================================
def make_intervention_points(tgt, task_id, n=100):
    """独立随机种子生成 100 个合法干预点；排除固定初始化点（全 0）。"""
    rng = random.Random(seeded(INTERVENTION_SEED, task_id))
    ins = tgt["controllable_inputs"]
    pts, seen = [], set()
    tries = 0
    while len(pts) < n and tries < n * 200:
        tries += 1
        u = {}
        for nid in ins:
            lo, hi = tgt["intervention_bounds"][nid]
            u[nid] = round(rng.uniform(lo, hi), 4)
        if all(abs(v) < 1e-12 for v in u.values()):
            continue                       # 排除固定初始化点
        key = tuple(sorted(u.items()))
        if key in seen:
            continue
        try:
            runtime_dag.normalized_response(tgt, u)
        except Exception:
            continue
        seen.add(key)
        pts.append(u)
    if len(pts) < n:
        raise AssertionError(f"{task_id}: 只生成 {len(pts)}/{n} 个合法干预点")
    return pts


# ==================================================================
# 落盘
# ==================================================================
REASON = dict(
    structure_error="结构不成立：标注与算式不符，或图连接与目标不同（eq:structure 不成立）",
    response_error="结构成立但归一化响应超出参考容差",
    local_perturbation="结构成立，仅在输入域某子区间超出参考容差",
)


def public(o):
    return {k: v for k, v in o.items() if not k.startswith("_")}


def write_group(g, cands, split, out_root):
    gid, tgt = g["group_id"], g["tgt"]
    gdir = out_root / gid
    (gdir / "data" / "input" / "objects").mkdir(parents=True, exist_ok=True)
    (gdir / "data" / "input" / "tasks").mkdir(parents=True, exist_ok=True)
    (gdir / "sealed").mkdir(parents=True, exist_ok=True)

    pos, neg = cands["pos"], cands["neg"]
    uniq = {}
    for o in [tgt] + pos + neg:
        uniq.setdefault(o["object_id"], o)
    allobjs = list(uniq.values())
    for o in allobjs:
        o = dict(o)
        o["split"] = split
        (gdir / "data" / "input" / "objects" / f"{o['object_id']}.json").write_text(
            json.dumps(public(o), ensure_ascii=False, indent=1), encoding="utf-8")

    tids = []
    for tag, pool in (("t01", pos), ("t02", neg)):
        tid = f"task_{gid}_{tag}"
        tids.append(tid)
        src_ids = [o["object_id"] for o in pool]
        random.Random(seeded(gid, tid)).shuffle(src_ids)   # 打乱顺序，不泄露有效源位置
        task = dict(
            task_id=tid, group_id=gid,
            target_id=tgt["object_id"],
            source_ids=src_ids,
            schema_version=SCHEMA_VERSION,
            vocab_version=VOCAB_VERSION,
            intervenable_inputs=tgt["controllable_inputs"],
            specified_outputs=tgt["designated_outputs"],
            intervention_range=tgt["intervention_bounds"],
        )
        (gdir / "data" / "input" / "tasks" / f"{tid}.json").write_text(
            json.dumps(task, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- sealed/reference.json（仅评价器可读）----
    ref = {}
    gtid = tids[0]
    valid = [dict(source_id=f"obj_{gid}_src", node_map=m["node_map"],
                  edge_map=m["edge_map"], max_abs_diff=m["max_abs_diff"])
             for m in cands["valid_maps"]]
    pts = scan_points(tgt)
    identity = {n: n for n in tgt["controllable_inputs"]}

    def make_excl(o):
        mx, worst, _ = max_gap_for_map(o, tgt, identity, points=pts, limit=1e9)
        return dict(source_id=o["object_id"], kind=o.get("_kind", "unknown"),
                    reason=REASON.get(o.get("_kind"), ""),
                    witness=dict(u=worst, max_abs_diff=mx,
                                 exceeds_tolerance=mx > ERR_THRESHOLD))

    excls = [make_excl(o) for o in pos if o["object_id"] != f"obj_{gid}_src"]
    ref[gtid] = dict(task_id=gtid, label="positive", valid=valid, exclusions=excls,
                     candidate_ids=[o["object_id"] for o in pos],
                     full_library_verified=True)

    ntid = tids[1]
    nex = [make_excl(o) for o in neg]
    ref[ntid] = dict(task_id=ntid, label="negative", valid=[], exclusions=nex,
                     candidate_ids=[o["object_id"] for o in neg],
                     full_library_verified=True,
                     enum_basis="节点双射 x 超边双射全空间枚举 + 固定采样协议响应验证")
    (gdir / "sealed" / "reference.json").write_text(
        json.dumps(ref, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- 干预点：仅测试组（PDF L1024）----
    if split == "test":
        ipts = {tid: make_intervention_points(tgt, tid) for tid in tids}
        (gdir / "sealed" / "intervention_points.json").write_text(
            json.dumps(dict(group_id=gid, seed=INTERVENTION_SEED, points_per_task=100,
                            tasks=ipts), ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- manifest.json（公开）----
    man = dict(
        group_id=gid, dataset="mred_v2",
        schema_version=SCHEMA_VERSION, vocab_version=VOCAB_VERSION,
        split=split,
        target_id=tgt["object_id"],
        object_ids=[o["object_id"] for o in allobjs],
        task_ids=tids,
        n_nodes=len(tgt["nodes"]),
        n_edges=len(tgt["edges"]),
        max_depth=runtime_dag.dependency_depth(tgt),
        n_inputs=len(tgt["controllable_inputs"]),
        has_shared_node=bool(runtime_dag.shared_nodes(tgt)),
    )
    (gdir / "manifest.json").write_text(
        json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- manifest.sealed.json（结构类别与家族只在封存侧）----
    sealed = dict(
        group_id=gid,
        proto=g["proto_name"],
        family_combo=g["combo_name"],
        edge_families=[e["edge_type"] for e in tgt["edges"]],
        seed=SEED,
        reference_tolerance=dict(min_ctc=MIN_CTC, max_error=MAX_ERROR,
                                 err_threshold=ERR_THRESHOLD),
    )
    (gdir / "manifest.sealed.json").write_text(
        json.dumps(sealed, ensure_ascii=False, indent=1), encoding="utf-8")


def dry_run(groups):
    """全量验算：构造候选 + 全库枚举排除，不写盘。"""
    rows = []
    for g in groups:
        tgt = g["tgt"]
        pts = scan_points(tgt)
        cands = build_candidates(g)
        pos_hit = full_pool_check(cands["pos"], tgt, pts)
        neg_hit = full_pool_check(cands["neg"], tgt, pts)
        identity = {n: n for n in tgt["controllable_inputs"]}

        def gap(o):
            return max_gap_for_map(o, tgt, identity, points=pts, limit=1e9)[0]

        rows.append(dict(
            group=g, cands=cands,
            ok_pos=list(pos_hit) == [f"obj_{g['group_id']}_src"],
            ok_neg=len(neg_hit) == 0,
            gaps=dict(struct=[gap(o) for o in cands["pos"][1:4]],
                      resp=[gap(o) for o in cands["pos"][4:7]],
                      loc=[gap(o) for o in cands["pos"][7:10]]),
            n_valid=len(cands["valid_maps"]),
        ))
    return rows


def main():
    import time as _t
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="全量验算，不落盘")
    ap.add_argument("--out", default=str(OUT_DIR))
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 组（调试）")
    args = ap.parse_args()

    groups = build_groups()
    if args.limit:
        groups = groups[: args.limit]
    print(f"构造 {len(groups)} 组 / {len(groups) * 2} 任务")

    t0 = _t.time()
    rows = dry_run(groups)
    dt = _t.time() - t0
    nbad = sum(1 for r in rows if not (r["ok_pos"] and r["ok_neg"]))
    print(f"\n全库枚举排除核验：{len(rows) - nbad}/{len(rows)} 组通过（{dt:.0f}s）")
    for r in rows:
        g, tgt = r["group"], r["group"]["tgt"]
        print(f"  {g['group_id']} {g['proto_name'][:18]:18s} "
              f"V={len(tgt['nodes'])} E={len(tgt['edges'])} "
              f"深={runtime_dag.dependency_depth(tgt)} "
              f"正={'OK' if r['ok_pos'] else 'BAD'} 负={'OK' if r['ok_neg'] else 'BAD'} "
              f"有效={r['n_valid']} 结构Δ={min(r['gaps']['struct']):.3f} "
              f"响应Δ={min(r['gaps']['resp']):.3f} 局部Δ={min(r['gaps']['loc']):.3f}")
    if nbad:
        print(f"\n!! {nbad} 组未通过，不落盘")
        return 1

    if args.dry:
        print("\ndry 模式：不落盘")
        return 0

    mp, cnt = assign_splits(groups)
    print(f"\n划分 train/val/test = {cnt['train']}/{cnt['val']}/{cnt['test']}")
    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)
    for r in rows:
        write_group(r["group"], r["cands"], mp[r["group"]["group_id"]], out_root)
    print(f"已写出 {len(rows)} 组到 {out_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
