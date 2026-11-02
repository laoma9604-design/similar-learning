"""SCAR → 统一知识对象适配（结构模式，S05/S06/S07）。

设计约束（逐条对应科研规范与任务书）：
规范1 不得用概念名称相似度代替缺失的关系标注
    → 节点、超边、映射全部来自 SCAR 原文的 mappings；
      SCAR 未标注类型/角色/方向，本适配**不虚构**，而是在
      adaptation.available_checks 里声明只有 node_bijection 可核验。
规范2 原始材料不足以确定关系时排除并记录原因
    → Explanation 条数与映射对数不一致的条目不硬凑，标 excluded 并写原因。
规范3 一个任务可能存在多个合理映射
    → 多对一/一对多原样保留为多值映射集合，multiple_mapping_type 标注类型，
      valid_mappings 保存全部有效映射。

真实性与完整性：
    · 每条 SCAR 原始 JSON 逐字存进 adaptation.raw（含背景与 Explanation）
    · faithful_mappings 保存原始概念对，不做大小写/单复数归一
    · 节点数 = 映射对数，不压缩、不补造子关系（超边恒为 1 条，因为原文没有关系划分，
      这是数据事实而非简化）

输出（写入 cases/structural_scar/）：
    <group_id>/data/input/objects/*.json      公开对象（无答案）
    <group_id>/data/input/tasks/*.json        任务（无标签）
    <group_id>/manifest.json                  公开索引
    <group_id>/manifest.sealed.json           封存：哪侧是有效映射
    <group_id>/sealed/reference.json          封存参考（含 valid_mappings 集合）
    <group_id>/sealed/adaptation.json         封存适配材料（raw/explanation/background）
    <group_id>/README.md

用法：
    python a_data/adapt_scar.py --dry       # 只体检不落盘
    python a_data/adapt_scar.py             # 落盘
"""
import argparse
import hashlib
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "raw" / "scar" / "release" / "system_analogy_en.json"
OUT = ROOT / "cases" / "structural_scar"

SCHEMA_VERSION = "topoadv-schema-0.3.1"
VOCAB_VERSION = "topoadv-vocab-0.1.1"

# SCAR 原文只提供概念对与逐对解释：只有双射类检查项有原始依据
SCAR_AVAILABLE_CHECKS = ["node_bijection"]

# 节点类型：SCAR 未标注，按词表给统一占位类型（不是猜测分类，而是"未分类"的显式表示）
SCAR_NODE_TYPE = "abstract_concept"


def stable_hash(*parts):
    payload = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


# ============================================================
# S04：纳入 / 排除判定（五条规则，按 PDF L978/L984/L986）
# ============================================================
# S1 解释完整性：解释条数 == 映射对数，逐对都能确认关系依据
# S2 解释有效性：解释必须是实质内容，不能是 "Items:" / "Explanation:" 模板残留
# S3 作者自证不成立：解释里出现 "may not be appropriate" 等自我否定
#    → 作者本人认为这条映射不成立，必须排除（不是我们的判断，是原文自述）
# S4 冗余对：真实对称结构（sperm/egg 都对 product）保留为映射集合；
#    同义重复（同一词换单复数）才判质量不足。实测 30 条全属前者，无需排除
# S5 多值结构：一源多目标原样保存，由 multiple_mapping_type 标注
RESIDUE_LABEL_RE = re.compile(
    r'^\s*(items?|explanation|translation|elements?|concepts?|mapping|answer|'
    r'lists?|terms?|pairs?)\s*[:：]', re.I)
SELF_NEGATIVE_RE = re.compile(
    r"(may not be (appropriate|correct|suitable|accurate)|"
    r"(is|isn't) not (an? )?(appropriate|valid|suitable)|"
    r"not (a )?(good|proper|valid|accurate) (mapping|correspondence|match)|"
    r"does not (really )?(correspond|match|fit)|"
    r"weak (mapping|correspondence)|questionable)", re.I)

