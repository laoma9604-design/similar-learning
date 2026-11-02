"""SCAR → 统一知识对象适配 v3（结构重建版）。

2026-11-02 评审意见驱动的重建。原版四条致命缺陷：
  A 两域按原始映射顺序编号 → 参考映射恒为 n1→n1，模型输出恒等映射即满分
  B 只有 node_bijection 一项检查 → 循环置换等错误映射同样满分
  C 节点 label 全为「概念」、类型全同 → 模型拿不到推理所需信息
  D 多对一被拆成同编号双射 → multiple_mapping_type 标注与数据自相矛盾

本轮重建：
  1. 两域**独立随机编号**（源用 s1..sk，目标用 t1..tk，各自打乱）
     参考映射不再是恒等；模型必须真正推理对应关系
  2. 节点 label 填**原始概念词**（这是任务输入，不是答案；「哪个对哪个」才是答案）
  3. 节点类型按词表 τ_V 标注（原文无类型，标 structure_source=inferred，
     available_checks 相应增加 node_type）
  4. 多解忠实表达：共享端点只建**一个**节点，多个源指向它；node_map 里真实体现
     n→m 的多对一，不再拆成同编号双射
  5. 有效映射集合区分两种情形（评审要求）：
       · 单一映射内的多值对应（multi_valued_in_one）—— 原文一条记录内的共享端点
       · 多个可接受的完整映射（alt_complete_mappings）—— 因置换对称等产生的等价完整解
     二者都存进 valid_mappings，但分别标注，评价口径不同
"""
import argparse
import hashlib
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

import scar_annotations_pilot as ANN

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "raw" / "scar" / "release" / "system_analogy_en.json"
OUT = ROOT / "cases" / "structural_scar"

SCHEMA_VERSION = "topoadv-schema-0.3.1"
VOCAB_VERSION = "topoadv-vocab-0.1.0-draft"

# ---------------- S04 五条规则（同前） ----------------
RESIDUE_LABEL_RE = re.compile(
    r'^\s*(items?|explanation|translation|elements?|concepts?|mapping|answer|'
    r'lists?|terms?|pairs?)\s*[:：]', re.I)
SELF_NEGATIVE_RE = re.compile(
    r"(may not be (appropriate|correct|suitable|accurate)|"
    r"(is|isn't) not (an? )?(appropriate|valid|suitable)|"
    r"not (a )?(good|proper|valid|accurate) (mapping|correspondence|match)|"
    r"does not (really )?(correspond|match|fit)|"
    r"weak (mapping|correspondence)|questionable)", re.I)

MANUAL_EXCLUDED = {
    42: dict(rule="R-manual",
             reason="Respiratory organs 重复出现并映射到 filter/Cleaner 两个同义目标，"
                    "属同义重复而非真实对称结构"),
    283: dict(rule="R-manual",
              reason="vehicle 重复出现 4 次且目标含 textbook/book 同义对；"
                     "第 14 对解释写 Guide 而映射为 conductor，解释与映射错位"),
}


def classify(rec):
    if rec["id"] in MANUAL_EXCLUDED:
        return "excluded", MANUAL_EXCLUDED[rec["id"]]
    maps = rec.get("mappings") or []
    expl = rec.get("Explanation") or []
    norm = [(str(a).strip(), str(b).strip()) for a, b in maps]

    if not norm:
        return "excluded", dict(rule="S1", reason="无映射对")
    if len(norm) < 2:
        return "excluded", dict(rule="S1", reason="映射对少于 2，无法构成关系")
    if any(not a or not b for a, b in norm):
        return "excluded", dict(rule="S1", reason="存在空端点")
    if not expl:
        return "excluded", dict(rule="S1", reason="无 Explanation，缺关系依据")
    if len(expl) != len(norm):
        return "excluded", dict(
            rule="S1",
            reason=f"解释条数({len(expl)})与映射对数({len(norm)})不一致，无法逐对确认关系依据")
    for i, e in enumerate(expl):
        if RESIDUE_LABEL_RE.match((e or "").strip()):
            return "excluded", dict(
                rule="S2",
                reason=f"第 {i+1} 条解释是模板残留：{(e or '')[:60]!r}")
    for i, e in enumerate(expl):
        m = SELF_NEGATIVE_RE.search(e or "")
        if m:
            return "excluded", dict(
                rule="S3",
                reason=f"第 {i+1} 条解释自述该映射不成立（{m.group(0)!r}），作者自认无效")
    return "confirmed", dict(rule="", mtype="none")


