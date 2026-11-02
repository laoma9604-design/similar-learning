"""SCAR 角色标注：仅收录 Explanation 明确给出具体角色的组。

抽取原则（规范1）：只用解释里明确陈述的角色，不用词义推测。
  收录："X is the source/carrier/channel/medium/container/resistance of ..."
  不收录："X is responsible for ..." —— 只说明职责，没给出可判定的角色类型
           （实测 28 组属于此类，若一律标 controller 等于把信息稀释掉）

覆盖：17 组 / 380。其余组的角色只用共享端点规则（hub / correlate）。
"""

ROLES = {
    15: {"light energy": "source"},
    18: {"body": "carrier"},
    24: {"Predator": "source"},
    37: {"water flow": "carrier"},
    42: {"trachea": "channel"},
    73: {"balloon bag": "container"},
    94: {"fuel": "source"},
    133: {"interface": "channel"},
    173: {"market": "carrier"},
    216: {"the nile": "source"},
    321: {"paper": "carrier"},
    323: {"wire": "channel"},
    348: {"water": "medium"},
    349: {"water": "medium"},
    350: {"fuel": "source"},
    369: {"water flow": "source"},
    373: {"sound": "carrier"},
}
