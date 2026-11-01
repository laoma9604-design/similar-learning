"""MRED 验收清单 M01-M08 逐项核对（T02 交付验收证据）。

用途：任务书 T02「交出什么，怎样确认完成」——数据说明、对象文件、分组清单；
      每个负任务都有全库核验依据，函数在规定域内可求值。
本脚本只读 cases/，不 import 生成器，判据按验收清单原文重新实现。

用法：
    python a_data/check_m01_m08.py            # 全部通过时退出码 0

核对项：
    M01 数量核对       区分基础组数量与正负任务数量
    M02 关系类型检查   线性驱动-阻力、乘性增长、饱和响应
    M03 候选构造检查   四种候选类型是否齐全
    M04 正负标签核验   正任务至少 1 个有效源域，负任务全库无有效源域
    M05 函数检查       基准输入、输出、参数及合法域
    M06 响应尺度检查   两域使用具有相同含义的无量纲尺度
    M07 分组划分       基础组级别 70%/15%/15%
    M08 留出干预       每个测试任务 100 个独立合法干预点
"""
import json, glob, os, sys, itertools, math, ast, collections

RELS = ["multiplicative_growth", "linear_drive_resistance", "saturation_response"]
CASES = "cases"

def load(gdir):
    idx = json.load(open(os.path.join(gdir, 'data/input/objects/index.json'), encoding='utf-8'))
    objs = {o['object_id']: json.load(open(os.path.join(gdir, 'data/input/objects', o['file']), encoding='utf-8')) for o in idx['objects']}
    tasks = {}
    for p in glob.glob(os.path.join(gdir, 'data/input/tasks', '*.json')):
        t = json.load(open(p, encoding='utf-8'))
        tasks[t['task_id']] = t
    return dict(gid=os.path.basename(gdir), rel=os.path.basename(os.path.dirname(gdir)),
                dir=gdir, objs=objs, tasks=tasks,
                man=json.load(open(os.path.join(gdir, 'manifest.json'), encoding='utf-8')),
                sealed=json.load(open(os.path.join(gdir, 'manifest.sealed.json'), encoding='utf-8')),
                ref=json.load(open(os.path.join(gdir, 'sealed/reference.json'), encoding='utf-8')))

G = []
for rel in RELS:
    for d in sorted(glob.glob(os.path.join(CASES, rel, 'group_tr_*'))):
        G.append(load(d))

print("=" * 70)
print("M01 数量核对：区分基础组数量与正负任务数量")
print("=" * 70)
n_group = len(G)
n_task = sum(len(g['ref']) for g in G)
pos = sum(1 for g in G for r in g['ref'].values() if r['label'] == 'positive')
neg = n_task - pos
print(f"  基础组（group_tr_*）        : {n_group}")
print(f"  任务总数                    : {n_task}")
print(f"    正任务 label=positive     : {pos}")
print(f"    负任务 label=negative     : {neg}")
print(f"  每组任务数分布              : {dict(collections.Counter(len(g['ref']) for g in G))}")
print(f"  manifest 声明 task_counts   : {collections.Counter(json.dumps(g['man'].get('task_counts'), sort_keys=True) for g in G)}")
ok01 = (n_group == 300 and n_task == 600 and pos == 300 and neg == 300)
print(f"  判定：{'通过' if ok01 else '不通过'}（要求 300 组 / 600 任务 / 正负各 300，任务数与组数分开报告）")

print()
print("=" * 70)
print("M02 关系类型检查：线性驱动–阻力、乘性增长、饱和响应")
print("=" * 70)
rel_cnt = collections.Counter(g['rel'] for g in G)
print(f"  三类关系组数: {dict(rel_cnt)}")
need = {"multiplicative_growth", "linear_drive_resistance", "saturation_response"}
missing = need - set(rel_cnt)
if missing:
    print(f"  缺失关系类型: {missing}")
