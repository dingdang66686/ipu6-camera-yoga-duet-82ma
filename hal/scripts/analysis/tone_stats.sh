#!/bin/bash
# 量化分析单张图片的整体色调: 每通道均值/中位/饱和度/亮度, 归一化色彩偏差
# 用法: tone_stats.sh <image> [gravity_crop_percent]
IMG="$1"
if [ -z "$IMG" ]; then echo "用法: $0 <image>"; exit 1; fi
CROP="${2:-100}"   # 默认整图
GRAV="center"

echo "### $IMG"
echo "-- 尺寸:"; identify "$IMG" | awk '{print $3}'

# 采样区域
if [ "$CROP" != "100" ]; then
  REGION=" -gravity $GRAV -crop ${CROP}%x${CROP}%+0+0 +repage"
else
  REGION=""
fi

# 每通道均值/标准偏差
magick "$IMG" $REGION -format "R_mean=%[fx:mean.r] G_mean=%[fx:mean.g] B_mean=%[fx:mean.b]\n" info:
magick "$IMG" $REGION -format "R_sd=%[fx:standard_deviation.r] G_sd=%[fx:standard_deviation.g] B_sd=%[fx:standard_deviation.b]\n" info:
# 每通道中位数(用 50% 分位近似 - 直方图)
magick "$IMG" $REGION -format "R_med=%[fx:quantumrange*%[fx:mean.r]]\n" info: >/dev/null 2>&1
# 亮度与饱和度(相对均值) - 用 HSB 通道
magick "$IMG" $REGION -colorspace HSL -channel G -separate +channel -format "Lightness_mean=%[fx:mean]\n" info:
magick "$IMG" $REGION -colorspace HSL -channel B -separate +channel -format "Saturation_mean=%[fx:mean] Saturation_sd=%[fx:standard_deviation]\n" info:

# 归一化色彩偏差(相对亮度): channel/luma
magick "$IMG" $REGION -colorspace sRGB -format "Luma=%[fx:0.2126*mean.r+0.7152*mean.g+0.0722*mean.b]\n" info:
