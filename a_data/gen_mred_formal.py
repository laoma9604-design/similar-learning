"""MRED 正式库生成主程序（v2）。

规模：300 基础组 / 600 任务 / 每任务 10 源域 / 三类干扰 / 测试任务各 100 干预点 / 70-15-15

用法：
    python a_data/gen_mred_formal.py --dry
    python a_data/gen_mred_formal.py --limit 3 --out /tmp/x
    python a_data/gen_mred_formal.py

v2 修复（2026-11-01 评审四条问题，全部经实测确认后修）：

【问题1】响应反例结构不兼容 —— 276 组目标 3 节点、干扰源 2 节点，双射不成立
  修：干扰源改为与目标域同构（同节点数/同角色/同端点），唯一差异是函数。
      三类干扰都能通过结构检查、进入响应检验。见 mred_interference v2。

【问题2】参数变体跨划分 —— 21/25 个域对跨多个划分；乘性类 4636 对完全相同的签名
  修：(a) 划分单位改为「基础对象组 + 其全部派生」，即同一 pair 的变体
          全部并入同一划分（L1020）。
      (b) 乘性类补上真正的参数轴：ratio 也按档位变化（ratio 跨域不可比
          的问题由「同组内 ratio 对齐到目标」解决，即组内 ratio 一致、
          跨组 ratio 变化），否则变体之间签名完全相同（L999 尺度变换）。

【问题3】公开输入泄漏标签 —— 300/300 组可被 label/命名/顺序直接判出答案
  修：文件名去标签（task_NNNN_p/q → 统一 t01/t02 之外的中性编号）、
      候选源列表按组哈希打乱、所有候选源 label 统一、节点 ID 共用同一池、
      正负任务的干扰源 ID 不再复用同一批、节点标签中性化（L1006）。

【问题4】全库排除证据不足 —— full_library_verified 是常量，无见证、无枚举
  修：负任务在封存侧记录 allowed_mappings_total（类型兼容映射的全枚举数）、
      rejected_mappings（逐个说明被哪一项拒绝）、
      每个干扰源附完整见证（二维 u、两域原始输出、归一化响应、误差），
      full_library_verified 改为由枚举结果算出的布尔值（L1008）。

其它按任务书补齐的细节：
- L1010 参考容差：min_ctc 0.95 / max_error 0.05，属于数据版本
- L1024 测试任务 100 个独立合法干预，独立种子，排除固定初始化点
- L993  真实领域对象注来源；受控合成标 controlled_synthetic，分开统计
- L986  允许多个有效映射时保存映射集合或判定条件
- L1008 重复模块存在置换对称时检查所有置换 → 位移类干扰（对称反例）
"""
import argparse
import hashlib
import itertools
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

SCHEMA_VERSION = "topoadv-schema-0.3.1"
VOCAB_VERSION = "topoadv-vocab-0.1.1"

# 干扰配比（L1006 + 用户 2026-10-28 拍板）
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
# 档位数必须与「每域对变体数」互质或不等周期，否则 variant 与 variant+k
# 会取到同一组合（实测 12 档位 vs 12 变体，第 2 与第 14 组对象完全相同）。
MULT_CURRENT_FACTORS = [0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 3.0, 5.0, 8.0,
                        10.0, 20.0, 0.02, 0.3, 1.5, 4.0, 7.0]
LIN_DRIVER_FACTORS = [0.1, 0.2, 0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 8.0,
                      10.0, 1.4, 1.8, 6.0, 12.0, 15.0, 25.0, 30.0]
LIN_RESIST_FACTORS = [0.25, 0.5, 0.8, 1.0, 1.25, 2.0, 4.0, 0.4, 1.5, 3.0]
SAT_TIERS = [(1.0, 1.0), (2.0, 1.0), (1.0, 2.0)]

# 乘性类 ratio 档位：组内两域取同一档（保证正例响应等价），
# 组间随变体改变（保证变体真的不同，修问题 2b）
MULT_RATIO_TIERS = [0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5]