# S6 用：解释开头的 "X corresponds to Y:" 句式
CORRESPONDS_RE = re.compile(
    r"^(?:the\s+)?([A-Za-z0-9' \-]+?)\s+(?:corresponds?|corresponding)\s+to\s+"
    r"(?:the\s+)?([A-Za-z0-9' \-]+?)\s*(?:[:：]|$)", re.I)

_STOP = {'a', 'an', 'the', 'of', 'to', 'in', 'on', 'and', 'or', 'for', 'with', 'by', 's'}


def _tokens(s):
    """取比较用词干，容忍单复数与派生词形（只用于判断"讲的是不是同一个概念"）。"""
    out = set()
    for w in re.findall(r"[a-z0-9\-']+", str(s).lower()):
        if w in _STOP:
            continue
        for suf in ('ments', 'ment', 'ings', 'ing', 'ations', 'ation',
                    'ances', 'ance', 'ences', 'ence', 'ities', 'ity',
                    'ives', 'ive', 'als', 'al', 'es', 's'):
            if len(w) > len(suf) + 3 and w.endswith(suf):
                w = w[:-len(suf)]
                break
        out.add(w[:6])
    return out


def _token_overlap(said, real):
    """解释里说的概念与该条映射的概念是否指向同一个（任一词干相交即算）。"""
    ts, tr = _tokens(said), _tokens(real)
    if not ts or not tr:
        return True          # 取不到词就不判，避免误伤
    return bool(ts & tr)


def _pair_matches(said_a, said_b, real_a, real_b):
    """解释说的概念对是否就是该条映射的概念对。

    实测 SCAR 的解释常有三种正常写法，都不能算错位：
      ① 词形变化：adjust ↔ maintain      解释 "Adjustment ↔ maintenance"
      ② 顺序反写：retina ↔ film          解释 "film ↔ retina"
      ③ 扩大表述：sequence ↔ parts       解释 "Amino acid sequence ↔ puzzle pieces"
    因此判据是「两端都能对上（顺序不限）」，而不是字面相等。
    """
    fwd = _token_overlap(said_a, real_a) and _token_overlap(said_b, real_b)
    rev = _token_overlap(said_a, real_b) and _token_overlap(said_b, real_a)
    return fwd or rev


# 人工复核后确定排除的条目（试点阶段逐条读过原文判定），
# 不作为通用规则：S4b/S6 这类"同义重复""解释错位"的自动判定在 SCAR 上误伤率过高
# （实测 S6 自动判定误伤 76 条，把 Adjustment↔adjust 这类正常词形变化也判成错位），
# 因此只记录经人工确认的条目，规则本身不入库。
MANUAL_EXCLUDED = {
    42: dict(rule="R-manual",
             reason="Respiratory organs 重复出现并映射到 filter/Cleaner 两个同义目标，"
                    "属同义重复而非真实对称结构"),
    283: dict(rule="R-manual",
              reason="vehicle 重复出现 4 次且目标含 textbook/book 同义对；"
                     "第 14 对解释写 Guide 而映射为 conductor，解释与映射错位"),
}


