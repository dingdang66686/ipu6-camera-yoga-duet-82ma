# Intel IPU6 camera HAL 工作仓库（Lenovo Yoga Duet 7 13ITL6 / 82MA）

本仓库固化了在 **Intel IPU6 (Tiger Lake)** 平台上让前置 **OV5678**（RGB-IR）与后置
**GC5035** 摄像头通过 Intel 专有 HAL 栈（`libcamhal` + `icamerasrc`）正常出流的
全部**配置层改动**与**配套工具脚本**，以便版本化管理、随时回滚与迁移。

> 上游源代码本身**未做修改**（`ipu6-camera-hal` 保持上游 `6fefa86`）。
> 让摄像头工作的关键是**配置匹配**，而非源码补丁——这一点是本仓库存在的核心理由。

> 📄 本目录的配置从何而来（尤其是厂商 Windows 驱动逆向出的 PLL/VTS、CCM、GPIO
> 映射、graph 模板）详见 **[`../docs/WINDOWS-REVERSE-ENGINEERING.md`](../docs/WINDOWS-REVERSE-ENGINEERING.md)**。

---

## 1. 硬件与软件环境

| 项目 | 值 |
|---|---|
| 机器 | Lenovo Yoga Duet 7 13ITL6（型号 82MA） |
| 平台 | Intel IPU6（Tiger Lake），PCI `8086:9a19` |
| **前置摄像头** | **OV5678** — 5MP **RGB-IR 4×4**，定焦，Windows Hello 人脸解锁 |
| **后置摄像头** | **GC5035** — 5MP RGB 自动对焦 |
| 系统 | CachyOS (Arch-based) |
| 内核 | `7.2.4-1-cachyos`（**clang/LLD 构建** → 内核模块必须 `make LLVM=1`） |
| HAL 包 | `intel-ipu6-camera-hal-git r130.6fefa86-1`（拥有 `/etc/camera/ipu6`） |
| GStreamer 插件 | `icamerasrc-git`（分支 `icamerasrc_slim_api`，HEAD `7517af7`） |
| PipeWire 插件（可选） | `icamera-spa`（独立仓库，MIT，见 §7.1） |

### 摄像头对应关系（官方确认）
OV5678 = **前置**（屏内，IR+RGB hybrid）｜GC5035 = **后置**（背板，普通 RGB）。
OV5678 与 OV5675 同寄存器族，回读 chip id `0x005675`。

---

## 2. 关键机制：HAL 如何枚举 sensor

理解这一点才能理解本仓库的配置为何长这样：

1. `CameraParser::getAvailableSensors()` 读取 `libcamhal_profile.xml` 的
   `availableSensors` 列表，对每项 `名字-uf-CSI端口`（如 `ov5678-uf-2`）：
   - `sensorName` = `ov5678`（第一个 `-` 之前）
   - sink entity 名 = `"Intel IPU6 CSI2 2"`（最后一个 `-` 之后是 CSI 端口号）
2. `MediaControl::checkAvailableSensor(name, sink)` 找到名为该 sink 的 media entity，
   再对其 source 做**前缀匹配** `checkHasSource(entity, "ov5678 ")`。
3. 因此 **`sensorName` 必须等于 media entity 名的第一段**，也就是驱动
   `i2c_driver.driver.name`。
4. sensor XML 里的 `$I2CBUS` 占位符被替换为 `getI2CBusAddress()` 的返回值
   （即 `3-0036`），所以必须写 `ov5678 $I2CBUS` 才能展开成实际实体名 `ov5678 3-0036`。

> ⚠️ 驱动重构会改变 entity 名。若把驱动 `.name` 从 `ov5675` 改成 `ov5678`，
> 上面所有 `ov5675` 引用都必须同步改名，否则 HAL 会静默剔除该 sensor。

---

## 3. 仓库结构

> 本目录是统一相机栈仓库 `ipu6-camera-yoga-duet-82ma` 的 **hal/ 子层**。
> 内核驱动层（DKMS 包，含 PSYS）见仓库根的 [`../drivers/`](../drivers/)。

```
hal/
├── configs/                      # /etc/camera/ipu6 的配置快照（可直接部署）
│   ├── libcamhal_profile.xml          [修改] 声明可用 sensors
│   ├── psys_policy_profiles.xml       [修改] PSYS pipe_executor 策略
│   ├── gcss/
│   │   ├── graph_descriptor.xml       [修改] 图描述符（引用名需与 settings 匹配）
│   │   ├── graph_settings_gc5035.xml  [新增] GC5035 图设置
│   │   └── graph_settings_ov5678.xml  [新增] OV5678 图设置（含全部 RGB-IR 分辨率）
│   ├── sensors/
│   │   ├── gc5035-uf.xml              [新增] GC5035 sensor 定义
│   │   └── ov5678-uf.xml              [新增] OV5678 sensor 定义
│   ├── gc5035.aiqb                    [新增] GC5035 调校数据（二进制）
│   └── ov5678.aiqb                    [新增] OV5678 调校数据（golden RGB-IR，二进制）
├── scripts/
│   ├── hal/                      # HAL/icamerasrc/aiqb 直接相关工具（16 个）
│   └── analysis/                 # 帧处理与画质分析工具（24 个）
├── patches/
│   └── icamerasrc-ov5678.diff         # icamerasrc 的 IR pad 支持改动
├── deploy.sh                     # 一键部署 configs/ → /etc/camera/ipu6
└── README.md
```

