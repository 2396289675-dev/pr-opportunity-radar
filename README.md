# 传播机会雷达 · pr-opportunity-radar

每天自动采集**官媒科技内容**与**全网热榜**，判读"腾讯能不能跟"的传播机会，
输出跟进优先级（P0 / P1 / P2）+ 今日出圈人物，生成本地看板并推送企业微信摘要。

给腾讯公关用：找的是**可对外发声的机会**，不是新闻聚合。
系统的价值在漏斗——热榜每天几百条，能碰的常常只有 0-5 条。

## 它做什么

```
全网热榜（微博/百度/头条）
      +                      →  采集 → 溯源 → 判读 → 看板 → 企微推送
官媒科技（新华/人民/光明/中新）
```

每条目产出六项：**报道媒体名 · 原文链接 · 事件描述 · 腾讯业务对位 · 风险 · 窗口期**。

- **P0** 立刻跟进（"官媒正面报道 + 正在快速起量"的交集，大部分日子是 0 条，属正常）
- **P1** 今日内看
- **P2** 观察储备
- 另有独立的**今日出圈人物**板块（素人走红、小店主爆火、正面典型人物等）

## 安装

### 方式一：一键安装（macOS / Linux）

```bash
cd pr-opportunity-radar
./install.sh
```

脚本会把整个目录复制（或软链）到 `~/.workbuddy/skills/pr-opportunity-radar/`，
并建好 `data/` 目录骨架。

### 方式二：手动安装

把整个 `pr-opportunity-radar` 文件夹放到 skill 目录下即可：

| 系统 | 路径 |
|---|---|
| macOS / Linux | `~/.workbuddy/skills/` |
| Windows | `%USERPROFILE%\.workbuddy\skills\` |

**整个文件夹本身就是项目根目录**——脚本用自身位置推导路径，
放到任何地方都能跑，不需要改配置。

## 环境要求

- **Python 3.9+**，**零第三方依赖**（只用标准库）
- 网络可访问国内媒体站点
- 企微推送需要 `wecom-cli` 并完成授权（可选，不装也能用本地看板）

## 快速开始

```bash
cd pr-opportunity-radar
mkdir -p data/raw data/judge data/cases

python3 scripts/collect.py --debug        # 1. 采集
python3 scripts/enrich.py --limit 40      # 2. 溯源（补媒体名/链接/事件素材）
                                          # 3. 判读：由 AI 读候选后写 data/judge/<日期>.json
python3 scripts/check_biz.py              # 4. 校验业务对位是否都在启用池内
python3 scripts/build_cases.py            # 5. 合并
python3 scripts/render_dashboard.py       # 6. 生成看板
open dashboard.html                       # 7. 查看
```

> **顺序不能反**：`collect.py` 会覆盖当天原始数据，
> 溯源（enrich）必须在其之后跑，否则补全的媒体名与链接全丢。

配好定时任务后，第 3 步的判读由 AI 自动完成，产出的是**结论**不是待办清单。

## 目录结构

```
pr-opportunity-radar/
├── SKILL.md                   技能定义（AI 读取，含全部判读标准与实测硬约束）
├── README.md                  本文件
├── install.sh                 一键安装脚本
├── scripts/
│   ├── collect.py             采集 + 硬过滤 + 跨源合并
│   ├── enrich.py              溯源：补报道媒体名 / 原文链接 / 正文摘要
│   ├── build_cases.py         合并采集与判读
│   ├── render_dashboard.py    渲染看板（数据内联，可直接双击打开）
│   ├── render_bizpool.py      渲染业务池筛选页
│   ├── apply_biz.py           把勾选结果写回配置
│   └── check_biz.py           校验业务对位合法性
├── assets/                    页面模板
├── config/
│   └── tencent_biz.json       腾讯业务白名单（40 条，当前启用 26 条）
├── data/                      运行时数据（github 上已忽略）
│   ├── raw/<date>.json        当日采集候选
│   ├── judge/<date>.json      判读结果
│   └── cases.json             看板数据源
├── dashboard.html             生成的看板
└── biz_pool.html              生成的业务池筛选页
```

## 腾讯业务白名单

判读时"对位到腾讯哪个业务"**只能从白名单里挑**，防止 AI 自己拍业务名
（此前误用过"腾讯招聘"——那是 HR 职能，不是对外业务线）。

配置在 `config/tencent_biz.json`，40 条分 5 组：
C 端产品与平台 / AI 与技术能力 / 数字内容与文娱 / 行业解决方案 / 公益与社会价值。

调整方式：双击 `biz_pool.html` 勾选 → 导出 →

```bash
python3 scripts/apply_biz.py ~/Downloads/tencent_biz_selected.json
```

## 判读红线

以下内容**一票否决**，不参与打分：

- 涉负面、涉争议、涉政敏感
- 竞品强关联
- **内容内核是给官方纠错/挑错的**——社会贡献必须是正向建设，
  要能被官方和主流媒体乐于转发

腾讯的定位是**发起方与工具提供方**，不抢叙事、不把自己写成英雄。

## 已知限制

- **微信公众号抓不到**，需手动补链接
- 央视网、知乎需登录或 JS 渲染，未接入
- 热榜条目衰减快，隔天补看意义不大；链接有时效参数
- 搜狗搜索结果多为跳转壳，可点开但解不出真实地址

## License

内部工具，按需使用。
