# SCAN 适配规范（N07）

本规范定义 `cases/structural_scan/` 的生成口径，供 B/C 复核。
生成脚本 `a_data/adapt_scan.py`，独立验收 `a_data/verify_scan.py`，
变异测试 `a_data/mutation_test_scan.py`，回归测试 `tests/test_scan_adapt.py`。

**N 编号对照**

| 编号 | 工作 | 交付 | 落点 |
|---|---|---|---|
| N01 | 获取原始 SCAN 数据 | 原始资源 | `data/raw/scan/`（gitignore，MIT） |
| N02 | 记录数据版本 | 来源说明 | `data/SCAN数据来源说明.md`（commit/MD5/许可） |
| N03 | 提取原始映射组 ID | 原始映射索引 | `_mapping_index.json`（65 组 ↔ 行号） |
| N04 | 识别映射中的概念 | 节点数据 | 对象 `nodes`（label = 概念原词） |
| N05 | 梳理映射关系 | 参考映射 | `sealed/reference.json` 的 `pair_map` |
| N06 | 记录派生实例与来源 | 派生关系记录 | `sealed/adaptation.json` 的 `raw` / `derived_from` |
| N07 | 统一结构标注 | 对象文件 | `data/input/objects/*.json` |
| N08 | 划分训练/验证/测试 | 分组清单 | `manifest.json` 的 `split` |

---

## 1. 一个原始映射组 = 一个 (target, source) 对，不是一个 CSV 行

这是 SCAN 与 SCAR 最大的结构差异，也是**最容易做错的一步**。

SCAN 的 451 行不是 451 个类比，而是 65 个对内部的词对列表；
同一个对里的行是**同义词拆分**，例如：

```
('life', 'theatre'):
    world    <- stage
    society  <- stage      ← 同一个源词 stage
    people   <- actors
    person   <- actor
    ...
```

若按行建组，`present ↔ stage` 和 `society ↔ stage` 会变成两个独立样本，
而它们其实是**同一次类比里共享端点 `stage` 的两条对应**。

**口径**：以 `(target, source)` 为组键，按原文首次出现顺序编号
`group_scan_0001..0065`。组 ID 与原始行号的对应关系写在 `_mapping_index.json`，
一行只能属于一个组（`verify_scan.py` A5 逐行核对，451 行全部覆盖、0 重复）。

---

## 2. 纳入与排除

判定顺序固定（顺序变了统计会漂移）：

```
空端点 → 映射对 < 2 → 去重后映射对 < 2 → 缺 analogy_type → 纳入
```

结果：**纳入 65 / 排除 0**。

SCAN 没有 Explanation，所以 SCAR 的四条排除规则（`S1` 解释条数不符、
`S2` 模板残留、`S3` 作者自认不成立、`R-manual`）在这里**全部不适用**——
不是没检查，是这类缺陷在无解释的数据里不存在。

---

## 3. 结构对象怎么写

### 3.1 两域独立随机编号（防恒等映射）

源域用 `s1..sk`、目标域用 `t1..tk`，各自按 `sha256(group_id + 侧别)` 播种打乱。
**参考映射恰为同编号的组 = 0**（旧 SCAR 版 387/387 全是，导致输出恒等即满分）。

### 3.2 节点 label = 概念原词（这是题目，不是答案）

节点 `label` 直接填原始概念词（`nucleus`、`sun`）。
**不能**改成「概念」占位——那会让任务变成不可完成的结构谜题（SCAR 评审原话）。
被封存的只有「哪个对哪个」：`pair_map` / `node_map`。

### 3.3 共享端点只建一个节点

源词 `stage` 同时对应 `world` 和 `society` ⇒ 源域只建**一个** `stage` 节点，
`pair_map` 里出现两条指向不同目标节点的对应。
不拆成同编号双射（那会让 `multiple_mapping_type` 标注与数据自相矛盾）。

### 3.4 类型标注

节点 `type` 取自 `T01-vocabulary.json` 的 τ_V 六类，**逐词人工判定**：

