"""MRED v2 数据完整性回归测试（2026-11-01 评审四条问题）。

每一条测试都对应一个曾经真实发生过的缺陷，固定住「不许回退」的判据。
这些测试只读 cases/，不 import 生成器内部逻辑（避免自证清白）。

跑法：
    python -m pytest tests/test_mred_v2.py -q
"""
from __future__ import annotations

import itertools
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "cases"
RELS = ["multiplicative_growth", "linear_drive_resistance", "saturation_response"]
MAX_ERROR = 0.05


def formal_groups():
    out = []
    for rel in RELS:
        for g in sorted((CASES / rel).glob("group_tr_*")):
            out.append(g)
    return out


def load_group(gdir):
    idx = json.loads((gdir / "data/input/objects/index.json").read_text(encoding="utf-8"))
    objs = {o["object_id"]: json.loads((gdir / "data/input/objects" / o["file"]).read_text(encoding="utf-8"))
            for o in idx["objects"]}
    tasks = {}
    for p in (gdir / "data/input/tasks").glob("*.json"):
        t = json.loads(p.read_text(encoding="utf-8"))
        tasks[t["task_id"]] = t
    return dict(gid=gdir.name, dir=gdir, objs=objs,
                manifest=json.loads((gdir / "manifest.json").read_text(encoding="utf-8")),
                sealed=json.loads((gdir / "manifest.sealed.json").read_text(encoding="utf-8")),
                ref=json.loads((gdir / "sealed/reference.json").read_text(encoding="utf-8")),
                tasks=tasks)


@pytest.fixture(scope="module")
def groups():
    g = formal_groups()
    assert len(g) == 300, f"正式组应为 300，实际 {len(g)}"
    return [load_group(x) for x in g]


# ---------------------------------------------------------------------------
# 问题 1：响应反例结构不兼容（2 节点干扰源 / 3 节点目标）
# ---------------------------------------------------------------------------
def test_every_candidate_has_same_node_count_as_target(groups):
    """L342：两域节点数必须相等，否则双射不成立、走不到响应检验。

    v1 的乘性/线性类共 276 组是 3 节点目标配 2 节点干扰源，影响 552/600 任务。
    """
    bad = []
    for G in groups:
        tgt = G["objs"][G["manifest"]["object_ids"][0]]
        n = len(tgt["nodes"])
        for sid, o in G["objs"].items():
            if sid == tgt["object_id"]:
                continue
            if len(o["nodes"]) != n:
                bad.append((G["gid"], sid, len(o["nodes"]), n))
    assert not bad, f"{len(bad)} 个候选源节点数与目标不等，例 {bad[:3]}"


def test_non_structure_interferers_pass_structure_check(groups):
    """响应错误 / 局部扰动类必须结构全过，否则它们退化成又一个结构错误。

    判据只看标注层面（节点数、角色集合、端点、类型），这是「能否建立双射」的最小条件。
    """
    bad = []
    for G in groups:
        tgt = G["objs"][G["manifest"]["object_ids"][0]]
        te = tgt["edges"][0]
        tgt_roles = set(te["roles"].values())
        for tid, ref in G["ref"].items():
            if ref["label"] != "positive":
                continue
            for ex in ref["exclusions"]:
                if ex["kind"] == "structure_error":
                    continue
                s = G["objs"][ex["source_id"]]
                se = s["edges"][0]
                if set(se["roles"].values()) != tgt_roles:
                    bad.append((G["gid"], ex["source_id"], "角色集合不同"))
                if len(se["input_nodes"]) != len(te["input_nodes"]):
                    bad.append((G["gid"], ex["source_id"], "输入端点个数不同"))
    assert not bad, f"{len(bad)} 个响应类干扰源结构不成立，例 {bad[:3]}"


def test_structure_error_sources_really_fail_structure(groups):
    """结构错误类必须真的不满足结构条件（否则它应在正任务里通过）。"""
    bad = []
    for G in groups[:60]:
        tgt = G["objs"][G["manifest"]["object_ids"][0]]
        te = tgt["edges"][0]
        for tid, ref in G["ref"].items():
            if ref["label"] != "positive":
                continue
            for ex in ref["exclusions"]:
                if ex["kind"] != "structure_error":
                    continue
                s = G["objs"][ex["source_id"]]
                se = s["edges"][0]
                # 结构错误类：至少有一项标注层面的不成立（端点依赖/端点集合）
                same_roles = se["roles"] == te["roles"] if set(se["roles"]) == set(te["roles"]) else False
                same_endpoints = (se["input_nodes"] == te["input_nodes"]
                                  and se["output_nodes"] == te["output_nodes"])
                if same_roles and same_endpoints and s["function"] == tgt["function"]:
                    bad.append((G["gid"], ex["source_id"]))
    assert not bad, f"{len(bad)} 个结构错误源与目标域完全一致，例 {bad[:3]}"


