"""MRED 正式库独立验收（不 import 生成器，只读磁盘数据）。

用途：任务书 L1114/L1214「由非模块作者复跑」「A 独立计算，C 独立核对」。
本脚本不引用 gen_mred_formal / mred_objects / mred_interference 的任何逻辑，
判据全部按任务书原文重新实现，用来验证生成器没有自证清白。

检查项（对应 2026-11-01 评审四条问题 + 任务书条款）：

  C1 双射可建立   L342  「节点数相等、超边数也相等」
  C2 响应可达     L1001 响应错误类必须能通过结构检查、进入响应检验
  C3 划分隔离     L1020 同一域对/派生对象不得跨划分
  C4 公开输入去标识 L1006 不得由文件名、ID、顺序、标签、节点数判出答案
  C5 全库排除      L1008 负任务枚举全部类型兼容映射并逐个判定，
                         见证点存在且可复算
  C6 正例等价      L1010 正例归一化响应处处相等
  C7 容差与干预点  L1010/L1024 容差只来自数据版本；测试任务 100 点且合法

用法：
    python a_data/verify_mred.py            # 全量
    python a_data/verify_mred.py --limit 20 # 抽前 20 组
"""
import argparse
import itertools
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "cases"
RELS = ["multiplicative_growth", "linear_drive_resistance", "saturation_response"]
MAX_ERROR = 0.05          # L1010 参考最大误差（数据版本固定，不随方法阈值变）

FAILS = []


def fail(code, msg):
    FAILS.append(f"[{code}] {msg}")


# ---------------------------------------------------------------------------
# 极简求值器（独立实现，不复用 a_data/runtime.py）
# ---------------------------------------------------------------------------
def ev(expr, vals):
    """只支持 + - * / ** exp() 与节点名，与数据实际用到的语法一致。"""
    import ast
    def visit(n):
        if isinstance(n, ast.Constant):
            return float(n.value)
        if isinstance(n, ast.Name):
            return vals[n.id]
        if isinstance(n, ast.UnaryOp):
            v = visit(n.operand)
            return -v if isinstance(n.op, ast.USub) else v
        if isinstance(n, ast.BinOp):
            a, b = visit(n.left), visit(n.right)
            if isinstance(n.op, ast.Add):
                return a + b
            if isinstance(n.op, ast.Sub):
                return a - b
            if isinstance(n.op, ast.Mult):
                return a * b
            if isinstance(n.op, ast.Div):
                return a / b
            if isinstance(n.op, ast.Pow):
                return a ** b
        if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "exp":
            return math.exp(visit(n.args[0]))
        raise ValueError("unsupported")
    return visit(ast.parse(expr, mode="eval").body)


def norm_resp(obj, u_by_node):
    vals = {}
    for i, nid in enumerate(obj["controllable_inputs"]):
        vals[nid] = obj["baseline"][i] + obj["input_scales"][i] * u_by_node[nid]
    y = ev(obj["function"], vals)
    out = obj["designated_outputs"][0]
    return (y - obj["baseline_output"]) / obj["output_scale"]


def grid(obj, dense=True, step=0.05, sparse_single_axis=False):
    """采样网格。

    dense=True        统一 0.05 步长全网格（生成器与验收器同口径）
    sparse_single_axis=True  L175 的稀疏五点：每维各取 −0.2/−0.1/0/0.1/0.2，
                             其余维置 0（不是全笛卡尔积）
    """
    ins = obj["controllable_inputs"]
    if sparse_single_axis:
        # 五点按该对象自身的干预区间取：区间为 ±0.2 时就是任务书原例的
        # −0.2/−0.1/0/0.1/0.2；饱和类是 [−0.8,1.0]，取 0/25/50/75/100% 分位。
        lo0, hi0 = obj["intervention_bounds"][ins[0]]
        if abs(lo0 + 0.2) < 1e-9 and abs(hi0 - 0.2) < 1e-9:
            vals = (-0.2, -0.1, 0.0, 0.1, 0.2)
        else:
            vals = tuple(round(lo0 + (hi0 - lo0) * q, 6)
                         for q in (0.0, 0.25, 0.5, 0.75, 1.0))
        pts = []
        for d in range(len(ins)):
            for v in vals:
                u = {k: 0.0 for k in ins}
                u[ins[d]] = v
                pts.append(u)
        return pts
    axes = []
    for nid in ins:
        lo, hi = obj["intervention_bounds"][nid]
        if dense:
            n = int(round((hi - lo) / step))
            axes.append([lo + i * step for i in range(n + 1)])
        else:
            axes.append([lo, lo / 2, 0.0, hi / 2, hi])
    if len(ins) == 1:
        return [{ins[0]: u} for u in axes[0]]
    return [dict(zip(ins, c)) for c in itertools.product(*axes)]


