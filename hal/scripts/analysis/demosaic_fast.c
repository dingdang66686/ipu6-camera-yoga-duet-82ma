/*
 * demosaic_fast.c — OV5678 RGB-IR demosaic + IR 分离（C 实现，供 ctypes 调用）
 *
 * 1:1 复现 /home/stray/camera-work/demosaic_color.py 的核心算法，
 * 但用 C 编写以获得实时性能。
 *
 * 4x4 CFA（绝对相位）:
 *    (0,0)G (0,1)I (0,2)G (0,3)I
 *    (1,0)R (1,1)G (1,2)B (1,3)G
 *    (2,0)G (2,1)I (2,2)G (2,3)I
 *    (3,0)B (3,1)G (3,2)R (3,3)G
 *    G:R:B = 4:1:1, IR = (偶行,奇列)
 *
 * API（供 ctypes 调用）:
 *   read_raw(buf, n, px, W, H)                解码 raw bytes -> uint16*px (无 stride)
 *   read_raw_stride(buf,n,px,W,H,stride)      带行 padding 的版本
 *   demosaic_nn(px,W,H,OX,OY,OW,OH,wb_r,wb_b,rgb)  出 rgb 彩色
 *   ir_nn(px,W,H,OX,OY,OW,OH,ir)              出 ir 灰度
 *   demosaic_and_ir(px, W,H, OX,OY,OW,OH,
 *                   wb_r, wb_b, rgb, ir)      出 rgb(uint8*OH*OW*3) + ir(uint8*OH*OW)
 */

#include <stdint.h>
#include <stdlib.h>
#include <math.h>

/* ---- raw 解码：每像素 2 字节，低 10 位取值 ----
 * stride: 每行字节数(含 padding)。行内有效像素 W 个(每像素 2 字节)，
 * 行尾可能有 padding 字节，按行读取时跳过。stride<=0 时视为无 padding，
 * 即 stride = W*2（连续布局）。
 */
static void read_raw_impl(const uint8_t* data, size_t n, uint16_t* px,
                          int W, int H, int stride) {
    if (stride <= 0) stride = W * 2;
    int y;
    size_t need = (size_t)stride * H;
    size_t len = n < need ? n : need;
    for (y = 0; y < H; y++) {
        const uint8_t* row = data + (size_t)y * stride;
        size_t rowo = (size_t)y * stride;
        int x;
        for (x = 0; x < W; x++) {
            size_t o = rowo + (size_t)x * 2;
            if (o + 1 < len)
                px[(size_t)y * W + x] = (row[x * 2] | ((uint16_t)row[x * 2 + 1] << 8)) & 0x3FF;
            else
                px[(size_t)y * W + x] = 0;
        }
    }
}

/* 兼容旧接口：无 stride（连续布局） */
void read_raw(const uint8_t* data, size_t n, uint16_t* px, int W, int H) {
    read_raw_impl(data, n, px, W, H, W * 2);
}

/* 带 stride 版本：供带行 padding 的 capture 帧使用 */
void read_raw_stride(const uint8_t* data, size_t n, uint16_t* px,
                     int W, int H, int stride) {
    read_raw_impl(data, n, px, W, H, stride);
}

/* 绝对相位 -> 通道: 0=R,1=G,2=B,-1=IR */
static const int PHASE[16] = {
    1, -1, 1, -1,   /* row0: G I G I */
    0,  1, 2,  1,   /* row1: R G B G */
    1, -1, 1, -1,   /* row2: G I G I */
    2,  1, 0,  1    /* row3: B G R G */
};
static int chan_at(int Y, int X) {
    return PHASE[((Y & 3) << 2) | (X & 3)];
}

/* 采样行式插值：复现 Python interp()
 * 遍历绝对行 Y in [inty-R, inty+R] 落入裁切区的，取该行上相位列
 * 对应最近的 X0-4/X0/X0+4 三候选列（c = 该相位所在列），半径内则加权。
 */
