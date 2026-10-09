#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
传播机会雷达 · 渲染层
--------------------------------------------------
把 cases.json 内联进 HTML 模板，产出可直接双击打开的看板。

之所以内联而不是让页面去 fetch，是因为本地 file:// 打开时会被跨域拦截，
每次跑完直接刷新浏览器即可看到最新结果。

用法：
    python3 render_dashboard.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "cases.json"
TPL = ROOT / "assets" / "template.html"
OUT = ROOT / "dashboard.html"


def main():
    if not SRC.exists():
        print(f"缺少数据：{SRC}，请先运行 build_cases.py", file=sys.stderr)
        return 1
    if not TPL.exists():
        print(f"缺少模板：{TPL}", file=sys.stderr)
        return 1

    data = json.loads(SRC.read_text(encoding="utf-8"))
    tpl = TPL.read_text(encoding="utf-8")

    # 防止数据里的 "</" 提前闭合 script 标签
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")

    OUT.write_text(tpl.replace("__DATA__", payload), encoding="utf-8")
    print(f"看板已生成：{OUT}  （P0 {data['stats']['p0']} / "
          f"P1 {data['stats']['p1']} / P2 {data['stats']['p2']}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
