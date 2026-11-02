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
    """规范1：映射全部来自原文，不得引入任何按词义推断的对应。"""
    for G in scar:
        orig = raw[int(G["ad"]["original_id"])]
        want = [[str(a).strip(), str(b).strip()] for a, b in orig["mappings"]]
        assert G["ad"]["faithful_mappings"] == want, f"{G['dir'].name} 映射被改动"
        # 参考映射的节点对应关系必须与 faithful_mappings 一一吻合
        nm = G["ref"][list(G["ref"])[0]]["valid"][0]["node_map"]
        assert len(nm) == len(want)


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
    """不压缩：节点数必须等于映射对数，任何规模都不许压成固定值。"""
    sizes = Counter()
    for G in scar:
        n = len(G["ad"]["faithful_mappings"])
        sizes[n] += 1
        idx = json.loads((G["dir"] / "data/input/objects/index.json").read_text(encoding="utf-8"))
        objs = [json.loads((G["dir"] / "data/input/objects" / o["file"]).read_text(encoding="utf-8"))
                for o in idx["objects"]]
        for o in objs:
            assert len(o["nodes"]) == n, f"{G['dir'].name} 节点数 {len(o['nodes'])} != {n}"
    # 规模必须多样，不能全被压成一种
    assert len(sizes) >= 5, f"节点规模过于单一: {dict(sizes)}"


def test_s06_multiple_mapping_type_matches_data(scar):
    """规范3：多值映射类型标注必须与原始数据实际结构一致。"""
    for G in scar:
        pairs = G["ad"]["faithful_mappings"]
        la = [a.lower() for a, _ in pairs]
        lb = [b.lower() for _, b in pairs]
        dup_a = any(c > 1 for c in Counter(la).values())
        dup_b = any(c > 1 for c in Counter(lb).values())
        want = ("both" if (dup_a and dup_b) else
                "one_to_many" if dup_a else
                "many_to_one" if dup_b else "none")
        got = G["ref"][list(G["ref"])[0]]["multiple_mapping_type"]
        assert got == want, f"{G['dir'].name} 标注 {got} != 实际 {want}"
        if want != "none":
            assert G["ref"][list(G["ref"])[0]]["valid_mappings"], \
                f"{G['dir'].name} 多值映射缺 valid_mappings"


def test_available_checks_declared_and_computable(scar):
    """available_checks 声明的项必须能算出非空清单（否则 SF/SIPR 无分母）。"""
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
        res = metrics.score_prediction(
            tgt, src,
            {"node_map": r["valid"][0]["node_map"], "edge_map": r["valid"][0]["edge_map"]},
            available=r["available_checks"])
        assert res["n_checks"] > 0, f"{G['dir'].name} 检查清单为空"
        assert res["sf"] == 1.0 and res["sipr"] == 1, f"{G['dir'].name} 参考映射未满分"
        # SCAR 只有双射类依据，不得声明类型/角色/方向
        assert r["available_checks"] == ["node_bijection"]


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
    """公开输入不含忠实映射、解释原文、背景或 SCAR 原词标签。

    注意：只检查 data/input/ 下的对象与任务（方法可见部分）。
    README 里写出系统名是有意为之（便于人复核），不属于方法输入。
    """
    for G in scar:
        obj_dir = G["dir"] / "data/input/objects"
        idx = json.loads((obj_dir / "index.json").read_text(encoding="utf-8"))
        objs = [json.loads((obj_dir / o["file"]).read_text(encoding="utf-8"))
                for o in idx["objects"]]
        tasks = [json.loads(p.read_text(encoding="utf-8"))
                 for p in (G["dir"] / "data/input/tasks").glob("*.json")]
        blob = json.dumps(objs + tasks, ensure_ascii=False)

        for leak in ("faithful_mappings", "Explanation", "background",
                     "system_a", "system_b"):
            assert leak not in blob, f"{G['dir'].name} 公开输入含 {leak}"

        # 检查方法可见的**标识性字段**：对象 label、节点 label、系统名。
        # 不能扫全部字段值：SCAR 的 concept 里就有 "structure"、"participant"
        # 这类词，会撞上字段名或角色名造成误报（实测两次）。
        ident = []
        for o in objs:
            ident.append(str(o.get("label", "")))
            ident.extend(str(n.get("label", "")) for n in o.get("nodes") or [])
        vals = {s.lower() for s in ident}
        words = {w for p in G["ad"]["faithful_mappings"] for w in p}
        for k in ("source", "target"):
            words.add(" ".join(str(G["ad"]["system"][k]).lower().split()))
        for w in words:
            assert w.lower() not in vals, f"{G['dir'].name} 公开标识字段含原词 {w!r}"
        # 节点 label 必须是中性占位（"概念"），不能是任何 SCAR 原词
        for o in objs:
            for n in o.get("nodes") or []:
                assert n["label"] == "概念", f"{G['dir'].name} 节点 label 非中性占位"