static double interp(const uint16_t* px, int W, int H,
                     int OX, int OY, int OW, int OH,
                     int inty, int intx, int ch, int R) {
    double sw = 0.0, s = 0.0;
    int Ymin = OY < inty - R ? inty - R : OY;
    int Ymax = OY + OH - 1 < inty + R ? OY + OH - 1 : inty + R;
    int Xmin = OX < intx - R ? intx - R : OX;
    int Xmax = OX + OW - 1 < intx + R ? OX + OW - 1 : intx + R;
    int Y, ci;
    for (Y = Ymin; Y <= Ymax; Y++) {
        int r = Y & 3;
        /* 遍历该绝对行 r 上所有相位列 == ch 的列 */
        for (ci = 0; ci < 4; ci++) {
            if (PHASE[(r << 2) | ci] != ch) continue;
            /* 三候选列 X0-4 / X0 / X0+4 */
            {
                int X0 = (intx >> 2) * 4 + ci;
                int cand[3]; int k;
                cand[0] = X0 - 4; cand[1] = X0; cand[2] = X0 + 4;
                for (k = 0; k < 3; k++) {
                    int X = cand[k];
                    if (X < Xmin || X > Xmax) continue;
                    if (X < 0 || X >= W || Y < 0 || Y >= H) continue;
                    {
                        int dy = Y - inty, dx = X - intx;
                        int d2 = dy * dy + dx * dx;
                        double w = 1.0 / (d2 + 1.0);
                        sw += w;
                        s += w * px[(size_t)Y * W + X];
                    }
                }
            }
        }
    }
    return (sw > 0.0) ? (s / sw) : 0.0;
}

/* 裁切区 IR：抽 (偶行,奇列)，双线性插值回满幅 */
static void extract_ir(const uint16_t* px, int W, int H,
                       int OX, int OY, int OW, int OH,
                       uint8_t* ir) {
    int gw = (OW + 1) / 2, gh = (OH + 1) / 2;
    uint16_t* grid = (uint16_t*)calloc((size_t)gw * gh, sizeof(uint16_t));
    int y, x;
    if (!grid) return;
    for (y = OY; y < OY + OH; y++) {
        if ((y & 1) != 0) continue;
        int gy = y >> 1;
        for (x = OX; x < OX + OW; x++) {
            if ((x & 1) != 1) continue;   /* IR 在绝对奇列 */
            int gx = x >> 1;
            if (gy >= 0 && gy < gh && gx >= 0 && gx < gw)
                grid[(size_t)gy * gw + gx] = px[(size_t)y * W + x];
        }
    }
    for (y = 0; y < OH; y++) {
        int ay = OY + y;
        int gy0 = ay >> 1;
        if (gy0 < 0) gy0 = 0; else if (gy0 > gh - 1) gy0 = gh - 1;
        int gy1 = gy0 + 1; if (gy1 > gh - 1) gy1 = gh - 1;
        double fy = ((ay & 1) == 1) ? 0.5 : 0.0;
        for (x = 0; x < OW; x++) {
            int ax = OX + x;
            int gx0 = ax >> 1;
            if (gx0 < 0) gx0 = 0; else if (gx0 > gw - 1) gx0 = gw - 1;
            int gx1 = gx0 + 1; if (gx1 > gw - 1) gx1 = gw - 1;
            double fx = ((ax & 1) == 0) ? 0.5 : 0.0;
            double v = (grid[(size_t)gy0 * gw + gx0] * (1 - fx) * (1 - fy) +
                        grid[(size_t)gy0 * gw + gx1] * fx * (1 - fy) +
                        grid[(size_t)gy1 * gw + gx0] * (1 - fx) * fy +
                        grid[(size_t)gy1 * gw + gx1] * fx * fy);
            int iv = (int)floor(v * 255.0 / 1023.0);
            if (iv > 255) iv = 255; if (iv < 0) iv = 0;
            ir[(size_t)y * OW + x] = (uint8_t)iv;
        }
    }
    free(grid);
}

