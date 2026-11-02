"""SCAN 适配回归测试（对应 N01–N08）。

每条测试锁定一个具体失败模式，防止后续修改把已修好的问题改回去。
只读 cases/structural_scan 与原始 CSV，**不 import adapt_scan 的内部判据**
（验收器与被测代码共享逻辑就会互相作证）。

重点锁定的失败模式（都是本轮实跑撞到过的）：
  · 按行建组 ⇒ 一个原始对被拆成多个对象（451 行 vs 65 对）
  · 两域按原文顺序编号 ⇒ 参考映射恒等
  · 把 target/src 两列方向弄反（many_to_one 与 one_to_many 标反）
  · 抹掉概念原词 ⇒ 任务不可完成
  · 代写 SCAN 没有的 Explanation / background / domain
  · 派生块跨划分（同一 target/source 被拆开）
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCAN = ROOT / "cases" / "structural_scan"
SRC = ROOT / "data" / "raw" / "scan" / "data" / "SCAN_dataset.csv"


def strip_w(s):
    return str(s).strip()


@pytest.fixture(scope="module")
def rows():
    assert SRC.is_file(), "缺原始数据 data/raw/scan"
    with SRC.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def scan():
    assert SCAN.is_dir(), "先运行 a_data/adapt_scan.py"
    dirs = sorted(p for p in SCAN.iterdir()
                  if p.is_dir() and p.name.startswith("group_scan_"))
    out = []
    for d in dirs:
        ref = json.loads((d / "sealed/reference.json").read_text(encoding="utf-8"))
        out.append(dict(
            dir=d,
            man=json.loads((d / "manifest.json").read_text(encoding="utf-8")),
            ad=json.loads((d / "sealed/adaptation.json").read_text(encoding="utf-8")),
            ref=ref,
            task=next(iter(ref.values())),
        ))
    return out


# ---------------- N03 原始映射组 ----------------
def test_n03_grouping_is_by_pair_not_by_row(scan, rows):
    """451 行必须聚成 65 个原始对；按行建组会把一个映射拆成多个对象。"""
    assert len(rows) == 451
    assert len(scan) == 65
    ex = json.loads((SCAN / "_excluded.json").read_text(encoding="utf-8"))
    assert ex["raw_count"] == 65
    assert ex["included"] + ex["excluded_count"] == 65
    idx = json.loads((SCAN / "_mapping_index.json").read_text(encoding="utf-8"))
    assert idx["mapping_groups"] == 65
    assert idx["raw_rows"] == 451
    # 每个原始对在索引里只出现一次
    keys = [(g["target"], g["source"]) for g in idx["groups"]]
    assert len(keys) == len(set(keys)) == 65


def test_n03_every_row_belongs_to_exactly_one_group(scan, rows):
    """N03 的可追溯性：451 行每行恰好属于一个组，不重不漏。"""
    seen = Counter()
    for g in scan:
        for i in g["ad"]["raw"]["row_indices"]:
            seen[i] += 1
    assert sorted(seen) == list(range(len(rows)))
    assert max(seen.values()) == 1, [i for i, c in seen.items() if c > 1][:5]


def test_n03_row_indices_match_pair_content(scan, rows):
    """组号指向的行必须真的是这个 (target, source) 对，不能张冠李戴。"""
    for g in scan:
        want_t = strip_w(rows[g["ad"]["raw"]["row_indices"][0]]["target"])
        want_s = strip_w(rows[g["ad"]["raw"]["row_indices"][0]]["source"])
        assert g["ad"]["system"]["target"] == want_t
        assert g["ad"]["system"]["source"] == want_s
        for i in g["ad"]["raw"]["row_indices"]:
            assert strip_w(rows[i]["target"]) == want_t
            assert strip_w(rows[i]["source"]) == want_s


# ---------------- N04 概念与节点 ----------------
def test_n04_concept_words_are_public_and_verbatim(scan):
    """概念原词是题目输入，必须公开且与原文一致（不能抹成「概念」占位）。"""
    for g in scan:
        fm = g["ad"]["faithful_mappings"]
        want = {strip_w(w) for p in fm for w in p}
        idx = json.loads((g["dir"] / "data/input/objects/index.json")
                         .read_text(encoding="utf-8"))
        got = set()
        for o in idx["objects"]:
            obj = json.loads((g["dir"] / "data/input/objects" / o["file"])
                             .read_text(encoding="utf-8"))
            got |= {n["label"] for n in obj["nodes"]}
        assert got == want, g["dir"].name


def test_n04_node_count_equals_unique_concepts(scan):
    """共享端点只建一个节点；节点数 = 各自去重概念数，不压缩不拆分。"""
    for g in scan:
        fm = g["ad"]["faithful_mappings"]
        idx = json.loads((g["dir"] / "data/input/objects/index.json")
                         .read_text(encoding="utf-8"))
        objs = {o["object_id"]: json.loads((g["dir"] / "data/input/objects" / o["file"])
                                           .read_text(encoding="utf-8"))
                for o in idx["objects"]}
        tgt_id, src_id = g["man"]["object_ids"][0], g["man"]["object_ids"][1]
        assert len(objs[src_id]["nodes"]) == len({strip_w(b) for _, b in fm})
        assert len(objs[tgt_id]["nodes"]) == len({strip_w(a) for a, _ in fm})


def test_n04_node_type_covers_all_words(scan):
    """类型必须落在 τ_V 里；覆盖缺口必须被记录（_type_gaps.json 为空）。"""
    vocab = json.loads((ROOT / "T01-vocabulary.json").read_text(encoding="utf-8"))
    tau_v = {t["type_id"] for t in vocab["node_types"]}
    gaps = json.loads((SCAN / "_type_gaps.json").read_text(encoding="utf-8"))
    assert gaps["missing_count"] == 0, gaps["missing"][:10]
    for g in scan:
        idx = json.loads((g["dir"] / "data/input/objects/index.json")
                         .read_text(encoding="utf-8"))
        for o in idx["objects"]:
            obj = json.loads((g["dir"] / "data/input/objects" / o["file"])
                             .read_text(encoding="utf-8"))
            for n in obj["nodes"]:
                assert n["type"] in tau_v, (g["dir"].name, n)


# ---------------- N05 参考映射 ----------------
def test_n05_reference_is_never_identity(scan):
    """两域独立编号：参考映射恰为同编号的组必须是 0（否则恒等输出即满分）。"""
    ident = [g["dir"].name for g in scan
             if all(s == t for s, t in g["task"]["pair_map"])]
    assert ident == [], ident


def test_n05_reference_pairmap_matches_original(scan):
    """参考映射必须与原文四列一一对应，顺序与词形（除首尾空白）一致。

    ⚠ 两处的列序**故意相反**，最容易读错（本轮就在这里误判过一次）：
      faithful_mappings 每项 = [targ_word, src_word]     （照抄 CSV 列序）
      pair_map          每项 = [源域节点ID, 目标域节点ID]（照抄项目铁律 source→target）
    所以用 pair_map 还原时必须取 (lab[t], lab[s])，否则整组对应全部镜像。
    """
    for g in scan:
        pairs = {(strip_w(a), strip_w(b)) for a, b in g["ad"]["faithful_mappings"]}
        ref_pairs = g["task"]["pair_map"]
        assert len(ref_pairs) == len(pairs)
        idx = json.loads((g["dir"] / "data/input/objects/index.json")
                         .read_text(encoding="utf-8"))
        lab = {}
        for o in idx["objects"]:
            obj = json.loads((g["dir"] / "data/input/objects" / o["file"])
                             .read_text(encoding="utf-8"))
            for n in obj["nodes"]:
                lab[n["node_id"]] = n["label"]
        # pair_map = [src_id, tgt_id] → (目标词, 源词) 与原文列序对齐
        restored = {(lab[t], lab[s]) for s, t in ref_pairs}
        assert restored == pairs, g["dir"].name


def test_n05_reference_scores_full(scan):
    """参考映射在结构模式下必须 SF=1 / SIPR=1，且分母项数与口径一致。"""
    import sys
    sys.path.insert(0, str(ROOT / "a_data"))
    import metrics
    for g in scan:
        idx = json.loads((g["dir"] / "data/input/objects/index.json")
                         .read_text(encoding="utf-8"))
        objs = {}
        for o in idx["objects"]:
            p = g["dir"] / "data/input/objects" / o["file"]
            raw = json.loads(p.read_text(encoding="utf-8"))
            objs[o["object_id"]] = dict(raw)
            objs[o["object_id"]]["_edges"] = {
                e["edge_id"]: e for e in raw.get("edges", [])}
        tgt = objs[g["man"]["object_ids"][0]]
        src = objs[g["man"]["object_ids"][1]]
        pm = g["task"]["pair_map"]
        res = metrics.score_prediction(tgt, src, {"pair_map": pm},
                                       ref_pairs=pm,
                                       ref_type_pattern=g["task"]["ref_type_pattern"])
        assert res["mode"] == "structural"
        assert res["n_checks"] == len(metrics.STRUCTURAL_CHECKS)
        assert res["sf"] == 1.0 and res["sipr"] == 1, (g["dir"].name, res["checks"])


def test_n05_wrong_mappings_cannot_score_full(scan):
    """恒等 / 循环 / 空映射都不得 SIPR=1；先断言负例真的与参考不同。"""
    import sys
    sys.path.insert(0, str(ROOT / "a_data"))
    import metrics
    tested = 0
    for g in scan:
        idx = json.loads((g["dir"] / "data/input/objects/index.json")
                         .read_text(encoding="utf-8"))
        objs = {}
        for o in idx["objects"]:
            p = g["dir"] / "data/input/objects" / o["file"]
            raw = json.loads(p.read_text(encoding="utf-8"))
            objs[o["object_id"]] = dict(raw)
            objs[o["object_id"]]["_edges"] = {
                e["edge_id"]: e for e in raw.get("edges", [])}
        tgt = objs[g["man"]["object_ids"][0]]
        src = objs[g["man"]["object_ids"][1]]
        pm = g["task"]["pair_map"]
        ref_set = {tuple(p) for p in pm}

        cyc = [[pm[i][0], pm[(i + 1) % len(pm)][1]] for i in range(len(pm))]
        cases = {"空映射": []}
        ident = [[a, a] for a, _ in pm]
        if {tuple(p) for p in ident} != ref_set:
            cases["恒等"] = ident
        if {tuple(p) for p in cyc} != ref_set:
            cases["循环"] = cyc
        for name, cand in cases.items():
            got = metrics.score_prediction(tgt, src, {"pair_map": cand},
                                           ref_pairs=pm,
                                           ref_type_pattern=g["task"]["ref_type_pattern"])
            assert got["sipr"] < 1, (g["dir"].name, name, got)
            tested += 1
    assert tested > 0


def test_n05_type_pattern_has_independent_snapshot(scan):
    """type_pattern 的基准必须是独立快照：只改候选类型时结果必须变。"""
    import sys
    sys.path.insert(0, str(ROOT / "a_data"))
    import metrics
    caught = 0
    for g in scan[:20]:
        idx = json.loads((g["dir"] / "data/input/objects/index.json")
                         .read_text(encoding="utf-8"))
        objs = {}
        for o in idx["objects"]:
            p = g["dir"] / "data/input/objects" / o["file"]
            raw = json.loads(p.read_text(encoding="utf-8"))
            objs[o["object_id"]] = dict(raw)
            objs[o["object_id"]]["_edges"] = {
                e["edge_id"]: e for e in raw.get("edges", [])}
        tgt = objs[g["man"]["object_ids"][0]]
        src = objs[g["man"]["object_ids"][1]]
        pm = g["task"]["pair_map"]
        before = g["task"]["ref_type_pattern"][0][0]
        alt = "force" if before != "force" else "entity"
        # 只改一个源节点的类型，配对完全不动
        node = next(n for n in src["nodes"] if n["node_id"] == pm[0][0])
        old_t = node["type"]
        node["type"] = alt
        got = metrics.score_prediction(tgt, src, {"pair_map": pm}, ref_pairs=pm,
                                       ref_type_pattern=g["task"]["ref_type_pattern"])
        assert got["checks"]["pair_consistency"]["passed"], "配对不该变"
        assert not got["checks"]["type_pattern"]["passed"], \
            f"{g['dir'].name} 只改节点类型却未被 type_pattern 抓到（基准跟着候选走？）"
        node["type"] = old_t
        caught += 1
    assert caught == len(scan[:20])


# ---------------- N06 派生与来源 ----------------
def test_n06_adaptation_keeps_raw_without_internal_pollution(scan, rows):
    """raw 必须逐字等于原文；split 之类内部字段不许混进 raw（SCAR 踩过）。"""
    for g in scan:
        idxs = g["ad"]["raw"]["row_indices"]
        assert g["ad"]["raw"]["rows"] == [dict(rows[i]) for i in idxs]
        blob = json.dumps(g["ad"], ensure_ascii=False)
        assert "_split" not in blob
        assert "mapping_group_id" in g["ad"]
        assert g["ad"]["mapping_group_id"] == g["man"]["group_id"]


def test_n06_no_invented_fields(scan):
    """SCAN 原文没有 Explanation / background / domain，必须如实留空。

    注意：不检查「domains 字段是否为 null」——schema 里根本没有这个字段，
    初版自造过它，现已删除。这里只管原文缺失的内容确实没被代写。
    """
    for g in scan:
        assert g["ad"]["explanation"] == []
        assert g["ad"]["background"] == {"source": "", "target": ""}
        # 不写 domain：原文无该字段，字段本身也不该出现在记录里
        assert "domains" not in g["ad"], "SCAN 无 domain 字段，不得自造"
        assert g["task"]["ref_roles"] == {}, "SCAN 无角色表述，不得凭空标注"


def test_n06_alternatives_are_not_relation_evidence(scan):
    """alternatives 是额外候选词，不得进公开输入，也不得当作等价完整映射。"""
    n_alt = 0
    for g in scan:
        assert g["task"]["mapping_forms"]["alt_complete_mappings"] == []
        if g["ad"]["alternatives"]:
            n_alt += 1
            idx = json.loads((g["dir"] / "data/input/objects/index.json")
                             .read_text(encoding="utf-8"))
            for o in idx["objects"]:
                obj = json.loads((g["dir"] / "data/input/objects" / o["file"])
                                 .read_text(encoding="utf-8"))
                assert "alternatives" not in obj
    # 原文只有 66 行带 alternatives，聚合到组级应远少于 65 组
    assert 0 < n_alt < 65


# ---------------- N07 结构标注 ----------------
def test_n07_labels_conform_to_vocab(scan):
    """relation_type / edge_type / role / node.type 全都要在词表里。"""
    vocab = json.loads((ROOT / "T01-vocabulary.json").read_text(encoding="utf-8"))
    tau_v = {t["type_id"] for t in vocab["node_types"]}
    tau_e = {e["edge_type_id"] for e in vocab["edge_types"]}
    role_ids = {r["role_id"] for e in vocab["edge_types"]
                for r in e.get("roles", [])}
    for g in scan:
        idx = json.loads((g["dir"] / "data/input/objects/index.json")
                         .read_text(encoding="utf-8"))
        for o in idx["objects"]:
            obj = json.loads((g["dir"] / "data/input/objects" / o["file"])
                             .read_text(encoding="utf-8"))
            assert obj["object_kind"] == "structural"
            assert obj["relation_type"] in tau_e, obj["relation_type"]
            assert obj["split"] in ("dev", "train", "val", "test")
            assert set(obj["provenance"]) == {"dataset", "original_id",
                                              "structure_source"}
            assert obj["provenance"]["dataset"] == "scan"
            for n in obj["nodes"]:
                assert set(n) == {"node_id", "label", "type"}
                assert n["type"] in tau_v
            for e in obj["edges"]:
                assert e["edge_type"] in tau_e
                for r in e["roles"].values():
                    assert r in role_ids, r


def test_n07_hub_matches_shared_endpoints(scan):
    """hub 是客观判据：被多个另一域概念对应的端点是 hub，其余为 correlate。"""
    for g in scan:
        fm = g["ad"]["faithful_mappings"]
        sc = Counter(strip_w(b) for _, b in fm)
        tc = Counter(strip_w(a) for a, _ in fm)
        idx = json.loads((g["dir"] / "data/input/objects/index.json")
                         .read_text(encoding="utf-8"))
        for o in idx["objects"]:
            obj = json.loads((g["dir"] / "data/input/objects" / o["file"])
                             .read_text(encoding="utf-8"))
            side_src = obj["object_id"].endswith("_src")
            cnt = sc if side_src else tc
            for n in obj["nodes"]:
                want = "hub" if cnt[n["label"]] > 1 else "correlate"
                assert obj["edges"][0]["roles"][n["node_id"]] == want, \
                    (g["dir"].name, n["label"], want)


# ---------------- N08 划分 ----------------
def test_n08_split_ratio_and_no_leak_across_blocks(scan):
    """70/15/15 ±0.03，且同一 target/source 的派生组不得跨划分（防泄漏）。"""
    cnt = Counter(g["man"]["split"] for g in scan)
    total = sum(cnt.values())
    for k, want in (("train", 0.70), ("val", 0.15), ("test", 0.15)):
        assert abs(cnt[k] / total - want) <= 0.03, (k, cnt[k] / total)
    sys_split = {}
    for g in scan:
        for key in ("target", "source"):
            name = " ".join(g["ad"]["system"][key].lower().split())
            sys_split.setdefault(key + ":" + name, set()).add(g["man"]["split"])
    cross = {k: v for k, v in sys_split.items() if len(v) > 1}
    assert cross == {}, cross


def test_n08_object_split_agrees_with_manifest(scan):
    """对象的 split 必须与组 manifest 一致（SCAR 曾整库写成 None）。"""
    for g in scan:
        idx = json.loads((g["dir"] / "data/input/objects/index.json")
                         .read_text(encoding="utf-8"))
        for o in idx["objects"]:
            obj = json.loads((g["dir"] / "data/input/objects" / o["file"])
                             .read_text(encoding="utf-8"))
            assert obj["split"] == g["man"]["split"], g["dir"].name


# ---------------- 退化与口径 ----------------
def test_n_many_to_one_direction_not_flipped(scan):
    """many_to_one / one_to_many 方向（最容易标反的一处）。

    faithful_mappings 每项 [targ_word, src_word]：
      源列重复 ⇒ 多个源概念共享同一目标 ⇒ many_to_one
      目标列重复 ⇒ 同一源对应多个目标 ⇒ one_to_many
    """
    for g in scan:
        fm = g["ad"]["faithful_mappings"]
        src_dup = len(fm) > len({strip_w(b) for _, b in fm})
        tgt_dup = len(fm) > len({strip_w(a) for a, _ in fm})
        want = ("both" if src_dup and tgt_dup else
                "many_to_one" if src_dup else
                "one_to_many" if tgt_dup else "none")
        assert g["task"]["multiple_mapping_type"] == want, \
            (g["dir"].name, g["task"]["multiple_mapping_type"], want)


def test_n_no_answer_fields_in_public_input(scan):
    """公开侧不得出现答案字段（映射/对/标签），但必须出现概念原词。"""
    for g in scan:
        def keys_of(v):
            if isinstance(v, dict):
                for k, x in v.items():
                    yield k
                    yield from keys_of(x)
            elif isinstance(v, list):
                for x in v:
                    yield from keys_of(x)
        man = g["man"]
        idx = json.loads((g["dir"] / "data/input/objects/index.json")
                         .read_text(encoding="utf-8"))
        objs = [json.loads((g["dir"] / "data/input/objects" / o["file"])
                           .read_text(encoding="utf-8")) for o in idx["objects"]]
        tasks = [json.loads(p.read_text(encoding="utf-8"))
                 for p in (g["dir"] / "data/input/tasks").glob("*.json")]
        present = set(keys_of([man] + objs + tasks))
        for leak in ("node_map", "pair_map", "valid_mappings",
                     "faithful_mappings", "raw_rows"):
            assert leak not in present, (g["dir"].name, leak)
        assert g["man"]["task_counts"]["positive"] == 1


# ---------------- 规范符合性（2026-11-02 复核新增）----------------
def test_schema_required_fields_present(scan):
    """adaptation / object 的 schema 必填字段必须齐全。

    这条是补盲区：初版 adaptation.json 漏了必填的 available_checks，
    而当时的 A/B 组验收一条都不查字段契约，靠人工对 schema 才发现。
    """
    schema = json.loads((ROOT / "T01-schema.json").read_text(encoding="utf-8"))
    ad_req = [k for k, v in schema["records"]["adaptation"]["fields"].items()
              if v.get("required") is True]
    obj_req = [k for k, v in schema["records"]["object"]["fields"].items()
               if v.get("required") is True]
    for g in scan:
        for k in ad_req:
            assert k in g["ad"], f"{g['dir'].name} adaptation 缺必填 {k}"
        idx = json.loads((g["dir"] / "data/input/objects/index.json")
                         .read_text(encoding="utf-8"))
        for o in idx["objects"]:
            ob = json.loads((g["dir"] / "data/input/objects" / o["file"])
                            .read_text(encoding="utf-8"))
            for k in obj_req:
                assert k in ob, f"{g['dir'].name}/{o['file']} object 缺必填 {k}"


def test_available_checks_in_enum_and_consistent(scan):
    """available_checks 取值 ∈ metrics.CHECK_GROUPS，且与实际判据一致。

    schema 要求这个字段声明「该组有原始依据可核验的检查项类别」，
    评价器按它决定分母；声明与实际判据不符就是又一个「声明字段无读取方」。
    """
    import sys
    sys.path.insert(0, str(ROOT / "a_data"))
    import metrics
    for g in scan:
        ac = g["ad"]["available_checks"]
        assert ac, f"{g['dir'].name} available_checks 为空"
        unknown = set(ac) - set(metrics.CHECK_GROUPS)
        assert not unknown, (g["dir"].name, unknown)
        assert list(ac) == list(g["task"]["structural_checks"]), \
            (g["dir"].name, ac, g["task"]["structural_checks"])
        # SCAN 无角色表述，因此不得声明 role
        if g["task"].get("ref_roles") == {}:
            assert "role" not in ac, g["dir"].name


def test_no_undeclared_custom_fields(scan):
    """schema 外的字段只允许与 SCAR 同类记录一致的那几个补充字段。

    初版自造过 raw_rows / derived_from / systems 三个名字，
    会让 B/C 解析器在两个结构数据集之间分叉。
    """
    schema = json.loads((ROOT / "T01-schema.json").read_text(encoding="utf-8"))
    declared = set(schema["records"]["adaptation"]["fields"])
    allowed_extra = {"node_type_source", "structural_checks", "system", "domains",
                     "note", "analogue_type", "alternatives", "mapping_group_id"}
    for g in scan:
        extra = set(g["ad"]) - declared - allowed_extra
        assert not extra, (g["dir"].name, sorted(extra))


def test_check_count_matches_declared_not_more(scan):
    """evaluate_self 算出的检查项数必须等于声明项数，不得凭空多出一项。

    锁定的 bug（2026-11-02 实跑抓出）：evaluate_self 里写
    `ref.get("ref_roles") or {从候选对象读角色}`，空 dict 是假值 ⇒ 回退到读候选，
    等于拿候选给自己打分。SCAN 的 ref_roles 全为空，65 组因此都多算了
    role_consistency 一项（声明 2 项、实算 3 项）。与 type_pattern 的自比 bug 同类。
    """
    import sys
    sys.path.insert(0, str(ROOT / "a_data"))
    import metrics
    for g in scan:
        assert g["task"]["ref_roles"] == {}
        assert len(g["task"]["structural_checks"]) == 2
        idx = json.loads((g["dir"] / "data/input/objects/index.json")
                         .read_text(encoding="utf-8"))
        objs = {}
        for o in idx["objects"]:
            raw = json.loads((g["dir"] / "data/input/objects" / o["file"])
                             .read_text(encoding="utf-8"))
            objs[o["object_id"]] = raw
        tgt = objs[g["man"]["object_ids"][0]]
        src = objs[g["man"]["object_ids"][1]]
        pm = g["task"]["pair_map"]
        # ref_roles 为空时必须传 None，而不是回退去读候选
        res = metrics.score_prediction(
            tgt, src, {"pair_map": pm}, ref_pairs=pm,
            ref_type_pattern=g["task"]["ref_type_pattern"], ref_roles=None)
        assert res["n_checks"] == 2, (g["dir"].name, res["n_checks"])
        assert "role_consistency" not in res["checks"]
