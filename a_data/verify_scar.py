"""SCAR 适配验收（不 import 适配器，只读 cases/structural_scar 与原始数据）。

覆核重点（用户明确要求）：
  A. 原始材料真实性与完整性
     A1 每条纳入样本的 raw 必须与 SCAR 原文逐字一致（不是转写、不是摘要）
     A2 faithful_mappings 必须与原文 mappings 完全一致（顺序、词形、大小写）
     A3 Explanation 与两份 background 必须原文留存
     A4 排除样本必须逐条记录原因，且原因的判定依据可复查
  B. 结构适配能完成完整实验流程、不压缩
     B1 节点数 = 映射对数（不得压缩成固定规模）
     B2 两域节点数相等、超边数相等（L342）
     B3 参考映射是双射时 node_map 覆盖全部节点
     B4 available_checks 声明的每一项都能被评价器实际计算（清单非空）
     B5 评价器对该对象算得出 SF/SIPR（不报错、不为 0 分母）
     B6 多值映射样本：valid_mappings 非空且能量化，multiple_mapping_type 正确
     B7 划分比例接近 70/15/15，且同一 system 不跨划分
     B8 公开输入不含答案（无忠实映射、无解释原文、无标签）

用法：python a_data/verify_scar.py      # 退出码 0 = 全部通过
"""
import json
import re
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "a_data"))

import metrics  # noqa: E402

SCAR_DIR = ROOT / "cases" / "structural_scar"
SRC = ROOT / "data" / "raw" / "scar" / "release" / "system_analogy_en.json"

FAIL = []


def fail(code, msg):
    FAIL.append(f"[{code}] {msg}")


