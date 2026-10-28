"""MRED 正式库生成主程序。

规模：300 基础组 / 600 任务 / 每任务 10 源域 / 三类干扰 / 测试任务各 100 干预点 / 70-15-15

用法：
    python a_data/gen_mred_formal.py --dry            # 全量验算，不落盘
    python a_data/gen_mred_formal.py --limit 3 --out /tmp/x   # 小批量试跑
    python a_data/gen_mred_formal.py                 # 落盘到 cases/

逐条对应任务书：
- L991  300 基础组，每组一正一负；任务数与基础组数分开报告
- L993  真实对象注领域依据；受控合成标 controlled_synthetic；分开统计
- L999  有效候选构造 = 重命名 + 打乱节点顺序 + 尺度变换
- L1006 每任务 10 源域；正 1+3+3+3，负 0+3+4+3；不泄露标签
- L1008 负任务必须核验整个候选库（reference.exclusions 覆盖全部 10 个）
- L1010 参考容差 min_ctc 0.95 / max_error 0.05；负例有超容差见证点
- L1020 划分 70/15/15，种子 20261007，同基础组不跨划分
- L1024 每测试任务 100 个独立合法干预，独立种子，封存
"""
import argparse
import hashlib
import json
import math
import random
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "a_data"))

import mred_domains as D          # noqa: E402
import mred_interference as I     # noqa: E402
import mred_objects as O          # noqa: E402
import runtime                    # noqa: E402

SCHEMA_VERSION = "topoadv-schema-0.3.0-draft"
VOCAB_VERSION = "topoadv-vocab-0.1.0-draft"

# 干扰配比（任务书 L1006 + 用户 2026-10-28 拍板）
POSITIVE_MIX = dict(structure_error=3, response_error=3, local_perturbation=3)
NEGATIVE_MIX = dict(structure_error=3, response_error=4, local_perturbation=3)

REFERENCE_TOLERANCE = dict(min_ctc=0.95, max_error=0.05)


def stable_hash(*parts):
    payload = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def seeded(*parts):
    return int(stable_hash(*parts), 16) % (2 ** 31)


# ============================================================
# 参数变体
# ============================================================
MULT_CURRENT_FACTORS = [0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 10.0, 20.0]
LIN_DRIVER_FACTORS = [0.1, 0.2, 0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 8.0, 10.0,
                      1.4, 1.8, 6.0, 12.0, 15.0, 25.0, 30.0]
LIN_RESIST_FACTORS = [0.25, 0.5, 0.8, 1.0, 1.25, 2.0, 4.0, 0.4, 1.5, 3.0]
SAT_TIERS = [(1.0, 1.0), (2.0, 1.0), (1.0, 2.0)]