`repo/`（上游 `ipu6-camera-hal` 克隆，作 diff 基线用）**不纳入本仓库**，见 `.gitignore`。

---

## 4. 配置改动详解

### 4.1 `libcamhal_profile.xml`
```xml
<availableSensors value="hm11b1-uf-1,ov01a1s-uf-1,tpg_ipu6,imx390,ar0234,
                           external_source,ar0234_usb,lt6911uxc,gc5035-uf-1,ov5678-uf-2"/>
```
末尾追加了两个本机 sensor：`gc5035-uf-1`（后置，CSI 端口 1）与 `ov5678-uf-2`（前置，CSI 端口 2）。

### 4.2 `psys_policy_profiles.xml`
```diff
- <pipe_executor name="ipu6_full_video1" pgs="isa_lb_rgbir_video_bayer"/>
+ <pipe_executor name="ipu6_full_video1" pgs="isa_lb_ir_video"/>
```

### 4.3 `gcss/graph_descriptor.xml`（20 行改动）
把引用名从 `isa_lb_rgbir_video_bayer` 改为 `isa_lb_ir_video`，**以匹配
`graph_settings_*.xml` 中 settings 块的实际程序名**。

> ★ **决定性根因**：`graph_descriptor.xml` 里 `<apply target=...>` / `<connection source/sink=...>`
> 的**引用名**必须与 settings 块的程序名一致。引用名不匹配 → `Failed to generate kernel list`
> + `not-negotiated` + `No matching graph config found`，摄像头无法出流。
> 注意 `<node name="isa_lb_rgbir_video_bayer" pg_id="187">` 是**节点定义名，不参与匹配**，无需改。

### 4.4 `gcss/graph_settings_ov5678.xml`
本机 OV5678 需按 **RGB-IR** 方式处理（IR 像素与 RGB 像素分离）。`8000`–`8007`
共 8 个分辨率块均为 RGB-IR 配置（`id=100204`、程序名 `isa_lb_ir_video`、含 `ir_md` 端口），
其余块保留为普通 bayer（`id=100000`）备用。

| settings key | 分辨率 |
|---|---|
| 8000 | 320×240 |
| 8001 | 640×360 |
| 8002 | 640×480 |
| 8003 | 1280×720 |
| 8004 | 1280×960 |
| 8005 | 1600×1200 |
| 8006 | 1920×1080 |
| 8007 | 2560×1920 |

> ⚠️ 原生分辨率 2592×1944 与半分辨率 1296×972 **没有对应 settings 块**，
> 已从 `sensors/ov5678-uf.xml` 的 `supportedStreamConfig` 中删除。
> 若声明了无 settings 支持的分辨率，出流会失败或回退。

> ⚠️ 文件内部的 `sensor_name="ov5675"` / `mode_id="ov5675_full"` 是**自洽的内部名，
> 不参与实体匹配，切勿修改**（对照：gc5035 用大写 `sensor_name="GC5035"` 也正常工作）。

### 4.5 `sensors/ov5678-uf.xml`
- `Sensor name="ov5678-uf"`
- 3 处 `$I2CBUS` 实体引用写为 `ov5678 $I2CBUS`（format / link srcName / videonode）
- `supportedTuningConfig` 的 aiqb 名为 `ov5678`
- `<graphSettingsFile value="graph_settings_ov5678.xml"/>`

### 4.6 `.aiqb` 调校数据
- `ov5678.aiqb`（424932 B, md5 `d64f0876bbf5af738aabfc475340da5a`）= **golden RGB-IR**
- `gc5035.aiqb`（396264 B, md5 `466cfdb0ebf884abc20d5b36963ccf57`）

> **颜色正确性的关键**：只有「RGB-IR 图（`id=100204`）+ golden RGB-IR aiqb」组合
> 才能得到中性色。历史上「纯 BAYER 图 + golden aiqb」偏冷、「纯 BAYER 图 + 普通 aiqb」
> 偏绿，都是错误组合。全部 8 个 8-bpp 分辨率的 U/V 均接近中性 128。

---

## 5. 部署

