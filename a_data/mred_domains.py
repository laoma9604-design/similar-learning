"""MRED 25 个真实域对的结构化定义（机器可读，权威源 = data/MRED域对规格.md）。

只放数据，不含逻辑。生成器从这里取域对，避免规格表与生成结果脱节。
"""

REL_MULT = "multiplicative_growth"
REL_LIN = "linear_drive_resistance"
REL_SAT = "saturation_response"


def mult_domain(object_label, names, baseline):
    """names: current/ratio/next 三个角色的展示名。baseline: 同键。"""
    return dict(object_label=object_label, names=names, baseline=baseline)


def lin_domain(object_label, names, baseline):
    return dict(object_label=object_label, names=names, baseline=baseline)


def sat_domain(object_label, names, baseline, R_max, K):
    """饱和类：input0 必须 = K（半饱和点），由生成器断言。"""
    return dict(object_label=object_label, names=names, baseline=baseline, R_max=R_max, K=K)


# ============================================================
# 一、乘性增长 9 个：next = current * (1 + ratio)
# ============================================================
MULT_PAIRS = [
    dict(pair_id="mult_01",
         source=mult_domain("细菌二分裂", {"current": "当前细菌数量", "ratio": "每代增长率", "next": "下一代数量"},
                            {"current": 1000, "ratio": 0.1}),
         target=mult_domain("银行复利", {"current": "当前本金", "ratio": "本期利率", "next": "下一期余额"},
                            {"current": 5000, "ratio": 0.1}),
         evidence="源=细菌二分裂增殖；目标=复利公式。跨域：生物→金融。",
         assumption=None),
    dict(pair_id="mult_02",
         source=mult_domain("细胞培养", {"current": "细胞数量", "ratio": "传代增长率", "next": "传代后数量"},
                            {"current": 10000, "ratio": 0.2}),
         target=mult_domain("定期存款", {"current": "存款本金", "ratio": "年利率", "next": "到期本息"},
                            {"current": 20000, "ratio": 0.03}),
         evidence="源=细胞传代增殖；目标=定期存款复利。跨域：生物→金融。",
         assumption=None),
    dict(pair_id="mult_03",
         source=mult_domain("酵母发酵", {"current": "酵母数量", "ratio": "每代增长率", "next": "下一代数量"},
                            {"current": 5000, "ratio": 0.15}),
         target=mult_domain("债券票息", {"current": "债券面值", "ratio": "票息率", "next": "复投后本金"},
                            {"current": 100000, "ratio": 0.04}),
         evidence="源=酵母增殖；目标=债券票息复投。跨域：生物→金融。",
         assumption=None),
    dict(pair_id="mult_04",
         source=mult_domain("藻类繁殖", {"current": "藻细胞数", "ratio": "增长率", "next": "下一代数量"},
                            {"current": 2000, "ratio": 0.25}),
         target=mult_domain("教育储蓄", {"current": "储蓄本金", "ratio": "年利率", "next": "到期本息"},
                            {"current": 30000, "ratio": 0.03}),
         evidence="源=藻类增殖；目标=教育储蓄复利。跨域：生物→金融。",
         assumption=None),
    dict(pair_id="mult_05",
         source=mult_domain("人口增长", {"current": "人口数", "ratio": "年增长率", "next": "次年人口"},
                            {"current": 1000000, "ratio": 0.02}),
         target=mult_domain("年金账户", {"current": "账户余额", "ratio": "年利率", "next": "年末余额"},
                            {"current": 500000, "ratio": 0.06}),
         evidence="源=人口指数增长；目标=年金账户复利累积。跨域：人口→金融。",
         assumption="增长率/利率稳定"),
    dict(pair_id="mult_06",
         source=mult_domain("兔子种群", {"current": "兔子数", "ratio": "繁殖增长率", "next": "下一代数量"},
                            {"current": 100, "ratio": 0.3}),
         target=mult_domain("分红再投", {"current": "持股数", "ratio": "分红再投比例", "next": "分红后持股"},
                            {"current": 500, "ratio": 0.02}),
         evidence="源=兔子繁殖；目标=股票分红再投资。跨域：生物→金融。",
         assumption=None),
    dict(pair_id="mult_07",
         source=mult_domain("病毒复制", {"current": "病毒数量", "ratio": "每代复制增长率", "next": "下一代数量"},
                            {"current": 1000, "ratio": 0.5}),
         target=mult_domain("基金净值", {"current": "单位净值", "ratio": "每期收益率", "next": "下期净值"},
                            {"current": 1.0, "ratio": 0.08}),
         evidence="源=病毒复制增殖；目标=基金净值复利。跨域：生物→金融。",
         assumption=None),
    dict(pair_id="mult_08",
         source=mult_domain("肿瘤细胞", {"current": "肿瘤细胞数", "ratio": "增长率", "next": "下一代数量"},
                            {"current": 1000, "ratio": 0.4}),
         target=mult_domain("信用卡债务", {"current": "欠款金额", "ratio": "月利率", "next": "滚存后欠款"},
                            {"current": 5000, "ratio": 0.02}),
         evidence="源=肿瘤细胞增殖；目标=信用卡复利债务。跨域：生物→金融。",
         assumption=None),
    dict(pair_id="mult_09",
         source=mult_domain("中子增殖", {"current": "中子数", "ratio": "净增殖系数", "next": "下一代数量"},
                            {"current": 100, "ratio": 0.05}),
         target=mult_domain("通胀物价", {"current": "物价指数", "ratio": "通胀率", "next": "下期物价"},
                            {"current": 100, "ratio": 0.03}),
         evidence="源=中子链式反应；目标=通胀物价指数。跨域：物理→经济。",
         assumption=None),
]

