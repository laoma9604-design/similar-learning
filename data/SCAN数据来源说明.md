# SCAN 数据来源说明（N02）

本文档是任务书 L1555 数据说明必填项中的「来源与许可」部分，对应 N01–N03 交付。
与 `MRED数据说明.md`、`SCAR数据来源说明.md` 并列，三份互不派生。

## 一、来源（N01）

| 项目 | 内容 |
|---|---|
| 数据集 | SCAN（Systematicity Challenge Analogies） |
| 论文 | *SCAN: A Framework for Systematicity in Analogical Reasoning* |
| 会议 | Findings of EMNLP 2022，pp. 2115–2131 |
| 论文入口 | https://aclanthology.org/2022.findings-emnlp.153 |
| 作者资源 | https://github.com/taczin/SCAN_analogies  ← 实际取数处 |
| 取数方式 | `git clone` 作者 GitHub 仓库 |
| 使用文件 | `data/SCAN_dataset.csv` |
| 未使用 | `data/datasets.py`（脚本）、`configs/`、`eval_results.py` 等实验代码 |

## 二、版本（N02）

| 项目 | 内容 |
|---|---|
| 仓库 commit | `91cb1ef118178be2710e09d16d381ea8b1d1fab4` |
| commit 日期 | 2023-03-19 17:35:32 +0100 |
| 文件 | `data/raw/scan/data/SCAN_dataset.csv` |
| 文件 MD5 | `870139e1c0551cce85484b7977b8bd0f` |
| 文件大小 | 20,440 字节 |
| 行数 | 452 行 = 1 表头 + **451** 条记录 |

版本以 commit hash 为准，可复现：`git clone` 后 `git checkout 91cb1ef`。

## 三、许可（N02）

**MIT License**，版权 2022 taczin（`data/raw/scan/LICENSE` 原文）。

- 允许复制、修改、合并、发布、再分发与商业使用，条件是保留版权声明与许可全文。
- 因此 SCAN **不涉及** SCAR 那种「无明示许可」的处置讨论。
- 即便如此，`data/raw/` 仍在 `.gitignore` 第 6 行，原始 CSV 不随仓库分发；
  仓库里只放我们生成的适配产物，并在此处与 `data/SCAN适配规范.md` 标注来源。

## 四、原始数据形态（N03/N04 的事实基础）

### 4.1 字段

`target, source, targ_word, src_word, alternatives, analogy_type`

- `target` / `source`：目标系统名 / 源系统名（如 `atom` / `solar system`）
- `targ_word` / `src_word`：该对映射中的目标概念与源概念
- `alternatives`：另一个候选源词，**不是**已给的关系依据（对照规范 1）
- `analogy_type`：`science` / `metaphor`

### 4.2 规模实测

| 指标 | 实测值 |
|---|---|
| 原始行数 | **451** |
| target-source 原始对 | **65**（一个对占 2–14 行，同义词拆分） |
| 每对行数分布 | 2:1, 3:1, 4:5, 5:11, 6:18, 7:12, 8:3, 9:2, 10:6, 11:1, 12:1, 13:2, 14:2 |
| 去重概念词 | **598**（适配产物节点 label 合并去重后也是 598，逐词一致） |
| 节点规模 | 两域合计 27 个节点封顶（`war→argument`，13+14）；单域最大 14，仅 `argument↔war` 一组 |
| analogy_type | metaphor 373 行 / science 78 行（组级：metaphor 54 / science 11） |
| 有 alternatives 的行 | **66**（聚合到组级为 **34** 组） |
| 带首尾空白的字段 | 2 处（`'public '`、`'guide '`），适配时 strip，`raw.rows` 保留原样 |
| 逆序重复对（A→B 与 B→A 同时存在） | 0 |
| 恒等词对（targ_word == src_word） | 存在（如 `attracts↔attracts`、`memory↔memory`），原文如此，保留 |

### 4.3 SCAN 与 SCAR 的结构差异（决定了适配口径）

| 维度 | SCAR | SCAN |
|---|---|---|
| 关系描述 | 每对一条 Explanation + 双背景 | **无任何解释/背景/领域字段** |
| 一对一记录 | 一条记录 = 一个完整类比 | **一个对拆成多行**，须按 (target, source) 聚合 |
| 噪声 | 解释条数不符、作者自认不成立 | 无此类（没有解释，也就没有解释层面的噪声） |
| 多值来源 | 记录内共享端点 | **同义词拆分**（`stage` 同时对应 `world`/`society`） |

## 五、纳入与排除（N04）

**纳入 65 / 排除 0**（`cases/structural_scan/_excluded.json`）。

判定顺序固定为：空端点 → 映射对 < 2 → 去重后 < 2 → 缺 analogy_type。
65 个对全部通过。

### 5.1 按任务书 L988 要求的五项统计

原文：「最终统计**原始组数、可适配组数、实际任务数、领域分布和排除类型**。」

| 统计项 | 值 |
|---|---|
| 原始组数 | **65**（target-source 对；原始行为 451） |
| 可适配组数 | **65**（100%） |
| 实际任务数 | **65**（1 组 = 1 正任务，无负任务，见 5.3） |
| 领域分布 | **无法按学科统计**——SCAN 原文无 `domain` 字段（见 5.2） |
| 排除类型 | **无排除**（0 条） |

### 5.2 领域分布：SCAN 原文没有这个字段

L982 列给 SCAR 的交付里明确有「解释评价」，但 SCAN 那一格只写
「结构映射评价；解释评价仅纳入参考材料充分的样本」，**没有 domain**。
实测确认 SCAN 六个字段里没有任何领域/学科标注。

按原文**自带**的可统计维度给出分布（不外推）：

