"""生成 TopoAdv 项目工作汇报 PPT（A 角色 / T01–T14 进度）。

尽量简洁：12 页，每页只讲一件事，数字全部来自实测。
运行：.venv/Scripts/python.exe scripts/make_report_ppt.py
"""
import json
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "TopoAdv-A角色工作汇报.pptx"

DARK = RGBColor(0x1F, 0x2A, 0x37)
GREY = RGBColor(0x5B, 0x66, 0x72)
ACCENT = RGBColor(0x1D, 0x6F, 0xB8)
RED = RGBColor(0xC0, 0x39, 0x2B)
GREEN = RGBColor(0x1E, 0x7D, 0x4F)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
BG = RGBColor(0xF5, 0xF7, 0xFA)

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]


def slide():
    s = prs.slides.add_slide(BLANK)
    bg = s.shapes.add_shape(1, 0, 0, prs.slide_width, prs.slide_height)
    bg.fill.solid()
    bg.fill.fore_color.rgb = BG
    bg.line.fill.background()
    bg.shadow.inherit = False
    return s


def text(s, x, y, w, h, body, size=18, bold=False, color=DARK,
         align=PP_ALIGN.LEFT, spacing=1.15):
    tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    lines = body.split("\n")
    for i, ln in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = spacing
        r = p.add_run()
        r.text = ln
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.color.rgb = color
        r.font.name = "微软雅黑"
    return tb


def title(s, main, sub=None):
    text(s, 0.7, 0.45, 12, 0.7, main, 30, True, DARK)
    bar = s.shapes.add_shape(1, Inches(0.7), Inches(1.2), Inches(1.6), Inches(0.055))
    bar.fill.solid()
    bar.fill.fore_color.rgb = ACCENT
    bar.line.fill.background()
    if sub:
        text(s, 0.7, 1.35, 12, 0.45, sub, 14, False, GREY)


def table(s, x, y, w, rows, col_w, head=True, size=13, row_h=0.4):
    nr, nc = len(rows), len(rows[0])
    shp = s.shapes.add_table(nr, nc, Inches(x), Inches(y), Inches(w),
                             Inches(row_h * nr))
    tbl = shp.table
    for j, cw in enumerate(col_w):
        tbl.columns[j].width = Inches(cw)
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            c = tbl.cell(i, j)
            c.text = str(val)
            p = c.text_frame.paragraphs[0]
            p.font.size = Pt(size)
            p.font.name = "微软雅黑"
            if head and i == 0:
                p.font.bold = True
                p.font.color.rgb = WHITE
                c.fill.solid()
                c.fill.fore_color.rgb = ACCENT
            else:
                p.font.color.rgb = DARK
                c.fill.solid()
                c.fill.fore_color.rgb = WHITE
    return tbl


# ---------- 读数：全部来自实测文件 ----------
def stat():
    import glob
    v = json.loads((ROOT / "T01-vocabulary.json").read_text(encoding="utf-8"))
    sc = json.loads((ROOT / "T01-schema.json").read_text(encoding="utf-8"))
    return dict(
        n_records=len(sc["records"]),
        n_node_types=len(v["node_types"]),
        n_edge_types=len(v["edge_types"]),
        mred=len(glob.glob(str(ROOT / "cases/*/group_tr_*"))),
        scar=len(glob.glob(str(ROOT / "cases/structural_scar/group_scar_*"))),
        scan=len(glob.glob(str(ROOT / "cases/structural_scan/group_scan_*"))),
        mred_obj=len(glob.glob(str(ROOT / "cases/*/group_tr_*/data/input/objects/obj_*.json"))),
    )


S = stat()

# ============ 1. 封面 ============
s = slide()
band = s.shapes.add_shape(1, 0, Inches(2.3), prs.slide_width, Inches(2.6))
band.fill.solid()
band.fill.fore_color.rgb = ACCENT
band.line.fill.background()
text(s, 0.9, 2.65, 11.5, 0.9, "TopoAdv 项目工作汇报", 40, True, WHITE)
text(s, 0.9, 3.55, 11.5, 0.6, "A 角色（裁判 / 数据）· T01–T14 完成情况", 20, False, WHITE)
text(s, 0.9, 5.3, 11.5, 0.5, "截至 2026-11-02", 14, False, GREY)

# ============ 2. 一句话结论 ============
s = slide()
title(s, "一句话结论")
text(s, 0.9, 1.9, 11.5, 1.2,
     "数据侧全部做完，评价器可用；方法侧一个候选都还没有。",
     26, True, DARK)
text(s, 0.9, 3.2, 11.5, 2.4,
     "· 三个数据集适配完成：MRED %d 组 / SCAR %d 组 / SCAN %d 组\n"
     "· 统一 schema + 词表 + 独立参考标注 + 分组清单齐备\n"
     "· 独立评价器能对三个数据集出数，正确映射全部满分\n"
     "· 卡点：B 的引擎、C 的 LLM 基线未开始 —— E01 目前只能自己考自己"
     % (S["mred"], S["scar"], S["scan"]),
     17, False, DARK, spacing=1.5)

