"""Print the three T01 files as a plain-language summary (no raw JSON to read)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def main():
    schema = load("T01-schema.json")
    vocab = load("T01-vocabulary.json")
    ex = load("T01-examples.json")

    print("=" * 64)
    print("T01 统一格式 · 白话摘要（draft-v2）")
    print("=" * 64)

    recs = schema["records"]
    print("\n【schema：%d 类记录，各自管什么】" % len(recs))
    for name in ["object", "vocab", "task", "adaptation", "reference",
                 "candidate", "audit", "prediction"]:
        print("  %-11s %s" % (name, recs[name]["desc"].split("。")[0]))

    print("\n  object（知识对象，方法输入，不含答案）关键字段：")
    for f in ["nodes", "edges", "function", "controllable_inputs",
              "designated_outputs", "baseline", "input_scales", "baseline_output", "output_scale", "legal_domain"]:
        print("    · %-20s %s" % (f, recs["object"]["fields"][f]["desc"]))

    print("\n  答案隔离：原始映射/解释/背景只放 adaptation，标签/见证点只放 reference；task_id 不编码正负。")

    print("\n【vocabulary：类型和角色能填哪些词】")
    print("  方向：%s ｜ %s" % (vocab["direction"]["-"], vocab["direction"]["+"]))
    for t in vocab["node_types"]:
        print("    · %s（%s）%s" % (t["type_id"], t["label"], t["status"]))
    for e in vocab["edge_types"]:
        roles = "、".join("%s(%s)" % (r["role_id"], r["direction"]) for r in e["roles"])
        print("    · %s（%s）%s：%s" % (e["edge_type_id"], e["label"], e["status"], roles))

    print("\n【examples：填好的样例】")
    print("  对象 %d 个：" % len(ex["objects"]))
    for o in ex["objects"]:
        print("    · %-26s %-12s %-10s 节点%d 边%d" % (
            o["object_id"], o["object_kind"], o["label"], len(o["nodes"]), len(o["edges"])))
    print("  适配材料 %d 份（封存：原始映射/解释/背景）：" % len(ex["adaptations"]))
    for a in ex["adaptations"]:
        print("    · %-24s %s → %s，%d 对映射，状态 %s" % (
            a["adaptation_id"], a["source_object_id"], a["target_object_id"],
            len(a["faithful_mappings"]), a["annotation_status"]))
    t = ex["task"]
    print("  任务：%s —— 目标=%s，候选源%d个（无标签）" % (t["task_id"], t["target_id"], len(t["source_ids"])))
    r = ex["reference"]
    print("  正任务答案：label=%s，valid %d 个有效源：" % (r["label"], len(r["valid"])))
    for v in r["valid"]:
        print("      · %s node_map=%s" % (v["source_id"], v["node_map"]))
    n = ex["negative_reference_example"]
    print("  负任务示例：label=%s，exclusions %d 条，见证误差=%s" % (
        n["label"], len(n["exclusions"]), n["exclusions"][0]["witness"]["error"]))

    print("\n  待你拍板：线性驱动-阻力、饱和响应两类的方程和角色名（见 验收清单.md）。")
    print("=" * 64)


if __name__ == "__main__":
    main()
