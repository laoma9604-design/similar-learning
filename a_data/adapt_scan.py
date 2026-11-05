"""SCAN → 统一知识对象适配 v1（N01–N08 落地）。

SCAN 与 SCAR 的差别（决定了本文件与 adapt_scar.py 的四处不同）：
  · SCAN 没有 Explanation、没有 background、没有 domain 字段
    ⇒ 关系依据只有「同一 target-source 对内的概念对列表」本身
  · 一个 target-source 对可能被切成**多行**（同义词拆分），
    按行建组会把一个原始映射拆成多个对象 ⇒ 必须先按 (target,source) 聚合
  · alternatives 字段是「另一个候选词」，不是关系依据（规范 1），
    但它是替代映射的证据，存进 sealed 供多解判定，不进方法输入
  · 同一 target 或同一 source 出现在多个对里（如 career↔mountain/hill/slope/journey）
    ⇒ 派生实例，划分时必须同组（L1020）

N 编号对照（用户给的任务表）：
  N01 获取原始数据      —— 本文件读 data/raw/scan/data/SCAN_dataset.csv
  N02 记录数据版本      —— data/SCAN数据来源说明.md（commit/MD5/许可）
  N03 提取原始映射组 ID —— 组 ID = group_scan_<原始对序号>，_mapping_index.json 记录
  N04 识别映射中的概念  —— 去重概念词成为节点 label（任务输入，不是答案）
  N05 梳理映射关系      —— sealed/reference.json 的 pair_map（答案，封存）
  N06 记录派生实例与来源—— adaptation.json 的 raw / derived_from / mapping_group_id
  N07 统一结构标注      —— nodes/edges/roles/type 按 T01-schema + T01-vocabulary
  N08 划分训练验证测试  —— assign_splits：同一 target/source 连通块不可分

设计红线（照抄 SCAR 结构重建后的做法）：
  1. 两域**独立随机编号**，参考映射不是恒等
  2. 节点 label 填**原始概念词**（题目），只有「哪个对哪个」是答案
  3. 共享端点只建**一个**节点，多对一真实表达，不拆成同编号双射
  4. 结构模式判据 pair_consistency + type_pattern（机械六类不适用跨范畴类比）
  5. type_pattern 的基准存进 reference.json 的 ref_type_pattern 快照，
     否则基准跟着候选变、永远相等（SCAR 实测 378/378 全漏判）
"""
import argparse
import csv
import hashlib
import json
import shutil
import sys
from collections import Counter, OrderedDict, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "raw" / "scan" / "data" / "SCAN_dataset.csv"
OUT = ROOT / "cases" / "structural_scan"
VOCAB = ROOT / "T01-vocabulary.json"

_VOCAB = json.loads(VOCAB.read_text(encoding="utf-8"))
VOCAB_ROLE_IDS = {
    r["role_id"]
    for e in _VOCAB["edge_types"]
    if e["edge_type_id"] == "analogy_correspondence"
    for r in e.get("roles", [])
}
VOCAB_TYPE_IDS = {t["type_id"] for t in _VOCAB["node_types"]}

# 版本号一律从源文件读，不硬编码（同类前科：VOCAB_VERSION 曾写死 0.1.0-draft）
_SCHEMA = json.load(open(ROOT / "T01-schema.json", encoding="utf-8"))
SCHEMA_VERSION = _SCHEMA["schema_version"]
VOCAB_VERSION = _VOCAB["vocab_version"]
STRUCTURAL_CHECKS = ["pair_consistency", "type_pattern"]

# 类型标注：与 SCAR 共用同一份全量词典（1946 词，人工逐词判定）。
# SCAN 独有词查不到时记进 _MISSING_TYPES 并落盘到 data/SCAN待标注类型.tsv，
# 由人工补标后重跑 —— 不允许静默兜底。
try:
    from scar_type_lexicon import LEXICON as TYPE_LEXICON
except ImportError:      # 允许从其它 cwd 运行
    sys.path.insert(0, str(ROOT / "a_data"))
    from scar_type_lexicon import LEXICON as TYPE_LEXICON

_MISSING_TYPES: set = set()

# SCAN 独有词的人工判定词典（51 词），与 SCAR 全量词典合并使用。
# 合并而不是二选一：同一个词在两份词典里必须给出同一个类型，冲突要能被发现。
try:
    from scan_type_lexicon import SCAN_TYPE_LEXICON
