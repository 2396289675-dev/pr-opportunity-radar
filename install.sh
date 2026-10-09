#!/usr/bin/env bash
# 传播机会雷达 · 一键安装到 WorkBuddy 技能目录
#
# 用法：在 pr-opportunity-radar 目录内执行 ./install.sh
# 可选参数：
#   --link   用软链接而不是复制（改代码即生效，适合开发）
#
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DST="${HOME}/.workbuddy/skills/pr-opportunity-radar"
MODE="copy"
[ "${1:-}" = "--link" ] && MODE="link"

echo "传播机会雷达 · 安装"
echo "  源目录：${SRC}"
echo "  目标：${DST}"
echo "  方式：${MODE}"
echo

# ---- 1. 检查 Python ----
if command -v python3 >/dev/null 2>&1; then
  PV="$(python3 --version 2>&1)"
  echo "✓ Python：$PV"
  MAJ="$(echo "$PV" | sed -E 's/Python ([0-9]+)\.([0-9]+).*/\1/')"
  MIN="$(echo "$PV" | sed -E 's/Python ([0-9]+)\.([0-9]+).*/\2/')"
  if [ "$MAJ" -lt 3 ] || { [ "$MAJ" -eq 3 ] && [ "$MIN" -lt 9 ]; }; then
    echo "✗ 需要 Python 3.9 或更高版本"
    exit 1
  fi
else
  echo "✗ 未找到 python3，请先安装 Python 3.9+"
  exit 1
fi

# ---- 2. 安装 ----
if [ -e "$DST" ] && [ "$MODE" = "copy" ]; then
  echo "  目标已存在，备份为 ${DST}.bak"
  rm -rf "${DST}.bak"
  mv "$DST" "${DST}.bak"
fi

mkdir -p "$(dirname "$DST")"

if [ "$MODE" = "link" ]; then
  rm -rf "$DST"
  ln -s "$SRC" "$DST"
else
  mkdir -p "$DST"
  # 复制除运行时数据与产物外的全部内容
  rsync -a --exclude 'data/' --exclude 'dashboard.html' \
        --exclude 'biz_pool.html' --exclude '__pycache__/' \
        --exclude '.DS_Store' "$SRC"/ "$DST"/
fi

# ---- 3. 数据目录骨架 ----
mkdir -p "$DST/data/raw" "$DST/data/judge" "$DST/data/cases"

echo
echo "✓ 已安装到 ${DST}"
ls -1 "$DST"

# ---- 4. 冒烟测试：确认脚本可运行 ----
echo
echo "冒烟测试："
if python3 "$DST/scripts/collect.py" --help >/dev/null 2>&1; then
  echo "  ✓ collect.py 可运行"
else
  echo "  · collect.py 无 --help（正常，直接跑即可）"
fi
for f in build_cases check_biz render_dashboard render_bizpool; do
  if python3 -c "import py_compile;py_compile.compile('$DST/scripts/$f.py',doraise=True)" 2>/dev/null; then
    echo "  ✓ $f.py 语法检查通过"
  else
    echo "  ✗ $f.py 编译失败"
  fi
done

echo
echo "下一步："
echo "  cd ${DST}"
echo "  python3 scripts/collect.py --debug"
echo
echo "注：企微推送需另装 wecom-cli 并授权；不装也能用本地看板。"
