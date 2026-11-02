"""SCAR 结构标注 · 试点 20 组（A 标注，待 B/C 复核）。

规则见 data/SCAR结构标注规则.md。逐条判定，不反推、不迁就。
"""

ANNOTATIONS = {}

ANNOTATIONS[23] = dict(
    node_types={"dna strand": "entity", "base pair": "entity",
                "bridge": "entity", "column": "entity"},
    type_basis="DNA 链、碱基对、桥、柱子都是可指认的具体结构物 → entity",
    roles={"dna strand": "correlate", "base pair": "correlate",
           "bridge": "correlate", "column": "correlate"},
    role_basis="一对一映射，无共享端点",
)

ANNOTATIONS[1] = dict(
    node_types={"changes": "process", "state": "property",
                "adjust": "process", "pointer": "entity",
                "time": "property", "maintain": "process"},
    type_basis=("changes/adjust 是正在发生的动作 → process；state/time 是状态 → property；"
                "pointer 是可指认的部件 → entity；maintain 是维护动作 → process"),
    roles={w: "correlate" for w in ["changes", "state", "adjust",
                                    "pointer", "time", "maintain"]},
    role_basis="一对一映射，无共享端点",
)

ANNOTATIONS[7] = dict(
    node_types={"cell": "entity", "dna": "substance", "cell organelle": "entity",
                "cytoplasm": "substance", "Worker": "entity",
                "raw material": "substance", "mechanical equipment": "entity",
                "Material warehouse": "entity"},
    type_basis=("cell/organelle/Worker/equipment/warehouse 可指认 → entity；"
                "dna 是遗传物质、cytoplasm 是基质、raw material 是被转化的材料 → substance"),
    roles={w: "correlate" for w in ["cell", "dna", "cell organelle", "cytoplasm",
                                    "Worker", "raw material",
                                    "mechanical equipment", "Material warehouse"]},
    role_basis="一对一映射，无共享端点",
)

ANNOTATIONS[29] = dict(
    node_types={"retina": "entity", "iris": "entity", "pupil": "entity",
                "lens": "entity", "choroid": "entity", "film": "entity",
                "diaphragm": "entity", "aperture": "entity",
                "black paint": "substance"},
    type_basis=("眼与相机的部件均可指认 → entity；black paint 是涂料 → substance。"
                "lens↔lens 同词，两域各有一个节点"),
    roles={w: "correlate" for w in ["retina", "iris", "pupil", "lens", "choroid",
                                    "film", "diaphragm", "aperture", "black paint"]},
    role_basis="一对一映射，无共享端点",
)

ANNOTATIONS[288] = dict(
    node_types={"weapon": "entity", "fighter": "entity", "war": "process",
                "money": "substance", "person": "entity",
                "businessman": "entity", "trade": "process", "business": "process"},
    type_basis=("weapon/fighter/person/businessman 可指认 → entity；"
                "war/trade/business 是活动 → process；money 是被使用的资源 → substance"),
    roles={"weapon": "correlate", "fighter": "hub", "war": "hub",
           "money": "correlate", "person": "correlate",
           "businessman": "correlate", "trade": "correlate", "business": "correlate"},
    role_basis=("fighter 出现在两对（→person, →businessman），"
                "war 出现在两对（→trade, →business），均为共享端点 → hub"),
)

ANNOTATIONS[69] = dict(
    node_types={"sperm": "entity", "egg": "entity", "testis": "entity",
                "ovaries": "entity", "vas deferens": "entity", "oviduct": "entity",
                "product": "substance", "factory": "entity",
                "transmission line": "entity"},
    type_basis=("配子与器官可指认 → entity；product 是产物（被转化的材料）→ substance；"
                "transmission line 是传输设施 → entity"),
    roles={"sperm": "correlate", "egg": "correlate", "testis": "correlate",
           "ovaries": "correlate", "vas deferens": "correlate",
           "oviduct": "correlate", "product": "hub", "factory": "hub",
           "transmission line": "hub"},
    role_basis=("product 被 sperm/egg 共享，factory 被 testis/ovaries 共享，"
                "transmission line 被 vas deferens/oviduct 共享 → 均为 hub"),
)