# ============================================================
# 二、线性驱动-阻力 8 个：response = driver / resistance
# ============================================================
LIN_PAIRS = [
    dict(pair_id="lin_01",
         source=lin_domain("电路", {"driver": "电压", "resistance": "电阻", "response": "电流"},
                           {"driver": 10, "resistance": 2}),
         target=lin_domain("水流", {"driver": "压差", "resistance": "流阻", "response": "流量"},
                           {"driver": 8, "resistance": 4}),
         evidence="源=欧姆定律 I=V/R；目标=泊肃叶/达西定律 Q=ΔP/R。跨域：电→流体。",
         assumption=None),
    dict(pair_id="lin_02",
         source=lin_domain("电路", {"driver": "电压", "resistance": "电阻", "response": "电流"},
                           {"driver": 12, "resistance": 3}),
         target=lin_domain("热传导", {"driver": "温差", "resistance": "热阻", "response": "热流"},
                           {"driver": 24, "resistance": 6}),
         evidence="源=欧姆定律；目标=傅里叶热传导 q=ΔT/Rth。跨域：电→热。",
         assumption=None),
    dict(pair_id="lin_03",
         source=lin_domain("电路", {"driver": "电压", "resistance": "电阻", "response": "电流"},
                           {"driver": 9, "resistance": 3}),
         target=lin_domain("扩散", {"driver": "浓度差", "resistance": "扩散阻力", "response": "扩散通量"},
                           {"driver": 6, "resistance": 2}),
         evidence="源=欧姆定律；目标=菲克扩散 J=ΔC/Rd。跨域：电→传质。",
         assumption=None),
    dict(pair_id="lin_04",
         source=lin_domain("电路", {"driver": "电压", "resistance": "电阻", "response": "电流"},
                           {"driver": 15, "resistance": 5}),
         target=lin_domain("力学阻尼", {"driver": "力", "resistance": "阻尼系数", "response": "速度"},
                           {"driver": 12, "resistance": 4}),
         evidence="源=欧姆定律；目标=线性阻尼 v=F/c。跨域：电→力学。",
         assumption=None),
    dict(pair_id="lin_05",
         source=lin_domain("电路", {"driver": "电压", "resistance": "电阻", "response": "电流"},
                           {"driver": 8, "resistance": 2}),
         target=lin_domain("磁路", {"driver": "磁动势", "resistance": "磁阻", "response": "磁通"},
                           {"driver": 16, "resistance": 4}),
         evidence="源=欧姆定律；目标=磁路欧姆定律 Φ=Fm/Rm。跨域：电→磁。",
         assumption=None),
    dict(pair_id="lin_06",
         source=lin_domain("电路", {"driver": "电压", "resistance": "电阻", "response": "电流"},
                           {"driver": 10, "resistance": 2}),
         target=lin_domain("血流", {"driver": "血压差", "resistance": "血管阻力", "response": "血流量"},
                           {"driver": 100, "resistance": 20}),
         evidence="源=欧姆定律；目标=血流阻力 Q=ΔP/Rv。跨域：电→生理。",
         assumption=None),
    dict(pair_id="lin_07",
         source=lin_domain("电路", {"driver": "电压", "resistance": "电阻", "response": "电流"},
                           {"driver": 6, "resistance": 3}),
         target=lin_domain("渗流", {"driver": "压力梯度", "resistance": "渗透阻力", "response": "渗流速度"},
                           {"driver": 8, "resistance": 4}),
         evidence="源=欧姆定律；目标=达西渗流。跨域：电→多孔介质流体。",
         assumption=None),
    dict(pair_id="lin_08",
         source=lin_domain("热传导", {"driver": "温差", "resistance": "热阻", "response": "热流"},
                           {"driver": 30, "resistance": 5}),
         target=lin_domain("扩散", {"driver": "浓度差", "resistance": "扩散阻力", "response": "扩散通量"},
                           {"driver": 12, "resistance": 2}),
         evidence="源=傅里叶热传导；目标=菲克扩散。跨域：热→传质（同为梯度驱动输运）。",
         assumption=None),
]