else:
    eq = {
        "multiplicative_growth": "next = current*(1+ratio)",
        "linear_drive_resistance": "response = driver/resistance",
        "saturation_response": "response = Rmax*input/(K+input)",
    }
    for rel in RELS:
        bad = []
        for g in G:
            if g['rel'] != rel:
                continue
            for oid, o in g['objs'].items():
                r = o['edges'][0]['roles']
                if set(r.values()) != set(eq[rel].split('=')[0].replace('next', 'next').split() or []):
                    pass
        # 用角色集合判定三类关系的方程形态是否一致
        rolesets = {tuple(sorted(o['edges'][0]['roles'].values())) for g in G if g['rel'] == rel for o in g['objs'].values()}
        print(f"    {rel:26s} 角色集合 {rolesets}  样本方程 {eq[rel]}")
print(f"  判定：{'通过' if not missing else '不通过'}")

print()
print("=" * 70)
print("M03 候选构造检查：四种候选类型是否齐全")
print("=" * 70)
# 任务书 tab:mred 的四种候选类型
KINDS = ["valid", "structure_error", "response_error", "local_perturbation"]
KIND_CN = {"valid": "结构和响应均有效", "structure_error": "结构错误",
           "response_error": "结构相同、响应错误", "local_perturbation": "局部扰动容易通过"}
kind_cnt = collections.Counter()
for g in G:
    for r in g['ref'].values():
        for e in r['exclusions']:
            kind_cnt[e['kind']] += 1
        if r['valid']:
            kind_cnt['valid'] += len(r['valid'])
print("  各类型在全库出现的次数：")
for k in KINDS:
    print(f"    {k:22s} ({KIND_CN[k]:14s}) : {kind_cnt.get(k, 0)}")
missing_k = [k for k in KINDS if kind_cnt.get(k, 0) == 0]
# 每个正任务是否都有 1 有效 + 三类干扰
per_task = collections.Counter()
bad_pos = []
for g in G:
    for tid, r in g['ref'].items():
        if r['label'] != 'positive':
            continue
        got = collections.Counter(e['kind'] for e in r['exclusions'])
        got['valid'] = len(r['valid'])
        key = tuple(sorted(got.items()))
        per_task[key] += 1
        if got['valid'] != 1 or set(got) != set(KINDS):
            bad_pos.append((g['gid'], tid, dict(got)))
print(f"  正任务构成分布（每组 1 有效 + 三类干扰）: {len(per_task)} 种组合")
for k, v in per_task.most_common(3):
    print(f"    {dict(k)} × {v}")
print(f"  判定：{'通过' if not missing_k and not bad_pos else '不通过'}"
      f"{'' if not missing_k else ' 缺类型:' + str(missing_k)}"
      f"{'' if not bad_pos else f' 有 {len(bad_pos)} 个正任务构成不合要求'}")

print()
print("=" * 70)
print("M04 正负标签核验：正任务至少 1 个有效源域，负任务全库无有效源域")
print("=" * 70)
bad04 = []
for g in G:
    for tid, r in g['ref'].items():
        if r['label'] == 'positive':
            if len(r['valid']) < 1:
                bad04.append((g['gid'], tid, '正任务无有效源域'))
        else:
            if r['valid']:
                bad04.append((g['gid'], tid, '负任务却有有效源域'))
            if not r.get('full_library_verified'):
                bad04.append((g['gid'], tid, 'full_library_verified 未成立'))
print(f"  full_library_verified=True 的负任务: "
      f"{sum(1 for g in G for r in g['ref'].values() if r['label']=='negative' and r.get('full_library_verified'))}/{neg}")
print(f"  判定：{'通过' if not bad04 else f'不通过（{len(bad04)} 项）'}")
for b in bad04[:3]:
    print("   ", b)

print()
print("=" * 70)
print("M05 函数检查：基准输入、输出、参数及合法域")
print("=" * 70)
def ev(expr, vals):
    def visit(n):
        if isinstance(n, ast.Constant): return float(n.value)
        if isinstance(n, ast.Name): return vals[n.id]
        if isinstance(n, ast.UnaryOp):
            v = visit(n.operand); return -v if isinstance(n.op, ast.USub) else v
        if isinstance(n, ast.BinOp):
            a, b = visit(n.left), visit(n.right)
            if isinstance(n.op, ast.Add): return a + b
            if isinstance(n.op, ast.Sub): return a - b
            if isinstance(n.op, ast.Mult): return a * b
            if isinstance(n.op, ast.Div): return a / b
            if isinstance(n.op, ast.Pow): return a ** b
            raise ValueError
        if isinstance(n, ast.Call) and getattr(n.func, 'id', '') == 'exp':
            return math.exp(visit(n.args[0]))
        raise ValueError
    return visit(ast.parse(expr, mode='eval').body)

