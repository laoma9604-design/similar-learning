# similar-learning

TopoAdv 项目的统一格式（三件套）：字段约定 + 取值约定 + 填好的样例。所有数据、候选、求值、评价都按这套字段走。

文件一：T01-schema.json —— 定"每个记录要填哪些栏"

它规定了 8 种"记录"，就是咱们流程里会出现的 8 种东西，每种该填什么字段全写清了：

· object（知识对象）：描述"一个系统长什么样"。核心是——nodes 节点（系统里有几个概念/变量，每个有 id、名字、类型）、edges 关系（节点怎么连，一条关系要写清哪几个是输入、哪几个是输出、每个节点在这条关系里扮演什么角色）。有函数的话还要 function（公式，直接写节点名的字符串，如 "A_t * (1 + rate_t)"）、baseline（基准输入值列表）、input_scales（输入尺度列表）、baseline_output（基准输出）、output_scale（输出尺度，把不同单位的量变成可比的）、legal_domain（合法输入范围）。最后是 provenance（这数据哪来的）。

· task（任务）：方法拿到的输入。只有目标、候选源域库、能干预哪些输入、看哪些输出、干预范围。没有答案。

· adaptation（适配材料）：公开数据的原始概念对应、解释、背景，封在这里，供复核用，不进方法。

· reference（参考答案）：正确映射、正负标签、见证点，锁在这，只有评价器能读。

· candidate / audit / prediction：分别是 B 出的候选、C 出的求值记录、运行入口出的最终结果。

文件开头还写了铁律，头一条就是"答案隔离"——方法能读的东西里绝对不能掺正确答案。

文件二：T01-vocabulary.json —— 定"字段里只能填哪些词"

· 方向只有两个：- 是输入端、+ 是输出端（不是正负号）。
· 节点类型：现在确认的只有"正值标量"（positive_scalar），另放了个"概念"占位——SCAR/SCAN 那些概念型该归哪类，得后面从数据里归纳。
· 关系类型三类（还要讨论），每类挂着自己的角色：
  - 乘性增长（复利、细菌增长这类）：当前量、变化比例、下一步量——任务书确认过的。
  - 线性驱动-阻力：驱动、阻力、响应——角色名是我取的，要按实际方程定。
  - 饱和响应：输入、响应——也是我暂时取的。
· 还有一个关键区分：类型 ≠ 角色。类型是"这东西是哪一类"（跟具体关系无关），角色是"它在这条关系里干什么"（跟具体关系绑定）。比如本金和利率都是"正值标量"这一类型，但在复利关系里一个是"当前量"、一个是"变化比例"。

文件三：T01-examples.json —— 填好的样例，定"长什么样"

· 7 个对象：
  - 银行复利（mechanistic，有函数）：本金 5000、利率 0.1，公式"下一期 = 本金 ×（1+利率）"，基准输出 5500。
  - 细菌增长（mechanistic）：数量 1000、增长率 0.1，公式"下一步 = 当前 ×（1+增长率）"。
  - 合成平方反例（mechanistic）：结构和细菌增长一样，但公式改成"当前²÷1000×（1+增长率）"，故意让响应不对，专门当负例。
  - 原子、太阳系、细胞、工厂（structural，无函数）：来自真实数据，节点就是那些概念词（原子核/电子/电荷…，细胞膜/细胞核/细胞器…）。
· mechanistic 和 structural 的区别：前者有能算的公式，能跑"干预—响应"校验；后者没有公式，只能做结构评价（SCAR/SCAN 就属于这种）。
· 2 份适配材料：SCAR 的细胞→工厂（5 对概念映射 + 5 条解释 + 两段背景全文）、SCAN 的原子→太阳系（6 对词对），原始数据原封不动封在里面当证据。
· 1 个任务：以银行为目标、两个候选源（细菌=对的、平方反例=错的），但任务里不标哪个对。
· 1 份正任务答案 + 1 份负任务答案：正任务标了"细菌是对的"、给了正确映射；负任务给了平方反例的排除依据——某个输入下误差 0.0576，超过容差 0.05，证明它不成立。

文件四：cases/ —— 按类比类拆的正式数据目录

上面三件套是"格式定义 + 总表样例"。真正跑实验时，数据按"概念 → 类比对"两层拆进 cases/ 目录，一个类比对（一个数据点）占一个 group 文件夹：

