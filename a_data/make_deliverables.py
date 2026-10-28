"""生成 A 侧交付清单：data/splits.csv（分组清单）+ data/reference_all.jsonl（参考标注汇总）。

任务书依据：
- L1109 T02 交付「数据说明、对象文件、分组清单；独立参考标注另存」
- L1530 A 提交「数据生成与适配代码、独立参考标注、划分清单」
- L1197 独立参考标注单独存放，只供评价器读取

只读 cases/，不改任何正式数据。
"""
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "cases"
DATA = ROOT / "data"
RELS = ["multiplicative_growth", "linear_drive_resistance", "saturation_response"]


def formal_groups():
    """只取正式组；dev 组按任务书 L991 不纳入正式测试，不进清单。"""
    out = []
    for rel in RELS:
        d = CASES / rel
        if not d.is_dir():
            continue
        for g in sorted(d.glob("group_tr_*")):
            out.append((rel, g))
    return out


def main():
    groups = formal_groups()
    print(f"正式组: {len(groups)}")

    # ---------------- 1) splits.csv 分组清单 ----------------
    split_rows = []
    for rel, g in groups:
        m = json.loads((g / "manifest.json").read_text(encoding="utf-8"))
        ms = json.loads((g / "manifest.sealed.json").read_text(encoding="utf-8"))
        split_rows.append(dict(
            group_id=m["group_id"],
            split=m["split"],
            relation_type=m["relation_type"],
            pair_id=m["pair_id"],
            variant_index=m["variant_index"],
            object_count=len(m["object_ids"]),
            positive_task=m["task_ids"][0],
            negative_task=m["task_ids"][1],
            valid_source=ms["valid_sources"][0],
            excluded_source_count=len(ms["excluded_sources"]),
            has_intervention_points="yes" if (g / "sealed/intervention_points.json").exists() else "no",
        ))

    split_path = DATA / "splits.csv"
    with split_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(split_rows[0]))
        w.writeheader()
        w.writerows(split_rows)
    print(f"  写入 {split_path}")

    cnt = Counter(r["split"] for r in split_rows)
    print(f"  划分: {dict(cnt)}")

    # ---------------- 2) reference_all.jsonl 参考标注汇总 ----------------
    # 每条一行，只含封存内容，供评价器流式读取，无需翻 300 个文件
    ref_path = DATA / "reference_all.jsonl"
    n = 0
    with ref_path.open("w", encoding="utf-8", newline="\n") as f:
        for rel, g in groups:
            m = json.loads((g / "manifest.json").read_text(encoding="utf-8"))
            ref = json.loads((g / "sealed/reference.json").read_text(encoding="utf-8"))
            for task_id, rec in ref.items():
                row = dict(
                    group_id=m["group_id"],
                    split=m["split"],
                    relation_type=m["relation_type"],
                    pair_id=m["pair_id"],
                    task_id=task_id,
                    label=rec["label"],
                    valid=rec["valid"],
                    exclusions=rec["exclusions"],
                    reference_tolerance=rec["reference_tolerance"],
                    status=rec["status"],
                    positive_max_deviation=rec.get("positive_max_deviation"),
                    full_library_verified=rec.get("full_library_verified"),
                    reference_file=str((g / "sealed/reference.json").relative_to(ROOT)).replace("\\", "/"),
                )
                f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
                n += 1
    print(f"  写入 {ref_path}（{n} 条任务级参考标注）")

    # ---------------- 3) 自检 ----------------
    print("\n=== 自检 ===")
    ok = True
    if len(split_rows) != 300:
        print(f"  FAIL splits.csv 行数 {len(split_rows)} != 300")
        ok = False
    if cnt != Counter(dict(train=210, val=45, test=45)):
        print(f"  FAIL 划分 {dict(cnt)}")
        ok = False
    if n != 600:
        print(f"  FAIL reference_all.jsonl {n} 条 != 600")
        ok = False

    labels = Counter()
    with ref_path.open(encoding="utf-8") as f:
        for line in f:
            labels[json.loads(line)["label"]] += 1
    if labels != Counter(dict(positive=300, negative=300)):
        print(f"  FAIL 正负计数 {dict(labels)}")
        ok = False
    print(f"  正负任务: {dict(labels)}")

    # 负任务必须全库核验
    bad = []
    with ref_path.open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["label"] == "negative":
                if not r["full_library_verified"] or len(r["exclusions"]) != 10 or r["valid"]:
                    bad.append(r["task_id"])
    if bad:
        print(f"  FAIL 负任务全库核验不完整: {bad[:3]}")
        ok = False
    print(f"  负任务全库核验: {'全部通过' if not bad else '有问题'}")

    print("\n" + ("完成。" if ok else "有问题，见上。"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
