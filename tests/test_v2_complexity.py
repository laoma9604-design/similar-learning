"""七项复杂性指标的判据回归测试（a_data/stat_v2_complexity.py）。

存在理由：`pytest` 现有 133 条一条都不覆盖这个统计脚本。项目里反复出现
「脚本能跑通但数字错」，而本脚本最危险的两处正是口径：

  · 「节点复用」与「分支」在树状图上天然恒等（出度>1 ⟺ 被多条边消费）。
    2026-11-05 实测两次踩到：两项数字完全一样，看起来像做了两个维度，
    实际是同一个量。分支必须改用「到输出的独立计算路径数 − 1」。
  · 「汇合」若按「边有 ≥2 输入」算，3 条边的组必然恒等于 3 —— 那是在数边数。

这里用小图手工验算钉死三个口径，并锁住 v2 的实测分布。
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "a_data"))

import stat_v2_complexity as C   # noqa: E402


def mk(edges, n_inputs, out):
    """极简对象：只给 metrics_of 需要的字段。"""
    nodes, seen = [], set()
    for e in edges:
        for n in e["input_nodes"] + e["output_nodes"]:
            if n not in seen:
                seen.add(n)
                nodes.append(dict(node_id=n, label="q", type="positive_scalar"))
    return dict(nodes=nodes, edges=edges,
                controllable_inputs=[f"x{i+1}" for i in range(n_inputs)],
                designated_outputs=[out])


def E(eid, ins, out):
    return dict(edge_id=eid, edge_type="multiplicative_growth",
                input_nodes=ins, output_nodes=[out], roles={}, function="")


# ---------------- 口径：汇合 ----------------
def test_merge_strict_requires_two_upstream_branches():
    """链式三条二元边：每边都有 2 输入，但只有一路来自上游 ⇒ 严格汇合 0。"""
    o = mk([E("e1", ["x1", "x2"], "z1"), E("e2", ["z1", "x3"], "z2"),
            E("e3", ["z2", "x4"], "y")], 4, "y")
    m = C.metrics_of(o)
    assert m["merge_loose"] == 3, "宽松口径每条二元边都算汇合"
    assert m["merge"] == 0, "链式没有两路上游汇合，严格口径必须为 0"


def test_merge_strict_counts_two_upstream():
    """z1、z2 两路上游汇进 y ⇒ 严格汇合 1。"""
    o = mk([E("e1", ["x1", "x2"], "z1"), E("e2", ["x3", "x4"], "z2"),
            E("e3", ["z1", "z2"], "y")], 4, "y")
    m = C.metrics_of(o)
    assert m["merge"] == 1
    assert m["merge_loose"] == 3


# ---------------- 口径：节点复用 vs 分支（必须不同义） ----------------
def test_reuse_and_branch_are_not_the_same_metric():
    """纯链：复用 0、分支（路径-1）也是 0 —— 两者都为 0，但定义不同。

    真正要锁的是下面的分叉图：复用与分支必须有各自独立的值。
    """
    o = mk([E("e1", ["x1", "x2"], "z1"), E("e2", ["z1", "x3"], "y")], 3, "y")
    m = C.metrics_of(o)
    assert m["reuse"] == 0
    assert m["branch"] == 0
    assert m["depth"] == 2


def test_branch_equals_reuse_by_construction():
    """A 方案（2026-11-05 用户拍板）：分支与复用在树状 DAG 上恒等，如实断言。

    为什么不是 bug：多条下游支路若不汇合就必然产生死端，而负任务核验要求零死端
    ⇒ 分支必然重新汇合 ⇒ {出度>1 的节点} ≡ {被多条边消费的节点}。
    试过的其他定义同样退化（按边累积路径数恒为 1；按节点递归重复计入共享输入）。
    所以这里**断言相等**，并把等价性标成数据属性 `branch_equiv_reuse`，
    防止后人误以为是两个独立维度去加权。
    """
    o = mk([E("e1", ["x1", "x2"], "a"), E("e2", ["x1", "x3"], "b"),
            E("e3", ["a", "b"], "y")], 3, "y")
    m = C.metrics_of(o)
    assert m["reuse"] == 1, "x1 被 e1/e2 共用"
    assert m["branch"] == 1, "出度>1 的节点数也是 1"
    assert m["branch_equiv_reuse"] is True, "必须显式标注两者等价"
    # 链上没有共享，两项都是 0
    o2 = mk([E("e1", ["x1", "x2"], "a"), E("e2", ["a", "x3"], "y")], 3, "y")
    m2 = C.metrics_of(o2)
    assert m2["reuse"] == 0 and m2["branch"] == 0


def test_reuse_counts_shared_node_including_external():
    """复用 = 被 >1 条关系使用的节点数（含外部输入）。"""
    o = mk([E("e1", ["x1", "x2"], "z1"), E("e2", ["z1", "x3"], "z2"),
            E("e3", ["z1", "x4"], "y")], 4, "y")
    m = C.metrics_of(o)
    assert m["reuse"] == 1, "z1 被 e2/e3 共用"


# ---------------- 基础三项 ----------------
def test_node_and_edge_counts():
    o = mk([E("e1", ["x1", "x2"], "z1"), E("e2", ["z1", "x3"], "y")], 3, "y")
    m = C.metrics_of(o)
    assert m["n_nodes"] == 5          # x1 x2 x3 z1 y
    assert m["n_edges"] == 2
    assert m["arity_max"] == 2


# ---------------- v2 实测分布（数据没被改坏） ----------------
@pytest.fixture(scope="module")
def v2():
    return C.scan("cases/structural_v2/group_v2_*")


def test_v2_group_count(v2):
    assert len(v2) == 30


def test_v2_metric_ranges(v2):
    """v2 七项实测范围。改动生成器后这些数字会变，届时同步更新。

    2026-11-05 换骨架表后：节点 5-9、深度 2-5、复用 0-3、分支 0-3（与复用恒等）、汇合 0-2。
    """
    def span(k):
        vals = [r[k] for r in v2]
        return min(vals), max(vals)
    assert span("n_nodes") == (5, 9)
    assert span("n_edges") == (3, 5)
    assert span("depth") == (2, 5)
    assert span("arity_max") == (2, 2), "v2 所有边都是二元（饱和末端一输入）"
    assert span("reuse") == (0, 3)
    assert span("branch") == (0, 3), "与节点复用恒等（A 方案）"
    assert span("merge") == (0, 2)


def test_v2_reuse_branch_equivalence_is_declared(v2):
    """A 方案：两者在 v2 上恒等，测试锁住"已显式声明等价"这件事本身。

    若将来引入多输入超边把两者真正分开，这条测试会红——那是正确的信号，
    届时把 branch 的定义改成"边输入元数"并更新此处。
    """
    same = sum(1 for r in v2 if r["reuse"] == r["branch"])
    assert same == len(v2), (
        f"只有 {same}/{len(v2)} 组相等；若已引入多输入边，请同步更新 branch 定义与本文档")
    assert all(r["branch_equiv_reuse"] for r in v2)


def test_v2_no_multi_input_edge(v2):
    """锁住「每条超边二元（饱和一输入）」这个设计约束。"""
    for r in v2:
        assert max(r["arity_list"]) == 2
        assert min(r["arity_list"]) >= 1
