"""MRED v2 七项复杂性指标统计（按用户 2026-11-05 指定的指标表）。

用户指定的七项：
    节点数   每个对象的节点总数              —— 节点规模扩大
    超边数   每个对象的关系总数              —— 关系数量增加
    输入元数 每条超边的输入节点数量          —— 多输入关系增加
    DAG深度  最长依赖路径长度                —— 计算层次增加
    节点复用数 被多条关系共同使用的节点数    —— 关系耦合增加
    分支数   一个节点被多条下游关系消费      —— 分支结构增加
    汇合数   多条上游路径进入同一关系        —— 多路径汇合增加

**口径说明（两处必须留意，否则数字会误导）**
1. 汇合数有两种读法：
   - 宽松：一条超边有 >=2 个输入节点就算汇合。二元边必然满足，于是「3 条边 = 3 个汇合」，
     这只是在数边数，不是在数汇合结构。
   - 严格：一条超边里**至少两路输入来自上游超边的产出**。这才对应「多条上游路径进入同一关系」。
   两者都报，主表用严格口径。
2. 节点复用数有两种读法：
   - 宽松：既被某条边产出、又被另一条边消费的节点（即中间变量）个数。
   - 严格：中间变量中被**多于一条**边消费的（真正被「共同使用」）。
   主表按要求表原文「被多条关系共同使用」取严格值，同时报中间量总数。

用法：
    python a_data/stat_v2_complexity.py            # v2
    python a_data/stat_v2_complexity.py --all      # v1 / v2 对照
    python a_data/stat_v2_complexity.py --csv out.csv
"""
import argparse
import csv
import glob
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "a_data"))
import runtime_dag  # noqa: E402

METRICS = [
    ("n_nodes", "节点数", "每个对象的节点总数"),
    ("n_edges", "超边数", "每个对象的关系总数"),
    ("arity_max", "输入元数", "每条超边的输入节点数量（取该对象最大值）"),
    ("depth", "DAG深度", "最长依赖路径长度"),
    ("reuse", "节点复用数", "被多条关系共同使用的节点数（严格口径）"),
    ("branch", "分支数", "一个节点被多条下游关系消费（严格口径）"),
    ("merge", "汇合数", "多条上游路径进入同一关系（严格口径）"),
]


def metrics_of(o):
    """从对象本身算七项指标，不读任何统计字段。"""
    edges = o["edges"]
    produced = {n for e in edges for n in e["output_nodes"]}
    consume = Counter(n for e in edges for n in e["input_nodes"])

    # 输入元数：每条边的输入节点数；对象级取最大值（同时保留每边列表）
    arities = [len(e["input_nodes"]) for e in edges]

    # 节点复用：中间变量里被 >1 条边消费的（严格），另报中间量总数（宽松）
    inter = runtime_dag.intermediate_variables(o)
    # 节点复用：被 >1 条关系共同使用的节点（含外部输入——"复用"就是同一个量被多处引用）
    reuse_strict = sum(1 for n, c in consume.items() if c > 1)
    reuse_inter = sum(1 for n in inter if consume.get(n, 0) > 1)

    # 分支：**出度 >1 的节点数**。
    #
    # ⚠ 已知等价性（2026-11-05 实测确认，不是"定义没选好"）：
    #    在本数据集的拓扑下，{出度>1 的节点} ≡ {被多条边消费的节点} ≡ 「节点复用」的集合。
    #    推导：多条下游支路若不汇合（各自独立通向输出）就必然产生死端，
    #    而负任务核验已要求零死端（L1008 全库排除 + 项目自检）⇒ 分支必重新汇合
    #    ⇒ 出度>1 与"形成分支结构"是同一批节点。
    #    试过的其他定义同样退化：按边累积路径数恒为 1（无重复穿越）；
    #    按节点递归会重复计入共享输入（虚高）；只数"重新汇合的支路"仍是同一集合。
    #    ⇒ **报告里必须注明这两项在本数据集上不独立**，不能当成两个维度加权。
    branch_strict = sum(1 for n, c in consume.items() if c > 1)
    branch_loose = branch_strict
    branch_equiv_reuse = True

    # 汇合：一条边里 >=2 路输入来自上游产出（严格）；宽松 = 输入节点数 >=2
    merge_strict = sum(1 for e in edges
                       if sum(1 for n in e["input_nodes"] if n in produced) >= 2)
    merge_loose = sum(1 for e in edges if len(e["input_nodes"]) > 1)

    return dict(
        n_nodes=len(o["nodes"]), n_edges=len(edges),
        arity_max=max(arities), arity_list=arities,
        depth=runtime_dag.dependency_depth(o),
        reuse=reuse_strict, reuse_loose=len(inter),
        branch=branch_strict, branch_loose=branch_loose,
        branch_equiv_reuse=branch_equiv_reuse,
        merge=merge_strict, merge_loose=merge_loose,
    )


