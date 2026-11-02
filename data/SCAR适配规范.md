# SCAR 数据适配规范

依据：任务书 L978、L984、L986；schema `topoadv-schema-0.3.1` 的 `records.object` / `records.adaptation`。
状态：已按 20 条试点验证规则可执行，规则稳定，可扩展到全量。
产出：`cases/structural_scar/`（378 组）。

---

## 一、总则

### 1.1 三条不可违反的科研规范

| 编号 | 规范 | 在本文档中的落实 |
|---|---|---|
| 规范1 | 不得用概念名称相似度代替缺失的关系标注 | 节点、超边、映射全部来自原文 `mappings`；类型/角色/方向原文未标，一律不推断（见第四节） |
| 规范2 | 原始材料不足以确定关系时排除并记录原因 | 五条排除规则 + `_excluded.json` 逐条记录，见第三节 |
| 规范3 | 一个任务可能存在多个合理映射时，保存有效映射集合 | 多值映射原样保留，`valid_mappings` + `multiple_mapping_type`，见第五节 |

### 1.2 与任务书的关系

| 任务书条款 | 本文档对应 |
|---|---|
| L978 可核验结构的样本做结构评价 | 第三节的筛选标准即「可核验」的操作化定义 |
| L984 先适配 20 组、B/C 复核、规则稳定后扩展 | 第六节试点记录；本文档即「正式的数据适配规范」 |
| L986 排除并记录原因、统计各类数量 | 第三节结果、第七节统计 |
| L957 结构模式，不执行响应检验 | 第四节：`object_kind=structural`，无 function/baseline |

---

## 二、数据来源

| 项目 | 内容 |
|---|---|
| 仓库 | `https://github.com/siyuyuan/scar` |
| commit | `3dfc897cf6cc685531edc80ab64f35660403fc6c` |
| 文件 | `release/system_analogy_en.json` |
| MD5 | `0093ecb866a9f5039ab1572a45ffadf9` |
| 原始条数 | 400（id 1–400） |
| 许可 | 无 LICENSE；README 仅要求引用。原始数据不进公开仓库（`data/raw/` 已 gitignore） |

---

## 三、纳入与排除规则

### 3.1 五条规则

判定顺序固定，命中第一条即排除（先排除后分类）。

**S1 解释完整性**（排除）
- 要求：`len(Explanation) == len(mappings)`，且每对映射都有对应解释
- 理由：PDF L984 禁止用词义相似度补关系标注，解释是唯一的关系依据。条数不齐就无法逐对确认
- 实测排除 13 条

**S2 解释有效性**（排除）
- 要求：解释必须是实质论证，不能是模板残留
- 识别：条目以 `Items:` / `Item:` / `Explanation:` / `Translation:` / `Elements:` 等列举标签开头
- 理由：这类条目在数量上满足 S1，但内容是残留模板，没有论证任何关系
- 实测：6 条，**全部已在 S1 排除范围内**，无额外损失

**S3 作者自证不成立**（排除）
- 要求：解释中不得出现作者对该映射的否定
- 识别：`may not be appropriate` / `is not appropriate` / `not a valid mapping` / `weak mapping` / `questionable` 等
- 理由：**作者本人在原文中写明该映射不成立**，这不是我们的判断，引用原文即可
- 实测排除 7 条（id 24, 220, 221, 256, 258, 277, 278）
- 这条是初版遗漏的，人工读试点时发现

**S4 冗余对**（不排除，仅质量标记）
- 判定：映射两端去单复数后出现重复
- 区分两种性质：
  - **真实对称结构**（保留）：`sperm ↔ product`、`egg ↔ product`——两个不同概念对应同一功能，生物学上成立
  - **同义重复**（质量不足）：`actors ↔ people`、`actor ↔ person`——同一个词换单复数再说一遍
- 实测：30 条有重复端，**全部属前者**，0 条排除

**S5 多值结构**（不排除，规范3 要求保存）
- 处理：原样保留完整映射集合，标注 `multiple_mapping_type ∈ {one_to_many, many_to_one, both}`
- `valid_mappings` 保存该集合，评价器逐条比对，命中任一条即算通过
- 理由：PDF L986「若一个任务允许多个有效映射，应保存有效映射集合或相应判定条件，避免把不同于某一参考答案的正确映射判错」

### 3.2 结果

| 规则 | 条数 | 是否排除 |
|---|---|---|
| S1 解释条数不符 | 13 | 是 |
| S2 模板残留 | 6 | 是（全在 S1 内） |
| S3 作者自认不成立 | 7 | 是（新增） |
| S4 冗余对 | 30 | 否（对称结构，保留） |
| R-manual 人工判定 | 2 | 是（见下） |
| **合计排除** | **22** | |
| **合计纳入** | **378** | 94.5% |

