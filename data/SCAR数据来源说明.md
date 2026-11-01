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

按三条科研规范执行：

- **规范1** 不得用概念名称相似度代替缺失的关系标注 → 节点、超边、映射全部来自原文 `mappings`；SCAR 未标注类型/角色/方向，本适配不虚构，通过 `available_checks` 显式声明只有节点双射类可核验。
- **规范2** 原始材料不足以确定关系时排除并记录原因 → 见下表。
- **规范3** 一个任务可能存在多个合理映射 → 多对一/一对多原样保留，标注 `multiple_mapping_type`，`valid_mappings` 保存有效映射集合，不强行改成双射。

**纳入 387 条，排除 13 条。**

排除原因全部为同一类：`Explanation` 条数与映射对数不一致，无法逐对确认关系依据。

| 原始 id | 映射对 | 解释条 | 系统 |
|---|---|---|---|
| 53 | 3 | 5 | blood circulation system → Water pipe system |
| 85 | 5 | 7 | Limit Modification System → Firewall |
| 146 | 5 | 4 | Feature Engineering → Miner |
| 148 | 2 | 4 | （见 _excluded.json） |
| 170 | 3 | 5 | （见 _excluded.json） |
| 239 | 3 | 5 | （见 _excluded.json） |
| 251 | 4 | 5 | （见 _excluded.json） |
| 287 | 11 | 7 | （见 _excluded.json） |
| 304 | 11 | 8 | （见 _excluded.json） |
| 311 | 10 | 9 | （见 _excluded.json） |
| 312 | 11 | 9 | （见 _excluded.json） |
| 318 | 13 | 8 | （见 _excluded.json） |
| 379 | 3 | 5 | （见 _excluded.json） |

完整记录见 `cases/structural_scar/_excluded.json`，含 system_a / system_b、映射对数、解释条数与判定依据。

## 六、适配产物

| 项目 | 数量 |
|---|---|
| 适配组 | 387 |
| 节点规模 | 2~14，与映射对数一致（未压缩） |
| 双射（唯一参考映射） | 362 |
| 一对多（one_to_many） | 23 |
| 多对一（many_to_one） | 2 |
| 划分 | train 271（70.03%）/ val 58（14.99%）/ test 58（14.99%） |
| 结构模式 | 是（L957：无可靠响应函数，不执行响应检验） |
| 可核验检查项 | `node_bijection`（其余五类无原始标注，不虚构） |

适配脚本：`a_data/adapt_scar.py`
独立验收：`a_data/verify_scar.py`
回归测试：`tests/test_scar_adapt.py`
产出目录：`cases/structural_scar/`