except ImportError:
    sys.path.insert(0, str(ROOT / "a_data"))
    from scan_type_lexicon import SCAN_TYPE_LEXICON

_CONFLICTS = {k: (TYPE_LEXICON[k], v) for k, v in SCAN_TYPE_LEXICON.items()
              if k in TYPE_LEXICON and TYPE_LEXICON[k] != v}
assert not _CONFLICTS, f"两份类型词典对同一词判定不一致: {_CONFLICTS}"
MERGED_LEXICON = {**TYPE_LEXICON, **SCAN_TYPE_LEXICON}

# schema 必填字段 available_checks 的合法取值（不写死，从评价器读）
sys.path.insert(0, str(ROOT / "a_data"))
try:
    from metrics import CHECK_GROUPS as _CHECK_GROUPS
except ImportError:                                   # metrics 不可导入时不静默放行
    raise
SCAN_AVAILABLE_CHECKS = ["pair_consistency", "type_pattern"]
assert set(SCAN_AVAILABLE_CHECKS) <= set(_CHECK_GROUPS), \
    f"available_checks 含未知类别: {set(SCAN_AVAILABLE_CHECKS) - set(_CHECK_GROUPS)}"



def norm_word(w):
    return " ".join(str(w).strip().lower().split())


def infer_node_type(word):
    key = norm_word(word)
    t = MERGED_LEXICON.get(key)
    if t and t in VOCAB_TYPE_IDS:
        return t
    _MISSING_TYPES.add(norm_word_label(word))
    return "abstract_concept"


def norm_word_label(w):
    return str(w).strip()


# ============================================================
# N03 原始映射组：按 (target, source) 聚合，一行词对不是一个组
# ============================================================
def load_scan():
    with SRC.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    return rows


def group_rows(rows):
    """按 (target, source) 聚合，保持原文首次出现顺序作为组序号。"""
    groups = OrderedDict()
    for idx, r in enumerate(rows):
        key = (str(r["target"]).strip(), str(r["source"]).strip())
        groups.setdefault(key, []).append((idx, r))
    return groups


# ============================================================
# N04/N05 纳入判定与结构构建
# ============================================================
def classify(pairs, analogy_types):
    """判定这一组能不能做成结构任务。

    判定顺序固定（与 SCAR 一致，避免计数随实现漂移）：
      空端点 → 映射对 <2 → 词对为空
    SCAN 无 Explanation，所以没有「解释条数」这条；关系依据就是同一对内的
    概念对集合本身（原文即如此），不是靠词义推测。
    """
    if any(not a or not b for a, b in pairs):
        return "excluded", dict(rule="C1", reason="存在空端点")
    if len(pairs) < 2:
        return "excluded", dict(rule="C1", reason="映射对少于 2，无法构成关系")
    if len(set(pairs)) < 2:
        return "excluded", dict(rule="C1", reason="去重后映射对不足 2")
    if not analogy_types:
        return "excluded", dict(rule="C1", reason="缺 analogy_type")
    return "confirmed", dict(rule="")


def hash_seed(*parts):
    return hashlib.sha256(
        json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
        .encode("utf-8")).hexdigest()[:16]


def seeded(*parts):
    return int(hash_seed(*parts)[:8], 16)


def _type_pattern_of(src_obj, tgt_obj, pair_map):
    smap = {n["node_id"]: n["type"] for n in src_obj["nodes"]}
    tmap = {n["node_id"]: n["type"] for n in tgt_obj["nodes"]}
    return sorted([smap[a], tmap[b]] for a, b in pair_map)


