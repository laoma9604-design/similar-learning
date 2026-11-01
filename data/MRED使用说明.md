# MRED 数据集使用说明

给 B（引擎）、C（求值/搜索）以及后来接手的人看：**拿到这套数据具体怎么读、怎么调、哪里是坑。**

规格与合规依据见 `data/MRED数据说明.md`；目录职责见 `目录说明.md`。本文只讲操作。

---

## 一、30 秒上手

```python
from pathlib import Path
import json, sys

ROOT = Path("dabao")                  # 仓库根
sys.path.insert(0, str(ROOT / "a_data"))
import runtime                        # 求值器，只有 82 行，先读它

# 只要正式库，别用 cases/*/group_*（那会把 5 个 dev 组混进来）
groups = sorted(ROOT.glob("cases/*/group_tr_*"))
print(len(groups))                    # 300

g = groups[0]
# 任务文件名不编码正负：一律 task_<组>_t01.json / _t02.json
tasks = sorted((g / "data/input/tasks").glob("*.json"))
task = json.loads(tasks[0].read_text(encoding="utf-8"))
print(task["target_id"], len(task["source_ids"]))   # 目标 + 10 个候选源域
```

---

## 二、一个组里有什么

```
group_tr_0000/
├── manifest.json                  ← 公开索引（split / task_ids / object_ids）
├── manifest.sealed.json          ← 封存：哪些源域有效 / 哪些该排除
├── relation/                     ← 封存：正确映射、角色、真实领域名与节点语义
├── counterexamples/              ← 封存：10 个干扰源的标注与见证点
├── data/input/                   ← ★ 方法输入，只有这里的东西能读
│   ├── objects/                  ← 12 个对象（1 目标 + 1 有效源 + 10 干扰源）
│   └── tasks/                    ← task_<组>_t01.json / task_<组>_t02.json
└── sealed/                       ← 封存答案（仅评价器）
    ├── reference.json
    └── intervention_points.json  ← 只有测试组有
```

**红线：`manifest.sealed.json`、`relation/`、`counterexamples/`、`sealed/` 这四样方法一律不许读。**
方法能碰的只有 `data/input/` 和 `manifest.json`（后者只用来定位 task_id，不能读 sealed 版本）。

---

## 三、任务格式

```json
{
  "task_id": "task_group_tr_0000_t01",
  "group_id": "group_tr_0000",
  "target_id": "obj_group_tr_0000_tgt",
  "source_ids": ["obj_group_tr_0000_i03", "obj_group_tr_0000_src", "...共 10 个"],
  "intervenable_inputs": ["v7", "v4"],
  "specified_outputs": ["v3"],
  "intervention_range": {"v7": [-0.2, 0.2], "v4": [-0.2, 0.2]}
}
```

- `task_id` **不编码正负**（`t01`/`t02` 只是组内序号，不含 `_pos`/`_neg`），正负只在 `sealed/reference.json` 的 `label` 里
- `source_ids` **顺序按组哈希打乱**，有效源不在固定位置（v1 曾固定在首位，等于白送答案）
- 正任务 10 个源域里有 1 个是对的；负任务 10 个全是干扰源
- 你要做的是：从 `source_ids` 里挑出与 `target_id` 同构的那个（可能是 0 个 → 返回拒绝）
- **节点 ID 用 `v1..v9` 中性池**，同一组内目标域、有效源、全部干扰源的 ID 集合完全一致，无法按 ID 区分谁是答案
- **节点 label 是「量 A / 量 B / 量 C」**，真实语义（当前本金 / 本期利率）只在封存的 `relation/analogy.json` 里
- 三个类型的关系里，乘性与线性类有 3 个节点（2 输入 + 1 输出），饱和类 2 个节点（1 输入 + 1 输出）；
  **所有候选源与目标域的节点数一定相同**（v1 曾出现 3 节点目标配 2 节点干扰源，那些候选走不到响应检验）

