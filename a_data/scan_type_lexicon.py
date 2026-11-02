"""SCAN 独有概念词的节点类型人工判定（51 词，2026-11-02）。

为什么单独建一份：a_data/scar_type_lexicon.py 的 1946 词是从 SCAR 全量概念里
逐词判定的，SCAN 有 51 个词它没有。这些词同样**逐词人工判定**，不写规则推断——
按 T01-vocabulary.json 的 node_type 判别问句：
  entity          能指到/摸到的具体对象
  substance       被消耗/转化的材料
  process         动作或发生的事
  property        特征/数值/状态
  force           力或连接机制
  abstract_concept 不占空间、承载意义的东西
拿不准就记 abstract_concept 并在 AMBIGUOUS 里留痕，不许静默兜底。

词典格式与 scar_type_lexicon.py 一致（key = norm_word：小写、空白归一）。
"""
SCAN_TYPE_LEXICON = {
    # ---- entity：可指认的具体对象/人/机构 ----
    "baggage": "entity",          # 行李，可搬运的实物
    "boss": "entity",             # 指人
    "car": "entity",              # 车辆
    "ceo": "entity",              # 指人
    "class": "entity",            # 班级：可指认的一群学生（非"分类"义）
    "colleague": "entity",        # 指人
    "company": "entity",          # 企业：可指认的组织
    "constitution": "entity",     # 宪法/章程：可指认的成文文件
    "course": "entity",           # 课程：可指认的开设单元
    "employee": "entity",         # 指人
    "exam": "entity",             # 考试：可指认的事件性实体
    "examiner": "entity",         # 指人
    "guide": "entity",            # 向导/指南：指人或成文指南
    "hardware": "entity",         # 硬件：可指认的器件集合
    "incumbent": "entity",        # 在任者：指人
    "job": "entity",              # 职位/工作：可指认的岗位
    "landscape": "entity",        # 地貌：可指认的地表
    "lawyer": "entity",           # 指人
    "lecture": "entity",          # 讲座：可指认的授课单元
    "lift": "entity",             # 电梯/搭车：可指认的装置（"搭车"义亦为具体行为对象）
    "neuron": "entity",           # 神经元：可指认的细胞
    "office": "entity",           # 办公室/职位：可指认的处所
    "opponent": "entity",         # 指人
    "passport": "entity",         # 护照：可指认的证件
    "prison": "entity",           # 监狱：可指认的处所
    "professor": "entity",        # 指人
    "ram": "entity",              # 内存条：可指认的器件
    "scholarship": "entity",      # 奖学金：可指认的资助项目
    "station": "entity",          # 车站：可指认的处所
    "stop": "entity",             # 停靠站：具体处所
    "textbook": "entity",         # 教材：可指认的书
    "ticket": "entity",           # 票：可指认的凭证
    "tracks": "entity",           # 轨道/足迹：可指认的物理痕迹
    "transport": "entity",        # 交通工具：可指认的载体（"运输"义见 AMBIGUOUS）
    "trophy": "entity",           # 奖杯：可指认的物件
    "workers": "entity",          # 指人
    "opinion": "entity",          # 意见：作为可持有的对象（idea 类比中当"物品"用）

    # ---- process：动作或发生的事 ----
    "argumentation": "process",   # 论证：进行的活动
    "convincing": "process",      # 说服：进行的行为
    "reading": "process",         # 阅读：进行的行为（课程类比中指上课形式）
    "remission": "process",       # 病情缓解：发生的过程
    "retirement": "process",      # 退休：发生的人生阶段转变
    "separation": "process",      # 分离：发生的过程
    "victorious": "process",      # 取胜：发生的事（形容词作名词用）

    # ---- property：特征/数值/状态 ----
    "consciousness": "property",  # 意识：状态
    "stance": "property",         # 立场：态度状态
    "tactic": "property",         # 战术：做事方式（方式属性）

    # ---- abstract_concept：不占空间、承载意义 ----
    "future": "abstract_concept",
    "intellect": "abstract_concept",
    "issue": "abstract_concept",       # 议题（非"期号"实物义）
    "passengers": "abstract_concept",  # 乘客整体：类比中作"内容物"讲，非具体个人
}

# 判过但义项两可、按 SCAR 的「拿不准一律标 abstract_concept」留痕
AMBIGUOUS = {
    "transport": "既可指交通工具(entity)，也可指运输过程(process)；"
                 "SCAN 的 education↔journey 中作'教书的形式载体'，取 entity",
    "passengers": "可指人(entity)，但 love↔journey 中讲的是'承载的东西'，取抽象",
    "lift": "电梯(entity) / 搭车(process)；取 entity",
    "tactic": "战术可作行动方案(entity)或方式属性(property)；取 property",
}
