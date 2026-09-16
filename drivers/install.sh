#!/usr/bin/env bash
# install.sh — 构建/安装 Yoga Duet 82MA 的 IPU6 相机内核模块（bash 版）
#
# 本脚本构建并安装 5 个模块到 /updates/dkms（覆盖内核内置/旧版本模块）：
#   ov5678   gc5035   ipu-bridge   intel_skl_int3472_discrete   intel-ipu6-psys
#
# 其中 intel-ipu6-psys 是 PSYS 层（mainline 内核不含，必须由本包提供）。
#
# 必须用 bash 运行：
#   sudo bash install.sh            # 默认 all: add → build → install
# 或分步：
#   sudo bash install.sh add
#   sudo bash install.sh build
#   sudo bash install.sh install
#   sudo bash install.sh clean
#   sudo bash install.sh verify

set -euo pipefail

readonly PKG_NAME="yoga-duet-ipu6-cameras"
readonly PKG_VERSION="0.2.0"
readonly KVER="$(uname -r)"
readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# DKMS 要求包源码位于 /usr/src/<pkg>-<ver>
readonly DKMS_SRC="/usr/src/${PKG_NAME}-${PKG_VERSION}"

readonly MODULES=(
    ov5678
    gc5035
    ipu-bridge
    intel_skl_int3472_discrete
    intel-ipu6-psys
)

require_root() {
    if [[ $EUID -ne 0 ]]; then
        echo "错误：需要 root 权限。请用 sudo 运行：" >&2
        echo "  sudo bash $0" >&2
        exit 1
    fi
}

check_dkms() {
    if ! command -v dkms >/dev/null 2>&1; then
        echo "错误：未安装 dkms。" >&2
        echo "请先安装（root）： sudo pacman -S --noconfirm dkms" >&2
        exit 1
    fi
}

sanitize_sources() {
    # 移除编译产物，避免污染 dkms 打包
    find "${SCRIPT_DIR}/src" -type f \
        \( -name '*.o' -o -name '*.ko' -o -name '*.mod' -o -name '*.mod.c' \
           -o -name '*.cmd' -o -name 'Module.symvers' -o -name 'modules.order' \) \
        -delete 2>/dev/null || true
    find "${SCRIPT_DIR}/src" -type d -name '.tmp_versions' -exec rm -rf {} + 2>/dev/null || true
    # 四个由 prepare.sh 生成的驱动源（psys 是 vendored，保留）
    rm -f "${SCRIPT_DIR}"/src/ov5678/*.c \
          "${SCRIPT_DIR}"/src/gc5035/*.c \
          "${SCRIPT_DIR}"/src/ipu_bridge/*.c \
          "${SCRIPT_DIR}"/src/int3472/*.c 2>/dev/null || true
}

usage() {
    grep -E '^#( |$)' "${BASH_SOURCE[0]}" | sed -n '2,13p' | sed 's/^# \{0,1\}//'
    echo
    echo "用法: sudo bash $0 [all|add|build|install|clean|verify]"
    echo "  默认 all: 依次 add → build → install"
}

cmd_add() {
    require_root
    check_dkms
    sanitize_sources
    echo "==> dkms add：安装到 ${DKMS_SRC}"
    # 移除同版本旧记录；并提示移除旧的 0.1.0（若存在）
    if dkms status 2>/dev/null | grep -q "${PKG_NAME}/${PKG_VERSION}"; then
        dkms remove -m "${PKG_NAME}" -v "${PKG_VERSION}" --all 2>/dev/null || true
    fi
    if dkms status 2>/dev/null | grep -q "${PKG_NAME}/0.1.0"; then
        echo "   检测到旧版 0.1.0（不含 PSYS），先移除以免冲突"
        dkms remove -m "${PKG_NAME}" -v "0.1.0" --all 2>/dev/null || true
        rm -rf "/usr/src/${PKG_NAME}-0.1.0" 2>/dev/null || true
    fi
    rm -rf "${DKMS_SRC}"
    mkdir -p "${DKMS_SRC}"
    cp -a "${SCRIPT_DIR}/." "${DKMS_SRC}/"
    pushd "${DKMS_SRC}" >/dev/null
    dkms add -m "${PKG_NAME}" -v "${PKG_VERSION}"
    popd >/dev/null
}

cmd_build() {
    require_root
    check_dkms
    echo "==> dkms build"
    dkms build -m "${PKG_NAME}" -v "${PKG_VERSION}" -k "${KVER}"
    echo "    构建完成。check: dkms status"
}

cmd_install() {
    require_root
    check_dkms
    echo "==> dkms install 到 /lib/modules/${KVER}/updates/dkms"
    dkms install -m "${PKG_NAME}" -v "${PKG_VERSION}" -k "${KVER}" --force
    echo "==> 已安装。下一步："
    echo "    1) 重建 initramfs（按引导器选择）："
    echo "         GRUB/systemd-boot:  sudo mkinitcpio -P"
    echo "         Limine:             sudo limine-mkinitcpio   # 注意: mkinitcpio -P 在 Limine 上不会更新启动项"
    echo "       （相机模块不在 initramfs 内、由 udev 运行时加载，此步可选但推荐）"
    echo "    2) 重启系统（IPU6 模块无法安全热重载，必须重启）"
    echo "    3) 验证: sudo bash $0 verify"
}

cmd_verify() {
    echo "==> 校验已安装模块（vermagic 与当前内核是否一致）"
    local rc=0
    for m in "${MODULES[@]}"; do
        local path
        path="$(modinfo -n "$m" 2>/dev/null || true)"
        if [[ -z "$path" ]]; then
            printf '  %-32s 缺失\n' "$m"; rc=1; continue
        fi
        local vm
        vm="$(modinfo -F vermagic "$m" 2>/dev/null | awk '{print $1}')"
        if [[ "$vm" == "$KVER" ]]; then
            printf '  %-32s OK   %s\n' "$m" "$path"
        else
            printf '  %-32s 不匹配 (vermagic=%s, 期望=%s)\n' "$m" "$vm" "$KVER"; rc=1
        fi
    done
    echo
    echo "==> 关键检查：intel-ipu6-psys 是否来自 /updates/dkms"
    modinfo -n intel-ipu6-psys 2>/dev/null || echo "  (未找到)"
    return $rc
}

cmd_clean() {
    require_root
    check_dkms
    dkms remove -m "${PKG_NAME}" -v "${PKG_VERSION}" --all 2>/dev/null || true
    rm -rf "${DKMS_SRC}"
    echo "已清理 ${PKG_NAME} ${PKG_VERSION} 的 dkms 记录与 /usr/src staging"
}

main() {
    local action="${1:-all}"
    case "$action" in
        all)     cmd_add; cmd_build; cmd_install ;;
        add)     cmd_add ;;
        build)   cmd_build ;;
        install) cmd_install ;;
        verify)  cmd_verify ;;
        clean)   cmd_clean ;;
        *)       usage; exit 1 ;;
    esac
}

main "$@"
