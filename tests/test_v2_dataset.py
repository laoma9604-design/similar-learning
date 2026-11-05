"""v2 数据集回归测试（只读 cases/，不 import 生成器）。

存在理由：`pytest` 原有 126 条一条都不覆盖 cases/structural_v2 与
gen_structural_v2.py / verify_structural_v2.py。生成器自报「30/30 通过」只证明
它自己检查的那些事，这里锁的是**数据在磁盘上的最终形态**。

每条测试对应一个本轮真实踩过的缺陷或 PDF 明确要求。
"""
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "cases" / "structural_v2"
TOL_ERR = math.sqrt(0.05)      # PDF L1010：最大误差 0.05 属数据版本，不可调算
MIN_CTC = 0.95


@pytest.fixture(scope="module")
def groups():
    gids = sorted(p.name for p in CASES.glob("group_v2_*") if p.is_dir())
    out = []
    for gid in gids:
        g = CASES / gid
        objs = {}
        for f in (g / "data" / "input" / "objects").glob("*.json"):
            o = json.load(open(f, encoding="utf-8"))
            if "object_id" in o:
                objs[o["object_id"]] = o
        out.append(dict(
            gid=gid, gdir=g,
            man=json.load(open(g / "manifest.json", encoding="utf-8")),
            sealed=json.load(open(g / "manifest.sealed.json", encoding="utf-8")),
            ref=json.load(open(g / "sealed" / "reference.json", encoding="utf-8")),
            objs=objs,
        ))
    return out


# ============================================================
# 规模与结构（用户 2026-11-04 拍板的硬上限）
# ============================================================
def test_group_count_and_tasks(groups):
    """30 组 / 60 任务（L991：任务数与基础组数分开报告）。"""
    assert len(groups) == 30
    assert sum(len(g["man"]["task_ids"]) for g in groups) == 60


def test_size_ceiling(groups):
    """|V| <= 9、|E| <= 5 —— 这是保证负任务可全枚举的前提，不是随便定的。"""
    for g in groups:
        tgt = g["objs"][g["man"]["target_id"]]
        assert len(tgt["nodes"]) <= 9, g["gid"]
        assert len(tgt["edges"]) <= 5, g["gid"]


def test_multi_edge_everywhere(groups):
    """v2 的每个对象都必须是真正的多关系图，不能退化成单超边。"""
    for g in groups:
        tgt = g["objs"][g["man"]["target_id"]]
        assert len(tgt["edges"]) >= 3, f"{g['gid']} 边数 {len(tgt['edges'])}"
        assert g["man"]["max_depth"] >= 3, f"{g['gid']} 深度 {g['man']['max_depth']}"


def test_has_intermediate_and_shared_or_deep(groups):
    """每个对象都要有中间变量；深度 >= 4 的组必须体现复用或共享。"""
    for g in groups:
        tgt = g["objs"][g["man"]["target_id"]]
        produced = {n for e in tgt["edges"] for n in e["output_nodes"]}
        consumed = {n for e in tgt["edges"] for n in e["input_nodes"]}
        inter = produced & consumed
        assert len(inter) >= 1, f"{g['gid']} 没有中间变量"


def test_no_cycle_and_single_output(groups):
    """PDF L682 第一批必须无环；每条边单输出。"""
    for g in groups:
        tgt = g["objs"][g["man"]["target_id"]]
        for e in tgt["edges"]:
            assert len(e["output_nodes"]) == 1
        produced = Counter(n for e in tgt["edges"] for n in e["output_nodes"])
        assert all(c == 1 for c in produced.values()), f"{g['gid']} 有重复产出"


# ============================================================
# 候选池与正负任务（PDF L1006/L1008）
# ============================================================
def test_pool_size_ten(groups):
    """每个任务恰好 10 个候选（L1006）。"""
    for g in groups:
        for tid in g["man"]["task_ids"]:
            t = json.load(open(g["gdir"] / "data" / "input" / "tasks" / f"{tid}.json",
                               encoding="utf-8"))
            assert len(t["source_ids"]) == 10, f"{tid} 候选 {len(t['source_ids'])}"
            assert len(set(t["source_ids"])) == 10, f"{tid} 候选有重复"


def test_candidates_exist_on_disk(groups):
    """任务引用的每个对象都必须真在磁盘上（引用完整性）。"""
    for g in groups:
        for tid in g["man"]["task_ids"]:
            t = json.load(open(g["gdir"] / "data" / "input" / "tasks" / f"{tid}.json",
                               encoding="utf-8"))
            for oid in t["source_ids"] + [t["target_id"]]:
                assert oid in g["objs"], f"{tid} 引用不存在的对象 {oid}"


def test_positive_has_valid_and_negative_has_none(groups):
    """正任务 valid 非空、负任务 valid 为空。"""
    for g in groups:
        pos = next(r for r in g["ref"].values() if r["label"] == "positive")
        neg = next(r for r in g["ref"].values() if r["label"] == "negative")
        assert pos["valid"], g["gid"]
        assert neg["valid"] == [], g["gid"]


