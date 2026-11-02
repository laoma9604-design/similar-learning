"""SCAR 适配回归测试（对应 S01-S07 与三条科研规范）。

每条测试锁定一个具体失败模式，防止后续修改把已修好的问题改回去。
只读 cases/structural_scar 与原始数据，不 import 适配器的内部判据。
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCAR = ROOT / "cases" / "structural_scar"
SRC = ROOT / "data" / "raw" / "scar" / "release" / "system_analogy_en.json"


@pytest.fixture(scope="module")
def scar():
    assert SCAR.is_dir(), "先运行 a_data/adapt_scar.py"
    dirs = sorted(p for p in SCAR.iterdir() if p.is_dir() and p.name.startswith("group_scar_"))
    out = []
    for d in dirs:
        out.append(dict(
            dir=d,
            man=json.loads((d / "manifest.json").read_text(encoding="utf-8")),
            ad=json.loads((d / "sealed/adaptation.json").read_text(encoding="utf-8")),
            ref=json.loads((d / "sealed/reference.json").read_text(encoding="utf-8")),
            sealed=json.loads((d / "manifest.sealed.json").read_text(encoding="utf-8")),
        ))
    return out


@pytest.fixture(scope="module")
def raw():
    return {json.loads(l)["id"]: json.loads(l)
            for l in SRC.open(encoding="utf-8") if l.strip()}


def test_s03_counts_reconcile(scar, raw):
    """S03：纳入 + 排除 = 原始数量，且排除原因按声明的规则可复查。"""
    import re
    ex = json.loads((SCAR / "_excluded.json").read_text(encoding="utf-8"))
    assert ex["raw_count"] == len(raw) == 400
    assert ex["included"] == len(scar)
    assert ex["included"] + ex["excluded_count"] == ex["raw_count"]

    RESIDUE = re.compile(r'^\s*(items?|explanation|translation|elements?|concepts?|'
                         r'mapping|answer|lists?|terms?|pairs?)\s*[:：]', re.I)
    SELFNEG = re.compile(
        r"(may not be (appropriate|correct|suitable|accurate)|"
        r"(is|isn't) not (an? )?(appropriate|valid|suitable)|"
        r"not (a )?(good|proper|valid|accurate) (mapping|correspondence|match)|"
        r"does not (really )?(correspond|match|fit)|"
        r"weak (mapping|correspondence)|questionable)", re.I)

    for r in ex["records"]:
        o = raw[int(r["original_id"])]
        assert r["reason"], f"排除项 {r['original_id']} 无原因"
        rule = r.get("rule")
        expl = o.get("Explanation") or []
        maps = o.get("mappings") or []
        # 声明的规则必须属实，不能为了排除而编规则
        if rule == "S1":
            assert len(expl) != len(maps), f"排除项 {r['original_id']} 声明 S1 但不符"
        elif rule == "S2":
            assert any(RESIDUE.match((e or "").strip()) for e in expl), \
                f"排除项 {r['original_id']} 声明 S2 但无模板残留"
        elif rule == "S3":
            assert any(SELFNEG.search(e or "") for e in expl), \
                f"排除项 {r['original_id']} 声明 S3 但无自我否定"
        elif rule == "R-manual":
            assert len(r.get("reason", "")) >= 20, \
                f"排除项 {r['original_id']} 人工判定理由过于笼统"
        else:
            pytest.fail(f"排除项 {r['original_id']} 规则未知 {rule!r}")


def test_s04_no_guessed_relations(scar, raw):
    """规范1：映射全部来自原文，节点集合由 faithful_mappings 唯一确定。"""
    for G in scar:
        orig = raw[int(G["ad"]["original_id"])]
        want = [[str(a).strip(), str(b).strip()] for a, b in orig["mappings"]]
        assert G["ad"]["faithful_mappings"] == want, f"{G['dir'].name} 映射被改动"

        # 参考映射必须完整覆盖原文的每一对（pair_map 不受 dict 键唯一性限制）
        r = G["ref"][list(G["ref"])[0]]
        pm = r["pair_map"]
        assert len(pm) == len(want), f"{G['dir'].name} pair_map 条数 {len(pm)} != 原文 {len(want)}"
        # pair_map 的节点集合必须与两域节点数吻合（共享端点不重复建节点）
        idx = json.loads((G["dir"] / "data/input/objects/index.json")
                         .read_text(encoding="utf-8"))
        objs = {o["object_id"]: json.loads((G["dir"] / "data/input/objects" / o["file"])
                                           .read_text(encoding="utf-8"))
                for o in idx["objects"]}
        # 源域 = valid 里给出的 source_id，不靠节点数大小猜
        sid = r["valid"][0]["source_id"]
        src_obj = objs[sid]
        tgt_obj = objs[[k for k in objs if k != sid][0]]
        assert len({a for a, _ in pm}) == len(src_obj["nodes"]), f"{G['dir'].name} 源节点数不符"
        assert len({b for _, b in pm}) == len(tgt_obj["nodes"]), f"{G['dir'].name} 目标节点数不符"


def test_s07_raw_preserved_verbatim(scar, raw):
    """S07：原文逐字留存，不得混入任何内部字段（曾把 _split 写进 raw）。"""
    for G in scar:
        orig = raw[int(G["ad"]["original_id"])]
        assert G["ad"]["raw"] == orig, f"{G['dir'].name} raw 与原文不一致"
        assert "_split" not in G["ad"]["raw"]
        assert G["ad"]["explanation"] == (orig.get("Explanation") or [])
        assert G["ad"]["background"]["source"] == orig.get("system_a_background", "")
        assert G["ad"]["background"]["target"] == orig.get("system_b_background", "")


def test_s05_node_count_not_compressed(scar):
    """不压缩：两域节点数 = 各自去重后的概念数；共享端点不重复建节点。"""
    sizes = Counter()
    for G in scar:
        pairs = G["ad"]["faithful_mappings"]
        n_src = len({a for a, _ in pairs})
        n_tgt = len({b for _, b in pairs})
        sizes[(n_src, n_tgt)] += 1
        idx = json.loads((G["dir"] / "data/input/objects/index.json").read_text(encoding="utf-8"))
        objs = {o["object_id"]: json.loads((G["dir"] / "data/input/objects" / o["file"])
                                           .read_text(encoding="utf-8"))
                for o in idx["objects"]}
        got = sorted(len(o["nodes"]) for o in objs.values())
        assert got == sorted([n_src, n_tgt]), \
            f"{G['dir'].name} 节点数 {got} != [{n_src}, {n_tgt}]"
    # 规模必须多样
    assert len({s[0] for s in sizes}) >= 5, f"规模过于单一: {dict(sizes)}"
    # 必须存在两域节点数不等的组（多值对应），否则说明共享端点被拆开了
    assert any(s[0] != s[1] for s in sizes), "没有任何多值结构，共享端点可能被拆成独立节点"


def test_s06_multiple_mapping_type_matches_data(scar):
    """规范3：多值类型标注必须与结构一致。

    语义（易错点，曾标反）：
      many_to_one  多个源概念对应同一个目标（目标端去重后变少）
      one_to_many  同一个源概念对应多个目标（源端去重后变少）
    """
    for G in scar:
        pairs = G["ad"]["faithful_mappings"]
        src_dup = len(pairs) > len({a for a, _ in pairs})
        tgt_dup = len(pairs) > len({b for _, b in pairs})
        want = ("both" if (src_dup and tgt_dup) else
                "many_to_one" if src_dup else
                "one_to_many" if tgt_dup else "none")
        r = G["ref"][list(G["ref"])[0]]
        assert r["multiple_mapping_type"] == want, \
            f"{G['dir'].name} 标注 {r['multiple_mapping_type']} != 实际 {want}"
        if want != "none":
            assert r["valid_mappings"], f"{G['dir'].name} 多值映射缺 valid_mappings"
            assert r["mapping_forms"]["multi_valued_in_one"] is True
        # 多个可接受的完整映射：SCAR 未提供，必须为空而不是编造
        assert r["mapping_forms"]["alt_complete_mappings"] == [], \
            f"{G['dir'].name} 不应凭空产生替代完整映射"


def test_available_checks_declared_and_computable(scar):
    """结构模式：参考映射必须满分（标注与结构自洽的机器自检）。"""
    import sys
    sys.path.insert(0, str(ROOT / "a_data"))
    import metrics

    for G in scar:
        r = G["ref"][list(G["ref"])[0]]
        idx = json.loads((G["dir"] / "data/input/objects/index.json").read_text(encoding="utf-8"))
        objs = {o["object_id"]: metrics.load_object(G["dir"] / "data/input/objects" / o["file"])
                for o in idx["objects"]}
        tgt = objs[G["man"]["object_ids"][0]]
        src = objs[[o for o in G["man"]["object_ids"] if o != tgt["object_id"]][0]]
        res = metrics.score_prediction(tgt, src, {"pair_map": r["pair_map"]},
                                       ref_pairs=r["pair_map"])
        assert res["mode"] == "structural"
        assert res["n_checks"] == len(metrics.STRUCTURAL_CHECKS)
        assert res["sf"] == 1.0 and res["sipr"] == 1, \
            f"{G['dir'].name} 参考映射未满分 SF={res['sf']} {res['checks']}"


def test_wrong_mappings_cannot_score_full(scar):
    """区分力：错误映射不得满分（评审核心问题）。

    旧版只有 node_bijection 一项，任何排列都是双射 → 循环置换也满分。
    必须保证：恒等映射、循环置换、相邻交换都不再拿满分。
    """
    import sys
    sys.path.insert(0, str(ROOT / "a_data"))
    import metrics

    leak = {"identity": 0, "cycle": 0, "swap": 0}
    for G in scar:
        r = G["ref"][list(G["ref"])[0]]
        idx = json.loads((G["dir"] / "data/input/objects/index.json").read_text(encoding="utf-8"))
        objs = {o["object_id"]: metrics.load_object(G["dir"] / "data/input/objects" / o["file"])
                for o in idx["objects"]}
        tgt = objs[G["man"]["object_ids"][0]]
        src = objs[[o for o in G["man"]["object_ids"] if o != tgt["object_id"]][0]]
        rp = r["pair_map"]

        tids = {n["node_id"] for n in tgt["nodes"]}
        ident = [[n["node_id"], n["node_id"]] for n in src["nodes"] if n["node_id"] in tids]
        if ident and metrics.score_prediction(tgt, src, {"pair_map": ident},
                                              ref_pairs=rp)["sipr"] == 1:
            leak["identity"] += 1

        cyc = [[rp[i][0], rp[(i + 1) % len(rp)][1]] for i in range(len(rp))]
        if metrics.score_prediction(tgt, src, {"pair_map": cyc}, ref_pairs=rp)["sipr"] == 1:
            leak["cycle"] += 1

        if len(rp) >= 2:
            sw = [[rp[0][0], rp[1][1]], [rp[1][0], rp[0][1]]] + rp[2:]
            if metrics.score_prediction(tgt, src, {"pair_map": sw}, ref_pairs=rp)["sipr"] == 1:
                leak["swap"] += 1

    assert leak["identity"] == 0, f"恒等映射拿满分 {leak['identity']} 组"
    assert leak["cycle"] == 0, f"循环置换拿满分 {leak['cycle']} 组"
    # 相邻交换只错了 2 对，要求绝大多数被识别（允许极少偶然重合）
    assert leak["swap"] <= 2, f"相邻交换拿满分 {leak['swap']} 组（过多）"


def test_split_ratio_and_no_system_leak(scar):
    """划分接近 70/15/15，同一 system 不跨划分。"""
    sp = Counter(G["man"]["split"] for G in scar)
    total = sum(sp.values())
    assert abs(sp["train"] / total - 0.70) <= 0.03
    assert abs(sp["val"] / total - 0.15) <= 0.03
    assert abs(sp["test"] / total - 0.15) <= 0.03

    blocks = {}
    for G in scar:
        for k in ("source", "target"):
            nm = " ".join(str(G["ad"]["system"][k]).lower().split())
            blocks.setdefault((k, nm), set()).add(G["man"]["split"])
    leak = [k for k, v in blocks.items() if len(v) > 1]
    assert not leak, f"{len(leak)} 个 system 跨划分，例 {leak[:3]}"


def test_public_input_has_no_answer(scar):
    """公开输入含概念词（任务输入），但**不含哪对哪的对应关系**（答案）。

    边界（2026-11-02 评审后修正）：
      概念原词、系统名 → 公开。这是模型推理所需输入，抹掉会让任务无法完成。
      概念对应关系、Explanation、背景 → 封存。这才是答案。
    旧版把原词也当答案隐藏，评审指出「删除了模型推理需要的概念信息」。
    """
    for G in scar:
        obj_dir = G["dir"] / "data/input/objects"
        idx = json.loads((obj_dir / "index.json").read_text(encoding="utf-8"))
        objs = [json.loads((obj_dir / o["file"]).read_text(encoding="utf-8"))
                for o in idx["objects"]]
        tasks = [json.loads(p.read_text(encoding="utf-8"))
                 for p in (G["dir"] / "data/input/tasks").glob("*.json")]
        blob = json.dumps(objs + tasks, ensure_ascii=False)

        # 答案类字段一律不得进入方法可见部分。
        # 只查字段名，不做全文匹配：SCAR 的概念里就有 "background"、结构里就有
        # "node_map" 同名词，全文匹配会误报（第三次踩同类坑）。
        def keys_of(v):
            if isinstance(v, dict):
                for k, x in v.items():
                    yield k
                    yield from keys_of(x)
            elif isinstance(v, list):
                for x in v:
                    yield from keys_of(x)

        present = set(keys_of(objs)) | set(keys_of(tasks))
        for leak in ("faithful_mappings", "Explanation", "system_a_background",
                     "system_b_background", "valid_mappings", "node_map"):
            assert leak not in present, f"{G['dir'].name} 公开输入含答案字段 {leak}"

        # 概念原词必须公开（评审要求），且与原始映射覆盖的概念集合一致
        pub_labels = {n["label"] for o in objs for n in o.get("nodes") or []}
        words = {w for p in G["ad"]["faithful_mappings"] for w in p}
        assert pub_labels == words, \
            f"{G['dir'].name} 公开概念集与原文不一致：多 {pub_labels - words}，缺 {words - pub_labels}"

        # 关键：不能通过「编号顺序」泄露对应关系
        # 参考映射若为恒等，模型输出 id 相同即满分（旧版 387/387 全是）
        pm = G["ref"][list(G["ref"])[0]]["pair_map"]
        assert not all(a == b for a, b in pm), \
            f"{G['dir'].name} 参考映射为恒等，编号顺序在泄露答案"


# ---------------------------------------------------------------------------
# 格式合规（对照 T01-schema.json 与 T01-vocabulary.json）
# ---------------------------------------------------------------------------
def test_object_fields_match_schema(scar):
    """object 字段必须严格符合 schema：必填齐全、无多余字段、枚举值合法。"""
    schema = json.loads((ROOT / "T01-schema.json").read_text(encoding="utf-8"))
    vocab = json.loads((ROOT / "T01-vocabulary.json").read_text(encoding="utf-8"))
    od = schema["records"]["object"]["fields"]
    node_types = {t["type_id"] for t in vocab["node_types"]}
    allowed_split = {"dev", "train", "val", "test"}

    for G in scar:
        obj_dir = G["dir"] / "data/input/objects"
        idx = json.loads((obj_dir / "index.json").read_text(encoding="utf-8"))
        for o in idx["objects"]:
            obj = json.loads((obj_dir / o["file"]).read_text(encoding="utf-8"))
            # 必填齐全
            for k, spec in od.items():
                if isinstance(spec, dict) and spec.get("required") is True:
                    assert k in obj, f"{G['dir'].name} 缺必填字段 {k}"
            # split 必须是枚举值（曾写成 None）
            assert obj["split"] in allowed_split, \
                f"{G['dir'].name} split={obj['split']!r} 不是合法枚举"
            assert obj["split"] == G["man"]["split"], f"{G['dir'].name} split 与组不一致"
            # object_kind 枚举
            assert obj["object_kind"] in ("mechanistic", "structural")
            # provenance 只允许 schema 规定的三项（license 等不逐对象重复）
            assert set(obj["provenance"]) == {"dataset", "original_id", "structure_source"}, \
                f"{G['dir'].name} provenance 含多余字段 {set(obj['provenance'])}"
            # node 每项只允许 {node_id,label,type}，type ∈ τ_V
            for n in obj["nodes"]:
                assert set(n) == {"node_id", "label", "type"}, \
                    f"{G['dir'].name} node 含多余字段 {set(n)}"
                assert n["type"] in node_types, f"{G['dir'].name} node.type 不在词表"


def test_type_pattern_catches_type_only_errors(scar):
    """type_pattern 的独立价值：配对完全正确、只有类型标注错时能否抓到。

    背景：实测 pair_consistency 一项就能识破全部排列类错误
    （adjacent_swap 99.5%、cycle 100%），type_pattern 在那类测试里从未起作用。
    必须单独证明它在「配对对、类型错」这类错误上有效，否则就是冗余检查项。
    """
    import sys
    sys.path.insert(0, str(ROOT / "a_data"))
    import metrics

    caught = applicable = 0
    for G in scar:
        r = G["ref"][list(G["ref"])[0]]
        idx = json.loads((G["dir"] / "data/input/objects/index.json").read_text(encoding="utf-8"))
        objs = {o["object_id"]: metrics.load_object(G["dir"] / "data/input/objects" / o["file"])
                for o in idx["objects"]}
        tgt = objs[G["man"]["object_ids"][0]]
        src = objs[[o for o in G["man"]["object_ids"] if o != tgt["object_id"]][0]]
        pm = r["pair_map"]

        rtp = r["ref_type_pattern"]
        assert metrics.score_prediction(tgt, src, {"pair_map": pm}, ref_pairs=pm,
                                        ref_type_pattern=rtp)["sipr"] == 1

        # 只改一个源节点的类型，pair_map 原样不动
        n0 = src["nodes"][0]
        orig = n0["type"]
        n0["type"] = "force" if orig != "force" else "entity"
        res = metrics.score_prediction(tgt, src, {"pair_map": pm}, ref_pairs=pm,
                                       ref_type_pattern=rtp)
        n0["type"] = orig

        applicable += 1
        # 必须由 type_pattern 抓到，且 pair_consistency 仍通过（证明是纯类型错误）
        if (res["checks"]["pair_consistency"]["passed"]
                and not res["checks"]["type_pattern"]["passed"]):
            caught += 1

    assert applicable > 0
    assert caught > 0, (
        f"type_pattern 一个都没抓到（{caught}/{applicable}）："
        "说明它与类型标注脱节或检查项失效")
    print(f"\ntype_pattern 抓到纯类型错误: {caught}/{applicable}")


def test_role_consistency_catches_role_errors(scar):
    """role_consistency 的区分力：有角色依据的节点被改角色时能否抓到。

    只对 reference 提供 ref_roles 的组启用（Explanation 明确写了
    "X is the source/channel/..."）。其余组该项不出现，不得凭空检查。
    """
    import sys
    sys.path.insert(0, str(ROOT / "a_data"))
    import metrics

    with_roles = tested = caught = 0
    for G in scar:
        r = G["ref"][list(G["ref"])[0]]
        if not r.get("ref_roles"):
            continue
        with_roles += 1
        idx = json.loads((G["dir"] / "data/input/objects/index.json").read_text(encoding="utf-8"))
        objs = {o["object_id"]: metrics.load_object(G["dir"] / "data/input/objects" / o["file"])
                for o in idx["objects"]}
        tgt = objs[G["man"]["object_ids"][0]]
        src = objs[[o for o in G["man"]["object_ids"] if o != tgt["object_id"]][0]]
        pm, rtp, rroles = r["pair_map"], r["ref_type_pattern"], r["ref_roles"]

        base = metrics.score_prediction(tgt, src, {"pair_map": pm}, ref_pairs=pm,
                                        ref_type_pattern=rtp, ref_roles=rroles)
        assert base["sipr"] == 1, f"{G['dir'].name} 参考映射未满分"
        assert "role_consistency" in base["checks"]

        # 改掉一个有依据节点的角色
        nid = next(iter(rroles))
        want = rroles[nid]
        target_obj = src if any(n["node_id"] == nid for n in src["nodes"]) else tgt
        e = target_obj["edges"][0]
        orig = e["roles"][nid]
        e["roles"][nid] = "hub" if want != "hub" else "correlate"
        res = metrics.score_prediction(tgt, src, {"pair_map": pm}, ref_pairs=pm,
                                       ref_type_pattern=rtp, ref_roles=rroles)
        e["roles"][nid] = orig

        tested += 1
        assert res["checks"]["pair_consistency"]["passed"]  # 配对没错
        if not res["checks"]["role_consistency"]["passed"]:
            caught += 1

    assert with_roles > 0, "没有任何组提供 ref_roles"
    assert caught == tested, (
        f"role_consistency 只抓到 {caught}/{tested}，角色检查项失效")
    print(f"\nrole_consistency 抓到角色错误: {caught}/{tested}（共 {with_roles} 组有角色依据）")