ANNOTATIONS[62] = dict(
    node_types={"breeds": "entity", "selection": "process", "conformance": "property",
                "artificial": "property", "popularity": "property",
                "breeding": "process", "domesticated": "property",
                "species": "entity", "competition": "process",
                "adaptation": "process", "natural": "property",
                "fitness": "property", "mating": "process", "wild": "property"},
    type_basis=("breeds/species 是群体 → entity；selection/breeding/competition/adaptation/"
                "mating 是过程 → process；conformance/popularity/fitness/artificial/"
                "natural/domesticated/wild 是属性 → property"),
    roles={w: "correlate" for w in [
        "breeds", "selection", "conformance", "artificial", "popularity",
        "breeding", "domesticated", "species", "competition", "adaptation",
        "natural", "fitness", "mating", "wild"]},
    role_basis="一对一映射，无共享端点",
)

ANNOTATIONS[61] = dict(
    node_types={"virus": "entity", "reproduction": "process", "infection": "process",
                "eradication": "process", "vaccine": "substance",
                "code": "abstract_concept", "malware": "entity",
                "replication": "process", "installation": "process",
                "removal": "process", "antivirus": "entity"},
    type_basis=("virus/malware/antivirus 可指认 → entity；reproduction/infection/"
                "eradication/replication/installation/removal 是过程 → process；"
                "vaccine 是投用制剂 → substance；code 是不占空间的指令集 → abstract_concept"),
    roles={"virus": "hub", "reproduction": "correlate", "infection": "correlate",
           "eradication": "correlate", "vaccine": "correlate",
           "code": "correlate", "malware": "correlate",
           "replication": "correlate", "installation": "correlate",
           "removal": "correlate", "antivirus": "correlate"},
    role_basis="virus 同时映射到 code 与 malware → hub",
)

ANNOTATIONS[27] = dict(
    node_types={"dna sequence": "substance", "Sequencing technology": "entity",
                "puzzle pieces": "entity", "stitching": "process"},
    type_basis=("dna sequence 是被读取的序列材料 → substance；Sequencing technology 与 "
                "puzzle pieces 可指认 → entity；stitching 是拼接动作 → process"),
    roles={w: "correlate" for w in ["dna sequence", "Sequencing technology",
                                    "puzzle pieces", "stitching"]},
    role_basis="一对一映射，无共享端点",
)

ANNOTATIONS[105] = dict(
    node_types={"active site": "entity", "reaction speed": "property",
                "reaction process": "process", "transportation hub": "entity",
                "transport efficiency": "property", "transport process": "process"},
    type_basis=("active site/transportation hub 是可指认的场所 → entity；"
                "speed/efficiency 是属性 → property；两个 process 是过程 → process"),
    roles={w: "correlate" for w in [
        "active site", "reaction speed", "reaction process",
        "transportation hub", "transport efficiency", "transport process"]},
    role_basis="一对一映射，无共享端点",
)

ANNOTATIONS[338] = dict(
    node_types={"people": "entity", "Social system": "abstract_concept",
                "Historical events": "process", "Role": "abstract_concept",
                "script": "abstract_concept", "plot": "abstract_concept"},
    type_basis=("people 是人群 → entity；Historical events 是发生的事 → process；"
                "Social system/Role/script/plot 承载意义 → abstract_concept"),
    roles={w: "correlate" for w in [
        "people", "Social system", "Historical events", "Role", "script", "plot"]},
    role_basis="一对一映射，无共享端点",
)

ANNOTATIONS[259] = dict(
    node_types={"group": "abstract_concept", "element": "abstract_concept",
                "operate": "process", "invariant subset": "abstract_concept",
                "Symmetry group": "abstract_concept", "atom": "entity",
                "to rotate": "process", "invariant axis": "entity"},
    type_basis=("群/元素/不变子集/对称群是不占空间的数学对象 → abstract_concept；"
                "operate/to rotate 是操作 → process；atom 与 invariant axis 可指认 → entity"),
    roles={w: "correlate" for w in [
        "group", "element", "operate", "invariant subset",
        "Symmetry group", "atom", "to rotate", "invariant axis"]},
    role_basis="一对一映射，无共享端点",
)

ANNOTATIONS[297] = dict(
    node_types={"war": "process", "battleground": "entity", "combatant": "entity",
                "position": "abstract_concept", "attack": "process",
                "maneuver": "process", "retreat": "process",
                "surrender": "process", "victory": "property",
                "argument": "process", "topic": "abstract_concept",
                "debater": "entity", "claim": "abstract_concept",
                "criticize": "process", "rhetoric": "abstract_concept",
                "retraction": "process", "loss": "property", "win": "property"},
    type_basis=("battleground/combatant/debater 可指认 → entity；war/attack/maneuver/retreat/"
                "surrender/argument/criticize/retraction 是过程 → process；"
                "position/claim/rhetoric/topic 承载意义 → abstract_concept；"
                "victory/loss/win 是结果状态 → property"),
    roles={w: "correlate" for w in [
        "war", "battleground", "combatant", "position", "attack", "maneuver",
        "retreat", "surrender", "victory", "argument", "topic", "debater",
        "claim", "criticize", "rhetoric", "retraction", "loss", "win"]},
    role_basis="一对一映射，无共享端点",
)