def build_group(gid, key, rows_for_pair, group_index):
    """一个 (target, source) 原始对 → 一个 structural 基础组。

    两域独立随机编号；共享端点只建一个节点；多值在 pair_map 中真实体现。
    """
    target_sys, source_sys = key
    pairs = []
    for _, r in rows_for_pair:
        p = (norm_word_label(r["targ_word"]), norm_word_label(r["src_word"]))
        if p not in pairs:
            pairs.append(p)
    a_types = [str(r["analogy_type"]).strip() for _, r in rows_for_pair]
    alts = []
    for _, r in rows_for_pair:
        for a in str(r.get("alternatives") or "").split(","):
            a = a.strip()
            if a and a not in alts:
                alts.append(a)

    status, detail = classify(pairs, a_types)
    analogy_type = Counter(a_types).most_common(1)[0][0] if a_types else ""

    src_words, tgt_words = [], []
    for a, b in pairs:          # 注意：pairs 是 (target_word, source_word)
        if b not in src_words:
            src_words.append(b)
        if a not in tgt_words:
            tgt_words.append(a)

    src_id_of, tgt_id_of = {}, {}
    order = list(range(len(src_words)))
    __import__("random").Random(seeded(gid, "src_ids")).shuffle(order)
    for j, i in enumerate(order):
        src_id_of[src_words[i]] = f"s{j + 1}"
    order = list(range(len(tgt_words)))
    __import__("random").Random(seeded(gid, "tgt_ids")).shuffle(order)
    for j, i in enumerate(order):
        tgt_id_of[tgt_words[i]] = f"t{j + 1}"

    pair_map = [[src_id_of[b], tgt_id_of[a]] for a, b in pairs]
    node_map = {}
    for s, t in pair_map:
        node_map.setdefault(s, t)

    # 语义与 SCAR 一致（注意方向别标反）：
    #   many_to_one = 多个源概念共享同一目标概念（src_word 重复）
    #   one_to_many = 同一源概念对应多个目标概念（targ_word 重复）
    src_dup = len(pairs) > len(src_words)
    tgt_dup = len(pairs) > len(tgt_words)
    mtype = ("both" if src_dup and tgt_dup else
             "many_to_one" if src_dup else
             "one_to_many" if tgt_dup else "none")

    def make_obj(oid, words, id_of, label, side):
        cnt = Counter()
        for a, b in pairs:
            cnt[b if side == "src" else a] += 1
        roles = {id_of[w]: ("hub" if cnt[w] > 1 else "correlate") for w in words}
        for w in words:
            assert roles[id_of[w]] in VOCAB_ROLE_IDS, roles[id_of[w]]
        return {
            "object_id": oid,
            "object_kind": "structural",
            "relation_type": "analogy_correspondence",
            "split": None,
            "label": label,
            "nodes": [dict(node_id=id_of[w], label=w, type=infer_node_type(w))
                      for w in words],
            "edges": [dict(edge_id="e1", edge_type="analogy_correspondence",
                           input_nodes=[id_of[w] for w in words],
                           output_nodes=[],
                           roles=roles)],
            "provenance": {"dataset": "scan", "original_id": gid,
                           "structure_source": "provided"},
        }

    src_obj = make_obj(f"obj_{gid}_src", src_words, src_id_of,
                       f"{source_sys}", "src")
    tgt_obj = make_obj(f"obj_{gid}_tgt", tgt_words, tgt_id_of,
                       f"{target_sys}", "tgt")

    return dict(
        group_id=gid, mapping_group_id=gid, group_index=group_index,
        target_system=target_sys, source_system=source_sys,
        pairs=pairs, raw_rows=[dict(r) for _, r in rows_for_pair],
        row_indices=[i for i, _ in rows_for_pair],
        alternatives=alts, analogy_type=analogy_type,
        status=status, classify_detail=detail,
        multiple_mapping_type=mtype,
        src_obj=src_obj, tgt_obj=tgt_obj,
        node_map=node_map, pair_map=pair_map, edge_map={"e1": "e1"},
        n_src=len(src_words), n_tgt=len(tgt_words), n_pairs=len(pairs),
    )


# ============================================================
# 落盘
# ============================================================
def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                               allow_nan=False) + "\n", encoding="utf-8")


