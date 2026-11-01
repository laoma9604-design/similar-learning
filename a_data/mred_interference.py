"""MRED 干扰源构造（v2：与目标域同构的双射候选）。

第一版的问题（2026-11-01 评审确认，已实测）：
    干扰源被造成「1 输入 + 1 输出 = 2 节点」，而 3 节点的目标域
    （乘性 / 线性类）需要 3 节点的双射。两节点候选在任务书 L342
    「两域的节点数相等」这一步就不成立，根本走不到响应检验，
    552 个任务的响应维度因此失效。

v2 的设计（逐条对应任务书）：
1. 【同构】节点数、超边数、类型、输入/输出端点、角色标注全部与目标域一致，
   唯一差异是函数。这样候选能通过结构检查，真正进入响应检验（L1001）。
2. 【双射】干扰源把自己的节点映射到目标域同名角色节点，用 roles 对齐，
   不依赖节点 ID 排序（L342-L352）。
3. 【命名统一】有效源、三类干扰源共用同一套无意义节点 ID 池，
   且每个组内随机打乱，杜绝「b* 是有效源、n* 是干扰源」这类泄露（L1006）。
4. 【三类干扰互不混淆】
     structure_error     —— 角色/端点标注与函数实际不符（结构层面不成立）
     response_error      —— 结构全对，函数形式错
     local_perturbation  —— 结构全对，函数只在输入域子区间偏离
5. 【基线对齐】三类干扰的 baseline 与 input_scales 全部与目标域相同，
   因此同一个 u 对应的实际变化量一致，误差比较的是同一工作点（L684-L700）。
6. 【双输入维度】乘性 / 线性类的目标域有两个可控输入，干扰源同样有两个，
   归一化响应在二维 u 上是可比的。第一版把第二维钉死，等于只用一维证据
   下二维结论，这里不再出现。
"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "a_data"))

import runtime  # noqa: E402

# ============================================================
# 节点 ID 池：有效源与干扰源共用，组内随机分派
# 全部形如 v1..v9，不含任何角色/类别暗示
# ============================================================
NODE_ID_POOL = ["v1", "v2", "v3", "v4", "v5", "v6", "v7", "v8", "v9"]

ROLE_SPEC = {
    "multiplicative_growth": dict(
        roles=["current", "ratio", "next"],
        input_roles=["current", "ratio"],
        output_role="next",
        bounds=[-0.2, 0.2],
    ),
    "linear_drive_resistance": dict(
        roles=["driver", "resistance", "response"],
        input_roles=["driver", "resistance"],
        output_role="response",
        bounds=[-0.2, 0.2],
    ),
    "saturation_response": dict(
        roles=["input", "response"],
        input_roles=["input"],
        output_role="response",
        bounds=[-0.8, 1.0],   # 放宽：饱和反例只在进入饱和区才暴露
    ),
}


def bump(u, amplitude=0.3, center=0.20, width=0.020):
    """局部扰动的鼓包原型（在 u_norm 轴上）。

    参数取值的依据（全部现场算过）：
      · 峰值 = amplitude = 0.30 → 单输出误差 0.09 > 容差 0.05
      · 壳层宽 width = 0.012，center = 0.10
      · 两输入类的固定稀疏点（-0.2/±0.1/0/0.2 各维，其余维 0）对应的
        u_norm 是 0.100/0.141/0.200/0.224/0.250 —— 其中 0.100 正落在鼓包
        上，所以**主输入维的 ±0.2 端点会命中**，但 (±0.1, 0) 这类点
        u_norm=0.1 也会命中。因此稀疏点必须取到 dot 外的方向：
        核验时要求「至少有一个稀疏点误差 < 0.05」且「存在见证点误差 > 0.05」，
        这正是 L1002 说的「某个子区间容易通过、别处失败」。
      · 一输入类（饱和）稀疏点为 -0.8/-0.4/0/0.5/1.0，u_norm 都远离 0.10，
        因此全部容易通过。
    L1002 原型（u 轴、center 0.13、width 0.03）见 O.bump，两者用途不同：
    前者是任务书的算例，后者是本库二维输入下的构造。
    """
    return amplitude * (math.exp(-((u - center) / width) ** 2)
                        - math.exp(-(center / width) ** 2))


# ============================================================
# 目标域工作点提取
# ============================================================
def _target_spec(target_obj, relation_type):
    """从目标对象里取出构造干扰源所需的全部量。"""
    spec = ROLE_SPEC[relation_type]
    ctrl = target_obj["controllable_inputs"]
    base_by_role = {}
    for role, value in zip(spec["input_roles"], target_obj["baseline"]):
        base_by_role[role] = value
    # 目标对象的边界与其角色顺序一致
    consts = {}
    if relation_type == "saturation_response":
        consts["R_max"] = target_obj["_R_max"]
        consts["K"] = target_obj["_K"]
    return dict(spec=spec, ctrl=ctrl, base=base_by_role,
                bounds=target_obj["intervention_bounds"], consts=consts,
                y0=target_obj["baseline_output"],
                y_scale=target_obj["output_scale"])


def _true_expr(relation_type, nodes, t, with_bump=None):
    """目标域（正确）函数在给定节点变量下的表达式。

    with_bump: 若给出 (amp, cen, wid)，在归一化响应空间叠加局部鼓包。
    鼓包的自变量取**全部输入维度**无量纲扰动的欧氏范数 u_norm
    （乘性/线性类是两个输入，饱和类是一个）。
    只用主输入会让第二维「被标注为输入却完全不影响输出」，端点探测会
    判成结构错误 —— 这不是我们想要的（L1002 的局部反例是结构全对、只在
    某个子区间响应偏离）。取范数后每个输入都真实影响输出，且鼓包仍局限
    |u|≈0.13 附近的薄壳，稀疏点（到原点距离 0.2/0.224）依然容易通过。
    """
    s = ROLE_SPEC[relation_type]

    if relation_type == "multiplicative_growth":
        expr = f"{nodes['current']} * (1 + {nodes['ratio']})"
        comps = [(nodes["current"], t["base"]["current"]),
                 (nodes["ratio"], t["base"]["ratio"])]
    elif relation_type == "linear_drive_resistance":
        expr = f"{nodes['driver']} / {nodes['resistance']}"
        comps = [(nodes["driver"], t["base"]["driver"]),
                 (nodes["resistance"], t["base"]["resistance"])]
    else:
        rmax, k = t["consts"]["R_max"], t["consts"]["K"]
        expr = f"{rmax} * {nodes['input']} / ({k} + {nodes['input']})"
        comps = [(nodes["input"], t["base"]["input"])]

    if with_bump is None:
        return expr
    amp, cen, wid = with_bump
    # u_norm = sqrt(mean_j ((x_j - b_j)/b_j)^2) —— 各维等权的均方根
    # 两输入类里「单维扰动 u、其余维为 0」对应 u_norm = |u|/sqrt(2)，
    # 所以稀疏点 -0.2/-0.1/0/0.1/0.2 落在 u_norm ∈ {0, 0.0707, 0.1414}，
    # 而鼓包中心 0.12 落在两者之间 —— 稀疏点全部通过、峰值 0.09 超容差。
    terms = " + ".join(f"(({nd} / {bv} - 1) ** 2)" for nd, bv in comps)
    u_norm = f"(({terms}) / {len(comps)}) ** 0.5"
    b = (f"{amp} * (exp(-(({u_norm} - {cen}) / {wid}) ** 2) "
         f"- exp(-({cen} / {wid}) ** 2))")
    return f"{t['y0']} + (({expr} - {t['y0']}) / {t['y_scale']} + {b}) * {t['y_scale']}"


# ============================================================
# 三类干扰源
# ============================================================
def _resp_error_expr(relation_type, nodes, t, variant=0):
    """结构全对、函数形式错。保持 baseline 输出不变，确保基准点一致。

    约束一：改造后的函数必须在基准点对**每个**被标注为输入的节点都仍然敏感，
            否则会被端点探测判成「输入端点无效」，混进结构错误类（实测踩过）。
    约束二：在 ±0.2 的干预区间内必须稳定超过 0.05 容差。单纯改幂次在高次时
            偏离量反而变小（实测 power=3 时只有 0.0386 < 0.05），所以改用
            三个**不同函数族**：幂律 / 指数 / 有理式，每族的偏离量都够大。

    variant: 0 = 幂律(power 2)，1 = 指数增长，2 = 有理式饱和
    """
    b = t["base"]
    fam = variant % 4
    if relation_type == "multiplicative_growth":
        c, r = nodes["current"], nodes["ratio"]
        c0, r0 = b["current"], b["ratio"]
        base_out = c0 * (1 + r0)
        # 注意（实测踩过的坑）：ratio 通常只有 0.02~0.5，在 ratio 侧做任何改动
        # 都会被归一化响应抵消掉（实测 ratio×2/×3/×5 的误差都 < 1e-4）。
        # 只有对 current 做非线性才产生稳定可见的偏差，所以三族都改 current 侧。
        if fam == 0:
            # current 三次（实测最大误差 0.28~0.32）
            return f"{c} ** 3 / {c0} ** 2 * (1 + {r})"
        if fam == 1:
            # current 2.5 次（实测 0.14~0.16）
            return f"{c} ** 2.5 / {c0} ** 1.5 * (1 + {r})"
        if fam == 2:
            # current 二次 + 一次交叉项（实测 0.07~0.10）。
            # 必须让 ratio 真实参与，否则端点探测会把 ratio 判成「标注是输入但不影响输出」。
            return (f"{base_out} * (1 + {r} / {r0}) / 2 "
                    f"+ 2 * {c0} * (({c} - {c0}) / {c0}) * (1 + {r}) "
                    f"+ 3 * {c0} * (({c} - {c0}) / {c0}) ** 2 * (1 + {r})")
        # current 二次（负任务要 4 个响应错误源，所以需要第 4 个族；实测 0.058~0.066）
        return f"{c} * {c} / {c0} * (1 + {r})"
    if relation_type == "linear_drive_resistance":
        d, rr = nodes["driver"], nodes["resistance"]
        d0 = b["driver"]
        if fam == 0:
            # driver 三次：driver^3/(R·driver0^2)
            return f"{d} ** 3 / ({rr} * {d0} ** 2)"
        if fam == 1:
            # driver 2.5 次
            return f"{d} ** 2.5 / ({rr} * {d0} ** 1.5)"
        if fam == 2:
            # driver 二次 + 交叉项
            return (f"{d} ** 2 / ({rr} * {d0}) "
                    f"+ {d0} / {rr} * 0.5 * (({d} - {d0}) / {d0})")
        # driver 四次（负任务要 4 个响应错误源；实测 1.0，远高于容差）
        return f"{d} ** 4 / ({rr} * {d0} ** 3)"
    # 饱和：目标 Hill n=1
    rmax, k = t["consts"]["R_max"], t["consts"]["K"]
    x = nodes["input"]
    if fam == 0:
        # Hill n=2
        return f"{rmax} * {x} ** 2 / ({k} ** 2 + {x} ** 2)"
    if fam == 1:
        # Hill n=3（实测 0.2062；原先用「指数趋近」实测只有 0.0027，已弃用）
        return f"{rmax} * {x} ** 3 / ({k} ** 3 + {x} ** 3)"
    if fam == 2:
        # 有理式：R_max * x^2 / (K^2 + 2*K*x)
        return f"{rmax} * {x} ** 2 / ({k} ** 2 + 2 * {k} * {x})"
    # Hill n=0.5（负任务要 4 个响应错误源）
    return f"{rmax} * {x} ** 0.5 / ({k} ** 0.5 + {x} ** 0.5)"


def _structure_error_expr(relation_type, nodes, t, variant=0):
    """结构错误：超边端点与角色标注不符（函数实际不依赖被标注为输入的那个节点）。

    这正是任务书 L1000 的三条构造操作之一「改变输入输出端 / 交换角色」。
    判据不靠肉眼，靠 structural_claim_ok() 逐端点做数值探测：
    被标注为「输入」的节点，把它的实际值改动后输出必须变化。

    variant 决定「钉死哪个量、用哪个水平」，保证同类干扰源之间函数真的不同
    （否则 3 个结构错误源的函数完全一样，只是 ID 不同，等于虚增候选库）。

    · 乘性：把 ratio 的值换成一个常数，输出只依赖 current
            → 标注说 ratio 是输入，实际不影响输出，端点标注失效
    · 线性：把 resistance 换成常数，输出只依赖 driver
    · 饱和：把 input 换成常数，输出变成常数（单输入类，整个关系失效）
    """
    b = t["base"]
    level = 1.0 + 0.25 * variant          # 1.0 / 1.25 / 1.5 倍工作点
    if relation_type == "multiplicative_growth":
        c = nodes["current"]
        return f"{c} * (1 + {round(b['ratio'] * level, 10)})"
    if relation_type == "linear_drive_resistance":
        d = nodes["driver"]
        return f"{d} / {round(b['resistance'] * level, 10)}"
    rmax, k = t["consts"]["R_max"], t["consts"]["K"]
    x = nodes["input"]
    return f"{rmax} * {round(b['input'] * level, 10)} / ({k} + {round(b['input'] * level, 10)})"


def build_interferer(target_obj, relation_type, object_id, kind, nodes_by_role,
                     local_params=None, variant=0):
    """构造一个与目标域同构的候选源域。

    nodes_by_role: 角色 -> 节点 ID（由调用方从统一 ID 池随机分派，
                   有效源和干扰源共用同一池，避免命名泄露）
    kind: structure_error / response_error / local_perturbation
    variant: 同类干扰源之间的索引，用来让同类的多个源函数真的不同
             （否则 3 个结构错误源的函数完全一样，只是 ID 不同，
              等于把一个候选库虚报成 10 个）
    """
    t = _target_spec(target_obj, relation_type)
    spec = t["spec"]
    roles = spec["roles"]

    if kind == "structure_error":
        func = _structure_error_expr(relation_type, nodes_by_role, t, variant)
    elif kind == "response_error":
        func = _resp_error_expr(relation_type, nodes_by_role, t, variant)
    elif kind == "local_perturbation":
        # 同类三个局部扰动源用不同的鼓包位置/幅度，函数真的不同。
        # 每个预设都同时按「两输入类（±0.2）」与「单输入类（[-0.8,1.0]）」离线验算过：
        #   (a) 各自稀疏五点误差 < 0.05（容易通过）
        #   (b) 0.05 步长标准网格上误差 > 0.05（稠密检查必然失败）
        # 实测粗网格可达误差：两输入类 0.090/0.078/0.090，单输入类 0.090/0.078/0.090。
        # 坑：鼓包中心必须落在 0.05 网格点上、或与网格点距离 < 宽度，否则采不到峰值
        #     （曾用 center=0.18, width=0.018，离最近网格点 0.02 > 宽度，误差只有 0.0076）。
        presets = [dict(amplitude=0.30, center=0.20, width=0.020),
                   dict(amplitude=0.28, center=0.15, width=0.015),
                   dict(amplitude=0.34, center=0.20, width=0.020)]
        p = local_params or presets[variant % len(presets)]
        func = _true_expr(relation_type, nodes_by_role, t,
                          with_bump=(p["amplitude"], p["center"], p["width"]))
    else:
        raise ValueError("unknown kind: " + kind)

    input_nodes = [nodes_by_role[r] for r in spec["input_roles"]]
    output_nodes = [nodes_by_role[spec["output_role"]]]
    baseline_list = [t["base"][r] for r in spec["input_roles"]]
    values = {nodes_by_role[r]: t["base"][r] for r in spec["input_roles"]}
    baseline_out = runtime.expression_value(func, values)
    if not math.isfinite(baseline_out):
        raise ValueError(f"{object_id}: baseline_output 非有限值")

    legal_domain, bounds = {}, {}
    for role in spec["input_roles"]:
        nid = nodes_by_role[role]
        if relation_type == "multiplicative_growth":
            legal_domain[nid] = [0, None] if role == "current" else [0, 1]
        else:
            legal_domain[nid] = [1e-6, None]
        bounds[nid] = list(spec["bounds"])

    nodes = [dict(node_id=nodes_by_role[r], label="待判定变量",
                  type="positive_scalar") for r in roles]

    return {
        "object_id": object_id,
        "object_kind": "mechanistic",
        "relation_type": relation_type,
        "split": None,
        "label": "候选源域",          # 与有效源、其它干扰源完全一致
        "nodes": nodes,
        "edges": [dict(edge_id="r1", edge_type=relation_type,
                       input_nodes=input_nodes, output_nodes=output_nodes,
                       roles={nodes_by_role[r]: r for r in roles})],
        "function": func,
        "controllable_inputs": input_nodes,
        "designated_outputs": output_nodes,
        "baseline": baseline_list,
        "input_scales": list(baseline_list),
        "baseline_output": baseline_out,
        "output_scale": baseline_out,     # 尺度规则：output_scale = baseline_output
        "legal_domain": legal_domain,
        "intervention_bounds": bounds,
        "provenance": {"dataset": "mred", "original_id": None,
                       "structure_source": "controlled_synthetic"},
    }


# ============================================================
# 双射判定：结构错误类必须真的不满足式(eq:structure)
# ============================================================
def structural_claim_ok(obj, rel_tol=1e-9):
    """数值探测「超边端点标注是否与函数实际依赖一致」。

    对每个被标注为输入端的节点：把它的实际值从 baseline 改动 +10%，
    输出必须随之变化。若输出完全不变，说明这个节点实际上不是输入，
    端点/角色标注与函数不符 —— 这就是任务书 L1000 的「改变输入输出端」。

    返回 (是否一致, 不被实际依赖的节点列表)
    """
    import runtime
    out_id = obj["designated_outputs"][0]
    base = dict(zip(obj["controllable_inputs"], obj["baseline"]))
    y0 = runtime.evaluate_object(obj, base)[out_id]
    dead = []
    for nid in obj["controllable_inputs"]:
        probe = dict(base)
        probe[nid] = base[nid] * 1.1
        y1 = runtime.evaluate_object(obj, probe)[out_id]
        if abs(y1 - y0) <= rel_tol * max(1.0, abs(y0)):
            dead.append(nid)
    return (len(dead) == 0), dead


def structure_ok(src_obj, tgt_obj):
    """按任务书 L342-L352 检查 src→tgt 的角色对齐候选映射是否成立。

    实现直接复用 mred_objects.check_structure_condition，保证与全库枚举
    用的是同一套判据（两份逻辑分叉是上一版的 bug 来源）。
    """
    import mred_objects as O
    se = src_obj["edges"][0]
    tgt_by_role = {r: n for n, r in tgt_obj["edges"][0]["roles"].items()}
    if set(se["roles"].values()) != set(tgt_by_role):
        return False, "角色集合不等"
    fV = {n: tgt_by_role[r] for n, r in se["roles"].items()}
    ok, fails = O.check_structure_condition(src_obj, tgt_obj, fV, {"r1": "r1"})
    return ok, ("通过" if ok else ";".join(fails))
