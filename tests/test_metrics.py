"""独立结构评价器（a_data/metrics.py）的正式回归测试。

分两层：
  1. 合成小例子 —— 断言任务书给出的已知答案，不依赖仓库里的数据文件，跑得飞快；
  2. 真实数据全量 —— 在 MRED 300 个正式组上用封存正确映射自评价，守"数据与口径一致"。

跑法（项目根目录）：
    python -m pytest tests/ -q
只用标准 pytest，无需额外依赖。

每个用例都对应任务书一句原文，注释里标了行号。改评价器时先跑这个。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "a_data"))

import metrics as _m  # noqa: E402

from metrics import (  # noqa: E402
    _synth_binary_pair,
    _synth_pair,
    aggregate,
    build_checks,
    evaluate_response,
    load_group,
    response_error,
    score_prediction,
    selftest,
    sgn_eta,
)


def _metrics():
    """返回 metrics 模块本体（新增指标直接取模块属性）。"""
    return _m


# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------

@pytest.fixture
def ternary():
    """三节点、一条三元超边（细菌增长 / 银行复利）。清单应为 11 项。"""
    return _synth_pair()


@pytest.fixture
def binary():
    """二节点、一条二元超边（饱和响应）。清单应为 9 项。"""
    return _synth_binary_pair()


GOLD = {"node_map": {"N_t": "A_t", "r_s": "r_t", "N_next": "A_next"},
        "edge_map": {"e_s": "e_t"}}


# ---------------------------------------------------------------------------
# 1. 任务书已知答案
# ---------------------------------------------------------------------------

def test_selftest_passes():
    """命令行的 --selftest 必须绿。"""
    assert selftest() == 0


def test_ternary_checklist_has_11_items(ternary):
    """三节点三元超边：2 + 3 + 3 + 3 = 11（L1036）。"""
    tgt, src = ternary
    checks = build_checks(tgt, src, GOLD["node_map"], GOLD["edge_map"])
    assert len(checks) == 11


def test_binary_checklist_has_9_items(binary):
    """二节点二元超边：2 + 2 + 3 + 2 = 9。项数由结构决定，不是常数。"""
    tgt, src = binary
    r = score_prediction(tgt, src, {"node_map": {"in_s": "input", "out_s": "response"},
                                    "edge_map": {"e_s": "r1"}})
    assert r["n_checks"] == 9
    assert r["sf"] == pytest.approx(1.0)
    assert r["sipr"] == 1


def test_correct_mapping_scores_perfect(ternary):
    """正确映射 SF=1、SIPR=1（L1113 验收要求）。"""
    tgt, src = ternary
    r = score_prediction(tgt, src, GOLD)
    assert r["n_passed"] == 11
    assert r["sf"] == pytest.approx(1.0)
    assert r["sipr"] == 1
    assert r["error_breakdown"] == {"type_error": 0, "endpoint_error": 0, "role_error": 0}


def test_role_swap_gives_9_of_11(ternary):
    """交换两个输入角色：两项角色失败，SF=9/11、SIPR=0（L132 / L1036）。

    这是任务书点名要求用来验收评价器的例子，数字必须精确复现。
    """
    tgt, src = ternary
    swapped = {"node_map": {"N_t": "r_t", "r_s": "A_t", "N_next": "A_next"},
               "edge_map": {"e_s": "e_t"}}
    r = score_prediction(tgt, src, swapped)
    assert r["n_passed"] == 9
    assert r["sf"] == pytest.approx(9 / 11)
    assert r["sipr"] == 0
    assert r["error_breakdown"]["role_error"] == 2
    assert r["error_breakdown"]["type_error"] == 0
    assert r["error_breakdown"]["endpoint_error"] == 0


# ---------------------------------------------------------------------------
# 2. 分母规则：清单由目标结构确定，不随候选质量收缩（L1034）
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pred", [
    {"node_map": {"N_t": "A_t", "N_next": "A_next"}, "edge_map": {"e_s": "e_t"}},  # 缺一个
    {"node_map": dict(GOLD["node_map"]), "edge_map": {}},                          # 缺超边
    {"node_map": {}, "edge_map": {}},                                              # 全空
    {"node_map": {"N_t": "r_t", "r_s": "A_t", "N_next": "A_next"},
     "edge_map": {"e_s": "e_t"}},                                                  # 角色错
], ids=["missing_node", "missing_edge", "empty", "role_swap"])
def test_denominator_never_shrinks(ternary, pred):
    tgt, src = ternary
    assert score_prediction(tgt, src, pred)["n_checks"] == 11


def test_no_candidate_scores_zero(ternary):
    """无候选任务两项记零（L1034），且不产生检查项。"""
    tgt, src = ternary
    r = score_prediction(tgt, src, None)
    assert r["has_candidate"] is False
    assert r["sf"] == 0.0
    assert r["sipr"] == 0


def test_lazy_candidate_never_outranks_correct_one(ternary):
    """漏答的候选不可能比正确映射得分高——这是分母收缩 bug 的直接守卫。"""
    tgt, src = ternary
    good = score_prediction(tgt, src, GOLD)["sf"]
    lazy = score_prediction(tgt, src, {"node_map": dict(GOLD["node_map"]),
                                       "edge_map": {}})["sf"]
    assert lazy < good


# ---------------------------------------------------------------------------
# 3. 双射与重复占用（L341："不能遗漏或重复占用"）
# ---------------------------------------------------------------------------

def test_duplicate_occupation_is_rejected(ternary):
    """两个源节点占用同一目标节点：双射失败、被占节点失败、不得满分。

    回归守卫：旧实现用 next() 反查会静默取第一个源节点，把重复占用洗成通过。
    """
    tgt, src = ternary
    dup = {"node_map": {"N_t": "A_t", "r_s": "A_t", "N_next": "A_next"},
           "edge_map": {"e_s": "e_t"}}
    r = score_prediction(tgt, src, dup)
    assert r["n_checks"] == 11
    assert r["checks"]["node_bijection"]["passed"] is False
    assert r["checks"]["node_type:A_t"]["passed"] is False
    assert r["sipr"] == 0
    assert r["sf"] < 1.0


def test_duplicate_edge_occupation_is_rejected(ternary):
    """两条源超边占用同一目标超边：超边双射失败。"""
    tgt, src = ternary
    dup = {"node_map": dict(GOLD["node_map"]),
           "edge_map": {"e_s": "e_t", "e_extra": "e_t"}}
    r = score_prediction(tgt, src, dup)
    assert r["checks"]["edge_bijection"]["passed"] is False
    assert r["sipr"] == 0


def test_missing_mapping_breaks_bijection(ternary):
    """遗漏一个源节点：双射必须失败。"""
    tgt, src = ternary
    r = score_prediction(tgt, src, {"node_map": {"N_t": "A_t", "N_next": "A_next"},
                                    "edge_map": {"e_s": "e_t"}})
    assert r["checks"]["node_bijection"]["passed"] is False
    assert r["sipr"] == 0


# ---------------------------------------------------------------------------
# 4. 错误归类不串味
# ---------------------------------------------------------------------------

def test_type_error_isolated(ternary):
    """把一个目标的节点类型改掉，只应产生 1 项 type_error。"""
    import copy
    tgt, src = ternary
    tgt = copy.deepcopy(tgt)
    tgt["_nodes"]["A_t"]["type"] = "ratio"
    r = score_prediction(tgt, src, GOLD)
    assert r["error_breakdown"]["type_error"] == 1
    assert r["error_breakdown"]["role_error"] == 0


def test_missing_node_buckets(ternary):
    """缺一个节点映射：恰好 1 项 type、2 项 endpoint、1 项 role 失败。"""
    tgt, src = ternary
    r = score_prediction(tgt, src, {"node_map": {"N_t": "A_t", "N_next": "A_next"},
                                    "edge_map": {"e_s": "e_t"}})
    assert r["error_breakdown"] == {"type_error": 1, "endpoint_error": 2, "role_error": 1}


def test_output_miswired_hits_endpoints_and_roles(ternary):
    """输出节点接错：端点集合与角色都应报错。"""
    tgt, src = ternary
    pred = {"node_map": {"N_t": "A_next", "r_s": "r_t", "N_next": "A_t"},
            "edge_map": {"e_s": "e_t"}}
    r = score_prediction(tgt, src, pred)
    assert r["error_breakdown"]["endpoint_error"] == 2
    assert r["error_breakdown"]["role_error"] == 2
    assert r["sipr"] == 0


# ---------------------------------------------------------------------------
# 5. 聚合口径（L1034）
# ---------------------------------------------------------------------------

def test_aggregate_averages_over_all_tasks(ternary):
    """SF/SIPR 是任务平均；无候选任务计入分母。"""
    tgt, src = ternary
    per_task = [score_prediction(tgt, src, GOLD),      # SF=1, SIPR=1
                score_prediction(tgt, src, None)]      # 记零
    agg = aggregate(per_task)
    assert agg["n_tasks"] == 2
    assert agg["SF"] == pytest.approx(0.5)
    assert agg["SIPR"] == pytest.approx(0.5)
    assert agg["no_candidate"] == 1


def test_aggregate_handles_empty():
    assert aggregate([]) == {"n_tasks": 0, "SF": None, "SIPR": None}


# ---------------------------------------------------------------------------
# 6. 真实数据全量（守"数据与评价器口径一致"）
# ---------------------------------------------------------------------------

def test_real_mred_gold_mappings_score_perfect():
    """MRED 300 个正式组：gold 映射全部满分，且项数与结构推导式吻合。

    这一条最慢（几秒），但它是唯一能发现"数据被改坏"或"口径漂移"的守卫。
    """
    from metrics import iter_groups

    def expected_size(tgt):
        return (2 + len(tgt["nodes"]) + 3 * len(tgt["edges"])
                + sum(len(set(e["input_nodes"]) | set(e["output_nodes"]))
                      for e in tgt["edges"]))

    n_groups = n_tasks = 0
    for _rel, gdir in iter_groups("mred"):
        if not gdir.name.startswith("group_tr_"):
            continue
        grp = load_group(gdir)
        tgt_obj = grp["objects"].get(grp["manifest"]["object_ids"][0])
        assert tgt_obj is not None, f"{gdir.name}: 目标对象缺失"
        n_groups += 1
        want = expected_size(tgt_obj)
        for tid, ref in grp["reference"].items():
            if ref.get("label") != "positive" or not ref.get("valid"):
                continue
            truth = ref["valid"][0]
            src_obj = grp["objects"].get(truth["source_id"])
            assert src_obj is not None, f"{gdir.name}/{tid}: 源对象缺失"
            res = score_prediction(tgt_obj, src_obj,
                                   {"node_map": truth["node_map"],
                                    "edge_map": truth["edge_map"]})
            n_tasks += 1
            assert res["n_checks"] == want, f"{gdir.name}/{tid}: 项数 {res['n_checks']} != {want}"
            assert res["n_passed"] == want, f"{gdir.name}/{tid}: 未满分 {res['n_passed']}/{want}"
            assert res["sipr"] == 1, f"{gdir.name}/{tid}: SIPR=0"
            assert res["checks"]["node_bijection"]["passed"], \
                f"{gdir.name}/{tid}: gold 本身不是双射"

    assert n_groups == 300, f"正式组应为 300，实际 {n_groups}"
    assert n_tasks == 300, f"正任务应为 300，实际 {n_tasks}"


# ---------------------------------------------------------------------------
# T06：响应指标（CTC / Ebar / Rhat）与返回指标（VRR / FAR / Coverage）
# 任务书 L731-748、L772-788、L1039-1047
# ---------------------------------------------------------------------------

def test_response_error_matches_taskbook_table():
    """L748 三行数值表：(0.20,0.20)→0 / (0.44,0.20)→0.0576 / (-0.01,0.01)→0.0004。"""
    m = _metrics()
    for rs, rt, want in ((0.20, 0.20, 0.0), (0.44, 0.20, 0.0576),
                         (-0.01, 0.01, 0.0004)):
        assert abs(m.response_error(rs, rt) - want) < 1e-9


def test_sgn_eta_three_way_split():
    """L731：容差内归为 0（近似不变），两侧分别为 +1/-1。"""
    m = _metrics()
    assert m.sgn_eta(0.44, 0.001) == 1
    assert m.sgn_eta(-0.44, 0.001) == -1
    assert m.sgn_eta(0.003, 0.01) == 0
    assert m.sgn_eta(-0.003, 0.01) == 0


def test_rhat_is_max_not_mean():
    """L772：Rhat 是最大平均误差，不是平均。喂 0.001/0.002/0.08 → 0.08。"""
    import types
    m = _metrics()
    seq = {0: 0.0316228, 1: 0.0447214, 2: 0.2828427}
    tgt, src = {"designated_outputs": ["y"]}, {"designated_outputs": ["y"]}
    fake = types.ModuleType("runtime")
    fake.normalized_response = lambda o, u: {
        "y": 0.0 if o is tgt else seq[u["i"]]}
    orig = m.evaluate_response.__globals__["_import_runtime"]
    m.evaluate_response.__globals__["_import_runtime"] = lambda: fake
    try:
        r = m.evaluate_response(src, tgt, [{"i": 0}, {"i": 1}, {"i": 2}])
    finally:
        m.evaluate_response.__globals__["_import_runtime"] = orig
    assert abs(r["rhat"] - 0.08) < 1e-3
    assert abs(r["ebar"] - 0.027666) < 1e-3


def test_no_intervention_points_means_not_done():
    """L788：没有完成任何干预时 CTC/Ebar 无定义，不能按零误差通过。"""
    m = _metrics()
    r = m.evaluate_response({"designated_outputs": ["y"]},
                            {"designated_outputs": ["y"]}, [])
    assert r["ctc"] is None and r["ebar"] is None and r["rhat"] is None
    assert r["status"] != "ok"


def test_square_counterexample_direction_ok_but_error_high():
    """平方反例：CTC=1（方向一致）但 Rhat=0.0576 > 容差 0.05。

    这正是任务书要求同时保留方向与幅度两个指标的理由（L780 的表格）。
    """
    m = _metrics()
    dev = m.CASES / "multiplicative_growth" / "group_dev_0001"
    if not dev.is_dir():
        pytest.skip("缺 dev 组")
    g = m.load_group(dev)
    tgt = g["objects"][g["manifest"]["object_ids"][0]]
    sq = g["objects"]["obj_group_dev_0001_i08"]
    r = m.evaluate_response(sq, tgt, [{"v7": 0.2, "v4": 0.0}])
    assert r["ctc"] == 1.0
    assert abs(r["rhat"] - 0.0576) < 1e-9


def test_return_metrics_vrr_far_coverage():
    """L1043-1047：正任务返回错误映射只降 VRR，不计入 FAR。"""
    m = _metrics()
    a = m.aggregate([
        dict(task_id="p1", label="positive", has_candidate=True, valid=True,
             sf=1.0, sipr=1, response=None),
        dict(task_id="p2", label="positive", has_candidate=True, valid=False,
             sf=0.5, sipr=0, response=None),
        dict(task_id="n1", label="negative", has_candidate=False, valid=False,
             sf=0.0, sipr=0, response=None),
    ])
    assert a["VRR"] == 0.5        # 只有 p1 返回且有效
    assert a["FAR"] == 0.0        # n1 没返回
    assert abs(a["Coverage"] - 2 / 3) < 1e-12


def test_empty_denominator_is_na_not_zero():
    """任一分母为空记 N/A(None)，不能写 0——0 会被读成表现完美。"""
    m = _metrics()
    a = m.aggregate([dict(task_id="p1", label="positive", has_candidate=True,
                          valid=True, sf=1.0, sipr=1, response=None)])
    assert a["FAR"] is None
    assert a["CTC"] is None and a["Ebar"] is None
