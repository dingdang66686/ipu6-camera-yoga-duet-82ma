# IPU6 相机栈完整解决方案 — Lenovo Yoga Duet 7 13ITL6 (82MA)

一套针对 **Lenovo Yoga Duet 7 13ITL6（机型代号 82MA，Intel Tiger Lake / IPU6）**
的完整 Linux 相机栈适配方案，涵盖从**内核驱动**到**用户态 HAL 配置**的全部层。

> 本仓库解决的核心问题：mainline 内核 + 发行版组件**默认无法**驱动这台机器的
> IPU6 双摄（前置 OV5678 RGB-IR + 后置 GC5035）。需要补上三层缺失内容：
> 定制内核模块、树外 PSYS 驱动、以及 HAL 运行时配置。

---

## 硬件环境

| 项 | 值 |
|----|----|
| 机型 | Lenovo Yoga Duet 7 13ITL6（`82MA`） |
| SoC | Intel Tiger Lake（IPU6，PCI ID `8086:9a19`） |
| 前置摄像头 | **OV5678** — 5MP RGB-IR（4×4 彩色滤光 + IR），定焦，Windows Hello 用 |
| 后置摄像头 | **GC5035** — 5MP RGB，自动对焦 |
| 参考系统 | CachyOS（Arch 系），内核 `7.2.4-1-cachyos`（clang 构建） |

---

