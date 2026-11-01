# SCAR 数据来源说明（S02）

本文档是任务书 L1555 数据说明必填项中的「来源与许可」部分，对应 S01–S03 交付。

## 一、来源（S01）

| 项目 | 内容 |
|---|---|
| 数据集 | SCAR（Structure Abduction of Analogical Reasoning） |
| 论文 | *Beneath Surface Similarity: Large Language Models Make Reasonable Scientific Analogies after Structure Abduction* |
| 会议 | Findings of EMNLP 2023，pp. 2446–2460 |
| 论文入口 | https://aclanthology.org/2023.findings-emnlp.160 |
| DOI | 10.18653/v1/2023.findings-emnlp.160 |
| 作者资源 | https://github.com/siyuyuan/scar  ← 实际取数处 |
| 取数方式 | `git clone` 作者 GitHub 仓库 |
| 使用文件 | `release/system_analogy_en.json`（英文版，400 条） |

未使用 `release/system_analogy_zh.json`（中文译版，同为 400 条）。两版是同一批类比的不同语言版本，**不是两组独立数据**，若将来用中文版做 E07 人工评分材料，须在结果中说明与英文版为同一实体，不能当作独立样本计数。

## 二、版本（S02）

| 项目 | 内容 |
|---|---|
| 仓库 commit | `3dfc897cf6cc685531edc80ab64f35660403fc6c` |
| commit 日期 | 2024-01-04 16:54:08 +0800 |
| 文件 | `data/raw/scar/release/system_analogy_en.json` |
| 文件 MD5 | `0093ecb866a9f5039ab1572a45ffadf9` |
| 文件大小 | 1,393,355 字节 |
| 原始条数 | 400（id 1–400 连续无重复） |

版本以 commit hash 为准，可复现：`git clone` 后 `git checkout 3dfc897`。

## 三、许可（S02）

**状态：作者未提供明示许可。**

- 仓库无 `LICENSE` 文件（GitHub API `license` 字段为 `null`）
- README 仅声明「If you find our paper or resources useful, please kindly cite our paper」并提供联系邮箱
- 未找到公开的数据使用条款

**本项目采取的处理方式（保守口径）**：

1. 原始数据**不进入本项目的公开仓库**。`data/raw/` 已在 `.gitignore` 中，从未被 git 跟踪。
2. 适配产物只包含**概念对与结构标注**，不复制 SCAR 作者的背景描述与 Explanation 原文。这些长文本属于作者撰写的实质性内容，若非必要不随仓库发布。
3. 适配产物中的原始数据逐字副本（`sealed/adaptation.json` 的 `raw` / `explanation` / `background` 字段）仅用于 B、C 复核时比对，若本仓库需要公开发布，这些字段应随 `sealed/` 一并评估是否纳入。
4. 引用按论文要求给出（见第一节）。

**未做的事**：未向作者发送书面授权请求。依据是本项目仅在组内用于研究评价、不对外分发原始数据，且 L978 只要求用 SCAR 做结构评价（不需要背景与解释长文本）。若后续需要公开发布含原文的适配产物，应先取得作者书面同意。

## 四、原始数量统计（S03）

| 项目 | 数量 |
|---|---|
| 原始条数 | 400 |
| 语言 | en（单语言） |
| 涉及领域 | 13 类 |
| 领域对 | 93 种 |
| 映射对总数 | 1618 |
| 映射对数范围 | 2 ~ 14 |
| 有背景（system_a/b 均有） | 400（100%） |
| 有 Explanation | 400（100%） |

领域分布（按 system_a + system_b 出现次数）：

| 领域 | 次数 | 领域 | 次数 |
|---|---|---|---|
| Biology | 148 | Geography | 44 |
| History | 129 | Chemical | 42 |
| Physics | 93 | Literature | 41 |
| Philosophy | 92 | Economy | 28 |
| Computer | 56 | Sport | 14 |
| Engineering | 55 | Mathematics | 8 |
| Art | 50 | | |

映射对数分布：

| 对数 | 条数 | 对数 | 条数 |
|---|---|---|---|
| 2 | 31 | 8 | 10 |
| 3 | 188 | 9 | 3 |
| 4 | 81 | 10 | 3 |
| 5 | 38 | 11 | 4 |
| 6 | 15 | 12 | 1 |
| 7 | 24 | 13 | 1 |
| | | 14 | 1 |

## 五、纳入与排除（S04 口径）

严格按 PDF L978「可核验结构的样本做结构评价」、L984「不能用概念名称相似度替代缺失的关系标注」、L986「原材料不足以确定关系则排除并记录原因」执行。