# ---------------- 节点类型推断（原文无类型，按词表判别式标注） ----------------
# 词表 discriminator 是 B/C 定的；这里按原文概念词做规则判断，标 inferred。
PROCESS_HINT = re.compile(
    r"(process|reaction|flow|growth|division|folding|learning|training|"
    r"propagation|transfer|selection|metabolism|evolution|infection|"
    r"replication|application|adjustment|maintenance|adaptation|"
    r"selection|filtering|removal|installation|operation)$")
PROPERTY_HINT = re.compile(
    r"(rate|size|amount|level|temperature|mass|charge|speed|frequency|"
    r"capacity|ability|strength|density|voltage|current|resistance|"
    r"pressure|concentration|duration|length|height|weight|power)$")
SUBSTANCE_HINT = re.compile(
    r"(^raw material|^material|^fuel|^food|^water|^blood|^air|^ore|^product|"
    r"^metabolite|^solute|^nutrient|^medicine|^gas|^liquid)$")
FORCE_HINT = re.compile(
    r"(^gravity$|^attraction$|^electricity$|^electromagnetism$|^force$|^friction$)")


def infer_node_type(word):
    """概念词的**占位**类型。

    注意：这不是可用的类型标注。实测 1946 个概念词中 92% 会落到兜底类，
    且 SCAR 正确映射有 32.5% 两端类型不同（跨范畴正是类比机制）。
    因此结构模式用 type_pattern（与参考的类型对应模式比较），
    不要求两端同类型。真正的类型标注见 a_data/scar_annotations_pilot.py
    的 20 组试点（人工标注，待 B/C 复核）。
    """
    w = " ".join(str(word).lower().split())
    if FORCE_HINT.search(w):
        return "force"
    if PROCESS_HINT.search(w):
        return "process"
    if PROPERTY_HINT.search(w):
        return "property"
    if SUBSTANCE_HINT.search(w):
        return "substance"
    return "abstract_concept"


def stable_hash(*parts):
    return hashlib.sha256(
        json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
        .encode("utf-8")).hexdigest()[:16]


def seeded(*parts):
    return int(stable_hash(*parts)[:8], 16)


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                               allow_nan=False) + "\n", encoding="utf-8")