**R-manual 人工判定的 2 条**（试点读原文后确认，不做成通用规则）：

| 原始 id | 系统 | 问题 |
|---|---|---|
| 42 | Respiratory system → Air handling system | `Respiratory organs` 重复映射到 `filter` / `Cleaner` 两个同义目标，属同义重复而非真实对称结构 |
| 283 | journey → education | `vehicle` 重复 4 次且目标含 `textbook`/`book` 同义对；第 14 对解释写 `Guide` 而映射为 `conductor`，解释与映射错位 |

**为什么这两条不写成通用规则**：曾把「同义重复」和「解释错位」做成自动判定（S4b、S6），但实测在 SCAR 上误伤严重——S6 一次就排除 97 条，其中 76 条是正常条目（`Adjustment ↔ maintenance` 对 `adjust ↔ maintain` 这类正常词形变化被误判成错位）。为避免用工具凑出想要的结论，这两类只记录经人工确认的条目，不做自动推广。

---

## 四、对象转换规则（S05）

### 4.1 组与对象

一条 SCAR 记录 → 一个基础组，含两个 `structural` 对象。

| 项 | 规则 |
|---|---|
| 组 ID | `group_scar_{原始id:04d}` |
| 源域 | `system_a`（映射方向的起点） |
| 目标域 | `system_b` |
| 方向依据 | SCAR 的 `mappings` 是 `[system_a 词, system_b 词]`，与 schema 约定「source→target」一致 |
| `object_kind` | `structural`（L957 结构模式） |
| `relation_type` | `scar_analogy` |
| 节点数 | **= 映射对数**，2~14 全保留，不压缩 |
| 超边数 | 1 条（原文未划分关系，全部概念同处一条超边） |
| 节点 ID | `n1..nk`，两域各自独立编号（与 MRED 一致，不泄露语义） |
| 节点 label | 统一「概念」，**不得填入 SCAR 原词** |
| 节点 type | `abstract_concept` 占位（原文无类型标注，不做语义分类） |
| 超边 endpoints | 全部节点在 `input_nodes`，`output_nodes` 为空（类比无方向） |
| roles | 全部 `participant` |

### 4.2 关于超边只设 1 条

SCAR 原文**没有给出关系划分**——它给的是一个平面映射列表，没说「哪几个概念构成一个子关系」。

- 压成 1 条超边是**忠实于原文**，不是简化
- 强行切分多个超边需要我们自己判断「哪些概念属于同一子关系」，这属于用推断替代缺失标注，违反规范1
- 代价：SCAR 在谱预筛（E06）上会退化（单超边时谱只与节点数有关），应在 E06 中注明 SCAR 不适用

### 4.3 关于无 function / baseline

`object_kind=structural` 时 schema 明确「无 function/baseline 等求值字段」。

- 不编造响应函数（L1299 明确禁止）
- 不执行响应检验，`intervenable_inputs` 与 `specified_outputs` 为空
- 结果只支持结构评价（E01），不支持 E02

---

## 五、参考映射与有效映射集合（S06）

### 5.1 唯一参考映射（356 条）

```
node_map: {n1→n1, n2→n2, ...}   按 faithful_mappings 顺序
edge_map: {e1→e1}
```

自映射是合法的：SCAR 的映射就是「源域第 i 个概念 ↔ 目标域第 i 个概念」，节点 ID 按此顺序编。

### 5.2 多值映射集合（24 条：22 一对多 + 2 多对一）

`valid_mappings` 保存完整集合，`multiple_mapping_type` 标注结构类型。

例（id=69，多对一）：
```
sperm  ↔ product        egg    ↔ product
testis ↔ factory        ovaries ↔ factory
```
`sperm` 和 `egg` 都对应 `product`——生物学上成立（两性配子都产出产品）。压成双射会破坏原意。

评价器行为（`metrics.score_prediction`）：候选与集合逐条比对，命中任一条即 `sf=1, sipr=1`，并在返回值记录 `matched_index`。

---

## 六、检查项可用性声明

### 6.1 为什么需要声明

`metrics.build_checks` 默认按 MRED 的完整清单（11 项 / 二元 9 项）计算。SCAR 没有类型、角色、方向标注，强行按 11 项算会导致这些项恒判失败，SF 被系统性压低。

PDF L1034「清单由完整参考结构确定」——SCAR 的完整参考结构里本来就没有这三类标注，它们**不属于该任务的检查项集合**。

### 6.2 声明方式

```
adaptation.available_checks = ["node_bijection"]
```