- 复用 SCAR 全量词典 `a_data/scar_type_lexicon.py`（1946 词）
- SCAN 独有的 51 个词另建 `a_data/scan_type_lexicon.py`，逐词给出判定与理由
- 词典查不到的词**不静默兜底**：记进 `_MISSING_TYPES`，
  落盘到 `_type_gaps.json`。当前缺口 **0**
- 两份词典对同一个词判定不一致会直接断言失败（`_CONFLICTS`）

`node_type_source = "inferred"`：原文没有类型字段，这是按词表判别式补的标注，
必须如实标明，不能写成 `provided`。

### 3.5 超边与角色

- 每组两域各一条超边 `e1`，包含本域全部节点，`output_nodes: []`（原文无方向）
- `edge_type` / `relation_type` = `analogy_correspondence`（vocab 0.1.1 结构类）
- 角色只有两个可客观判定的值：
  - `hub` —— 本域内对应数 > 1 的端点（被多个另一域概念对应的共享端点）
  - `correlate` —— 其余
- `roles` 挂在**超边上**（`edges[0].roles`），不在节点上
- **`ref_roles = {}`**：SCAN 原文没有任何角色表述（没有 `acts as` / `is the source`
  这类句子），因此 `role_consistency` 这一项**不启用**。不许用词义推测补。

### 3.6 字段白名单（与 schema 一致）

`node` 恰为 `{node_id, label, type}`；`provenance` 恰为
`{dataset, original_id, structure_source}`（`license` 记在数据来源说明，不逐对象重复）；
`object.split ∈ {dev, train, val, test}`，由组在落盘前填入。

### 3.7 available_checks（schema 必填，决定分母）

`adaptation.available_checks` 声明「该组**有原始依据**可核验的检查项类别」，
取值必须 ∈ `metrics.CHECK_GROUPS`（不是 MRED 的六类标签，而是评价器认的八个 key）。
SCAN 的声明是：

```
available_checks = ["pair_consistency", "type_pattern"]
```

依据（逐项说明为什么含、为什么不含）：

| 类别 | 是否声明 | 理由 |
|---|---|---|
| `pair_consistency` | ✅ | 概念对应关系是原文直接给出的 |
| `type_pattern` | ✅ | 类型是 inferred，但对应关系成立时其**模式**可核 |
| `node_bijection` | ❌ | 29 组多值对应 ⇒ **实测 29/29 正确映射都判失败** |
| `edge_bijection` | ❌ | 原文无超边划分，恒 1↔1，无区分力 |
| `node_type` | ❌ | 要求两端同类型；跨范畴对应是类比机制本身，会误伤正确答案 |
| `edge_type` | ❌ | 原文无超边类型 |
| `input_output_set` | ❌ | 原文无方向 |
| `role` | ❌ | 原文无任何角色表述（`ref_roles = {}`） |

评价器只把这些类别计入分母，未列出的不判失败、直接不进分母
（依据 L1034「清单由完整参考结构确定」）。**禁止为凑满清单把缺失标注推断成 provided。**

**实测证据（2026-11-02，65 组全量）**：如果硬套机械模式（只开 `node_bijection` +
`node_type`），**正确映射只有 8/65 拿满分**；29 个多值组 **29/29 全部失败**。
这不是数据错，是判据不适用——多值对应必然违反双射，跨范畴对应必然违反"两端同类型"。
所以 SCAN 必须走结构模式，`available_checks` 也只能声明那两项。

---

## 4. 参考映射与有效映射集合

### 4.1 两种列序，故意相反（最容易读错）

```
faithful_mappings  每项 = [targ_word, src_word]       ← 照抄 CSV 列序
pair_map           每项 = [源域节点ID, 目标域节点ID]  ← 照抄铁律 source→target
```

把 `pair_map` 还原成概念对时必须是 `(label[目标], label[源])`，
弄反会让整组对应镜像翻转，而 `pair_consistency` 照样给满分（因为它是对称比较集合）。
`tests/test_scan_adapt.py::test_n05_reference_pairmap_matches_original` 锁定这条。

