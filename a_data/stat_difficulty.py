"""MRED 结构难度 / 响应难度实测（只读）。

这两项不能靠标签断言，必须实测：
  结构难度 = 按「结构检查」能否拒绝该对象（相对正确映射）
             分档：single（只有 1 条边，结构信息最少）
                   multi（多条边，需同时满足多边约束）
                   branch（一个输出被多条边影响 / 一条边输出被多边消费）
                   merge（多个输入汇到同一输出）
  响应难度 = 该对象相对目标域归一化响应的偏离形态：
             全域差异   = 绝大多数干预点都超容差
             局部差异   = 只有一小片区域超容差（任务书 L170 的 b(u) 鼓包）
             方向差异   = 归一化响应的符号/单调方向不同
             幅度差异   = 方向一致但幅度显著不同
             无差异     = 与目标域在容差内等价（不该出现的干扰源）

判据（与 data 侧容差一致）：max_error = 0.05，err = min(1, (rs-rt)^2)
  超容差 <=> |rs - rt| > sqrt(0.05) = 0.2236

用法：
    python a_data/stat_difficulty.py
    python a_data/stat_difficulty.py --csv out.csv
"""
import argparse
import collections
import glob
import itertools
import json
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "a_data"))

import runtime  # noqa: E402

DATASETS = {
    "multiplicative_growth": "乘性增长",
    "linear_drive_resistance": "线性驱动-阻力",
    "saturation_response": "饱和响应",
}

MAX_ERROR = 0.05
TOL = math.sqrt(MAX_ERROR)          # |Δr| 超过此值即超容差 = 0.2236
GRID_STEP = 0.05


def norm_resp(obj, u_by_node):
    return runtime.normalized_response(obj, u_by_node)[obj["designated_outputs"][0]]


def eval_grid(obj):
    """按对象自身干预区间生成 0.05 步长网格。"""
    inputs = obj["controllable_inputs"]
    axes = []
    for n in inputs:
        lo, hi = obj["intervention_bounds"][n]
        ticks = []
        k = lo
        while k <= hi + 1e-12:
            ticks.append(round(k, 10))
            k += GRID_STEP
        if ticks[-1] < hi - 1e-12:
            ticks.append(hi)
        axes.append(ticks)
    return list(itertools.product(*axes))


# ------------------------------------------------------------
# 结构难度：只看拓扑形态
# ------------------------------------------------------------
def structural_difficulty(obj):
    edges = obj.get("edges", [])
    m = len(edges)
    if m == 0:
        return "empty"
    if m == 1:
        return "single"

    # 统计每个节点在每个位置出现的次数
    as_out = collections.Counter()     # 该节点作为「被边产出的输出」出现几次
    as_in = collections.Counter()      # 该节点作为「被边消费的输入」出现几次
    for e in edges:
        for n in e["output_nodes"]:
            as_out[n] += 1
        for n in e["input_nodes"]:
            as_in[n] += 1

    # 汇合 merge：多条边的输出汇聚到同一节点（a->c, b->c）
    merge = any(v >= 2 for v in as_out.values())
    # 分支 branch：同一节点的值被多条边当作输入消费（a->b, a->c），
    # 或某条边直接产出多个节点
    branch = any(v >= 2 for v in as_in.values()) or any(
        len(e["output_nodes"]) > 1 for e in edges)

    if merge and branch:
        return "branch+merge"
    if merge:
        return "merge"
    if branch:
        return "branch"
    return "multi"


