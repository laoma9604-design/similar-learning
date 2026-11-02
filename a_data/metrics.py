"""独立结构评价器 —— 逐任务检查清单 + SF / SIPR（任务书 L1026-1036）。

只做 E01 的结构指标，不含响应指标（CTC/Ebar 需要 audit 记录，由 C 侧产出）。

检查清单（任务书 L1034 原文）：
    统一检查清单包含：节点双射与超边双射各一项，每个节点的类型一项，
    每条超边的类型、输入集合和输出集合各一项，每个节点--超边关联的角色一项。

项数 = 2 + |V_t| + 3|E_t| + Σ_e |participants(e)|，由目标域结构决定，不是常数：
    三节点三元超边 -> 11（任务书 L1036 的例子）
    二节点二元超边 -> 9（饱和响应）

三项分类错误（任务书 L1327 要求"类型、端点、角色三类错误比例"）：
    type_error    节点类型 / 超边类型不匹配
    endpoint_error 节点双射 / 超边双射 / 超边输入集合 / 超边输出集合失败
    role_error    节点--超边角色不匹配

重要：节点 ID 在源域一侧是随机名（b2/b1/b4），目标域可能是语义名
（current/ratio/next）。角色判断一律读 edges[].roles，不得用 node_id 字面比较。

用法（命令行）：
    python a_data/metrics.py --selftest        # 用任务书已知答案自检
    python a_data/metrics.py --dataset mred    # 跑 MRED 全部组的自评价
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "cases"

CHECK_KEYS = ("node_bijection", "edge_bijection")


# --------------------------------------------------------------------------
# 对象加载
# --------------------------------------------------------------------------

def load_object(path: Path) -> dict[str, Any]:
    """读一个 object JSON，补出按 node_id / edge_id 索引的视图。"""
    obj = json.loads(path.read_text(encoding="utf-8"))
    obj["_nodes"] = {n["node_id"]: n for n in obj.get("nodes") or []}
    obj["_edges"] = {e["edge_id"]: e for e in obj.get("edges") or []}
    return obj


def load_group(group_dir: Path) -> dict[str, Any]:
    """读一个类比对组：对象表 + 封存参考（reference.json）。"""
    obj_dir = group_dir / "data" / "input" / "objects"
    objects: dict[str, dict[str, Any]] = {}
    if obj_dir.is_dir():
        for p in sorted(obj_dir.glob("*.json")):
            if p.name == "index.json":
                continue
            obj = load_object(p)
            objects[obj["object_id"]] = obj

    ref_path = group_dir / "sealed" / "reference.json"
    reference = {}
    if ref_path.is_file():
        reference = json.loads(ref_path.read_text(encoding="utf-8"))
    return {
        "group_id": group_dir.name,
        "group_dir": group_dir,          # 响应指标要读 sealed/intervention_points.json
        "objects": objects,
        "reference": reference,
        "manifest": json.loads((group_dir / "manifest.json").read_text(encoding="utf-8"))
        if (group_dir / "manifest.json").is_file()
        else {},
    }


# --------------------------------------------------------------------------
# 检查清单（11 项对应的通用构造）
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# 检查项分六类（与 L1034 的统一清单一一对应）
# 用于「该对象有原始依据可核验哪些项」的声明（adaptation.available_checks）
# --------------------------------------------------------------------------
CHECK_GROUPS = {
    "node_bijection": "节点双射",
    "edge_bijection": "超边双射",
    "node_type": "每个节点的类型",
    "edge_type": "每条超边的类型",
    "input_output_set": "输入集合与输出集合",
    "role": "每个节点-超边关联的角色",
    # 结构模式专用（SCAR/SCAN）：与上面六类互斥使用
    "pair_consistency": "概念对应关系与参考一致（含多值端点）",
    "type_pattern": "类型对应模式与参考一致（不要求两端同类型）",
}

# 结构模式可用的检查项（机械模式的六类不适用于跨范畴类比）
STRUCTURAL_CHECKS = ("pair_consistency", "type_pattern")


def build_structural_checks(tgt, src, cand_pairs, ref_pairs,
                            type_pattern_required=True,
                            ref_type_pattern=None,
                            ref_roles=None):
    """结构模式（SCAR/SCAN）的检查清单。

    为什么不用机械模式的六类（实测依据，2026-11-02）：
      · node_bijection：SCAR 存在多值对应（virus→code,malware / sperm,egg→product），
        双射必然失败，与真实结构矛盾
      · node_type（要求两端同类型）：SCAR 的正确映射中 32.5% 是跨类型
        （virus(实体)↔code(抽象)、vaccine(物质)↔antivirus(实体)），
        跨范畴正是类比的核心机制，要求同类型会误伤正确答案

    三项检查：
      pair_consistency 候选的概念对应集合必须与参考一致（顺序无关，含多值端点）
      type_pattern     候选的类型对应模式必须与参考一致
      role_consistency 有角色依据的节点，候选必须保持同一角色
                       （仅当 reference 提供 ref_roles 时才启用）
    """
    checks = {}

    def pairset(pairs):
        return {(str(a), str(b)) for a, b in pairs}

    cs, rs = pairset(cand_pairs), pairset(ref_pairs)
    checks["pair_consistency"] = {
        "kind": "endpoint_error", "passed": cs == rs,
        "detail": (f"候选 {len(cs)} 对 / 参考 {len(rs)} 对；"
                   f"缺 {sorted(rs - cs)[:3]} 多 {sorted(cs - rs)[:3]}"),
    }

    if type_pattern_required:
        tmap = {n["node_id"]: n.get("type") for n in tgt["nodes"]}
        smap = {n["node_id"]: n.get("type") for n in src["nodes"]}
        cpat = sorted([smap.get(a), tmap.get(b)] for a, b in cand_pairs)
        if ref_type_pattern is not None:
            rpat = [list(x) for x in ref_type_pattern]
        else:
            rpat = sorted([smap.get(a), tmap.get(b)] for a, b in ref_pairs)
        checks["type_pattern"] = {
            "kind": "type_error", "passed": cpat == rpat,
            "detail": f"候选 {cpat[:3]} / 参考 {rpat[:3]}",
        }

    # ---- 角色一致性：只有原文明确给出角色的节点才检查 ----
    # ref_roles: {节点ID: 角色}，只含 Explanation 有依据的节点。
    # 无依据的节点不在其中，不参与本项 —— 不能用词义推测补。
    if ref_roles:
        # roles 挂在超边上（edge.roles）。角色依据可能落在源域或目标域，
        # 两域的角色表都要查，否则目标端标注全部失效（实测漏掉 3 组）。
        role_by_node = {}
        for obj in (src, tgt):
            for e in obj.get("_edges", {}).values():
                role_by_node.update(e.get("roles") or {})
        mismatch = []
        for nid, want in ref_roles.items():
            got = role_by_node.get(nid)
            if got != want:
                mismatch.append(f"{nid}: 候选{got} != 参考{want}")
        checks["role_consistency"] = {
            "kind": "role_error", "passed": not mismatch,
            "detail": (f"{len(ref_roles)} 个有依据节点，"
                       f"{len(mismatch)} 个角色不符: {mismatch[:3]}")
            if mismatch else f"{len(ref_roles)} 个有依据节点角色全部一致",
        }

    return checks

# 检查项 key → 类别（key 形如 node_type:<node_id>、role:<node_id>）
def _group_of(check_key: str) -> str:
    return check_key.split(":", 1)[0]


def build_checks(target: dict[str, Any], src: dict[str, Any],
                 node_map: dict[str, str], edge_map: dict[str, str],
                 available: list[str] | None = None) -> dict[str, dict[str, Any]]:
    """按参考结构构造完整检查清单，逐项判定候选映射是否通过。

    返回 {check_key: {"kind": ..., "passed": bool, "detail": ...}}
    清单由**目标域完整参考结构**确定（任务书 L1034"清单由完整参考结构确定，
    未匹配项记失败"），所以先遍历 target，再看候选有没有给出对应匹配。

    available: 该对象**有原始依据可核验**的检查项类别（Six 类，见 CHECK_GROUPS）。
        None → 不做过滤，清单与 MRED 一致（11 项 / 二元 9 项），保持既有行为。
        给出时 → 只保留声明为可用的类别；其余类别不进分母（不是判失败）。
        依据：L1034「清单由完整参考结构确定」——SCAR 的完整参考结构里
        本来就没有类型/角色/方向这三类标注，它们不属于该任务的检查项集合。
        绝不用「词义相似」之类猜测去补这些项（规范1）。
    """
    checks: dict[str, dict[str, Any]] = {}
    tnodes, tedges = target["_nodes"], target["_edges"]
    snodes, sedges = src["_nodes"], src["_edges"]

    # ---- 端点类：节点双射 / 超边双射 ----
    t_node_ids = set(tnodes)
    s_node_ids = set(snodes)

    # 节点双射：参考目标节点全被覆盖、映射单射、且不存在多余映射
    mapped_targets = [v for v in node_map.values()]
    node_bijection_ok = (
        t_node_ids.issubset(set(mapped_targets))
        and len(set(mapped_targets)) == len(mapped_targets)
        and set(node_map) == s_node_ids
    )
    checks["node_bijection"] = {
        "kind": "endpoint_error", "passed": node_bijection_ok,
        "detail": f"node_map={node_map}",
    }

    t_edge_ids = set(tedges)
    s_edge_ids = set(sedges)
    mapped_t_edges = list(edge_map.values())
    edge_bijection_ok = (
        t_edge_ids.issubset(set(mapped_t_edges))
        and len(set(mapped_t_edges)) == len(mapped_t_edges)
        and set(edge_map) == s_edge_ids
    )
    checks["edge_bijection"] = {
        "kind": "endpoint_error", "passed": edge_bijection_ok,
        "detail": f"edge_map={edge_map}",
    }

    # ---- 逐节点类型 ----
    # 反查必须先建索引，不能逐个 next() 扫描：重复映射到同一目标时，
    # next() 会静默取第一个源节点，把"重复占用"洗成通过（任务书 L341 禁止重复占用）。
    # 这里保留全部反查候选，多于一个即判该目标节点被重复占用。
    rev_nodes: dict[str, list[str]] = {}
    for s_id, t_id in node_map.items():
        rev_nodes.setdefault(t_id, []).append(s_id)

    for nid in sorted(tnodes):
        t_type = tnodes[nid].get("type")
        srcs = rev_nodes.get(nid) or []
        if not srcs or any(s not in snodes for s in srcs):
            checks[f"node_type:{nid}"] = {
                "kind": "type_error", "passed": False,
                "detail": f"目标节点 {nid} 无有效源节点映射",
            }
            continue
        if len(srcs) > 1:
            # 重复占用（非双射），本节点无法确定唯一对应，判失败
            checks[f"node_type:{nid}"] = {
                "kind": "endpoint_error", "passed": False,
                "detail": f"目标节点 {nid} 被 {len(srcs)} 个源节点重复占用 {srcs}",
            }
            continue
        src_nid = srcs[0]
        s_type = snodes[src_nid].get("type")
        checks[f"node_type:{nid}"] = {
            "kind": "type_error", "passed": s_type == t_type,
            "detail": f"{src_nid}({s_type}) -> {nid}({t_type})",
        }

    # ---- 逐超边：类型 / 输入集合 / 输出集合 ----
    rev_edges: dict[str, list[str]] = {}
    for s_id, t_id in edge_map.items():
        rev_edges.setdefault(t_id, []).append(s_id)

    for tid in sorted(tedges):
        te = tedges[tid]
        srcs_e = rev_edges.get(tid) or []
        # 唯一反查：多于一个即重复占用，按"无对应"处理（双射已单独判失败）
        src_eid = srcs_e[0] if len(srcs_e) == 1 else None
        se = sedges.get(src_eid) if src_eid else None

        if se is None:
            for suffix, kind in (("type", "type_error"),
                                 ("inputs", "endpoint_error"), ("outputs", "endpoint_error")):
                checks[f"edge_{suffix}:{tid}"] = {
                    "kind": kind, "passed": False,
                    "detail": f"目标超边 {tid} 无源超边映射",
                }
            # 角色项同样要占位，保证清单项数恒定（L1034 未匹配项记失败）
            for t_nid in sorted(set(te.get("input_nodes") or []) | set(te.get("output_nodes") or [])):
                checks[f"role:{t_nid}@{tid}"] = {
                    "kind": "role_error", "passed": False,
                    "detail": f"目标超边 {tid} 无源超边映射，角色无从比较",
                }
            continue

        checks[f"edge_type:{tid}"] = {
            "kind": "type_error",
            "passed": se.get("edge_type") == te.get("edge_type"),
            "detail": f"{src_eid}({se.get('edge_type')}) -> {tid}({te.get('edge_type')})",
        }

        # 输入/输出集合：源侧集合经 node_map 映射后必须等于目标侧集合
        for suffix, fld in (("inputs", "input_nodes"), ("outputs", "output_nodes")):
            mapped = {node_map.get(x) for x in se.get(fld) or []}
            want = set(te.get(fld) or [])
            checks[f"edge_{suffix}:{tid}"] = {
                "kind": "endpoint_error", "passed": mapped == want,
                "detail": f"mapped={sorted(x for x in mapped if x)} want={sorted(want)}",
            }

        # ---- 逐节点-超边关联的角色 ----
        # 清单由**目标域**参考结构确定（L1034"清单由完整参考结构确定，未匹配项记失败"），
        # 所以按目标侧参与者遍历，源侧没给出对应映射的记失败——分母不随候选变化。
        participants = set(te.get("input_nodes") or []) | set(te.get("output_nodes") or [])
        for t_nid in sorted(participants):
            cand = rev_nodes.get(t_nid) or []
            s_nid = cand[0] if len(cand) == 1 else None
            if s_nid is None or se is None:
                checks[f"role:{t_nid}@{tid}"] = {
                    "kind": "role_error", "passed": False,
                    "detail": f"目标节点 {t_nid} 无唯一源节点映射到本关系",
                }
                continue
            s_role = (se.get("roles") or {}).get(s_nid)
            t_role = (te.get("roles") or {}).get(t_nid)
            checks[f"role:{t_nid}@{tid}"] = {
                "kind": "role_error", "passed": s_role == t_role and s_role is not None,
                "detail": f"{s_nid}({s_role}) -> {t_nid}({t_role})",
            }

    # ---- 按「该对象有原始依据可核验的项」过滤 ----
    # available=None 时不过滤（MRED 行为不变）；
    # 给出时只保留声明可用的类别，其余整类不进分母（不是判失败）。
    if available is not None:
        keep = set(available)
        unknown = keep - set(CHECK_GROUPS)
        if unknown:
            raise ValueError(f"available_checks 含未知类别: {sorted(unknown)}；"
                             f"合法值: {sorted(CHECK_GROUPS)}")
        checks = {k: v for k, v in checks.items() if _group_of(k) in keep}
        if not checks:
            raise ValueError("available_checks 过滤后检查清单为空，"
                             "无法计算 SF/SIPR；请检查该对象的可用项声明")

    return checks


# --------------------------------------------------------------------------
# 任务评分
# --------------------------------------------------------------------------

def score_prediction(target: dict[str, Any], src: dict[str, Any],
                     prediction: dict[str, Any] | None,
                     available: list[str] | None = None,
                     valid_set: list[dict[str, Any]] | None = None,
                     ref_pairs: list | None = None,
                     ref_type_pattern: list | None = None,
                     ref_roles: dict | None = None) -> dict[str, Any]:
    """对单个任务的候选映射打分。prediction=None 表示方法无候选（两项记零）。

    available: 该对象有原始依据可核验的检查项类别；None 时与 MRED 口径一致。
    ref_pairs: **结构模式专用**。给出时改用 build_structural_checks，
        候选须提供 pair_map（[[源,目标],...]），按 pair 集合与类型模式判定。
        这是 SCAR/SCAN 的正确口径——机械模式的六类检查在跨范畴类比上会误伤。
    ref_type_pattern: 参考类型快照（reference.json 的 ref_type_pattern）。
        不传则 type_pattern 退化为基准随候选变化，形同自比，必须传。
    valid_set: **评价侧**提供的有效映射集合（来自 reference），不是模型提交的内容。
    """
    if prediction is None:
        return {
            "has_candidate": False, "sf": 0.0, "sipr": 0,
            "n_checks": 0, "n_passed": 0, "checks": {},
            "error_breakdown": {"type_error": 0, "endpoint_error": 0, "role_error": 0},
        }

    # ---- 结构模式（SCAR/SCAN）：按概念对应集合与类型模式判定 ----
    # 机械模式的六类检查（双射、两端同类型）在跨范畴类比上会误伤正确答案：
    # 实测 SCAR 正确映射中 32.5% 两端类型不同，多值对应也无法满足双射。
    if ref_pairs is not None:
        cand_pairs = prediction.get("pair_map")
        if cand_pairs is None:
            # 回退：从 node_map 还原（丢掉多值信息，但至少能量化）
            cand_pairs = [[s, t] for s, t in (prediction.get("node_map") or {}).items()]
        checks = build_structural_checks(target, src, cand_pairs, ref_pairs,
                                         ref_type_pattern=ref_type_pattern,
                                         ref_roles=ref_roles)
        n_total = len(checks)
        n_pass = sum(1 for c in checks.values() if c["passed"])
        breakdown = {"type_error": 0, "endpoint_error": 0, "role_error": 0}
        for c in checks.values():
            if not c["passed"]:
                breakdown[c["kind"]] += 1
        return {
            "has_candidate": True,
            "sf": n_pass / n_total if n_total else 0.0,
            "sipr": 1 if n_total and n_pass == n_total else 0,
            "n_checks": n_total, "n_passed": n_pass,
            "checks": checks,
            "error_breakdown": breakdown,
            "mode": "structural",
        }

    # ---- 有效映射集合（规范3）----
    # 一个任务可能有多条合理映射（多对一结构、置换对称等）。此时候选只要**完整命中**
    # 集合中任一条即算全通过；否则按最接近的那条报错。
    #
    # 关键：valid_set 必须来自**评价侧**（reference），不能从 prediction 里取。
    # 早期版本从 prediction 里取 valid_set 并拿它给自己 build_checks，等于用参考答案
    # 给自己打分，空映射/乱映射都能得满分（实测：空映射 SF=1.0）。评审发现后改为参数传入。
    if valid_set:
        # 模型提交的映射必须与集合中某一条**完全一致**（不是拿参考去给自己打分）
        try:
            cand_nm = prediction["node_map"]
            cand_em = prediction["edge_map"]
        except KeyError:
            cand_nm, cand_em = {}, {}
        for idx, ref in enumerate(valid_set):
            # 按内容比较，不按 dict 书写顺序：{n1:m2,n2:m1} 与 {n2:m1,n1:m2} 是同一映射
            if (dict(cand_nm) == dict(ref["node_map"])
                    and dict(cand_em) == dict(ref.get("edge_map") or {})):
                checks = build_checks(target, src, cand_nm, cand_em,
                                      available=available)
                n_total = len(checks)
                return {
                    "has_candidate": True, "sf": 1.0, "sipr": 1,
                    "n_checks": n_total, "n_passed": n_total,
                    "checks": checks, "matched_index": idx,
                    "valid_set_size": len(valid_set),
                    "error_breakdown": {"type_error": 0, "endpoint_error": 0,
                                        "role_error": 0},
                }
        # 未命中任何一条：按候选自身与第一条参考的差异报检查明细，SIPR 记 0
        ref = valid_set[0]
        checks = build_checks(target, src, cand_nm, cand_em, available=available)
        n_total = len(checks)
        n_pass = sum(1 for c in checks.values() if c["passed"])
        breakdown = {"type_error": 0, "endpoint_error": 0, "role_error": 0}
        for c in checks.values():
            if not c["passed"]:
                breakdown[c["kind"]] += 1
        return {
            "has_candidate": True,
            "sf": n_pass / n_total if n_total else 0.0,
            "sipr": 0,
            "n_checks": n_total, "n_passed": n_pass,
            "checks": checks, "matched_index": None,
            "valid_set_size": len(valid_set),
            "error_breakdown": breakdown,
        }

    checks = build_checks(target, src,
                          prediction["node_map"], prediction["edge_map"],
                          available=available)
    n_total = len(checks)
    n_pass = sum(1 for c in checks.values() if c["passed"])
    breakdown = {"type_error": 0, "endpoint_error": 0, "role_error": 0}
    for c in checks.values():
        if not c["passed"]:
            breakdown[c["kind"]] += 1

    return {
        "has_candidate": True,
        "sf": n_pass / n_total if n_total else 0.0,
        "sipr": 1 if n_pass == n_total and n_total else 0,
        "n_checks": n_total, "n_passed": n_pass,
        "checks": checks,
        "error_breakdown": breakdown,
    }


# --------------------------------------------------------------------------
# 响应指标（CTC / Ebar）与返回指标（VRR / FAR / Coverage）
# 任务书 L731-748（CTC/E）、L772-790（Rhat/阈值）、L1039-1047（三类指标定义）
# --------------------------------------------------------------------------

def _import_runtime():
    """按需导入求值器。

    metrics 平时只做结构评价（不需要函数），导入 runtime 会拉起表达式解析；
    放到函数里按需导入，保证只跑结构指标时行为不变。
    """
    import importlib
    if str(ROOT / "a_data") not in sys.path:
        sys.path.insert(0, str(ROOT / "a_data"))
    return importlib.import_module("runtime")


def sgn_eta(r: float, eta: float) -> int:
    """把响应分成 +1 / 0 / -1 三类（L731）。容差 η 在验证阶段固定。"""
    if r > eta:
        return 1
    if r < -eta:
        return -1
    return 0


def response_error(r_src: float, r_tgt: float) -> float:
    """E(f,I) 单输出形式：min{1, (r_s - r_t)^2}（L748 公式，先平方后截断）。"""
    d = r_src - r_tgt
    return min(1.0, d * d)


def evaluate_response(src_obj, tgt_obj, points, eta=0.001):
    """在一个任务的全部留出干预点上算 CTC 与 Ebar（任务内平均）。

    points: [{输入ID: 无量纲 u}, ...]，与 task.intervention_range 同构。
    两域用**同一组** u（映射决定了源域哪个输入被改变，L725）。

    返回：
      ctc       方向一致率 = 一致组合数 / (干预数 × 输出数)
      ebar      逐干预 E 的任务内平均
      rhat      已检查干预中的最大 E（L772）
      n_points  完成的干预数；0 表示检验未完成，CTC/Ebar 不得按 0 误差通过
    """
    rt = _import_runtime()
    outs = tgt_obj["designated_outputs"]
    n_pairs = n_agree = 0
    errs = []
    for u in points:
        r_t = rt.normalized_response(tgt_obj, u)
        r_s = rt.normalized_response(src_obj, u)
        e_out = 0.0
        for y in outs:
            a, b = r_s[y], r_t[y]
            if sgn_eta(a, eta) == sgn_eta(b, eta):
                n_agree += 1
            n_pairs += 1
            e_out += response_error(a, b)
        errs.append(e_out / len(outs))          # 先对输出取平均
    if not errs:
        return {"ctc": None, "ebar": None, "rhat": None, "n_points": 0,
                "status": "未完成（无干预点）"}
    return {
        "ctc": n_agree / n_pairs if n_pairs else None,
        "ebar": sum(errs) / len(errs),
        "rhat": max(errs),                       # 再对不同干预取最大
        "n_points": len(errs),
        "status": "ok",
    }


def score_return_behavior(per_task: list[dict[str, Any]],
                          labels: dict[str, str] | None = None) -> dict[str, Any]:
    """VRR / FAR / Coverage（L1043-1047）。

    a_i: 方法是否返回映射；v_i: 返回是否通过独立有效性检查（未返回记 0）。
    正任务返回错误映射只降低 VRR，不计入 FAR 分子。
    任一分母为空记 None（报 N/A），不写 0——0 会被读成"表现完美"。
    """
    pos = [t for t in per_task if t.get("label") == "positive"]
    neg = [t for t in per_task if t.get("label") == "negative"]
    vrr = (sum(1 for t in pos if t.get("has_candidate") and t.get("valid"))
           / len(pos)) if pos else None
    far = (sum(1 for t in neg if t.get("has_candidate")) / len(neg)) if neg else None
    cov = (sum(1 for t in per_task if t.get("has_candidate")) / len(per_task)
           if per_task else None)
    return {"VRR": vrr, "FAR": far, "Coverage": cov,
            "n_pos": len(pos), "n_neg": len(neg)}


def aggregate(per_task: list[dict[str, Any]]) -> dict[str, Any]:
    """SF 是检查项通过比例的任务平均；SIPR 是全部检查同时通过的任务比例（L1034）。

    无候选任务两项记零（L1034 原文），因此分母是全部任务数 N。
    响应指标（CTC/Ebar）先在任务内平均、再对**有响应的任务**平均（L1039：
    "没有可执行返回时记 N/A"），并报出实际任务数。
    """
    n = len(per_task)
    if n == 0:
        return {"n_tasks": 0, "SF": None, "SIPR": None}
    resp = [t for t in per_task if t.get("response")
            and t["response"].get("ctc") is not None]
    out = {
        "n_tasks": n,
        "SF": sum(t["sf"] for t in per_task) / n,
        "SIPR": sum(t["sipr"] for t in per_task) / n,
        "no_candidate": sum(0 if t["has_candidate"] else 1 for t in per_task),
    }
    if resp:
        out["CTC"] = sum(t["response"]["ctc"] for t in resp) / len(resp)
        out["Ebar"] = sum(t["response"]["ebar"] for t in resp) / len(resp)
        out["Rhat"] = sum(t["response"]["rhat"] for t in resp) / len(resp)
        out["n_response_tasks"] = len(resp)
    else:
        out["CTC"] = out["Ebar"] = out["Rhat"] = None
        out["n_response_tasks"] = 0
    out.update(score_return_behavior(per_task))
    return out


# --------------------------------------------------------------------------
# 自检：任务书已知答案（L132、L1036、L1113）
# --------------------------------------------------------------------------

def _synth_pair() -> tuple[dict, dict]:
    """三节点一条三元关系的最小例子（细菌增长 / 银行复利）。"""
    src = {
        "object_id": "src", "_nodes": {
            "N_t": {"node_id": "N_t", "type": "positive_scalar"},
            "r_s": {"node_id": "r_s", "type": "positive_scalar"},
            "N_next": {"node_id": "N_next", "type": "positive_scalar"},
        },
        "_edges": {"e_s": {"edge_id": "e_s", "edge_type": "multiplicative_growth",
                           "input_nodes": ["N_t", "r_s"], "output_nodes": ["N_next"],
                           "roles": {"N_t": "current", "r_s": "ratio", "N_next": "next"}}},
    }
    tgt = {
        "object_id": "tgt", "_nodes": {
            "A_t": {"node_id": "A_t", "type": "positive_scalar"},
            "r_t": {"node_id": "r_t", "type": "positive_scalar"},
            "A_next": {"node_id": "A_next", "type": "positive_scalar"},
        },
        "_edges": {"e_t": {"edge_id": "e_t", "edge_type": "multiplicative_growth",
                           "input_nodes": ["A_t", "r_t"], "output_nodes": ["A_next"],
                           "roles": {"A_t": "current", "r_t": "ratio", "A_next": "next"}}},
    }
    return tgt, src


def _synth_binary_pair() -> tuple[dict, dict]:
    """二节点一条二元关系（饱和响应形态），用于验证清单项数不是常数。"""
    def mk(prefix: str, in_id: str, out_id: str, edge_id: str) -> dict:
        return {
            "object_id": prefix,
            "_nodes": {in_id: {"node_id": in_id, "type": "positive_scalar"},
                       out_id: {"node_id": out_id, "type": "positive_scalar"}},
            "_edges": {edge_id: {"edge_id": edge_id, "edge_type": "saturation_response",
                                 "input_nodes": [in_id], "output_nodes": [out_id],
                                 "roles": {in_id: "input", out_id: "response"}}},
        }
    return mk("tgt", "input", "response", "r1"), mk("src", "in_s", "out_s", "e_s")


def selftest() -> int:
    """断言任务书给出的已知答案。返回退出码。"""
    tgt, src = _synth_pair()
    good = {"node_map": {"N_t": "A_t", "r_s": "r_t", "N_next": "A_next"},
            "edge_map": {"e_s": "e_t"}}

    failures: list[str] = []

    # 1) 正确映射：清单 11 项全过，SF=1、SIPR=1
    r = score_prediction(tgt, src, good)
    if r["n_checks"] != 11:
        failures.append(f"清单项数应为 11，实际 {r['n_checks']}")
    if abs(r["sf"] - 1.0) > 1e-12:
        failures.append(f"正确映射 SF 应为 1，实际 {r['sf']}")
    if r["sipr"] != 1:
        failures.append(f"正确映射 SIPR 应为 1，实际 {r['sipr']}")

    # 2) 交换两个输入角色：两项角色检查失败 -> SF=9/11、SIPR=0（L132 / L1036）
    swap = {"node_map": {"N_t": "r_t", "r_s": "A_t", "N_next": "A_next"},
            "edge_map": {"e_s": "e_t"}}
    r2 = score_prediction(tgt, src, swap)
    if r2["n_passed"] != 9:
        failures.append(f"角色交换例通过项应为 9，实际 {r2['n_passed']}")
    if abs(r2["sf"] - 9 / 11) > 1e-12:
        failures.append(f"角色交换例 SF 应为 9/11={9/11:.6f}，实际 {r2['sf']}")
    if r2["sipr"] != 0:
        failures.append(f"角色交换例 SIPR 应为 0，实际 {r2['sipr']}")
    if r2["error_breakdown"]["role_error"] != 2:
        failures.append(f"角色交换例应有 2 项 role 错误，实际 "
                        f"{r2['error_breakdown']['role_error']}")

    # 3) 无候选任务：两项记零（L1034）
    r3 = score_prediction(tgt, src, None)
    if r3["sf"] != 0.0 or r3["sipr"] != 0:
        failures.append("无候选任务 SF/SIPR 应都为 0")

    # 4) 类型错误应归到 type_error，不污染端点/角色
    tgt2 = json.loads(json.dumps(tgt))
    tgt2["_nodes"]["A_t"]["type"] = "ratio"
    r4 = score_prediction(tgt2, src, good)
    if r4["error_breakdown"]["type_error"] != 1:
        failures.append(f"改一个节点类型应得 1 项 type 错误，实际 "
                        f"{r4['error_breakdown']['type_error']}")

    # 5) 分母不随候选变化：缺一个节点映射时清单仍是 11 项，未匹配项记失败（L1034）
    partial = {"node_map": {"N_t": "A_t", "N_next": "A_next"}, "edge_map": {"e_s": "e_t"}}
    r5 = score_prediction(tgt, src, partial)
    if r5["n_checks"] != 11:
        failures.append(f"缺映射时清单仍应为 11 项，实际 {r5['n_checks']}")
    if r5["sipr"] != 0:
        failures.append("缺映射任务 SIPR 应为 0")
    if r5["n_passed"] >= 11:
        failures.append("缺映射任务不应满分")

    # 6) 空映射（方法什么都没返回）清单仍是 11 项
    r6 = score_prediction(tgt, src, {"node_map": {}, "edge_map": {}})
    if r6["n_checks"] != 11:
        failures.append(f"空映射时清单仍应为 11 项，实际 {r6['n_checks']}")
    if r6["n_passed"] != 0 or r6["sipr"] != 0:
        failures.append("空映射应 0 项通过")

    # 7) 项数随目标结构变化：二节点二元超边应为 9 项（饱和响应），不是 11
    tgt9, src9 = _synth_binary_pair()
    r7 = score_prediction(tgt9, src9,
                          {"node_map": {"in_s": "input", "out_s": "response"},
                           "edge_map": {"e_s": "r1"}})
    if r7["n_checks"] != 9:
        failures.append(f"二节点二元超边清单应为 9 项，实际 {r7['n_checks']}")
    if abs(r7["sf"] - 1.0) > 1e-12 or r7["sipr"] != 1:
        failures.append(f"二节点正确映射应 SF=1，实际 SF={r7['sf']} SIPR={r7['sipr']}")

    # 8) 重复占用（非双射）不得被洗成通过：两个源节点映射到同一目标
    #    任务书 L341「不能遗漏或重复占用」。旧实现用 next() 反查会静默取第一个源节点。
    dup = {"node_map": {"N_t": "A_t", "r_s": "A_t", "N_next": "A_next"},
           "edge_map": {"e_s": "e_t"}}
    r8 = score_prediction(tgt, src, dup)
    if r8["n_checks"] != 11:
        failures.append(f"重复占用时清单仍应为 11 项，实际 {r8['n_checks']}")
    if r8["sipr"] != 0:
        failures.append("重复占用不应满分")
    if r8["checks"]["node_bijection"]["passed"]:
        failures.append("重复占用时节点双射必须判失败")
    if r8["checks"]["node_type:A_t"]["passed"]:
        failures.append("被重复占用的目标节点不得判通过")

    # 9) 响应误差公式：任务书 L748 三行数值表逐位复现
    #    (r_s, r_t, E) = (0.20,0.20,0) / (0.44,0.20,0.0576) / (-0.01,0.01,0.0004)
    for rs, rt, want in ((0.20, 0.20, 0.0), (0.44, 0.20, 0.0576),
                         (-0.01, 0.01, 0.0004)):
        got = response_error(rs, rt)
        if abs(got - want) > 1e-9:
            failures.append(f"响应误差 E({rs},{rt}) 应为 {want}，实际 {got}")

    # 10) 方向分类：带容差的三分类（L731）
    if (sgn_eta(0.44, 0.001), sgn_eta(0.20, 0.001)) != (1, 1):
        failures.append("0.44 与 0.20 应同判为增大")
    if sgn_eta(-0.01, 0.001) == sgn_eta(0.01, 0.001):
        failures.append("-0.01 与 0.01 方向应相反")
    if sgn_eta(0.003, 0.01) != 0:
        failures.append("容差 0.01 时 0.003 应判为近似不变")

    # 10b) Rhat 必须是"最大"而不是"平均"（L772）。
    #      用假求值器喂三组误差 0.001 / 0.002 / 0.08：
    #      均值 0.02767、最大 0.08。单点用例区分不了两者（均值=最大），必须多点。
    import types as _types
    src_seq = {0: 0.0316228, 1: 0.0447214, 2: 0.2828427}   # 平方后 ≈ .001/.002/.08
    tgt_f, src_f = {"designated_outputs": ["y"]}, {"designated_outputs": ["y"]}
    fake = _types.ModuleType("runtime")

    def _nr(obj, u):
        return {"y": 0.0 if obj is tgt_f else src_seq[u["i"]]}
    fake.normalized_response = _nr
    _orig_import = evaluate_response.__globals__["_import_runtime"]
    evaluate_response.__globals__["_import_runtime"] = lambda: fake
    try:
        rr = evaluate_response(src_f, tgt_f, [{"i": 0}, {"i": 1}, {"i": 2}])
    finally:
        evaluate_response.__globals__["_import_runtime"] = _orig_import
    if abs(rr["rhat"] - 0.08) > 1e-3:
        failures.append(f"Rhat 应取最大 0.08（均值 0.0277），实际 {rr['rhat']:.6f}")
    if abs(rr["ebar"] - 0.027666) > 1e-3:
        failures.append(f"Ebar 应为均值 0.0277，实际 {rr['ebar']:.6f}")

    # 10c) 没有完成任何干预时，CTC/Ebar 不得算出来，也不得报 ok（L788）
    rr0 = evaluate_response(src_f, tgt_f, [])
    if rr0["ctc"] is not None or rr0["ebar"] is not None:
        failures.append("无干预点时 CTC/Ebar 应为 None（检验未完成），"
                        f"实际 ctc={rr0['ctc']} ebar={rr0['ebar']}")
    if rr0["status"] == "ok":
        failures.append("无干预点不得标记为 ok")

    # 11) CTC/Ebar 在真实 dev 组上：平方反例方向一致但幅度不对
    #     CTC=1（方向全对）、Rhat=0.0576（幅度超容差 0.05）
    #     这正是任务书要说明"只看方向会漏掉平方反例"的依据
    dev = CASES / "multiplicative_growth" / "group_dev_0001"
    if dev.is_dir():
        g = load_group(dev)
        ref = next(iter(g["reference"].values()))
        tgt_d = g["objects"][g["manifest"]["object_ids"][0]]
        sq = g["objects"].get("obj_group_dev_0001_i08")
        pts = [{"v7": 0.2, "v4": 0.0}]
        if sq is not None:
            rr = evaluate_response(sq, tgt_d, pts)
            if abs(rr["rhat"] - 0.0576) > 1e-9:
                failures.append(f"平方反例 Rhat 应为 0.0576，实际 {rr['rhat']}")
            if rr["ctc"] != 1.0:
                failures.append(f"平方反例 CTC 应为 1，实际 {rr['ctc']}")
            rr2 = evaluate_response(g["objects"][ref["valid"][0]["source_id"]],
                                    tgt_d, pts)
            if abs(rr2["ebar"]) > 1e-12:
                failures.append(f"正确源域 Ebar 应为 0，实际 {rr2['ebar']}")

    # 12) 返回行为：VRR / FAR / Coverage 与空分母记 N/A（L1043-1047）
    agg = aggregate([
        dict(task_id="p1", label="positive", has_candidate=True, valid=True,
             sf=1.0, sipr=1, response=None),
        dict(task_id="p2", label="positive", has_candidate=False, valid=False,
             sf=0.0, sipr=0, response=None),
        dict(task_id="n1", label="negative", has_candidate=False, valid=False,
             sf=0.0, sipr=0, response=None),
    ])
    if abs(agg["VRR"] - 0.5) > 1e-12:
        failures.append(f"VRR 应为 0.5（1/2 正任务返回有效），实际 {agg['VRR']}")
    if abs(agg["FAR"] - 0.0) > 1e-12:
        failures.append(f"FAR 应为 0（负任务未返回），实际 {agg['FAR']}")
    if abs(agg["Coverage"] - 1 / 3) > 1e-12:
        failures.append(f"Coverage 应为 1/3，实际 {agg['Coverage']}")
    # 正任务返回错误映射只降 VRR，不计入 FAR
    agg2 = aggregate([dict(task_id="p1", label="positive", has_candidate=True,
                           valid=False, sf=0.5, sipr=0, response=None),
                      dict(task_id="n1", label="negative", has_candidate=True,
                           valid=False, sf=0.0, sipr=0, response=None)])
    if agg2["VRR"] != 0.0 or agg2["FAR"] != 1.0:
        failures.append(f"VRR/FAR 应为 0/1，实际 {agg2['VRR']}/{agg2['FAR']}")
    # 分母为空记 None，不写 0
    agg3 = aggregate([dict(task_id="p1", label="positive", has_candidate=True,
                           valid=True, sf=1.0, sipr=1, response=None)])
    if agg3["FAR"] is not None:
        failures.append("无负任务时 FAR 应为 N/A(None)，不应写 0")
    if agg3["CTC"] is not None:
        failures.append("无响应任务时 CTC 应为 N/A(None)，不应写 0")

    if failures:
        print("SELFTEST FAILED")
        for f in failures:
            print("  -", f)
        return 1
    print("SELFTEST PASSED  (12 组断言：11/9 项清单、正确映射 SF=1、角色交换 9/11、"
          "缺/空/重复映射均不满分、响应误差三行表、CTC/Ebar 平方反例、"
          "VRR/FAR/Coverage 与空分母记 N/A)")
    return 0


# --------------------------------------------------------------------------
# 跑整个数据集
# --------------------------------------------------------------------------

def iter_groups(dataset: str | None = None):
    """遍历 cases/ 下的组目录。dataset=None 表示全部（含 dev 组）。"""
    for rel_dir in sorted(p for p in CASES.iterdir() if p.is_dir()):
        for g in sorted(p for p in rel_dir.iterdir() if p.is_dir()):
            manifest = g / "manifest.json"
            if not manifest.is_file():
                continue
            m = json.loads(manifest.read_text(encoding="utf-8"))
            if dataset and m.get("dataset") != dataset:
                continue
            yield m.get("relation_type"), g


def evaluate_self(group: dict[str, Any]) -> dict[str, Any]:
    """用封存参考里的正确映射当作预测，验证评价器链路（自评价）。

    这不是方法成绩，只是端到端连通性检查：正确映射应得 SF=1、SIPR=1。
    负任务（valid 为空）跳过——它的正确行为是"拒绝"，属 E02 返回行为，不属 E01。
    """
    results = []
    for task_id, ref in group["reference"].items():
        label = ref.get("label")
        truth = (ref.get("valid") or [None])[0]
        tgt_id = group["manifest"].get("object_ids", [None])[0]
        tgt = group["objects"].get(tgt_id)

        # 负任务（valid 为空）：正确行为是"拒绝"，不进 E01 结构评分，
        # 但**必须进返回行为统计**（FAR 的分母是负任务，L1043）。
        if label == "negative" or not truth:
            results.append({
                "task_id": task_id, "label": label or "negative",
                "has_candidate": False, "sf": 0.0, "sipr": 0,
                "n_checks": 0, "n_passed": 0, "checks": {},
                "error_breakdown": {"type_error": 0, "endpoint_error": 0,
                                    "role_error": 0},
                "response": None,
            })
            continue

        src = group["objects"].get(truth["source_id"])
        if src is None or tgt is None:
            continue
        pred = {"node_map": truth["node_map"], "edge_map": truth["edge_map"]}
        # ---- 结构模式（SCAR/SCAN）必须走 pair_map ----
        # 只传 node_map 会掉进机械模式：node_node_map 是 dict，装不下多值对应，
        # 且双射/两端同类型这两类检查在跨范畴类比上必然误伤正确答案。
        # 实测（2026-11-02）：不传 pair_map 时 SCAR 291/378、SCAN 57/65 的正确映射
        # 都拿不到满分 —— 是**调用方式**的缺陷，不是数据或判据的问题。
        kwargs = {}
        if ref.get("pair_map") is not None:
            pred["pair_map"] = ref["pair_map"]
            # ref_roles **必须**直接取参考侧的值，空 dict 就传 None（不启用该项）。
            # 曾经写成 `ref.get("ref_roles") or {读候选的角色}` —— 空 dict 是假值，
            # 于是回退到从候选对象读角色，等于拿候选给自己打分：
            # SCAN 的 ref_roles 全为空，65 组因此凭空多出第 3 项 role_consistency
            # （文档与参考标注都写 2 项）。与 type_pattern 的自比 bug 同一类错误。
            ref_roles = ref.get("ref_roles")
            kwargs = dict(ref_pairs=ref["pair_map"],
                          ref_type_pattern=ref.get("ref_type_pattern"),
                          ref_roles=(ref_roles if ref_roles else None))
        res = score_prediction(tgt, src, pred, **kwargs)
        res["task_id"] = task_id
        res["label"] = label
        # 用封存正确映射当预测 ⇒ 视为"已返回且有效"，
        # 由此 VRR/Coverage 在自评价下应为 1（链路连通性检查）
        res["valid"] = bool(res["sipr"] == 1)

        # ---- 响应指标：只在有封存干预点的任务上算（L1024/L1039）----
        res["response"] = None
        pts_file = group["group_dir"] / "sealed/intervention_points.json"
        if pts_file.is_file() and src.get("function") and tgt.get("function"):
            pts = json.loads(pts_file.read_text(encoding="utf-8")).get("tasks", {})
            if task_id in pts:
                try:
                    res["response"] = evaluate_response(src, tgt, pts[task_id])
                except ValueError as e:          # 干预越界/合法域冲突：记未完成
                    res["response"] = {"ctc": None, "ebar": None, "rhat": None,
                                       "n_points": 0, "status": f"求值失败: {e}"}
        results.append(res)
    return {"group_id": group["group_id"], "tasks": results}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="独立结构评价器（E01 SF/SIPR）")
    ap.add_argument("--selftest", action="store_true", help="跑任务书已知答案自检")
    ap.add_argument("--dataset", default=None, help="只跑某数据集（如 mred）")
    ap.add_argument("--json-out", default=None, help="逐任务结果写到此路径")
    ap.add_argument("--csv-out", default=None,
                    help="逐任务结果写为 CSV（任务书 T06 约定的 metrics_per_task.csv）")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    all_tasks: list[dict[str, Any]] = []
    n_groups = 0
    bad_groups: list[str] = []
    for rel, gdir in iter_groups(args.dataset):
        grp = load_group(gdir)
        if not grp["reference"]:
            continue
        n_groups += 1
        out = evaluate_self(grp)
        for t in out["tasks"]:
            t["group_id"] = grp["group_id"]
            all_tasks.append(t)
        # 正任务的正确映射必须满分，否则是评价器或数据有问题。
        # 负任务跳过 —— 它的正确行为是"拒绝"，SF/SIPR 本就不适用（L1034）。
        for t in out["tasks"]:
            if t.get("label") == "positive" and (
                    abs(t["sf"] - 1.0) > 1e-12 or t["sipr"] != 1):
                bad_groups.append(f"{grp['group_id']}/{t['task_id']} SF={t['sf']:.4f}")

    agg = aggregate(all_tasks)
    print(f"组数: {n_groups}   任务数: {agg['n_tasks']}"
          f"（正 {agg['n_pos']} / 负 {agg['n_neg']}）")
    print(f"自评价（用封存正确映射当预测）: SF={agg['SF']:.6f}  SIPR={agg['SIPR']:.6f}")
    # 响应与返回指标（L1039-1047）：任何分母为空记 N/A，不写 0
    def _f(v):
        return "N/A" if v is None else f"{v:.6f}"
    print(f"  返回行为: VRR={_f(agg['VRR'])}  FAR={_f(agg['FAR'])}  "
          f"Coverage={_f(agg['Coverage'])}")
    print(f"  响应指标: CTC={_f(agg['CTC'])}  Ebar={_f(agg['Ebar'])}  "
          f"Rhat={_f(agg['Rhat'])}  （有响应的任务 {agg['n_response_tasks']}）")
    if bad_groups:
        print(f"\n未满分任务 {len(bad_groups)} 个（前 10）:")
        for b in bad_groups[:10]:
            print("  -", b)
    else:
        print("全部正任务 SF=1 / SIPR=1 —— 评价器链路与数据一致")

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(all_tasks, ensure_ascii=False, indent=1), encoding="utf-8")
        print("逐任务结果 ->", args.json_out)

    # T06 交付约定：metrics_per_task.csv（逐任务一行，供汇总与复核）
    if args.csv_out:
        import csv as _csv
        cols = ["group_id", "task_id", "label", "mode", "has_candidate", "valid",
                "sf", "sipr", "n_checks", "n_passed",
                "type_error", "endpoint_error", "role_error",
                "n_points", "CTC", "Ebar", "Rhat"]
        with open(args.csv_out, "w", encoding="utf-8-sig", newline="") as f:
            w = _csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for t in all_tasks:
                eb = t.get("error_breakdown") or {}
                rp = t.get("response") or {}
                w.writerow(dict(
                    group_id=t["group_id"], task_id=t["task_id"],
                    label=t.get("label", "positive"),
                    mode=t.get("mode", "mechanistic"),
                    has_candidate=int(bool(t.get("has_candidate"))),
                    valid=int(bool(t.get("valid"))),
                    sf=f"{t['sf']:.6f}", sipr=t["sipr"],
                    n_checks=t["n_checks"], n_passed=t["n_passed"],
                    type_error=eb.get("type_error", 0),
                    endpoint_error=eb.get("endpoint_error", 0),
                    role_error=eb.get("role_error", 0),
                    # 响应指标为空表示"该任务没有留出干预点/无函数"，
                    # 写成空串而不是 0（0 会被读成"误差极小"）
                    n_points=rp.get("n_points", ""),
                    CTC="" if rp.get("ctc") is None else f"{rp['ctc']:.6f}",
                    Ebar="" if rp.get("ebar") is None else f"{rp['ebar']:.6f}",
                    Rhat="" if rp.get("rhat") is None else f"{rp['rhat']:.6f}"))
        print("逐任务 CSV ->", args.csv_out)
    return 0 if not bad_groups else 2


if __name__ == "__main__":
    sys.exit(main())