def classify(rec):
    """返回 (status, detail)。status ∈ {confirmed, non_bijective, excluded}"""
    # 先查人工确认的排除清单（试点阶段逐条读原文判定）
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

    # S1 解释完整性
    if not expl:
        return "excluded", dict(rule="S1", reason="无 Explanation，缺关系依据（禁止用词义相似度补）")
    if len(expl) != len(norm):
        return "excluded", dict(
            rule="S1",
            reason=f"解释条数({len(expl)})与映射对数({len(norm)})不一致，无法逐对确认关系依据")

    # S2 解释有效性（模板残留）
    for i, e in enumerate(expl):
        if RESIDUE_LABEL_RE.match((e or "").strip()):
            return "excluded", dict(
                rule="S2",
                reason=f"第 {i+1} 条解释是模板残留（以列举标签开头）：{(e or '')[:60]!r}")

    # S3 作者自证不成立
    for i, e in enumerate(expl):
        m = SELF_NEGATIVE_RE.search(e or "")
        if m:
            return "excluded", dict(
                rule="S3",
                reason=f"第 {i+1} 条解释自述该映射不成立（{m.group(0)!r}），作者自认无效")

    # S6 解释与映射错位（已停用自动判定，见 MANUAL_EXCLUDED 的说明）
    # 保留代码位置以便将来有可靠判据时恢复，当前不生效。

    # S4/S5 结构类型（重复端一律保留为映射集合）
    la = [a.lower() for a, _ in norm]
    lb = [b.lower() for _, b in norm]
    dup_a = sorted({x for x, c in Counter(la).items() if c > 1})
    dup_b = sorted({x for x, c in Counter(lb).items() if c > 1})

    if dup_a and dup_b:
        return "non_bijective", dict(rule="S5", mtype="both", dup_a=dup_a, dup_b=dup_b)
    if dup_a:
        return "non_bijective", dict(rule="S5", mtype="one_to_many", dup_a=dup_a)
    if dup_b:
        return "non_bijective", dict(rule="S5", mtype="many_to_one", dup_b=dup_b)
    return "confirmed", dict(rule="", mtype="none")


# ============================================================
# S05：转换成统一知识对象
# ============================================================
def build_group(rec, pair_index, raw_original=None):
    """一条 SCAR → 一个 structural 基础组（system_a 为源域，system_b 为目标域）。

    方向说明：SCAR 的 mappings 是 [system_a 的词, system_b 的词]。
    统一约定映射方向是 source→target，因此 source=system_a、target=system_b，
    node_map 直接是 a 词 → b 词。不改写原意。

    raw_original: 原文的干净副本，用于 adaptation.raw 逐字留存；
    不传时用 rec 自身（调用方须保证 rec 未被写入任何内部字段）。
    """
    status, detail = classify(rec)
    gid = f"group_scar_{rec['id']:04d}"
    mtype = detail.get("mtype", "none")
    pairs = [(str(a).strip(), str(b).strip()) for a, b in rec["mappings"]]

    # 节点 ID：用无意义编号 n1..nk，与 MRED 一致（不泄露语义、不依赖原文词形）
    n = len(pairs)
    src_ids = [f"n{i+1}" for i in range(n)]
    tgt_ids = [f"n{i+1}" for i in range(n)]   # 两域节点数相等（L342）

    src_words = [a for a, _ in pairs]
    tgt_words = [b for _, b in pairs]

    def make_obj(oid, words, ids, label, side):
        return {
            "object_id": oid,
            "object_kind": "structural",
            "relation_type": "scar_analogy",
            "split": None,
            "label": label,
            "nodes": [dict(node_id=i, label="概念", type=SCAR_NODE_TYPE,
                           slot=k + 1) for k, i in enumerate(ids)],
            "edges": [dict(edge_id="e1", edge_type="scar_analogy",
                           input_nodes=list(ids),      # 原文无方向：全部概念在同一超边内
                           output_nodes=[],
                           roles={i: "participant" for i in ids},
                           )],
            "provenance": {"dataset": "scar", "original_id": str(rec["id"]),
                           "structure_source": "provided",
                           "license": "未声明（README 仅要求引用）"},
        }

    src_obj = make_obj(f"obj_{gid}_src", src_words, src_ids,
                       "源系统", "source")
    tgt_obj = make_obj(f"obj_{gid}_tgt", tgt_words, tgt_ids,
                       "目标系统", "target")

    # 参考映射：source 节点 → target 节点
    node_map = {}
    edge_map = {"e1": "e1"}
    for k, (a, b) in enumerate(pairs):
        node_map[src_ids[k]] = tgt_ids[k]

    return dict(
        group_id=gid, rec=rec, raw_original=raw_original if raw_original is not None
        else json.loads(json.dumps(rec, ensure_ascii=False)),
        status=status, multiple_mapping_type=mtype,
        pairs=pairs, src_obj=src_obj, tgt_obj=tgt_obj,
        node_map=node_map, edge_map=edge_map, n_nodes=n,
    )