/* 主接口：对裁切区每像素做 R,G,B 插值 + WB，输出 rgb(uint8) 与 ir(uint8) */
void demosaic_and_ir(const uint16_t* px, int W, int H,
                     int OX, int OY, int OW, int OH,
                     double wb_r, double wb_b,
                     uint8_t* rgb, uint8_t* ir) {
    static const int RG = 3, RB = 8;
    int yy;
    extract_ir(px, W, H, OX, OY, OW, OH, ir);
    for (yy = 0; yy < OH; yy++) {
        int ty = OY + yy;
        int xx;
        uint8_t* row = rgb + (size_t)yy * OW * 3;
        for (xx = 0; xx < OW; xx++) {
            int tx = OX + xx;
            double gr = interp(px, W, H, OX, OY, OW, OH, ty, tx, 1, RG);
            double rr = interp(px, W, H, OX, OY, OW, OH, ty, tx, 0, RB) * wb_r;
            double bb = interp(px, W, H, OX, OY, OW, OH, ty, tx, 2, RB) * wb_b;
            int ri = (int)floor(rr * 255.0 / 1023.0);
            int gi = (int)floor(gr * 255.0 / 1023.0);
            int bi = (int)floor(bb * 255.0 / 1023.0);
            if (ri > 255) ri = 255; if (ri < 0) ri = 0;
            if (gi > 255) gi = 255; if (gi < 0) gi = 0;
            if (bi > 255) bi = 255; if (bi < 0) bi = 0;
            row[xx * 3 + 0] = (uint8_t)ri;
            row[xx * 3 + 1] = (uint8_t)gi;
            row[xx * 3 + 2] = (uint8_t)bi;
        }
    }
}

/* 最近邻采样：返回半径 R 内相位==ch 的最近像素原始值(0-1023) */
static double nearest(const uint16_t* px, int W, int H,
                      int OX, int OY, int OW, int OH,
                      int inty, int intx, int ch, int R) {
    double best = 0.0;
    int bd = 1 << 30;
    int Ymin = OY < inty - R ? inty - R : OY;
    int Ymax = OY + OH - 1 < inty + R ? OY + OH - 1 : inty + R;
    int Xmin = OX < intx - R ? intx - R : OX;
    int Xmax = OX + OW - 1 < intx + R ? OX + OW - 1 : intx + R;
    int Y, ci;
    for (Y = Ymin; Y <= Ymax; Y++) {
        int r = Y & 3;
        for (ci = 0; ci < 4; ci++) {
            if (PHASE[(r << 2) | ci] != ch) continue;
            {
                int X0 = (intx >> 2) * 4 + ci;
                int cand[3]; int k;
                cand[0] = X0 - 4; cand[1] = X0; cand[2] = X0 + 4;
                for (k = 0; k < 3; k++) {
                    int X = cand[k];
                    if (X < Xmin || X > Xmax) continue;
                    if (X < 0 || X >= W || Y < 0 || Y >= H) continue;
                    {
                        int dy = Y - inty, dx = X - intx;
                        int d2 = dy * dy + dx * dx;
                        if (d2 < bd) { bd = d2; best = px[(size_t)Y * W + X]; }
                    }
                }
            }
        }
    }
    return best;
}

/* ---- 预计算相位 -> 最近 G/R/B 采样相对偏移表（NN 快速模式提速用）---- */
static int gDY[4][4], gDX[4][4], rDY[4][4], rDX[4][4], bDY[4][4], bDX[4][4];
static int built = 0;

static int chan_at_rel(int py, int px) {
    return PHASE[((py & 3) << 2) | (px & 3)];
}

static void build_tables(void) {
    int py, px;
    if (built) return;
    for (py = 0; py < 4; py++) for (px = 0; px < 4; px++) {
        static const int cds[3] = {0, 1, 2};   /* R,G,B */
        int ci;
        for (ci = 0; ci < 3; ci++) {
            int c = cds[ci];
            int bestd = 1 << 30, bdy = 0, bdx = 0;
            int dy, dx;
            for (dy = -6; dy <= 6; dy++) for (dx = -6; dx <= 6; dx++) {
                if (chan_at_rel(py + dy, px + dx) != c) continue;
                { int d = dy * dy + dx * dx; if (d < bestd) { bestd = d; bdy = dy; bdx = dx; } }
            }
            if (c == 0) { rDY[py][px] = bdy; rDX[py][px] = bdx; }
            else if (c == 1) { gDY[py][px] = bdy; gDX[py][px] = bdx; }
            else { bDY[py][px] = bdy; bDX[py][px] = bdx; }
        }
    }
    built = 1;
}