def write_group(g):
    gid = g["group_id"]
    gdir = OUT / gid
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
        group_id=gid, dataset="scan", relation_type="analogy_correspondence",
        schema_version=SCHEMA_VERSION, vocab_version=VOCAB_VERSION,
        split=g["split"], object_ids=[tgt_id, src_id], task_ids=[task_id],
        task_counts=dict(positive=1, negative=0, total=1),
        source_counts=dict(positive=1, negative=0),
        node_count_source=g["n_src"], node_count_target=g["n_tgt"],
        node_count_note="两域节点数可以不等：SCAN 存在共享端点的多值对应",
        multiple_mapping_type=g["multiple_mapping_type"],
        analogue_type=g["analogy_type"],
    ))
    dump(gdir / "manifest.sealed.json", dict(
        group_id=gid, valid_sources=[src_id],
        annotation_status=g["status"]))

    dump(gdir / "sealed/reference.json", {task_id: dict(
        task_id=task_id, label="positive",
        valid=[dict(source_id=src_id, node_map=g["node_map"],
                    edge_map=g["edge_map"])],
        pair_map=g["pair_map"],
        valid_mappings=[dict(node_map=g["node_map"], edge_map=g["edge_map"],
                             pair_map=g["pair_map"])],
        mapping_forms=dict(
            multi_valued_in_one=g["multiple_mapping_type"] != "none",
            alt_complete_mappings=[],
            note=("multi_valued_in_one：同一原始对内的共享端点/多目标对应；"
                  "alt_complete_mappings：置换对称等产生的等价完整映射。"
                  "SCAN 原文字段 alternatives 是「另一个候选词」，"
                  "它不构成等价完整映射（原文未给该词的对应关系），"
                  "故此处为空，另存 alternatives_provided 供复核。"),
        ),
        alternatives_provided=g["alternatives"],
        exclusions=[],
        reference_tolerance=None,
        allowed_mappings_total=None,
        status="structural_only",
        multiple_mapping_type=g["multiple_mapping_type"],
        structural_checks=STRUCTURAL_CHECKS,
        node_type_source="inferred",
        ref_type_pattern=_type_pattern_of(g["src_obj"], g["tgt_obj"],
                                          g["pair_map"]),
        ref_roles={},          # SCAN 原文无角色表述，不启用 role_consistency
        full_library_verified=True,
    )})

    dump(gdir / "sealed/adaptation.json", dict(
        adaptation_id=f"adapt_scan_{g['group_index']:04d}",
        dataset="scan", original_id=gid, mapping_group_id=gid,
        source_object_id=src_id, target_object_id=tgt_id,
        faithful_mappings=[[a, b] for a, b in g["pairs"]],
        # SCAN 原文没有解释与背景：如实留空，不代写
        explanation=[], background={"source": "", "target": ""},
        raw=dict(target=g["target_system"], source=g["source_system"],
                 row_indices=g["row_indices"], rows=g["raw_rows"]),
        structure_source="provided",
        node_type_source="inferred",
        annotation_status=g["status"],
        valid_mappings=[dict(node_map=g["node_map"], edge_map=g["edge_map"])],
        # schema 必填字段（2026-11-02 复核补）：该组**有原始依据**可核验的检查项类别，
        # 取值必须 ∈ metrics.CHECK_GROUPS。SCAN 原文只给概念对：
        #   · pair_consistency —— 对应关系是原文给的
        #   · type_pattern     —— 类型是 inferred，但对应关系成立时模式可核
        # 不含 node_bijection（29 组多值对应，双射必然失败）、
        # 不含 role（原文无任何角色表述）、不含输入输出集合（原文无方向）。
        available_checks=list(SCAN_AVAILABLE_CHECKS),
        # 与 available_checks 同值：结构模式实际使用的判据。
        # schema 里没有这个字段名，保留是因为 reference.json/README 用同一口径，
        # 但真正被评价器读取的是 available_checks。
        structural_checks=STRUCTURAL_CHECKS,
        multiple_mapping_type=g["multiple_mapping_type"],
        analogue_type=g["analogy_type"],
        alternatives=g["alternatives"],
        # 与 SCAR 同类记录保持同名（schema 未定义该字段，属两个结构数据集共有的
        # 补充字段；不加 schema 以外的自定义名字，避免 B/C 解析器分叉）
        system={"source": g["source_system"], "target": g["target_system"]},
        note=("映射来自原文 (target,source,targ_word,src_word) 四列；"
              "SCAN 无 Explanation/background/domain/role 表述，"
              "对应字段留空且 ref_roles 为空（不启用 role_consistency）。"
              "节点类型按词表 discriminator 推断（node_type_source=inferred）。"
              "alternatives 是额外候选词，不是关系依据，仅存封存供复核。"),
    ))

    (gdir / "README.md").write_text(
        f"{gid} —— SCAN：{g['source_system']} → {g['target_system']}\n\n"
        f"类比类型：{g['analogy_type']}    （原始行号 {g['row_indices']}）\n"
        f"概念对：{g['n_pairs']}    源域节点：{g['n_src']}    "
        f"目标域节点：{g['n_tgt']}\n"
        f"结构类型：{g['multiple_mapping_type']}\n"
        f"结构模式检查项：{', '.join(STRUCTURAL_CHECKS)}\n"
        f"无响应函数，不执行响应检验（任务书 L957）\n\n"
        f"参考映射在 sealed/reference.json，不进入方法输入。\n",
        encoding="utf-8")