```
cases/
  <概念>/          ← 机制类用 relation_type（乘性增长等）；结构类暂挂 structural/
    <group_id>/          ← 一个类比对 = 一个数据点（稳定 group_id）
      manifest.json      ← 公开：ID、数据集、版本、split
      manifest.sealed.json ← 封存：valid / excluded sources
      relation/          ← 类比关系（封存）：analogy + node_map + edge_map + roles + formula
      counterexamples/   ← 反例（封存）：每个反例一个子文件夹 + witness + expected
      data/input/        ← 方法输入（公开）：objects 每对象一文件 + tasks 正负
      sealed/            ← 封存答案（仅 A/EVAL）
```

命名规矩：文件夹只用稳定 ID——概念层用 relation_type，类比对层用 group_id；人类可读名字（细菌增长/银行复利）只放 manifest / analogy 的 label 字段，不拿数据名当文件夹名。这样改名字不动文件夹，加数据只加编号文件夹。

现在有 5 个类比对：
- multiplicative_growth / group_dev_0001：细菌增长 → 银行复利（机制类·乘性增长）
- linear_drive_resistance / group_dev_0004：电路 → 水流（机制类·线性驱动-阻力）
- saturation_response / group_dev_0005：酶反应 → 吸附（机制类·饱和响应）
- structural / group_dev_0002：太阳系 → 原子（SCAN）
- structural / group_dev_0003：细胞 → 工厂（SCAR 55）

详细规则看 cases/README.md。

文件五：每个文件干什么 + 哪些固定、哪些还要讨论

一、cases/ 里一个类比对（group 文件夹）的每个文件

- manifest.json —— 公开元数据：group_id、数据集、relation_type、版本、split、这个组包含哪些对象和任务。
- manifest.sealed.json —— 封存元数据：哪个 source 有效、哪个是反例（只给评价器看）。
- relation/analogy.json —— 这条类比是谁对谁：source、target、relation_type、方向。
- relation/node_map.json —— 节点映射（源→目标，N_t→A_t 这种）。
- relation/edge_map.json —— 边映射（源→目标）。
- relation/roles.json —— 角色三组对应（current/ratio/next，每个角色标它的源节点和目标节点）。
- relation/formula.md —— 源/目标两条公式，给人看，机器读的是 objects 里的 function。
- counterexamples/<source_id>/counterexample.json —— 反例描述（结构通过但响应不对）。
- counterexamples/<source_id>/witness.json —— 见证点（哪个输入、两域输出差多少、误差超没超容差）。
- counterexamples/expected.json —— 期望结果（应该拒绝，理由 no_candidate_passed_response_threshold）。
- data/input/objects/*.json —— 每个对象一份（schema 的 object 记录），方法输入。
- data/input/objects/index.json —— 对象索引（object_id → 文件名）。
- data/input/tasks/positive.json / negative.json —— 正/负任务（方法输入，不含答案）。
- sealed/reference.json —— 封存答案（正负任务的 valid/exclusions），仅 A/EVAL 读。

二、已经固定的（不用再讨论）

- 映射方向一律 source→target。
- 稳定字符串 ID 关联，不靠文件顺序。
- 答案隔离：task/object 不含答案，reference 封存。
- object 字段已精简到 15 个。
- 乘性增长方程 next = current × (1 + ratio)、角色 current/ratio/next（任务书确认）。
- 数据划分 70/15/15、种子 20261007。
- cases/ 命名规矩：概念层用 relation_type、类比对层用 group_id，不用数据名。
- object 已补 relation_type、split 字段（schema draft-v4）。
- 线性驱动-阻力 response=driver/resistance、饱和响应 response=R_max·input/(K+input)，角色已定稿（driver/resistance/response、input/response）。
- 反例 label 不带「反例/错误」字样（任务书 L1006），受控合成标注放封存区 counterexample.json。

三、仍需讨论（重点，高亮）

- ❓ 节点类型：concept 占位要换成 6 类，3 个边界待拍板（water/food 归实体还是物质；force 单列否；disease/war/life tenure 就近归）。
- ❓ 角色是否每条边类型独立命名（避免 rate 既当类型又当角色）。
- ❓ 结构类概念（中心-环绕 / 系统-子系统）T02 归纳。
- ❓ cases/ 里 sealed 和 references 要不要分开（现在合并成 sealed/reference.json，待定）。
- ❓ 数据规模 300 / 600 / 1200 三选一。
- ❓ SCAR 许可（仓库无 LICENSE，待向作者确认）。

（接口类的 pending——评价指标清单、audit.jsonl 格式、candidate.method 枚举等——统一记在 待定事项清单.txt 第 11~17 条，这里不重复。）