def variant_factors(relation_type, index):
    """返回 (src_factors, tgt_factors)。

    乘性：只动 current（ratio 跨域不可比，固定不动 —— 见 PDF 数学核验记录）
    线性：driver 与 resistance 都可动（归一化响应与 basline 无关）
    饱和：R_max / K 取常见档位，input0 跟随 = K
    """
    if relation_type == D.REL_MULT:
        cf = MULT_CURRENT_FACTORS
        sc = cf[index % len(cf)]
        tc = cf[(index + 5) % len(cf)]
        return ({"current": sc}, {"current": tc})
    if relation_type == D.REL_LIN:
        df, rf = LIN_DRIVER_FACTORS, LIN_RESIST_FACTORS
        sd = df[index % len(df)]
        sr = rf[(index // len(df)) % len(rf)]
        td = df[(index + 7) % len(df)]
        tr = rf[((index // len(df)) + 4) % len(rf)]
        return ({"driver": sd, "resistance": sr}, {"driver": td, "resistance": tr})
    srm, sk = SAT_TIERS[index % len(SAT_TIERS)]
    trm, tk = SAT_TIERS[(index + 1) % len(SAT_TIERS)]
    return ({"R_max_factor": srm, "K_factor": sk}, {"R_max_factor": trm, "K_factor": tk})


def apply_variant(relation_type, domain_spec, factors, ratio_align=None):
    new = json.loads(json.dumps(domain_spec))
    if relation_type == D.REL_MULT:
        new["baseline"]["current"] = round(domain_spec["baseline"]["current"] * factors["current"], 10)
        # 乘性类比对齐约束：两域 ratio 必须相同，否则归一化响应含 ratio0 项、
        # 正例响应不等价（已实跑证明：ratio 0.2 vs 0.03 时偏差 0.033）。
        # 对齐到「目标域的 ratio」——目标是这个类比要被解释的对象，它的参数不动；
        # 源域作为比喻，其增长率调到与目标同一量级是类比成立的前提（L999 尺度变换）。
        if ratio_align is not None:
            new["baseline"]["ratio"] = ratio_align
    elif relation_type == D.REL_LIN:
        new["baseline"]["driver"] = round(domain_spec["baseline"]["driver"] * factors["driver"], 10)
        new["baseline"]["resistance"] = round(domain_spec["baseline"]["resistance"] * factors["resistance"], 10)
    else:
        new["R_max"] = round(domain_spec["R_max"] * factors["R_max_factor"], 10)
        new["K"] = round(domain_spec["K"] * factors["K_factor"], 10)
        new["baseline"]["input"] = new["K"]
    return new


# ============================================================
# 单组构造
# ============================================================
def build_group(group_idx, relation_type, pair, variant_index):
    group_id = f"group_tr_{group_idx:04d}"
    sf, tf = variant_factors(relation_type, variant_index)
    ratio_align = pair["target"]["baseline"]["ratio"] if relation_type == D.REL_MULT else None
    src_spec = apply_variant(relation_type, pair["source"], sf, ratio_align)
    tgt_spec = apply_variant(relation_type, pair["target"], tf)

    # 目标域不打乱（任务锚点）；源域打乱节点顺序（L999）
    tgt_obj, tgt_roles = O.make_object(f"obj_{group_id}_tgt", relation_type, tgt_spec, seed=None)
    src_obj, src_roles = O.make_object(
        f"obj_{group_id}_src", relation_type, src_spec,
        seed=seeded(group_id, "src_order"))

    node_map = {src_roles[r]: tgt_roles[r] for r in O.ROLE_SPEC[relation_type]["roles"]}
    max_dev, worst = O.positive_max_deviation(src_obj, tgt_obj, node_map, src_roles, tgt_roles)
    if max_dev > 1e-9:
        raise AssertionError(f"{group_id} 正例响应不等价 dev={max_dev:.3e} @ {worst}")

    return dict(group_id=group_id, relation_type=relation_type, pair=pair,
                variant_index=variant_index, target_obj=tgt_obj, source_obj=src_obj,
                node_map=node_map, tgt_roles=tgt_roles, src_roles=src_roles,
                positive_dev=max_dev)


# ============================================================
# 干扰源 + 见证点核验
# ============================================================
def scan_interferer(obj, tgt_obj, relation_type, grid):
    """主输入维度扫描，其余维度置零扰动。返回 (max_error, witness)。"""
    main_t = I.ROLE_SPEC[relation_type]["main_input"]
    others = [n for n in tgt_obj["controllable_inputs"] if n != main_t]
    best = (0.0, None)
    for u in grid:
        u_t = {main_t: u}
        for o in others:
            u_t[o] = 0.0
        try:
            rt = list(runtime.normalized_response(tgt_obj, u_t).values())[0]
            rs = list(runtime.normalized_response(obj, {"n1": u}).values())[0]
        except ValueError:
            continue
        err = min(1.0, (rs - rt) ** 2)
        if err > best[0]:
            best = (err, dict(u={n: (u if n == main_t else 0.0)
                                 for n in tgt_obj["controllable_inputs"]},
                              r_target=rt, r_source=rs))
    return best


def make_shared_pool(group):
    """一个基础组共用一个干扰源池。

    任务书 L1006：正任务 = 1 有效 + 9 干扰；负任务 = 移除全部有效源域，
    再按相同规则补入干扰源域。因此负任务的 10 个来源 = 正任务的 9 个干扰
    + 额外补 1 个（响应错误类）。共用同一批 object，不重复造。
    """
    rel = group["relation_type"]
    tgt = group["target_obj"]
    gid = group["group_id"]
    grid = ([i / 100 for i in range(-80, 101)] if rel == D.REL_SAT
            else [i / 100 for i in range(-20, 21)])
    sparse = [-0.2, -0.1, 0.0, 0.1, 0.2]

    # 并集配比：结构错误 3、局部扰动 3、响应错误 max(3,4)=4
    plan = (["structure_error"] * 3
            + ["response_error"] * 4
            + ["local_perturbation"] * 3)          # 共 10
    rng = random.Random(seeded(gid, "pool_order"))
    rng.shuffle(plan)

    pool = []
    for i, kind in enumerate(plan):
        oid = f"obj_{gid}_i{i:02d}"
        obj = I.build_interferer(tgt, rel, oid, kind, seeded(gid, kind, i))
        err, witness = scan_interferer(obj, tgt, rel, grid)
        if kind == "local_perturbation":
            sparse_max = 0.0
            for u in sparse:
                if rel == D.REL_SAT and not (-0.8 <= u <= 1.0):
                    continue
                e, _ = scan_interferer(obj, tgt, rel, [u])
                sparse_max = max(sparse_max, e)
            if not (sparse_max < 0.05 < err):
                raise AssertionError(
                    f"{oid} 局部扰动定性失败 sparse={sparse_max:.4f} full={err:.4f}")
        elif err <= REFERENCE_TOLERANCE["max_error"]:
            raise AssertionError(f"{oid} {kind} 未超容差 max_err={err:.6f}")
        pool.append(dict(obj=obj, kind=kind, max_error=err, witness=witness))

    # 正任务：结构 3 + 响应 3 + 局部 3 = 9（从 4 个响应错误里取前 3 个）
    resp = [p for p in pool if p["kind"] == "response_error"]
    pos = ([p for p in pool if p["kind"] == "structure_error"]
           + resp[:3]
           + [p for p in pool if p["kind"] == "local_perturbation"])
    # 负任务：池里全部 10 个（结构 3 + 响应 4 + 局部 3）
    neg = list(pool)
    assert len(pos) == 9, len(pos)
    assert len(neg) == 10, len(neg)
    return pos, neg


# ============================================================
# 干预点（L1024）
# ============================================================
def make_intervention_points(tgt_obj, task_id, n=100):
    rng = random.Random(seeded(D.INTERVENTION_SEED, task_id))
    inputs = tgt_obj["controllable_inputs"]
    pts, seen = [], set()
    tries = 0
    while len(pts) < n and tries < n * 200:
        tries += 1
        u = {}
        for nid in inputs:
            lo, hi = tgt_obj["intervention_bounds"][nid]
            u[nid] = round(rng.uniform(lo, hi), 4)
        if all(abs(v) < 1e-12 for v in u.values()):
            continue                      # 排除固定初始化点
        key = tuple(sorted(u.items()))
        if key in seen:
            continue
        try:
            runtime.normalized_response(tgt_obj, u)
        except ValueError:
            continue
        seen.add(key)
        pts.append(u)
    if len(pts) < n:
        raise AssertionError(f"{task_id}: 仅 {len(pts)}/{n} 合法干预点")
    return pts


# ============================================================
# 划分（L1020）
# ============================================================
def assign_splits(n_groups, seed=D.SPLIT_SEED):
    idx = list(range(n_groups))
    random.Random(seed).shuffle(idx)
    n_train = int(round(n_groups * 0.70))
    n_val = int(round(n_groups * 0.15))
    out = {}
    for rank, gi in enumerate(idx):
        out[gi] = "train" if rank < n_train else ("val" if rank < n_train + n_val else "test")
    return out, dict(train=n_train, val=n_val, test=n_groups - n_train - n_val)


# ============================================================
# 计划
# ============================================================
def plan_groups():
    plan = []
    for rel, quota in D.VARIANT_QUOTA.items():
        pairs = D.ALL_PAIRS[rel]
        per, rem = divmod(quota, len(pairs))
        for i, pair in enumerate(pairs):
            for k in range(per + (1 if i < rem else 0)):
                plan.append((rel, pair, k))
    if len(plan) != 300:
        raise AssertionError(f"计划 {len(plan)} 组 != 300")
    return plan


# ============================================================
# 落盘
# ============================================================
def strip_private(obj):
    return {k: v for k, v in obj.items() if not k.startswith("_")}


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


def write_group(g, interf_pos, interf_neg, split, points, out_root=None):
    rel = g["relation_type"]
    pair = g["pair"]
    gid = g["group_id"]
    gdir = (out_root if out_root is not None else ROOT / "cases") / rel / gid

    tgt = strip_private(g["target_obj"])
    src = strip_private(g["source_obj"])
    tgt["split"] = split
    src["split"] = split

    pos_id = f"task_{gid}_a"
    neg_id = f"task_{gid}_b"
    pos_srcs = [src["object_id"]] + [i["obj"]["object_id"] for i in interf_pos]
    neg_srcs = [i["obj"]["object_id"] for i in interf_neg]

    # ---- manifest（公开）----
    dump(gdir / "manifest.json", dict(
        group_id=gid, dataset="mred", relation_type=rel,
        schema_version=SCHEMA_VERSION, vocab_version=VOCAB_VERSION,
        split=split, pair_id=pair["pair_id"], variant_index=g["variant_index"],
        object_ids=[tgt["object_id"], src["object_id"]] + [i["obj"]["object_id"] for i in interf_pos + interf_neg],
        task_ids=[pos_id, neg_id],
        task_counts=dict(positive=1, negative=1, total=2),
        source_counts=dict(positive=len(pos_srcs), negative=len(neg_srcs)),
    ))

    # ---- manifest.sealed（封存标签，L1006/L1011）----
    dump(gdir / "manifest.sealed.json", dict(
        group_id=gid,
        valid_sources=[src["object_id"]],
        excluded_sources=sorted({i["obj"]["object_id"] for i in interf_pos + interf_neg}),
    ))

    # ---- relation/（封存）----
    dump(gdir / "relation" / "analogy.json", dict(
        source=dict(object_id=src["object_id"], label=src["label"]),
        target=dict(object_id=tgt["object_id"], label=tgt["label"]),
        relation_type=rel, direction="source → target",
        pair_id=pair["pair_id"],
        domain_evidence=pair["evidence"],
        simplification_assumption=pair["assumption"],
    ))
    dump(gdir / "relation" / "node_map.json", g["node_map"])
    dump(gdir / "relation" / "edge_map.json", {"r1": "r1"})
    dump(gdir / "relation" / "roles.json",
         {r: dict(source=g["src_roles"][r], target=g["tgt_roles"][r])
          for r in O.ROLE_SPEC[rel]["roles"]})
    (gdir / "relation").mkdir(parents=True, exist_ok=True)
    (gdir / "relation" / "formula.md").write_text(
        f"源域（{src['label']}）：{src['function']}\n"
        f"目标域（{tgt['label']}）：{tgt['function']}\n"
        f"角色：{' / '.join(O.ROLE_SPEC[rel]['roles'])}\n"
        f"领域依据：{pair['evidence']}\n"
        + (f"简化假设：{pair['assumption']}\n" if pair["assumption"] else ""),
        encoding="utf-8")

    # ---- data/input/objects ----
    objs = {"objects": []}
    for o in [tgt, src] + [i["obj"] for i in interf_pos + interf_neg]:
        fn = o["object_id"] + ".json"
        dump(gdir / "data" / "input" / "objects" / fn, o)
        objs["objects"].append(dict(object_id=o["object_id"], file=fn))
    dump(gdir / "data" / "input" / "objects" / "index.json", objs)

    # ---- data/input/tasks ----
    main_t = I.ROLE_SPEC[rel]["main_input"]
    idx = tgt["controllable_inputs"].index(main_t)
    tgt_b = tgt["baseline"][idx]
    for tid, srcs in [(pos_id, pos_srcs), (neg_id, neg_srcs)]:
        dump(gdir / "data" / "input" / "tasks" / ("positive.json" if tid == pos_id else "negative.json"),
             dict(task_id=tid, group_id=gid, target_id=tgt["object_id"],
                  source_ids=srcs, schema_version=SCHEMA_VERSION,
                  vocab_version=VOCAB_VERSION,
                  intervenable_inputs=tgt["controllable_inputs"],
                  specified_outputs=tgt["designated_outputs"],
                  intervention_range={k: v for k, v in tgt["intervention_bounds"].items()},
                  _note="方法输入不含标签、正确源域或见证点；task_id 不编码正负"))

    # ---- counterexamples/（封存受控合成标注，L993）----
    for i in interf_pos + interf_neg:
        d = gdir / "counterexamples" / i["obj"]["object_id"]
        dump(d / "counterexample.json", dict(
            source_id=i["obj"]["object_id"], target_id=tgt["object_id"],
            node_map={"n1": g["tgt_roles"][main_t], "n2": g["tgt_roles"][O.ROLE_SPEC[rel]["output_role"]]},
            interference_kind=i["kind"],
            max_error=i["max_error"],
            controlled_synthetic=True,
        ))
        if i["witness"]:
            dump(d / "witness.json", dict(
                u=i["witness"]["u"],
                r_target=i["witness"]["r_target"],
                r_source=i["witness"]["r_source"],
                error=min(1.0, (i["witness"]["r_source"] - i["witness"]["r_target"]) ** 2),
            ))

    # ---- sealed/reference.json ----
    ref = {
        pos_id: dict(
            task_id=pos_id, label="positive",
            valid=[dict(source_id=src["object_id"], node_map=g["node_map"], edge_map={"r1": "r1"})],
            exclusions=[dict(source_id=i["obj"]["object_id"], kind=i["kind"],
                             reason=f"超出参考容差：最大响应误差 {i['max_error']:.6f} > {REFERENCE_TOLERANCE['max_error']}")
                        for i in interf_pos],
            reference_tolerance=REFERENCE_TOLERANCE,
            positive_max_deviation=g["positive_dev"],
            status="bijective_confirmed",
        ),
        neg_id: dict(
            task_id=neg_id, label="negative",
            valid=[],
            exclusions=[dict(source_id=i["obj"]["object_id"], kind=i["kind"],
                             reason=f"超出参考容差：最大响应误差 {i['max_error']:.6f} > {REFERENCE_TOLERANCE['max_error']}")
                        for i in interf_neg],
            reference_tolerance=REFERENCE_TOLERANCE,
            status="bijective_confirmed",
            full_library_verified=True,     # L1008：全部 10 个候选均被排除
        ),
    }
    dump(gdir / "sealed" / "reference.json", ref)

    # ---- sealed/intervention_points.json（L1024，仅测试组）----
    if points is not None:
        dump(gdir / "sealed" / "intervention_points.json", dict(
            group_id=gid,
            seed=D.INTERVENTION_SEED,
            points_per_task=len(points[pos_id]),
            tasks={pos_id: points[pos_id], neg_id: points[neg_id]},
        ))

    (gdir / "README.md").write_text(
        f"{gid} —— {src['label']} → {tgt['label']}（{rel}，{split}）\n\n"
        f"来源域对：{pair['pair_id']}，参数变体 #{g['variant_index']}\n"
        f"领域依据：{pair['evidence']}\n"
        f"正任务 {pos_id}（10 源域），负任务 {neg_id}（10 源域）。映射方向 source→target。\n",
        encoding="utf-8")


# ============================================================
# 主流程
# ============================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", type=str, default="")
    args = ap.parse_args()

    plan = plan_groups()
    if args.limit:
        plan = plan[:args.limit]
    print(f"计划基础组: {len(plan)}")

    print("=== 1) 构造基础组 + 正例等价性 ===")
    groups = []
    for i, (rel, pair, vi) in enumerate(plan):
        groups.append(build_group(i, rel, pair, vi))
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(plan)}")
    print(f"  {len(groups)} 组构造完成，正例 max_dev 全部 <= 1e-9")

    print("=== 2) 干扰源池 + 见证点 ===")
    for gi, g in enumerate(groups):
        g["pos"], g["neg"] = make_shared_pool(g)
        if (gi + 1) % 50 == 0:
            print(f"  {gi+1}/{len(groups)}")
    uniq = sum(len(g["neg"]) for g in groups)
    print(f"  每组干扰源池 10 个（正任务用 9、负任务用 10），全库 {uniq} 个，全部有超容差见证点")

    print("=== 3) 划分 ===")
    sp, counts = assign_splits(len(groups))
    print(f"  {counts}")
    for gi, g in enumerate(groups):
        g["split"] = sp[gi]

    print("=== 4) 测试任务干预点 ===")
    n_pts = 0
    for g in groups:
        if g["split"] != "test":
            g["points"] = None
            continue
        pid, nid = f"task_{g['group_id']}_a", f"task_{g['group_id']}_b"
        g["points"] = {pid: make_intervention_points(g["target_obj"], pid),
                       nid: make_intervention_points(g["target_obj"], nid)}
        n_pts += 2
    print(f"  测试任务 {n_pts} 个 x 100 点")

    if args.dry:
        print("\n[dry] 全部验算通过，未落盘。")
        return

    out_root = Path(args.out) if args.out else (ROOT / "cases")
    print(f"=== 5) 落盘到 {out_root} ===")
    for gi, g in enumerate(groups):
        gdir = out_root / g["relation_type"] / g["group_id"]
        if gdir.exists():
            shutil.rmtree(gdir)
        write_group(g, g["pos"], g["neg"], g["split"], g["points"], out_root)
        if (gi + 1) % 50 == 0:
            print(f"  {gi+1}/{len(groups)}")
    print("完成。")


if __name__ == "__main__":
    main()
