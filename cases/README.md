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
```

命名铁律：文件夹只用稳定 ID（概念=relation_type、类比对=group_id、反例=source_id），人类可读名字只放 label。

现有 3 个类比对：
- multiplicative_growth/group_dev_0001：细菌增长→银行复利（机制类）
- structural/group_dev_0002：太阳系→原子（SCAN）
- structural/group_dev_0003：细胞→工厂（SCAR 55）