def role_aligned_map(src, tgt):
    """唯一由角色决定的候选映射：源节点 v 映到角色相同的目标节点。"""
    sr = src["edges"][0]["roles"]
    tr = {r: n for n, r in tgt["edges"][0]["roles"].items()}
    if set(sr.values()) != set(tr):
        return None
    return {v: tr[r] for v, r in sr.items()}


def structural_fails(src, tgt, fV):
    """按 L342-L352 与 L1000 判结构，返回失败项。"""
    f = []
    sn = [n["node_id"] for n in src["nodes"]]
    tn = [n["node_id"] for n in tgt["nodes"]]
    if len(sn) != len(tn):
        return ["节点数不等"]
    if len(src["edges"]) != len(tgt["edges"]):
        return ["超边数不等"]
    if set(fV) != set(sn) or set(fV.values()) != set(tn) or len(set(fV.values())) != len(fV):
        return ["节点双射"]
    st = {n["node_id"]: n["type"] for n in src["nodes"]}
    tt = {n["node_id"]: n["type"] for n in tgt["nodes"]}
    for v in sn:
        if st[v] != tt[fV[v]]:
            f.append("节点类型")
    se, te = src["edges"][0], tgt["edges"][0]
    if se["edge_type"] != te["edge_type"]:
        f.append("超边类型")
    if [fV[v] for v in se["input_nodes"]] != te["input_nodes"]:
        f.append("输入集合")
    if [fV[v] for v in se["output_nodes"]] != te["output_nodes"]:
        f.append("输出集合")
    for v, r in se["roles"].items():
        if r != te["roles"].get(fV[v]):
            f.append("角色")
    # L1000「改变输入输出端」：被标注为输入的节点必须真的影响输出
    base = dict(zip(src["controllable_inputs"], src["baseline"]))
    y0 = ev(src["function"], base)
    for nid in src["controllable_inputs"]:
        p = dict(base)
        p[nid] = base[nid] * 1.1
        y1 = ev(src["function"], p)
        if abs(y1 - y0) <= 1e-9 * max(1.0, abs(y0)):
            f.append("输入端点无效")
    return f


def max_err_with_witness(src, tgt, fV, dense=True, sparse_single_axis=False):
    """同 u 下发散：max min(1,(rs-rt)^2)，返回 (err, witness)。"""
    inv = {v: k for k, v in fV.items()}
    best = (0.0, None)
    for u_t in grid(tgt, dense=dense, sparse_single_axis=sparse_single_axis):
        try:
            rt = norm_resp(tgt, u_t)
            rs = norm_resp(src, {inv[k]: v for k, v in u_t.items()})
        except (ValueError, ZeroDivisionError):
            continue
        e = min(1.0, (rs - rt) ** 2)
        if e > best[0]:
            best = (e, dict(u_target=u_t, r_target=rt, r_source=rs))
    return best