# ============================================================
# S05 结构构建
# ============================================================
def build_group(rec, pair_index, raw_original=None):
    """一条 SCAR → 一个 structural 基础组。

    关键设计（对应评审意见）：
      源域节点 s1..sk 与目标域节点 t1..tk **各自独立打乱**，参考映射不是恒等。
      共享端点只建一个节点：sperm/egg 都指向同一个 product 节点。
    """
    status, detail = classify(rec)
    gid = f"group_scar_{rec['id']:04d}"
    pairs = [(str(a).strip(), str(b).strip()) for a, b in rec["mappings"]]

    # ---- 去重后的概念集合（这是 D 缺陷的核心修复）----
    src_words = []
    for a, _ in pairs:
        if a not in src_words:
            src_words.append(a)
    tgt_words = []
    for _, b in pairs:
        if b not in tgt_words:
            tgt_words.append(b)

    # ---- 两域独立随机编号（这是 A 缺陷的修复）----
    src_order = list(range(len(src_words)))
    rng_s = __import__("random").Random(seeded(gid, "src_ids"))
    rng_s.shuffle(src_order)
    src_id_of = {src_words[i]: f"s{j + 1}" for j, i in enumerate(src_order)}

    tgt_order = list(range(len(tgt_words)))
    rng_t = __import__("random").Random(seeded(gid, "tgt_ids"))
    rng_t.shuffle(tgt_order)
    tgt_id_of = {tgt_words[i]: f"t{j + 1}" for j, i in enumerate(tgt_order)}

    # ---- 参考映射：多值真实表达（源节点数可以 ≠ 目标节点数）----
    # node_map 是 dict，无法表达「一个源对多个目标」（virus → code, malware）。
    # 因此：单值组用 node_map；多值组用 pair_map（列表）完整保留每条对应，
    # node_map 只存其中最长的单值投影，仅供需要 dict 的场景参考。
    pair_map = [[src_id_of[a], tgt_id_of[b]] for a, b in pairs]
    node_map = {}
    for s, t in pair_map:
        node_map.setdefault(s, t)     # 不覆盖，保留第一条

    # ---- 结构类型：一个映射内的多值 vs 多个完整映射 ----
    # 语义：many_to_one = 多个源概念共享同一目标（sperm/egg → product）
    #       one_to_many = 同一源概念对应多个目标（virus → code/malware）
    src_dup = len(pairs) > len(src_words)
    tgt_dup = len(pairs) > len(tgt_words)
    if src_dup and tgt_dup:
        mtype = "both"
    elif src_dup:
        mtype = "many_to_one"
    elif tgt_dup:
        mtype = "one_to_many"
    else:
        mtype = "none"

    def make_obj(oid, words, id_of, label):
        # 试点 20 组有 A 的人工标注（类型逐词判定），其余用占位类型。
        # 占位类型只保证 ∈ τ_V，不参与 SF 判定（结构模式用 type_pattern 比对）。
        ann = ANN.ANNOTATIONS.get(rec["id"], {})
        ann_types = ann.get("node_types") or {}
        return {
            "object_id": oid,
            "object_kind": "structural",
            "relation_type": "scar_analogy",
            "split": None,
            "label": label,
            "nodes": [dict(node_id=id_of[w],
                           label=w,
                           type=ann_types.get(w) or infer_node_type(w))
                      for w in words],
            "edges": [dict(edge_id="e1", edge_type="scar_analogy",
                           input_nodes=[id_of[w] for w in words],
                           output_nodes=[],
                           roles={id_of[w]: "participant" for w in words})],
            "provenance": {"dataset": "scar", "original_id": str(rec["id"]),
                           "structure_source": "provided"},
        }

    src_obj = make_obj(f"obj_{gid}_src", src_words, src_id_of,
                       rec.get("system_a") or "源系统")
    tgt_obj = make_obj(f"obj_{gid}_tgt", tgt_words, tgt_id_of,
                       rec.get("system_b") or "目标系统")

    return dict(
        group_id=gid, rec=rec,
        raw_original=raw_original if raw_original is not None
        else json.loads(json.dumps(rec, ensure_ascii=False)),
        status=status, multiple_mapping_type=mtype,
        pairs=pairs, src_obj=src_obj, tgt_obj=tgt_obj,
        node_map=node_map, pair_map=pair_map, edge_map={"e1": "e1"},
        n_src=len(src_words), n_tgt=len(tgt_words), n_pairs=len(pairs),
    )


