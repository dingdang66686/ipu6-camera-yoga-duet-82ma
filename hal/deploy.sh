#!/usr/bin/env bash
#
# deploy.sh — 将本仓库 configs/ 下的 HAL 配置快照部署回 /etc/camera/ipu6
#
# 目标：Intel IPU6 camera HAL (libcamhal) 运行时配置目录。
# 部署前会为每个将被覆盖/新增的文件创建带时间戳的 .bak 备份。
#
# 用法：
#   ./deploy.sh                 # 部署全部（需 sudo）
#   ./deploy.sh --dry-run       # 仅打印将要执行的操作，不落盘
#   ./deploy.sh --check         # 对比仓库与 /etc 的差异（需 sudo 读 /etc）
#   TARGET=/path ./deploy.sh    # 部署到自定义根（如测试用临时目录）
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$REPO_DIR/configs"
TARGET="${TARGET:-/etc/camera/ipu6}"
STAMP="$(date +%Y%m%d-%H%M%S)"

DRY_RUN=0
CHECK_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --check)   CHECK_ONLY=1 ;;
    -h|--help) sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "未知参数: $arg" >&2; exit 2 ;;
  esac
done

# 需要 sudo 写入 /etc（若 TARGET 指向用户可写目录则不需要）
need_sudo() { [[ "$TARGET" == /etc/* || "$TARGET" == /usr/* ]]; }
if need_sudo && [[ $EUID -ne 0 ]]; then
  if [[ $DRY_RUN -eq 0 && $CHECK_ONLY -eq 0 ]]; then
    echo ">> 需要 root 权限写入 $TARGET，使用 sudo 重新执行…"
    exec sudo -n "$0" "$@"
  fi
fi

files=()
while IFS= read -r f; do files+=("$f"); done < <(cd "$SRC_DIR" && find . -type f | sed 's|^\./||' | sort)

echo "== 仓库: $SRC_DIR"
echo "== 目标: $TARGET"
echo "== 文件数: ${#files[@]}"
echo

if [[ $CHECK_ONLY -eq 1 ]]; then
  echo "== 差异检查 (仅报告，不修改) =="
  rc=0
  for rel in "${files[@]}"; do
    if [[ ! -e "$TARGET/$rel" ]]; then
      printf "  [缺失]   %s\n" "$rel"
    elif cmp -s "$SRC_DIR/$rel" "$TARGET/$rel"; then
      printf "  [一致]   %s\n" "$rel"
    else
      printf "  [不同]   %s\n" "$rel"
      rc=1
    fi
  done
  exit $rc
fi

if [[ $DRY_RUN -eq 1 ]]; then
  echo "== DRY-RUN，以下操作不会执行 =="
  for rel in "${files[@]}"; do
    if [[ -e "$TARGET/$rel" ]] && cmp -s "$SRC_DIR/$rel" "$TARGET/$rel"; then
      printf "  [跳过]   %s (已一致)\n" "$rel"
    else
      printf "  [安装]   %s\n" "$rel"
      [[ -e "$TARGET/$rel" ]] && printf "           └─ 备份为 %s.bak.deploy-%s\n" "$rel" "$STAMP"
    fi
  done
  exit 0
fi

echo "== 开始部署（覆盖项将先备份为 .bak.deploy-$STAMP）=="
for rel in "${files[@]}"; do
  dst="$TARGET/$rel"
  mkdir -p "$(dirname "$dst")"
  if [[ -e "$dst" ]] && cmp -s "$SRC_DIR/$rel" "$dst"; then
    printf "  [跳过]   %s\n" "$rel"
    continue
  fi
  if [[ -e "$dst" ]]; then
    cp -p "$dst" "$dst.bak.deploy-$STAMP"
    printf "  [备份]   %s.bak.deploy-%s\n" "$rel" "$STAMP"
  fi
  cp -p "$SRC_DIR/$rel" "$dst"
  printf "  [安装]   %s\n" "$rel"
done

echo
echo "== 完成。回滚：将对应 *.bak.deploy-$STAMP 还原即可。"
echo "   例: sudo cp -p $TARGET/sensors/ov5678-uf.xml.bak.deploy-$STAMP $TARGET/sensors/ov5678-uf.xml"