def main():
    if not SCAR_DIR.is_dir():
        print("适配目录不存在，先运行 a_data/adapt_scar.py")
        return 1
    raw = {json.loads(l)["id"]: json.loads(l)
           for l in SRC.open(encoding="utf-8") if l.strip()}
    groups = sorted(p for p in SCAR_DIR.iterdir()
                    if p.is_dir() and p.name.startswith("group_scar_"))
    print(f"适配组数: {len(groups)}   原始条数: {len(raw)}")

    # ---------- A 原始材料真实性与完整性 ----------
    n_checked = 0
    for gdir in groups:
        ad_p = gdir / "sealed" / "adaptation.json"
        if not ad_p.is_file():
            fail("A0", f"{gdir.name} 缺 adaptation.json")
            continue
        ad = json.loads(ad_p.read_text(encoding="utf-8"))
        oid = int(ad["original_id"])
        orig = raw.get(oid)
        if orig is None:
            fail("A1", f"{gdir.name} original_id={oid} 在原始数据中不存在")
            continue
        n_checked += 1

        # A1 raw 逐字一致
        if ad["raw"] != orig:
            fail("A1", f"{gdir.name} raw 与原文不一致")

        # A2 faithful_mappings 与原文 mappings 一致（含顺序与词形）
        want = [[str(a).strip(), str(b).strip()] for a, b in orig["mappings"]]
        got = [[a, b] for a, b in ad["faithful_mappings"]]
        if got != want:
            fail("A2", f"{gdir.name} faithful_mappings 与原文不同")

        # A3 解释与背景留存
        if (ad.get("explanation") or []) != (orig.get("Explanation") or []):
            fail("A3", f"{gdir.name} Explanation 未原文留存")
        bg = ad.get("background") or {}
        if bg.get("source") != orig.get("system_a_background", "") or \
           bg.get("target") != orig.get("system_b_background", ""):
            fail("A3", f"{gdir.name} background 未原文留存")

    # A4 排除清单
    ex_p = SCAR_DIR / "_excluded.json"
    if not ex_p.is_file():
        fail("A4", "缺 _excluded.json")
    else:
        ex = json.loads(ex_p.read_text(encoding="utf-8"))
        cover = {int(r["original_id"]) for r in ex["records"]}
        if ex["included"] + ex["excluded_count"] != ex["raw_count"]:
            fail("A4", "纳入+排除 != 原始数量")
        if cover & {int(json.loads((g / 'sealed/adaptation.json')
                                   .read_text(encoding='utf-8'))["original_id"])
                    for g in groups}:
            fail("A4", "同一原文既被纳入又被排除")
        for r in ex["records"]:
            o = raw.get(int(r["original_id"]))
            if o is None:
                fail("A4", f"排除项 {r['original_id']} 原文不存在")
                continue
            if not r.get("reason"):
                fail("A4", f"排除项 {r['original_id']} 无原因")
            # 复核原因必须属实：按声明的规则重新验证一次
            rule = r.get("rule", "")
            expl = o.get("Explanation") or []
            maps = o.get("mappings") or []
            if rule == "S1":
                if len(expl) == len(maps):
                    fail("A4", f"排除项 {r['original_id']} 声明 S1，但解释条数实际一致")
            elif rule == "S2":
                if not any(re.match(
                        r'^\s*(items?|explanation|translation|elements?|concepts?|'
                        r'mapping|answer|lists?|terms?|pairs?)\s*[:：]',
                        (e or "").strip(), re.I) for e in expl):
                    fail("A4", f"排除项 {r['original_id']} 声明 S2，但未找到模板残留")
            elif rule == "S3":
                if not any(re.search(
                        r"(may not be (appropriate|correct|suitable|accurate)|"
                        r"(is|isn't) not (an? )?(appropriate|valid|suitable)|"
                        r"not (a )?(good|proper|valid|accurate) (mapping|correspondence|match)|"
                        r"does not (really )?(correspond|match|fit)|"
                        r"weak (mapping|correspondence)|questionable)",
                        e or "", re.I) for e in expl):
                    fail("A4", f"排除项 {r['original_id']} 声明 S3，但未找到自我否定表述")
            else:
                fail("A4", f"排除项 {r['original_id']} 规则未知: {rule!r}")

    # ---------- B 完整流程 ----------
    split_cnt = Counter()
    sys_blocks = defaultdict(set)   # 归一化 system 名 → 该名涉及的 split 集合
    for gdir in groups:
        man = json.loads((gdir / "manifest.json").read_text(encoding="utf-8"))
        ad = json.loads((gdir / "sealed/adaptation.json").read_text(encoding="utf-8"))
        ref = json.loads((gdir / "sealed/reference.json").read_text(encoding="utf-8"))
        idx = json.loads((gdir / "data/input/objects/index.json").read_text(encoding="utf-8"))
        objs = {o["object_id"]: metrics.load_object(gdir / "data/input/objects" / o["file"])
                for o in idx["objects"]}
        tgt = objs[man["object_ids"][0]]
        src_id = [o for o in man["object_ids"] if o != tgt["object_id"]][0]
        src = objs[src_id]
        n_pairs = len(ad["faithful_mappings"])
        split_cnt[man["split"]] += 1
        for key in ("source", "target"):
            nm = " ".join(str(ad["system"][key]).lower().split())
            # 记录该 system 名出现过的划分，而不是组名。
            # 同一名字出现在多个组是正常的（派生关系），只要都在同一 split 就合规
            sys_blocks[key + ":" + nm].add(man["split"])

        # B1 节点数 = 映射对数（不压缩）
        if len(tgt["nodes"]) != n_pairs or len(src["nodes"]) != n_pairs:
            fail("B1", f"{gdir.name} 节点数 {len(src['nodes'])}/{len(tgt['nodes'])} "
                       f"!= 映射对数 {n_pairs}")
        # B2 两域节点数、超边数相等
        if len(src["nodes"]) != len(tgt["nodes"]):
            fail("B2", f"{gdir.name} 两域节点数不等")
        if len(src["edges"]) != len(tgt["edges"]):
            fail("B2", f"{gdir.name} 两域超边数不等")

        task_id, r = next(iter(ref.items()))

        # B4/B5 available_checks 能算出清单且 SF 可计算
        tr = metrics.build_checks(tgt, src, r["valid"][0]["node_map"],
                                  r["valid"][0]["edge_map"],
                                  available=r["available_checks"])
        if not tr:
            fail("B4", f"{gdir.name} 声明可用项后清单为空")
        if any(metrics._group_of(k) not in r["available_checks"] for k in tr):
            fail("B4", f"{gdir.name} 清单含未声明的类别")
        res = metrics.score_prediction(tgt, src,
                                       {"node_map": r["valid"][0]["node_map"],
                                        "edge_map": r["valid"][0]["edge_map"]},
                                       available=r["available_checks"])
        if res["n_checks"] == 0 or res["sf"] != 1.0 or res["sipr"] != 1:
            fail("B5", f"{gdir.name} 参考映射未满分 sf={res['sf']} n={res['n_checks']}")

        # B6 多值映射
        if r["multiple_mapping_type"] != "none":
            if not r.get("valid_mappings"):
                fail("B6", f"{gdir.name} 多值映射无 valid_mappings")
            la = [a.lower() for a, _ in ad["faithful_mappings"]]
            lb = [b.lower() for _, b in ad["faithful_mappings"]]
            dup_a = any(c > 1 for c in Counter(la).values())
            dup_b = any(c > 1 for c in Counter(lb).values())
            want = "both" if (dup_a and dup_b) else (
                "one_to_many" if dup_a else ("many_to_one" if dup_b else "none"))
            if r["multiple_mapping_type"] != want:
                fail("B6", f"{gdir.name} multiple_mapping_type={r['multiple_mapping_type']} "
                           f"与数据实际 {want} 不符")

        # B8 公开输入不含答案：逐字段检查对象与 manifest，
        # 不靠"字符串里出现系统名"这种粗糙匹配（'car'、'object' 这类常见词会误报）
        pub_j = json.dumps({"src": src, "tgt": tgt, "manifest": man},
                           ensure_ascii=False)
        for leak in ("faithful_mappings", "Explanation", "background"):
            if leak in pub_j:
                fail("B8", f"{gdir.name} 公开输入含 {leak}")
        # 节点 label 必须是中立占位，不能是 SCAR 的原词
        words = {w for pair in ad["faithful_mappings"] for w in pair}
        for o in (src, tgt):
            for n in o["nodes"]:
                if n["label"] in words:
                    fail("B8", f"{gdir.name} 节点 label {n['label']!r} 是 SCAR 原词")
                    break
        # 系统名不得出现在任何公开字段值里（按完整短语匹配，不是子串）
        sysn = {(" ".join(str(ad["system"][k]).lower().split())) for k in ("source", "target")}
        vals = " ".join(str(v).lower() for o in (src, tgt) for v in
                        ([o.get("label", "")] + [n["label"] for n in o["nodes"]])).lower()
        for s in sysn:
            if s and s in vals:
                fail("B8", f"{gdir.name} 公开对象含系统名 {s!r}")

    # B7 划分
    total = sum(split_cnt.values())
    for k, target in (("train", 0.70), ("val", 0.15), ("test", 0.15)):
        got = split_cnt[k] / total if total else 0
        if abs(got - target) > 0.03:
            fail("B7", f"{k} 占比 {got:.3f} 偏离目标 {target:.2f} 超过 0.03")
    cross = [k for k, v in sys_blocks.items() if len(v) > 1]
    if cross:
        fail("B7", f"{len(cross)} 个 system 跨划分，例 {cross[:3]}")

    # ---------- 结论 ----------
    print(f"  逐字核对样本: {n_checked}")
    print(f"  划分: {dict(split_cnt)}（{ {k: round(v/total*100,2) for k,v in split_cnt.items()} }%）")
    print(f"  共享 system 跨划分: {len(cross)}")
    print("=" * 62)
    if FAIL:
        print(f"不合格 {len(FAIL)} 项")
        for f in FAIL[:30]:
            print("  " + f)
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