---

## 四、对象格式

```json
{
  "object_id": "obj_group_tr_0000_tgt",
  "object_kind": "mechanistic",
  "relation_type": "multiplicative_growth",
  "label": "目标域",
  "nodes": [{"node_id": "v7", "label": "量 A", "type": "positive_scalar"}, ...],
  "edges": [{"edge_id": "r1", "edge_type": "multiplicative_growth",
             "input_nodes": ["v7", "v4"], "output_nodes": ["v3"],
             "roles": {"v7": "current", "v4": "ratio", "v3": "next"}}],
  "function": "v7 * (1 + v4)",
  "controllable_inputs": ["v7", "v4"],
  "designated_outputs": ["v3"],
  "baseline": [5000, 0.1],
  "input_scales": [5000, 0.1],
  "baseline_output": 5100,
  "output_scale": 5100,
  "legal_domain": {"v7": [0, null], "v4": [0, 1]},
  "intervention_bounds": {"v7": [-0.2, 0.2], "v4": [-0.2, 0.2]},
  "provenance": {"dataset": "mred", "original_id": null, "structure_source": "provided"}
}
```

**注意 `label`**：公开对象里所有候选源的 label 都是「候选源域」、目标是「目标域」，节点 label 是「量 A / 量 B / 量 C」。
真实领域名（细菌二分裂 / 银行复利）与节点语义（当前本金 / 本期利率）只写在封存的 `relation/analogy.json` 里——
v1 曾在公开对象上直接写真实领域名，等于把答案印在题面上。

### 三个最容易搞错的地方

**1. `baseline` / `input_scales` 是列表，按 `controllable_inputs` 的顺序对齐**

不是按字母、不是按节点顺序。看 `controllable_inputs = ["v7", "v4"]` → `baseline = [5000, 0.1]` 意思是 `v7=5000, v4=0.1`。

**2. `function` 用的是 node_id 字符串，不是角色名**

`v7 * (1 + v4)` —— 节点 ID 从 `v1..v9` 池里按组哈希随机分派，跨组不固定。正确做法是原样把 `function` 丢给 `runtime.expression_value()`，不要自己解析，也不要假设某个 ID 一定是某个角色。

**3. 饱和类的 R_max、K 是写死在字符串里的常量，不是节点**

`20.0 * v1 / (2.0 + v1)` —— `20.0` 和 `2.0` 不是 `controllable_inputs` 的成员，别去 `baseline` 里找它们。

---

## 五、求值：直接用 runtime.py

```python
import runtime

obj = json.loads((g / "data/input/objects/obj_group_tr_0000_tgt.json").read_text(encoding="utf-8"))

# 1) 在 baseline 上求值（应该等于 baseline_output）
inputs = dict(zip(obj["controllable_inputs"], obj["baseline"]))
runtime.evaluate_object(obj, inputs)        # {'v3': 5100.0}

# 2) 施加无量纲干预 u，得到实际输入值
runtime.intervene(obj, {"v7": 0.2, "v4": 0.0})   # {'v7': 6000.0, 'v4': 0.1}

# 3) 一步到位拿归一化响应
runtime.normalized_response(obj, {"v7": 0.2, "v4": 0.0})   # {'v3': 0.2}
```

**干预必须给全部 `controllable_inputs`**，少一个就报 `Dimensionless intervention must specify every input ID`。这是最常见的报错。
**节点 ID 不要写死**：不同组的 ID 从 `v1..v9` 池随机分派，上面这些 ID 只对 `group_tr_0000` 这个组有效，请从对象自己的 `controllable_inputs` 里读。

---

## 六、三类关系的归一化响应（可用来做解析验证）

`r = (y(u) − y₀) / output_scale`，其中 `输入 = baseline + input_scales × u`。

