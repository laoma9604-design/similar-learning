"""SCAN 适配的变异测试：故意改坏数据，验证 verify_scan.py 真的会报红。

为什么必须有这一步：verify_scan.py 写完后第一次跑就报了 86 项不合格，
其中 84 项是**验收器自己写错**（方向标反、大小写归一用错地方）；
反过来，它对「跨划分」这一项只打印不判失败，数据真的被拆块时它照样"全部通过"。
只跑一遍绿不能说明验收器有用，必须证明它能红。

每个变异：改一处 → 跑验收器 → 断言退出码非 0 → 复原 → 断言退出码回到 0。
用法：python a_data/mutation_test_scan.py      # 退出码 0 = 全部变异都能被抓到
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "cases" / "structural_scan"
PY = sys.executable


def fresh_cases():
    """每次变异都在副本上做，绝不碰正式数据。"""
    tmp = Path(tempfile.mkdtemp(prefix="scan_mut_"))
    shutil.copytree(CASES, tmp / "structural_scan")
    return tmp


def run_verify(root):
    r = subprocess.run([PY, str(ROOT / "a_data" / "verify_scan.py")],
                       capture_output=True, text=True,
                       env={**__import__("os").environ,
                            "SCAN_CASES_ROOT": str(root)})
    return r.returncode, r.stdout + r.stderr


# 让验收器支持临时根目录（变异测试专用），不必复制整仓
def patch_root_support():
    p = ROOT / "a_data" / "verify_scan.py"
    src = p.read_text(encoding="utf-8")
    if "SCAN_CASES_ROOT" in src:
        return
    src = src.replace(
        'SCAN_DIR = ROOT / "cases" / "structural_scan"',
        'SCAN_DIR = Path(os.environ.get("SCAN_CASES_ROOT", "")) or '
        'ROOT / "cases" / "structural_scan"')
    p.write_text(src, encoding="utf-8")


def mutate(name, fn):
    tmp = fresh_cases()
    g = tmp / "structural_scan"
    fn(g)

    def go():
        r = subprocess.run([PY, str(ROOT / "a_data" / "verify_scan.py")],
                           capture_output=True, text=True,
                           env={**__import__("os").environ,
                                "SCAN_CASES_ROOT": str(g)})
        return r.returncode, r.stdout + r.stderr

    code, out = go()
    shows = [l.strip() for l in out.splitlines()
             if l.strip().startswith("[")]
    shutil.rmtree(tmp, ignore_errors=True)
    # 退出码非 0 还不够：可能是验收器本身崩了（traceback），那不算抓到。
    # 必须真的输出了一条守卫信息才作数。
    crashed = "Traceback (most recent call last)" in out
    return name, code, shows[:3], crashed


def _rw(p, fn):
    d = json.loads(p.read_text(encoding="utf-8"))
    fn(d)
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def m_identity(g):
    p = g / "group_scan_0011/sealed/reference.json"
    def f(d):
        t = next(iter(d))
        d[t]["pair_map"] = [[a, a] for a, _ in d[t]["pair_map"]]
    _rw(p, f)


def m_rewrite_word(g):
    p = g / "group_scan_0011/sealed/adaptation.json"
    _rw(p, lambda d: d["faithful_mappings"].__setitem__(0, ["DEMOCRACY", d["faithful_mappings"][0][1]]))


def m_invent_explanation(g):
    p = g / "group_scan_0011/sealed/adaptation.json"
    _rw(p, lambda d: d.__setitem__("explanation", ["我替作者编了一句"]))


def m_mtype_flip(g):
    # 0011 实际是 one_to_many，改成 many_to_one
    p = g / "group_scan_0011/sealed/reference.json"
    _rw(p, lambda d: d[next(iter(d))].__setitem__("multiple_mapping_type", "many_to_one"))


def m_split_block(g):
    # 0011 原属 test，挪到 train → 与同块其他组跨划分
    p = g / "group_scan_0011/manifest.json"
    _rw(p, lambda d: d.__setitem__("split", "train"))


def m_type_snapshot(g):
    p = g / "group_scan_0011/sealed/reference.json"
    _rw(p, lambda d: d[next(iter(d))].__setitem__("ref_type_pattern", [["force", "force"]]))


def m_drop_row(g):
    # 删掉一组的原始行号 → 行覆盖出现缺口
    p = g / "group_scan_0002/sealed/adaptation.json"
    _rw(p, lambda d: (d["raw"]["row_indices"].pop(),
                      d["raw"]["rows"].pop()))


def m_drop_required_field(g):
    # 删掉 schema 必填的 available_checks（初版真的漏了它）
    p = g / "group_scan_0003/sealed/adaptation.json"
    _rw(p, lambda d: d.pop("available_checks"))


def m_invent_custom_field(g):
    # 加一个 schema 外、SCAR 也没有的自定义字段
    p = g / "group_scan_0003/sealed/adaptation.json"
    _rw(p, lambda d: d.__setitem__("my_own_field", 1))


def m_node_drop(g):
    # 删一个节点 → 节点数 != 去重概念数
    p = g / "group_scan_0021/data/input/objects/obj_group_scan_0021_src.json"
    _rw(p, lambda d: d["nodes"].pop())


MUTATIONS = [
    ("M1 参考映射改恒等", m_identity),
    ("M2 改一个概念词", m_rewrite_word),
    ("M3 代写不存在的解释", m_invent_explanation),
    ("M4 多值类型倒置", m_mtype_flip),
    ("M5 拆开派生块跨划分", m_split_block),
    ("M6 类型快照写坏", m_type_snapshot),
    ("M7 丢掉一组原始行", m_drop_row),
    ("M8 删掉一个节点", m_node_drop),
    ("M9 删掉必填字段 available_checks", m_drop_required_field),
    ("M10 自造 schema 外字段", m_invent_custom_field),
]


def main():
    patch_root_support()
    bad = []
    for name, fn in MUTATIONS:
        try:
            n, code, shows, crashed = mutate(name, fn)
        except Exception as e:                     # noqa: BLE001
            bad.append(f"{name}: 变异本身出错 {e}")
            print(f"  {name}: 变异出错 {e}")
            continue
        ok = code != 0 and bool(shows) and not crashed
        tag = "抓到" if ok else ("★崩溃未守卫★" if crashed else "★漏检★")
        print(f"  {name}: {tag}  {shows}")
        if not ok:
            bad.append(name)
    print("=" * 60)
    if bad:
        print(f"不合格 {len(bad)} 项: {bad}")
        return 1
    print(f"全部 {len(MUTATIONS)} 项变异都被守卫抓到（无崩溃、无漏检）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