**五条判定规则**（第一条到第三条为排除依据，第四条到第五条为保留规则）：

| 规则 | 内容 | 判定依据 |
|---|---|---|
| S1 解释完整性 | 解释条数 = 映射对数，逐对都能确认关系依据 | 原文 Explanation 与 mappings 对应关系 |
| S2 解释有效性 | 解释必须是实质论证，不能是 `Items:` / `Explanation:` 模板残留 | 解释文本本身 |
| S3 作者自证不成立 | 解释中出现「may not be appropriate」等自我否定 | 作者原话 |
| S4 冗余对 | 真实对称结构保留为映射集合；同义重复才判质量不足 | 映射两端去单复数后比对 |
| S5 多值结构 | 一源多目标/多源一目标原样保存，`multiple_mapping_type` 标注 | 映射两端重复检测 |

**结果：纳入 380 条，排除 20 条（95.0%）。**

| 规则 | 条数 | 说明 |
|---|---|---|
| S1 解释条数不符 | 13 | 无法逐对确认关系依据 |
| S2 模板残留 | 6 | **全部含于 S1 之内**，无额外损失 |
| S3 作者自认不成立 | 7 | **原先遗漏，本次新增排除** |
| S4 冗余对 | 30 | 全为真实对称结构（如 sperm/egg 均对应 product），保留为映射集合，0 条排除 |

S3 新增的 7 条（作者在解释里明确写了该映射不成立）：

| 原始 id | 系统 | 作者原话 |
|---|---|---|
| 24 | Food Chain → Information Flow | this mapping may not be appropriate |
| 220 | Egypt → India | This mapping may not be appropriate because... |
| 221 | Egypt → Ancient Rome | This analogy may not be appropriate because... |
| 256 | Gone with the Wind → Peach Blossom Fan | This analogy may not be appropriate |
| 258 | Thorn Birds → Fortress Besieged | This mapping is not appropriate |
| 277 | mountain → career | This mapping may not be appropriate since... |
| 278 | hill → career | This mapping may not be appropriate because... |

完整记录见 `cases/structural_scar/_excluded.json`，每条含 `rule`（S1/S2/S3）、`reason`（含原文片段）、system 对、映射对数与解释条数。验收脚本与回归测试均会按声明的规则重新复核，防止为了排除而编造规则。

**关于 S1 与 S2 的发现过程**：初版筛选只检查「解释条数 = 映射对数」，漏掉了 S2 与 S3 两类。S2 和 S3 是在人工阅读 20 条试点样本时发现的（见第六节的试点记录），随后扩展为全量规则。

## 六、试点记录（20 条人工判定）

按 PDF L984「先适配 20 个原始组」的要求，人工逐条阅读了 20 条代表性样本（覆盖 2/3/4/5/8/9/10/11/14 对、双射与非双射、含异常条目）。

| 判定 | 条数 | id |
|---|---|---|
| 纳入 | 11 | 23, 1, 7, 29, 61, 62, 271, 144, 69, 77, 356 |
| 排除 | 7 | 273, 287, 24, 53, 85, 146, 148 |
| 存疑（待 B/C 复核） | 2 | 42, 283 |

排除依据分类：
- **作者自认不成立**：id=24，解释原文为 `this mapping may not be appropriate`
- **解释是模板残留**：id=53（`Items: blood, water flow, ...`）、id=85（`Explanation:`）、id=148（`Item: data set, bait, ...`）——这三条解释条数完全对得上，躲过了初版筛选
- **解释与映射错位**：id=287（映射 `ground ↔ stance`，解释却是 `Weapon corresponds to argument...`）、id=146、id=273

试点暴露的问题直接转化为全量规则 S2 与 S3。

## 七、适配产物

| 项目 | 数量 |
|---|---|
| 适配组 | 380 |
| 节点规模 | 2~14，与映射对数一致（未压缩） |
| 双射（唯一参考映射） | 356 |
| 一对多（one_to_many） | 22 |
| 多对一（many_to_one） | 2 |
| 划分 | train 266（70.0%）/ val 57（15.0%）/ test 57（15.0%） |
| 结构模式 | 是（L957：无可靠响应函数，不执行响应检验） |
| 可核验检查项 | `node_bijection`（其余五类无原始标注，不虚构） |

适配脚本：`a_data/adapt_scar.py`
独立验收：`a_data/verify_scar.py`
回归测试：`tests/test_scar_adapt.py`
产出目录：`cases/structural_scar/`
