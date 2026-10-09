#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
传播机会雷达 · 业务池合规校验
--------------------------------------------------
检查判读结果里的 biz 字段有没有用到「业务池之外」或「已被用户关掉」的业务名。
判读只能从 config/tencent_biz.json 中 enabled=true 的业务里挑。

用法：
    python3 scripts/check_biz.py            # 校验今天
    python3 scripts/check_biz.py --date 2026-10-08
"""

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "config" / "tencent_biz.json"
JUDGE_DIR = ROOT / "data" / "judge"
TZ = timezone(timedelta(hours=8))

# 池外名称的兜底识别：biz 里出现「腾讯XX」却没命中任何别名
STRAY = re.compile(r"腾讯[\u4e00-\u9fa5A-Za-z0-9·]{1,10}")


def load_pool():
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    items = list(cfg.get("items", [])) + list(cfg.get("custom_items", []))
    by_id = {i["id"]: i for i in items}
    # 别名按长度降序，避免「微信」先于「微信支付」命中
    aliases = []
    for it in items:
        names = [it["name"]] + list(it.get("aliases") or [])
        for a in sorted({n for n in names if n}, key=len, reverse=True):
            aliases.append((a, it))
    aliases.sort(key=lambda x: -len(x[0]))
    return cfg, items, by_id, aliases


def scan(text, aliases):
    """返回 (命中的业务, 未被识别的可疑名称)

    biz 的格式是「业务名 · 一句话说明」，只对「·」之前的业务名区做校验，
    「·」之后是叙述文字，出现「腾讯」不是业务名，不参与校验。
    """
    if not text:
        return [], []
    head = text.split("·")[0] if "·" in text else text
    hits, rest = [], head
    for a, it in aliases:
        if a in rest:
            if it not in hits:
                hits.append(it)
            rest = rest.replace(a, "　")
    stray = [m.group(0) for m in STRAY.finditer(rest)]
    # 过滤掉被占位符切断的噪声
    stray = [s.strip("　· ") for s in stray if len(s.strip("　· ")) >= 3]
    return hits, stray


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    args = ap.parse_args()

    date = args.date or datetime.now(TZ).strftime("%Y-%m-%d")
    jpath = JUDGE_DIR / f"{date}.json"
    if not jpath.exists():
        print(f"缺少判读文件：{jpath}", file=sys.stderr)
        return 1

    cfg, items, by_id, aliases = load_pool()
    judge = json.loads(jpath.read_text(encoding="utf-8"))

    problems, disabled_hits = [], []
    total = 0
    for it in judge.get("items", []):
        biz = it.get("biz", "")
        if not biz:
            problems.append((it.get("score", 0), it["id"], "biz 为空", ""))
            continue
        total += 1
        hits, stray = scan(biz, aliases)
        off = [h["name"] for h in hits if not h.get("enabled")]
        if off:
            disabled_hits.append((it.get("score", 0), it["id"], biz, "、".join(off)))
        if stray:
            problems.append((it.get("score", 0), it["id"], biz, "池外名称：" + "、".join(stray)))

    n_on = sum(1 for i in items if i.get("enabled"))
    print(f"业务池：{len(items)} 条，启用 {n_on} 条 ｜ 校验 {date} 的 {total} 条判读")

    if not problems and not disabled_hits:
        print("✓ 全部 biz 都在启用池内")
        return 0

    if disabled_hits:
        print("\n✗ 用了已被关掉的业务：")
        for sc, id_, biz, who in sorted(disabled_hits, key=lambda x: -x[0]):
            print(f"  [{sc}] {biz[:60]}")
            print(f"       已禁用：{who} —— 改用它池内的替代项，或把它重新勾选")
    if problems:
        print("\n✗ 用了业务池之外的名称：")
        for sc, id_, biz, why in sorted(problems, key=lambda x: -x[0]):
            print(f"  [{sc}] {biz[:60]}")
            print(f"       {why} —— 要么换成池内业务，要么在业务池页面「自己加一条」")
    return 1


if __name__ == "__main__":
    sys.exit(main())
