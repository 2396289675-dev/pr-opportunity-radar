#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
传播机会雷达 · 展示页渲染
--------------------------------------------------
产出「可对外展示 / 可嵌入网站」的单文件 HTML，与日常工作看板 dashboard.html 区分开。

差异：
  - 工作看板给本人看，信息密集、按 P0/P1/P2 全量平铺；
  - 展示页给外人看，加了漏斗可视化讲清系统价值，人物做卡片化，
    P2 收成紧凑列表，并做了窄屏与 iframe 嵌入适配。

特点：数据内联、零外部依赖（无 CDN、无外链字体与图片），
单文件可直接双击打开，也可上传服务器或 iframe 嵌入。

用法：
    python3 scripts/render_showcase.py                      # 默认输出到 <根目录>/showcase.html
    python3 scripts/render_showcase.py -o ~/Desktop/xx.html # 指定输出位置
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "cases.json"
TPL = ROOT / "assets" / "showcase_template.html"
OUT = ROOT / "showcase.html"


def main():
    ap = argparse.ArgumentParser(description="渲染可对外展示的单文件看板")
    ap.add_argument("-o", "--out", default=str(OUT), help="输出文件路径")
    ap.add_argument("--data", default=str(SRC), help="cases.json 路径")
    args = ap.parse_args()

    src = Path(args.data).expanduser()
    out = Path(args.out).expanduser()

    if not src.exists():
        print(f"缺少数据：{src}，请先运行 build_cases.py", file=sys.stderr)
        return 1
    if not TPL.exists():
        print(f"缺少模板：{TPL}", file=sys.stderr)
        return 1

    data = json.loads(src.read_text(encoding="utf-8"))
    tpl = TPL.read_text(encoding="utf-8")

    # 防止数据里的 "</" 提前闭合 script 标签
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(tpl.replace("__DATA__", payload), encoding="utf-8")

    st = data["stats"]
    size_kb = out.stat().st_size / 1024
    print(f"展示页已生成：{out}")
    print(f"  {data.get('date','')} · 判读 {st['judged']} 条 "
          f"（P0 {st['p0']} / P1 {st['p1']} / P2 {st['p2']}）· 人物 {st['people']} 人")
    print(f"  单文件 {size_kb:.0f} KB，零外部依赖，可直接上传或 iframe 嵌入")
    return 0


if __name__ == "__main__":
    sys.exit(main())
