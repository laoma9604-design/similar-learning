"""stat_structure.py / stat_difficulty.py 的判据单元测试。

存在理由：这两个脚本是我新增的统计工具，项目既有的 90 条测试一条都不覆盖它们。
开发过程中实测踩到 5 个 bug，全都"脚本能跑通"但数字是错的：
  1. 漏返回 depth 键 -> KeyError
  2. 深度算法没算「外部输入」，单超边也报 0
  3. 深度算法的剥离循环污染了 produced，导致节点复用全报 True
  4. 「线性(仅四则)」漏判除号，产出「线性+除式」这种自相矛盾标签
  5. 响应分类四版来回翻转（局部/幅度）
本测试用构造出来的小超图逐条钉死这些判据。

跑法：python -m pytest tests/test_stat_structure.py -q
"""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "a_data"))

import stat_structure as S  # noqa: E402


def mk(edges, function="a + b", nodes=None):
    """构造一个最小对象。edges = [([输入], [输出]), ...]"""
    ids = nodes or sorted({n for e in edges for n in e[0] + e[1]})
    return {
        "nodes": [{"node_id": n, "type": "positive_scalar"} for n in ids],
        "edges": [{"input_nodes": list(i), "output_nodes": list(o)} for i, o in edges],
        "function": function,
    }


# ---------------- 拓扑深度 ----------------
@pytest.mark.parametrize("edges,expected", [
    ([], 0),                                          # 无边
    ([(["a"], ["b"])], 1),                            # 单边
    ([(["a", "b"], ["c"])], 1),                       # 单边多输入（本库全部如此）
    ([(["a"], ["b"]), (["b"], ["c"])], 2),            # 两跳链
    ([(["a"], ["b"]), (["b"], ["c"]), (["c"], ["d"])], 3),   # 三跳链
    ([(["a"], ["b"]), (["c"], ["d"])], 1),            # 两条互不相连的边
    ([(["a", "b"], ["c"]), (["c", "d"], ["e"])], 2),  # 汇合后接力
])
def test_depth(edges, expected):
    assert S.measure(mk(edges))["depth"] == expected


def test_depth_key_always_present():
    """曾漏返回 depth 键，统计时裸 KeyError。"""
    assert "depth" in S.measure(mk([(["a"], ["b"])]))


# ---------------- 节点复用 ----------------
def test_node_reuse_false_for_star_topology():
    """本库形态：a,b -> c，无任何节点被复用。曾因变量污染全部误报 True。"""
    assert S.measure(mk([(["a", "b"], ["c"])]))["node_reuse"] is False


def test_node_reuse_false_for_two_independent_edges():
    assert S.measure(mk([(["a"], ["b"]), (["c"], ["d"])]))["node_reuse"] is False


def test_node_reuse_true_when_chained():
    """b 既被产出又被消费 = 复用。"""
    assert S.measure(mk([(["a"], ["b"]), (["b"], ["c"])]))["node_reuse"] is True


def test_node_reuse_true_when_multi_edge():
    """a 同时参与两条边（输入侧并入两条）= 复用。"""
    assert S.measure(mk([(["a", "b"], ["c"]), (["a"], ["d"])]))["node_reuse"] is True


# ---------------- 函数类型 ----------------
def test_func_only_four_ops():
    m = S.measure(mk([(["a"], ["b"])], function="a * (1 + b)"))
    assert m["func_ops"]["仅四则(线性)"] is True
    assert not m["func_ops"]["除式"]


def test_func_div_is_not_linear():
    """曾只查幂次，把含除式也算成线性 -> 标签自相矛盾。"""
    m = S.measure(mk([(["a"], ["b"])], function="a / b"))
    assert m["func_ops"]["仅四则(线性)"] is False
    assert m["func_ops"]["除式"] is True


def test_func_pow_and_exp():
    m = S.measure(mk([(["a"], ["b"])], function="a ** 2 + exp(b)"))
    assert m["func_ops"]["幂次"] and m["func_ops"]["指数"]
    assert m["func_ops"]["仅四则(线性)"] is False


def test_func_labels_mutually_consistent():
    """「仅四则」与任何其他算子标签不得并存（曾出现「线性+除式」）。"""
    for f in ["a + b", "a / b", "a ** 2", "a * exp(b)"]:
        ops = S.measure(mk([(["a"], ["b"])], function=f))["func_ops"]
        if ops["仅四则(线性)"]:
            assert not (ops["幂次"] or ops["指数"] or ops["除式"]), f


# ---------------- 输入/输出元数、规模 ----------------
def test_arity_and_scale():
    m = S.measure(mk([(["a", "b"], ["c"])]))
    assert m["in_arity"] == [2]
    assert m["out_arity"] == [1]
    assert m["n_nodes"] == 3
    assert m["n_edges"] == 1


def test_saturation_like_single_input():
    m = S.measure(mk([(["a"], ["b"])], function="10 * a / (1 + a)"))
    assert m["in_arity"] == [1]
    assert m["n_edges"] == 1


# ---------------- 结构难度分档 ----------------
@pytest.mark.skipif(
    importlib.util.find_spec("runtime") is None,
    reason="stat_difficulty 依赖 runtime，缺失则跳过")
def test_structural_difficulty_tiers():
    import stat_difficulty as D
    assert D.structural_difficulty(mk([(["a", "b"], ["c"])])) == "single"
    # 两条互不相连的边
    assert D.structural_difficulty(mk([(["a"], ["b"]), (["c"], ["d"])])) == "multi"
    # 汇合 merge：多条边的输出汇聚到同一节点
    assert D.structural_difficulty(mk([(["a"], ["c"]), (["b"], ["c"])])) == "merge"
    # 分支 branch：同一节点被多条边消费
    assert D.structural_difficulty(mk([(["a"], ["b"]), (["a"], ["c"])])) == "branch"
    # 分支 + 汇合同时存在
    assert D.structural_difficulty(
        mk([(["a"], ["b"]), (["a"], ["c"]), (["b"], ["d"]), (["c"], ["d"])])
    ) == "branch+merge"


def test_structural_edge_cases():
    import stat_difficulty as D
    assert D.structural_difficulty(mk([])) == "empty"