/* 快速模式：最近邻 demosaic（表驱动，无逐像素扫描）。用于实时预览/服务 */
void demosaic_nn(const uint16_t* px, int W, int H,
                 int OX, int OY, int OW, int OH,
                 double wb_r, double wb_b,
                 uint8_t* rgb) {
    int yy;
    build_tables();
    for (yy = 0; yy < OH; yy++) {
        int ty = OY + yy;
        int xx;
        uint8_t* row = rgb + (size_t)yy * OW * 3;
        for (xx = 0; xx < OW; xx++) {
            int tx = OX + xx;
            int py = ty & 3, ppx = tx & 3;
            int sy, sx, gy, gx, ry, rx, by, bx;
            sy = ty + gDY[py][ppx]; sx = tx + gDX[py][ppx];
            if (sy < 0) sy = 0; else if (sy >= H) sy = H - 1;
            if (sx < 0) sx = 0; else if (sx >= W) sx = W - 1;
            gy = sy; gx = sx;
            sy = ty + rDY[py][ppx]; sx = tx + rDX[py][ppx];
            if (sy < 0) sy = 0; else if (sy >= H) sy = H - 1;
            if (sx < 0) sx = 0; else if (sx >= W) sx = W - 1;
            ry = sy; rx = sx;
            sy = ty + bDY[py][ppx]; sx = tx + bDX[py][ppx];
            if (sy < 0) sy = 0; else if (sy >= H) sy = H - 1;
            if (sx < 0) sx = 0; else if (sx >= W) sx = W - 1;
            by = sy; bx = sx;
            {
                double gr = px[(size_t)gy * W + gx];
                double rr = (double)px[(size_t)ry * W + rx] * wb_r;
                double bb = (double)px[(size_t)by * W + bx] * wb_b;
                int ri = (int)floor(rr * 255.0 / 1023.0);
                int gi = (int)floor(gr * 255.0 / 1023.0);
                int bi = (int)floor(bb * 255.0 / 1023.0);
                if (ri > 255) ri = 255; if (ri < 0) ri = 0;
                if (gi > 255) gi = 255; if (gi < 0) gi = 0;
                if (bi > 255) bi = 255; if (bi < 0) bi = 0;
                row[xx * 3 + 0] = (uint8_t)ri;
                row[xx * 3 + 1] = (uint8_t)gi;
                row[xx * 3 + 2] = (uint8_t)bi;
            }
        }
    }
}

/*
 * 快速 IR 抽取（表驱动最近邻）。IR 位于绝对 (偶行, 奇列)，呈 2x2 稀疏网格。
 * 对裁切区每个输出像素，取最近的 IR 采样点值，缩放到 0-255。
 * 只处理 1 通道，比 RGB 的 3 通道 demosaic 更快，用于实时 IR 流。
 */
void ir_nn(const uint16_t* px, int W, int H,
           int OX, int OY, int OW, int OH,
           uint8_t* ir) {
    int yy;
    for (yy = 0; yy < OH; yy++) {
        int ty = OY + yy;
        int xx;
        uint8_t* row = ir + (size_t)yy * OW;
        /* 最近偶行（IR 采样行） */
        int iy = (ty & 1) ? (ty + 1) : ty;      /* ty 奇 -> 最近偶行取 ty+1 */
        if (iy < 0) iy = 0; else if (iy >= H) iy = H - 1;
        for (xx = 0; xx < OW; xx++) {
            int tx = OX + xx;
            /* 最近奇列（IR 采样列） */
            int ix = (tx & 1) ? tx : (tx + 1);  /* tx 偶 -> 最近奇列取 tx+1 */
            if (ix < 0) ix = 0; else if (ix >= W) ix = W - 1;
            {
                int v = px[(size_t)iy * W + ix];
                int iv = (int)floor(v * 255.0 / 1023.0);
                if (iv > 255) iv = 255; if (iv < 0) iv = 0;
                row[xx] = (uint8_t)iv;
            }
        }
    }
}
