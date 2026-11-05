# v2 数据集使用说明（给 B / C）

数据位置：`cases/structural_v2/`，30 组 / 60 任务 / 360 个对象。
本系列是**独立测试集**，与 v1（单超边）并列，不与 v1.1 混用（v1.1 已删除）。

---

## 一、读这些

```
cases/structural_v2/group_v2_NNNN/
  manifest.json                     ← 公开：组号 / split / 对象与任务 ID / 规模
  data/input/objects/obj_*.json     ← 公开：对象（方法输入）
  data/input/tasks/task_*.json      ← 公开：任务（方法输入）
  sealed/reference.json             ← 禁读：正负标签、参考映射、见证点
  sealed/intervention_points.json   ← 禁读：仅测试组有，100 个干预点/任务
  manifest.sealed.json              ← 禁读：骨架名与家族组合
```

**禁读原因**：`sealed/` 下是答案。方法端、搜索器、任何调参过程都不能读。
读了就等于用答案调参，实验作废（PDF L1010：独立参考规则先于方法调参固定）。

---

## 二、任务 JSON

```json
{
  "task_id": "task_group_v2_0000_t01",
  "group_id": "group_v2_0000",
  "target_id": "obj_group_v2_0000_tgt",
  "source_ids": ["obj_..._s02", "obj_..._s00", "..."],   // 10 个候选，顺序已打乱
  "intervenable_inputs": ["v8", "v12", "v1", "v11"],
  "specified_outputs": ["v6"],
  "intervention_range": {"v8": [-0.2, 0.2], "...": [-0.2, 0.2]}
}
```

- 10 个候选里，正任务至少 1 个有效源；负任务 0 个。**标签不在 task 里**。
- `task_id` 不编码正负（t01/t02 只是序号，别拿它推标签）。
- `intervenable_inputs` 的顺序决定 `baseline` / `input_scales` 的对应关系。

---

## 三、对象 JSON

```json
{
  "object_id": "obj_group_v2_0000_tgt",
  "object_kind": "mechanistic",
  "relation_type": "multi_edge_dag",
  "nodes": [{"node_id": "v8", "label": "量 A", "type": "positive_scalar"}],
  "edges": [
    {
      "edge_id": "e1",
      "edge_type": "multiplicative_growth",
      "input_nodes": ["v8", "v12"],
      "output_nodes": ["v9"],
      "roles": {"v8": "current", "v12": "ratio", "v9": "next"},
      "function": "v8 * (1 + v12)"
    }
  ],
  "function": "整图展开的等价单式",
  "controllable_inputs": ["v8", "v12", "v1", "v11"],
  "designated_outputs": ["v6"],
  "baseline": [1000.0, 0.1, 100.0, 0.1],
  "input_scales": [1000.0, 0.1, 100.0, 0.1],
  "legal_domain": {"v8": [1e-6, null]},
  "intervention_bounds": {"v8": [-0.2, 0.2]},
  "baseline_output": 1331.0,
  "output_scale": 1331.0
}
```

求值：按拓扑序逐边算 `edges[i].function`，输入取自「外部输入 + 已完成边的产出」，
最终输出 = `designated_outputs[0]`。已有的求值器：`a_data/runtime_dag.py`。

```python
import sys; sys.path.insert(0, "a_data")
import runtime_dag
u = {"v8": 0.1, "v12": -0.1, "v1": 0.05, "v11": 0.0}
r = runtime_dag.normalized_response(obj, u)[obj["designated_outputs"][0]]
# r = (输出 - baseline_output) / output_scale
```

---

## 四、五个坑（每条都踩过）

**1. 角色只能读 `edges[].roles`，不能看节点名字**
节点 ID 是 `v1..v12` 随机分派，同一组内目标域和全部候选共用同一份 ID→角色映射。
`v8` 在某组是 `current`，在另一组可能是 `driver`。靠字面名字判角色必错。

**2. `baseline` 按 `controllable_inputs` 顺序，不是字典序**
`baseline[i]` 对应 `controllable_inputs[i]`。顺序错了**不会报错**，只会静默算错。

**3. 饱和边的 K 是内联常量，不是节点**
`"10.0 * v5 / (0.055 + v5)"` 里 `0.055` 是 K，`10.0` 是 R_max，两者都不是节点，
不出现在 `nodes` 里。别去图里找它们。

