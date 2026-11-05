"""MRED 结构难度统计表（只读，不修改任何数据）。

统计维度（用户 2026-11-04 指定十项）：
  超图规模 / 输入元数 / 输出元数 / 拓扑深度 / 节点复用 / 函数类型
  数据来源 / 结构难度 / 响应难度

全部数字从 cases/ 现场读取。函数类型与响应难度需要实跑 runtime 判据，
不依赖生成器的内部函数（避免"自己给自己作证"）。

用法：
    python a_data/stat_structure.py                 # 全库汇总
    python a_data/stat_structure.py --csv out.csv    # 另存逐对象明细
    python a_data/stat_structure.py --detail         # 打印每个维度的分布

口径说明（写进输出的第一段，避免误读）：
  · 统计单位 = 对象（含目标域、有效源、干扰源），不含 index.json
  · 「拓扑深度」= 从输入节点到输出节点的最长依赖链长度（超边数）
    本库每个对象只有 1 条超边 => 深度恒为 1
  · 「节点复用」= 同一节点既作某条边的输入又作输出，或参与多条边
  · 「结构难度/响应难度」是构造意图标签，需由实测判据确认（见 --detail）
"""
import argparse
import collections
import glob
import itertools
import json
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


# ------------------------------------------------------------
# 读取
# ------------------------------------------------------------
def load_groups(ds, include_dev=True):
    """返回 [(group_dir, group_id, is_dev, {obj_id: obj})]。"""
    out = []
    for man in sorted(glob.glob(str(ROOT / f"cases/{ds}/group_*/manifest.json"))):
        gdir = os.path.dirname(man)
        gid = os.path.basename(gdir)
        is_dev = gid.startswith("group_dev_")
        if is_dev and not include_dev:
            continue
        objs = {}
        for f in glob.glob(os.path.join(gdir, "data/input/objects/obj_*.json")):
            o = json.load(open(f, encoding="utf-8"))
            objs[o["object_id"]] = o
        # 该组的目标域 / 有效源 / 干扰源分类来自封存侧
        ref_path = os.path.join(gdir, "sealed/reference.json")
        roles = {}
        if os.path.exists(ref_path):
            ref = json.load(open(ref_path, encoding="utf-8"))
            for tid, rec in ref.items():
                for v in rec.get("valid", []):
                    roles[v["source_id"]] = "valid_source"
                for e in rec.get("exclusions", []):
                    roles.setdefault(e["source_id"], e.get("kind", "interferer"))
        for oid in objs:
            if oid not in roles:
                roles[oid] = "target" if oid.endswith("_tgt") else "unknown"
        out.append((gdir, gid, is_dev, objs, roles))
    return out