评价器只保留声明过的类别，未声明的类别**不进分母**（不是判失败）。SCAR 每个任务的清单只有 1 项。

### 6.3 后果（必须知道）

SCAR 的 SF/SIPR 与 MRED **口径不同，数值不可直接比较**：

| | SCAR | MRED（三节点） |
|---|---|---|
| 检查项 | 1 | 11 |
| 能测什么 | 只有一一对应（无重复占用、无遗漏） | 类型、端点、角色、双射全测 |
| 同一错误（两个输入概念对调） | SF=0.0 | SF=0.818 |

跨数据集比较应同时报 `SF_common`（仅取两边都支持的类别）。这条已写进 schema `conventions.struct_check_availability` 与 `conventions.multi_valid_mapping`。

---

## 七、划分规则（L1020）

| 项 | 规则 |
|---|---|
| 目标比例 | 70% / 15% / 15% |
| 不可分单位 | 共享 system 的全部组（同一 system 的派生关系必须同组） |
| system 归一化 | 先转小写、压缩空白，再判同一（实测不归一化会漏合并 92 个） |
| 划分方法 | 共享 system 并查集合并成连通块，按块大小降序贪心填充 |
| 实测结果 | train 265（70.11%）/ val 57（15.08%）/ test 56（14.81%） |
| 跨划分 system | 0 |

---

## 八、验收

| 脚本 | 覆盖 |
|---|---|
| `a_data/verify_scar.py` | A1 原文逐字一致、A2 映射未改动、A3 解释与背景留存、A4 排除原因可复查、B1 节点数不压缩、B2 两域节点数相等、B4/B5 检查项可计算、B6 多值类型准确、B7 划分达标、B8 公开输入无答案 |
| `tests/test_scar_adapt.py` | 8 条回归测试，锁定上述要点 |

验收脚本与测试均**按声明的规则重新复核**排除原因，防止为了排除而编造规则。

---

## 九、格式合规状况

### 9.0 结构重建（2026-11-02 评审后）

评审指出四条致命缺陷，已全部重建：

| 缺陷 | 现象 | 修复 |
|---|---|---|
| A 编号承载答案 | 两域按映射顺序编号，参考映射恒为 n1→n1；模型输出恒等即满分 | 两域独立随机编号（源 s1..sk、目标 t1..tk），实测恒等映射组数 **0/378**（旧版 387/387） |
| B 检查项无区分力 | 只有 node_bijection，循环置换也是双射 | 改用 pair_consistency + type_pattern，实测循环置换误判满分 **0/378**（旧版 12/20） |
| C 节点全叫「概念」 | 模型拿不到推理所需信息 | 节点 label 填**原始概念词**，系统名公开。概念词是任务输入，不算答案 |
| D 多解失真 | 共享端点被拆成独立节点，`many_to_one` 标注与实际矛盾 | 共享端点只建**一个**节点；`node_map` 改 `pair_map`（列表），装得下「一源对多目标」 |

### 9.0.1 边界：什么公开、什么封存

| 材料 | 处置 | 理由 |
|---|---|---|
| 概念原词、系统名 | **公开** | 模型推理所需输入，抹掉则任务无法完成 |
| 概念对应关系（哪对哪） | **封存** | 这就是答案 |
| Explanation、背景 | **封存** | 含答案与论证 |
| 节点类型（试点 20 组） | 公开 | 属于结构信息，非答案 |

### 9.0.2 为什么不用机械模式的六类检查

实测依据（`a_data/scar_annotations_pilot.py` 20 组人工标注）：

- **node_bijection 不适用**：SCAR 有真实多值对应（`virus→code,malware`、`sperm,egg→product`），双射必然失败
- **node_type（两端同类型）不适用**：正确映射中 **32.5%（41/126）** 两端类型不同
  - `virus(实体) ↔ code(抽象)`、`vaccine(物质) ↔ antivirus(实体)`、`choroid(实体) ↔ black paint(物质)`
  - **跨范畴对应正是类比的核心机制**，要求同类型会系统性地误伤正确答案

因此结构模式改用两条在 SCAR 上真正成立的检查：

| 检查 | 内容 | 实测 |
|---|---|---|
| `pair_consistency` | 候选的概念对应集合与参考一致（顺序无关，含多值端点） | 参考映射 378/378 满分 |
| `type_pattern` | 类型**对应模式**与参考一致（如参考是 entity→concept，候选也必须是），不要求两端同类型 | 恒等/循环置换误判 0/378 |

清单项数为 2，与 MRED 的 11 项口径不同，跨数据集比较须注明。

### 9.1 已合规（对照 T01-schema.json 与 T01-vocabulary.json）

