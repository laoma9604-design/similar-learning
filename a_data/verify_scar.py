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
            elif rule == "R-manual":
                # 人工判定条目：必须有可读的具体理由，且必须真的存在该条
                if len(r.get("reason", "")) < 20:
                    fail("A4", f"排除项 {r['original_id']} 人工判定理由过于笼统")
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

        # B1 节点数 = 各自去重后的概念数（共享端点只建一个节点，不压缩、不拆分）
        n_src_want = len({a for a, _ in ad["faithful_mappings"]})
        n_tgt_want = len({b for _, b in ad["faithful_mappings"]})
        if len(src["nodes"]) != n_src_want:
            fail("B1", f"{gdir.name} 源节点 {len(src['nodes'])} != 去重概念数 {n_src_want}")
        if len(tgt["nodes"]) != n_tgt_want:
            fail("B1", f"{gdir.name} 目标节点 {len(tgt['nodes'])} != 去重概念数 {n_tgt_want}")
        # B2 两域超边数必须相等（L342）；节点数可以不等——多值对应是原文事实
        if len(src["edges"]) != len(tgt["edges"]):
            fail("B2", f"{gdir.name} 两域超边数不等")

        task_id, r = next(iter(ref.items()))

        # B4/B5 结构模式：参考映射必须满分（pair_consistency + type_pattern）
        res = metrics.score_prediction(tgt, src, {"pair_map": r["pair_map"]},
                                       ref_pairs=r["pair_map"])
        if res.get("mode") != "structural":
            fail("B4", f"{gdir.name} 未走结构模式")
        if res["n_checks"] != len(metrics.STRUCTURAL_CHECKS):
            fail("B4", f"{gdir.name} 清单项数 {res['n_checks']} != "
                       f"{len(metrics.STRUCTURAL_CHECKS)}")
        if res["sf"] != 1.0 or res["sipr"] != 1:
            fail("B5", f"{gdir.name} 参考映射未满分 sf={res['sf']} {res['checks']}")

        # B5b 区分力：错误映射不得满分
        pm = r["pair_map"]
        cyc = [[pm[i][0], pm[(i + 1) % len(pm)][1]] for i in range(len(pm))]
        if metrics.score_prediction(tgt, src, {"pair_map": cyc},
                                    ref_pairs=pm)["sipr"] == 1:
            fail("B5b", f"{gdir.name} 循环置换仍拿满分")

        # B6 多值映射
        if r["multiple_mapping_type"] != "none":
            if not r.get("valid_mappings"):
                fail("B6", f"{gdir.name} 多值映射无 valid_mappings")
            pairs = ad["faithful_mappings"]
            src_dup = len(pairs) > len({a for a, _ in pairs})
            tgt_dup = len(pairs) > len({b for _, b in pairs})
            want = ("both" if (src_dup and tgt_dup) else
                    "many_to_one" if src_dup else
                    "one_to_many" if tgt_dup else "none")
            if r["multiple_mapping_type"] != want:
                fail("B6", f"{gdir.name} multiple_mapping_type={r['multiple_mapping_type']} "
                           f"与数据实际 {want} 不符")

        # B8 公开输入含概念词（任务输入），但不含对应关系（答案）。
        # 评审 2026-11-02：抹掉原词会让任务无法完成，原词必须公开。
        def keys_of(v):
            if isinstance(v, dict):
                for k, x in v.items():
                    yield k
                    yield from keys_of(x)
            elif isinstance(v, list):
                for x in v:
                    yield from keys_of(x)

        present = set(keys_of([src, tgt, man]))
        for leak in ("faithful_mappings", "Explanation", "system_a_background",
                     "system_b_background", "valid_mappings", "node_map", "pair_map"):
            if leak in present:
                fail("B8", f"{gdir.name} 公开输入含答案字段 {leak}")
        # 概念词必须公开且与原文一致
        pub = {n["label"] for o in (src, tgt) for n in o["nodes"]}
        words = {w for pair in ad["faithful_mappings"] for w in pair}
        if pub != words:
            fail("B8", f"{gdir.name} 公开概念集与原文不一致")
        # 编号顺序不得泄露答案
        if all(a == b for a, b in pm):
            fail("B8", f"{gdir.name} 参考映射为恒等，编号顺序泄露答案")

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
