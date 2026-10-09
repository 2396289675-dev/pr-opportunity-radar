#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
传播机会雷达 · 合并层
--------------------------------------------------
把「采集层产出」与「agent 判读结果」合成为看板数据源。

判读由 agent 完成（不是脚本），判读结果落在 data/judge/<date>.json，
本脚本只做关联、补全与排序，不产生任何判断。

用法：
    python3 build_cases.py            # 合并今天
    python3 build_cases.py --date 2026-10-08
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
JUDGE_DIR = ROOT / "data" / "judge"
CASES_DIR = ROOT / "data" / "cases"
TZ = timezone(timedelta(hours=8))

CARRY_FIELDS = ("urls", "sources", "source_count", "on_hotlist",
                "official", "official_tier", "heat", "best_rank",
                "topic_tags", "person_hits", "is_person",
                # 溯源层补齐：报道媒体名、主报道链接、报道列表、事件描述素材
                "media", "url", "reports", "summary_raw")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    args = ap.parse_args()

    date = args.date or datetime.now(TZ).strftime("%Y-%m-%d")
    raw_path = RAW_DIR / f"{date}.json"
    judge_path = JUDGE_DIR / f"{date}.json"

    for p in (raw_path, judge_path):
        if not p.exists():
            print(f"缺少文件：{p}", file=sys.stderr)
            return 1

    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    judge = json.loads(judge_path.read_text(encoding="utf-8"))
    by_id = {c["id"]: c for c in raw["candidates"]}

    # 今日出圈人物：与机会条目并列的一类，不参与 P0/P1/P2 分级
    people = []
    for p in judge.get("people", []):
        src = by_id.get(p["id"])
        people.append({
            "id": p["id"],
            "name": p.get("name", ""),
            "type": p.get("type", ""),
            "why": p.get("why", ""),
            "usable": p.get("usable", ""),
            "risk": p.get("risk", ""),
            "heat": (src or {}).get("heat", 0) or p.get("heat", 0),
            "title": src["title"] if src else "",
            "urls": (src or {}).get("urls", []),
            "sources": (src or {}).get("sources", []),
            "media": (src or {}).get("media", ""),
            "url": (src or {}).get("url", ""),
            "reports": (src or {}).get("reports", []),
            "summary_raw": (src or {}).get("summary_raw", ""),
            "summary": p.get("summary", ""),
        })
    people.sort(key=lambda x: -(x.get("heat") or 0))

    cases, missing = [], []
    for it in judge["items"]:
        src = by_id.get(it["id"])
        if not src:
            missing.append(it["id"])
            continue
        merged = {"id": it["id"], "title": src["title"]}
        for f in CARRY_FIELDS:
            merged[f] = src.get(f)
        for f in ("priority", "score", "topic", "opportunity",
                  "tencent_angle", "risk", "action", "window", "summary", "biz"):
            merged[f] = it.get(f, "")
        # 事件描述：判读写的是什么就用什么；没写则退回溯源素材
        if not merged["summary"]:
            merged["summary"] = src.get("summary_raw", "")
        cases.append(merged)

    if missing:
        print(f"警告：{len(missing)} 条判读在候选中找不到对应 id：{missing}", file=sys.stderr)

    cases.sort(key=lambda c: (c.get("score") or 0), reverse=True)

    counted = {p: sum(1 for c in cases if c["priority"] == p) for p in ("P0", "P1", "P2")}
    out = {
        "date": date,
        "built_at": datetime.now(TZ).isoformat(timespec="seconds"),
        "focus": judge.get("focus", []),
        "p0_note": judge.get("p0_note", ""),
        "stats": {
            "raw": raw["stats"]["raw"],
            "blocked": raw["stats"]["blocked"],
            "candidates": raw["stats"]["candidates"],
            "judged": len(cases),
            "p0": counted["P0"],
            "p1": counted["P1"],
            "p2": counted["P2"],
            "people": len(people),
        },
        "scope_note": judge.get("scope_note", ""),
        "people": people,
        "cases": cases,
    }

    CASES_DIR.mkdir(parents=True, exist_ok=True)
    (CASES_DIR / f"{date}.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    # 看板固定读取最新一份
    (ROOT / "data" / "cases.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    s = out["stats"]
    print(f"{date}：候选 {s['candidates']} 条 → 判读入库 {s['judged']} 条 "
          f"（P0 {s['p0']} / P1 {s['p1']} / P2 {s['p2']}）｜出圈人物 {s['people']} 人")
    print(f"输出：data/cases.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