| 关系 | 闭式解 | 说明 |
|---|---|---|
| 线性驱动-阻力 | `r = (1+u_d)/(1+u_r) − 1` | **与 baseline 无关**，任意两域天然一致 |
| 饱和响应 | `r = u/(2+u)` | **与 R_max、K 无关**，前提是 input₀=K |
| 乘性增长 | `r = u_c + r₀·u_r/(1+r₀) + r₀·u_c·u_r/(1+r₀)` | 含 `r₀`，故两域 ratio 必须相同 |

**实用含义**：
- 线性类 driver 和 resistance 两个维度都能跨域比较
- 饱和类只有一个维度（input）
- 乘性类只有 current 能跨域比较，`ratio` 只能当固定参数

写解析验证用例时直接用上面三行式子，不要自己推。

---

## 七、判断「源域是否与目标域同构」

标准做法（评价器的口径）：

```python
# 在同构映射下，两域归一化响应应该处处相等
for u in grid:                                  # u 在主输入维度上扫描
    r_t = runtime.normalized_response(target, u_target)[out_t]
    r_s = runtime.normalized_response(source, u_source)[out_s]
    err = min(1.0, (r_s - r_t) ** 2)            # 单输出误差定义
    max_err = max(max_err, err)

# 判据
if max_err <= 0.05 and direction_agreement >= 0.95:
    判为有效源域
else:
    判为干扰源
```

- 参考容差：`min_ctc = 0.95`、`max_error = 0.05`（存于 `sealed/reference.json`）
- **不能只查几个固定点**——局部扰动类在五点 {−0.2,−0.1,0,0.1,0.2} 上最大误差只有 0.0122（低于容差），但 `u≈0.13` 处有 0.0900。必须做密集搜索。

---

## 八、三类干扰源的特征（别误判）

| 类型 | 每组几个 | 典型最大误差 | 特征 |
|---|---|---|---|
| 结构错误 | 3 | 0.0000（响应与目标完全一致） | **结构层面不成立**：某个被标注为输入的节点实际不影响输出（端点标注与函数不符），靠结构检查排除，不是靠响应 |
| 响应错误 | 3（负任务 4） | 0.0581 ~ 1.0000（均值 0.3080） | 结构全对，只有函数形式不同；4 个不同函数族，标准网格上必然超容差 |
| 局部扰动 | 3 | 0.0784 ~ 0.1156（均值 0.0947） | 稀疏五点最大 0.0131（**低于**容差），标准网格上必超容差 |

局部扰动的鼓包加在**全部输入维无量纲扰动的均方根** `u_norm` 上（不是单维 u），中心 0.20、宽 0.02：

```
b(u_norm) = 0.30 × [ exp(−((u_norm−0.20)/0.020)²) − exp(−(0.20/0.020)²) ]
```

这样二维输入的每一维都真实影响输出（否则第二维「标注是输入却不影响输出」会被判成结构错误），
同时稀疏五点（每维 −0.2/−0.1/0/0.1/0.2，其余维置 0，故 u_norm ∈ {0, 0.0707, 0.1414}）全部落在鼓包外，
而 0.05 步长的标准网格能采到 u_norm≈0.20 ——「稀疏点容易通过、稠密检查必然失败」在固定网格上稳定成立。

---

## 九、测试任务的封存干预点

只有 `split == "test"` 的 48 组有 `sealed/intervention_points.json`，共 96 个测试任务 × 100 点。

```json
{
  "group_id": "group_tr_0012",
  "seed": 20261007,
  "points_per_task": 100,
  "tasks": {
    "task_group_tr_0012_t01": [{"v7": 0.0834, "v4": -0.1271}, ...100 条],
    "task_group_tr_0012_t02": [...]
  }
}
```

**这是响应评价点，由 A 封存，方法与搜索器一律不得读取。** 只用评价器在算指标时读。

注意区分：
- 这里的 100 点是**评价用**的固定点
- 方法自己搜索找到的见证点是**方法产出**
- 两者不能混（任务书 L1024 明确「参考负例见证点另存，不混作方法已经找到的反例」）