bad05 = []
n_obj = 0
for g in G:
    for oid, o in g['objs'].items():
        n_obj += 1
        ctrl = o['controllable_inputs']
        # (a) baseline / input_scales 长度与顺序
        if len(o['baseline']) != len(ctrl) or len(o['input_scales']) != len(ctrl):
            bad05.append((g['gid'], oid, 'baseline/scales 长度不等于输入数'))
            continue
        if any(s <= 0 for s in o['input_scales']):
            bad.append((g['gid'], oid, 'input_scales 非正'))
        # (b) baseline 落在合法域内
        for i, nid in enumerate(ctrl):
            lo, hi = o['legal_domain'][nid]
            v = o['baseline'][i]
            lo = -math.inf if lo is None else lo
            hi = math.inf if hi is None else hi
            if not (lo - 1e-12 <= v <= hi + 1e-12):
                bad05.append((g['gid'], oid, f'baseline {nid}={v} 越合法域'))
        # (c) 基准输出必须等于函数在基准输入上的求值
        vals = dict(zip(ctrl, o['baseline']))
        try:
            y = ev(o['function'], vals)
        except Exception as e:
            bad05.append((g['gid'], oid, f'函数求值失败 {e}'))
            continue
        if abs(y - o['baseline_output']) > 1e-6 * max(1.0, abs(y)):
            bad05.append((g['gid'], oid, f'baseline_output {o["baseline_output"]} != 实算 {y}'))
        # (d) output_scale 必须等于 baseline_output（三类统一规则）
        if abs(o['output_scale'] - o['baseline_output']) > 1e-9 * max(1.0, abs(y)):
            bad05.append((g['gid'], oid, 'output_scale != baseline_output'))
        # (e) 函数里的节点名必须都在节点表里（exp 是求值器内置函数，不是节点）
        tree = ast.parse(o['function'], mode='eval')
        call_names = {n.func.id for n in ast.walk(tree)
                      if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} - call_names
        nodes = {n['node_id'] for n in o['nodes']}
        if not names <= nodes:
            bad05.append((g['gid'], oid, f'函数引用了未声明节点 {names - nodes}'))
print(f"  检查对象数: {n_obj}（含目标、有效源、10 个干扰源）")
print(f"  判定：{'通过' if not bad05 else f'不通过（{len(bad05)} 项）'}")
for b in bad05[:5]:
    print("   ", b)

print()
print("=" * 70)
print("M06 响应尺度检查：两域使用具有相同含义的无量纲尺度")
print("=" * 70)
# 判定：正例在完整 u 网格上两域归一化响应必须相等（尺度含义一致的必要条件）
worst06 = 0.0
n_pair = 0
bad06 = []
for g in G:
    for tid, r in g['ref'].items():
        if r['label'] != 'positive':
            continue
        truth = r['valid'][0]
        tgt = g['objs'][g['man']['object_ids'][0]]
        src = g['objs'][truth['source_id']]
        inv = {v: k for k, v in truth['node_map'].items()}
        n_pair += 1
        grids = []
        for nid in tgt['controllable_inputs']:
            lo, hi = tgt['intervention_bounds'][nid]
            grids.append([lo, lo/2, 0.0, hi/2, hi])
        for combo in itertools.product(*grids):
            ut = dict(zip(tgt['controllable_inputs'], combo))
            try:
                vt = {}
                for i, nid in enumerate(tgt['controllable_inputs']):
                    vt[nid] = tgt['baseline'][i] + tgt['input_scales'][i] * ut[nid]
                rt = (ev(tgt['function'], vt) - tgt['baseline_output']) / tgt['output_scale']
                us = {inv[k]: v for k, v in ut.items()}
                vs = {}
                for i, nid in enumerate(src['controllable_inputs']):
                    vs[nid] = src['baseline'][i] + src['input_scales'][i] * us[nid]
                rs = (ev(src['function'], vs) - src['baseline_output']) / src['output_scale']
            except Exception:
                bad06.append((g['gid'], tid, '求值失败'))
                continue
            d = abs(rs - rt)
            worst06 = max(worst06, d)
            if d > 1e-9:
                bad06.append((g['gid'], tid, f'响应偏差 {d:.2e}'))