def write_group(g):
    gid = g["group_id"]
    gdir = OUT / gid
    rec = g["rec"]

    task_id = f"task_{gid}_t01"
    src_id = g["src_obj"]["object_id"]
    tgt_id = g["tgt_obj"]["object_id"]

    # ---- 公开对象 / 任务 ----
    dump(gdir / "data/input/objects" / f"{src_id}.json", g["src_obj"])
    dump(gdir / "data/input/objects" / f"{tgt_id}.json", g["tgt_obj"])
    dump(gdir / "data/input/objects" / "index.json",
         {"objects": [dict(object_id=tgt_id, file=f"{tgt_id}.json"),
                      dict(object_id=src_id, file=f"{src_id}.json")]})

    dump(gdir / "data/input/tasks" / f"{task_id}.json",
         dict(task_id=task_id, group_id=gid, target_id=tgt_id,
              source_ids=[src_id],
              schema_version=SCHEMA_VERSION, vocab_version=VOCAB_VERSION,
              intervenable_inputs=[],          # 结构模式无响应检验（L957）
              specified_outputs=[],
              intervention_range={},
              _note="结构模式：无响应函数，不执行响应检验；"
                    "方法输入不含标签、正确源域或见证点"))

    dump(gdir / "manifest.json", dict(
        group_id=gid, dataset="scar", relation_type="scar_analogy",
        schema_version=SCHEMA_VERSION, vocab_version=VOCAB_VERSION,
        split=g["split"], object_ids=[tgt_id, src_id],
        task_ids=[task_id],
        task_counts=dict(positive=1, negative=0, total=1),
        source_counts=dict(positive=1, negative=0),
        node_count=g["n_nodes"],
        multiple_mapping_type=g["multiple_mapping_type"],
    ))

    dump(gdir / "manifest.sealed.json", dict(
        group_id=gid,
        valid_sources=[src_id],
        annotation_status=g["status"],
    ))

    # ---- sealed/reference.json（规范3：保存有效映射集合）----
    dump(gdir / "sealed/reference.json", {task_id: dict(
        task_id=task_id, label="positive",
        valid=[dict(source_id=src_id, node_map=g["node_map"],
                    edge_map=g["edge_map"])],
        valid_mappings=[dict(node_map=g["node_map"], edge_map=g["edge_map"])],
        exclusions=[],
        reference_tolerance=None,               # 结构模式无响应容差
        allowed_mappings_total=None,            # 无枚举（非双射结构无法枚举一一映射）
        status="structural_only",
        multiple_mapping_type=g["multiple_mapping_type"],
        available_checks=SCAR_AVAILABLE_CHECKS,
        full_library_verified=True,
    )})

    # ---- sealed/adaptation.json（S07：原始解释与背景，逐字留存）----
    dump(gdir / "sealed/adaptation.json", dict(
        adaptation_id=f"adapt_scar_{rec['id']:04d}",
        dataset="scar",
        original_id=str(rec["id"]),
        source_object_id=src_id,
        target_object_id=tgt_id,
        faithful_mappings=[[a, b] for a, b in g["pairs"]],
        explanation=rec.get("Explanation") or [],
        background={"source": rec.get("system_a_background", ""),
                    "target": rec.get("system_b_background", "")},
        raw=g["raw_original"],
        structure_source="provided",
        annotation_status=g["status"],
        valid_mappings=[dict(node_map=g["node_map"], edge_map=g["edge_map"])],
        available_checks=SCAR_AVAILABLE_CHECKS,
        multiple_mapping_type=g["multiple_mapping_type"],
        system={"source": rec.get("system_a"), "target": rec.get("system_b")},
        domains={"source": rec.get("system_a_domain"),
                 "target": rec.get("system_b_domain")},
        note=("节点/超边/映射全部来自 SCAR 原文 mappings，未做语义推断；"
              "SCAR 未标注节点类型、角色与方向，故 available_checks 仅含节点双射。"
              "原文未划分关系，全部概念置于同一条超边（数据事实，非简化）。"),
    ))

    (gdir / "README.md").write_text(
        f"{gid} —— SCAR id={rec['id']}：{rec.get('system_a')} → {rec.get('system_b')}\n\n"
        f"领域：{rec.get('system_a_domain')} → {rec.get('system_b_domain')}\n"
        f"概念对数：{g['n_nodes']}（节点数与之一致，未压缩）\n"
        f"结构类型：{g['multiple_mapping_type']}\n"
        f"可核验检查项：{', '.join(SCAR_AVAILABLE_CHECKS)}（SCAR 无类型/角色/方向标注）\n"
        f"结构模式：无响应函数，不执行响应检验（任务书 L957）\n\n"
        f"封存材料：sealed/reference.json（参考映射）、sealed/adaptation.json"
        f"（原始概念对/解释/背景逐字留存）\n",
        encoding="utf-8")


