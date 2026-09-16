# drivers/ — DKMS 相机内核模块

本目录是 Yoga Duet 82MA 的 IPU6 相机**内核层** DKMS 包，产出 5 个模块：

| 模块 | 说明 | 来源 |
|------|------|------|
| `ov5678` | 前置 5MP RGB-IR 传感器驱动（Windows Hello 用） | vendored（自 in-tree `ov5675` 派生，重命名符号 + OV5678 PLL/VTS + OVTI5678 ACPI match） |
| `gc5035` | 后置 5MP RGB 自动对焦传感器驱动 | vendored（Intel ipu6-drivers，mainline 内核不含） |
| `ipu-bridge` | 传感器 ↔ IPU6 桥接（新增 OVTI5678/GCTI5035 到支持列表） | in-kernel 基线 + 补丁 002 |
| `intel_skl_int3472_discrete` | INT3472 GPIO/电源管理（新增 OVTI5678/GCTI5035 GPIO 类型映射） | in-kernel 基线 + 补丁 003 |
| `intel-ipu6-psys` | **PSYS 层**（IPU6 后处理子系统，mainline 内核完全不提供） | vendored（Intel ipu6-drivers，含全部必需头文件） |

## 目录结构

```
drivers/
  dkms.conf              # DKMS 配置（5 个 BUILT_MODULE_NAME）
  Makefile               # 顶层串行构建
  install.sh             # 一键 add/build/install/verify/clean（bash）
  scripts/
    prepare.sh           # DKMS PRE_BUILD：抓取 in-kernel 基线 + 打补丁
    verify-gc5035-fix.sh # 校验 gc5035 时钟修改是否生效
  patches/
    002-ipu-bridge.patch        # ipu-bridge 支持 OVTI5678 / GCTI5035
    003-int3472-discrete.patch  # INT3472 GPIO 类型映射
    004-gc5035.patch            # 移除 INT3472 CLDB 时钟 workaround
  baseline-cache/        # in-kernel 基线缓存（按内核版本）+ vendored 源码
    <kver>/{ipu_bridge,int3472}/   # 按内核版本抓取并缓存
    ov5678/ov5678.c                # vendored（不随内核版本变化）
    gc5035/gc5035.c                # vendored（打补丁 004 前）
  src/
    ov5678/ gc5035/ ipu_bridge/ int3472/   # 由 prepare.sh 生成（.gitignore）
    psys/                                  # vendored PSYS 源码 + 头文件（跟踪）
```

## 构建机制

`dkms.conf` 使用**单个** `MAKE[0]` 入口调用顶层 `Makefile`，串行编译 5 个子目录。
之所以不用 5 个并行 `MAKE[]` 条目：并行构建会在共享的 `/lib/modules/.../build`
内核树里触发 MODPOST / BTF 竞态，导致 gc5035 / ipu-bridge 间歇失败。

两类源码来源：

- **in-kernel 基线 + 补丁**（`ipu-bridge`、`int3472`）：`scripts/prepare.sh`（DKMS
  PRE_BUILD）按内核版本从 `gregkh/linux` 抓取对应 tag 的原始 `.c`，再打本仓库补丁。
  抓取结果缓存到 `baseline-cache/<kver>/`，离线也能重建。
- **vendored**（`ov5678`、`gc5035`、`psys`）：完整源码直接随包发布，不依赖网络，
  也不随内核版本漂移。

> PSYS 的源码与头文件全部 vendored：mainline 内核的
> `/lib/modules/.../build` **既没有** ipu6/ipu 头文件，**也没有** psys 目录，
> 因此 PSYS 必须自带全部依赖头文件才能独立构建（见 `src/psys/`）。

## 安装

```bash
sudo bash install.sh            # add → build → install
sudo mkinitcpio -P              # 重建 initramfs
sudo reboot
sudo bash install.sh verify     # 重启后校验 vermagic
```

或分步：

```bash
sudo bash install.sh add
sudo bash install.sh build
sudo bash install.sh install
```

## 前置条件

- CachyOS / Arch 系内核以 clang 构建（`CONFIG_CC_IS_CLANG=y`），因此模块**必须**
  用 clang 编译（顶层 Makefile 固定 `LLVM=1`）。用 gcc 会因内核构建参数
  （`-mllvm` / `-fexperimental-late-parse-attributes`）报错。
- 需要 `dkms`、`linux-headers`（或对应内核的 `-headers` 包）、`curl`（首次抓取基线）。

## 许可

本包中的驱动源码来自 Linux 内核与 Intel ipu6-drivers，均为 **GPL-2.0**。
