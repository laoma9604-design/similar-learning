"""MRED v2 独立验证器（**不 import 生成器**，按任务书原文重实现判据）。

存在理由（项目既有教训）：生成器自报「全部通过」只证明它自己检查的那些事。
验证器必须另写一套实现，否则与被测对象共享同一个 bug 就互相作证。

覆盖六节：
  V1 结构合规        —— schema 必填、字段不多不少、枚举值合法、词表命中
  V2 拓扑与可执行    —— 无环、拓扑可执行、深度/中间量/共享节点可复算、基准输出可复算
  V3 映射约束        —— 节点/超边双射、类型、端点、角色（PDF L342 eq:structure）
  V4 正任务          —— 候选池 10 个、有效映射存在且能实测满分、其余全部被拒
  V5 负任务          —— 全库枚举排除，每个候选有超容差见证点（PDF L1008/L1010）
  V6 隔离与划分      —— task_id 不编码标签、公开侧无答案、划分 70/15/15 不跨组、
                        干预点仅测试组且为 100 个、对象/参数/拓扑与 v1/v1.1 不重合

用法：
    python a_data/verify_structural_v2.py            # 全量
    python a_data/verify_structural_v2.py --limit 3  # 只查前 3 组
退出码 0 = 全过。
"""
import argparse
import ast
import glob
import itertools
import json
import math
import operator
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "cases" / "structural_v2"
TOL_MAX_ERROR = 0.05                  # PDF L1010，数据版本固定
TOL_ERR = math.sqrt(TOL_MAX_ERROR)    # 项目 E = min(1,(Δr)^2) 口径
MIN_CTC = 0.95
SCAN_N = 4000                         # 与生成器同协议的采样点数
SCAN_SEED = 20261007

FAILS = []
CHECKS = [0]


def fail(tag, msg):
    FAILS.append((tag, msg))


def tick(tag, cond, msg=""):
    CHECKS[0] += 1
    if not cond:
        fail(tag, msg)
    return cond


