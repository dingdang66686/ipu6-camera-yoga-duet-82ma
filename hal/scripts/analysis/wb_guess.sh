#!/bin/bash
# 估计白平衡: 全图中"亮且低饱和"中性像素的平均 RGB (归一化到 G=1)
# 用法: wb_guess.sh <image>
IMG="$1"
# 用 IM fx 表达式: 对每个像素, 亮(brightness>B) 且低饱和(S<Smax) 的像素计入掩码
B=${2:-0.70}      # 亮度阈值
SMAX=${3:-0.25}   # 饱和度上限
# 将原图转 HSL 分别取亮度(L)与饱和度(S)通道做掩码
magick "$IMG" -colorspace HSL -channel R -separate +channel -threshold ${B}% /tmp/_L.png
magick "$IMG" -colorspace HSL -channel B -separate +channel /tmp/_S.png
# 掩码 = L通道(>=B) AND NOT(S> SMAX): 用 composite 相乘
magick /tmp/_L.png /tmp/_S.png -compose multiply -composite /tmp/_m.png
# 用掩码在 sRGB 上取平均RGB
magick "$IMG" \( /tmp/_m.png -fill black -colorize 100 \) -compose CopyOpacity -composite -format "白平衡中性区: R=%[fx:mean.r] G=%[fx:mean.g] B=%[fx:mean.b] (像素占比=%[fx:mean.a])\n" info:
echo "HINT: 中性应 R≈G≈B; 若 R<G 则是绿色/青色偏, 若 R>G 是暖偏"
