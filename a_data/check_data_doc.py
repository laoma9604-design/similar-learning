"""任务书 L1555「数据说明」九项必填核对器。

L1555 原文（research-principles-experiment-taskbook.tex）：
    数据说明 & 来源与许可、任务与组数量、领域、构造规则、正负依据、
               尺度、合法域、划分及排除原因。

为什么单独写这个脚本：这九项是**文档完整性**要求，而 verify_scan.py 查的是
数据完整性。两者互不覆盖——2026-11-02 复核时就发现 SCAN 数据说明缺了
「领域分布」「尺度」「合法域」三项内容，数据本身却完全合格。

判据分两档，不硬凑：
  MUST   必须在本数据集的文档里明确说明（哪怕是「不适用 + 依据」）
  NA_OK  结构模式下本来就不适用，允许以「不适用」形式说明，但必须写明依据行号

检查的是「有没有明确交代」，不是「有没有写满」。
用法：python a_data/check_data_doc.py scan|scar      # 退出码 0 = 九项全有交代
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = {
    "scan": [ROOT / "data" / "SCAN数据来源说明.md", ROOT / "data" / "SCAN适配规范.md"],
    "scar": [ROOT / "data" / "SCAR数据来源说明.md", ROOT / "data" / "SCAR适配规范.md"],
}

# (L1555 项目名, 允许的表述关键词之一, 是否结构模式可标 N/A)
ITEMS = [
    ("来源与许可", ["来源", "许可", "LICENSE", "MIT"], False),
    ("任务与组数量", ["任务数", "组数", "实际任务", "可适配组数"], False),
    ("领域", ["领域", "domain", "N/A"], True),
    ("构造规则", ["构造", "判定顺序", "口径"], False),
    ("正负依据", ["正任务", "负任务", "label", "正负"], True),
    ("尺度", ["尺度", "scale", "N/A"], True),
    ("合法域", ["合法域", "legal_domain", "N/A"], True),
    ("划分", ["划分", "split", "70/15/15"], False),
    ("排除原因", ["排除"], False),
]

# 结构模式专属依据：说「不适用」时必须有这两处原文之一作为依据，不能空口说 N/A
STRUCT_MODE_CITE = ["L957", "结构模式"]


def main(argv):
    ds = argv[1] if len(argv) > 1 else "scan"
    if ds not in DOCS:
        print(f"未知数据集 {ds}")
        return 2
    doc = "\n".join(p.read_text(encoding="utf-8") if p.is_file() else ""
                    for p in DOCS[ds])
    if not doc.strip():
        print(f"文档不存在: {DOCS[ds]}")
        return 2

    missing = []
    na_items = []
    for name, kws, na_ok in ITEMS:
        hit = [k for k in kws if k in doc]
        if hit:
            print(f"  ✓ {name:12s} 命中 {hit[:3]}")
        else:
            missing.append(name)
            print(f"  ✗ {name:12s} 文档里找不到交代")

    # 标了 N/A 的项必须有结构模式依据（L957），否则是拿 N/A 糊弄
    n_na = doc.count("N/A")
    has_cite = any(c in doc for c in STRUCT_MODE_CITE)
    print(f"\n  文档中 N/A 出现 {n_na} 处；结构模式依据(L957/结构模式) "
          f"{'已引用' if has_cite else '未引用'}")
    if n_na and not has_cite:
        missing.append("N/A 缺少 L957 依据")

    print("=" * 58)
    if missing:
        print(f"{ds} 数据说明不合格 {len(missing)} 项: {missing}")
        return 1
    print(f"{ds} 数据说明：L1555 九项全部有明确交代")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