| 维度 | 分布 |
|---|---|
| `analogy_type`（原文自带字段） | metaphor **54** 组 / science **11** 组 |
| 原始行级 | metaphor 373 行 / science 78 行 |
| 系统规模 | 不同 target **45** 个、不同 source **50** 个、不同系统名合计 **93** 个 |
| 复用最多的系统 | `career` 4 次、`journey` 4 次、`politics` 4 次、`war`/`money`/`innovation`/`family`/`crime` 各 3 次 |

science 的 11 组逐条列出（供 B/C 复核领域归类）：
`solar system→atom`、`water flow→heat transfer`、`waves→sounds`、
`combustion→respiration`、`sound→light`、`projectile→planet`、
`artificial selection→natural selection`、`billiard balls→gas molecules`、
`computer→mind`、`slot machine→bacterial mutation`、`virus→code`。

> **不做的事**：不用系统名关键词去反推学科（如把 `solar system` 判成 Physics）。
> 那属于用推断替代缺失标注，违反 L984 那句「不能用概念名称相似度替代缺失的关系标注」。
> E01 结果表里 SCAN 的领域一栏记为 N/A，并注明原因。

### 5.3 正负依据：SCAN 只有正任务

L991 规定的正负任务构造是 **MRED 专用**（「MRED 的任务单位是一个目标及其候选源域库，
正任务表示库中至少存在一个有效映射，负任务表示库中没有有效映射」）。

SCAN/SCAN 类结构数据集在原文里**根本没有负任务概念**：每个 target-source 对都是
作者声明的有效类比。若自造「错误映射」当负任务：

- SCAR/SCAN 没有可执行函数 ⇒ 负任务的「响应超容差」证据链立不起来（L957）
- 只能靠自造，属于编数据

**因此 65 组全部是 `label = "positive"`，负任务数 0。**
`manifest.json` 里 `task_counts = {positive: 1, negative: 0, total: 1}`。
E02 的 VRR/FAR（返回行为）**不适用**于 SCAN，须在结果表标 N/A。

### 5.4 尺度与合法域：结构模式下不适用

L1555 的数据说明要求写「尺度、合法域」。这两项属于 MRED 的响应求值契约
（`input_scales` / `output_scale` / `legal_domain`），SCAN 走**结构模式**：

- L957 原文：SCAR、SCAN 中没有可靠响应函数的样本，「采用明确标注的结构模式：
  只训练结构损失，从结构通过者中选映射，**不执行响应搜索**」
- 因此对象记录里 `function` / `baseline` / `input_scales` / `output_scale` /
  `legal_domain` / `intervention_bounds` **全部不填**（schema 中这些字段对
  `object_kind = structural` 非必填）
- 任务记录里 `intervenable_inputs: []`、`specified_outputs: []`、
  `intervention_range: {}`
- `reference.reference_tolerance = null`、`allowed_mappings_total = null`

**不是漏写，是这两项在结构模式下没有定义。** 写 N/A 并注明依据，比填假值诚实。

**为什么 SCAN 没有排除项，而 SCAR 排掉 22 条**：SCAR 的排除理由全部建立在
「原文有 Explanation」之上（解释条数不符、模板残留、作者自认不成立）；
SCAN 没有解释字段，这几类缺陷在这份数据里**不存在**，不是「检查没做」。

**遗留的风险（必须如实写进结果表）**：SCAN 原始材料不含任何关系描述
（无 explanation / background / domain / role 表述）。本适配的关系依据
**只有「同一 target-source 对内的概念对集合」本身**，即原文把
`nucleus↔sun` 列在同一对里，就视为作者声明了这条对应。
这与 SCAR「Explanation 逐对解释」的证据强度不同：

- 合规的部分：没有用概念名称相似度去补任何缺失的关系标注（规范 1）。
- 不合规的部分：也无法用规范 1 更高标准要求它——那份材料在这份数据里不存在。
- 因此 SCAN 的 E01 只能在 `pair_consistency` + `type_pattern` 两项口径下报，
  且必须与 SCAR/MRED 分列，不得直接比 SF 数值。

## 六、适配产物（N05–N08）

| 产物 | 路径 | 内容 |
|---|---|---|
| 原始映射索引 | `cases/structural_scan/_mapping_index.json` | 65 个组 ID ↔ (target, source) ↔ 原始行号 |
| 排除清单 | `cases/structural_scan/_excluded.json` | 空（0 条） |
| 类型缺口 | `cases/structural_scan/_type_gaps.json` | 空（51 个 SCAN 独有词已人工补标） |
| 结构对象 | `cases/structural_scan/group_scan_0001..0065/` | 共 **588** 个文件（585 组内 + 3 个索引）；每组 9 或 10 个（2 节点组少一个对象文件） |
| 适配脚本 | `a_data/adapt_scan.py`（带 `--dry`） | 可重跑复现 |
| 独立验收器 | `a_data/verify_scan.py` | A1–A6 / B1–B8，不 import 适配器 |
| 变异测试 | `a_data/mutation_test_scan.py` | 10 项变异全部被守卫抓到 |
| 回归测试 | `tests/test_scan_adapt.py` | 23 条，全仓 82 passed |

划分：**train 46 / val 10 / test 9**（70.77% / 15.38% / 13.85%）。
不是 70/15/15 精确值：同一 target 或 source 的派生组必须同组（L1020），
65 组聚成 30 个不可分块，块大小 `[10,9,5,5,3,3,3,2,2,2,2,1×19]`。
穷举证明 **(46,10,9) 是唯一的可行组合**（见 `verify_scan.py` 的 B7b），
所以 13.85% 是这条硬约束下的最优，不是算法没调好。