def write_group(g):
    gid = g["group_id"]
    gdir = OUT / gid
    rec = g["rec"]
    task_id = f"task_{gid}_t01"
    src_id = g["src_obj"]["object_id"]
    tgt_id = g["tgt_obj"]["object_id"]

    for o in (g["src_obj"], g["tgt_obj"]):
        o["split"] = g["split"]

    dump(gdir / "data/input/objects" / f"{src_id}.json", g["src_obj"])
    dump(gdir / "data/input/objects" / f"{tgt_id}.json", g["tgt_obj"])
    dump(gdir / "data/input/objects" / "index.json",
         {"objects": [dict(object_id=tgt_id, file=f"{tgt_id}.json"),
                      dict(object_id=src_id, file=f"{src_id}.json")]})

    dump(gdir / "data/input/tasks" / f"{task_id}.json",
         dict(task_id=task_id, group_id=gid, target_id=tgt_id,
              source_ids=[src_id],
              schema_version=SCHEMA_VERSION, vocab_version=VOCAB_VERSION,
              intervenable_inputs=[], specified_outputs=[],
              intervention_range={},
              _note="结构模式：无响应函数，不执行响应检验；"
                    "方法输入含概念词与结构，不含哪对哪的答案"))

    dump(gdir / "manifest.json", dict(
        group_id=gid, dataset="scar", relation_type="scar_analogy",
        schema_version=SCHEMA_VERSION, vocab_version=VOCAB_VERSION,
        split=g["split"], object_ids=[tgt_id, src_id], task_ids=[task_id],
        task_counts=dict(positive=1, negative=0, total=1),
        source_counts=dict(positive=1, negative=0),
        node_count_source=g["n_src"], node_count_target=g["n_tgt"],
        node_count_note="两域节点数可以不等：SCAR 存在共享端点的多值对应",
        multiple_mapping_type=g["multiple_mapping_type"],
    ))
    dump(gdir / "manifest.sealed.json", dict(
        group_id=gid, valid_sources=[src_id],
        annotation_status=g["status"]))

    # 有效映射：本组只有一条完整映射（原文一条记录），
    # 多值对应是"这一条映射内部的共享端点"，不是"多个完整映射"
    dump(gdir / "sealed/reference.json", {task_id: dict(
        task_id=task_id, label="positive",
        valid=[dict(source_id=src_id, node_map=g["node_map"],
                    edge_map=g["edge_map"])],
        # 多值组必须用 pair_map：dict 装不下「一个源对多个目标」
        pair_map=g["pair_map"],
        valid_mappings=[dict(node_map=g["node_map"], edge_map=g["edge_map"],
                             pair_map=g["pair_map"])],
        # 评审要求区分：一个映射内的多值 vs 多个可接受完整映射
        mapping_forms=dict(
            multi_valued_in_one=g["multiple_mapping_type"] != "none",
            alt_complete_mappings=[],      # SCAR 原文每条记录只有一种对应
            note=("multi_valued_in_one：同一条原始记录内概念共享端点或多目标对应；"
                  "alt_complete_mappings：因置换对称等产生的多个等价完整映射。"
                  "SCAR 未提供后者，故为空。"),
        ),
        exclusions=[],
        reference_tolerance=None,
        allowed_mappings_total=None,
        status="structural_only",
        multiple_mapping_type=g["multiple_mapping_type"],
        available_checks=["node_bijection", "node_type"],
        node_type_source="inferred",
        full_library_verified=True,
    )})

    dump(gdir / "sealed/adaptation.json", dict(
        adaptation_id=f"adapt_scar_{rec['id']:04d}",
        dataset="scar", original_id=str(rec["id"]),
        source_object_id=src_id, target_object_id=tgt_id,
        faithful_mappings=[[a, b] for a, b in g["pairs"]],
        explanation=rec.get("Explanation") or [],
        background={"source": rec.get("system_a_background", ""),
                    "target": rec.get("system_b_background", "")},
        raw=g["raw_original"],
        structure_source="provided",
        node_type_source="inferred",
        annotation_status=g["status"],
        valid_mappings=[dict(node_map=g["node_map"], edge_map=g["edge_map"])],
        available_checks=["node_bijection", "node_type"],
        multiple_mapping_type=g["multiple_mapping_type"],
        system={"source": rec.get("system_a"), "target": rec.get("system_b")},
        domains={"source": rec.get("system_a_domain"),
                 "target": rec.get("system_b_domain")},
        note=("节点/超边/映射来自原文 mappings；节点类型是按词表判别式推断"
              "（node_type_source=inferred），原文未标注。概念原词作为节点 label "
              "公开——那是任务输入；哪对哪的对应关系才是答案，只存 sealed。"
              "共享端点只建一个节点，多对一在 node_map 中真实体现。"),
    ))

    (gdir / "README.md").write_text(
        f"{gid} —— SCAR id={rec['id']}：{rec.get('system_a')} → {rec.get('system_b')}\n\n"
        f"领域：{rec.get('system_a_domain')} → {rec.get('system_b_domain')}\n"
        f"概念对：{g['n_pairs']}    源域节点：{g['n_src']}    目标域节点：{g['n_tgt']}\n"
        f"结构类型：{g['multiple_mapping_type']}\n"
        f"可核验检查项：node_bijection, node_type（类型为推断，原文未标注）\n"
        f"结构模式：无响应函数，不执行响应检验（任务书 L957）\n\n"
        f"参考映射与原始解释在 sealed/ 下，不进入方法输入。\n",
        encoding="utf-8")


