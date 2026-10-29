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
        "objects": objects,
        "reference": reference,
        "manifest": json.loads((group_dir / "manifest.json").read_text(encoding="utf-8"))
        if (group_dir / "manifest.json").is_file()
        else {},
    }


# --------------------------------------------------------------------------
# 检查清单（11 项对应的通用构造）
# --------------------------------------------------------------------------

def build_checks(target: dict[str, Any], src: dict[str, Any],
                 node_map: dict[str, str], edge_map: dict[str, str]) -> dict[str, dict[str, Any]]:
    """按参考结构构造完整检查清单，逐项判定候选映射是否通过。

    返回 {check_key: {"kind": ..., "passed": bool, "detail": ...}}
    清单由**目标域完整参考结构**确定（任务书 L1034"清单由完整参考结构确定，
    未匹配项记失败"），所以先遍历 target，再看候选有没有给出对应匹配。
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
    for nid in sorted(tnodes):
        t_type = tnodes[nid].get("type")
        # 反查：哪个源节点映射到了这个目标节点
        src_nid = next((s for s, t in node_map.items() if t == nid), None)
        if src_nid is None or src_nid not in snodes:
            checks[f"node_type:{nid}"] = {
                "kind": "type_error", "passed": False,
                "detail": f"目标节点 {nid} 无源节点映射",
            }
            continue
        s_type = snodes[src_nid].get("type")
        checks[f"node_type:{nid}"] = {
            "kind": "type_error", "passed": s_type == t_type,
            "detail": f"{src_nid}({s_type}) -> {nid}({t_type})",
        }

    # ---- 逐超边：类型 / 输入集合 / 输出集合 ----
    for tid in sorted(tedges):
        te = tedges[tid]
        src_eid = next((s for s, t in edge_map.items() if t == tid), None)
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
            s_nid = next((s for s, t in node_map.items() if t == t_nid), None)
            if s_nid is None or se is None:
                checks[f"role:{t_nid}@{tid}"] = {
                    "kind": "role_error", "passed": False,
                    "detail": f"目标节点 {t_nid} 无源节点映射到本关系",
                }
                continue
            s_role = (se.get("roles") or {}).get(s_nid)
            t_role = (te.get("roles") or {}).get(t_nid)
            checks[f"role:{t_nid}@{tid}"] = {
                "kind": "role_error", "passed": s_role == t_role and s_role is not None,
                "detail": f"{s_nid}({s_role}) -> {t_nid}({t_role})",
            }

    return checks


# --------------------------------------------------------------------------
# 任务评分
# --------------------------------------------------------------------------

def score_prediction(target: dict[str, Any], src: dict[str, Any],
                     prediction: dict[str, Any] | None) -> dict[str, Any]:
    """对单个任务的候选映射打分。prediction=None 表示方法无候选（两项记零）。"""
    if prediction is None:
        return {
            "has_candidate": False, "sf": 0.0, "sipr": 0,
            "n_checks": 0, "n_passed": 0, "checks": {},
            "error_breakdown": {"type_error": 0, "endpoint_error": 0, "role_error": 0},
        }

    checks = build_checks(target, src,
                          prediction["node_map"], prediction["edge_map"])
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


def aggregate(per_task: list[dict[str, Any]]) -> dict[str, Any]:
    """SF 是检查项通过比例的任务平均；SIPR 是全部检查同时通过的任务比例（L1034）。

    无候选任务两项记零（L1034 原文），因此分母是全部任务数 N。
    """
    n = len(per_task)
    if n == 0:
        return {"n_tasks": 0, "SF": None, "SIPR": None}
    return {
        "n_tasks": n,
        "SF": sum(t["sf"] for t in per_task) / n,
        "SIPR": sum(t["sipr"] for t in per_task) / n,
        "no_candidate": sum(0 if t["has_candidate"] else 1 for t in per_task),
    }


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

    if failures:
        print("SELFTEST FAILED")
        for f in failures:
            print("  -", f)
        return 1
    print("SELFTEST PASSED  (11 项清单 / 正确映射 SF=1 SIPR=1 / 角色交换 SF=9/11 SIPR=0)")
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
        if ref.get("label") != "positive":
            continue
        if not ref.get("valid"):
            continue
        truth = ref["valid"][0]
        src = group["objects"].get(truth["source_id"])
        tgt_ids = set()
        # 目标域对象：manifest 里第一个对象 id 约定为 tgt
        tgt_id = group["manifest"].get("object_ids", [None])[0]
        tgt = group["objects"].get(tgt_id)
        if src is None or tgt is None:
            continue
        pred = {"node_map": truth["node_map"], "edge_map": truth["edge_map"]}
        res = score_prediction(tgt, src, pred)
        res["task_id"] = task_id
        results.append(res)
    return {"group_id": group["group_id"], "tasks": results}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="独立结构评价器（E01 SF/SIPR）")
    ap.add_argument("--selftest", action="store_true", help="跑任务书已知答案自检")
    ap.add_argument("--dataset", default=None, help="只跑某数据集（如 mred）")
    ap.add_argument("--json-out", default=None, help="逐任务结果写到此路径")
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
        # 正确映射必须满分，否则是评价器或数据有问题
        for t in out["tasks"]:
            if abs(t["sf"] - 1.0) > 1e-12 or t["sipr"] != 1:
                bad_groups.append(f"{grp['group_id']}/{t['task_id']} SF={t['sf']:.4f}")

    agg = aggregate(all_tasks)
    print(f"组数: {n_groups}   正任务数: {agg['n_tasks']}")
    print(f"自评价（用封存正确映射当预测）: SF={agg['SF']:.6f}  SIPR={agg['SIPR']:.6f}")
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
    return 0 if not bad_groups else 2


if __name__ == "__main__":
    sys.exit(main())