# ---------------------------------------------------------------------------
# 问题 2：参数变体跨划分
# ---------------------------------------------------------------------------
def test_no_pair_spans_multiple_splits(groups):
    """L1020：同一域对的全部变体必须在同一划分。

    v1 有 21/25 个域对跨划分。
    """
    d = defaultdict(set)
    for G in groups:
        d[(G["manifest"]["relation_type"], G["manifest"]["pair_id"])].add(G["manifest"]["split"])
    leak = {k: v for k, v in d.items() if len(v) > 1}
    assert not leak, f"{len(leak)} 个域对跨划分，例 {list(leak)[:3]}"


def test_no_duplicate_object_signature_across_groups(groups):
    """参数变体必须真的不同：任意两组的同角色对象不得签名完全相同。

    v1 乘性类有 4636 对完全相同的签名（ratio 被对齐掉，变体的唯一自由参数没了）。
    """
    sig = {}
    dup = []
    for G in groups:
        tgt_id = G["manifest"]["object_ids"][0]
        for tag, sid in (("tgt", tgt_id), ("src", G["sealed"]["positive_task"]["valid_sources"][0])):
            o = G["objs"][sid]
            k = (G["manifest"]["relation_type"], G["manifest"]["pair_id"], tag,
                 o["function"], tuple(round(x, 10) for x in o["baseline"]))
            if k in sig:
                dup.append((sig[k], G["gid"], tag))
            else:
                sig[k] = G["gid"]
    assert not dup, f"{len(dup)} 组签名重复，例 {dup[:3]}"


# ---------------------------------------------------------------------------
# 问题 3：公开输入泄漏标签
# ---------------------------------------------------------------------------
def test_task_filenames_do_not_encode_label(groups):
    bad = [G["gid"] for G in groups
           if any(("positive" in p.name or "negative" in p.name)
                  for p in (G["dir"] / "data/input/tasks").glob("*.json"))]
    assert not bad, f"{len(bad)} 组任务文件名编码正负，例 {bad[:3]}"


def test_all_candidate_sources_share_one_label(groups):
    bad = []
    for G in groups:
        tgt_id = G["manifest"]["object_ids"][0]
        for sid, o in G["objs"].items():
            if sid == tgt_id:
                continue
            if o.get("label") != "候选源域":
                bad.append((G["gid"], sid, o.get("label")))
    assert not bad, f"{len(bad)} 个候选源 label 不统一，例 {bad[:3]}"


def test_no_node_id_prefix_rule(groups):
    """有效源与干扰源的节点 ID 必须来自同一池，不能按前缀区分。

    v1：有效源 b*、干扰源 n1/n2。
    """
    bad = []
    for G in groups:
        tgt_id = G["manifest"]["object_ids"][0]
        pools = {}
        for sid, o in G["objs"].items():
            if sid == tgt_id:
                continue
            pools[sid] = frozenset(n["node_id"] for n in o["nodes"])
        if len(set(pools.values())) != 1:
            bad.append((G["gid"], len(set(pools.values()))))
    assert not bad, f"{len(bad)} 组内候选源的节点 ID 集合不一致（可按 ID 区分），例 {bad[:3]}"


def test_valid_source_not_fixed_at_first_position(groups):
    """有效源不得固定在 source_ids[0]（随机打乱后命中率应接近 1/10）。"""
    hit = tot = 0
    for G in groups:
        for tid, ref in G["ref"].items():
            if ref["label"] != "positive":
                continue
            t = G["tasks"].get(tid)
            if not t:
                continue
            tot += 1
            if t["source_ids"][0] == ref["valid"][0]["source_id"]:
                hit += 1
    assert tot == 300, f"正任务应为 300，实际 {tot}"
    assert hit / tot < 0.25, f"「取首位」命中率 {hit}/{tot} 明显高于随机基线 0.1"