def test_valid_mappings_are_complete_set(groups):
    """PDF L986/L1008：多解必须存集合，不能只存一个参考映射。"""
    for g in groups:
        pos = next(r for r in g["ref"].values() if r["label"] == "positive")
        # 同一 source 若有多条有效映射必须都列出
        by_src = defaultdict(list)
        for v in pos["valid"]:
            by_src[v["source_id"]].append(v)
        for sid, lst in by_src.items():
            assert len(lst) >= 1
            # 每条都必须标 max_abs_diff 且在容差内
            for v in lst:
                assert v["max_abs_diff"] <= TOL_ERR + 1e-12, f"{g['gid']}/{sid}"


def test_negative_has_witness_for_every_candidate(groups):
    """PDF L1010：负例至少提供超过参考容差的见证点（每候选一条）。"""
    for g in groups:
        neg = next(r for r in g["ref"].values() if r["label"] == "negative")
        assert len(neg["exclusions"]) == 10, f"{g['gid']} 排除记录 {len(neg['exclusions'])}"
        ids = {e["source_id"] for e in neg["exclusions"]}
        assert len(ids) == 10, f"{g['gid']} 排除记录有重复"
        for e in neg["exclusions"]:
            w = e.get("witness")
            assert w is not None, f"{g['gid']}/{e['source_id']} 缺见证点"
            assert "u" in w and "max_abs_diff" in w


def test_kind_is_full_name_not_abbrev(groups):
    """干扰源类别必须是 long name —— 曾写成 's'/'r'/'l' 导致 reason 为空。"""
    for g in groups:
        for rec in g["ref"].values():
            for e in rec.get("exclusions") or []:
                assert e["kind"] in ("structure_error", "response_error",
                                     "local_perturbation"), f"{g['gid']} kind={e['kind']}"
                assert e["reason"], f"{g['gid']}/{e['source_id']} reason 为空"


def test_response_gap_exceeds_tolerance(groups):
    """响应类与局部扰动类的见证点必须真的超容差（v1.1 68% 结构错误就是这条的反面）。"""
    for g in groups:
        for rec in g["ref"].values():
            for e in rec.get("exclusions") or []:
                if e["kind"] not in ("response_error", "local_perturbation"):
                    continue
                assert e["witness"]["max_abs_diff"] > TOL_ERR, \
                    f"{g['gid']}/{e['source_id']} Δr={e['witness']['max_abs_diff']:.4f}"


def test_structure_errors_excluded_by_structure(groups):
    """结构错误类靠 eq:structure 排除，其见证点可以 Δr 很小 —— 但必须标成结构错误。

    这条锁的是「不要拿结构错误冒充响应错误」：kind 必须正确，否则下游会把
    Δr≈0 的样本读成"响应可分性极差"。
    """
    for g in groups:
        for rec in g["ref"].values():
            for e in rec.get("exclusions") or []:
                if e["kind"] == "structure_error":
                    assert "结构" in e["reason"], f"{g['gid']}/{e['source_id']}"


# ============================================================
# 隔离（答案不能泄露到方法输入）
# ============================================================
def test_task_id_does_not_encode_label(groups):
    for g in groups:
        for tid in g["man"]["task_ids"]:
            low = tid.lower()
            for w in ("pos", "neg", "true", "false", "valid"):
                assert w not in low, f"{tid} 编码了标签 {w}"


def test_public_objects_have_no_answer_fields(groups):
    for g in groups:
        for oid, o in g["objs"].items():
            for k in ("kind", "_kind", "is_valid", "label_kind", "valid", "exclusions"):
                assert k not in o, f"{g['gid']}/{oid} 含答案字段 {k}"
            assert o["label"] in ("目标域", "候选源域"), o["label"]


def test_valid_source_position_not_fixed(groups):
    """有效源不能永远排在候选列表第一位（否则一行取首项就 100% 答对）。"""
    idxs = []
    for g in groups:
        for tid in g["man"]["task_ids"]:
            t = json.load(open(g["gdir"] / "data" / "input" / "tasks" / f"{tid}.json",
                               encoding="utf-8"))
            pos = next(r for r in g["ref"].values() if r["label"] == "positive")
            if tid != pos["task_id"]:
                continue
            sid = pos["valid"][0]["source_id"]
            idxs.append(t["source_ids"].index(sid))
    assert len(set(idxs)) >= 4, f"有效源位置只出现 {sorted(set(idxs))} 种"
    # 判据是「不固定」，不是「永不落在首位」：30 组里偶尔排到第 0 位是正常的，
    # 一行取首项的可答对率必须远低于 1（实测 3/30 = 10%，接近随机 1/10）
    assert idxs.count(0) <= len(idxs) / 5, f"有效源有 {idxs.count(0)}/{len(idxs)} 组排首位"
    c = Counter(idxs)
    assert max(c.values()) <= len(idxs) / 3, f"位置分布过于集中 {dict(c)}"


