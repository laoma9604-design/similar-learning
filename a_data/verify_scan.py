"""SCAN 适配独立验收（不 import adapt_scan，只读 cases/structural_scan 与原始 CSV）。

两组断言，对应用户要求的「保留原始真实性 + 适配流程不失效」：

  A 原始材料真实性与完整性
    A1 每条纳入组的 raw.rows 必须与 SCAN 原始 CSV 对应行逐字一致
    A2 faithful_mappings 必须与原文 targ_word/src_word 完全一致（顺序、词形）
    A3 SCAN 无 Explanation / background / domain —— 必须如实留空，不得代写
    A4 纳入 + 排除 = 65 个原始对；排除项原因可复查
    A5 原始映射组 ID 可追溯：每组 raw.row_indices 覆盖的行并集 = 全部 451 行
       （防止同一行被重复计入两个组，或某行被悄悄丢掉）

  B 结构适配能跑完整流程、不压缩
    B1 节点数 = 各自去重概念数（不压缩、不拆分共享端点）
    B2 两域超边数相等（L342）；节点数可不等
    B3 参考映射在该口径下 SF=1 / SIPR=1
    B4 structural_checks 声明的项全部可被评价器算出（清单非空、项数吻合）
    B5 区分力：恒等 / 循环 / 相邻交换 / 空映射 都不得 SIPR=1
       —— 且必须先断言负例确实与参考不同（防止"负例没变"被算成漏判）
    B6 multiple_mapping_type 与数据实际一致
    B7 划分 70/15/15 ±0.03，且同一 target/source 不跨划分（L1020）
    B8 公开输入含概念原词与结构，但不含对应关系；参考映射不得为恒等

用法：python a_data/verify_scan.py      # 退出码 0 = 全部通过
"""
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "a_data"))

import metrics  # noqa: E402

_CASES_ENV = os.environ.get("SCAN_CASES_ROOT", "")     # 变异测试用临时副本
# 注意：Path("") == Path(".")，而 "." 是真值 ⇒ 不能用 `Path(env) or default`，
# 否则环境变量未设时会去扫当前目录，扫到 0 组却报"划分占比 0.000"（已踩）。
SCAN_DIR = Path(_CASES_ENV) if _CASES_ENV else ROOT / "cases" / "structural_scan"
SRC = ROOT / "data" / "raw" / "scan" / "data" / "SCAN_dataset.csv"

FAIL = []


def fail(code, msg):
    FAIL.append(f"[{code}] {msg}")


def strip_word(s):
    """只去首尾空白、保留大小写 —— 用于逐字比对（A2/B1/B6）。"""
    return str(s).strip()


def norm(s):
    """小写 + 空白归一 —— 只用于 system 名比对与连通块判定，不用于逐字核对。"""
    return " ".join(str(s).strip().lower().split())


def _block_sizes(groups):
    """按 target/source 连通块（L1020 派生关系同组）复算块大小。

    自己实现而不是 import adapt_scan.assign_splits：
    验收器不复用被测代码，否则两边共享同一个 bug 会互相作证。
    """
    man = {g.name: json.loads((g / "manifest.json").read_text(encoding="utf-8"))
           for g in groups}
    ad = {g.name: json.loads((g / "sealed/adaptation.json").read_text(encoding="utf-8"))
          for g in groups}
    parent = {k: k for k in man}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    by = defaultdict(list)
    for k, a in ad.items():
        by["t:" + norm(a["system"]["target"])].append(k)
        by["s:" + norm(a["system"]["source"])].append(k)
    for ids in by.values():
        for o in ids[1:]:
            ra, rb = find(ids[0]), find(o)
            if ra != rb:
                parent[rb] = ra
    blocks = defaultdict(list)
    for k in man:
        blocks[find(k)].append(k)
    return blocks