ANNOTATIONS[292] = dict(
    node_types={"liquid": "substance", "pouring": "process", "flow": "process",
                "flux": "process", "outflow": "process", "container": "entity",
                "sea": "entity", "source": "entity", "pool": "entity",
                "money": "substance", "investing": "process", "transfer": "process",
                "income": "substance", "profit": "substance", "loss": "property",
                "spending": "process", "bank": "entity", "account": "entity",
                "wealth": "substance", "salary": "substance", "capital": "substance"},
    type_basis=("liquid/money/income/profit/wealth/salary/capital 是流动或积累的资源 → substance；"
                "pouring/flow/flux/outflow/investing/transfer/spending 是过程 → process；"
                "container/sea/source/pool/bank/account 是容器或场所 → entity；"
                "loss 是状态 → property"),
    roles={"liquid": "correlate", "pouring": "correlate", "flow": "correlate",
           "flux": "hub", "outflow": "hub", "container": "hub",
           "sea": "correlate", "source": "correlate", "pool": "correlate",
           "money": "correlate", "investing": "correlate", "transfer": "correlate",
           "income": "correlate", "profit": "correlate", "loss": "correlate",
           "spending": "correlate", "bank": "correlate", "account": "correlate",
           "wealth": "correlate", "salary": "correlate", "capital": "correlate"},
    role_basis="flux→income/profit、outflow→loss/spending、container→bank/account 三处共享端点 → hub",
)

ANNOTATIONS[291] = dict(
    node_types={"war": "process", "army": "entity", "general": "entity",
                "battle": "process", "soldier": "entity", "frontline": "entity",
                "weapon": "entity", "sport": "process", "team": "entity",
                "coach": "entity", "match": "process", "game": "process",
                "race": "process", "sportsman": "entity", "footballer": "entity",
                "player": "entity", "field": "entity", "ball": "entity"},
    type_basis=("army/general/frontline/weapon/team/coach/field/ball 与三类选手可指认 → entity；"
                "war/battle/sport/match/game/race 是活动 → process"),
    roles={"war": "correlate", "army": "correlate", "general": "correlate",
           "battle": "hub", "soldier": "hub", "frontline": "correlate",
           "weapon": "correlate", "sport": "correlate", "team": "correlate",
           "coach": "correlate", "match": "correlate", "game": "correlate",
           "race": "correlate", "sportsman": "correlate",
           "footballer": "correlate", "player": "correlate",
           "field": "correlate", "ball": "correlate"},
    role_basis="battle→match/game/race 与 soldier→sportsman/footballer/player 两处共享端点 → hub",
)

ANNOTATIONS[273] = dict(
    node_types={"theatre": "entity", "stage": "entity", "actors": "entity",
                "actor": "entity", "script": "abstract_concept", "act": "process",
                "role": "abstract_concept", "decoration": "substance",
                "life": "process", "world": "entity", "people": "entity",
                "person": "entity", "history": "process", "event": "process",
                "age": "property", "fate": "abstract_concept",
                "surroundings": "entity", "society": "entity"},
    type_basis=("theatre/stage/actors/actor/world/people/person/surroundings/society 可指认 → entity；"
                "script/role/fate 承载意义 → abstract_concept；"
                "act/history/event/life 是过程 → process；age 是时段 → property；"
                "decoration 是布置材料 → substance"),
    roles={"theatre": "correlate", "stage": "hub", "actors": "correlate",
           "actor": "correlate", "script": "correlate", "act": "hub",
           "role": "correlate", "decoration": "correlate", "life": "correlate",
           "world": "correlate", "people": "correlate", "person": "correlate",
           "history": "correlate", "event": "correlate", "age": "correlate",
           "fate": "correlate", "surroundings": "correlate", "society": "correlate"},
    role_basis="stage→world/society、act→event/age 两处共享端点 → hub",
    type_note="actors/actor、people/person 是同一概念的单复数两写，属原文冗余",
)