# ------------------------------------------------------------
# 响应难度：相对目标域的偏离形态
# ------------------------------------------------------------
def response_difficulty(src, tgt):
    """返回 (类别, 统计量dict)。src==tgt 时返回 same。"""
    tin = tgt["controllable_inputs"]
    sin = src["controllable_inputs"]
    if len(tin) != len(sin):
        return "结构不可比(输入数不同)", {}

    grid = eval_grid(tgt)
    diffs = []
    sign_flip = 0
    mono_flip = 0
    n_ok = 0
    for combo in grid:
        u_t = dict(zip(tin, combo))
        u_s = dict(zip(sin, combo))
        try:
            rt = norm_resp(tgt, u_t)
            rs = norm_resp(src, u_s)
        except Exception:
            continue
        if not (math.isfinite(rt) and math.isfinite(rs)):
            continue
        n_ok += 1
        diffs.append(abs(rs - rt))

    if not diffs:
        return "无法求值", {}

    n = len(diffs)
    over = sum(1 for d in diffs if d > TOL)
    frac = over / n
    maxd = max(diffs)

    # 方向差异：在主维度上比较两端响应的相对方向
    for idx, tn in enumerate(tin):
        u_lo = {k: 0.0 for k in tin}
        u_hi = {k: 0.0 for k in tin}
        lo, hi = tgt["intervention_bounds"][tn]
        u_lo[tn], u_hi[tn] = lo / 2, hi / 2
        try:
            a_t, b_t = norm_resp(tgt, u_lo), norm_resp(tgt, u_hi)
            a_s, b_s = norm_resp(src, dict(zip(sin, u_lo.values()))), \
                       norm_resp(src, dict(zip(sin, u_hi.values())))
        except Exception:
            continue
        if (b_t - a_t) * (b_s - a_s) < 0:
            mono_flip += 1

    stats = dict(over_frac=frac, max_abs_diff=maxd, n_grid=n)

    # 分类口径（关键：要和任务书 L170 的「局部差异」区分开）
    #   全域差异  : 几乎处处超容差
    #   幅度差异  : 超容差点连成整片，且沿主维度单调增长（幂律/倍数偏差都属此类）
    #   局部差异  : 超容差点被「容差内的沉默区」隔开，只在输入域的一小段里偏离
    #               （任务书 b(u) 鼓包的定义特征）
    #   方向差异  : 主维度上响应的变化方向与目标相反
    if frac >= 0.9:
        return "全域差异", stats
    if frac == 0:
        return ("无差异(容差内等价)" if maxd <= TOL else "极少点差异"), stats
    if mono_flip > 0:
        return "方向差异", stats

    # 用「超容差区段数」判局部 vs 幅度：
    # 沿「对角线」扫描（所有输入取同一个 u）——本库的鼓包是对角形态的，
    # 只沿单维轴扫会整条错过（v2 实测：单维轴 max|Δr|=6e-5，对角线 0.30）。
    # 同时沿每个单维轴扫一次取并集，避免漏掉只在单维生效的干扰。
    segments = []
    tpaths = []
    # 路径 1..k：每个单维轴（其余维=0）
    for idx, tn in enumerate(tin):
        ticks, lo, hi = [], *tgt["intervention_bounds"][tn]
        k = lo
        while k <= hi + 1e-12:
            ticks.append(round(k, 10)); k += GRID_STEP
        if ticks[-1] < hi - 1e-12:
            ticks.append(hi)
        tpaths.append([(tn, t) for t in ticks])
    # 路径 k+1：对角线（所有维取同一 u，限在公共区间内）
    lo_all = max(tgt["intervention_bounds"][n][0] for n in tin)
    hi_all = min(tgt["intervention_bounds"][n][1] for n in tin)
    ticks, k = [], lo_all
    while k <= hi_all + 1e-12:
        ticks.append(round(k, 10)); k += GRID_STEP
    diag = [tuple((n, t) for n in tin) for t in ticks]
    tpaths.append([(tn, t) for tn, t in diag[0]] if diag else [])

    # 对角线单独按「整条线上所有维同时取该 u」处理
    diag_seq = []
    for t in ticks:
        u_t = {n: t for n in tin}
        try:
            diag_seq.append(abs(norm_resp(src, dict(zip(sin, u_t.values())))
                                - norm_resp(tgt, u_t)) > TOL)
        except Exception:
            diag_seq.append(False)

    def count_seg(seq):
        seg, prev = 0, False
        for s in seq:
            if s and not prev:
                seg += 1
            prev = s
        return seg

    axis_segs = []
    for path in tpaths[:-1]:
        seq = []
        for tn, t in path:
            u_t = {n: 0.0 for n in tin}; u_t[tn] = t
            try:
                seq.append(abs(norm_resp(src, dict(zip(sin, u_t.values())))
                               - norm_resp(tgt, u_t)) > TOL)
            except Exception:
                seq.append(False)
        axis_segs.append(count_seg(seq))

    stats["segments_axis"] = axis_segs
    stats["segments_diag"] = count_seg(diag_seq)
    stats["over_frac_diag"] = sum(diag_seq) / max(len(diag_seq), 1)
    stats["diag_seq"] = "".join("1" if s else "0" for s in diag_seq)

    # ---------------- 最终分类口径（以「超容差覆盖率」为主判据） ----------------
    # 前几版用「区段数」「两侧端点」判局部，连改三版仍在局部/幅度之间来回翻转
    # （实测：乘性局部扰动 over_frac 中位 4.9%、峰值 0.30，区段数不稳定）。
    # 按项目铁律改为离散度判据——局部 = 偏离只覆盖少数干预点，与「大部分点位
    # 都偏离」的幅度差异天然分开，不依赖区段切分。
    cover = frac                     # 全网格超容差占比
    stats["coverage"] = cover
    if cover >= 0.9:
        return "全域差异", stats
    if cover < 0.30:
        # 只覆盖少数点位 => 局部
        stats["shape"] = "局部(覆盖率<30%)"
        return "局部差异", stats
    stats["shape"] = "幅度(覆盖率>=30%)"
    return "幅度差异", stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="")
    args = ap.parse_args()

    rows = []
    for ds, cn in DATASETS.items():
        for man in sorted(glob.glob(str(ROOT / f"cases/{ds}/group_*/manifest.json"))):
            gdir = os.path.dirname(man)
            gid = os.path.basename(gdir)
            ref_path = os.path.join(gdir, "sealed/reference.json")
            if not os.path.exists(ref_path):
                continue
            ref = json.load(open(ref_path, encoding="utf-8"))

            objs = {}
            for f in glob.glob(os.path.join(gdir, "data/input/objects/obj_*.json")):
                o = json.load(open(f, encoding="utf-8"))
                objs[o["object_id"]] = o

            # 目标域取 tgt
            tgt = next((o for k, o in objs.items() if k.endswith("_tgt")), None)
            if tgt is None:
                continue

            kind_of = {}
            for rec in ref.values():
                for v in rec.get("valid", []):
                    kind_of[v["source_id"]] = "valid_source"
                for e in rec.get("exclusions", []):
                    kind_of.setdefault(e["source_id"], e.get("kind", "?"))

            for oid, o in objs.items():
                role = "target" if oid == tgt["object_id"] else kind_of.get(oid, "?")
                if role == "target":
                    continue
                cat, st = response_difficulty(o, tgt)
                rows.append(dict(
                    dataset=ds, dataset_cn=cn, group_id=gid,
                    object_id=oid, role=role,
                    structural=structural_difficulty(o),
                    structural_tgt=structural_difficulty(tgt),
                    response=cat, **st))

    print("=" * 78)
    print("MRED 难度实测（相对目标域）")
    print("=" * 78)
    print(f"参评对象（不含目标域）: {len(rows)}")
    print()

    print("【结构难度】拓扑形态")
    c = collections.Counter((r["dataset"], r["role"], r["structural"]) for r in rows)
    for ds, cn in DATASETS.items():
        print(f"  {cn}:")
        items = {(k[1], k[2]): v for k, v in c.items() if k[0] == ds}
        for k, v in sorted(items.items()):
            print(f"      {k[0]:20s} {k[1]:24s} {v:5d}")
    print()
    print("  （目标域自身）")
    for ds, cn in DATASETS.items():
        sub = [r for r in rows if r["dataset"] == ds]
        print(f"      {cn}: {dict(collections.Counter(r['structural_tgt'] for r in sub))}")
    print()

    print("【响应难度】相对目标域的偏离形态")
    c = collections.Counter((r["dataset"], r["role"], r["response"]) for r in rows)
    for ds, cn in DATASETS.items():
        print(f"  {cn}:")
        items = {(k[1], k[2]): v for k, v in c.items() if k[0] == ds}
        for k, v in sorted(items.items()):
            print(f"      {k[0]:20s} {k[1]:26s} {v:5d}")
    print()

    print("【关键交叉表】有效源被判成什么（应全部是「无差异」）")
    for ds, cn in DATASETS.items():
        sub = [r for r in rows if r["dataset"] == ds and r["role"] == "valid_source"]
        print(f"  {cn}: {dict(collections.Counter(r['response'] for r in sub))}")
    print()
    print("【关键交叉表】干扰源里有没有「容差内等价」（不该有，有就是假干扰）")
    for ds, cn in DATASETS.items():
        sub = [r for r in rows if r["dataset"] == ds
               and r["role"] in ("structure_error", "response_error", "local_perturbation")
               and r["response"].startswith("无差异")]
        tot = sum(1 for r in rows if r["dataset"] == ds
                  and r["role"] in ("structure_error", "response_error", "local_perturbation"))
        print(f"  {cn}: {len(sub)}/{tot}"
              f" = {100*len(sub)/max(tot,1):.1f}%")
    print()

    if args.csv:
        import csv as _csv
        keys = ["dataset", "group_id", "object_id", "role", "structural",
                "response", "over_frac", "max_abs_diff", "n_grid"]
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as fh:
            w = _csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow(r)
        print(f"明细已写入: {args.csv}")


if __name__ == "__main__":
    main()
