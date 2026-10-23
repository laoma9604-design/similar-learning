"""统一运行入口的共享接口定义。

对齐依据：
- T01-schema.json 的记录字段（Task/Candidate/Audit/Prediction/Reference）
- 任务书 sec:route（四个接口函数）、sec:audit（调用计数规则）
本文件只定义"形状"（数据类型 + 函数签名），不实现方法逻辑。
分工：B 实现 generate，C 实现 audit，统一运行入口实现 predict，A 实现 evaluate。
字段的"必填/可选"以 T01-schema.json 为准，这里只对齐字段名与类型。
"""
from __future__ import annotations

from typing import Any, Optional, TypedDict


class Node(TypedDict, total=False):
    node_id: str
    label: str
    type: str  # τ_V，如 positive_scalar / entity / substance / ...


class Edge(TypedDict, total=False):
    edge_id: str
    edge_type: str  # τ_E，如 multiplicative_growth
    input_nodes: list[str]  # '-' 端
    output_nodes: list[str]  # '+' 端
    roles: dict[str, str]  # node_id -> role


class Object(TypedDict, total=False):
    object_id: str
    object_kind: str  # mechanistic | structural
    label: str
    nodes: list[Node]
    edges: list[Edge]
    # ---- 以下仅 mechanistic 对象有 ----
    function: str
    controllable_inputs: list[str]  # J
    designated_outputs: list[str]  # Y
    baseline: list[float]  # 按 controllable_inputs 顺序
    input_scales: list[float]
    baseline_output: float
    output_scale: float
    legal_domain: dict[str, list[Optional[float]]]  # null = 无穷
    intervention_bounds: dict[str, list[float]]
    provenance: dict[str, Any]


class Task(TypedDict):
    task_id: str
    group_id: str
    target_id: str
    source_ids: list[str]
    schema_version: str
    vocab_version: str
    intervenable_inputs: list[str]  # 目标域可干预输入 J
    specified_outputs: list[str]  # 目标域指定输出 Y
    intervention_range: dict[str, list[float]]


class Candidate(TypedDict):
    candidate_id: str
    task_id: str
    source_id: str
    node_map: dict[str, str]  # source -> target 双射
    edge_map: dict[str, str]  # source -> target 双射
    raw_score: float
    generation_order: int
    method: str
    structure_check: dict[str, Any]  # {passed, failed_items, per_item}


class InterventionPoint(TypedDict, total=False):
    u: dict[str, float]  # 无量纲扰动
    target_input: dict[str, float]
    source_input: dict[str, float]
    target_output: dict[str, float]
    source_output: dict[str, float]
    r_target: dict[str, float]
    r_source: dict[str, float]
    error: float
    new_calls: int  # 本次新增调用 0/1/2
    cache_hit: bool


class Audit(TypedDict):
    candidate_id: str
    task_id: str
    interventions: list[InterventionPoint]
    CTC: float  # 一致通过比例
    Ebar: float  # 最大误差
    Rhat: float
    baseline_calls: int  # 单列，不占每候选干预预算
    total_new_calls: int
    completed_interventions: int
    termination_reason: str


class Prediction(TypedDict):
    task_id: str
    returned: bool
    final_candidate_id: Optional[str]
    source_id: Optional[str]
    rejection_reason: Optional[str]
    stage_timings: dict[str, float]
    model_calls: int
    function_calls: int
    explanation_file: Optional[str]


class Reference(TypedDict):
    task_id: str
    label: str  # positive | negative
    valid: list[dict[str, Any]]  # 正任务必填，负任务为空
    exclusions: list[dict[str, Any]]  # 负任务必填
    reference_tolerance: dict[str, float]  # {min_ctc, max_error}
    status: str


class Config(TypedDict, total=False):
    seed: int
    # budget 键名对齐任务书：B_call / B_I / G
    budget: dict[str, Any]
    # 方法筛选阈值 γ(CTC 下限) / ζ(误差上限)
    thresholds: dict[str, float]
    # 各方法自定义项，统一运行入口不解读
    method_specific: dict[str, Any]


def generate(task: Task, config: Config) -> list[Candidate]:
    """B 或基线适配器：给定任务，返回原始候选列表。

    每个候选含源域、节点/超边映射、方法分数与生成顺序；失败也要返回原因。
    """
    raise NotImplementedError


def audit(task: Task, candidate: Candidate, config: Config) -> Audit:
    """C：对指定映射施加干预，返回逐点记录、汇总指标、实际调用与停止原因。

    不可执行或初始化未完成时，必须明确返回该状态，不得伪造零误差。
    """
    raise NotImplementedError


def predict(
    task: Task,
    candidates: list[Candidate],
    audits: list[Audit],
    config: Config,
) -> Prediction:
    """统一运行入口：按方法规则选最终映射或拒绝，保留选中候选 ID 与全部拒绝原因。

    原始候选文件继续保存。任务书原签名 predict(task, candidates, audits)；
    这里补 config 用于读筛选阈值 γ/ζ，属实现细节。
    """
    raise NotImplementedError


def evaluate(
    predictions: list[Prediction],
    references: list[Reference],
) -> dict[str, Any]:
    """A：方法运行结束后读封存参考，输出逐任务指标与汇总所需分母。

    评价器不向方法反馈测试答案。
    """
    raise NotImplementedError