**4. 饱和边只有 1 个输入，其余边都是 2 个**
饱和是单输入关系，只出现在末端。其余边一律二元（乘性/线性）。
所以 `edges[i].input_nodes` 长度是 1 或 2。

**5. 目标域和有效源域的节点 ID 相同，但参数不同**
同一组内 `tgt` 与 `src` 的图结构、节点 ID 完全一样，差别只在 `baseline` 数值。
所以「参考映射恰好是恒等映射」是构造方式决定的，不是数据泄漏——
方法侧看不到另一组，也看不到 baseline 的差异来源。

---

## 五、三条使用限制（不写清楚会被误用）

**1. 结构错误候选不能用 CTC 筛**
实测：结构错误类 **50% 的 CTC ≥ 0.95**。只看方向一致率会放过近一半结构错误源。
结构错误必须靠 eq:structure（双射 / 类型 / 端点 / 角色）排除。

**2. 复杂度指标里「节点复用」与「分支」恒等**
在树状 DAG 上，一个节点被多条边消费 ⟺ 它是个分支点（否则就是死端）。
实测 30/30 组两值完全相等。**不是七个独立维度，实际六个**。
详见 `docs/MRED_v2独立复杂度审计报告.md` 2.4 节。

**3. 最弱干扰源的余量很薄**
局部扰动的最小 Δr = 0.2604，容差阈值 √0.05 = 0.2236，只高 16.4%。
采样点或参数微调就可能跌破阈值，把干扰源变成合法源域。
改采样协议前必须先跑一遍负任务复核。

---

## 六、参考容差（PDF L1010，数据版本固定，不可调）

```
方向一致率 CTC >= 0.95
参考最大误差 <= 0.05
```

**注意换算**：项目里响应误差定义是 `E = min(1, (r_s - r_t)²)`，
所以「最大误差 ≤ 0.05」对应 **`|Δr| ≤ √0.05 = 0.2236`**，不是 `|Δr| ≤ 0.05`。
别拿一半的数字当阈值。

---

## 七、数据规模

| 项目 | 值 |
|---|---|
| 基础组 | 30 |
| 任务 | 60（每组 1 正 1 负） |
| 候选/任务 | 10 |
| 对象 | 360（每组 12 个 = 1 目标 + 1 有效源 + 3 结构错 + 3 响应错 + 3 局部扰动 + 1 额外响应错） |
| 划分 | train 21 / val 4 / test 5（70/15/15，种子 20261007） |
| 干预点 | 仅 5 个测试组，每任务 100 个 |
| 节点数 | 5–9 |
| 超边数 | 3–5 |
| DAG 深度 | 2–5 |
| 结构种类 | 30 种（30 个骨架，两两不同） |

---

## 八、前 5 分钟做什么

```bash
cd dabao
python a_data/verify_structural_v2.py      # 数据自检，应 16041 条 0 失败（约 3 分钟）
python -m pytest tests/ -q                 # 应 143 passed

python -c "
import json,glob,sys; sys.path.insert(0,'a_data')
import runtime_dag
gd = sorted(glob.glob('cases/structural_v2/group_v2_*'))[0]
man = json.load(open(gd+'/manifest.json'))
obj = json.load(open(gd+'/data/input/objects/'+man['target_id']+'.json'))
print('节点', len(obj['nodes']), '边', len(obj['edges']), '输出', obj['designated_outputs'])
u = {n: 0.0 for n in obj['controllable_inputs']}
print('零扰动响应', runtime_dag.normalized_response(obj, u))
"
```

最后一条应输出 `{指定输出: 0.0}` —— 零扰动时归一化响应必须是 0。
若不是 0，说明 baseline / output_scale 读错了。

**读错一个字段，后面全错且不报错。**

---

## 九、交付物与本数据的关系

- 本数据集用于 E01（结构质量）与 E02（响应一致）
- 每个任务 10 候选，正任务 1 有效 / 负任务 0 有效
- 负任务的「全库排除」已做：枚举节点双射 × 超边双射的全部结构合法映射，
  逐一验证响应，不是只验证预先指定的错误候选

相关文档：
- `docs/MRED_v2构造说明与验收报告.md` — 构造方法与验收结果
- `docs/MRED_v2独立复杂度审计报告.md` — 复杂度实测与口径说明