```bash
./deploy.sh --check      # 对比仓库与 /etc/camera/ipu6 的差异（只读）
./deploy.sh --dry-run    # 预览将要执行的操作
./deploy.sh              # 实际部署（需要 root，自动 sudo）
```

- 覆盖前会为每个文件创建 `.bak.deploy-<时间戳>` 备份，可据此回滚。
- 也可部署到自定义根：`TARGET=/tmp/test ./deploy.sh`
- 部署到 `/etc` 后无需重启内核；重新运行 `gst-launch-1.0 icamerasrc` 即可生效。

### 验证出流

```bash
# 前置 OV5678（1280x720 NV12，抓 3 帧后自然 EOS）
gst-launch-1.0 icamerasrc device-name=ov5678-uf \
  ! video/x-raw,width=1280,height=720,format=NV12 \
  ! queue ! multifilesink location=/tmp/x_%d.yuv max-files=3

# 后置 GC5035
gst-launch-1.0 icamerasrc device-name=gc5035-uf \
  ! video/x-raw,width=1280,height=720,format=NV12 \
  ! queue ! multifilesink location=/tmp/g_%d.yuv max-files=3
```

HAL 日志应出现 `aiqb file name ov5678.aiqb`（或 `gc5035.aiqb`），
每帧 NV12 1280×720 = 1 384 320 字节。

> ⚠️ **不要用 `timeout` 强杀 gst**：SIGKILL 会导致 ISYS deadlock，之后连基线都出不了流，
> 需重启系统。请用 `multifilesink max-files=N` 让 pipeline 自然 EOS。

---

## 6. 内核模块依赖：PSYS 层

专有栈的 `Intel IPU6 CSI2 BE` 等 PSYS media entity 只在**树外 (OOT) psys 驱动**中存在。

- **PSYS 现已整合进 DKMS 包。** 仓库根的 [`../drivers/`](../drivers/) 是一个产出
  5 个模块的统一 DKMS 包（`ov5678 gc5035 ipu-bridge intel_skl_int3472_discrete
  intel-ipu6-psys`），其中 `intel-ipu6-psys` 就是 PSYS 层。安装该 DKMS 包后，
  每次内核更新会自动重建 PSYS，不再需要手动编译。
- PSYS 源码与头文件全部 vendored 在 `../drivers/src/psys/`（mainline 内核既无
  psys 目录也无所需头文件，必须自带）。

```bash
# 一键安装全部 5 个模块（含 PSYS）
cd ../drivers && sudo bash install.sh
sudo mkinitcpio -P && sudo reboot
```

- **自动加载**：无需额外的 `modules-load.d`/`modprobe.d` 条目。模块自带 alias
  `auxiliary:intel_ipu6.psys intel_ipu6_psys`，udev 会在 `intel_ipu6` 注册 psys
  辅助设备时自动 `modprobe`。
- 验证：`lsmod | grep psys`、`ls -l /dev/ipu-psys0`、`dmesg | grep psys`。

---

## 7. `patches/icamerasrc-ov5678.diff`

`icamerasrc` 的改动：为 GStreamer `icamerasrc` 元素新增 `ir_%u` request pad
（`CAMERA_STREAM_IR`），用于单独请求红外流。改动文件：

- `src/gstcambasesrc.h`（+1）
- `src/gstcamerasrc.cpp`（+22/-4）

基线 commit：`7517af78f49a18dde6de86042055aa14ebe6d184`（分支 `icamerasrc_slim_api`）。

```bash
cd <icamerasrc 源码目录>          # 如 ipu6-aur/icamerasrc-git/src/icamerasrc
git apply /path/to/patches/icamerasrc-ov5678.diff
```

> 本项为**可选**：它不是当前单彩/双彩出流的必要条件，仅在需要独立 IR pad 时使用。

### 7.1 相关路径：`icamera-spa`（PipeWire SPA 插件）

除了 GStreamer 的 `icamerasrc`，本栈还有一条**可选的原生 PipeWire 消费路径**，
维护在**独立仓库**中：<https://github.com/dingdang66686/icamera-spa>（MIT）。

- 它是一个 PipeWire **SPA source 节点**（`api.icamera.source`），通过
  `camhal_backend.cpp` 直接调用与 `icamerasrc` **同一套 `libcamhal`**，
  绕过 GStreamer 与 v4l2loopback，把前后摄直接呈现在 PipeWire 图中。
- **因此它天然复用本目录部署的 `/etc/camera/ipu6` 配置与 `.aiqb`**（§4 全部改动），
  以及仓库根 `../drivers/` 安装的内核模块（含 `intel-ipu6-psys`）。
- 它还会用 WirePlumber Lua monitor 自动发现内置相机（排除 USB/UVC），并支持
  在 streaming 中通过 `pw-cli` 动态调整 3A（曝光/增益/AWB）。