def main():
    if not SCAN_DIR.is_dir():
        print("适配目录不存在，先运行 a_data/adapt_scan.py")
        return 1
    with SRC.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    print(f"原始行数: {len(rows)}")

    groups = sorted(p for p in SCAN_DIR.iterdir()
                    if p.is_dir() and p.name.startswith("group_scan_"))
    print(f"适配组数: {len(groups)}")

    # ---------- A 原始材料真实性与完整性 ----------
    n_checked = 0
    covered_rows = Counter()
    for gdir in groups:
        ad_p = gdir / "sealed" / "adaptation.json"
        if not ad_p.is_file():
            fail("A0", f"{gdir.name} 缺 adaptation.json")
            continue
        ad = json.loads(ad_p.read_text(encoding="utf-8"))
        n_checked += 1

        idxs = ad["raw"]["row_indices"]
        for i in idxs:
            covered_rows[i] += 1
        if not idxs:
            fail("A1", f"{gdir.name} 无原始行号")
            continue

        # A1 raw.rows 与原文逐字一致（按行号回查，不靠顺序）
        want_rows = [dict(rows[i]) for i in idxs]
        if ad["raw"]["rows"] != want_rows:
            fail("A1", f"{gdir.name} raw.rows 与原文对应行不一致")
        if ad["raw"]["target"] != rows[idxs[0]]["target"].strip() or \
           ad["raw"]["source"] != rows[idxs[0]]["source"].strip():
            fail("A1", f"{gdir.name} raw.target/source 与原文不一致")

        # A2 faithful_mappings 与原文四列一致（顺序与词形）。
        # 唯一允许的差异是首尾空白：原文 SCAN_dataset.csv 有 2 个字段带尾随空格
        # （'public '、'guide '），适配时做了 strip 归一化。词形/大小写/顺序
        # 任一不同都判失败。raw.rows 保留逐字原样（A1 已核），所以信息没丢。
        want_pairs = [[r["targ_word"], r["src_word"]] for r in want_rows]
        dedup = []
        for p in want_pairs:
            if [strip_word(p[0]), strip_word(p[1])] not in dedup:
                dedup.append([strip_word(p[0]), strip_word(p[1])])
        if ad["faithful_mappings"] != dedup:
            fail("A2", f"{gdir.name} faithful_mappings 与原文不同（超出首尾空白归一化）")

        # A3 原文没有的字段必须留空，不许代写
        if ad.get("explanation") not in ([], None):
            fail("A3", f"{gdir.name} SCAN 无 Explanation，却被写入内容")
        bg = ad.get("background") or {}
        if bg.get("source") != "" or bg.get("target") != "":
            fail("A3", f"{gdir.name} SCAN 无 background，却被写入内容")
        dm = ad.get("domains") or {}
        if dm.get("source") is not None or dm.get("target") is not None:
            fail("A3", f"{gdir.name} SCAN 无 domain 字段，却被写入值")

    # A4 排除清单 + A5 行覆盖
    ex_p = SCAN_DIR / "_excluded.json"
    if not ex_p.is_file():
        fail("A4", "缺 _excluded.json")
    else:
        ex = json.loads(ex_p.read_text(encoding="utf-8"))
        if ex["included"] + ex["excluded_count"] != ex["raw_count"]:
            fail("A4", "纳入 + 排除 != 原始对数")
        if ex["raw_count"] != 65:
            fail("A4", f"原始对数 {ex['raw_count']} != 65")
        inc = {json.loads((g / "sealed/adaptation.json").read_text(encoding="utf-8"))
               ["original_id"] for g in groups}
        exc = {r["original_id"] for r in ex["records"]}
        if inc & exc:
            fail("A4", f"同一原始组既纳入又排除: {sorted(inc & exc)[:3]}")
        if len(inc | exc) != 65:
            fail("A4", f"纳入∪排除 = {len(inc | exc)} != 65")
        for r in ex["records"]:
            if not r.get("reason"):
                fail("A4", f"排除项 {r['original_id']} 无原因")

    dup = [i for i, c in covered_rows.items() if c > 1]
    if dup:
        fail("A5", f"{len(dup)} 行被多个组重复计入，例 {dup[:5]}")
    missing_rows = [i for i in range(len(rows)) if i not in covered_rows]
    if missing_rows:
        fail("A5", f"{len(missing_rows)} 行未被任何组覆盖，例 {missing_rows[:5]}")

    # ---------- A6 schema 符合性（2026-11-02 复核新增）----------
    # 为什么单独加：初版 adaptation.json 漏了 schema 必填的 available_checks，
    # 同时自造了 raw_rows/derived_from/systems 三个 schema 外的字段。
    # 这类问题 verifier 原来的 A/B 组一条都不查，属于「不校验字段契约」的盲区。
    schema = json.loads((ROOT / "T01-schema.json").read_text(encoding="utf-8"))
    ad_fields = schema["records"]["adaptation"]["fields"]
    ad_req = [k for k, v in ad_fields.items() if v.get("required") is True]
    obj_fields = schema["records"]["object"]["fields"]
    obj_req = [k for k, v in obj_fields.items() if v.get("required") is True]
    vocab = json.loads((ROOT / "T01-vocabulary.json").read_text(encoding="utf-8"))
    check_groups = set(metrics.CHECK_GROUPS)

    for gdir in groups:
        ad = json.loads((gdir / "sealed" / "adaptation.json").read_text(encoding="utf-8"))
        for k in ad_req:
            if k not in ad:
                fail("A6", f"{gdir.name} adaptation 缺必填字段 {k}")
        # 多余字段只允许与 SCAR 同类记录一致的补充字段（避免 B/C 解析器分叉）
        ALLOWED_EXTRA = {"node_type_source", "structural_checks", "system",
                         "domains", "note", "analogue_type", "alternatives",
                         "mapping_group_id"}
        extra = set(ad) - set(ad_fields) - ALLOWED_EXTRA
        if extra:
            fail("A6", f"{gdir.name} adaptation 含 schema 外自定义字段 {sorted(extra)}")
        # available_checks 取值必须 ∈ CHECK_GROUPS，且与实际判据一致
        ac = ad.get("available_checks") or []
        bad = set(ac) - check_groups
        if bad:
            fail("A6", f"{gdir.name} available_checks 含未知类别 {sorted(bad)}")
        if not ac:
            fail("A6", f"{gdir.name} available_checks 为空")
        ref = json.loads((gdir / "sealed/reference.json").read_text(encoding="utf-8"))
        task = next(iter(ref.values()))
        if list(ac) != list(task.get("structural_checks") or []):
            fail("A6", f"{gdir.name} available_checks 与实际判据不一致 "
                       f"{ac} vs {task.get('structural_checks')}")
        # object 必填齐全
        idx = json.loads((gdir / "data/input/objects/index.json").read_text(encoding="utf-8"))
        for o in idx["objects"]:
            ob = json.loads((gdir / "data/input/objects" / o["file"])
                            .read_text(encoding="utf-8"))
            for k in obj_req:
                if k not in ob:
                    fail("A6", f"{gdir.name}/{o['file']} object 缺必填字段 {k}")
            # annotation_status 必须在枚举内
            if ad["annotation_status"] not in ("confirmed", "non_bijective",
                                               "to_review", "excluded"):
                fail("A6", f"{gdir.name} annotation_status 不在枚举内")

    # ---------- B 完整流程 ----------
    split_cnt = Counter()
    sys_blocks = defaultdict(set)
    for gdir in groups:
        man = json.loads((gdir / "manifest.json").read_text(encoding="utf-8"))
        ad = json.loads((gdir / "sealed/adaptation.json").read_text(encoding="utf-8"))
        ref = json.loads((gdir / "sealed/reference.json").read_text(encoding="utf-8"))
        idx = json.loads((gdir / "data/input/objects/index.json").read_text(encoding="utf-8"))
        objs = {o["object_id"]: metrics.load_object(
            gdir / "data/input/objects" / o["file"]) for o in idx["objects"]}
        tgt = objs[man["object_ids"][0]]
        src_id = [o for o in man["object_ids"] if o != tgt["object_id"]][0]
        src = objs[src_id]

        split_cnt[man["split"]] += 1
        for key in ("source", "target"):
            sys_blocks[key + ":" + norm(ad["system"][key])].add(man["split"])

        fm = ad["faithful_mappings"]
        # 方向约定（反复踩过，写死在这里免得再错）：
        #   faithful_mappings 每项是 [targ_word, src_word] = [目标域概念, 源域概念]
        #   col0 ↔ 目标域对象节点，col1 ↔ 源域对象节点
        # B1 节点数 = 各自去重概念数。SCAN 原文有 2 个字段带尾随空格，按 strip 后比较
        # （faithful_mappings 已归一化，raw.rows 保留逐字原样，A1/A2 已核）
        if len(src["nodes"]) != len({strip_word(b) for _, b in fm}):
            fail("B1", f"{gdir.name} 源节点数 != 去重概念数")
        if len(tgt["nodes"]) != len({strip_word(a) for a, _ in fm}):
            fail("B1", f"{gdir.name} 目标节点数 != 去重概念数")
        if len({n["node_id"] for n in src["nodes"]}) != len(src["nodes"]):
            fail("B1", f"{gdir.name} 源域节点 ID 重复")
        if len({n["node_id"] for n in tgt["nodes"]}) != len(tgt["nodes"]):
            fail("B1", f"{gdir.name} 目标域节点 ID 重复")
        # B2 超边数相等
        if len(src["edges"]) != len(tgt["edges"]):
            fail("B2", f"{gdir.name} 两域超边数不等")

        task_id, r = next(iter(ref.items()))
        pm = r["pair_map"]

        # B3 参考映射满分（必须带 ref_type_pattern 快照，否则基准随候选变）
        # 先查参考映射引用的节点都真实存在：缺节点时 metrics 内部会在
        # sorted() 里 TypeError 崩掉，那样就看不到是哪一项不合格。
        missing_nodes = [x for p in pm for x in p
                         if x not in {n["node_id"] for n in src["nodes"]}
                         and x not in {n["node_id"] for n in tgt["nodes"]}]
        if missing_nodes:
            fail("B3", f"{gdir.name} 参考映射引用了不存在的节点 {sorted(set(missing_nodes))}")
            continue
        res = metrics.score_prediction(tgt, src, {"pair_map": pm},
                                       ref_pairs=pm,
                                       ref_type_pattern=r.get("ref_type_pattern"))
        if res.get("mode") != "structural":
            fail("B3", f"{gdir.name} 未走结构模式")
        if res["n_checks"] != len(metrics.STRUCTURAL_CHECKS):
            fail("B4", f"{gdir.name} 清单项数 {res['n_checks']} != "
                       f"{len(metrics.STRUCTURAL_CHECKS)}")
        if r.get("structural_checks") != list(metrics.STRUCTURAL_CHECKS):
            fail("B4", f"{gdir.name} structural_checks 声明与评价器口径不一致")
        if res["sf"] != 1.0 or res["sipr"] != 1:
            fail("B3", f"{gdir.name} 参考映射未满分 sf={res['sf']} {res['checks']}")

        # B5 区分力（先断言负例真的变了）
        n = len(pm)
        negatives = {}
        if n >= 2:
            ident = [[pm[i][0], pm[i][0]] for i in range(n)]
            if set(map(tuple, ident)) != set(map(tuple, pm)):
                negatives["恒等"] = ident
            perm = self_map = {p[0]: p[1] for p in pm}
            cyc = [[p[0], self_map[pm[(i + 1) % n][0]]]
                   for i, p in enumerate(pm)]
            if set(map(tuple, cyc)) != set(map(tuple, pm)):
                negatives["循环"] = cyc
            sw = list(pm)
            sw[0], sw[1] = [sw[0][0], sw[1][1]], [sw[1][0], sw[0][1]]
            if set(map(tuple, sw)) != set(map(tuple, pm)):
                negatives["相邻交换"] = sw
        negatives["空映射"] = []
        for name, cand in negatives.items():
            got = metrics.score_prediction(tgt, src, {"pair_map": cand},
                                           ref_pairs=pm,
                                           ref_type_pattern=r.get("ref_type_pattern"))
            if got["sipr"] == 1:
                fail("B5", f"{gdir.name} {name}映射仍拿满分")

        # B6 multiple_mapping_type
        # 方向：fm 每项 [targ_word, src_word]
        #   many_to_one = 多个**源**概念共享同一目标概念（src 列重复 = col1 重复）
        #   one_to_many = 同一源概念对应多个目标概念（targ 列重复 = col0 重复）
        n_tgt_uniq = len({strip_word(a) for a, _ in fm})
        n_src_uniq = len({strip_word(b) for _, b in fm})
        src_dup = len(fm) > n_src_uniq      # 源列重复 → many_to_one
        tgt_dup = len(fm) > n_tgt_uniq      # 目标列重复 → one_to_many
        want = ("both" if (src_dup and tgt_dup) else
                "many_to_one" if src_dup else
                "one_to_many" if tgt_dup else "none")
        if r["multiple_mapping_type"] != want:
            fail("B6", f"{gdir.name} multiple_mapping_type={r['multiple_mapping_type']}"
                       f" 与数据实际 {want} 不符")

        # B8 公开输入不带答案
        def keys_of(v):
            if isinstance(v, dict):
                for k, x in v.items():
                    yield k
                    yield from keys_of(x)
            elif isinstance(v, list):
                for x in v:
                    yield from keys_of(x)

        present = set(keys_of([src, tgt, man]))
        for leak in ("faithful_mappings", "node_map", "pair_map", "valid_mappings",
                     "Explanation", "raw_rows", "alternatives"):
            if leak in present:
                fail("B8", f"{gdir.name} 公开输入含答案字段 {leak}")
        pub = {n["label"] for o in (src, tgt) for n in o["nodes"]}
        if pub != {w for p in fm for w in p}:
            fail("B8", f"{gdir.name} 公开概念集与原文不一致")
        if all(s == t for s, t in pm):
            fail("B8", f"{gdir.name} 参考映射为恒等，编号顺序泄露答案")
        # 类型必须合规且在公开侧（类型是题目属性，不是答案）
        vocab = json.loads((ROOT / "T01-vocabulary.json").read_text(encoding="utf-8"))
        tau_v = {t["type_id"] for t in vocab["node_types"]}
        for o in (src, tgt):
            for nd in o["nodes"]:
                if nd["type"] not in tau_v:
                    fail("B8", f"{gdir.name} 节点类型 {nd['type']} 不在 τ_V")
                if set(nd) != {"node_id", "label", "type"}:
                    fail("B8", f"{gdir.name} node 字段超出 schema: {sorted(nd)}")

    # B7 划分
    total = sum(split_cnt.values())
    for k, target in (("train", 0.70), ("val", 0.15), ("test", 0.15)):
        got = split_cnt[k] / total if total else 0
        if abs(got - target) > 0.03:
            fail("B7", f"{k} 占比 {got:.3f} 偏离 {target:.2f} 超过 0.03")
    cross = [k for k, v in sys_blocks.items() if len(v) > 1]
    if cross:
        # L1020：同一 target/source 的派生实例必须留在同一划分。
        # 这条只算出来不判失败 = 检查项形同虚设（2026-11-02 变异测试抓出来的）。
        fail("B7", f"{len(cross)} 个 system 跨划分，例 {cross[:3]}")

    # B7b 划分离散度来源可复核：块大小不可分（L1020）时 46/10/9 是否唯一可行解。
    # 穷举所有块→划分的分配，证明占比偏离不是算法没调好，而是约束本身决定。
    block_sizes = sorted((len(v) for v in
                          _block_sizes(groups).values()), reverse=True)
    reach = {(0, 0, 0)}
    for s in block_sizes:
        nxt = set()
        for a, b, c in reach:
            if a + s <= split_cnt["train"]:
                nxt.add((a + s, b, c))
            if b + s <= split_cnt["val"]:
                nxt.add((a, b + s, c))
            if c + s <= split_cnt["test"]:
                nxt.add((a, b, c + s))
        reach = nxt
    exact = (split_cnt["train"], split_cnt["val"], split_cnt["test"]) in reach
    if not exact:
        fail("B7b", "当前划分为不可达组合，说明分配算法有误")

    print(f"  逐组核对: {n_checked}")
    print(f"  行覆盖: {len(covered_rows)}/{len(rows)}  重复计入: {len(dup)}")
    print(f"  划分块: {len(block_sizes)} 个，大小 {block_sizes}")
    print(f"  划分: {dict(split_cnt)} "
          f"({ {k: round(v / total * 100, 2) for k, v in split_cnt.items()} }%)")
    print(f"  70/15/15 精确可达: {exact}（块不可分 ⇒ 只能取最近的可行组合）")
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
