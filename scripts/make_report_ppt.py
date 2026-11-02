"""生成 TopoAdv 项目工作汇报 PPT（A 角色）。

只讲"已经做了什么"，8 页，数字全部来自实测。
运行：.venv/Scripts/python.exe scripts/make_report_ppt.py
文件被 Office 打开时无法覆盖，可先输出到别处：
  PPT_OUT='C:\\Users\\ASUS\\AppData\\Local\\Temp\\_x.pptx' .venv/Scripts/python.exe scripts/make_report_ppt.py
"""
import glob
import json
import os
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "docs" / "TopoAdv-A角色工作汇报.pptx"
OUT = Path(os.environ.get("PPT_OUT") or DEFAULT_OUT)

DARK = RGBColor(0x1F, 0x2A, 0x37)
GREY = RGBColor(0x5B, 0x66, 0x72)
ACCENT = RGBColor(0x1D, 0x6F, 0xB8)
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
    for i, ln in enumerate(body.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = spacing
        r = p.add_run()
        r.text = ln
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.color.rgb = color
        r.font.name = "微软雅黑"


def title(s, main, sub=None):
    text(s, 0.7, 0.45, 12, 0.7, main, 30, True, DARK)
    bar = s.shapes.add_shape(1, Inches(0.7), Inches(1.2), Inches(1.6), Inches(0.055))
    bar.fill.solid()
    bar.fill.fore_color.rgb = ACCENT
    bar.line.fill.background()
    if sub:
        text(s, 0.7, 1.35, 12, 0.4, sub, 14, False, GREY)


def table(s, x, y, w, rows, col_w, size=14, row_h=0.5):
    shp = s.shapes.add_table(len(rows), len(rows[0]), Inches(x), Inches(y),
                             Inches(w), Inches(row_h * len(rows)))
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
            c.fill.solid()
            if i == 0:
                p.font.bold = True
                p.font.color.rgb = WHITE
                c.fill.fore_color.rgb = ACCENT
            else:
                p.font.color.rgb = DARK
                c.fill.fore_color.rgb = WHITE


def stat():
    v = json.loads((ROOT / "T01-vocabulary.json").read_text(encoding="utf-8"))
    sc = json.loads((ROOT / "T01-schema.json").read_text(encoding="utf-8"))
    return dict(
        records=len(sc["records"]),
        node_types=len(v["node_types"]),
        edge_types=len(v["edge_types"]),
        mred=len(glob.glob(str(ROOT / "cases/*/group_tr_*"))),
        scar=len(glob.glob(str(ROOT / "cases/structural_scar/group_scar_*"))),
        scan=len(glob.glob(str(ROOT / "cases/structural_scan/group_scan_*"))),
        objs=len(glob.glob(str(ROOT / "cases/*/group_tr_*/data/input/objects/obj_*.json"))),
    )


S = stat()

# 1 封面
s = slide()
band = s.shapes.add_shape(1, 0, Inches(2.45), prs.slide_width, Inches(2.3))
band.fill.solid()
band.fill.fore_color.rgb = ACCENT
band.line.fill.background()
text(s, 0.9, 2.8, 11.5, 0.9, "TopoAdv 项目工作汇报", 40, True, WHITE)
text(s, 0.9, 3.65, 11.5, 0.6, "A 角色（裁判 / 数据）", 20, False, WHITE)
text(s, 0.9, 5.2, 11.5, 0.5, "2026-11-02", 14, False, GREY)

# 2 工作概览
s = slide()
title(s, "工作概览")
table(s, 0.7, 1.9, 11.9, [
    ["任务", "内容", "状态"],
    ["T01", "统一对象 schema、类型词表、样例", "完成"],
    ["T02", "MRED 构造 + SCAR 适配 + SCAN 适配", "完成"],
    ["T06", "独立评价器（结构指标）", "完成"],
    ["T05", "SME 基线适配", "未开始"],
    ["T11–T14", "汇总与复现", "待方法就位"],
], [1.6, 8.0, 2.3], size=15, row_h=0.6)

# 3 T01
s = slide()
title(s, "T01 统一对象与评价协议", "三人共同")
text(s, 0.9, 1.95, 11.6, 2.6,
     "交付三件套\n\n"
     "· T01-schema.json        %d 类记录（object / task / reference / candidate 等）\n"
     "· T01-vocabulary.json    节点类型 %d 类、关系类型 %d 类\n"
     "· T01-examples.json      各类记录样例"
     % (S["records"], S["node_types"], S["edge_types"]),
     18, False, DARK, spacing=1.45)
text(s, 0.9, 4.95, 11.6, 1.3,
     "已定的口径：\n"
     "· 映射方向 source→target\n"
     "· 概念原词公开（题目），对应关系封存（答案）",
     17, False, DARK, spacing=1.3)

# 4 T02 三个数据集
s = slide()
title(s, "T02 数据：三个数据集", "任务书 tab:data，三者并列、互不派生")
table(s, 0.7, 1.85, 11.9, [
    ["数据集", "原始材料", "产出", "划分"],
    ["MRED（自建）", "25 个真实域对 × 参数变体",
     "%d 组 / 600 任务 / %d 对象" % (S["mred"], S["objs"]), "210 / 42 / 48"],
    ["SCAR", "400 条科学类比", "%d 组（排除 22）" % S["scar"], "265 / 57 / 56"],
    ["SCAN", "451 行 / 65 个映射对", "%d 组（排除 0）" % S["scan"], "46 / 10 / 9"],
], [2.4, 4.0, 3.5, 2.0], size=14, row_h=0.62)
text(s, 0.7, 4.9, 11.9, 1.6,
     "SCAR / SCAN 无响应函数，按任务书 L957 采用结构模式：\n"
     "只做结构与解释评价，不为它们编造公式。",
     16, False, GREY, spacing=1.4)

# 5 T02 配套材料
s = slide()
title(s, "T02 配套材料")
text(s, 0.9, 1.95, 11.6, 4.4,
     "· 独立参考标注      600 条任务级记录，与对象文件分开存放\n"
     "· 分组清单          splits.csv，%d 组\n"
     "· 正负依据          负任务的排除记录均有见证点\n"
     "· 结构标注          SCAR 1922 / SCAN 598 个概念词逐词标类型，缺口 0\n"
     "· 数据说明          MRED / SCAR / SCAN 各一份\n"
     "· 派生实例          同一原始类比衍生的组，划分时保持同组（跨划分 0）"
     % S["mred"],
     18, False, DARK, spacing=1.7)

# 6 T06 评价器
s = slide()
title(s, "T06 独立评价器")
table(s, 0.7, 1.9, 11.9, [
    ["数据集", "判据", "项数", "正确映射"],
    ["MRED", "双射 / 类型 / 端点 / 角色", "11 或 9", "300 / 300"],
    ["SCAR", "对应集合 + 类型对应模式", "2", "378 / 378"],
    ["SCAN", "对应集合 + 类型对应模式", "2", "65 / 65"],
], [1.8, 5.4, 2.4, 2.3], size=15, row_h=0.62)
text(s, 0.7, 4.9, 11.9, 1.6,
     "产出 metrics_per_task.csv（逐任务 SF / SIPR / 错误归因）。\n"
     "错误映射（恒等、循环、空映射）均不满分。",
     16, False, GREY, spacing=1.4)

# 7 验收
s = slide()
title(s, "验收")
table(s, 0.7, 1.9, 11.9, [
    ["工具", "作用", "结果"],
    ["verify_mred / scar / scan", "独立验收，不与生成器共用逻辑", "全部通过"],
    ["mutation_test", "改坏数据验证守卫会报错", "10 / 10"],
    ["pytest", "回归测试", "83 passed"],
    ["check_data_doc", "数据说明九项核对", "全部通过"],
    ["check_m01_m08", "8 项交付验收条件", "全部通过"],
], [4.2, 6.0, 1.7], size=14, row_h=0.6)

# 8 收尾
s = slide()
band = s.shapes.add_shape(1, 0, Inches(2.5), prs.slide_width, Inches(2.2))
band.fill.solid()
band.fill.fore_color.rgb = ACCENT
band.line.fill.background()
text(s, 0.9, 2.85, 11.5, 0.9, "T01、T02、T06 已完成", 34, True, WHITE)
text(s, 0.9, 3.75, 11.5, 0.6, "数据与评价协议可交付，方法接入后即可跑 E01/E02", 18, False, WHITE)

OUT.parent.mkdir(parents=True, exist_ok=True)
prs.save(OUT)
print("saved", OUT)