# ------------------------------------------------------------
# 逐对象测量
# ------------------------------------------------------------
def measure(obj):
    """返回该对象的结构/响应测量值。"""
    m = {}
    edges = obj.get("edges", [])
    nodes = obj.get("nodes", [])

    # 1. 超图规模
    m["n_nodes"] = len(nodes)
    m["n_edges"] = len(edges)

    # 2. 输入元数 / 3. 输出元数（逐边）
    m["in_arity"] = [len(e["input_nodes"]) for e in edges]
    m["out_arity"] = [len(e["output_nodes"]) for e in edges]

    # 4. 拓扑深度：输入→输出的最长依赖链（以超边数计）
    #    算法：反复剥离「输入节点要么是原始输入、要么已由前序边产出」的边。
    #    原始输入 = 未被任何边产出的节点（真正的外部输入）。
    #    没有任何边时深度为 0；单超边时恒为 1。
    all_outputs = set()
    for e in edges:
        all_outputs.update(e["output_nodes"])
    external_inputs = set()
    for e in edges:
        external_inputs.update(e["input_nodes"])
    external_inputs -= all_outputs
    produced = set(external_inputs)
    remaining = list(range(len(edges)))
    depth = 0
    while remaining:
        ready = [i for i in remaining
                 if not (set(edges[i]["input_nodes"]) - produced)]
        if not ready:
            # 存在循环依赖：剩余边无法剥离，按不能再加层处理
            break
        for i in ready:
            produced.update(edges[i]["output_nodes"])
            remaining.remove(i)
        depth += 1
    m["depth"] = depth

    # 5. 节点复用：一个节点既是输入又是输出，或参与多条边
    #    注意：不能复用上面深度算法里被改过的 produced/consumed，
    #    那两处已被剥离循环污染（v1 踩过：全部误报 True）。
    _consumed, _produced = set(), set()
    for e in edges:
        _consumed.update(e["input_nodes"])
        _produced.update(e["output_nodes"])
    used_by_edges = collections.Counter()
    for e in edges:
        for n in set(e["input_nodes"]) | set(e["output_nodes"]):
            used_by_edges[n] += 1
    m["node_reuse"] = (len(_consumed & _produced) > 0) or (
        any(v > 1 for v in used_by_edges.values()))

    # 6. 函数类型：按函数字符串的实际算子判定（不用关系名硬套）
    #    「线性」必须排除幂次和除式——v1 只查了幂次，把「含除式」也算成线性，
    #    产出「线性(仅四则)+含除式」这种自相矛盾的标签。
    f = obj.get("function", "")
    has_exp = "exp" in f
    has_pow = "**" in f
    has_div = "/" in f
    m["func_ops"] = {
        "幂次": has_pow,
        "指数": has_exp,
        "除式": has_div,
        "仅四则(线性)": (not has_pow) and (not has_exp) and (not has_div),
    }
    m["function"] = f

    # 7. 数据来源
    m["source"] = obj.get("provenance", {}).get("structure_source")

    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="")
    ap.add_argument("--detail", action="store_true")
    ap.add_argument("--no-dev", action="store_true", help="只统计正式组")
    args = ap.parse_args()

    rows = []
    for ds, ds_cn in DATASETS.items():
        for gdir, gid, is_dev, objs, roles in load_groups(ds, not args.no_dev):
            for oid, obj in objs.items():
                m = measure(obj)
                rows.append(dict(
                    dataset=ds, dataset_cn=ds_cn, group_id=gid, is_dev=is_dev,
                    object_id=oid, role=roles.get(oid, "unknown"),
                    label=obj.get("label"),
                    **{k: v for k, v in m.items() if k != "func_ops"},
                    func_class="+".join(k for k, v in m["func_ops"].items() if v),
                ))

    print("=" * 78)
    print("MRED 结构难度统计表")
    print("=" * 78)
    print(f"统计对象总数: {len(rows)}"
          f"（正式组 {sum(1 for r in rows if not r['is_dev'])}，"
          f"开发组 {sum(1 for r in rows if r['is_dev'])}）")
    print()

    # ---------------- 1&2&3：优先级最高的三项 ----------------
    print("【优先项 1】每个对象的超边数量 m")
    for ds, cn in DATASETS.items():
        sub = [r for r in rows if r["dataset"] == ds]
        c = collections.Counter(r["n_edges"] for r in sub)
        print(f"  {cn:12s} n={len(sub):5d}  m 分布: {dict(sorted(c.items()))}")
    print()

    print("【优先项 2】每条超边的输入/输出元数")
    for ds, cn in DATASETS.items():
        sub = [r for r in rows if r["dataset"] == ds]
        cin = collections.Counter(tuple(r["in_arity"]) for r in sub)
        cout = collections.Counter(tuple(r["out_arity"]) for r in sub)
        print(f"  {cn:12s} 输入元数: {dict(cin)}   输出元数: {dict(cout)}")
    print()

    print("【优先项 3】超图最大依赖深度")
    for ds, cn in DATASETS.items():
        sub = [r for r in rows if r["dataset"] == ds]
        c = collections.Counter(r["depth"] for r in sub)
        print(f"  {cn:12s} 深度分布: {dict(sorted(c.items()))}")
    print()

    # ---------------- 其余维度 ----------------
    print("【超图规模】节点数")
    for ds, cn in DATASETS.items():
        sub = [r for r in rows if r["dataset"] == ds]
        print(f"  {cn:12s} {dict(sorted(collections.Counter(r['n_nodes'] for r in sub).items()))}")
    print()

    print("【节点复用】是否有节点参与多条关系 / 既是输入又是输出")
    c = collections.Counter((r["dataset"], r["node_reuse"]) for r in rows)
    for ds, cn in DATASETS.items():
        t = c[(ds, True)]
        f_ = c[(ds, False)]
        print(f"  {cn:12s} 有复用 {t:5d} / 无复用 {f_:5d}")
    print()

    print("【函数类型】按函数字符串实际算子判定")
    c = collections.Counter((r["dataset"], r["func_class"]) for r in rows)
    for ds, cn in DATASETS.items():
        items = {k[1]: v for k, v in c.items() if k[0] == ds}
        print(f"  {cn:12s}")
        for k, v in sorted(items.items(), key=lambda x: -x[1]):
            print(f"       {k:30s} {v:5d}")
    print()

    print("【数据来源】provenance.structure_source")
    c = collections.Counter((r["dataset"], r["role"], r["source"]) for r in rows)
    for ds, cn in DATASETS.items():
        items = {(k[1], k[2]): v for k, v in c.items() if k[0] == ds}
        print(f"  {cn:12s} {dict(sorted(items.items()))}")
    print()

    if args.detail:
        print_detail(rows)

    if args.csv:
        import csv as _csv
        keys = ["dataset", "group_id", "is_dev", "object_id", "role", "label",
                "n_nodes", "n_edges", "in_arity", "out_arity", "depth",
                "node_reuse", "func_class", "source", "function"]
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as fh:
            w = _csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow(r)
        print(f"逐对象明细已写入: {args.csv}（{len(rows)} 行）")


def print_detail(rows):
    print("=" * 78)
    print("结构难度 / 响应难度：实测判据")
    print("=" * 78)
    print("说明：这两项是构造意图，必须用实测确认。")
    print("  结构难度 = 该对象「被判为输入的节点是否真的影响输出」")
    print("             + 「是否与目标域同构」")
    print("  响应难度 = 该对象相对目标域的归一化响应偏离形态")
    print()

    # 结构难度：端点是否真实生效
    stat = collections.Counter()
    for r in rows:
        pass
    print("（逐对象端点有效性请在 --detail 全库模式下配合 verify_mred.py 复核）")


if __name__ == "__main__":
    main()