```bash
git clone https://github.com/dingdang66686/icamera-spa.git
cd icamera-spa && make all
sudo make install            # → /usr/lib/spa-0.2/icamera/libspa-icamera.so
sudo make install-monitor    # WirePlumber monitor + Lua 模块 + 51-icamera.conf
systemctl --user restart wireplumber
pw-cli ls Node | grep icamera
```

> ⚠️ 它的 `51-icamera.conf` 默认会禁用 v4l2 / libcamera 相机 monitor。两条路径
> （`icamerasrc` 与 `icamera-spa`）可共存；如果桌面只想看到 icamera 源就用默认，
> 否则需编辑该 conf 去掉禁用项。

---

## 8. `scripts/`

### `scripts/hal/` — HAL 直接相关（16 个）
| 脚本 | 用途 |
|---|---|
| `aiqb_parse.py`, `aiqb_dump.py` | 解析/转储 aiqb 调校数据 |
| `aiqb_ccm_*.py`, `aiqb_extract_ccm.py`, `aiqb_scan_ccm*.py` | 提取/扫描 aiqb 中的 CCM（色彩校正矩阵） |
| `extract_lut31.py` | 提取 aiqb id31（GAMMA-LUT tone-map） |
| `parse_aiqb_records.py` | 解析 aiqb（ia_mkn/CPFF）记录链 |
| `gen_rgbir_blocks.py` | **生成 RGB-IR settings 块**（改造普通 bayer 块 → `id=100204`） |
| `grab_frame.py`, `grab_gst_frame.py`, `grab_nv12.py`, `grab_filesink_analyze.py` | 通过 GStreamer 抓取 NV12 帧 |
| `pw-spike-verify.py` | 验证帧内亮点/异常 |

### `scripts/analysis/` — 帧处理与画质分析（24 个）
- 色彩：`render_color.py`, `demosaic_color.py`, `test_demosaic_fast.py`, `color_tune.py`,
  `color_tune_server.py`, `wb_tune.py`, `wb_guess.sh`, `tone_stats.sh`, `cfa_verify.py`,
  `separate_ir.py`（RGB-IR 分离）, `gen_preview_nn.py`
- 坏点/高光：`scan_ppm_dots.py`, `check_red.py`, `analyze_highlights.py`, `jpg_check.py`, `card2_stable.py`
- 测试卡/图案：`gen_testcard.py`, `analyze_card.py`, `analyze_testpat.py`, `analyze_testpat2.py`,
  `analyze_flip.py`, `analyze_rgb.py`, `analyze_std_vs_cls.py`
- `demosaic_fast.c` — OV5678 RGB-IR demosaic + IR 分离的 C 实现（ctypes 调用），
  由 `gen_preview_nn.py` / `test_demosaic_fast.py` 使用。编译：
  ```bash
  cc -O3 -shared -fPIC -o demosaic_fast.so demosaic_fast.c -lm
  ```

---

## 9. 常用坑与经验

- **`$I2CBUS` 必须由驱动 `.name` 前缀**，否则展开的实体名不匹配。
- **sensor XML 声明的分辨率必须有对应 settings 块**，否则出流失败/回退。
- **`graph_descriptor.xml` 引用名必须等于 settings 程序名**（详见 §4.3）。
- **`graph_settings` 内部 `sensor_name`/`mode_id` 不要改**（自洽内部名）。
- **分析 NV12 的 U/V**：先把 Y 下采样 2×2 得 mask 再索引 UV（UV 平面半分辨率 + 可能有 padding），
  不要直接 2D reshape。
- **改动 settings 块时**：勿把原 `<settings>` 行留在 prefix 里（会重复 header）。
- **不要 SIGKILL gst**（见 §5 警告）。
- 包管理器升级 `intel-ipu6-camera-hal-git` 会**覆盖 `/etc/camera/ipu6`** —— 升级后用
  `./deploy.sh` 重新部署本仓库配置。
- **两条消费路径共用同一套配置**：`icamerasrc`（GStreamer）与 `icamera-spa`
  （PipeWire，见 §7.1）都读 `/etc/camera/ipu6`，改配置对两者同时生效。

---

## 10. 变更历史

| 日期 | 事件 |
|---|---|
| 2026-09-01 | 打通单彩出流；建立 RGB-IR settings 方案；全部 8 个 8-bpp 分辨率中性色 |
| 2026-09-01 | 从 `ov5678-uf.xml` 删除无 settings 支持的 2592×1944 / 1296×972 |
| 2026-09-16 | 驱动 `.name` `ov5675`→`ov5678`，HAL 配置全栈同步改名（方案 A） |
| 2026-09-16 | OOT psys 模块在 7.2.4 内核重建并验证自动加载 |
| 2026-09-16 | 本仓库建立，收拢配置快照 + 工具脚本，纳入 git 维护 |