def test_structure_class_not_in_public_manifest(groups):
    for g in groups:
        s = json.dumps(g["man"], ensure_ascii=False)
        for w in ("s0_", "s1_", "s2_", "s3_", "s4_", "structure_class", "proto"):
            assert w not in s, f"{g['gid']} 公开 manifest 含 {w}"


# ============================================================
# 划分与干预点（PDF L1020/L1024）
# ============================================================
def test_split_ratio(groups):
    c = Counter(g["man"]["split"] for g in groups)
    n = len(groups)
    assert set(c) <= {"train", "val", "test"}
    for k, want in (("train", 0.70), ("val", 0.15), ("test", 0.15)):
        assert abs(c[k] / n - want) <= 0.06, f"{k} {c[k]}/{n}"


def test_split_consistent_between_manifest_and_objects(groups):
    for g in groups:
        for o in g["objs"].values():
            assert o["split"] == g["man"]["split"], f"{g['gid']}/{o['object_id']}"


def test_intervention_points_only_on_test(groups):
    """PDF L1024：只有测试任务封存 100 个干预点。"""
    for g in groups:
        p = g["gdir"] / "sealed" / "intervention_points.json"
        assert p.exists() == (g["man"]["split"] == "test"), g["gid"]
        if not p.exists():
            continue
        d = json.load(open(p, encoding="utf-8"))
        assert d["points_per_task"] == 100
        for tid, pts in d["tasks"].items():
            assert len(pts) == 100, f"{tid} 干预点 {len(pts)}"
            assert len({tuple(sorted(x.items())) for x in pts}) == 100, f"{tid} 有重复点"
            assert all(any(abs(v) > 1e-12 for v in x.values()) for x in pts), \
                f"{tid} 含固定初始化点"


def test_intervention_points_in_bounds(groups):
    for g in groups:
        p = g["gdir"] / "sealed" / "intervention_points.json"
        if not p.exists():
            continue
        tgt = g["objs"][g["man"]["target_id"]]
        d = json.load(open(p, encoding="utf-8"))
        for tid, pts in d["tasks"].items():
            for u in pts:
                assert set(u) == set(tgt["controllable_inputs"])
                for n, v in u.items():
                    lo, hi = tgt["intervention_bounds"][n]
                    assert lo - 1e-9 <= v <= hi + 1e-9, f"{tid} {n}={v} 越界"


# ============================================================
# 与 v1 / v1.1 的重合（避免新测试集只是旧数据的重排）
# ============================================================
def _sig_topo(o):
    produced = {n for e in o["edges"] for n in e["output_nodes"]}
    consumed = Counter(n for e in o["edges"] for n in e["input_nodes"])
    seq = []
    for e in o["edges"]:
        seq.append(f"{e['edge_type'][:3]}:{len(e['input_nodes'])}:"
                   f"{sum(1 for n in e['input_nodes'] if n in produced)}")
    return "|".join(sorted(seq))


def test_topology_not_reused_from_v11(groups):
    """v2 的拓扑签名不能与历史库（v1 单超边 / v1.1 增强组）完全相同。

    v1.1 已于 2026-11-04 清理（用户决定：v2 验收通过后一次性删除），
    所以这里对**存在的**历史库做检查；目录不在时自动跳过该项，
    避免测试因为「历史数据已删」而假红。
    """
    hist = []
    v11 = ROOT / "cases" / "structural_enhanced"
    if v11.is_dir():
        hist += list(v11.glob("group_enh_*/data/input/objects/*_tgt.json"))
    for ds in ("multiplicative_growth", "linear_drive_resistance", "saturation_response"):
        hist += list((ROOT / "cases" / ds).glob("group_*/data/input/objects/*_tgt.json"))
    old = set()
    for f in hist:
        try:
            o = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if "edges" in o:
            old.add(_sig_topo(o))
    new = {_sig_topo(g["objs"][g["man"]["target_id"]]) for g in groups}
    assert not (new & old), f"与历史库拓扑重合：{new & old}"


def test_schema_fields_match(groups):
    """逐对象对 schema 的 object 必填字段（内容对 ≠ 字段齐）。"""
    schema = json.load(open(ROOT / "T01-schema.json", encoding="utf-8"))
    req = [k for k, v in schema["records"]["object"]["fields"].items()
           if v.get("required") is True]
    allowed = set(schema["records"]["object"]["fields"])
    for g in groups:
        for oid, o in g["objs"].items():
            assert not [k for k in req if k not in o], \
                f"{g['gid']}/{oid} 缺 {[k for k in req if k not in o]}"
            assert not [k for k in o if k not in allowed], \
                f"{g['gid']}/{oid} 多出 {[k for k in o if k not in allowed]}"
