#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
传播机会雷达 · 采集层
--------------------------------------------------
职责：多源采集 -> 硬过滤 -> 跨源去重合并 -> 输出待判读候选

刻意不做的事：判读打分。判读需要模型理解"腾讯能不能自然接入"，
写不成规则，交由运行时的 agent 完成（见 dashboard 生成步骤）。

用法：
    python3 collect.py            # 采集今天
    python3 collect.py --debug    # 打印每个源抓取条数
"""

import argparse
import gzip
import hashlib
import json
import re
import ssl
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
TZ = timezone(timedelta(hours=8))

# ---------------------------------------------------------------------------
# 题材画像：AI普惠/适老化/无障碍 · 凡人微光 · 乡村振兴数字助农
# 命中只做标记（弱信号），不做丢弃——热榜标题太短，丢弃会误杀。
# ---------------------------------------------------------------------------
TOPIC_RULES = {
    "ai_public_good": "AI|人工智能|大模型|机器人|具身智能|算法|算力|芯片|智能|数字化|数字技术|"
                      "无人驾驶|自动驾驶|脑机|量子|编程|代码|开发者|开源|5G|6G|数字人|"
                      "语音识别|图像识别|翻译|科技|技术创新|智慧|云平台|数据要素",
    "elder_accessibility": "老人|老年|银发|养老|适老|敬老|无障碍|残障|残疾人|视障|听障|盲人|"
                           "手语|助残|轮椅|独居|陪护|关爱|罕见病|康复|助听|盲道",
    "ordinary_people": "外卖|骑手|快递|小哥|农民工|务工|打工|小店|摊贩|早餐|保洁|护工|"
                       "货车司机|出租车|工匠|手艺|非遗|乡村教师|留守|志愿者|环卫|"
                       "大爷|大妈|阿姨|大叔|师傅|姑娘|小伙|普通人|村民|果农|菜农|渔民",
    "rural_digital": "乡村|农村|农民|助农|农产品|直播带货|返乡|脱贫|县域|合作社|"
                     "种粮|丰收|田地|扶贫|乡村振兴|数字乡村|电商进村",
}

# ---------------------------------------------------------------------------
# 出圈人物识别
# 人物是独立的一类机会，不能走题材门槛——"殷玉珍种树40年"不沾任何题材词，
# 但正是典型人物出圈。所以命中人物信号的条目无条件保留，交由判读层判断。
# ---------------------------------------------------------------------------
PERSON_IDENTITY = ("劳模|劳动模范|工匠|大国工匠|院士|科学家|村支书|村主任|第一书记|"
                   "护林员|农民|果农|菜农|渔民|牧民|骑手|外卖|快递|主播|网红|博主|"
                   "师傅|大妈|大爷|阿姨|大叔|大婶|小伙|姑娘|老人|老太|"
                   "民警|辅警|交警|医生|护士|教师|老师|支教|司机|志愿者|护工|"
                   "保洁|环卫|手艺人|非遗|传承人|老兵|退伍军人|退役军人|"
                   "母亲|父亲|奶奶|爷爷|女孩|男孩|少年|学生|大学生|"
                   "残障|视障|听障|轮椅|抗癌|村民|摊主|店主|老板")

PERSON_ACTION = ("走红|火了|爆火|刷屏|获赞|感动|当选|荣获|获评|被评为|上榜|"
                 "被找到|重逢|寻找|寻人|致敬|点赞|泪目|破防|捐|救人|捐献|"
                 "坚守|义务|免费|接力|还清|照顾|赡养|抚养|逆行|托举|撑起")

# 姓名 + 动作：抓"殷玉珍种树40年""XX找到了"这类，姓名本身进不了词表
PERSON_NAME_RE = re.compile(
    r"([\u4e00-\u9fa5]{2,4})(?:走红|火了|爆火|刷屏|获赞|当选|荣获|获评|"
    r"被评为|被找到|重逢|泪目|破防|救人|辞世|逝世)")


# ---------------------------------------------------------------------------
# 硬否决词表（一票否决，直接丢弃）
# ---------------------------------------------------------------------------
# 严重类：对所有来源一票否决（负面恶性、涉政敏感、娱乐八卦）
BLOCK_SEVERE = ("事故|遇难|死亡|身亡|去世|逝世|哀悼|坠|坍塌|垮|火灾|爆炸|凶|杀害|"
                "强奸|猥亵|性侵|虐待|诈骗|传销|赌博|吸毒|抓|捕|判刑|起诉|立案|"
                "罚款|曝光|投诉|维权|欠薪|裁员|倒闭|跑路|中毒|召回|翻车|"
                "道歉|致歉|争议|抵制|痛批|质疑|造假|山寨|侵权|抄袭|拘留|涉案|"
                "违法|违规|约谈|断裂|断裂|停售|下架|禁|塌|"
                "明星|演唱会|综艺|票房|电视剧|恋情|官宣|离婚|绯闻|八卦|粉丝|偶像|"
                "选秀|新歌|专辑|代言|网红|主播|漫展|番剧|"
                "习近平|总书记|政治局|常委|中央军委|俄乌|以色列|哈马斯|乌克兰|"
                "特朗普|拜登|普京|制裁|关税战|军演|台海|南海|钓鱼岛|武装|"
                "袭击|开火|冲突|打击|导弹")

# 噪音类：只对热榜应用。官媒的"国庆假期科技赋能文旅"是有效内容，
# 不能因为含"假期"被误杀，所以这条规则不作用于官媒源。
BLOCK_NOISE = ("放假|调休|高速免费|返程|限行|天气|降温|暴雨|台风|高温|寒潮|"
               "节气|立春|雨水|惊蛰|春分|清明|谷雨|立夏|芒种|夏至|小暑|立秋|"
               "处暑|白露|秋分|寒露|霜降|立冬|小雪|大雪|冬至|小寒|大寒|"
               "星座|运势|彩票|开奖|球|联赛|夺冠|赛事|NBA|C罗|梅西|国足|"
               "股价|涨停|跌停|财报|业绩|汇率|降价|涨价|优惠券|红包|"
               "考试|高考|考研|录取|开学|放假通知|"
               "休\\d|上\\d休|假期安排|"
               "剧情|伏笔|大结局|剧中|角色|演员|编剧|原著|改编")

# 竞品/同业主体：不否决，只在判读阶段降权（可能只是背景信息）
COMPETITOR = ("阿里|阿里巴巴|淘宝|天猫|蚂蚁|支付宝|字节|抖音|今日头条|西瓜|"
              "百度|京东|美团|拼多多|小米|华为|荣耀|苹果|三星|OPPO|vivo|"
              "蔚来|小鹏|理想|比亚迪|大疆|网易|快手|携程|滴滴|拼多多|"
              "商汤|科大讯飞|智谱|月之暗面|MiniMax|字节跳动|微软|谷歌|英伟达|OpenAI")

# 导航/无意义标题（抓官媒列表页时混入）
NAV_WORDS = {"首页", "更多", "新闻", "视频", "图片", "导航", "登录", "注册", "English",
             "手机版", "客户端", "下载", "关于我们", "联系我们", "版权声明", "网站地图",
             "上一页", "下一页", "返回", "频道", "专题", "排行", "搜索", "更多>>",
             "正文", "评论", "分享", "打印", "关闭", "中国", "科技", "要闻",
             "经济·科技·生态", "中国科学技术协会", "中国科协",
             "国家自然科学基金委员会", "科技部", "教育部",
             "工业和信息化部", "中国科学院", "中国工程院",
             "科普中国直播服务", "科普中国繁星追梦",
             "科普中国军事科技", "科普中国科学报国正当时"}

# 页脚/证照类垃圾（官媒列表页底部常年挂着）
PAGE_JUNK = re.compile(
    r"许可证|ICP|备案|安备|字第|网文|执业|登记证|Copyright|版权所有|"
    r"隐私|举报|友情链接|站点地图|联系方式|违法和不良信息|营业执照|"
    r"广播电视节目制作|增值电信|信息网络传播视听|网络出版服务|网络文化经营")

# 光明网等站点的专题导航项以「·」开头，不是正文
LEADING_DOT = re.compile(r"^[·•]")


# ---------------------------------------------------------------------------
# 抓取
# ---------------------------------------------------------------------------
def fetch(url, headers=None, timeout=20):
    h = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9",
         "Accept-Encoding": "gzip"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            try:
                raw = gzip.decompress(raw)
            except OSError:
                pass
        ctype = r.headers.get("Content-Type", "")
        m = re.search(r"charset=([\w-]+)", ctype, re.I)
        enc = m.group(1) if m else "utf-8"
    try:
        return raw.decode(enc, errors="replace")
    except (LookupError, UnicodeDecodeError):
        return raw.decode("utf-8", errors="replace")


DATE_IN_URL = re.compile(r"/(\d{4})[-/]?(\d{2})[-/]?(\d{2})")


def url_age_days(url, today):
    """从 URL 里解析发布日期距今天数；解析不到返回 None（不据此丢弃）"""
    m = DATE_IN_URL.search(url)
    if not m:
        return None
    try:
        d = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=TZ)
    except ValueError:
        return None
    return abs((today - d).days)


# ---------------------------------------------------------------------------
# 各数据源
# ---------------------------------------------------------------------------
def src_weibo(debug=False):
    txt = fetch("https://weibo.com/ajax/side/hotSearch",
                {"Referer": "https://weibo.com/", "Accept": "application/json"})
    data = json.loads(txt)
    out = []
    for i, it in enumerate(data.get("data", {}).get("realtime", [])):
        word = (it.get("word") or it.get("note") or "").strip()
        if not word:
            continue
        out.append({
            "title": word,
            "heat": int(it.get("num") or it.get("raw_hot") or 0),
            "rank": i + 1,
            "url": "https://s.weibo.com/weibo?q=" + urllib.parse.quote(word),
            "source": "微博热搜",
            "source_type": "hotlist",
            "desc": it.get("note", ""),
        })
    if debug:
        print(f"  [微博热搜] {len(out)} 条", file=sys.stderr)
    return out


def src_baidu(debug=False):
    html = fetch("https://top.baidu.com/board?tab=realtime")
    m = re.search(r"<!--s-data:(.*?)-->", html, re.S)
    if not m:
        if debug:
            print("  [百度热搜] 解析失败", file=sys.stderr)
        return []
    data = json.loads(m.group(1))
    out = []
    n = 0
    for card in data.get("data", {}).get("cards", []):
        for it in card.get("content", []):
            word = (it.get("word") or it.get("query") or "").strip()
            if not word:
                continue
            n += 1
            out.append({
                "title": word,
                "heat": int(it.get("hotScore") or 0),
                "rank": n,
                "url": it.get("rawUrl") or it.get("url") or "",
                "source": "百度热搜",
                "source_type": "hotlist",
                "desc": (it.get("desc") or "")[:200],
            })
    if debug:
        print(f"  [百度热搜] {len(out)} 条", file=sys.stderr)
    return out


def src_toutiao(debug=False):
    txt = fetch("https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc")
    data = json.loads(txt)
    out = []
    for i, it in enumerate(data.get("data", [])):
        title = (it.get("Title") or "").strip()
        if not title:
            continue
        out.append({
            "title": title,
            "heat": int(it.get("HotValue") or 0),
            "rank": i + 1,
            "url": it.get("Url") or "",
            "source": "头条热榜",
            "source_type": "hotlist",
            "desc": (it.get("Label") or ""),
        })
    if debug:
        print(f"  [头条热榜] {len(out)} 条", file=sys.stderr)
    return out


def clean_text(s):
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"[\s\u3000]+", "", s)
    return s.strip()


def extract_links(html, base, min_len=8, max_len=80):
    """从列表页抽取 (href, title)，去导航词与重复"""
    seen = set()
    out = []
    # 人民网等站点用单引号写 href，双引号正则会整页漏抓
    for m in re.finditer(r"""<a\s[^>]*?href=["']([^"']+)["'][^>]*?>([\s\S]{0,300}?)</a>""",
                         html):
        href, title = m.group(1), clean_text(m.group(2))
        if not (min_len <= len(title) <= max_len):
            continue
        if title in NAV_WORDS or title in seen:
            continue
        if PAGE_JUNK.search(title) or LEADING_DOT.match(title):
            continue
        if not re.search(r"[\u4e00-\u9fa5]", title):
            continue
        full = urllib.parse.urljoin(base, href)
        seen.add(title)
        out.append((full, title))
    return out


def src_official(name, url, base, tier, today, debug=False, max_age=7):
    try:
        html = fetch(url)
    except Exception as e:
        if debug:
            print(f"  [{name}] 抓取失败: {e}", file=sys.stderr)
        return []
    out = []
    outdated = 0
    for href, title in extract_links(html, base):
        # 列表页常混入往年旧稿，按 URL 里的日期剔除
        age = url_age_days(href, today)
        if age is not None and age > max_age:
            outdated += 1
            continue
        out.append({
            "title": title,
            "heat": 0,
            "rank": None,
            "url": href,
            "source": name,
            "source_type": "official",
            "tier": tier,
            "desc": "",
        })
    if debug:
        print(f"  [{name}] {len(out)} 条（剔旧 {outdated}）", file=sys.stderr)
    return out[:40]


# 实测可用性（2026-10）：
#   新华网科技 33 条 / 光明网科技 质量好 / 人民网科技·社会 当天更新
#   央视网科技为 JS 渲染抓不到；新华网社会是 2023 年僵尸页 —— 均已剔除
OFFICIAL_SOURCES = [
    ("新华网科技", "http://www.news.cn/tech/", "http://www.news.cn/", "央媒"),
    # 注意：/GB/1057/index.html 这个子频道页没有正文列表（只有证照信息），
    # 必须用频道首页
    ("人民网科技", "http://scitech.people.com.cn/", "http://scitech.people.com.cn/", "央媒"),
    ("人民网社会", "http://society.people.com.cn/", "http://society.people.com.cn/", "央媒"),
    ("光明网科技", "https://tech.gmw.cn/", "https://tech.gmw.cn/", "央媒"),
]


# ---------------------------------------------------------------------------
# 过滤
# ---------------------------------------------------------------------------
def norm_title(t):
    t = re.sub(r"[#\s\u3000]", "", t)
    t = re.sub(r"[^\w\u4e00-\u9fa5]", "", t)
    return t


def severe_hit(text):
    """严重类：一票否决，对所有来源生效"""
    return bool(re.search(BLOCK_SEVERE, text))


def noise_hit(text):
    """噪音类：仅用于裁掉热榜里的无关内容，不作用于官媒（会误杀"假期科技赋能"这类）"""
    return bool(re.search(BLOCK_NOISE, text))


def topic_tags(title, desc=""):
    text = title + " " + desc
    return [k for k, pat in TOPIC_RULES.items() if re.search(pat, text)]


def person_hints(text):
    """人物信号证据列表。空列表 = 不像人物，交给题材门槛处理"""
    hits = []
    for label, pat in (("身份", PERSON_IDENTITY), ("事迹", PERSON_ACTION)):
        m = re.search(pat, text)
        if m:
            hits.append(f"{label}:{m.group(0)}")
    m = PERSON_NAME_RE.search(text)
    if m:
        hits.append(f"人名:{m.group(1)}")
    return hits


def sim(a, b):
    return SequenceMatcher(None, a, b).ratio()


# ---------------------------------------------------------------------------
# 合并
# ---------------------------------------------------------------------------
def merge_items(items, threshold=0.62):
    """同一事件跨源合并：热榜多榜同现 -> 热度累加；官媒同现 -> 官媒背书标记"""
    groups = []
    for it in items:
        key = norm_title(it["title"])
        placed = False
        for g in groups:
            if any(sim(key, norm_title(m["title"])) >= threshold for m in g):
                g.append(it)
                placed = True
                break
        if not placed:
            groups.append([it])

    merged = []
    for g in groups:
        # 标题取信息量最大的（最长），热榜标题通常更短
        lead = max(g, key=lambda x: len(x["title"]))
        sources = []
        urls = []
        for m in g:
            if m["source"] not in sources:
                sources.append(m["source"])
            if m.get("url") and m["url"] not in urls:
                urls.append(m["url"])
        hot = [m for m in g if m["source_type"] == "hotlist"]
        off = [m for m in g if m["source_type"] == "official"]
        ranks = [m["rank"] for m in hot if m.get("rank")]
        tags = sorted({t for m in g for t in topic_tags(m["title"], m.get("desc", ""))})
        all_text = " ".join(m["title"] + " " + m.get("desc", "") for m in g)
        phits = person_hints(all_text)
        merged.append({
            "text": all_text,
            "id": hashlib.md5(norm_title(lead["title"]).encode()).hexdigest()[:12],
            "title": lead["title"],
            "urls": urls,
            "sources": sources,
            "source_count": len(sources),
            "on_hotlist": bool(hot),
            "official": bool(off),
            "official_tier": next((m.get("tier") for m in off if m.get("tier")), ""),
            "heat": sum(m.get("heat", 0) for m in hot),
            "best_rank": min(ranks) if ranks else None,
            "topic_tags": tags,
            "person_hits": phits,
            "is_person": bool(phits),
            "has_competitor": bool(re.search(COMPETITOR, lead["title"] + " " +
                                             " ".join(m.get("desc", "") for m in g))),
            "desc": next((m.get("desc", "") for m in g if m.get("desc")), ""),
        })
    return merged


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--date", default=None, help="YYYY-MM-DD，默认今天")
    args = ap.parse_args()

    today_dt = (datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=TZ)
                if args.date else datetime.now(TZ))
    today = today_dt.strftime("%Y-%m-%d")
    print(f"采集日期：{today}", file=sys.stderr)

    raw_items, errors = [], []
    for fn in (src_weibo, src_baidu, src_toutiao):
        try:
            raw_items += fn(args.debug)
        except Exception as e:
            errors.append(f"{fn.__name__}: {e}")
            print(f"  [失败] {fn.__name__}: {e}", file=sys.stderr)

    for name, url, base, tier in OFFICIAL_SOURCES:
        raw_items += src_official(name, url, base, tier, today_dt, args.debug)

    # 第一层：严重类一票否决，对所有来源生效
    dropped, pool = [], []
    for it in raw_items:
        if severe_hit(it["title"] + " " + it.get("desc", "")):
            dropped.append({"title": it["title"], "reason": "严重类"})
        else:
            pool.append(it)

    # 先合并再过滤：否则"热榜在榜 + 官媒已报道"的高价值信号会被热榜的
    # 题材门槛单独砍掉，丢失"正在起量"这个关键特征
    candidates = []
    for c in merge_items(pool):
        # 官媒已过编辑把关；人物是独立机会类型，都不受题材门槛限制
        if c["official"] or c["is_person"]:
            candidates.append(c)
            continue
        if noise_hit(c["text"]):
            dropped.append({"title": c["title"], "reason": "噪音类"})
        elif not c["topic_tags"]:
            dropped.append({"title": c["title"], "reason": "无题材信号"})
        else:
            candidates.append(c)

    # 排序：官媒背书优先，其次跨源数，其次热度
    candidates.sort(key=lambda c: (
        c["official"], c["source_count"], c["heat"]
    ), reverse=True)

    result = {
        "date": today,
        "collected_at": datetime.now(TZ).isoformat(timespec="seconds"),
        "stats": {
            "raw": len(raw_items),
            "blocked": len(dropped),
            "candidates": len(candidates),
            "with_official": sum(1 for c in candidates if c["official"]),
            "with_person": sum(1 for c in candidates if c["is_person"]),
            "errors": errors,
        },
        "candidates": candidates,
        "dropped_sample": dropped[:30],
    }

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / f"{today}.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    s = result["stats"]
    print(f"\n原始 {s['raw']} 条 → 硬过滤丢弃 {s['blocked']} 条 → 合并后候选 {s['candidates']} 条")
    print(f"其中含官媒背书 {s['with_official']} 条，疑似人物 {s['with_person']} 条")
    if errors:
        print(f"源错误：{errors}")
    print(f"输出：{out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