### 4.2 多值类型的方向定义

| 值 | 判据（`fm` = `faithful_mappings`） |
|---|---|
| `many_to_one` | 源列重复：多个源概念共享同一目标概念 |
| `one_to_many` | 目标列重复：同一源概念对应多个目标概念 |
| `both` | 两列都重复 |
| `none` | 都不重复（36 组） |

实测分布：none 36 / many_to_one 27 / one_to_many 1 / both 1。

### 4.3 alternatives 不是关系依据

`alternatives` 字段（34 组有值）是「另一个候选源词」，原文**没有**给出该词与
目标概念的对应关系。因此：

- 存进 `sealed/reference.json` 的 `alternatives_provided` 供复核
- `mapping_forms.alt_complete_mappings` **保持为空**，不能把 alternatives 当作等价完整映射
- **不进公开输入**（否则等于把答案的候选集递给方法）

---

## 5. 结构模式判据（与机械六类的区别）

SCAN 与 SCAR 一样没有响应函数，走结构模式，`structural_checks` 两项：

| 检查项 | 含义 |
|---|---|
| `pair_consistency` | 候选的概念对应集合与参考一致（顺序无关，含多值端点） |
| `type_pattern` | 类型**对应模式**一致（参考是 `entity→abstract`，候选也必须），不要求两端同类型 |

不用机械六类的原因（SCAR 已实测，SCAN 同理）：

- `node_bijection`：SCAN 有 29 组多值对应，双射必然失败，与真实结构矛盾
- `node_type`（要求两端同类型）：类比的核心机制就是跨范畴对应，会系统性误伤

`ref_type_pattern` **快照**存进 `reference.json` 作为 `type_pattern` 的独立基准。
不存的话基准会跟着候选变，永远相等——SCAR 实测该 bug 让 378/378 的纯类型错误全部漏判。

`n_checks = 2`，与 MRED 的 11/9 项口径**不同**，跨数据集比较必须注明。

---

## 6. 划分（N08）：派生实例必须同组

### 6.1 规则

同一 `target` 或同一 `source` 出现在多个对里 ⇒ 派生实例，划分时必须同组。
SCAN 里这种情形很多：

- `career` ↔ mountain / hill / slope / journey（**4 个对**共享目标 `career`：
  `group_scan_0025/0026/0027/0058`）
- `innovation` ↔ bloom / blossom / flower（**3 个对**共享目标：`0022/0023/0024`）
- `war` 作为源域出现在 **3 个对**：`argument↔war`(0011) / `sport↔war`(0039) /
  `business↔war`(0064)。注意 `debate↔battle` 不含 `war`，是同块但不同对
- `journey` 作为源域出现在 **4 个对**：`0031/0051/0052/0058`
- `politics` 作为目标出现在 **4 个对**：`0054/0060/0061/0062`
- `crime` 作为目标出现在 **3 个对**：`0048/0049/0065`

**具体口径**：按 `target`/`source` 建并查集求连通块，块不可分，整块进同一个 split。
65 组最终聚成 30 个不可分块（最大块 10 组：`life↔theatre` 与 `marriage↔boat/game`
等通过共享 system 连成一片）。

**这就是用户提的防泄漏要求的落地**：不能把 `career↔mountain` 放训练、
`career↔journey` 放测试，然后把它们当两个独立样本。

### 6.2 实际结果与离散来源

| 项 | 值 |
|---|---|
| 连通块数 | 30 |
| 块大小 | `[10, 9, 5, 5, 3, 3, 3, 2, 2, 2, 2, 1, 1, ...]`（19 个单例） |
| 划分 | train **46** / val **10** / test **9** |
| 占比 | 70.77% / 15.38% / 13.85% |
| 跨划分 system | **0** |

test 13.85% 偏低不是算法问题：穷举 30 个块的所有分配，
**(46, 10, 9) 是唯一可行组合**（`verify_scan.py` 的 B7b 输出 `精确可达: True`）。
换任何分配都会破坏「派生同组」这条更硬的约束。