---

## 十、读数据的正确姿势

```python
from pathlib import Path
import json

ROOT = Path("dabao")

# ✅ 正式库
formal = sorted(ROOT.glob("cases/*/group_tr_*"))      # 300

# ✅ 开发组（联调用，不纳入正式测试）
dev = sorted(ROOT.glob("cases/*/group_dev_*"))        # 5

# ❌ 别这么写，会把 dev 组混进统计
wrong = sorted(ROOT.glob("cases/*/group_*"))          # 305
```

按划分过滤：

```python
import csv
splits = {r["group_id"]: r["split"] for r in csv.DictReader(open(ROOT/"data/splits.csv", encoding="utf-8-sig"))}
train = [g for g in formal if splits[g.name] == "train"]     # 210
val   = [g for g in formal if splits[g.name] == "val"]       # 45
test  = [g for g in formal if splits[g.name] == "test"]      # 45
```

**不要自己重新划分**——划分种子 20261007 已固定，改写会造成实验间不可比。

---

## 十一、答案在哪（仅评价器）

`data/reference_all.jsonl`：600 条任务级记录，一行一个任务，流式读取即可，不用翻 300 个文件。

```python
import json
ref = {}
for line in open(ROOT/"data/reference_all.jsonl", encoding="utf-8"):
    r = json.loads(line)
    ref[r["task_id"]] = r

r = ref["task_group_tr_0000_t01"]
r["label"]            # "positive"
r["valid"]            # [{"source_id": "...", "node_map": {...}, "edge_map": {...}}]
r["exclusions"]       # [...]
r["allowed_mappings_total"]   # 60（10 个源域 × 6 个类型兼容双射，全部枚举过）
r["reference_tolerance"]      # {"min_ctc": 0.95, "max_error": 0.05}
```

负任务 `valid` 为空、`exclusions` 覆盖全部 10 个候选、`full_library_verified` 为真，且每个 exclusion 都带：
- `candidate_mappings`：该源域被枚举的映射数（6）
- `detail`：逐映射的失败项（如 `["输入端点无效:v4"]`、`["输入集合:r1","角色:v7"]`）
- `max_error` + `witness`（响应错误/局部扰动类）：`u_target`、`u_source`、`r_target`、`r_source`、`node_map`，只读这个文件就能复算

**`full_library_verified` 是由枚举结果算出来的，不是常量**——正任务因为库里有有效映射，该字段必为 false。v1 曾把它写死成 true，且 `reference_all.jsonl` 里没有一条带见证。

**这是封存答案，只有评价器（A）能读，方法与搜索器不许读。**

---

## 十二、常见报错

| 报错 | 原因 | 解决 |
|---|---|---|
| `Dimensionless intervention must specify every input ID` | 干预只给了部分输入 | 把 `controllable_inputs` 全部填上 |
| `Intervention outside bounds` | u 超出 `intervention_bounds` | 乘性/线性是 ±0.2，饱和是 [-0.8, 1.0] |
| `Input outside legal domain` | 干预后实际值越界（如 ratio 变负） | 检查 u 与 baseline 的组合 |
| `Unsupported expression syntax` | 自己解析了 function | 用 `runtime.expression_value()` |
| `Input IDs must exactly match controllable_inputs` | 多传或少传输入 | 严格按 `controllable_inputs` 的键 |

---

## 十三、要改数据时

数据由脚本生成，**不要手改 JSON**。

```bash
python a_data/gen_mred_formal.py --dry     # 全量验算，不落盘，约 2 分钟
python a_data/gen_mred_formal.py           # 验算通过才落盘
python a_data/make_deliverables.py         # 重生成 splits.csv + reference_all.jsonl
```

改完数据**必须**重跑 `make_deliverables.py`，否则清单和参考标注会与数据脱节。