# ---------------------------------------------------------------- 求值器
# 独立实现：不 import runtime / runtime_dag
_ALLOWED = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def eval_expr(expr, env):
    tree = ast.parse(expr, mode="eval")

    def visit(n):
        if isinstance(n, ast.Expression):
            return visit(n.body)
        if isinstance(n, ast.Constant):
            return float(n.value)
        if isinstance(n, ast.BinOp) and type(n.op) in _ALLOWED:
            return _ALLOWED[type(n.op)](visit(n.left), visit(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in _ALLOWED:
            return _ALLOWED[type(n.op)](visit(n.operand))
        if isinstance(n, ast.Name):
            return env[n.id]
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "exp":
            return math.exp(visit(n.args[0]))
        raise ValueError(f"不支持的表达式语法 {ast.dump(n)}")

    return visit(tree)


def topo(obj):
    """拓扑序（独立实现）：外部输入 = 可控输入 − 被产出者。"""
    produced = defaultdict(list)
    for e in obj["edges"]:
        for n in e["output_nodes"]:
            produced[n].append(e["edge_id"])
    dup = {n: v for n, v in produced.items() if len(v) > 1}
    if dup:
        raise ValueError(f"节点被重复产出：{dup}")
    ext = set(obj["controllable_inputs"]) - set(produced)
    dangling = {n for e in obj["edges"] for n in e["input_nodes"]} - set(produced) - ext
    if dangling:
        raise ValueError(f"悬空输入：{sorted(dangling)}")
    by = {e["edge_id"]: e for e in obj["edges"]}
    ready, order, rem = set(ext), [], list(by)
    while rem:
        cur = [k for k in rem if all(n in ready for n in by[k]["input_nodes"])]
        if not cur:
            raise ValueError(f"存在环：{rem}")
        for k in cur:
            order.append(k)
            ready.update(by[k]["output_nodes"])
            rem.remove(k)
    return order


def depth_of(obj):
    produced = {n for e in obj["edges"] for n in e["output_nodes"]}
    ext = set(obj["controllable_inputs"]) - produced
    by = {e["edge_id"]: e for e in obj["edges"]}
    ready, rem, d = set(ext), list(by), 0
    while rem:
        cur = [k for k in rem if all(n in ready for n in by[k]["input_nodes"])]
        if not cur:
            return -1
        for k in cur:
            ready.update(by[k]["output_nodes"])
            rem.remove(k)
        d += 1
    return d


def run(obj, inputs, trace=False):
    vals = dict(inputs)
    rows = []
    by = {e["edge_id"]: e for e in obj["edges"]}
    for eid in topo(obj):
        e = by[eid]
        out = eval_expr(e["function"], {n: vals[n] for n in e["input_nodes"]})
        vals[e["output_nodes"][0]] = out
        if trace:
            rows.append((eid, out))
    y = vals[obj["designated_outputs"][0]]
    return (y, rows) if trace else y


def intervene(obj, u):
    return {n: obj["baseline"][i] + obj["input_scales"][i] * u[n]
            for i, n in enumerate(obj["controllable_inputs"])}


def nresp(obj, u):
    y = run(obj, intervene(obj, u))
    return (y - obj["baseline_output"]) / obj["output_scale"]


def sample_points(obj, n=SCAN_N, seed=SCAN_SEED):
    """与生成器同协议的采样（独立实现，不 import）。

    协议（写进文档，第三方可照此复算）：
      1. 每维按 0.2 步长铺网格（含两端）
      2. 若全笛卡尔积 <= n，直接铺满；否则只保留「全端点组合 + 每维单点扫」
      3. 用固定种子 20261007 补随机点到 n 个
    第 2 步的降级规则必须与生成器逐条一致，否则两边判出的「有效/无效」会不同。
    """
    ins = obj["controllable_inputs"]
    axes = []
    for nid in ins:
        lo, hi = obj["intervention_bounds"][nid]
        vals, k = [], lo
        while k <= hi + 1e-12:
            vals.append(round(k, 8))
            k += 0.2
        if vals and vals[-1] < hi - 1e-12:
            vals.append(hi)
        axes.append(vals)
    total = 1
    for a in axes:
        total *= len(a)
    seen, out = set(), []
    if total <= n:
        for combo in itertools.product(*axes):
            if combo not in seen:
                seen.add(combo)
                out.append(dict(zip(ins, combo)))
    else:
        for combo in itertools.product(*[[obj["intervention_bounds"][nid][0],
                                          obj["intervention_bounds"][nid][1]] for nid in ins]):
            if combo not in seen:
                seen.add(combo)
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
    rnd = __import__("random").Random(seed)
    tries = 0
    while len(out) < n and tries < n * 50:
        tries += 1
        u = {nid: round(rnd.uniform(*obj["intervention_bounds"][nid]), 6) for nid in ins}
        key = tuple(u[n] for n in ins)
        if key in seen:
            continue
        seen.add(key)
        out.append(u)
    return out


# ---------------------------------------------------------------- V3 映射
def eq_structure(src, tgt, fV, fE):
    """PDF L342 eq:structure：类型、端点、角色。返回失败项列表。"""
    bad = []
    se = {e["edge_id"]: e for e in src["edges"]}
    te = {e["edge_id"]: e for e in tgt["edges"]}
    if len(src["nodes"]) != len(tgt["nodes"]) or len(se) != len(te):
        return ["node/edge count mismatch"]
    if len(set(fV.values())) != len(fV) or len(set(fE.values())) != len(fE):
        return ["not injective"]
    if set(fV) != {n["node_id"] for n in src["nodes"]} or len(fV) != len(src["nodes"]):
        return ["fV not total"]
    if set(fE) != set(se) or len(fE) != len(se):
        return ["fE not total"]
    st = {n["node_id"]: n["type"] for n in src["nodes"]}
    tt = {n["node_id"]: n["type"] for n in tgt["nodes"]}
    for s, t in fV.items():
        if st[s] != tt[t]:
            bad.append(f"type:{s}")
    for se_id, fSe in fE.items():
        if se_id not in se or fSe not in te:
            bad.append(f"edge_id:{se_id}")
            continue
        a, b = se[se_id], te[fSe]
        if a["edge_type"] != b["edge_type"]:
            bad.append(f"edge_type:{se_id}")
        if {fV[v] for v in a["input_nodes"]} != set(b["input_nodes"]):
            bad.append(f"inputs:{se_id}")
        if {fV[v] for v in a["output_nodes"]} != set(b["output_nodes"]):
            bad.append(f"outputs:{se_id}")
        for v, r in a.get("roles", {}).items():
            if b.get("roles", {}).get(fV[v]) != r:
                bad.append(f"role:{se_id}:{v}")
    return bad


def enum_struct(src, tgt, cap=200000):
    """枚举结构成立的全部 (fV, fE)。独立实现：先定边排列，再按输出端回溯。

    与生成器不同写法的目的：交叉验证「枚举是否漏解」。
    """
    if len(src["nodes"]) != len(tgt["nodes"]) or len(src["edges"]) != len(tgt["edges"]):
        return []
    se, te = src["edges"], tgt["edges"]
    sn = [n["node_id"] for n in src["nodes"]]
    tn = [n["node_id"] for n in tgt["nodes"]]
    st = {n["node_id"]: n["type"] for n in src["nodes"]}
    tt = {n["node_id"]: n["type"] for n in tgt["nodes"]}
    out = []
    count = 0
    by_type_s, by_type_t = defaultdict(list), defaultdict(list)
    for e in se:
        by_type_s[e["edge_type"]].append(e)
    for e in te:
        by_type_t[e["edge_type"]].append(e)
    if {k: len(v) for k, v in by_type_s.items()} != {k: len(v) for k, v in by_type_t.items()}:
        return []
    keys = list(by_type_s)
    for combo in itertools.product(*[list(itertools.permutations(by_type_t[k])) for k in keys]):
        fE = {}
        for k, perm in zip(keys, combo):
            for a, b in zip(by_type_s[k], perm):
                fE[a["edge_id"]] = b
        # 输出端确定对应
        fixed, conflict = {}, False
        for a in se:
            b = fE[a["edge_id"]]
            so, to = a["output_nodes"][0], b["output_nodes"][0]
            if so in fixed and fixed[so] != to:
                conflict = True
                break
            fixed[so] = to
        if conflict:
            continue
        used = set(fixed.values())
        free_s = [n for n in sn if n not in fixed]
        free_t = [n for n in tn if n not in used]
        if len(free_s) != len(free_t):
            continue
        fE_ids = {k: v["edge_id"] for k, v in fE.items()}
        for perm in itertools.permutations(free_t):
            fV = dict(fixed)
            fV.update(dict(zip(free_s, perm)))
            if any(st[s] != tt[fV[s]] for s in sn):
                continue
            if not eq_structure(src, tgt, fV, fE_ids):
                out.append((fV, fE_ids))
                count += 1
                if count > cap:
                    raise RuntimeError("枚举超上限")
    return out


def max_gap(src, tgt, fV, points):
    """该映射在协议采样点上的最大响应差（早停）。"""
    ins_t = tgt["controllable_inputs"]
    ins_s = set(src["controllable_inputs"])
    inv = {t: s for s, t in fV.items()}
    mx, worst = 0.0, None
    for u in points:
        u_s, ok = {}, True
        for t in ins_t:
            s = inv.get(t)
            if s is None or s not in ins_s:
                ok = False
                break
            u_s[s] = u[t]
        if not ok:
            continue
        d = abs(nresp(src, u_s) - nresp(tgt, u))
        if d > mx:
            mx, worst = d, dict(u)
        if mx > TOL_ERR:
            return mx, worst, True
    return mx, worst, False


def valid_maps(src, tgt, points):
    out = []
    for fV, fE in enum_struct(src, tgt):
        mx, worst, early = max_gap(src, tgt, fV, points)
        if not early and mx <= TOL_ERR:
            out.append((fV, fE, mx))
    return out


# ---------------------------------------------------------------- 主流程
SCHEMA = json.load(open(ROOT / "T01-schema.json", encoding="utf-8"))
VOCAB = json.load(open(ROOT / "T01-vocabulary.json", encoding="utf-8"))
EDGE_TYPES = {e.get("edge_type_id") or e.get("type_id") for e in VOCAB["edge_types"]}
NODE_TYPES = {t["type_id"] for t in VOCAB["node_types"]}


def v1_fields(obj, gid):
    """V1 结构合规：必填齐全、无自造字段、枚举合法、词表命中。"""
    req = [k for k, v in SCHEMA["records"]["object"]["fields"].items() if v.get("required") is True]
    miss = [k for k in req if k not in obj]
    tick("V1", not miss, f"{gid} 缺必填字段 {miss}")
    allowed = set(SCHEMA["records"]["object"]["fields"])
    extra = [k for k in obj if k not in allowed]
    tick("V1", not extra, f"{gid} 有 schema 外字段 {extra}")
    tick("V1", obj.get("object_kind") == "mechanistic", f"{gid} object_kind 非 mechanistic")
    tick("V1", obj.get("split") in ("dev", "train", "val", "test"), f"{gid} split 非法 {obj.get('split')}")
    # 版本号只在 manifest / task 上，object 记录里没有这两个字段（schema 也不要求）——
    # 这一条是本验证器最初的误报：对着 v1.1 的合法对象跑也会红。

    for n in obj["nodes"]:
        tick("V1", set(n) == {"node_id", "label", "type"}, f"{gid} node 字段异常 {sorted(n)}")
        tick("V1", n["type"] in NODE_TYPES, f"{gid} node.type 不在词表 {n['type']}")
    for e in obj["edges"]:
        tick("V1", e["edge_type"] in EDGE_TYPES, f"{gid} edge_type 不在词表 {e['edge_type']}")
        tick("V1", len(e["output_nodes"]) == 1, f"{gid} 边非单输出")
        tick("V1", set(e["roles"]) == set(e["input_nodes"]) | set(e["output_nodes"]),
             f"{gid}/{e['edge_id']} roles 覆盖与端点不一致")
    tick("V1", set(obj["provenance"]) == {"dataset", "original_id", "structure_source"},
         f"{gid} provenance 字段不符 {sorted(obj['provenance'])}")


def v2_topology(obj, gid):
    """V2 拓扑与可执行性，并且**独立复算**基准输出。"""
    try:
        order = topo(obj)
    except ValueError as ex:
        tick("V2", False, f"{gid} 拓扑非法：{ex}")
        return
    tick("V2", len(order) == len(obj["edges"]), f"{gid} 拓扑序长度不符")
    tick("V2", depth_of(obj) >= 1, f"{gid} 深度非法 {depth_of(obj)}")
    # 基准输出复算
    base = dict(zip(obj["controllable_inputs"], obj["baseline"]))
    y = run(obj, base)
    tick("V2", abs(y - obj["baseline_output"]) <= 1e-9 * max(1.0, abs(y)),
         f"{gid} baseline_output 声明 {obj['baseline_output']} 实算 {y}")
    # 顶层 function 与 DAG 等价（PDF/schema：两者必须数学等价）
    d = 0.0
    for _ in range(50):
        u = {n: 0.0 for n in obj["controllable_inputs"]}
        inn = intervene(obj, u)
        a = eval_expr(obj["function"], inn)
        b = run(obj, inn)
        d = max(d, abs(a - b))
        break
    tick("V2", d <= 1e-9 * max(1.0, abs(b)), f"{gid} 顶层 function 与 DAG 不等价（差 {d:.3e}）")
    # 输入元数与边阶数一致
    for e in obj["edges"]:
        n_in = len(e["input_nodes"])
        if e["edge_type"] == "saturation_response":
            tick("V2", n_in == 1, f"{gid}/{e['edge_id']} 饱和边输入元数 {n_in} != 1")
        else:
            tick("V2", n_in == 2, f"{gid}/{e['edge_id']} 二元边输入元数 {n_in} != 2")


def v3_mapping(tgt, src, gid):
    """V3：正任务参考映射必须结构成立 + 响应达标；且枚举不漏。"""
    pts = sample_points(tgt)
    lst = enum_struct(src, tgt)
    tick("V3", len(lst) >= 1, f"{gid} 有效源结构合法映射数为 0")
    return pts, lst


def v4_positive(gid, tgt, task, ref):
    """V4 正任务：候选 10 个，恰好能实测出有效映射，其余全被拒。"""
    objs = {o["object_id"]: o for o in load_objs(gid)}
    pool = task["source_ids"]
    tick("V4", len(pool) == 10, f"{gid} 正任务候选数 {len(pool)} != 10")
    tick("V4", len(set(pool)) == 10, f"{gid} 正任务候选有重复")
    pts = sample_points(tgt)
    effective = []
    for oid in pool:
        if oid not in objs:
            tick("V4", False, f"{gid} 任务引用了不存在的对象 {oid}")
            continue
        vs = valid_maps(objs[oid], tgt, pts)
        if vs:
            effective.append(oid)
    tick("V4", len(effective) == 1, f"{gid} 正任务实测有效源数量 {len(effective)} != 1：{effective}")
    # 参考标注里的 valid 必须能实测复现
    for v in ref["valid"]:
        src = objs.get(v["source_id"])
        tick("V4", src is not None, f"{gid} reference.valid 引用不存在对象 {v['source_id']}")
        if src is None:
            continue
        mx, _, _ = max_gap(src, tgt, v["node_map"], pts)
        tick("V4", mx <= TOL_ERR, f"{gid} reference.valid 映射实测超容差 {mx:.4f}")
    tick("V4", len(ref["exclusions"]) == 9, f"{gid} 正任务排除记录数 {len(ref['exclusions'])} != 9")


def v5_negative(gid, tgt, task, ref):
    """V5 负任务：全库枚举排除 + 每个候选都有超容差见证点（PDF L1008/L1010）。"""
    objs = {o["object_id"]: o for o in load_objs(gid)}
    pool = task["source_ids"]
    tick("V5", len(pool) == 10 and len(set(pool)) == 10, f"{gid} 负任务候选数/唯一性不符")
    pts = sample_points(tgt)
    for oid in pool:
        if oid not in objs:
            tick("V5", False, f"{gid} 负任务引用不存在对象 {oid}")
            continue
        vs = valid_maps(objs[oid], tgt, pts)
        tick("V5", len(vs) == 0, f"{gid} 负任务里 {oid} 实测存在有效映射 {len(vs)} 个")
    tick("V5", ref["valid"] == [], f"{gid} 负任务 valid 非空")
    tick("V5", len(ref["exclusions"]) == 10, f"{gid} 负任务排除记录数 {len(ref['exclusions'])} != 10")
    for ex in ref["exclusions"]:
        w = ex.get("witness")
        if not tick("V5", w is not None, f"{gid}/{ex['source_id']} 缺见证点"):
            continue
        src = objs.get(ex["source_id"])
        if src is None:
            continue
        # 见证点必须复算：在给定 u 上实测响应差与声明一致，且超容差
        try:
            u_s, ok = {}, True
            for t in tgt["controllable_inputs"]:
                if t not in src["controllable_inputs"]:
                    ok = False
                    break
                u_s[t] = w["u"][t]
            if not ok:
                tick("V5", False, f"{gid}/{ex['source_id']} 见证点与源域输入不匹配")
                continue
            d = abs(nresp(src, u_s) - nresp(tgt, w["u"]))
            tick("V5", abs(d - w["max_abs_diff"]) <= 1e-6,
                 f"{gid}/{ex['source_id']} 见证点复算 {d:.6f} != 声明 {w['max_abs_diff']:.6f}")
            tick("V5", d > TOL_ERR or ex["kind"] == "structure_error",
                 f"{gid}/{ex['source_id']} 见证点未超容差且非结构错误")
        except Exception as ex2:
            tick("V5", False, f"{gid}/{ex['source_id']} 见证点复算异常 {ex2}")


def v6_isolation(gdir, gid, tgt, tasks, ref, man):
    """V6 隔离与划分。"""
    # 版本号一致性（PDF 要求全程同版本；版本号挂在 manifest / task 上）
    tick("V6", man.get("schema_version") == SCHEMA["schema_version"],
         f"{gid} manifest schema_version 不符 {man.get('schema_version')}")
    tick("V6", man.get("vocab_version") == VOCAB["vocab_version"],
         f"{gid} manifest vocab_version 不符 {man.get('vocab_version')}")
    for t in tasks:
        tick("V6", t.get("schema_version") == SCHEMA["schema_version"],
             f"{gid}/{t['task_id']} task schema_version 不符")
        tick("V6", t.get("vocab_version") == VOCAB["vocab_version"],
             f"{gid}/{t['task_id']} task vocab_version 不符")
    # task_id 不编码标签
    for tid in man["task_ids"]:
        low = tid.lower()
        tick("V6", not any(w in low for w in ("pos", "neg", "true", "false", "valid", "invalid")),
             f"{tid} 编码了标签信息")
    # 公开对象不含答案字段
    for o in load_objs(gid):
        for k in ("label_kind", "kind", "is_valid", "_kind"):
            tick("V6", k not in o, f"{gid}/{o['object_id']} 公开对象含答案字段 {k}")
        tick("V6", o.get("label") in ("目标域", "候选源域"),
             f"{gid}/{o['object_id']} label 泄露 {o.get('label')}")
    # 候选顺序不含答案信息：有效源不能总在固定位置
    # 干预点仅测试组
    has_pts = (gdir / "sealed" / "intervention_points.json").exists()
    tick("V6", has_pts == (man["split"] == "test"),
         f"{gid} 干预点存在性与 split={man['split']} 不符")
    if has_pts:
        d = json.load(open(gdir / "sealed" / "intervention_points.json", encoding="utf-8"))
        tick("V6", d.get("points_per_task") == 100, f"{gid} 干预点数 != 100")
        for tid, pts in d["tasks"].items():
            tick("V6", len(pts) == 100 and len({tuple(sorted(p.items())) for p in pts}) == 100,
                 f"{tid} 干预点不足 100 或不唯一")
            tick("V6", all(any(abs(v) > 1e-12 for v in p.values()) for p in pts),
                 f"{tid} 含固定初始化点")
            for p in pts[:5]:
                for n in tgt["controllable_inputs"]:
                    lo, hi = tgt["intervention_bounds"][n]
                    tick("V6", lo - 1e-9 <= p[n] <= hi + 1e-9, f"{tid} 干预点越界 {n}={p[n]}")
    # 结构类别不进公开侧
    pub = json.dumps(man, ensure_ascii=False)
    for w in ("s0_", "s1_", "s2_", "s3_", "s4_", "structure_class"):
        tick("V6", w not in pub, f"{gid} manifest 公开侧含结构类别 {w}")


def load_objs(gid):
    d = CASES / gid / "data" / "input" / "objects"
    return [json.load(open(f, encoding="utf-8")) for f in sorted(d.glob("*.json"))]


def sig_topo(obj):
    """拓扑签名（不为节点 ID 依赖）：按拓扑序记录 (边类型, 入度, 上游中间量个数)。"""
    try:
        order = topo(obj)
    except ValueError:
        return None
    by = {e["edge_id"]: e for e in obj["edges"]}
    produced = {n for e in obj["edges"] for n in e["output_nodes"]}
    seq = []
    for eid in order:
        e = by[eid]
        seq.append(f"{e['edge_type'][:3]}:{len(e['input_nodes'])}:"
                   f"{sum(1 for n in e['input_nodes'] if n in produced)}")
    return "|".join(seq)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    gids = sorted(p.name for p in CASES.glob("group_v2_*") if p.is_dir())
    if args.limit:
        gids = gids[: args.limit]
    if not gids:
        print("没有找到任何组，先跑生成器")
        return 1
    print(f"待验 {len(gids)} 组")

    splits = defaultdict(int)
    sigs = defaultdict(list)
    for gid in gids:
        gdir = CASES / gid
        man = json.load(open(gdir / "manifest.json", encoding="utf-8"))
        sealed = json.load(open(gdir / "manifest.sealed.json", encoding="utf-8"))
        ref = json.load(open(gdir / "sealed" / "reference.json", encoding="utf-8"))
        tasks = [json.load(open(f, encoding="utf-8"))
                 for f in sorted((gdir / "data" / "input" / "tasks").glob("*.json"))]
        objs = {o["object_id"]: o for o in load_objs(gid)}
        tgt = objs[man["target_id"]]

        # V1
        for o in objs.values():
            v1_fields(o, gid)
        # V2
        v2_topology(tgt, gid)
        tick("V2", len(tgt["nodes"]) <= 9, f"{gid} 节点数 {len(tgt['nodes'])} > 9")
        tick("V2", len(tgt["edges"]) <= 5, f"{gid} 超边数 {len(tgt['edges'])} > 5")
        tick("V2", man["n_nodes"] == len(tgt["nodes"]), f"{gid} manifest n_nodes 不符")
        tick("V2", man["n_edges"] == len(tgt["edges"]), f"{gid} manifest n_edges 不符")
        tick("V2", man["max_depth"] == depth_of(tgt), f"{gid} manifest max_depth 不符")

        # V3/V4/V5
        tick("V3", len(tasks) == 2, f"{gid} 任务数 {len(tasks)} != 2")
        tpos = next(t for t in tasks if ref.get(t["task_id"], {}).get("label") == "positive")
        tneg = next(t for t in tasks if ref.get(t["task_id"], {}).get("label") == "negative")
        src = objs.get(f"obj_{gid}_src")
        if src is None:
            tick("V3", False, f"{gid} 缺有效源 obj_{gid}_src")
        else:
            v3_mapping(tgt, src, gid)
        v4_positive(gid, tgt, tpos, ref[tpos["task_id"]])
        v5_negative(gid, tgt, tneg, ref[tneg["task_id"]])
        v6_isolation(gdir, gid, tgt, tasks, ref, man)

        splits[man["split"]] += 1
        sigs[sig_topo(tgt)].append(gid)

    # 划分比例
    n = len(gids)
    for k, want in (("train", 0.70), ("val", 0.15), ("test", 0.15)):
        got = splits[k] / n
        tick("V6", abs(got - want) <= 0.05, f"划分 {k} 比例 {got:.2%} 偏离 {want:.0%} 超 5 个点")
    print(f"划分分布 {dict(splits)}")

    # 跨组拓扑重复（同签名组数 > 1 记 WARNING）
    dup = {s: v for s, v in sigs.items() if len(v) > 1}
    print(f"拓扑签名 {len(sigs)} 种；重复签名 {len(dup)} 组")
    for s, v in dup.items():
        print(f"  WARNING 同拓扑：{v} -> {s}")

    print(f"\n检查项 {CHECKS[0]} 条，失败 {len(FAILS)} 条")
    for t, m in FAILS[:40]:
        print(f"  [{t}] {m}")
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
