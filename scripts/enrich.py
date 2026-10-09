#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
传播机会雷达 · 溯源层
--------------------------------------------------
解决一个问题：热榜条目的「来源」只是榜单名（百度热搜、头条热榜），
不是报道这件事的媒体。本层把热榜事件溯源到真实报道，同时给官媒条目
补上正文首段，作为「事件描述」的素材。

产出字段（写回候选）：
    reports   : [{media, title, url}]   真实报道列表
    media     : 主报道媒体名（取第一条）
    url       : 主报道链接
    summary_raw: 事件描述素材（官媒取正文首段；热榜取搜索结果标题）

用法：
    python3 enrich.py                 # 溯源今天
    python3 enrich.py --date 2026-10-08
    python3 enrich.py --limit 40      # 最多处理多少条（默认 40）
    python3 enrich.py --ids a1b2,c3d4 # 只处理指定 id
"""

import argparse
import json
import re
import sys
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect import fetch, clean_text  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
TZ = timezone(timedelta(hours=8))

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# 域名 → 媒体名。命中即采用，未命中则返回域名本身。
MEDIA_MAP = [
    ("mp.weixin.qq.com", "微信公众号"),
    ("news.qq.com", "腾讯新闻"), ("new.qq.com", "腾讯新闻"),
    ("people.com.cn", "人民网"), ("news.cn", "新华网"), ("xinhuanet.com", "新华网"),
    ("cctv.com", "央视网"), ("gmw.cn", "光明网"), ("chinanews.com.cn", "中国新闻网"),
    ("thepaper.cn", "澎湃新闻"), ("jiemian.com", "界面新闻"),
    ("bjnews.com.cn", "新京报"), ("yicai.com", "第一财经"),
    ("stdaily.com", "科技日报"), ("cnr.cn", "央广网"), ("china.com.cn", "中国网"),
    ("huanqiu.com", "环球网"), ("workercn.cn", "工人日报"),
    ("cctvnews", "央视新闻"), ("xinhua", "新华网"),
    ("sina.com.cn", "新浪"), ("sohu.com", "搜狐"), ("163.com", "网易"),
    ("ifeng.com", "凤凰网"), ("36kr.com", "36氪"), ("ithome.com", "IT之家"),
    ("cnbeta.com.tw", "cnBeta"), ("zhihu.com", "知乎"),
    ("toutiao.com", "今日头条"), ("baijiahao.baidu.com", "百家号"),
    ("weibo.com", "微博"), ("douyin.com", "抖音"), ("xiaohongshu.com", "小红书"),
    ("stcn.com", "证券时报"), ("yunnan", "云南网"),
]

# 搜索结果里不算「报道」的站点
JUNK_SITE = ("baike.baidu.com", "zhidao.baidu.com", "tieba.baidu.com",
             "baidu.com/s?", "wikipedia", "sogou.com", "bing.com")


def media_of(url):
    host = ""
    m = re.match(r"https?://([^/]+)", url or "")
    if m:
        host = m.group(1).lower()
    for dom, name in MEDIA_MAP:
        if dom in host:
            return name
    return host or "来源不明"


def resolve(url):
    """解析搜狗的 /link?url= 跳转壳，跟随重定向拿真实地址。失败返回原值。"""
    if not url.startswith("/link?url="):
        return url
    full = "https://www.sogou.com" + url
    try:
        req = urllib.request.Request(full, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.geturl()
    except Exception:
        return full


def search_reports(query, limit=5):
    """用搜狗搜索事件，返回 [{media, title, url, snippet}]。百度易被拦，搜狗实测可用。"""
    url = ("https://www.sogou.com/web?query=" + urllib.parse.quote(query))
    try:
        html = fetch(url, headers={"Referer": "https://www.sogou.com/"}, timeout=15)
    except Exception:
        return []
    out, seen = [], set()

    # 按结果块切分，块内同时取标题、链接、媒体名与摘要
    for blk in html.split('class="vrwrap"')[1:]:
        m = re.search(r'<h3[^>]*>\s*<a[^>]*?href="([^"]+)"[^>]*>([\s\S]{0,400}?)</a>', blk)
        if not m:
            continue
        link, title = m.group(1), clean_text(m.group(2))
        if len(title) < 6:
            continue
        # 媒体名优先取页面上显示的来源标签，比从域名猜更准
        mm = re.search(r'citeurl[^>]*>[\s\S]{0,300}?<span>([^<]{1,30})</span>', blk)
        media = clean_text(mm.group(1)) if mm else ""
        media = {"公众号": "微信公众号"}.get(media, media)
        if not media:
            media = media_of(link)
        # 摘要：去掉标签后的正文，掐掉「推荐您搜索」之后的推荐词
        txt = re.sub(r"<[^>]+>", " ", blk)
        txt = re.sub(r"\s+", " ", txt).strip()
        txt = txt.split("推荐您搜索")[0].strip()
        parts = [p for p in txt.split(" ") if len(p) > 1]
        snippet = " ".join(parts[2:16])[:180] if len(parts) > 4 else ""

        # 多数结果是搜狗的 /link?url= 跳转壳，解析不出真实地址。
        # 壳链接点开仍会跳到原文，保留即可；只有解析成功的直链才做垃圾站过滤。
        real = resolve(link)
        shell = real.startswith("https://www.sogou.com/link")
        if not shell and any(j in real for j in JUNK_SITE):
            continue
        if real in seen:
            continue
        seen.add(real)
        out.append({"media": media, "title": title, "url": real, "snippet": snippet})
        if len(out) >= limit:
            break

    # 主报道优先选央媒与主流媒体；微信公众号排最后 —— 它只显示「公众号」，
    # 看不出是哪家机构，作为「报道的媒体名」信息量不够。
    def rank(r):
        m = r["media"]
        if any(k in m for k in ("人民网", "新华网", "光明网", "央视", "中国新闻网",
                                "科技日报", "央广网", "中国网", "工人日报", "南方日报",
                                "澎湃", "新京报", "界面", "第一财经", "环球", "半月谈")):
            return 0
        if "微信" in m or "公众号" in m:
            return 2
        return 1

    out.sort(key=rank)
    return out


def fetch_lead(url, maxlen=200):
    """抓正文前两段，作为事件描述素材。失败返回空串。"""
    try:
        html = fetch(url, timeout=15)
    except Exception:
        return ""
    # 优先取带段落语义的 <p>，过滤脚本/样式
    html = re.sub(r"(?is)<(script|style)[^>]*>[\s\S]*?</\1>", " ", html)
    paras = []
    for m in re.finditer(r"(?is)<p[^>]*>([\s\S]{0,1200}?)</p>", html):
        t = clean_text(m.group(1))
        if len(t) >= 25 and not re.search(r"(版权|免责|声明|ICP|许可证|编辑：|责任编辑)", t):
            paras.append(t)
        if sum(len(p) for p in paras) >= maxlen:
            break
    return (" ".join(paras))[:maxlen]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--ids", default=None, help="逗号分隔，只处理这些 id")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    date = args.date or datetime.now(TZ).strftime("%Y-%m-%d")
    path = RAW_DIR / f"{date}.json"
    if not path.exists():
        print(f"缺少文件：{path}", file=sys.stderr)
        return 1

    data = json.loads(path.read_text(encoding="utf-8"))
    cands = data["candidates"]

    only = set(args.ids.split(",")) if args.ids else None
    # 排序优先级：热榜条目先处理 —— 它们没有真实报道链接，溯源是刚需；
    # 官媒条目本身已带链接与媒体名，只是补正文摘要，配额不够时可以先不补。
    targets = [c for c in cands if not only or c["id"] in only]
    targets.sort(key=lambda c: (c.get("official") is True, -(c.get("heat") or 0)))
    targets = targets[:args.limit]

    print(f"溯源 {len(targets)}/{len(cands)} 条候选", file=sys.stderr)

    n_rep = n_lead = 0
    for i, c in enumerate(targets, 1):
        if c.get("official") and c.get("urls"):
            # 官媒：抓正文首段作为描述素材；媒体名即来源
            lead = fetch_lead(c["urls"][0])
            c["summary_raw"] = lead
            c["media"] = c["sources"][0] if c["sources"] else ""
            c["url"] = c["urls"][0]
            c["reports"] = [{"media": c["media"], "title": c["title"], "url": c["url"]}]
            n_lead += 1 if lead else 0
        else:
            # 热榜：搜真实报道
            reps = search_reports(c["title"])
            c["reports"] = reps
            c["media"] = reps[0]["media"] if reps else ""
            c["url"] = reps[0]["url"] if reps else (c["urls"][0] if c.get("urls") else "")
            # 描述素材：优先用搜索结果正文摘要，其次退回标题拼接
            snip = next((r.get("snippet") for r in reps if r.get("snippet")), "")
            c["summary_raw"] = snip or " ｜ ".join(r["title"] for r in reps[:3])
            n_rep += 1 if reps else 0
        if args.debug:
            print(f"  [{i}] {c['title'][:34]} → {c['media'] or '未找到'}", file=sys.stderr)
        time.sleep(0.5)  # 礼貌抓取，别把源打封

    # 未处理的候选补空字段，避免下游 KeyError
    done = {c["id"] for c in targets}
    for c in cands:
        if c["id"] not in done:
            c.setdefault("reports", [])
            c.setdefault("media", "")
            c.setdefault("url", (c.get("urls") or [""])[0])
            c.setdefault("summary_raw", "")

    data["enriched_at"] = datetime.now(TZ).isoformat(timespec="seconds")
    data["enrich_stats"] = {"processed": len(targets), "with_reports": n_rep,
                            "with_lead": n_lead}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"完成：找到真实报道 {n_rep} 条 · 抓到正文摘要 {n_lead} 条")
    print(f"写回：{path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
