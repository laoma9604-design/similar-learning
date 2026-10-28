# 给 B：这批数据怎么用

> 白话版。要正经理由和数据规格，看 `data/MRED数据说明.md`；要逐字段操作手册，看 `data/MRED使用说明.md`。
> 这篇只讲：**你要干什么、数据长啥样、哪里会踩坑。**

---

## 一句话

A 这边把 300 个"目标域 + 10 个候选源域"的任务集做好了，全都推在 GitHub 上了。你的活是：**对这 10 个候选，产出一批可能的结构映射（原始候选），并给出分数。**

现在不用管"哪个是对的"——那是评价器的事，答案锁在 `sealed/` 里，你不能读也不需要读。

---

## 数据在哪、有多少

仓库根目录下 `cases/`：

```
cases/multiplicative_growth/group_tr_0001 ~ 0146     乘性增长，146 组
cases/linear_drive_resistance/group_tr_0147 ~ 0276   线性驱动-阻力，130 组
cases/saturation_response/group_tr_0277 ~ 0300       饱和响应，24 组
```

**300 组，每组 2 个任务（一正一负），共 600 个任务。**

⚠️ `cases/` 里还有 5 个 `group_dev_*` 的老联调组，**不纳入正式测试**。读数据一定要这样筛：

```python
groups = sorted(Path("cases").glob("*/group_tr_*"))   # 300 个，对
# 别写 cases/*/group_*，那样会混进 5 个 dev 组变成 305
```

---

## 一个任务长什么样

```python
import json
from pathlib import Path

g = Path("cases/multiplicative_growth/group_tr_0000")
task = json.loads((g/"data/input/tasks/positive.json").read_text(encoding="utf-8"))
```

```json
{
  "task_id": "task_group_tr_0000_a",
  "target_id": "obj_group_tr_0000_tgt",
  "source_ids": ["obj_group_tr_0000_src", "obj_group_tr_0000_i01", ...共 10 个],
  "intervenable_inputs": ["current", "ratio"],
  "specified_outputs": ["next"],
  "intervention_range": {"current": [-0.2, 0.2], "ratio": [-0.2, 0.2]}
}
```

就是：**给你 1 个目标域 + 10 个候选源域，让你挑出能跟目标域"结构对得上"的那些装进候选池。**

- `task_id` 里**看不出正负**（没有 `_pos`/`_neg`），别想着靠 ID 猜
- 正任务 10 个里有 1 个是对的；负任务 10 个全是坑
- 你要产的是**原始候选**，不要只留一个最优解 —— 任务书要求"原始候选未被覆盖"，后面结构校验和响应审计要在这上面做

---

## 对象长什么样（重点看这个）

```python
tgt = json.loads((g/"data/input/objects"/f"{task['target_id']}.json").read_text(encoding="utf-8"))
```

```json
{
  "object_id": "obj_group_tr_0000_tgt",
  "relation_type": "multiplicative_growth",
  "label": "银行复利",
  "nodes": [
    {"node_id": "current", "label": "当前本金",     "type": "positive_scalar"},
    {"node_id": "ratio",   "label": "本期利率",     "type": "positive_scalar"},
    {"node_id": "next",    "label": "下一期余额",   "type": "positive_scalar"}
  ],
  "edges": [{
    "edge_id": "r1",
    "edge_type": "multiplicative_growth",
    "input_nodes": ["current", "ratio"],
    "output_nodes": ["next"],
    "roles": {"current": "current", "ratio": "ratio", "next": "next"}
  }],
  "function": "current * (1 + ratio)",
  "controllable_inputs": ["current", "ratio"],
  "designated_outputs": ["next"],
  "baseline": [5000, 0.1],
  "input_scales": [5000, 0.1],
  "baseline_output": 5500,
  "output_scale": 5500
}
```

### ⚠️ 坑一：节点名字是乱的，别靠名字匹配

目标域的节点叫 `current` / `ratio` / `next`，但**源域的节点 ID 被随机打乱过**：

```json
"nodes": [{"node_id": "b2", "label": "当前细菌数量"},
          {"node_id": "b1", "label": "每代增长率"},
          {"node_id": "b4", "label": "下一代数量"}]
```

看清楚：`b2` 才是"当前数量"，`b1` 是"增长率"。**节点 ID 的字母顺序跟角色顺序完全无关。**

而且**每个组的字母分配都不一样**（`group_tr_0000` 是 b1/b2/b4，下一组可能是 a3/a5/b2），别把上面这组名字写死在代码里。

你要靠的是 `edges[].roles` 这个字段：

```python
tgt_roles = tgt["edges"][0]["roles"]   # {"current": "current", "ratio": "ratio", "next": "next"}
src_roles = src["edges"][0]["roles"]   # {"b2": "current", "b1": "ratio", "b4": "next"}
```

**角色名才是跨域通用的**，节点 ID 只是本地标签。这是 A 故意的——任务书要求有效候选必须"打乱节点顺序"，不然你靠 `n1→n1` 这种编号就能白嫖。

### ⚠️ 坑二：干扰源的节点是 2 个，真实源域是 3 个

