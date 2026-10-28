# cases/ —— 按类比类拆分的正式数据目录

两层：概念 → 类比对（group_id）。字段名/标签沿用 T01-schema.json，文件拆分参考队友的结构图。

```
cases/
  <概念>/                        ← 机制类=relation_type；结构类暂挂 structural/
    <group_id>/                  ← 一个类比对 = 一个数据点（稳定 group_id，不用数据名）
      manifest.json              ← 公开：group_id/数据集/对象ID/任务ID/版本/split
      manifest.sealed.json       ← 封存：valid_sources / excluded_sources
      relation/                  ← 类比关系（封存）
        analogy.json             ← source/target/relation_type
        node_map.json            ← 节点映射（source→target）
        edge_map.json            ← 边映射（source→target）
        roles.json               ← 角色（current/ratio/next 三组对应）
        formula.md               ← 源/目标公式
      counterexamples/           ← 反例（封存）
        <source_id>/             ← 每个反例一个子文件夹
          counterexample.json
          witness.json           ← 见证点
        expected.json            ← 期望拒绝 reason
      data/                      ← 方法输入（B/C 可读，不含答案）
        input/objects/           ← 每对象一文件 + index.json
        input/tasks/             ← positive.json / negative.json
      sealed/                    ← 封存答案（仅 A/EVAL，schema reference 记录）
        reference.json           ← 参考标注 + 容差 + 排除理由
        intervention_points.json ← 仅测试组：每任务 100 个封存干预点
```

命名铁律：文件夹只用稳定 ID（概念=relation_type、类比对=group_id、反例=source_id），人类可读名字只放 label。

---

## 正式库与开发组：靠 group_id 前缀区分

**目录不分离，用 group_id 前缀区分。** 任务书 L991 的约束是「开发数据不纳入正式测试」，约束的是使用范围而非物理路径，前缀 + `split` 字段双保险已足够。

| 前缀 | 含义 | 数量 | split 取值 |
|---|---|---|---|
| `group_tr_` | **正式基础组**（MRED 正式库） | **300** | `train` / `val` / `test` |
| `group_dev_` | 开发联调组（任务书 L991「不纳入正式测试」） | 5 | `dev` |

**B/C 读数据时必须按前缀过滤：**

```python
from pathlib import Path
formal = sorted(Path("cases").glob("*/group_tr_*"))   # 只要正式库
dev    = sorted(Path("cases").glob("*/group_dev_*"))  # 只要开发组
```

不要用 `cases/*/group_*`——那会把 5 个 dev 组混进正式统计。

---

## 正式库规模（详见 data/MRED数据说明.md）

| 项目 | 数量 |
|---|---|
| 基础组 | 300 |
| 任务 | 600（每组 1 正 + 1 负） |
| 每任务候选源域 | 10 |
| 每组对象 | 12（1 目标 + 1 有效源 + 10 干扰源，正负任务共用干扰源池） |
| 划分 | train 210 / val 45 / test 45（种子 20261007） |
| 测试任务干预点 | 90 个测试任务 × 100 点 |

分类别：乘性增长 146 组、线性驱动-阻力 130 组（共 9 + 8 = 17 个真实域对）、饱和响应 24 组（8 个域对）。

**生成脚本**：`python a_data/gen_mred_formal.py --dry` 全量验算不落盘，去掉 `--dry` 落盘。

---

## 开发组（5 个，不纳入正式测试）

- multiplicative_growth/group_dev_0001：细菌增长→银行复利（机制类·乘性增长）
- linear_drive_resistance/group_dev_0004：电路→水流（机制类·线性驱动-阻力）
- saturation_response/group_dev_0005：酶反应→吸附（机制类·饱和响应）
- structural/group_dev_0002：太阳系→原子（SCAN）
- structural/group_dev_0003：细胞→工厂（SCAR 55）