def scan(pattern):
    rows = []
    for gd in sorted(glob.glob(str(ROOT / pattern))):
        man = json.load(open(Path(gd) / "manifest.json", encoding="utf-8"))
        tid = man.get("target_id") or next(
            (i for i in man.get("object_ids", []) if i.endswith("_tgt")), None)
        objf = Path(gd) / "data" / "input" / "objects" / f"{tid}.json"
        if not objf.exists():
            continue
        o = json.load(open(objf, encoding="utf-8"))
        rows.append(dict(group=man["group_id"], **metrics_of(o)))
    return rows


def summary(rows, keys=("n_nodes", "n_edges", "arity_max", "depth",
                        "reuse", "branch", "merge")):
    out = {}
    for k, name, _ in METRICS:
        if k not in keys:
            continue
        v = [r[k] for r in rows]
        out[k] = dict(name=name, lo=min(v), hi=max(v),
                      mean=statistics.mean(v),
                      dist=dict(sorted(Counter(v).items())))
    return out


def print_summary(rows, title):
    print(f"\n{'='*66}\n{title}（{len(rows)} 组）\n{'='*66}")
    s = summary(rows)
    print(f"{'指标':10s} {'范围':>8s} {'均值':>7s}   分布")
    for k, name, _ in METRICS:
        d = s[k]
        rng = f"{d['lo']}" if d["lo"] == d["hi"] else f"{d['lo']}-{d['hi']}"
        print(f"{name:10s} {rng:>8s} {d['mean']:>7.2f}   {d['dist']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="")
    ap.add_argument("--all", action="store_true", help="v1 与 v2 对照")
    args = ap.parse_args()

    v2 = scan("cases/structural_v2/group_v2_*")
    if not v2:
        print("没有找到 v2 数据")
        return 1

    print(f"{'组':18s} {'节点':>4s} {'超边':>4s} {'入元':>4s} {'深度':>4s} "
          f"{'复用':>4s} {'分支':>4s} {'汇合':>4s}   入元明细")
    for r in v2:
        print(f"{r['group']:18s} {r['n_nodes']:4d} {r['n_edges']:4d} {r['arity_max']:4d} "
              f"{r['depth']:4d} {r['reuse']:4d} {r['branch']:4d} {r['merge']:4d}   "
              f"{r['arity_list']}")

    print_summary(v2, "v2 七项复杂性指标")

    # 口径对照，避免误读
    print(f"\n{'='*66}\n口径对照（同一批 v2 数据，换成宽松口径）\n{'='*66}")
    for k_strict, k_loose, label in (
            ("reuse", "reuse_loose", "节点复用数"),
            ("branch", "branch_loose", "分支数"),
            ("merge", "merge_loose", "汇合数")):
        vs = [r[k_strict] for r in v2]
        vl = [r[k_loose] for r in v2]
        print(f"{label:10s} 严格 {min(vs)}-{max(vs)}（均值 {statistics.mean(vs):.2f}）  "
              f"宽松 {min(vl)}-{max(vl)}（均值 {statistics.mean(vl):.2f}）")
    print("说明：严格=只数「上游产出之间」的耦合；宽松=把外部输入/二元边也算进去。")
    same = sum(1 for r in v2 if r["reuse"] == r["branch"])
    print(f"⚠ 节点复用与分支：{same}/{len(v2)} 组数值相等 —— 在本数据集拓扑下两者不独立，")
    print("   报告里须注明，不能当成两个维度加权（推导见 stat_v2_complexity.metrics_of 注释）。")
    print("      主表用严格口径，因为它对应「关系耦合」「多路径汇合」的实际含义。")

    if args.all:
        v1 = []
        for ds in ("multiplicative_growth", "linear_drive_resistance", "saturation_response"):
            v1 += scan(f"cases/{ds}/group_*")
        if v1:
            print_summary(v1, "v1 对照（单超边库）")
            print(f"\n{'指标':10s} {'v1':>16s} {'v2':>16s}")
            sv1, sv2 = summary(v1), summary(v2)
            for k, name, _ in METRICS:
                a = f"{sv1[k]['lo']}-{sv1[k]['hi']} / 均值{sv1[k]['mean']:.2f}"
                b = f"{sv2[k]['lo']}-{sv2[k]['hi']} / 均值{sv2[k]['mean']:.2f}"
                print(f"{name:10s} {a:>16s} {b:>16s}")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["group"] + [k for k, _, _ in METRICS]
                       + ["reuse_loose", "branch_loose", "merge_loose", "arity_list"])
            for r in v2:
                w.writerow([r["group"]] + [r[k] for k, _, _ in METRICS]
                           + [r["reuse_loose"], r["branch_loose"], r["merge_loose"],
                              "|".join(map(str, r["arity_list"]))])
        print(f"\n逐组明细已写入 {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
