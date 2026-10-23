# cases/ —— 按类比类组织的正式数据结构

把原来堆在 T01-examples.json 里的数据，按"概念 → 类比对"两层拆开。字段名/标签沿用 T01-schema.json 原定写法（object / adaptation / task / reference 四类记录，positive/negative、valid/exclusions 等标签都不动）。

## 目录结构（两层）

```
cases/
  <concept>/                    ← 概念层：relation_type（机制类）/ structural（结构类暂挂，T02 细分）
    <group_id>/                 ← 类比对层：稳定 group_id（正负任务同组），不用数据名
      class.json                ← 类比对元数据：source/target 的 object_id + label、relation_type、方向
      task.json                 ← 方法输入（仅 mechanistic 类有）
      relation/                 ← 类比关系 = 正例（封存）
        objects.json            ← 目标对象 + 正例源对象（schema 的 object 记录）
        reference.json          ← 正例答案（封存，schema 的 reference 记录）
        adaptation.json         ← 忠实映射证据（仅 structural 类有，schema 的 adaptation 记录）
      counterexamples/          ← 反例 = 负例（封存）
        objects.json            ← 负例源对象
        reference.json          ← 排除依据 + witness（封存）
      data/                     ← 原始来源证据（不参与方法输入）
        raw.json                ← case-fixtures 原始数值 / SCAR 原文 / SCAN 原文行
```

## 命名铁律：用稳定 ID，不用数据名

- 概念层：机制类用 relation_type（multiplicative_growth / linear_drive_resistance / saturation_response，词表里定死的稳定 ID）；结构类暂挂 structural/，T02 归纳出概念后再细分。
- 类比对层：用 group_id（group_dev_0001、group_dev_0002……），跟 schema 里"正负任务同组"的 group_id 对齐。人类可读名字（细菌增长/银行复利）只放 class.json 的 label 字段。
- 这样改 label 不动文件夹，加数据只加 group 编号文件夹。

## 现有类比对

| 概念 | group_id | 类比对 | 类型 | 反例 |
|---|---|---|---|---|
| multiplicative_growth | group_dev_0001 | 细菌增长→银行复利 | mechanistic | 合成平方反例 |
| structural | group_dev_0002 | 太阳系→原子 | structural | 暂无 |
| structural | group_dev_0003 | 细胞→工厂 | structural | 暂无 |

## 三条铁律（沿用 T01-schema）

1. **方向一律 source→target**：node_map / edge_map 源域为键、目标域为值。class.json 里写死了 source 是谁、target 是谁。
2. **答案隔离**：方法输入 = task.json + relation/counterexamples 里的 objects.json（按 ID 取，不被告知正负）。reference.json 是封存答案，只有 evaluate 读。
3. **稳定 ID**：object/adaptation/task/reference/group 全部用稳定字符串 ID 关联，不靠文件顺序对齐。

## 与旧文件的关系

- T01-examples.json、case-fixtures.json 原样保留，当"总表 / 生成来源"。
- cases/ 里的内容与旧文件字段值一致，只是按两层拆开。
- 等 B/C 用 cases/ 结构跑通后，再决定要不要删旧文件。

## 怎么加一个新的类比对

1. 确定它属于哪个概念（机制类 = relation_type；结构类先挂 structural/）。
2. 新建 cases/<concept>/<group_id>/ 文件夹，group_id 按顺序编号。
3. 写 class.json（source/target 的 object_id + label、relation_type、方向）。
4. relation/ 放正例对象 + 答案；counterexamples/ 放负例对象 + 排除依据；data/ 放原始来源。
5. mechanistic 类补 task.json；structural 类暂无 task。