| 对象 | 节点数 | 节点 ID |
|---|---|---|
| 目标域 | 3 | `current` / `ratio` / `next`（或打乱后的等价物） |
| 真实源域 | 3 | `b1` `b2` `b4` 这类随机名 |
| 干扰源（10 个里的 9 个） | **2** | `n1` / `n2` |

**注意：节点数能不能当筛选特征，你自己判断要不要用。** 任务书要求"不要让节点数泄露标签"，A 这边已经保证所有干扰源统一 2 节点、label 统一叫"候选源域"。但你要做的是正经的图谱匹配，不是靠数节点数作弊——那种做法在 E01 结构质量指标上会被识破，论文里也站不住。

### ⚠️ 坑三：`baseline` / `input_scales` 是列表，按 `controllable_inputs` 顺序

不是按字母、不是按 `nodes` 顺序。看 `controllable_inputs = ["current", "ratio"]` → `baseline = [5000, 0.1]` 意思是 `current=5000, ratio=0.1`。

搞错顺序不会报错，但会算出离谱的数。**建议第一步就写个断言：在 baseline 上求值必须等于 `baseline_output`。**

```python
import sys; sys.path.insert(0, "a_data")
import runtime

inputs = dict(zip(obj["controllable_inputs"], obj["baseline"]))
y = runtime.evaluate_object(obj, inputs)
assert abs(list(y.values())[0] - obj["baseline_output"]) < 1e-9   # 5500 == 5500
```

### ⚠️ 坑四：饱和类的常数写死在函数字符串里，不是节点

```
"function": "40.0 * input / (2.0 + input)"
```

`40.0` 和 `2.0` 是 R_max 和 K，**不是节点**，别去 `controllable_inputs` 或 `baseline` 里找。`controllable_inputs` 只有 `["input"]` 一个。

---

## 三类关系，各有几个可变维度

这个直接影响你怎么建图。A 已经用数学验证过（不是我随口说的）：

| 关系 | 节点角色 | 能干预的维度 |
|---|---|---|
| `multiplicative_growth` 乘性增长 | current / ratio / next | **只有 current**，ratio 只能当固定参数 |
| `linear_drive_resistance` 线性驱动-阻力 | driver / resistance / response | driver 和 resistance 都行 |
| `saturation_response` 饱和响应 | input / response | 只有 input |

**为什么乘性的 ratio 不能动？** 因为它的响应公式里带了 `ratio₀`，两个域的 ratio₀ 不同就算不到一块去。A 这边已经把每对域对的 ratio 对齐了（都取目标域的值），所以数据是对的，只是**你在做响应审计时不要单独扰 ratio**。

---

## 你要交的东西

按任务书 T03：

```
candidates_raw.jsonl   ← 每个任务一批原始候选 + 检查明细 + 分数
```

要求：
- **原始候选不能被覆盖**。后面结构校验会筛掉一批，但被筛掉的也要留着（做指标要算）
- 已知正确映射要能通过校验
- 角色交换的映射要按预期失败
- 「模型找到正确映射的能力」留到实验里评价，现在不用证明自己找得对

文件放 `runs/<运行ID>/candidates_raw.jsonl`，目录结构看根目录 `目录说明.md`。

---

## 绝对不要碰的东西

| 路径 | 内容 | 为什么不能读 |
|---|---|---|
| `manifest.sealed.json` | 哪个源域是对的 | 读了就是作弊 |
| `relation/` | 正确映射、node_map、edge_map | 直接给答案 |
| `counterexamples/` | 干扰源的类别和见证点 | 告诉你哪个是坑 |
| `sealed/reference.json` | 完整答案 + 容差 | 只有评价器能读 |
| `sealed/intervention_points.json` | 测试任务的 100 个评价点 | 封存，方法与搜索器禁止读 |

**你只能读 `data/input/` 和 `manifest.json`（后者只用来看 `split` 和 `task_ids`）。**

---

## 前 5 分钟该干的事

```bash
git clone https://github.com/laoma9604-design/similar-learning.git
cd similar-learning

# 1. 确认能读到 300 组
python -c "from pathlib import Path; print(len(list(Path('cases').glob('*/group_tr_*'))))"
# 应该输出 300

# 2. 随便挑一组，把对象、任务、roles 读一遍，看懂格式
# 3. 写个断言：baseline 求值 == baseline_output，跑通全部对象
# 4. 拿 task 的 source_ids 加载 10 个对象，检查它们的 roles 字段
# 5. 开始写你的矩阵/编码/谱预筛
```

第 3 步别跳过。3300 个对象里只要有一个读错了，后面所有实验数字都是错的，而且不会报错。

---

## 有问题找谁

- **数据格式、字段含义、某组数据看着不对** → 找 A（我）
- **求值、搜索、API 调用相关** → 找 C
- **任务书要求看不懂** → 看 `research-principles-experiment-taskbook.tex`，那是权威源，别信我转述

---

## 附：别自己重新划分数据

`splits.csv` 里已经定好了 210 train / 45 val / 45 test，种子是 20261007。**不要自己切**，切了实验之间就没法比了。

```python
import csv
splits = {r["group_id"]: r["split"] for r in csv.DictReader(open("data/splits.csv", encoding="utf-8-sig"))}
train = [g for g in groups if splits[g.name] == "train"]
```
