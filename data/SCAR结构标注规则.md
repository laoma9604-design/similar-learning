# SCAR 结构标注规则

用途：按任务书 L984「由 B、C 复核类型、角色、端点与参考映射」，为 SCAR 样本补齐
完整参考结构，使 L1034 的六类检查项都能成立，SF/SIPR 具备区分力。

状态：待 B/C 复核。本文件是 A 的标注依据，复核时逐条对照。

---

## 一、为什么必须人工标注

SCAR 原文只提供：系统名、领域、概念对映射、逐对解释。**没有**节点类型、
超边端点和角色标注。

三种自动方案实测均不可用（记录在此，避免重复尝试）：

| 方案 | 实测结果 |
|---|---|
| 按词表判别式的关键词规则推断类型 | 92.1% 概念词落入兜底类 `abstract_concept`；31.7% 的正确映射会被类型检查判失败 |
| 按解释句式归纳关系类型 | 13.8% 的组主导信号与次强信号接近，判据不明确 |
| 按系统名关键词分类 | 302/325 落入「其他」 |

根因：SCAR 的类比**本就跨范畴**（具体↔抽象、实体↔过程是类比的价值所在），
任何按词形/范畴的自动规则都会误判。因此按 L984 走人工标注 + B/C 复核。

---

## 二、节点类型标注规则

取值来自 `T01-vocabulary.json` 的 τ_V（`positive_scalar` 不适用于结构类，排除）。
**按 B/C 已写的 discriminator 判定**，判定顺序固定：

| 顺序 | 类型 | 判别问题 | 判「是」则定为此类 |
|---|---|---|---|
| 1 | `force` | 是力或连接机制吗？ | gravity / attraction / electricity / friction |
| 2 | `substance` | 是被消耗/转化的材料吗？ | 原材料 / 产物 / 燃料 / 养料 / 试剂 |
| 3 | `process` | 是动作或正在发生的事吗？ | reaction / flow / war / election / digestion |
| 4 | `property` | 是特征/数值/状态吗？ | temperature / mass / speed / success / fate |
| 5 | `entity` | 能指到/摸到的具体对象吗？ | cell / computer / virus / river / machine / fence |
| 6 | `abstract_concept` | 不占空间、承载意义吗？ | law / memory / knowledge / idea / policy / code |

### 2.1 判定要点

**按「在这个类比语境里指什么」判，不按字面。**
- `water` 在「水循环」里是 `substance`（被转化的材料）；在「水利系统」里可能指 `entity`（设施）
- 判定依据优先看该组 Explanation 里如何描述这个词

**专有名词一律 `entity`**（B/C 词表已注明）：人名、地名、朝代、作品名
- `Aldous Huxley`、`America`、`Ancient India`、`Bible` → `entity`

**同时满足多类时按上表顺序取先命中的**
- `blood flow` 既是物质流动又是过程 → 取 `process`（顺序 3 在 2 前不合适，见下）

**顺序上的一处例外**：若词是「物质 + 流动/传输」这类复合（`blood flow`、
`water flow`），主体是流动这件事，判 `process`；若主体是物质本身（`blood`、
`water`），判 `substance`。判定看中心词。

### 2.2 不允许的做法

- 不允许用「两个词类型必须相同」来反推类型（那会为了迁就正确映射而歪曲标注）
- 不允许同一词在不同组标不同类型，除非 Explanation 明确指出不同所指
- 无法判定时标 `abstract_concept` 并在 `type_note` 写明理由

---

## 三、超边端点标注规则

SCAR 的关系是「A 系统的概念 ↔ B 系统的概念」，一对一或一对多。超边表示这条类比关系。

| 字段 | 标注方法 |
|---|---|
| `input_nodes` | 该组的**全部节点**（源域与目标域各自的全部概念节点都在这一条超边内） |
| `output_nodes` | 空 |
| `edge_id` | 固定 `e1` |
| `edge_type` | 待 T02 归纳结构类词表；暂用 `scar_analogy` |

**为什么 output 为空**：SCAR 的类比关系没有「输出」概念——它说的是「这两个概念
在各自系统里扮演对应角色」，不存在由一个量算出另一个量的方向。这与 MRED 的
`next = current*(1+ratio)` 有明确 output 不同。

**这意味着**：L1034 的「输入集合和输出集合各一项」在 SCAR 上退化为
「输入集合是否覆盖全部节点 + 输出集合是否为空」，仍可判定，但只测「端点标注
是否自洽」，不测方向正确性。这一点须在 E01 结果中说明。

---

## 四、角色标注规则

SCAR 没有现成角色体系。按类比关系的实际结构定义三个角色：

| 角色 ID | 含义 | 判别 |
|---|---|---|
| `correlate` | 参与对应的概念节点 | 该节点在 faithful_mappings 中出现 |
| `hub` | 被多个源节点共享的端点 | 该节点在同一组的 mappings 中被 **≥2 个** 另一域节点映射到 |
| `pivot` | 类比关系的枢纽（系统整体） | 该组的概念节点中，Explanation 反复引用作为整体背景的那个 |

**简化建议**：SCAR 每组只有一条超边，所有节点都是 `correlate`；
只把**共享端点**额外标为 `hub`（若一个节点既是 correlate 又是 hub，记 `hub`）。
`pivot` 暂不使用——原文没有可靠依据判定哪个概念是"枢纽"。

这样一来角色检查的内容是：**候选是否把该共享的端点也共享了**，
即多值结构是否被保持。这与评审指出的问题（多解失真）正面对应。

---

## 五、标注产物格式

在 `sealed/annotation.json` 中逐组记录：

```json
{
  "group_id": "group_scar_0069",
  "original_id": "69",
  "node_types": {"sperm": "entity", "egg": "entity", "product": "substance"},
  "type_basis": "按 Explanation 描述判定：sperm/egg 为配子（具体对象）；product 为产物（被转化的材料）",
  "edge_endpoints": {"e1": {"input": ["sperm", "egg", "..."], "output": []}},
  "roles": {"sperm": "correlate", "egg": "correlate", "product": "hub"},
  "role_basis": "sperm 与 egg 均映射到 product，故 product 为 hub",
  "annotator": "A",
  "review_status": "pending_bc"
}
```

标注以**概念原词**为键（不依赖节点 ID，因 ID 是随机分派的）。
落盘时由转换器把原词映射到节点 ID。

---

## 六、B/C 复核清单

复核者逐组检查：

1. 每个节点的类型是否与 Explanation 描述一致
2. `hub` 标注是否与 faithful_mappings 的共享关系一致
3. 端点标注是否覆盖全部节点、output 是否为空
4. 用参考映射跑评价器，SF/SIPR 应为 1（若不为 1，说明标注与映射不自洽）

第 4 条是关键的机器自检：**标注若写错，正确映射就会不满分**，复核者能立刻发现。

---

## 七、试点范围

按 L984 先做 20 组。选取原则：覆盖不同规模（2/3/4/5/8 对）、不同领域、
不同结构类型（单值/多值），并包含 1-2 条本身较难的样本。

试点通过复核后，再按同一规则扩展全量。