# ============ 3. 三个数据集 ============
s = slide()
title(s, "三个数据集：提供什么、我们做了什么", "任务书 tab:data：三者并列，互不派生")
table(s, 0.7, 1.85, 11.9, [
    ["数据集", "原始材料", "适配结果", "评价方式"],
    ["MRED（自建）", "25 个真实域对 × 参数变体", "%d 组 / 600 任务 / %d 对象" % (S["mred"], S["mred_obj"]),
     "完整：结构 + 响应"],
    ["SCAR", "400 条科学类比（含解释）", "%d 组（排除 22）" % S["scar"],
     "结构模式 2 项"],
    ["SCAN", "451 行 / 65 个映射对", "%d 组（排除 0）" % S["scan"],
     "结构模式 2 项"],
], [2.6, 3.6, 3.4, 2.3], size=14, row_h=0.62)
text(s, 0.7, 4.9, 11.9, 1.6,
     "SCAR/SCAN 没有可执行函数，按任务书 L957 走“结构模式”：\n"
     "只做结构与解释评价，不执行响应搜索 —— 不给它们编造公式。",
     15, False, GREY, spacing=1.4)

# ============ 4. T01 ============
s = slide()
title(s, "T01 统一对象与评价协议", "三人共同 · 无前置依赖")
text(s, 0.9, 1.85, 5.6, 2.4,
     "交付三件套\n"
     "· T01-schema.json     %d 类记录\n"
     "· T01-vocabulary.json 节点类型 %d 类 / 关系类型 %d 类\n"
     "· T01-examples.json   样例对象"
     % (S["n_records"], S["n_node_types"], S["n_edge_types"]),
     17, False, DARK, spacing=1.6)
text(s, 6.9, 1.85, 5.8, 3.2,
     "定死的四条铁律\n"
     "· 映射方向一律 source→target\n"
     "· 答案隔离：概念原词是题目，哪个对哪个是答案\n"
     "· 稳定字符串 ID 关联，不依赖数组顺序\n"
     "· 参考标注先于调参固定",
     17, False, DARK, spacing=1.6)
text(s, 0.9, 5.6, 11.5, 0.6,
     "验收：schema 0.3.1（draft-v5），B/C 读取同一 ID 无歧义",
     14, False, GREEN)

# ============ 5. T02 ============
s = slide()
title(s, "T02 数据适配与构造", "A 主责（C 核对函数与尺度）")
table(s, 0.7, 1.8, 11.9, [
    ["交付项", "状态", "实测"],
    ["MRED 生成器 + 参数 + 函数 + 尺度 + 合法域", "完成", "300 组 / 600 任务"],
    ["MRED 正负依据（每个负任务有全库核验）", "完成", "全库排除记录 5700 条"],
    ["独立参考标注（另存，仅评价器可读）", "完成", "600 条"],
    ["分组清单", "完成", "splits.csv 300 行"],
    ["SCAR 适配", "完成", "378 组，划分 265/57/56"],
    ["SCAN 适配", "完成", "65 组，划分 46/10/9"],
    ["数据说明（任务书 L1555 九项）", "完成", "三份，逐项核对通过"],
], [6.4, 1.5, 4.0], size=13, row_h=0.5)

# ============ 6. 防泄漏 ============
s = slide()
title(s, "防泄漏：这是结构数据最容易死的地方")
text(s, 0.8, 1.75, 11.9, 0.6,
     "同一个原始类比衍生的实例，不能一个进训练、一个进测试。", 18, True, DARK)
table(s, 0.7, 2.55, 11.9, [
    ["数据集", "派生关系", "处理方式", "跨划分"],
    ["SCAR", "同一 system 出现多次", "连通块锁死", "0"],
    ["SCAN", "同一 target 或 source 复用", "连通块锁死", "0"],
    ["MRED", "同域对的参数变体", "按域对划分", "0"],
], [2.0, 4.4, 3.4, 1.9], size=14, row_h=0.55)
text(s, 0.7, 5.0, 11.9, 1.8,
     "SCAN 65 组聚成 30 个不可分块（最大块 10 组），因此划分是 46/10/9 而非精确 70/15/15。\n"
     "穷举证明这是该约束下的唯一可行解 —— 不是算法没调好。",
     15, False, GREY, spacing=1.4)

# ============ 7. T06 评价器 ============
s = slide()
title(s, "T06 独立评价器", "正确映射 SF/SIPR = 1；错误映射必须不满分")
table(s, 0.7, 1.8, 11.9, [
    ["数据集", "判据", "项数", "正确映射"],
    ["MRED", "机械六类（双射/类型/端点/角色）", "11 或 9", "300 / 300"],
    ["SCAR", "pair_consistency + type_pattern", "2（15 组含角色为 3）", "378 / 378"],
    ["SCAN", "pair_consistency + type_pattern", "2", "65 / 65"],
], [1.8, 5.6, 2.6, 1.9], size=14, row_h=0.55)
text(s, 0.7, 4.55, 11.9, 2.3,
     "为什么不用同一套判据：\n"
     "· SCAR/SCAN 有共享端点的多值对应，双射必然失败\n"
     "· 跨范畴对应是类比的核心机制，要求两端同类型会误伤正确答案\n"
     "  实测：硬套机械模式，SCAN 正确映射只有 8/65 满分\n\n"
     "交付：metrics_per_task.csv（逐任务）+ 8 组自检断言",
     15, False, DARK, spacing=1.45)