ANNOTATIONS[296] = dict(
    node_types={"boat": "entity", "passenger": "entity", "shipwreck": "process",
                "storm": "process", "sail": "process", "rock": "entity",
                "anchor": "entity", "marriage": "process", "spouse": "entity",
                "divorce": "process", "quarrel": "process", "anger": "property",
                "happiness": "property", "love": "property", "affair": "process",
                "problem": "abstract_concept", "home": "entity"},
    type_basis=("boat/passenger/rock/anchor/spouse/home 可指认 → entity；"
                "shipwreck/storm/sail/marriage/divorce/quarrel/affair 是过程 → process；"
                "anger/happiness/love 是情感状态 → property；problem 是抽象 → abstract_concept"),
    roles={"boat": "correlate", "passenger": "correlate", "shipwreck": "correlate",
           "storm": "hub", "sail": "hub", "rock": "hub", "anchor": "correlate",
           "marriage": "correlate", "spouse": "correlate", "divorce": "correlate",
           "quarrel": "correlate", "anger": "correlate", "happiness": "correlate",
           "love": "correlate", "affair": "correlate", "problem": "correlate",
           "home": "correlate"},
    role_basis="storm→quarrel/anger、sail→happiness/love、rock→affair/problem 三处共享端点 → hub",
)

ANNOTATIONS[316] = dict(
    node_types={"machine": "entity", "politician": "entity",
                "algorithm": "abstract_concept", "operator": "entity",
                "oil": "substance", "breakdown": "process", "rust": "process",
                "politics": "process", "law": "abstract_concept",
                "president": "entity", "press": "entity", "campaign": "process",
                "money": "substance", "crisis": "process", "corruption": "process"},
    type_basis=("machine/politician/operator/president/press 可指认 → entity；"
                "algorithm/law 承载意义 → abstract_concept；oil/money 是资源 → substance；"
                "breakdown/rust/politics/campaign/crisis/corruption 是过程 → process"),
    roles={"machine": "correlate", "politician": "correlate", "algorithm": "correlate",
           "operator": "correlate", "oil": "hub", "breakdown": "correlate",
           "rust": "correlate", "politics": "correlate", "law": "correlate",
           "president": "correlate", "press": "correlate", "campaign": "correlate",
           "money": "correlate", "crisis": "correlate", "corruption": "correlate"},
    role_basis="oil→press/campaign/money 三对共享端点 → hub",
)

ANNOTATIONS[275] = dict(
    node_types={"blossom": "process", "water": "substance", "stem": "entity",
                "soil": "entity", "planting": "process", "greenhouse": "entity",
                "symbiosis": "process", "innovation": "process", "funding": "substance",
                "research": "process", "laboratory": "entity",
                "idea": "abstract_concept", "conference": "process",
                "collaboration": "process"},
    type_basis=("stem/soil/greenhouse/laboratory 可指认 → entity；water/funding 是投入的资源 → substance；"
                "blossom/planting/symbiosis/innovation/research/conference/collaboration 是过程 → process；"
                "idea 是抽象 → abstract_concept"),
    roles={"blossom": "hub", "water": "correlate", "stem": "correlate",
           "soil": "correlate", "planting": "correlate", "greenhouse": "correlate",
           "symbiosis": "correlate", "innovation": "correlate", "funding": "correlate",
           "research": "correlate", "laboratory": "correlate", "idea": "correlate",
           "conference": "correlate", "collaboration": "correlate"},
    role_basis="blossom→innovation/idea 共享端点 → hub",
)

ANNOTATIONS[282] = dict(
    node_types={"disease": "process", "doctor": "entity", "patient": "entity",
                "hospital": "entity", "medicine": "substance", "cure": "process",
                "poverty": "process", "politician": "entity", "benefactor": "entity",
                "citizen": "entity", "state": "entity", "subsidy": "substance",
                "payment": "substance", "money": "substance"},
    type_basis=("doctor/patient/hospital/politician/benefactor/citizen/state 可指认 → entity；"
                "medicine/subsidy/payment/money 是资源 → substance；"
                "disease/cure/poverty 是过程 → process"),
    roles={"disease": "correlate", "doctor": "hub", "patient": "correlate",
           "hospital": "correlate", "medicine": "hub", "cure": "correlate",
           "poverty": "correlate", "politician": "correlate",
           "benefactor": "correlate", "citizen": "correlate", "state": "correlate",
           "subsidy": "correlate", "payment": "correlate", "money": "correlate"},
    role_basis="doctor→politician/benefactor、medicine→subsidy/payment 两处共享端点 → hub",
)