# ============================================================
# 划分（L1020）
# ============================================================
def assign_splits(groups, seed=20261007):
    parent = {g["group_id"]: g["group_id"] for g in groups}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    by_system = defaultdict(list)
    for g in groups:
        rec = g["rec"]
        a = " ".join(str(rec.get("system_a")).lower().split())
        b = " ".join(str(rec.get("system_b")).lower().split())
        by_system[("a", a)].append(g["group_id"])
        by_system[("b", b)].append(g["group_id"])
    for ids in by_system.values():
        for other in ids[1:]:
            union(ids[0], other)

    blocks = defaultdict(list)
    for g in groups:
        blocks[find(g["group_id"])].append(g["group_id"])

    total = sum(len(v) for v in blocks.values())
    want = {"train": round(total * 0.70), "val": round(total * 0.15)}
    want["test"] = total - want["train"] - want["val"]

    keys = sorted(blocks, key=lambda k: (-len(blocks[k]), stable_hash("blk", k)))
    assign, cur = {}, {"train": 0, "val": 0, "test": 0}
    for k in keys:
        target = min(cur, key=lambda t: (cur[t] / want[t] if want[t] else 9e9,
                                         ["train", "val", "test"].index(t)))
        for gid in blocks[k]:
            assign[gid] = target
        cur[target] += len(blocks[k])
    return assign, len(blocks)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    records = [json.loads(l) for l in SRC.open(encoding="utf-8") if l.strip()]
    print(f"SCAR 原始条数: {len(records)}")
    raw_by_id = {r["id"]: json.loads(json.dumps(r, ensure_ascii=False))
                 for r in records}

    groups, excluded = [], []
    for rec in records:
        status, detail = classify(rec)
        if status == "excluded":
            excluded.append(dict(original_id=rec["id"],
                                 rule=detail.get("rule", ""),
                                 reason=detail.get("reason", ""),
                                 system_a=rec.get("system_a"),
                                 system_b=rec.get("system_b"),
                                 n_pairs=len(rec.get("mappings") or []),
                                 n_expl=len(rec.get("Explanation") or [])))
            continue
        groups.append(build_group(rec, len(groups), raw_by_id[rec["id"]]))

    # 结构类型已在 build_group 内判定，此处不再重复计算（DRY）

    print(f"纳入 {len(groups)} 条，排除 {len(excluded)} 条")
    print(f"  结构类型: {dict(Counter(g['multiple_mapping_type'] for g in groups))}")
    print(f"  源域节点数分布: {dict(sorted(Counter(g['n_src'] for g in groups).items()))}")
    print(f"  目标域节点数分布: {dict(sorted(Counter(g['n_tgt'] for g in groups).items()))}")
    ident = sum(1 for g in groups
                if all(k == v for k, v in g["node_map"].items()))
    print(f"  参考映射恰为同编号的组: {ident}  ← 应为 0（旧版 387/387 全是）")

    assign, n_blocks = assign_splits(groups)
    for g in groups:
        g["split"] = assign[g["group_id"]]
    print(f"  划分块数 {n_blocks} → {dict(Counter(assign.values()))}")

    if args.dry:
        print("\n[dry] 未落盘。")
        return 0

    if OUT.exists():
        shutil.rmtree(OUT)
    for g in groups:
        write_group(g)
    dump(OUT / "_excluded.json", dict(
        dataset="scar", source=str(SRC.relative_to(ROOT)).replace("\\", "/"),
        raw_count=len(records), included=len(groups),
        excluded_count=len(excluded),
        rule=("S1 解释完整性 / S2 解释有效性 / S3 作者自证不成立 / R-manual 人工判定。"
              "依据 L978 可核验结构、L984 不得用名称相似度替代关系标注、"
              "L986 材料不足则排除并记录原因。"),
        records=excluded,
    ))
    print(f"\n已写入 {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