# ============================================================
# 三、饱和响应 8 个：response = R_max * input / (K + input)
#    约束：input0 = K
# ============================================================
SAT_PAIRS = [
    dict(pair_id="sat_01",
         source=sat_domain("酶催化", {"input": "底物浓度", "response": "反应速率"},
                           {"input": 1.0}, R_max=10.0, K=1.0),
         target=sat_domain("吸附", {"input": "平衡浓度", "response": "吸附量"},
                           {"input": 2.0}, R_max=20.0, K=2.0),
         evidence="源=Michaelis-Menten 酶动力学；目标=Langmuir 吸附等温线。跨域：生化→物理化学。",
         assumption=None),
    dict(pair_id="sat_02",
         source=sat_domain("酶催化", {"input": "底物浓度", "response": "反应速率"},
                           {"input": 1.0}, R_max=10.0, K=1.0),
         target=sat_domain("Monod生长", {"input": "底物浓度", "response": "比生长速率"},
                           {"input": 0.5}, R_max=2.0, K=0.5),
         evidence="源=米氏方程；目标=Monod 生长方程 mu=mu_max*S/(Ks+S)。跨域：生化→微生物。",
         assumption=None),
    dict(pair_id="sat_03",
         source=sat_domain("酶催化", {"input": "底物浓度", "response": "反应速率"},
                           {"input": 1.0}, R_max=10.0, K=1.0),
         target=sat_domain("受体结合", {"input": "配体浓度", "response": "结合量"},
                           {"input": 10.0}, R_max=100.0, K=10.0),
         evidence="源=米氏方程；目标=受体-配体结合等温线。跨域：生化→细胞生物。",
         assumption=None),
    dict(pair_id="sat_04",
         source=sat_domain("酶催化", {"input": "底物浓度", "response": "反应速率"},
                           {"input": 1.0}, R_max=10.0, K=1.0),
         target=sat_domain("光合", {"input": "光强", "response": "光合速率"},
                           {"input": 200.0}, R_max=20.0, K=200.0),
         evidence="源=米氏方程；目标=光合光响应曲线。跨域：生化→植物生理。",
         assumption=None),
    dict(pair_id="sat_05",
         source=sat_domain("载体转运", {"input": "底物浓度", "response": "转运速率"},
                           {"input": 5.0}, R_max=50.0, K=5.0),
         target=sat_domain("葡萄糖重吸收", {"input": "血糖浓度", "response": "重吸收速率"},
                           {"input": 150.0}, R_max=375.0, K=150.0),
         evidence="源=载体介导饱和转运；目标=肾小管葡萄糖重吸收。跨域：同机制不同生理场景。",
         assumption=None),
    dict(pair_id="sat_06",
         source=sat_domain("离子通道", {"input": "配体浓度", "response": "开放概率"},
                           {"input": 10.0}, R_max=1.0, K=10.0),
         target=sat_domain("受体结合", {"input": "配体浓度", "response": "结合量"},
                           {"input": 5.0}, R_max=100.0, K=5.0),
         evidence="源=配体门控离子通道开放概率；目标=受体-配体结合。跨域：膜蛋白→信号通路。",
         assumption="离子通道配体门控实际常具协同（Hill n>1），此处取理想 n=1（非协同）模型，才套得上饱和响应模板"),
    dict(pair_id="sat_07",
         source=sat_domain("气体吸附", {"input": "气体分压", "response": "表面覆盖度"},
                           {"input": 5.0}, R_max=1.0, K=5.0),
         target=sat_domain("血红蛋白结合", {"input": "氧分压", "response": "氧饱和度"},
                           {"input": 3.5}, R_max=1.0, K=3.5),
         evidence="源=Langmuir 气体吸附；目标=肌红蛋白/单体血红蛋白氧合。跨域：物理→生理。",
         assumption="真实血红蛋白为四聚体、具协同（Hill n≈2.8）；此处取单体血红蛋白（肌红蛋白型，n=1）简化模型，非真实 Hb 四聚体"),
    dict(pair_id="sat_08",
         source=sat_domain("光合", {"input": "光强", "response": "光合速率"},
                           {"input": 200.0}, R_max=20.0, K=200.0),
         target=sat_domain("营养吸收", {"input": "营养浓度", "response": "吸收速率"},
                           {"input": 2.0}, R_max=10.0, K=2.0),
         evidence="源=光合光响应曲线；目标=肠道营养吸收饱和。跨域：植物生理→动物生理。",
         assumption=None),
]

ALL_PAIRS = {REL_MULT: MULT_PAIRS, REL_LIN: LIN_PAIRS, REL_SAT: SAT_PAIRS}

# ============================================================
# 变体配额（用户 2026-10-28 拍板：乘性、线性为主，饱和取常见档位适当扩充）
# ============================================================
VARIANT_QUOTA = {REL_MULT: 146, REL_LIN: 130, REL_SAT: 24}

SPLIT_SEED = 20261007
SPLIT_RATIOS = (0.70, 0.15, 0.15)
INTERVENTION_POINTS_PER_TEST_TASK = 100
INTERVENTION_SEED = 20261007


def summary():
    lines = [f"域对总数: {sum(len(v) for v in ALL_PAIRS.values())}"]
    for rel, pairs in ALL_PAIRS.items():
        lines.append(f"  {rel}: {len(pairs)} 个")
    lines.append("配额: " + ", ".join(f"{k}={v}" for k, v in VARIANT_QUOTA.items())
                 + f" (合计 {sum(VARIANT_QUOTA.values())})")
    return "\n".join(lines)


if __name__ == "__main__":
    print(summary())
