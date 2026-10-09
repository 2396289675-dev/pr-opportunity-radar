#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
传播机会雷达 · 业务池筛选页渲染
--------------------------------------------------
把 config/tencent_biz.json 内联进 assets/biz_pool_template.html，
产出根目录 biz_pool.html（双击即可勾选，不受 file:// 跨域限制）。

用法：
    python3 scripts/render_bizpool.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "config" / "tencent_biz.json"
TPL = ROOT / "assets" / "biz_pool_template.html"
OUT = ROOT / "biz_pool.html"


def main():
    if not CFG.exists():
        print(f"缺少配置文件：{CFG}", file=sys.stderr)
        return 1
    if not TPL.exists():
        print(f"缺少模板：{TPL}", file=sys.stderr)
        return 1

    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    tpl = TPL.read_text(encoding="utf-8")

    payload = json.dumps(cfg, ensure_ascii=False)
    # 内联进 <script> 时必须转义 </ ，否则会提前闭合脚本块
    payload = payload.replace("</", "<\\/")

    if "__DATA__" not in tpl:
        print("模板缺少 __DATA__ 占位符", file=sys.stderr)
        return 1

    OUT.write_text(tpl.replace("__DATA__", payload), encoding="utf-8")
    n = len(cfg.get("items", []))
    n_on = sum(1 for i in cfg.get("items", []) if i.get("enabled"))
    print(f"业务池：{n} 条（当前启用 {n_on}）+ 自定义 "
          f"{len(cfg.get('custom_items', []))} 条 → {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