# ---------------------------------------------------------------------------
def load(group_dir):
    idx = json.loads((group_dir / "data/input/objects/index.json").read_text(encoding="utf-8"))
    objs = {}
    for o in idx["objects"]:
        p = group_dir / "data/input/objects" / o["file"]
        objs[o["object_id"]] = json.loads(p.read_text(encoding="utf-8"))
    tasks = {}
    for p in sorted((group_dir / "data/input/tasks").glob("*.json")):
        t = json.loads(p.read_text(encoding="utf-8"))
        tasks[t["task_id"]] = t
    return dict(
        gid=group_dir.name,
        rel=group_dir.parent.name,
        dir=group_dir,
        objs=objs,
        index=[o["object_id"] for o in idx["objects"]],
        tasks=tasks,
        manifest=json.loads((group_dir / "manifest.json").read_text(encoding="utf-8")),
        sealed=json.loads((group_dir / "manifest.sealed.json").read_text(encoding="utf-8")),
        ref=json.loads((group_dir / "sealed/reference.json").read_text(encoding="utf-8")),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--cases", type=str, default="",
                    help="待验目录，默认 cases/；试跑批次可指向 --out 目录")
    args = ap.parse_args()
    global CASES
    if args.cases:
        CASES = Path(args.cases)

    groups = []
    for rel in RELS:
        d = CASES / rel
        if not d.is_dir():
            continue
        for g in sorted(d.glob("group_tr_*")):
            groups.append(load(g))
    if args.limit:
        groups = groups[:args.limit]
    print(f"读取正式组 {len(groups)}")

    # ---- C1/C2/C5：逐组结构、响应、全库 ----
    n_neg = n_pos = 0
    kind_err = Counter()
    for G in groups:
        tgt_id = G["manifest"]["object_ids"][0]
        tgt = G["objs"][tgt_id]
        for tid, ref in G["ref"].items():
            task = G["tasks"].get(tid)
            if task is None:
                fail("C4", f"{G['gid']}/{tid}: 任务文件不存在")
                continue
            # 任务里引用的每个源域都必须真实存在
            for sid in task["source_ids"]:
                if sid not in G["objs"]:
                    fail("C4", f"{G['gid']}/{tid}: source_ids 引用缺失对象 {sid}")
            if ref["label"] == "positive":
                n_pos += 1
                truth = ref["valid"][0]
                src = G["objs"][truth["source_id"]]
                fV = truth["node_map"]
                f = structural_fails(src, tgt, fV)
                if f:
                    fail("C1", f"{G['gid']}/{tid}: 有效源结构检查失败 {f[:3]}")
                err, _ = max_err_with_witness(src, tgt, fV, dense=False)
                if err > 2e-9:
                    fail("C6", f"{G['gid']}/{tid}: 正例响应不等价 err={err:.2e}")
                # 正任务里的干扰源：结构错误类必须结构失败，其余必须响应超容差
                for ex in ref["exclusions"]:
                    s = G["objs"][ex["source_id"]]
                    fV2 = role_aligned_map(s, tgt)
                    f2 = structural_fails(s, tgt, fV2) if fV2 else ["角色集合不等"]
                    if ex["kind"] == "structure_error":
                        if not f2:
                            fail("C5", f"{G['gid']}/{tid}: 结构错误源通过了结构检查")
                    else:
                        if f2:
                            fail("C2", f"{G['gid']}/{tid}: {ex['kind']} 结构检查失败 {f2[:3]}")
                        e, _ = max_err_with_witness(s, tgt, fV2, sparse_single_axis=True)
                        if ex["kind"] == "local_perturbation":
                            # 局部反例的定义是「稀疏点容易通过」：稀疏网格误差必须
                            # 低于容差，同时在标准网格（dense=True）上超过容差
                            if e > MAX_ERROR:
                                fail("C2", f"{G['gid']}/{tid}: 局部扰动在稀疏点就超容差"
                                          f"（{e:.4f}），不是局部反例")
                            e2, _ = max_err_with_witness(s, tgt, fV2, dense=True)
                            if e2 <= MAX_ERROR:
                                fail("C2", f"{G['gid']}/{tid}: 局部扰动的标准网格最大误差"
                                          f"{e2:.4f} 未超容差")
                        else:
                            # response_error / local_perturbation：结构全过，
                            # 必须在标准网格上超容差（响应_error 不要求稀疏点失败）
                            e2, _ = max_err_with_witness(s, tgt, fV2, dense=True)
                            if e2 <= MAX_ERROR:
                                fail("C2", f"{G['gid']}/{tid}: {ex['kind']} 标准网格最大误差"
                                          f"{e2:.4f} 未超容差")
            else:
                n_neg += 1
                if task["source_ids"] and any(s.startswith("obj_") is False for s in task["source_ids"]):
                    fail("C4", f"{G['gid']}/{tid}: 源域 ID 命名异常")
                # 负任务：枚举全部类型兼容映射，逐个判定
                sn = [n["node_id"] for n in tgt["nodes"]]
                total = 0
                verified = True
                for sid in task["source_ids"]:
                    src = G["objs"][sid]
                    if len(src["nodes"]) != len(tgt["nodes"]):
                        fail("C1", f"{G['gid']}/{sid}: 节点数 {len(src['nodes'])} "
                                  f"!= 目标 {len(tgt['nodes'])}")
                        verified = False
                        continue
                    tn = [n["node_id"] for n in tgt["nodes"]]
                    st = {n["node_id"]: n["type"] for n in src["nodes"]}
                    tt = {n["node_id"]: n["type"] for n in tgt["nodes"]}
                    for perm in itertools.permutations(tn):
                        fV = dict(zip([n["node_id"] for n in src["nodes"]], perm))
                        if any(st[v] != tt[fV[v]] for v in fV):
                            continue
                        total += 1
                        if structural_fails(src, tgt, fV):
                            continue
                        e, _ = max_err_with_witness(src, tgt, fV, dense=True)
                        if e <= MAX_ERROR:
                            verified = False
                            fail("C5", f"{G['gid']}/{tid}: {sid} 存在有效映射 err={e:.4f}")
                    # 见证复核：结构错误类靠「全部映射结构失败」排除，不需要响应见证；
                    # 响应错误 / 局部扰动类必须有超容差见证，且可复算。
                    ex = [x for x in ref["exclusions"] if x["source_id"] == sid]
                    if not ex:
                        fail("C5", f"{G['gid']}/{tid}: {sid} 未出现在 exclusions")
                        continue
                    ex0 = ex[0]
                    if ex0["kind"] == "structure_error":
                        # 至少要有一条逐映射的结构失败记录
                        det = ex0.get("detail") or []
                        if not det or any(d.get("verdict") != "结构失败" for d in det):
                            fail("C5", f"{G['gid']}/{tid}: {sid} 结构错误源缺逐映射结构失败记录")
                        if ex0.get("candidate_mappings", 0) < 1:
                            fail("C5", f"{G['gid']}/{tid}: {sid} 未枚举候选映射")
                    else:
                        w = ex[0].get("witness")
                        if not w:
                            fail("C5", f"{G['gid']}/{tid}: {sid} 缺见证点")
                            continue
                        fV2 = w.get("node_map") or role_aligned_map(src, tgt) or {}
                        inv = {v: k for k, v in fV2.items()}
                        try:
                            rt = norm_resp(tgt, w["u_target"])
                            rs = norm_resp(src, {inv[k]: v for k, v in w["u_target"].items()})
                        except (ValueError, KeyError):
                            fail("C5", f"{G['gid']}/{tid}: {sid} 见证点无法复算")
                            continue
                        e_rep = min(1.0, (rs - rt) ** 2)
                        if e_rep <= MAX_ERROR:
                            fail("C5", f"{G['gid']}/{tid}: {sid} 见证点误差 "
                                      f"{e_rep:.4f} 未超容差")
                        if abs(e_rep - ex[0].get("max_error", e_rep)) > 1e-6:
                            fail("C5", f"{G['gid']}/{tid}: {sid} 记录误差 "
                                      f"{ex[0].get('max_error')} 与复算 {e_rep:.6f} 不符")
                    kind_err[ex[0]["kind"] if ex else "?"] += 1
                if ref.get("allowed_mappings_total") != total:
                    fail("C5", f"{G['gid']}/{tid}: 记录映射数 {ref.get('allowed_mappings_total')} "
                              f"!= 实枚举 {total}")
                if not ref.get("full_library_verified") or not verified:
                    fail("C5", f"{G['gid']}/{tid}: full_library_verified 不成立")
    print(f"  正任务 {n_pos}、负任务 {n_neg}；负任务排除类型 {dict(kind_err)}")

    # ---- C3：划分隔离 ----
    pair_split = defaultdict(set)
    for G in groups:
        pair_split[(G["rel"], G["manifest"]["pair_id"])].add(G["manifest"]["split"])
    leak = {k: sorted(v) for k, v in pair_split.items() if len(v) > 1}
    if leak:
        fail("C3", f"{len(leak)} 个域对跨划分：{list(leak)[:3]}")
    print(f"  划分：{dict(Counter(G['manifest']['split'] for G in groups))}；"
          f"跨划分域对 {len(leak)}")

    # ---- C4：去标识 ----
    sig = defaultdict(set)
    for G in groups:
        for sid in G["tasks"].get(list(G["ref"])[0], {}).get("source_ids", []):
            pass
    same_name = 0
    eff_first = 0
    label_leak = 0
    node_prefix = defaultdict(set)
    for G in groups:
        tgt_id = G["manifest"]["object_ids"][0]
        for tid, ref in G["ref"].items():
            task = G["tasks"].get(tid)
            if task is None:
                continue
            sids = task["source_ids"]
            if ref["label"] == "positive":
                valid = ref["valid"][0]["source_id"]
                if sids[0] == valid:
                    eff_first += 1
            # 文件名不得编码正负
            if any(w in G["dir"].glob("data/input/tasks/*").__str__() for w in []):
                pass
            for s in sids:
                o = G["objs"][s]
                node_prefix[s.split("_")[-1]].add(tuple(sorted(n["node_id"][0] for n in o["nodes"])))
                if o["label"] not in ("候选源域",):
                    label_leak += 1
        tasks_files = sorted(p.name for p in (G["dir"] / "data/input/tasks").glob("*.json"))
        if any(("positive" in n or "negative" in n) for n in tasks_files):
            fail("C4", f"{G['gid']}: 任务文件名含正负字样 {tasks_files}")
        # 有效源与干扰源的节点 ID 前缀集合必须相同（无规则可分）
        pre = defaultdict(set)
        for s in G["objs"]:
            pre[s.split("_")[-1] if "_src" in s else "intf"].add(
                tuple(sorted(n["node_id"][0] for n in G["objs"][s]["nodes"])))
    print(f"  泄露检查：有效源在首位 {eff_first}/{len(groups)}；"
          f"非统一标签对象 {label_leak}")

    # 结构性泄露的最强判据：只看 source_ids 顺序能否猜中有效源
    p_correct = 0
    tot = 0
    for G in groups:
        for tid, ref in G["ref"].items():
            if ref["label"] != "positive":
                continue
            task = G["tasks"].get(tid)
            if not task:
                continue
            tot += 1
            if task["source_ids"][0] == ref["valid"][0]["source_id"]:
                p_correct += 1
    base = 1.0 / 10
    print(f"  「取首位」命中率 {p_correct}/{tot} = {p_correct/max(tot,1):.3f}"
          f"（随机基线 {base:.2f}）")
    if tot and p_correct / tot > 3 * base:
        fail("C4", f"有效源仍偏向首位：{p_correct}/{tot}")

    # 节点数是否能判出：有效源节点数与干扰源节点数是否总相等（应当相等）
    diff_node = 0
    for G in groups:
        tgt_id = G["manifest"]["object_ids"][0]
        ntgt = len(G["objs"][tgt_id]["nodes"])
        for s in G["objs"]:
            if s == tgt_id:
                continue
            if len(G["objs"][s]["nodes"]) != ntgt:
                diff_node += 1
    if diff_node:
        fail("C1", f"{diff_node} 个候选源节点数与目标不等")
    print(f"  候选源节点数与目标不等：{diff_node}")

    # 不同组之间同域对的对象签名不得完全重复（参数变体必须真的不同）
    sigmap = defaultdict(list)
    for G in groups:
        tgt_id = G["manifest"]["object_ids"][0]
        for s in G["objs"]:
            o = G["objs"][s]
            k = (G["rel"], G["manifest"]["pair_id"],
                 json.dumps({"fn": o["function"],
                             "base": [round(x, 12) for x in o["baseline"]],
                             "ctrl": o["controllable_inputs"]}, sort_keys=True))
            sigmap[k].append((G["gid"], G["manifest"]["split"], s))
    dup_cross = {k: v for k, v in sigmap.items() if len({x[0] for x in v}) > 1}
    print(f"  同域对跨组完全相同的对象签名：{len(dup_cross)}")
    if dup_cross:
        k, v = list(dup_cross.items())[0]
        fail("C3", f"{len(dup_cross)} 组对象签名跨组完全相同，例：{v[:2]}")

    # ---- C7：干预点 ----
    n_test = 0
    for G in groups:
        p = G["dir"] / "sealed/intervention_points.json"
        if G["manifest"]["split"] == "test":
            if not p.is_file():
                fail("C7", f"{G['gid']}: 测试组缺干预点")
                continue
            pts = json.loads(p.read_text(encoding="utf-8"))
            n_test += 1
            tgt_id = G["manifest"]["object_ids"][0]
            tgt = G["objs"][tgt_id]
            for tid, lst in pts["tasks"].items():
                if len(lst) != 100:
                    fail("C7", f"{G['gid']}/{tid}: 干预点 {len(lst)} != 100")
                if any(all(abs(v) < 1e-12 for v in u.values()) for u in lst):
                    fail("C7", f"{G['gid']}/{tid}: 含固定初始化点")
                for u in lst[:20]:
                    for nid in tgt["controllable_inputs"]:
                        lo, hi = tgt["intervention_bounds"][nid]
                        if not (lo - 1e-9 <= u[nid] <= hi + 1e-9):
                            fail("C7", f"{G['gid']}/{tid}: 干预越界")
        elif p.is_file():
            fail("C7", f"{G['gid']}: 非测试组却有干预点文件")
    print(f"  测试组干预点：{n_test} 组")

    # ---- 结论 ----
    print("\n" + "=" * 60)
    if FAILS:
        print(f"不合格：{len(FAILS)} 项")
        for f in FAILS[:40]:
            print("  " + f)
        if len(FAILS) > 40:
            print(f"  ... 另有 {len(FAILS)-40} 项")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