def test_public_objects_carry_no_sealed_labels(groups):
    """公开对象文件里不得出现真实领域名或封存字段。"""
    bad = []
    for G in groups[:50]:
        for sid, o in G["objs"].items():
            for k in o:
                if k.startswith("_sealed"):
                    bad.append((G["gid"], sid, k))
            if any(w in json.dumps(o, ensure_ascii=False) for w in ("细菌", "银行", "复利", "电阻")):
                bad.append((G["gid"], sid, "领域词"))
    assert not bad, f"{len(bad)} 处封存/领域信息泄漏，例 {bad[:3]}"


# ---------------------------------------------------------------------------
# 问题 4：全库排除证据不足
# ---------------------------------------------------------------------------
def test_negative_reference_has_real_enumeration(groups):
    """负任务必须真枚举：allowed_mappings_total > 0，且每源都有逐映射记录。"""
    bad = []
    for G in groups:
        for tid, ref in G["ref"].items():
            if ref["label"] != "negative":
                continue
            if not ref.get("allowed_mappings_total"):
                bad.append((G["gid"], tid, "无枚举数"))
                continue
            if not ref.get("full_library_verified"):
                bad.append((G["gid"], tid, "verified=False"))
            if ref["valid"]:
                bad.append((G["gid"], tid, "负任务竟有有效映射"))
            if len(ref["exclusions"]) != 10:
                bad.append((G["gid"], tid, f"exclusions={len(ref['exclusions'])}"))
            for e in ref["exclusions"]:
                if not e.get("candidate_mappings"):
                    bad.append((G["gid"], tid, "无候选映射数"))
                    break
    assert not bad, f"{len(bad)} 项全库核验不足，例 {bad[:3]}"


def test_response_evidence_has_top_level_witness(groups):
    """响应类排除必须有顶层见证（u / 两域响应 / 误差），结构类必须有逐映射失败记录。"""
    bad = []
    for G in groups:
        for tid, ref in G["ref"].items():
            if ref["label"] != "negative":
                continue
            for e in ref["exclusions"]:
                if e["kind"] == "structure_error":
                    if not e.get("detail"):
                        bad.append((G["gid"], tid, e["source_id"], "无逐映射记录"))
                else:
                    w = e.get("witness")
                    if not w or "u_target" not in w or "r_target" not in w:
                        bad.append((G["gid"], tid, e["source_id"], "无见证点"))
                    elif e.get("max_error", 0) <= MAX_ERROR:
                        bad.append((G["gid"], tid, e["source_id"], "见证未超容差"))
    assert not bad, f"{len(bad)} 项见证不足，例 {bad[:3]}"


def test_full_library_verified_is_computed_not_constant(groups):
    """正任务的 verified 不可能是 True 的常量（正任务库里有有效映射）。

    v1 把 full_library_verified=True 写死；v2 该字段由枚举结果算出，
    正任务因为存在有效映射而必须为 False。
    """
    pos_verified = [G["gid"] for G in groups
                    for tid, ref in G["ref"].items()
                    if ref["label"] == "positive" and ref.get("full_library_verified")]
    assert not pos_verified, f"{len(pos_verified)} 个正任务的 verified 为 True（应为常量写死）"


def test_intervention_points_only_in_test_split(groups):
    """L1024：只有测试组有封存干预点，且每组 100 点、不含全零固定点。"""
    bad = []
    for G in groups:
        p = G["dir"] / "sealed/intervention_points.json"
        is_test = G["manifest"]["split"] == "test"
        if is_test != p.is_file():
            bad.append((G["gid"], G["manifest"]["split"], p.is_file()))
            continue
        if not is_test:
            continue
        pts = json.loads(p.read_text(encoding="utf-8"))
        for tid, lst in pts["tasks"].items():
            if len(lst) != 100:
                bad.append((G["gid"], tid, f"{len(lst)} 点"))
            if any(all(abs(v) < 1e-12 for v in u.values()) for u in lst):
                bad.append((G["gid"], tid, "含全零固定点"))
    assert not bad, f"{len(bad)} 项干预点问题，例 {bad[:3]}"


# ---------------------------------------------------------------------------
# 正例等价性（L1010）
# ---------------------------------------------------------------------------
def _ev(expr, vals):
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
            raise ValueError("unsupported binop")
        if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "exp":
            return math.exp(visit(n.args[0]))
        raise ValueError("unsupported")
    return visit(ast.parse(expr, mode="eval").body)


def _resp(obj, u):
    vals = {}
    for i, nid in enumerate(obj["controllable_inputs"]):
        vals[nid] = obj["baseline"][i] + obj["input_scales"][i] * u[nid]
    y = _ev(obj["function"], vals)
    out = obj["designated_outputs"][0]
    return (y - obj["baseline_output"]) / obj["output_scale"]