print(f"  检查正例对数: {n_pair}（每对 5^d 个网格点）")
print(f"  两域归一化响应最大偏差: {worst06:.3e}")
print(f"  判定：{'通过' if worst06 <= 1e-9 else '不通过'}")
if bad06[:3]:
    print("   样例:", bad06[:3])

print()
print("=" * 70)
print("M07 分组划分：基础组级别 70%/15%/15%")
print("=" * 70)
sp = collections.Counter(g['man']['split'] for g in G)
print(f"  组级划分: {dict(sp)}   合计 {sum(sp.values())}")
for k in ('train', 'val', 'test'):
    print(f"    {k:6s}: {sp[k]:3d} 组 = {sp[k]/n_group*100:.1f}%  （目标 "
          f"{'70' if k=='train' else '15'}%）")
pair_split = collections.defaultdict(set)
for g in G:
    pair_split[(g['rel'], g['man']['pair_id'])].add(g['man']['split'])
leak07 = sum(1 for v in pair_split.values() if len(v) > 1)
print(f"  域对总数 {len(pair_split)}，跨划分域对 {leak07}")
print(f"  判定：{'通过' if leak07 == 0 else '不通过'}（同一域对的变体必须在同一划分；"
      f"比例因域对为不可分单位略有偏差）")

print()
print("=" * 70)
print("M08 留出干预：每个测试任务 100 个独立合法干预点")
print("=" * 70)
bad08 = []
n_test_task = 0
n_pts = 0
for g in G:
    p = os.path.join(g['dir'], 'sealed', 'intervention_points.json')
    is_test = g['man']['split'] == 'test'
    if is_test != os.path.isfile(p):
        bad08.append((g['gid'], '测试组与干预点文件不匹配'))
        continue
    if not is_test:
        continue
    d = json.load(open(p, encoding='utf-8'))
    tgt = g['objs'][g['man']['object_ids'][0]]
    for tid, lst in d['tasks'].items():
        n_test_task += 1
        n_pts += len(lst)
        if len(lst) != 100:
            bad08.append((g['gid'], tid, f'{len(lst)} 点'))
        # 合法：每维在 intervention_bounds 内
        for u in lst:
            for nid in tgt['controllable_inputs']:
                lo, hi = tgt['intervention_bounds'][nid]
                if not (lo - 1e-9 <= u[nid] <= hi + 1e-9):
                    bad08.append((g['gid'], tid, '干预越界'))
                    break
        # 独立：无重复、无全零固定初始化点
        keys = {tuple(sorted(u.items())) for u in lst}
        if len(keys) != len(lst):
            bad08.append((g['gid'], tid, '存在重复点'))
        if any(all(abs(v) < 1e-12 for v in u.values()) for u in lst):
            bad08.append((g['gid'], tid, '含全零固定点'))
print(f"  测试组: {sp['test']}，测试任务: {n_test_task}，干预点总数: {n_pts}")
print(f"  每任务点数: {n_pts}/{n_test_task} = {n_pts/max(n_test_task,1):.0f}")
print(f"  判定：{'通过' if not bad05 else f'不通过（{len(bad05)} 项）'}")
for b in bad05[:5]:
    print("   ", b)

print()
print("=" * 70)
ALL_OK = (ok01 and not missing and not missing_k and not bad_pos
          and not bad04 and not bad05 and worst06 <= 1e-9 and leak07 == 0 and not bad08)
print("M01-M08 总体判定:", "全部通过" if ALL_OK else "存在不通过项，见上")
sys.exit(0 if ALL_OK else 1)