| 项目 | 规定 | 状态 |
|---|---|---|
| object 必填 8 项 | object_id / object_kind / relation_type / split / label / nodes / edges / provenance | 全齐 |
| `object_kind` | enum[mechanistic, structural] | `structural` |
| `split` | enum[dev,train,val,test] | 由组划分填入（曾误写为 `None`，已修） |
| `provenance` | 只含 `{dataset, original_id, structure_source}`；license/version/commit 统一记在数据来源说明，不逐对象重复 | 已修（曾多带 `license`） |
| `node` 字段 | 只允许 `{node_id, label, type}` | 已修（曾多带 `slot`） |
| `node.type` | ∈ τ_V | `abstract_concept` |
| adaptation 必填 11 项 | 含 `available_checks` / `multiple_mapping_type` | 全齐 |

`tests/test_scar_adapt.py::test_object_fields_match_schema` 逐对象锁定上述各项，防止回退。

### 9.2 尚未合规：结构类词表缺失（阻塞项）

| 项目 | 规定 | 实际 | 阻塞原因 |
|---|---|---|---|
| `relation_type`（结构类） | 「结构类=类比概念（中心-环绕 / 系统-子系统等，**T02 归纳定**）」 | `scar_analogy` | 词表里只有三个机械关系，结构类值至今未归纳 |
| `edge_type` | 必须 ∈ τ_E | `scar_analogy` | 同上，τ_E 无结构类值 |
| `edge.roles` | ρ(v,e)，值需在角色体系内 | `participant` | 同上，无结构类角色词表 |

**这不是适配可以做主的**：`T01-vocabulary.json` 的 `edge_types` 只有 `multiplicative_growth` / `linear_drive_resistance` / `saturation_response` 三项，都是带函数模板的机械关系。SCAR 是无函数的类比关系，需要 T02 归纳出结构类条目后，本适配的这三个字段才有合法取值。

**已尝试但失败的自动归纳**（记录在此，避免重复尝试）：

| 方法 | 结果 |
|---|---|
| 按系统名关键词分类 | 302/325 落到「其他」，分类器不可用 |
| 按解释句式信号归纳 | 13.8% 组出现主导信号与次强信号接近，判据不明确 |
| 解释覆盖检查（P2） | 60 条误报 |
| 解释错位判定（S6） | 97 条排除中 76 条误伤（`Adjustment↔maintenance` 对 `adjust↔maintain` 被判错位） |

四次尝试都指向同一结论：**SCAR 的解释是自由文本改写，无法用字符串规则可靠映射到结构标签**。因此这三个字段的处理只能等 T02 词表，不能用推断值填充（规范1）。

**临时约定**：在词表补齐前，`scar_analogy` / `participant` 作为占位值使用，已在代码注释与本文档标明。B/C 复核时须注意这三个字段尚非最终值。

| 限制 | 影响 | 处理 |
|---|---|---|
| 无节点类型标注 | E01 类型类检查项无法算 | 不推断；`available_checks` 不声明该类 |
| 无角色标注 | E01 角色类检查项无法算；「角色错配」分析做不了 | 同上 |
| 无方向 | 输入/输出集合检查项无法算 | 同上 |
| 单超边 | E05/E06 的规模与预筛实验在 SCAR 上退化 | 声明 SCAR 不适用于这两个实验 |
| 14 对的大组 | 候选生成成本高 | 保留；若耗时过高在结果中说明 |

**补齐类型标注的可行性**：节点类型（entity/substance/process/property/force/abstract_concept）有语义范畴依据，理论上可标；但需要 1618 个概念逐个判断、两轮标注加仲裁，且必须 B/C 复核。角色与方向补不了——SCAR 的关系不是函数关系，MRED 的角色词表不适用。若将来补类型，须设 `structure_source: inferred`，与原文提供的部分区分开。

---

## 十、20 条试点记录

| 判定 | id |
|---|---|
| 纳入（11） | 23, 1, 7, 29, 61, 62, 271, 144, 69, 77, 356 |
| 排除（7） | 273, 287, 24, 53, 85, 146, 148 |
| 存疑待复核（2） | 42, 283 |

排除依据：
- id=24：作者自认不成立
- id=53/85/148：解释是模板残留（`Items:` / `Explanation:` / `Item:`）
- id=287：解释与映射错位（映射 `ground ↔ stance`，解释写 `Weapon corresponds to...`）
- id=146：解释错位（`dig ↔ data cleaning` 的解释写的是 `Filter corresponds to feature selection`）
- id=273：同义重复（`actors↔people` 与 `actor↔person`）

试点暴露的 S2、S3 已转为全量规则；S4 的 30 条经全量核查全属真实对称结构，不排除。
