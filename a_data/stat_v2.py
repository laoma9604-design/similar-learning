"""MRED v2 复杂度统计：结构 / 映射 / 响应三维，并与 v1、v1.1 统一口径对比。

用法：python a_data/stat_v2.py [--json-out path]
口径统一（三个库都按同一套定义计算）：
  · 单位：1 基础组 = 1 目标 + 10 候选 + 2 任务（正/负）
  · 结构维：|V|、|E|、输入元数、DAG 深度、中间变量数、共享节点数、分支/汇合数
  · 映射维：节点双射×超边双射的结构合法映射数、有效映射数、置换对称数
  · 响应维：三类干扰的响应可分性（恒等映射下最大 |Δr|）
"""
import argparse
import csv
import glob
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "a_data"))
import runtime_dag  # noqa: E402


def load_group(gdir):
    objs = {}
    for f in (gdir / "data" / "input" / "objects").glob("*.json"):
        o = json.load(open(f, encoding="utf-8"))
        if "object_id" not in o:      # index.json 之类不是对象
            continue
        objs[o["object_id"]] = o
    man = json.load(open(gdir / "manifest.json", encoding="utf-8"))
    ref = json.load(open(gdir / "sealed" / "reference.json", encoding="utf-8"))
    return objs, man, ref


def graph_metrics(o):
    """结构维：从对象本身算，不读任何统计字段。"""
    edges = o["edges"]
    produced = {n for e in edges for n in e["output_nodes"]}
    consumed = Counter(n for e in edges for n in e["input_nodes"])
    inter = runtime_dag.intermediate_variables(o)
    shared = runtime_dag.shared_nodes(o)
    # 分支 = 某节点的出度 > 1（被多条边消费）；汇合 = 某节点入度 > 1（吃多条边产出）
    branch = sum(1 for n, c in consumed.items() if c > 1)
    indeg = Counter(n for e in edges for n in e["input_nodes"])
    merge = sum(1 for e in edges if len(e["input_nodes"]) > 1)
    return dict(
        n_nodes=len(o["nodes"]), n_edges=len(edges),
        n_inputs=len(o["controllable_inputs"]),
        depth=runtime_dag.dependency_depth(o),
        n_intermediate=len(inter), n_shared=len(shared),
        branched=branch, merged=merge,
        arity=sorted({len(e["input_nodes"]) for e in edges}),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-out", default="")
    args = ap.parse_args()

    rows = []
    for ds, pat in (
        ("v2", "cases/structural_v2/group_v2_*"),
        ("v1.1", "cases/structural_enhanced/group_enh_*"),
        ("v1", "cases/multiplicative_growth/group_*"),
        ("v1", "cases/linear_drive_resistance/group_*"),
        ("v1", "cases/saturation_response/group_*"),
    ):
        for gd in sorted(glob.glob(str(ROOT / pat))):
            gdir = Path(gd)
            try:
                objs, man, ref = load_group(gdir)
            except Exception:
                continue
            # v1 的 manifest 没有 target_id，只有 object_ids；按 _tgt 后缀找
            tid_ = man.get("target_id") or next(
                (i for i in man.get("object_ids", []) if i.endswith("_tgt")), None)
            if tid_ is None or tid_ not in objs:
                continue
            tgt = objs[tid_]
            gm = graph_metrics(tgt)
            # 映射维：从 reference 读（v1 结构不同，缺字段就记 N/A）
            # 只看正任务：负任务的 exclusions 是同一批干扰源，重复计数会让候选数翻倍
            pos_rec = next((r for r in ref.values() if r.get("label") == "positive"), None)
            neg_rec = next((r for r in ref.values() if r.get("label") == "negative"), None)
            n_valid = len((pos_rec or {}).get("valid") or [])
            n_cand = len((pos_rec or {}).get("candidate_ids") or [])
            # 响应维：只有「结构成立但响应错」和「局部扰动」才有响应可分性的意义；
            # 结构错误类靠 eq:structure 排除，Δr 天然为 0（v1.1 的 483 条就是这样）
            gaps = []
            for rec in (pos_rec, neg_rec):
                for ex in (rec or {}).get("exclusions") or []:
                    if ex.get("kind") not in ("response_error", "local_perturbation"):
                        continue
                    w = ex.get("witness") or {}
                    if "max_abs_diff" in w:
                        gaps.append(w["max_abs_diff"])
                    elif "r_target" in w and "r_source" in w:   # v1 的写法
                        gaps.append(abs(w["r_source"] - w["r_target"]))
            rows.append(dict(
                dataset=ds, group=man.get("group_id"), split=man.get("split"),
                **gm,
                n_tasks=len(ref), n_valid_maps=n_valid, n_candidates=n_cand,
                gap_min=min(gaps) if gaps else float("nan"),
                gap_median=sorted(gaps)[len(gaps)//2] if gaps else float("nan"),
            ))

    # ---- 汇总表 ----
    byds = defaultdict(list)
    for r in rows:
        byds[r["dataset"]].append(r)
    print(f"{'数据集':6s} {'组数':>4s} {'任务':>4s} {'|V|':>9s} {'|E|':>6s} {'输入':>7s} "
          f"{'深度':>6s} {'中间量':>7s} {'共享':>5s} {'结构映射':>9s} {'有效映射':>8s}")
    for ds in ("v1", "v1.1", "v2"):
        rs = byds.get(ds)
        if not rs:
            continue

        def span(k):
            v = [r[k] for r in rs]
            lo, hi = min(v), max(v)
            return f"{lo}" if lo == hi else f"{lo}-{hi}"
        print(f"{ds:6s} {len(rs):4d} {sum(r['n_tasks'] for r in rs):4d} "
              f"{span('n_nodes'):>9s} {span('n_edges'):>6s} {span('n_inputs'):>7s} "
              f"{span('depth'):>6s} {span('n_intermediate'):>7s} {span('n_shared'):>5s} "
              f"{span('n_valid_maps'):>9s} {span('n_valid_maps'):>8s}")

    print("\n【结构维】v2 逐组")
    print(f"{'group':16s} {'|V|':>3s} {'|E|':>3s} {'入元':>4s} {'深':>2s} {'中间':>4s} {'共享':>4s} "
          f"{'分支':>4s} {'汇合':>4s} {'候选':>4s} {'有效映射':>8s} {'响应Δr最小':>10s}")
    for r in byds["v2"]:
        print(f"{r['group']:16s} {r['n_nodes']:3d} {r['n_edges']:3d} {r['n_inputs']:4d} "
              f"{r['depth']:2d} {r['n_intermediate']:4d} {r['n_shared']:4d} "
              f"{r['branched']:4d} {r['merged']:4d} {r['n_candidates']:4d} "
              f"{r['n_valid_maps']:8d} {r['gap_min']:10.4f}")

    # ---- 与 v1/v1.1 的重合风险 ----
    def sig_topology(o):
        try:
            order = runtime_dag.topological_order(o)
        except Exception:
            return None
        by = {e["edge_id"]: e for e in o["edges"]}
        prod = {n for e in o["edges"] for n in e["output_nodes"]}
        return "|".join(f"{by[i]['edge_type'][:3]}:{len(by[i]['input_nodes'])}:"
                        f"{sum(1 for n in by[i]['input_nodes'] if n in prod)}" for i in order)

    def sig_params(o):
        return json.dumps([[round(v, 6) for v in o["baseline"]]], sort_keys=True)

    sigs = defaultdict(set)
    for ds, pat in (("v1.1", "cases/structural_enhanced/group_enh_*"),
                    ("v1", "cases/multiplicative_growth/group_*/"),
                    ("v1", "cases/linear_drive_resistance/group_*/"),
                    ("v1", "cases/saturation_response/group_*/"),
                    ("v2", "cases/structural_v2/group_v2_*")):
        for gd in glob.glob(str(ROOT / pat)):
            gdir = Path(gd)
            try:
                objs, man, ref = load_group(gdir)
            except Exception:
                continue
            tid2 = man.get("target_id") or next(
                (i for i in man.get("object_ids", []) if i.endswith("_tgt")), None)
            if tid2 is None or tid2 not in objs:
                continue
            tgt = objs[tid2]
            st, sp = sig_topology(tgt), sig_params(tgt)
            if st:
                sigs[ds].add(("topo", st))
            sigs[ds].add(("param", sp))

    print("\n【重合风险】拓扑签名 / 参数签名")
    for ds in ("v1", "v1.1"):
        if ds in sigs:
            inter = sigs["v2"] & sigs[ds]
            tt = [x for x in inter if x[0] == "topo"]
            pp = [x for x in inter if x[0] == "param"]
            print(f"  v2 ∩ {ds}: 拓扑签名重复 {len(tt)}，参数签名重复 {len(pp)}")

    # ---- 覆盖矩阵 ----
    print("\n【覆盖】v2 结构深度 × 家族组合（封存侧读）")
    cov = Counter()
    for gd in sorted(glob.glob(str(ROOT / "cases/structural_v2/group_v2_*"))):
        s = json.load(open(Path(gd) / "manifest.sealed.json", encoding="utf-8"))
        fams = "".join("M" if f.startswith("mul") else ("L" if f.startswith("lin") else "S")
                       for f in s["edge_families"])
        m = json.load(open(Path(gd) / "manifest.json", encoding="utf-8"))
        cov[(m["max_depth"], fams)] += 1
    for k, v in sorted(cov.items()):
        print(f"  深度 {k[0]} × {k[1]:8s} : {v} 组")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(rows, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
        print(f"\n明细已写入 {args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
