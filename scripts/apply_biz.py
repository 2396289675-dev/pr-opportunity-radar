#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
传播机会雷达 · 业务池筛选结果写回
--------------------------------------------------
把用户在 biz_pool.html 导出 / 粘贴的选择结果写回 config/tencent_biz.json，
并重新渲染筛选页。

用法：
    python3 scripts/apply_biz.py ~/Downloads/tencent_biz_selected.json
    python3 scripts/apply_biz.py --json '{"enabled":["wechat",...],"custom_items":[...]}'
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "config" / "tencent_biz.json"
PY = sys.executable


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?", default=None,
                    help="biz_pool.html 导出的 tencent_biz_selected.json 路径")
    ap.add_argument("--json", default=None, help="直接给 JSON 字符串")
    args = ap.parse_args()

    if args.json:
        sel = json.loads(args.json)
    elif args.file:
        p = Path(args.file).expanduser()
        if not p.exists():
            print(f"找不到文件：{p}", file=sys.stderr)
            return 1
        sel = json.loads(p.read_text(encoding="utf-8"))
    else:
        print("需要给导出的 JSON 文件路径，或用 --json 直接给内容", file=sys.stderr)
        return 1

    enabled = set(sel.get("enabled", []))
    custom = sel.get("custom_items", []) or []

    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    items = cfg.get("items", [])
    by_id = {i["id"]: i for i in items}

    turned_off, turned_on, unknown = [], [], []
    for it in items:
        want = it["id"] in enabled
        if it.get("enabled") and not want:
            turned_off.append(it["name"])
        elif not it.get("enabled") and want:
            turned_on.append(it["name"])
        it["enabled"] = want
    for e in enabled:
        if e not in by_id and not e.startswith("custom_"):
            unknown.append(e)

    # 自定义条目：保留已存在的，追加新的
    old = {c["id"]: c for c in cfg.get("custom_items", [])}
    merged = []
    for c in custom:
        c.setdefault("group", "custom")
        c.setdefault("enabled", True)
        c.setdefault("recommended", False)
        c.setdefault("desc", "")
        c.setdefault("fit", "")
        c.setdefault("note", "")
        merged.append(c)
    for cid, c in old.items():
        if cid not in {x["id"] for x in merged}:
            merged.append(c)
    cfg["custom_items"] = merged

    from datetime import datetime, timedelta, timezone
    cfg["updated"] = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    CFG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"业务池已更新：启用 {sum(1 for i in items if i['enabled'])} / {len(items)} 条，"
          f"自定义 {len(merged)} 条")
    if turned_off:
        print(f"  本次关闭 {len(turned_off)}：{'、'.join(turned_off)}")
    if turned_on:
        print(f"  本次开启 {len(turned_on)}：{'、'.join(turned_on)}")
    if merged:
        print(f"  自定义新增：{'、'.join(c['name'] for c in custom)}")
    if unknown:
        print(f"  警告：选择结果里有认不出的 id：{unknown}")

    subprocess.run([PY, str(ROOT / "scripts" / "render_bizpool.py")])
    return 0


if __name__ == "__main__":
    sys.exit(main())