## 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│  应用层：GStreamer / PipeWire / libcamera 应用                 │
├─────────────────────────────────────────────────────────────┤
│  icamerasrc (GStreamer 插件，专有栈入口)          ← AUR 包     │
│      · patches/icamerasrc-ov5678.diff 提供 IR pad 支持        │
├─────────────────────────────────────────────────────────────┤
│  icamera-spa (PipeWire SPA 插件，可选替代路径) ← 独立仓库      │
│      · 直接对接 libcamhal，绕过 GStreamer / v4l2loopback      │
├─────────────────────────────────────────────────────────────┤
│  libcamhal (专有 IPU6 HAL)                      ← AUR 包     │
│      · 运行时配置 /etc/camera/ipu6/**            ← hal/ 部署  │
├─────────────────────────────────────────────────────────────┤
│  PSYS 子系统 (intel-ipu6-psys.ko)               ← drivers/   │
├─────────────────────────────────────────────────────────────┤
│  ISYS 子系统 (intel-ipu6-isys.ko，in-kernel)                  │
├─────────────────────────────────────────────────────────────┤
│  IPU6 核心 (intel-ipu6.ko，in-kernel)                         │
├─────────────────────────────────────────────────────────────┤
│  桥接/电源：ipu-bridge、intel_skl_int3472_discrete  ← drivers/│
├─────────────────────────────────────────────────────────────┤
│  传感器驱动：ov5678、gc5035                          ← drivers/│
└─────────────────────────────────────────────────────────────┘
```

本仓库负责其中的 **`drivers/` 与 `hal/`** 两层；`libcamhal` / `icamerasrc` 是
发行版（AUR）组件，本仓库提供其**配置**与**可选补丁**。

`icamera-spa` 是本栈的**可选用户态消费路径**（PipeWire 原生插件），维护在
**独立仓库**中，但直接复用本仓库部署的 `libcamhal` 与 `/etc/camera/ipu6` 配置,
详见文末「[相关项目：icamera-spa](#相关项目icamera-spa-pipewire-spa-插件)」。

---

## 仓库结构

```
ipu6-camera-yoga-duet-82ma/
├── drivers/          # 内核层：统一 DKMS 包（5 个模块，含 PSYS）
│   ├── dkms.conf     ·  install.sh  ·  Makefile
│   ├── scripts/prepare.sh        # 按内核版本抓取 in-kernel 基线 + 打补丁
│   ├── patches/{002,003,004}-*.patch
│   ├── baseline-cache/           # 基线缓存 + vendored 源码
│   └── src/{ov5678,gc5035,ipu_bridge,int3472,psys}/
│       └── README.md             # 驱动层详细文档
├── hal/              # 用户态层：libcamhal 配置快照 + 工具脚本
│   ├── configs/                  # /etc/camera/ipu6 的完整快照（含 .aiqb）
│   ├── deploy.sh                 # 一键部署 configs/ → /etc/camera/ipu6
│   ├── patches/icamerasrc-ov5678.diff
│   ├── scripts/{hal,analysis}/   # aiqb 分析、抓帧、画质调校工具
│   └── README.md                 # HAL 层详细文档（配置改动逐项解释）
└── README.md         # 本文件
```

---

## 快速开始

### 0. 前置依赖

```bash
# 内核构建依赖
sudo pacman -S --noconfirm dkms base-devel clang llvm curl

# 专有用户态组件（AUR，需 paru/yay 等 AUR helper）
paru -S --noconfirm intel-ipu6-camera-bin intel-ipu6-camera-hal-git icamerasrc-git
```

> ⚠️ **clang 构建**：CachyOS 内核以 clang 编译（`CONFIG_CC_IS_CLANG=y`），
> 因此内核模块**必须**用 clang 编译（DKMS 包已固定 `LLVM=1`）。用 gcc 会因
> 内核构建参数（`-mllvm` / `-fexperimental-late-parse-attributes`）报错。

### 1. 安装内核驱动（DKMS，含 PSYS）

```bash
cd drivers
sudo bash install.sh          # add → build → install（5 个模块）
sudo mkinitcpio -P            # 重建 initramfs
sudo reboot
```

重启后校验：

```bash
sudo bash install.sh verify   # 检查 5 个模块的 vermagic 是否匹配当前内核
```

### 2. 部署 HAL 配置

```bash
cd hal
./deploy.sh --check           # 先看差异（不落盘）
./deploy.sh                   # 部署 configs/ → /etc/camera/ipu6（自动 sudo + 备份）
```

### 3. 验证出流

```bash
# 前置 OV5678（1280x720 NV12）
gst-launch-1.0 icamerasrc device-name=ov5678 io-mode=4 ! \
    video/x-raw,format=NV12,width=1280,height=720 ! filesink location=/tmp/front.nv12

# 后置 GC5035
gst-launch-1.0 icamerasrc device-name=gc5035 io-mode=4 ! \
    video/x-raw,format=NV12 ! filesink location=/tmp/rear.nv12

# media 拓扑 / 设备枚举
media-ctl -d /dev/media0 -p
v4l2-ctl --list-devices
```

---

## 关键设计说明

### 为什么 PSYS 必须随 DKMS 包一起发布？

`Intel IPU6 CSI2 BE` 等 PSYS media entity 只在**树外 PSYS 驱动**中存在，
mainline 内核**完全不提供** PSYS（既无 `psys/` 目录，也无 `ipu6-*.h` / `ipu-*.h`
头文件）。因此本仓库将 PSYS 的全部源码与依赖头文件 **vendored** 进
`drivers/src/psys/`，并作为第 5 个模块随 DKMS 一起构建——这样每次内核更新后
PSYS 会自动重建，不再需要手动编译。

### 两类源码来源

- **in-kernel 基线 + 补丁**（`ipu-bridge`、`int3472`）：`scripts/prepare.sh` 按内核
  版本从 `gregkh/linux` 抓取对应 tag 的原始 `.c`，再打本仓库补丁；抓取结果缓存到
  `baseline-cache/<kver>/`，离线也能重建。
- **vendored**（`ov5678`、`gc5035`、`psys`）：完整源码随包发布，不依赖网络，也不会
  随内核版本漂移。

### ov5678 为何是独立驱动而非改 in-tree ov5675？

in-tree 的 `ov5675` 驱动不能直接用于 OV5678（PLL/VTS 值不同，且 ACPI match 会与
内置驱动冲突）。本仓库把 `ov5678` 做成**符号重命名 + OV5678 专用参数**的独立驱动，
确保不干扰内置 `ov5675`。

---

## 相关项目：icamera-spa（PipeWire SPA 插件）

`icamera-spa` 是本栈的**可选用户态消费路径**，维护在**独立仓库**：

> <https://github.com/dingdang66686/icamera-spa>（MIT）

它是一个**原生 PipeWire SPA source 节点**，直接从 `libcamhal` 拉取 NV12 帧，
**完全绕过 GStreamer (`icamerasrc`) 与 v4l2loopback**，把前后摄以 PipeWire
`Video/Source` 节点呈现给桌面应用（Camera、视频会议、xdg-desktop-portal 等），
并支持在 streaming 中通过 `pw-cli` 动态修改 3A（曝光/增益/AWB）。

### 与本仓库的关系

- **不替代本仓库，而是复用本仓库的两层成果**：
  - 依赖 `drivers/` 安装的内核驱动（含 `intel-ipu6-psys`）；
  - 复用 `hal/` 部署的 `/etc/camera/ipu6` 配置与 `.aiqb`（libcamhal 直接读取）。
- 二者是 **libcamhal 的两个并列消费者**：`icamerasrc`（GStreamer）与
  `icamera-spa`（PipeWire），可同时安装、互不冲突。
- 本仓库**不包含**其源码；`hal/` 中仅提供它同样会用到的 HAL 配置与调校数据。

### 安装与使用（简）

```bash
# 1) 先完成本仓库的 drivers/ 与 hal/ 部署（见上文「快速开始」）

# 2) 构建并安装 SPA 插件 + WirePlumber 集成
git clone https://github.com/dingdang66686/icamera-spa.git
cd icamera-spa && make all
sudo make install            # → /usr/lib/spa-0.2/icamera/libspa-icamera.so
sudo make install-monitor    # WirePlumber monitor + Lua 模块 + 51-icamera.conf
systemctl --user restart wireplumber

# 3) 验证节点
pw-cli ls Node | grep icamera
```

> ⚠️ 其 `51-icamera.conf` 默认会**禁用 v4l2 与 libcamera 相机 monitor**，让桌面只
> 看到 icamera 源。若系统还有依赖 v4l2/libcamera 的应用，请编辑该文件去掉禁用项。

---

## 已知注意事项

1. **`/etc/modprobe.d` 的 softdep 可能过时**：本机曾存在
   `softdep ipu_bridge pre: ov5675 gc5035`，其中 `ov5675` 应为 `ov5678`。
   安装后请检查并按需修正：
   ```bash
   grep -rn "ov5675" /etc/modprobe.d/ /etc/modules-load.d/ 2>/dev/null
   # 如命中，将 ov5675 改为 ov5678
   ```
2. **initramfs**：每次安装/更新 DKMS 模块后都需 `sudo mkinitcpio -P`。
3. **debug 符号**：若 `modinfo` 显示模块路径不在 `/lib/modules/*/updates/dkms/`，
   说明被内置/旧模块抢先，需确认 `dkms install --force` 已生效。

---

## 许可

- `drivers/` — 内核驱动源码来自 Linux 内核与 Intel ipu6-drivers，**GPL-2.0**。
- `hal/configs/` 中的 XML / `.aiqb` — Intel 相机 HAL 运行时配置，随
  `intel-ipu6-camera-hal` / `intel-ipu6-camera-bin` 分发。
- `hal/scripts/`、`deploy.sh`、`install.sh` — 本仓库原创，**MIT**。
- `icamera-spa` — 独立项目，**MIT**（见文末「相关项目」）。