# ============================================================
# N08 划分：同一 target/source 派生实例必须同组（L1020）
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
        by_system[("t", norm_word(g["target_system"]))].append(g["group_id"])
        by_system[("s", norm_word(g["source_system"]))].append(g["group_id"])
    for ids in by_system.values():
        for other in ids[1:]:
            union(ids[0], other)

    blocks = defaultdict(list)
    for g in groups:
        blocks[find(g["group_id"])].append(g["group_id"])

    total = sum(len(v) for v in blocks.values())
    want = {"train": round(total * 0.70), "val": round(total * 0.15)}
    want["test"] = total - want["train"] - want["val"]

    keys = sorted(blocks, key=lambda k: (-len(blocks[k]), hash_seed("blk", k)))
    assign, cur = {}, {"train": 0, "val": 0, "test": 0}
    for k in keys:
        target = min(cur, key=lambda t: (cur[t] / want[t] if want[t] else 9e9,
                                         ["train", "val", "test"].index(t)))
        for gid in blocks[k]:
            assign[gid] = target
        cur[target] += len(blocks[k])
    return assign, len(blocks)


# ============================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    rows = load_scan()
    pairs = group_rows(rows)
    print(f"SCAN 原始行数: {len(rows)}   target-source 原始对: {len(pairs)}")
    assert len(rows) == 451, len(rows)
    assert len(pairs) == 65, len(pairs)

    groups, excluded, index = [], [], []
    for gi, (key, rs) in enumerate(pairs.items()):
        gid = f"group_scan_{gi + 1:04d}"
        index.append(dict(mapping_group_id=gid, target=key[0], source=key[1],
                          row_indices=[i for i, _ in rs], n_rows=len(rs)))
        g = build_group(gid, key, rs, gi)
        if g["status"] == "excluded":
            excluded.append(dict(original_id=gid, target=key[0], source=key[1],
                                 rule=g["classify_detail"].get("rule", ""),
                                 reason=g["classify_detail"].get("reason", ""),
                                 row_indices=g["row_indices"],
                                 n_pairs=g["n_pairs"]))
            continue
        groups.append(g)

    print(f"纳入 {len(groups)} 组，排除 {len(excluded)} 组")
    print(f"  结构类型: {dict(Counter(g['multiple_mapping_type'] for g in groups))}")
    print(f"  映射对数分布: {dict(sorted(Counter(g['n_pairs'] for g in groups).items()))}")
    print(f"  类比类型: {dict(Counter(g['analogy_type'] for g in groups))}")
    ident = sum(1 for g in groups
                if all(k == v for k, v in g["node_map"].items()))
    print(f"  参考映射恰为同编号的组: {ident}  ← 应为 0")

    assign, n_blocks = assign_splits(groups)
    for g in groups:
        g["split"] = assign[g["group_id"]]
    print(f"  划分块数 {n_blocks} → {dict(Counter(assign.values()))}")

    # 类型覆盖：SCAN 独有词必须显式列出，不许静默兜底
    missing = sorted(_MISSING_TYPES)
    print(f"  类型词典未覆盖的概念词: {len(missing)}")
    if missing:
        print(f"    {missing[:10]}{' ...' if len(missing) > 10 else ''}")

    if args.dry:
        print("\n[dry] 未落盘。")
        return 0

    if OUT.exists():
        shutil.rmtree(OUT)
    for g in groups:
        write_group(g)
    dump(OUT / "_mapping_index.json", dict(
        dataset="scan", source="data/raw/scan/data/SCAN_dataset.csv",
        raw_rows=len(rows), mapping_groups=len(pairs),
        note="N03 原始映射索引：一个 (target, source) 对 = 一个原始映射组，"
             "组内多行为同义词拆分，同一组不得跨划分。",
        groups=index))
    dump(OUT / "_excluded.json", dict(
        dataset="scan", source="data/raw/scan/data/SCAN_dataset.csv",
        raw_count=len(pairs), included=len(groups),
        excluded_count=len(excluded),
        rule="C1 结构不足（空端点 / 映射对<2 / 缺 analogy_type）。",
        records=excluded))
    dump(OUT / "_type_gaps.json", dict(
        missing_count=len(missing), missing=missing,
        note="统一类型词典（a_data/scar_type_lexicon.py）未覆盖的 SCAN 概念词。"
             "为空表示全覆盖。"))
    print(f"\n已写入 {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