---

## 7. 验收现状

| 项 | 结果 |
|---|---|
| `python a_data/verify_scan.py` | **全部通过**（A1–A6 / B1–B8） |
| `python a_data/mutation_test_scan.py` | **10/10 变异都被守卫抓到**（无崩溃、无漏检） |
| `python -m pytest tests/` | **82 passed**（SCAR 59 + SCAN 23） |
| 参考映射满分 | 65/65（`pair_consistency` + `type_pattern`，sf=1.0 sipr=1） |
| 恒等/循环/空映射 | 全部 < 1，无一满分 |
| 类型标注缺口 | 0（598 词全覆盖） |
| 行覆盖 | 451/451，无重复计入 |
| schema 必填字段 | 0 缺失（含 `available_checks`） |

### 7.1 变异测试抓到的两个真 bug（记录在案）

验收器写完后第一次跑就报 86 项不合格，其中 **84 项是验收器自己写错**：

1. **方向标反**：`faithful_mappings` 是 `[targ, src]`，我按 `[src, targ]` 读了，
   导致 B1（节点数）和 B6（多值类型）在 29 组上误报。
2. **`Path("") == Path(".")`**：用 `Path(env) or default` 写临时目录支持，
   环境变量未设时 `"."` 是真值 ⇒ 去扫当前目录，扫到 0 组却报「占比 0.000」。

而变异测试反过来抓出验收器**该报不报**的一处：
**跨划分只打印 `共享 system 跨划分: 1`，没有 `fail()`**，数据真被拆块时照样"全部通过"。
现已修。这条是本轮最有价值的发现——只跑一遍绿不能说明检查项有用。

### 7.2 复核轮（2026-11-02 第二次）查出的规范缺口

上一轮"全部通过"的基础上，逐字段对 `T01-schema.json` 才发现三处不合规：

1. **`adaptation.available_checks` 是 schema 必填字段，65 组全漏**。
   它是 `struct_check_availability` 约定用来声明"该组有原始依据可核验哪些项"的，
   评价器按它决定分母。现已补为 `["pair_consistency", "type_pattern"]`
   （取值从 `metrics.CHECK_GROUPS` 校验，不写死）。
   **SCAR 的 378 组同样漏了这个字段**，一并补上，数据集未变（仍 378 组 / 265-57-56）。
2. **自造了 schema 外的字段名**：`raw_rows`、`derived_from`、`systems`。
   分别与 `raw`、`mapping_group_id`、`system` 重复，已删或改名并入。
   保留的 schema 外补充字段只允许 SCAR 也有的那几个（`node_type_source` /
   `system` / `note` 等），避免 B/C 解析器在两个结构数据集之间分叉。
3. **验证器不查字段契约**：A1–A5 全在查内容真实性，没有一条查"字段齐不齐"。
   已新增 **A6 schema 符合性**（必填齐全 / 无 schema 外自造字段 /
   `available_checks` 取值合法且与实际判据一致 / `annotation_status` 在枚举内）。

对应加固：变异测试从 8 项扩到 **10 项**（新增"删掉必填字段"和"自造 schema 外字段"），
回归测试从 20 条扩到 **23 条**（新增字段齐全、available_checks 一致、无自造字段三条）。
两条新变异都被抓到，新测试也验证过"改坏数据会变红"。

### 7.3 已知限制（必须写进 E01 表）

1. SCAN 清单 2 项 vs MRED 11/9 项，**SF 分母不同不能并排比**。
2. `type_pattern` 只在方法输出带节点类型时才有效；方法不输出类型时该项应剔除。
3. `pair_consistency` 一项就能识破全部排列类错误，SCAN 上的高分本身偏高。
4. SCAN 无任何关系描述，与 SCAR 的「逐对解释」证据强度不同，**结果表须与 SCAR 分列**。
5. `role_consistency` 不启用（`ref_roles = {}`），不参与分母。