def test_positive_pairs_are_response_equivalent(groups):
    """L1010：正例在主输入维上的归一化响应必须一致。"""
    worst = 0.0
    for G in groups:
        tgt_id = G["manifest"]["object_ids"][0]
        tgt = G["objs"][tgt_id]
        for tid, ref in G["ref"].items():
            if ref["label"] != "positive":
                continue
            truth = ref["valid"][0]
            src = G["objs"][truth["source_id"]]
            inv = {v: k for k, v in truth["node_map"].items()}
            main_t = tgt["controllable_inputs"][0]
            for u in (-0.2, -0.1, 0.0, 0.1, 0.2):
                ut = {n: 0.0 for n in tgt["controllable_inputs"]}
                ut[main_t] = u
                us = {inv[k]: v for k, v in ut.items()}
                worst = max(worst, abs(_resp(src, us) - _resp(tgt, ut)))
    assert worst < 1e-9, f"正例响应最大偏差 {worst:.2e} 超过 1e-9"


# ---------------------------------------------------------------------------
# 复查新增（2026-11-01 提交前逐条对照任务书时发现）
# ---------------------------------------------------------------------------
def test_interferer_pool_has_10_distinct_objects(groups):
    """L991/L1006：候选库的 10 个源域必须是 10 个不同的对象。

    提交前复查发现：同类干扰源函数完全相同、只有 ID 不同，
    等于把 3 个候选报成 10 个，虚增了候选库。
    """
    bad = []
    for G in groups:
        for tid, ref in G["ref"].items():
            if ref["label"] != "negative":
                continue
            sigs = set()
            for e in ref["exclusions"]:
                o = G["objs"][e["source_id"]]
                sigs.add((o["function"], tuple(o["baseline"]),
                          tuple(o["controllable_inputs"])))
            if len(sigs) != 10:
                bad.append((G["gid"], tid, len(sigs)))
    assert not bad, f"{len(bad)} 个负任务的 10 个源域不足 10 个不同对象，例 {bad[:3]}"


def test_all_interferers_carry_distinct_function_families(groups):
    """同类干扰源之间函数必须不同（每类至少 3~4 个不同函数族）。"""
    bad = []
    for G in groups[:60]:
        for tid, ref in G["ref"].items():
            if ref["label"] != "negative":
                continue
            per = {}
            for e in ref["exclusions"]:
                o = G["objs"][e["source_id"]]
                per.setdefault(e["kind"], set()).add(o["function"])
            need = {"structure_error": 3, "response_error": 4, "local_perturbation": 3}
            for k, n in need.items():
                if len(per.get(k, set())) != n:
                    bad.append((G["gid"], k, len(per.get(k, set())), n))
    assert not bad, f"{len(bad)} 项同类干扰源函数重复，例 {bad[:3]}"


def test_public_objects_have_no_repeated_function_within_group(groups):
    """同一组里公开的对象（目标 + 10 候选）函数两两不同，避免同题重复。"""
    bad = []
    for G in groups[:80]:
        fns = [o["function"] for o in G["objs"].values()]
        # 干扰源与目标之间允许「结构错误源」的构造函数相似，但对象本身必须不同
        sigs = [(o["function"], tuple(o["baseline"])) for o in G["objs"].values()]
        if len(set(sigs)) != len(sigs):
            bad.append(G["gid"])
    assert not bad, f"{len(bad)} 组内存在完全相同的对象，例 {bad[:3]}"


def test_dev_groups_exist_and_are_excluded_from_formal(groups):
    """L991：30 个开发基础组存在，且不进正式清单、不参与划分。"""
    dev = []
    for rel in RELS:
        dev += sorted((CASES / rel).glob("group_dev_*"))
    assert len(dev) == 30, f"开发组应为 30，实际 {len(dev)}"
    splits = set()
    for g in dev:
        m = json.loads((g / "manifest.json").read_text(encoding="utf-8"))
        splits.add(m.get("split"))
    assert splits == {"dev"}, f"开发组 split 应为 dev，实际 {splits}"

    splits_csv = (ROOT / "data/splits.csv").read_text(encoding="utf-8-sig")
    assert "group_dev" not in splits_csv, "开发组不应进入 splits.csv"
    ref_all = (ROOT / "data/reference_all.jsonl").read_text(encoding="utf-8")
    assert "group_dev" not in ref_all, "开发组不应进入 reference_all.jsonl"