def variant_factors(relation_type, index, variant_index):
    """返回 (src_factors, tgt_factors, ratio_tier)。

    index：该域对在本类中的第几组（决定 ratio 档位轮换）
    variant_index：参数变体序号
    """
    if relation_type == D.REL_MULT:
        cf = MULT_CURRENT_FACTORS
        sc = cf[variant_index % len(cf)]
        tc = cf[(variant_index + 5) % len(cf)]
        ratio_tier = MULT_RATIO_TIERS[index % len(MULT_RATIO_TIERS)]
        return ({"current": sc}, {"current": tc}, ratio_tier)
    if relation_type == D.REL_LIN:
        df, rf = LIN_DRIVER_FACTORS, LIN_RESIST_FACTORS
        sd = df[variant_index % len(df)]
        sr = rf[(variant_index // len(df)) % len(rf)]
        td = df[(variant_index + 7) % len(df)]
        tr = rf[((variant_index // len(df)) + 4) % len(rf)]
        return ({"driver": sd, "resistance": sr},
                {"driver": td, "resistance": tr}, None)
    srm, sk = SAT_TIERS[variant_index % len(SAT_TIERS)]
    trm, tk = SAT_TIERS[(variant_index + 1) % len(SAT_TIERS)]
    return ({"R_max_factor": srm, "K_factor": sk},
            {"R_max_factor": trm, "K_factor": tk}, None)


def apply_variant(relation_type, domain_spec, factors, ratio_tier=None):
    new = json.loads(json.dumps(domain_spec))
    if relation_type == D.REL_MULT:
        new["baseline"]["current"] = round(domain_spec["baseline"]["current"] * factors["current"], 10)
        # 两域 ratio 必须相同，否则归一化响应含 ratio0 项、正例不等价。
        # 档位由组决定：组内一致（正例成立），跨组变化（变体真的有差异）。
        new["baseline"]["ratio"] = ratio_tier
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
def build_group(group_idx, relation_type, pair, variant_index, pair_rank,
                prefix="tr"):
    group_id = f"group_{prefix}_{group_idx:04d}"
    sf, tf, ratio_tier = variant_factors(relation_type, pair_rank, variant_index)
    src_spec = apply_variant(relation_type, pair["source"], sf, ratio_tier)
    tgt_spec = apply_variant(relation_type, pair["target"], tf, ratio_tier)

    # 目标域、有效源、干扰源全部从同一节点 ID 池分派（防命名泄露）。
    # 关键：同一基础组内，两域以及全部干扰源的「角色 -> 节点 ID」必须一致，
    # 否则按角色对齐 u 会把扰动施加到错误的节点上（第一版踩过）。
    # 节点在列表中的顺序可以随机（L999 打乱顺序），ID 本身不能各抽各的。
    shared_ids = O.assign_node_ids(relation_type, seeded(group_id, "shared_ids"))
    tgt_ids = shared_ids
    src_ids = shared_ids

    tgt_obj, tgt_roles = O.make_object(
        f"obj_{group_id}_tgt", relation_type, tgt_spec, tgt_ids,
        label=pair["target"]["object_label"], public_label=O.PUBLIC_TARGET_LABEL)
    src_obj, src_roles = O.make_object(
        f"obj_{group_id}_src", relation_type, src_spec, src_ids,
        label=pair["source"]["object_label"])

    node_map = {src_roles[r]: tgt_roles[r] for r in O.ROLE_SPEC[relation_type]["roles"]}
    max_dev, worst = O.positive_max_deviation(src_obj, tgt_obj, node_map)
    if max_dev > 1e-9:
        raise AssertionError(f"{group_id} 正例响应不等价 dev={max_dev:.3e} @ {worst}")

    # 源域与目标域不能完全相同：两个一模一样的对象之间没有「类比」可做，
    # 且会让「挑出与目标同构的那个」退化成字符串比对（实测有 3 组撞车）。
    # 撞车时把源域再用下一个变体档位重算一次（同理，重算后仍撞车即报错）。
    if (src_obj["function"] == tgt_obj["function"]
            and [round(x, 10) for x in src_obj["baseline"]]
            == [round(x, 10) for x in tgt_obj["baseline"]]):
        sf, tf, ratio_tier = variant_factors(relation_type, pair_rank,
                                            variant_index + 1)
        src_spec = apply_variant(relation_type, pair["source"], sf, ratio_tier)
        src_obj, src_roles = O.make_object(
            f"obj_{group_id}_src", relation_type, src_spec, src_ids,
            label=pair["source"]["object_label"])
        node_map = {src_roles[r]: tgt_roles[r]
                    for r in O.ROLE_SPEC[relation_type]["roles"]}
        max_dev, worst = O.positive_max_deviation(src_obj, tgt_obj, node_map)
        if max_dev > 1e-9:
            raise AssertionError(f"{group_id} 正例响应不等价（重算后）"
                                 f"dev={max_dev:.3e} @ {worst}")
        if (src_obj["function"] == tgt_obj["function"]
                and [round(x, 10) for x in src_obj["baseline"]]
                == [round(x, 10) for x in tgt_obj["baseline"]]):
            raise AssertionError(f"{group_id} 源域与目标域完全相同，无法构成类比")

    return dict(group_id=group_id, relation_type=relation_type, pair=pair,
                pair_rank=pair_rank, variant_index=variant_index,
                target_obj=tgt_obj, source_obj=src_obj,
                node_map=node_map, tgt_roles=tgt_roles, src_roles=src_roles,
                positive_dev=max_dev)


# ============================================================
# 干扰源池 + 全库见证
# ============================================================
def u_grid_for(relation_type, target_obj=None, dense=True):
    """目标侧的 u 采样网格，键为目标域的节点 ID（二维时为笛卡尔积）。

    dense=True  用于参考判定的全库枚举（二维 41x41 = 1681 点）
    dense=False 用于局部扰动的「稀疏点容易通过」核验（5 点/维）
    """
    spec = I.ROLE_SPEC[relation_type]
    lo, hi = spec["bounds"]
    if dense:
        axes = [i / 20 for i in range(int(round(lo * 20)), int(round(hi * 20)) + 1)]
        step = 0.05
    else:
        axes = [lo, lo / 2, 0.0, hi / 2, hi]
        step = None
    in_roles = spec["input_roles"]
    if target_obj is None:
        keys = in_roles
    else:
        role_of = {}
        for e in target_obj["edges"]:
            role_of.update({n: r for n, r in e["roles"].items()})
        node_by_role = {r: n for n, r in role_of.items()}
        keys = [node_by_role[r] for r in in_roles]
    if len(keys) == 1:
        return [{keys[0]: u} for u in axes]
    return [dict(zip(keys, combo)) for combo in itertools.product(axes, axes)]


def fine_grid_for(relation_type, target_obj, center, half_width=0.04, step=0.005):
    """在粗网格最坏点附近加密（L1002「用独立高覆盖检查定位见证区间」）。"""
    import math as _m
    spec = I.ROLE_SPEC[relation_type]
    roles = spec["input_roles"]
    role_of = {}
    for e in target_obj["edges"]:
        role_of.update({n: r for n, r in e["roles"].items()})
    node_by_role = {r: n for n, r in role_of.items()}
    keys = [node_by_role[r] for r in roles]
    axes = []
    for k in keys:
        c = center.get(k, 0.0) if center else 0.0
        n = int(_m.floor(half_width / step))
        axes.append([round(c + i * step, 6) for i in range(-n, n + 1)])
    if len(keys) == 1:
        return [{keys[0]: u} for u in axes[0]]
    return [dict(zip(keys, combo)) for combo in itertools.product(*axes)]


def sparse_probe_points(relation_type, target_obj):
    """L175 的稀疏检查点：每维各取五个点，**其余维置 0**。

    五点取值按该对象的干预区间取（不是固定 ±0.2）：
      · 乘性/线性类区间 ±0.2 → −0.2/−0.1/0/0.1/0.2（即任务书原例）
      · 饱和类区间 [−0.8, 1.0] → 该区间的 0/25%/50%/75%/100% 分位
    不是全部笛卡尔积：任务书的「五个固定检查点」是沿单一输入方向的五点，
    二维输入下每个方向各五点，避免第二维同时偏移而意外命中鼓包。
    """
    spec = I.ROLE_SPEC[relation_type]
    role_of = {}
    for e in target_obj["edges"]:
        role_of.update({n: r for n, r in e["roles"].items()})
    node_by_role = {r: n for n, r in role_of.items()}
    keys = [node_by_role[r] for r in spec["input_roles"]]
    lo, hi = spec["bounds"]
    if abs(lo + 0.2) < 1e-9 and abs(hi - 0.2) < 1e-9:
        vals = [-0.2, -0.1, 0.0, 0.1, 0.2]
    else:
        vals = [lo + (hi - lo) * q for q in (0.0, 0.25, 0.5, 0.75, 1.0)]
    pts = []
    for d in range(len(keys)):
        for v in vals:
            u = {k: 0.0 for k in keys}
            u[keys[d]] = round(v, 6)
            pts.append(u)
    return pts


def map_u_to_source(u_t, src_obj, tgt_obj, node_map):
    """把目标侧 u（按目标节点 ID）翻成源侧 u（按源节点 ID），角色对齐。"""
    tgt_to_src = {v: k for k, v in node_map.items()}
    return {tgt_to_src[k]: v for k, v in u_t.items()}


_SCAN_CACHE = {}


def scan_interferer(src_obj, tgt_obj, node_map, relation_type, grid, tag=""):
    """在完整网格上找最大误差与见证点；两域用同一个 u（按角色对齐）。

    结果按 (对象ID, node_map, 网格签名) 缓存：正任务库和负任务库对同一个
    干扰源要各判一次，缓存后只算一遍，否则全量跑不动（实测 4 分钟仍未过半）。
    """
    key = (src_obj["object_id"], tgt_obj["object_id"],
           tuple(sorted(node_map.items())), relation_type, tag,
           len(grid),
           tuple(tuple(sorted(g.items())) for g in grid[:3]),
           tuple(tuple(sorted(g.items())) for g in grid[-3:]))
    if key in _SCAN_CACHE:
        return _SCAN_CACHE[key]
    sg = []
    for u_t in grid:
        sg.append((map_u_to_source(u_t, src_obj, tgt_obj, node_map), u_t))
    res = O.scan_error(src_obj, tgt_obj, sg)
    _SCAN_CACHE[key] = res
    return res


def make_shared_pool(group):
    """一个基础组共用一个干扰源池。

    L1006：正任务 = 1 有效 + 9 干扰；负任务 = 移除全部有效源域，
    再按相同规则补入干扰源域，总数仍为 10。
    """
    rel = group["relation_type"]
    tgt = group["target_obj"]
    gid = group["group_id"]
    src_ids = group["src_roles"]
    node_map = group["node_map"]
    dense = u_grid_for(rel, tgt, dense=True)
    sparse_grid = u_grid_for(rel, tgt, dense=False)

    plan = (["structure_error"] * 3
            + ["response_error"] * 4
            + ["local_perturbation"] * 3)          # 共 10
    rng = random.Random(seeded(gid, "pool_order"))
    rng.shuffle(plan)

    pool = []
    kind_seen = {}
    for i, kind in enumerate(plan):
        oid = f"obj_{gid}_i{i:02d}"
        # 干扰源沿用同一份「角色 -> 节点 ID」，保证 u 按角色对齐时落在正确节点上
        ids = O.assign_node_ids(rel, seeded(gid, "shared_ids"))
        # 同类干扰源的序号：让同一组内同类源彼此不同（L991 候选库不能虚增）
        variant = kind_seen.get(kind, 0)
        kind_seen[kind] = variant + 1
        obj = I.build_interferer(tgt, rel, oid, kind, ids, variant=variant)
        err, witness = scan_interferer(obj, tgt, node_map, rel, dense)

        if kind == "local_perturbation":
            # L1002：局部反例必须「稀疏点容易通过、稠密点失败」。
            # 鼓包幅度 0.3、宽 0.03，粗网格（步长 0.05）会错过峰值，
            # 因此在粗网格最坏点附近加密，用「独立高覆盖检查」定位见证。
            cen = witness["u_target"] if witness else {}
            # 在粗网格最坏点的邻域加密；同时补一段覆盖鼓包标称位置
            # （u_main=0.13）的窗口，避免粗网格把最坏点偏到鼓包外。
            fine = fine_grid_for(rel, tgt, cen, half_width=0.05, step=0.005)
            role_of = {}
            for e in tgt["edges"]:
                role_of.update({n: r for n, r in e["roles"].items()})
            main_role = I.ROLE_SPEC[rel]["input_roles"][0]
            bump_center = dict(cen)
            bump_center[role_of and [n for n, r in role_of.items() if r == main_role][0]] = 0.13
            fine += fine_grid_for(rel, tgt, bump_center, half_width=0.05, step=0.005)
            err_f, wit_f = scan_interferer(obj, tgt, node_map, rel, fine, tag="fine")
            if err_f > err:
                err, witness = err_f, wit_f
            sparse_max = 0.0
            for u_t in sparse_probe_points(rel, tgt):
                u_s = map_u_to_source(u_t, obj, tgt, node_map)
                try:
                    rt = list(runtime.normalized_response(tgt, u_t).values())[0]
                    rs = list(runtime.normalized_response(obj, u_s).values())[0]
                except ValueError:
                    continue
                sparse_max = max(sparse_max, min(1.0, (rs - rt) ** 2))
            if not (sparse_max < REFERENCE_TOLERANCE["max_error"] < err):
                raise AssertionError(
                    f"{oid} 局部扰动定性失败 sparse={sparse_max:.4f} fine={err:.4f}")
        elif kind == "structure_error":
            # 结构错误类：必须确定不满足式(eq:structure)，
            # 而且是与目标域节点数相同的完整映射（这正是第一版缺的）
            ok, reason = I.structure_ok(obj, tgt)
            if ok:
                raise AssertionError(f"{oid} 结构错误源竟然通过了结构检查")
            if len(obj["nodes"]) != len(tgt["nodes"]):
                raise AssertionError(f"{oid} 节点数与目标域不等")
        else:
            # 响应错误类：结构必须完全通过，只有响应超容差
            ok, reason = I.structure_ok(obj, tgt)
            if not ok:
                raise AssertionError(f"{oid} 响应错误源结构未通过：{reason}")
            if err <= REFERENCE_TOLERANCE["max_error"]:
                raise AssertionError(f"{oid} 响应错误源未超容差 max_err={err:.6f}")

        pool.append(dict(obj=obj, kind=kind, max_error=err, witness=witness,
                         nodes_by_role=ids))

    pos = ([p for p in pool if p["kind"] == "structure_error"]
           + [p for p in pool if p["kind"] == "response_error"][:3]
           + [p for p in pool if p["kind"] == "local_perturbation"])
    neg = list(pool)
    assert len(pos) == 9, len(pos)
    assert len(neg) == 10, len(neg)
    assert len({p["obj"]["object_id"] for p in neg}) == 10
    # 候选库不能虚增：10 个干扰源的对象内容必须两两不同
    # （早期版本同类干扰源函数完全一样、只有 ID 不同，等于把 3 个候选报成 10 个）
    sigs = {(p["obj"]["function"], tuple(p["obj"]["baseline"]),
             tuple(p["obj"]["controllable_inputs"])) for p in neg}
    if len(sigs) != 10:
        raise AssertionError(
            f"{gid}: 干扰源池只有 {len(sigs)} 个不同对象（应为 10）")
    return pos, neg


# ============================================================
# 全库枚举：类型兼容的一一映射 + 逐个判定（L1008）
# ============================================================
def full_library_check(tgt_obj, sources, rel, node_maps):
    """对候选库做完整枚举。

    sources: list[dict(obj=..., kind=..., ...)]
    返回 dict(total, valid, rejected, verified)

    判据口径（与 a_data/verify_mred.py 完全一致，两边必须能对上）：
      · 结构：check_structure_condition（含 L1000 端点依赖探测）
      · 响应：在**统一的 0.05 步长网格**上算 max min(1,(rs-rt)^2)，
        超过参考容差即排除。不再依赖加密网格兜底 —— 加密网格会让
        「排除」的结论取决于扫描精度，第三方复算对不上（实测踩过：
        粗网格 0.0414 判有效，加密后 0.09 判无效）。
      · 每个被排除的源域都在顶层附 witness（最坏点、两域输出、误差），
        第三方只读 reference.json 就能复算，不必翻 counterexamples/
    """
    total = 0
    valid = []
    rejected = []
    for item in sources:
        obj = item["obj"]
        cands = O.enumerate_allowed_mappings(obj, tgt_obj)
        total += len(cands)
        found_valid = None
        reasons = []
        worst_err = 0.0
        worst_wit = None
        for fV, fE in cands:
            ok, fails = O.check_structure_condition(obj, tgt_obj, fV, fE)
            if not ok:
                reasons.append(dict(node_map=fV, failed_checks=fails,
                                    verdict="结构失败"))
                continue
            grid = u_grid_for(rel, tgt_obj, dense=True)
            err, wit = scan_interferer(obj, tgt_obj, fV, rel, grid, tag="enum")
            if err > worst_err:
                worst_err, worst_wit = err, dict(wit, node_map=fV)
            if err > REFERENCE_TOLERANCE["max_error"]:
                reasons.append(dict(node_map=fV, failed_checks=["响应超容差"],
                                    verdict="响应失败", max_error=err))
                continue
            found_valid = dict(node_map=fV, edge_map=fE, max_error=err)
            break
        if found_valid is not None:
            valid.append(dict(source_id=obj["object_id"], **found_valid))
        else:
            rejected.append(dict(source_id=obj["object_id"], kind=item["kind"],
                                 candidate_mappings=len(cands),
                                 max_error=worst_err, witness=worst_wit,
                                 detail=reasons))
    # 全库核验成立的条件：
    #   (a) 枚举总数 > 0，且每个源域的候选映射都被枚举过；
    #   (b) 没有任何源域存在有效映射。
    # 排除理由必须逐源给足，但不同类别的证据强度不同：
    #   · 结构错误类 —— 全部映射在「节点/超边双射、类型、端点、角色、
    #     端点依赖」任一结构项上失败，这比响应超容差更强，不要求响应误差
    #     （这类源的函数往往在正确映射下响应完全一致，故意如此构造，
    #      用来单独检验 A03「去除离散结构校验」会放出多少候选）。
    #   · 响应错误 / 局部扰动类 —— 结构全部通过，必须有超过参考容差的
    #     见证响应误差（局部扰动类还要求稀疏点仍通过）。
    struct_bad = {"structure_error"}
    ok_reason = all(
        (r["kind"] in struct_bad and all(d["verdict"] == "结构失败" for d in r["detail"]))
        or (r["kind"] not in struct_bad and r["max_error"] > REFERENCE_TOLERANCE["max_error"])
        for r in rejected
    )
    verified = (len(valid) == 0 and total > 0
                and all(r["candidate_mappings"] >= 1 for r in rejected)
                and ok_reason)
    return dict(allowed_mappings_total=total, valid=valid,
                rejected=rejected, verified=verified, tolerance=REFERENCE_TOLERANCE)


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
# 划分（L1020）：划分单位 = 基础对象组 + 其全部派生
# ============================================================
def assign_splits_by_pair(groups):
    """按「域对 + 基础对象组」整体划分，同一 pair 的全部变体进同一划分。

    300 组 / 25 个域对 = 每对 12 组。pair 是不可分单位，因此比例只能在
    pair 边界上逼近 70/15/15。做法：对 pair 的排列顺序，在所有可能的分割点
    (i, j) 上选使 |train-210|+|val-45|+|test-45| 最小的一组，保证尽量接近，
    同时满足 L1020「同一对象的改写、参数变体、派生映射和正负任务留在同一组」
    与「跨任务共享的相同对象与派生对象须合并分组或从跨划分复用中移除」。
    """
    from collections import defaultdict
    by_pair = defaultdict(list)
    for g in groups:
        by_pair[(g["relation_type"], g["pair"]["pair_id"])].append(g)

    rng = random.Random(D.SPLIT_SEED)
    keys = list(by_pair.keys())
    rng.shuffle(keys)
    sizes = [len(by_pair[k]) for k in keys]
    total = sum(sizes)
    want = (round(total * 0.70), round(total * 0.15), total - round(total * 0.70)
            - round(total * 0.15))

    best = None
    for i in range(1, len(sizes)):
        for j in range(i + 1, len(sizes)):
            a = sum(sizes[:i])
            b = sum(sizes[i:j])
            c = sum(sizes[j:])
            cost = abs(a - want[0]) + abs(b - want[1]) + abs(c - want[2])
            if best is None or cost < best[0]:
                best = (cost, i, j)
    if best is None:
        # 小批量试跑（--limit）时 pair 太少，切不出三段：全部给 train
        _, i, j = 0, len(sizes), len(sizes)
    else:
        _, i, j = best

    assign = {}
    for idx, key in enumerate(keys):
        split = "train" if idx < i else ("val" if idx < j else "test")
        for g in by_pair[key]:
            assign[g["group_id"]] = split
    return assign


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
                plan.append(dict(relation_type=rel, pair=pair, variant_index=k,
                                 pair_rank=i))
    if len(plan) != 300:
        raise AssertionError(f"计划 {len(plan)} 组 != 300")
    return plan


def plan_dev_groups(n=30):
    """L991：第一批开发数据 30 个基础组，用于联调实现与检查标注流程。

    与正式库的区别（其余全部相同）：
      · 组 ID 前缀 group_dev_，不进 splits.csv / reference_all.jsonl
      · split 一律记 dev，不参与 70/15/15 划分
      · 每个域对轮转取变体，保证三类关系都覆盖到（按 quota 比例分配）
    """
    plan = []
    rels = list(D.VARIANT_QUOTA.keys())
    # 30 组按三类关系的正式配额比例分：乘性 15、线性 13、饱和 2（最小 1）
    alloc = {"multiplicative_growth": 15, "linear_drive_resistance": 13,
             "saturation_response": 2}
    assert sum(alloc.values()) == n, sum(alloc.values())
    for rel in rels:
        pairs = D.ALL_PAIRS[rel]
        quota = alloc[rel]
        for k in range(quota):
            pair = pairs[k % len(pairs)]
            plan.append(dict(relation_type=rel, pair=pair, variant_index=k,
                             pair_rank=k % len(pairs), is_dev=True))
    if len(plan) != n:
        raise AssertionError(f"开发组计划 {len(plan)} != {n}")
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


def write_group(g, interf_pos, interf_neg, split, points, check_neg, check_pos,
                out_root):
    rel = g["relation_type"]
    pair = g["pair"]
    gid = g["group_id"]
    gdir = out_root / rel / gid

    tgt = strip_private(g["target_obj"])
    src = strip_private(g["source_obj"])
    tgt["split"] = split
    src["split"] = split

    # 任务 ID 不编码正负（L1006）：用组内序号 p1/p2 也不写 positive/negative
    pos_id = f"task_{gid}_t01"
    neg_id = f"task_{gid}_t02"

    # ---- 候选顺序：按组哈希打乱，有效源不再固定首位 ----
    rng = random.Random(seeded(gid, "source_order"))
    pos_items = [dict(item=g["source_obj"], kind="valid")] + \
                [dict(item=p["obj"], kind=p["kind"]) for p in interf_pos]
    neg_items = [dict(item=p["obj"], kind=p["kind"]) for p in interf_neg]
    rng.shuffle(pos_items)
    rng.shuffle(neg_items)
    pos_src_ids = [it["item"]["object_id"] for it in pos_items]
    neg_src_ids = [it["item"]["object_id"] for it in neg_items]

    # ---- manifest（公开）----
    dump(gdir / "manifest.json", dict(
        group_id=gid, dataset="mred", relation_type=rel,
        schema_version=SCHEMA_VERSION, vocab_version=VOCAB_VERSION,
        split=split, pair_id=pair["pair_id"], variant_index=g["variant_index"],
        object_ids=[tgt["object_id"]] + pos_src_ids,
        task_ids=[pos_id, neg_id],
        task_counts=dict(positive=1, negative=1, total=2),
        source_counts=dict(positive=len(pos_src_ids), negative=len(neg_src_ids)),
    ))

    # ---- manifest.sealed（封存标签）----
    dump(gdir / "manifest.sealed.json", dict(
        group_id=gid,
        positive_task=dict(task_id=pos_id, valid_sources=[src["object_id"]],
                           excluded_sources=[p["obj"]["object_id"] for p in interf_pos]),
        negative_task=dict(task_id=neg_id, valid_sources=[],
                           excluded_sources=[p["obj"]["object_id"] for p in interf_neg]),
    ))

    # ---- relation/（封存：真实领域名、节点角色名都在这里）----
    dump(gdir / "relation" / "analogy.json", dict(
        source=dict(object_id=src["object_id"], label=g["source_obj"]["_sealed_label"],
                    node_labels=g["source_obj"]["_sealed_node_labels"]),
        target=dict(object_id=tgt["object_id"], label=g["target_obj"]["_sealed_label"],
                    node_labels=g["target_obj"]["_sealed_node_labels"]),
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
    (gdir / "relation" / "formula.md").write_text(
        f"源域（{g['source_obj']['_sealed_label']}）：{src['function']}\n"
        f"目标域（{g['target_obj']['_sealed_label']}）：{tgt['function']}\n"
        f"角色：{' / '.join(O.ROLE_SPEC[rel]['roles'])}\n"
        f"领域依据：{pair['evidence']}\n"
        + (f"简化假设：{pair['assumption']}\n" if pair["assumption"] else ""),
        encoding="utf-8")

    # ---- data/input/objects ----
    objs = {"objects": []}
    all_objs = [tgt, src] + [p["obj"] for p in interf_pos + interf_neg]
    seen = set()
    for o in all_objs:
        if o["object_id"] in seen:
            continue
        seen.add(o["object_id"])
        fn = o["object_id"] + ".json"
        dump(gdir / "data" / "input" / "objects" / fn, o)
        objs["objects"].append(dict(object_id=o["object_id"], file=fn))
    dump(gdir / "data" / "input" / "objects" / "index.json", objs)

    # ---- data/input/tasks（文件名不写 positive/negative）----
    for tid, srcs in [(pos_id, pos_src_ids), (neg_id, neg_src_ids)]:
        dump(gdir / "data" / "input" / "tasks" / f"{tid}.json",
             dict(task_id=tid, group_id=gid, target_id=tgt["object_id"],
                  source_ids=srcs, schema_version=SCHEMA_VERSION,
                  vocab_version=VOCAB_VERSION,
                  intervenable_inputs=tgt["controllable_inputs"],
                  specified_outputs=tgt["designated_outputs"],
                  intervention_range={k: v for k, v in tgt["intervention_bounds"].items()},
                  _note="方法输入不含标签、正确源域或见证点"))

    # ---- counterexamples/（封存受控合成标注 + 见证）----
    for p in interf_pos + interf_neg:
        d = gdir / "counterexamples" / p["obj"]["object_id"]
        dump(d / "counterexample.json", dict(
            source_id=p["obj"]["object_id"], target_id=tgt["object_id"],
            interference_kind=p["kind"],
            max_error=p["max_error"],
            controlled_synthetic=True,
            # L1008：候选库整体只允许这一种映射（角色对齐），记录被排除的原因
            excluded_because=("结构不成立（角色/端点与函数实际依赖不符）"
                              if p["kind"] == "structure_error"
                              else "结构通过但响应误差超参考容差"),
        ))
        w = p["witness"]
        if w:
            dump(d / "witness.json", dict(
                u_target=w["u_target"], u_source=w["u_source"],
                r_target=w["r_target"], r_source=w["r_source"],
                error=min(1.0, (w["r_source"] - w["r_target"]) ** 2),
            ))

    # ---- sealed/reference.json ----
    ref = {
        pos_id: dict(
            task_id=pos_id, label="positive",
            valid=[dict(source_id=src["object_id"], node_map=g["node_map"],
                        edge_map={"r1": "r1"})],
            exclusions=[dict(source_id=p["obj"]["object_id"], kind=p["kind"],
                             reason=("结构不成立" if p["kind"] == "structure_error"
                                     else f"响应超容差：{p['max_error']:.6f} > "
                                          f"{REFERENCE_TOLERANCE['max_error']}"),
                             witness=p["witness"])
                        for p in interf_pos],
            reference_tolerance=REFERENCE_TOLERANCE,
            positive_max_deviation=g["positive_dev"],
            allowed_mappings_total=check_pos["allowed_mappings_total"],
            status="bijective_confirmed",
            full_library_verified=check_pos["verified"],
        ),
        neg_id: dict(
            task_id=neg_id, label="negative",
            valid=[],
            exclusions=[dict(source_id=r["source_id"], kind=r["kind"],
                             reason="全部类型兼容映射均失败",
                             candidate_mappings=r["candidate_mappings"],
                             max_error=r["max_error"],
                             witness=r["witness"],
                             detail=[dict(node_map=d["node_map"],
                                          failed_checks=d["failed_checks"],
                                          verdict=d["verdict"])
                                     for d in r["detail"]])
                        for r in check_neg["rejected"]],
            reference_tolerance=REFERENCE_TOLERANCE,
            allowed_mappings_total=check_neg["allowed_mappings_total"],
            status="bijective_confirmed",
            full_library_verified=check_neg["verified"],
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
        f"{gid} —— {g['source_obj']['_sealed_label']} → "
        f"{g['target_obj']['_sealed_label']}（{rel}，{split}）\n\n"
        f"来源域对：{pair['pair_id']}，参数变体 #{g['variant_index']}\n"
        f"领域依据：{pair['evidence']}\n"
        f"正任务 {pos_id}（10 源域，1 有效 + 9 干扰）、"
        f"负任务 {neg_id}（10 源域，全部无效）。映射方向 source→target。\n"
        f"封存参考见 sealed/reference.json。\n",
        encoding="utf-8")


# ============================================================
# 主流程
# ============================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", type=str, default="")
    ap.add_argument("--dev", action="store_true",
                    help="生成 L991 要求的 30 个开发基础组（group_dev_*，不参与正式统计）")
    args = ap.parse_args()

    prefix = "dev" if args.dev else "tr"
    plan = plan_dev_groups() if args.dev else plan_groups()
    if args.limit:
        plan = plan[:args.limit]
    print(f"计划基础组: {len(plan)}（{'开发组' if args.dev else '正式组'}）")

    print("=== 1) 构造基础组 + 正例等价性 ===")
    groups = []
    for i, p in enumerate(plan):
        groups.append(build_group(i, p["relation_type"], p["pair"],
                                  p["variant_index"], p["pair_rank"],
                                  prefix=prefix))
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(plan)}")
    print(f"  {len(groups)} 组构造完成，正例 max_dev 全部 <= 1e-9")

    print("=== 2) 干扰源池 + 见证点 + 全库枚举 ===")
    for gi, g in enumerate(groups):
        g["pos"], g["neg"] = make_shared_pool(g)
        # 正任务库 = 有效源 + 9 干扰；负任务库 = 10 干扰
        pos_sources = [dict(obj=g["source_obj"], kind="valid")] + g["pos"]
        g["check_pos"] = full_library_check(
            g["target_obj"], pos_sources, g["relation_type"], g["node_map"])
        g["check_neg"] = full_library_check(
            g["target_obj"], [dict(obj=p["obj"], kind=p["kind"]) for p in g["neg"]],
            g["relation_type"], g["node_map"])
        if not g["check_neg"]["verified"]:
            raise AssertionError(f"{g['group_id']} 负任务全库核验未通过")
        if len(g["check_pos"]["valid"]) < 1:
            raise AssertionError(f"{g['group_id']} 正任务未找到有效映射")
        if (gi + 1) % 20 == 0:
            print(f"  {gi+1}/{len(groups)}")
    print(f"  每组 10 个干扰源，全库 {sum(len(g['neg']) for g in groups)} 个，"
          f"全部通过枚举核验")

    print("=== 3) 划分（按基础对象组整体划分）===")
    # 防「参数变体形同虚设」：任意两组的同角色对象不得签名完全相同
    # （L999 参数变体必须真的不同；签名相同意味着跨划分复用同一对象）
    seen_sig = {}
    dup = []
    for g in groups:
        for tag, o in (("tgt", g["target_obj"]), ("src", g["source_obj"])):
            sig = (g["relation_type"], g["pair"]["pair_id"], tag,
                   o["function"], tuple(round(x, 10) for x in o["baseline"]))
            if sig in seen_sig:
                dup.append((seen_sig[sig], g["group_id"], tag))
            else:
                seen_sig[sig] = g["group_id"]
    if dup:
        raise AssertionError(
            f"{len(dup)} 组对象签名跨组完全相同（参数变体退化为同一对象）：{dup[:3]}")
    print(f"  对象签名跨组重复：0（检查 {len(seen_sig)} 个签名）")

    if args.dev:
        # L991：开发组只用于联调与检查标注流程，不划分、不封存干预点
        for g in groups:
            g["split"] = "dev"
        print("  开发组不参与 70/15/15 划分（split 一律记 dev）")
    else:
        assign = assign_splits_by_pair(groups)
        for g in groups:
            g["split"] = assign[g["group_id"]]
    from collections import Counter
    cnt = Counter(g["split"] for g in groups)
    print(f"  {dict(cnt)}")
    pair_splits = {}
    for g in groups:
        pair_splits.setdefault((g["relation_type"], g["pair"]["pair_id"]), set()).add(g["split"])
    leak = [k for k, v in pair_splits.items() if len(v) > 1]
    if leak:
        raise AssertionError(f"{len(leak)} 个域对跨划分：{leak[:5]}")

    print("=== 4) 测试任务干预点 ===")
    n_pts = 0
    for g in groups:
        if g["split"] != "test":
            g["points"] = None
            continue
        pid, nid = f"task_{g['group_id']}_t01", f"task_{g['group_id']}_t02"
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
        write_group(g, g["pos"], g["neg"], g["split"], g["points"],
                    g["check_neg"], g["check_pos"], out_root)
        if (gi + 1) % 50 == 0:
            print(f"  {gi+1}/{len(groups)}")
    print("完成。")


if __name__ == "__main__":
    main()