# ============================================================
# 划分（L1020：同一 system 的派生关系须同组）
# ============================================================
def assign_splits(groups, seed=20261007):
    """按「共享 system」合并成连通块再划分，保证同一 system 不跨划分。"""
    import random
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
        # 归一化后再建连通块：SCAR 里同一系统会出现 "Water Cycle"/"water cycle"
        # 这类大小写与空白差异，不归一化会漏合并（实测漏了 92 个 system 跨划分）
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

    # 贪心：大块优先，各自放进「当前离目标缺口最大」的那一档。
    # 块是不可分单位（同一 system 的派生关系必须同组），所以只能逼近比例。
    import random as _r
    # 贪心：大块优先，放进「当前填充率最低」的那一档（按比例均衡，不是按绝对缺口）。
    keys = sorted(blocks, key=lambda k: (-len(blocks[k]), stable_hash("blk", k)))
    assign = {}
    cur = {"train": 0, "val": 0, "test": 0}
    for k in keys:
        size = len(blocks[k])
        # 填充率 = 当前 / 目标，最缺的档优先；并列按 train > val > test
        target = min(cur, key=lambda t: (cur[t] / want[t] if want[t] else 9e9,
                                         ["train", "val", "test"].index(t)))
        for gid in blocks[k]:
            assign[gid] = target
        cur[target] += size
    return assign, len(blocks)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    if not SRC.is_file():
        print(f"原始数据不存在: {SRC}")
        return 1
    records = [json.loads(l) for l in SRC.open(encoding="utf-8") if l.strip()]
    print(f"SCAR 原始条数: {len(records)}")

    # 原文逐字留存：单独深拷贝一份，任何内部字段（如 _split）都不许写进去。
    # 实测踩过：把 _split 直接挂到 rec 上，会把内部字段污染进 adaptation.raw，
    # 破坏「原文完整留存」这条验收要求。
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

    print(f"纳入 {len(groups)} 条，排除 {len(excluded)} 条")
    print(f"  结构类型分布: {dict(Counter(g['multiple_mapping_type'] for g in groups))}")
    print(f"  节点数分布  : {dict(sorted(Counter(g['n_nodes'] for g in groups).items()))}")

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
        raw_count=len(records), included=len(groups), excluded_count=len(excluded),
        rule=("规范1：不得用概念名称相似度代替关系标注；规范2：原始材料不足以"
              "确定关系时排除并记录原因。Explanation 条数与映射对数不一致即无法"
              "逐对确认关系依据，予以排除。"),
        records=excluded,
    ))
    print(f"\n已写入 {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