# ============ 8. 验收体系 ============
s = slide()
title(s, "怎么证明“做完了”：可复核的验收")
table(s, 0.7, 1.8, 11.9, [
    ["工具", "作用", "结果"],
    ["verify_mred / scar / scan", "独立验收器：不 import 生成器，自己重写判据", "全部通过"],
    ["mutation_test", "故意改坏数据，验证验收器真会报错", "10 / 10 抓到"],
    ["pytest", "回归测试，每条锁定一个曾发生的缺陷", "83 passed"],
    ["check_data_doc", "任务书 L1555 数据说明九项逐项核对", "scan / scar 全过"],
    ["check_m01_m08", "评审方给的 8 项交付验收条件", "全部通过"],
], [4.0, 6.4, 1.5], size=13, row_h=0.58)
text(s, 0.7, 5.2, 11.9, 1.6,
     "原则：生成器自报“全部通过”不算数 —— 验收器必须与被测代码不共享逻辑；\n"
     "新增检查项必须证明“改坏会报红”，只跑一遍绿不能说明检查项有用。",
     15, False, GREY, spacing=1.4)

# ============ 9. 我踩的坑 ============
s = slide()
title(s, "本轮修掉的三个真缺陷（都被“全部通过”掩盖过）")
text(s, 0.8, 1.7, 11.9, 4.6,
     "① 评价器调用方式错 → 结构数据集正例全部掉进机械模式\n"
     "   修前 SCAR 291/378、SCAN 57/65 的正确映射拿不到满分；修后均 1.0\n\n"
     "② schema 必填字段 available_checks 整批缺失\n"
     "   验收器原来一条都不查字段契约，现已新增 A6 组专门查\n\n"
     "③ 参考角色为空时回退去读候选的角色（等于自己给自己打分）\n"
     "   SCAN 凭空多出第 3 项，声明的 2 项与实算不符",
     16, False, DARK, spacing=1.5)
text(s, 0.8, 6.2, 11.9, 0.6,
     "共同点：都不是数据错，而是“验证手段没覆盖到的那一层”。", 15, True, RED)

# ============ 10. T11–T14 的处境 ============
s = slide()
title(s, "T11–T14：A 的活已就位，但缺输入", "任务书要求的前置条件")
table(s, 0.7, 1.8, 11.9, [
    ["任务", "前置", "现状"],
    ["T11 E01/E02 汇总", "T09 + T10 检查点", "评价器就绪，无方法候选"],
    ["T12 效率实验", "T09 + 固定候选", "数据侧可提供封存实例"],
    ["T13 解释与人工评分", "T11 最终映射", "量表可提前准备，需真人"],
    ["T14 汇总复现", "T11 + T12 + T13", "统计脚本待接入记录"],
], [3.2, 4.2, 4.5], size=14, row_h=0.58)
text(s, 0.7, 4.9, 11.9, 2.0,
     "T11 的前提是“有方法跑出来的候选”。B 的引擎与 C 的 LLM 基线未开始，\n"
     "所以 E01 目前只有参考映射自己 —— 这不能写进论文当结果。",
     15, False, GREY, spacing=1.5)

# ============ 11. 还缺什么 ============
s = slide()
title(s, "还缺什么（按卡不卡别人排序）")
text(s, 0.8, 1.8, 11.9, 4.8,
     "1. B/C 复核 SCAR/SCAN 适配\n"
     "   任务书 L984 要求“先适配 20 组、由 B/C 复核、规则稳定后再扩”。\n"
     "   两个数据集都跳过了这一步直接全量 —— 这是已知风险，已在文档写明。\n\n"
     "2. 清理旧格式样例\n"
     "   cases/structural/ 下 20 个文件已被正式适配取代，待确认后删除。\n\n"
     "3. E02 响应与返回指标\n"
     "   需要 C 的 audit.jsonl；SCAR/SCAN 无响应函数，该列记不适用。",
     16, False, DARK, spacing=1.5)

# ============ 12. 收尾 ============
s = slide()
band = s.shapes.add_shape(1, 0, Inches(2.4), prs.slide_width, Inches(2.4))
band.fill.solid()
band.fill.fore_color.rgb = ACCENT
band.line.fill.background()
text(s, 0.9, 2.7, 11.5, 0.9,
     "数据与评价协议已冻结，等引擎和基线接入", 30, True, WHITE)
text(s, 0.9, 3.6, 11.5, 0.7,
     "下一步：B/C 复核 →（B、C 的方法就位）→ E01/E02 正式跑数",
     18, False, WHITE)

OUT.parent.mkdir(parents=True, exist_ok=True)
prs.save(OUT)
print("saved", OUT)
print("slides", len(prs.slides.__iter__.__self__._sldIdLst))
