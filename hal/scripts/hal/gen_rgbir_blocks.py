#!/usr/bin/env python3
"""
为 OV5675 RGB-IR sensor 的其他分辨率生成 RGB-IR (id=100204) settings 块。
方法（基于文本替换，稳健）：
1. 取普通 bayer 块的完整文本（其尺寸参数已按目标分辨率正确）。
2. 改 header id 100000 -> 100204。
3. 把 <isa_lb_video> 块替换为 <isa_lb_ir_video>（加 RGB-IR 特有元素）。
4. <post_gdc_video> 换成 <post_gdc_video_bayer>。
"""
import re, sys, os

path = "/etc/camera/ipu6/gcss/graph_settings_ov5675.xml"
data = open(path).read()

def get_block(xml, key, pid):
    m = re.search(r"<settings key=\"%s\" id=\"%s\".*?</settings>" % (key, pid), xml, re.S)
    return m.group(0) if m else None

ir3 = get_block(data, "8003", "100204")
assert ir3, "8003/100204 missing"

# 在 8003 的 isa_lb_ir_video 内精确提取 RGB-IR 特有元素
ir3_isa = re.search(r"<isa_lb_ir_video>.*?</isa_lb_ir_video>", ir3, re.S).group(0)

def grab_ir(tag):
    # 匹配到配对的 </tag>（这些元素都非自闭合，内部可能含 />，所以不用非贪婪到 />）
    m = re.search(r"(?m)^\s*<%s\b.*?</%s>" % (tag, tag), ir3_isa, re.S)
    assert m, "missing %s" % tag
    return m.group(0)

def grab_ir_selfclose(tag):
    m = re.search(r"<%s\b[^>]*/>" % tag, ir3_isa)
    assert m, "missing %s" % tag
    return m.group(0)

rgb_ir_2_0 = grab_ir("rgb_ir_2_0")
pix_crop_ir_md = grab_ir("pix_crop_ir_md")
padder_bayer_a = grab_ir("padder_bayer_a")
pxl_crop_bayer_a = grab_ir("pxl_crop_bayer_a")
ir_md = grab_ir_selfclose("ir_md")

def build_ir_block_from_bayer(bayer_blk, key):
    # 目标分辨率从 video0 推出
    m = re.search(r"<video0\s+width=\"(\d+)\"\s+height=\"(\d+)\"", bayer_blk)
    w, h = int(m.group(1)), int(m.group(2))

    isa_bayer = re.search(r"<isa_lb_video>.*?</isa_lb_video>", bayer_blk, re.S).group(0)

    ir_isa = isa_bayer.replace("<isa_lb_video>", "<isa_lb_ir_video>")
    ir_isa = ir_isa.replace("</isa_lb_video>", "</isa_lb_ir_video>")
    # 1) main 后插 ir_md
    main_el = re.search(r"<main[^>]*/>", ir_isa).group(0)
    ir_isa = ir_isa.replace(main_el, main_el + "\n    " + ir_md, 1)
    # 2) 在 </sis_1_0_a> 之后（padder_yuv_a 之前）插 pix_crop_ir_md / padder_bayer_a / pxl_crop_bayer_a
    ir_isa = ir_isa.replace("    </sis_1_0_a>",
                            "    </sis_1_0_a>\n    " + pix_crop_ir_md + "\n    " +
                            padder_bayer_a + "\n    " + pxl_crop_bayer_a, 1)
    # 3) 在 </padder_yuv_a> 之后（strm_crop_sis_b 之前）插 rgb_ir_2_0
    ir_isa = ir_isa.replace("    </padder_yuv_a>",
                            "    </padder_yuv_a>\n    " + rgb_ir_2_0, 1)

    pg_bayer = re.search(r"<post_gdc_video>.*?</post_gdc_video>", bayer_blk, re.S).group(0)
    pg_ir = pg_bayer.replace("<post_gdc_video>", "<post_gdc_video_bayer>")
    pg_ir = pg_ir.replace("</post_gdc_video>", "</post_gdc_video_bayer>")

    header = re.search(r"<settings[^>]*>", bayer_blk).group(0)
    header = header.replace('id="100000"', 'id="100204"')
    # prefix: 去掉原 header，只保留 header 之后到 <isa_lb_video> 之前
    prefix = bayer_blk.split(">", 1)[1].split("<isa_lb_video>")[0]
    suffix = bayer_blk.split("</post_gdc_video>")[1]

    return header + "\n" + prefix + "\n" + ir_isa + "\n" + pg_ir + "\n" + suffix

if __name__ == "__main__":
    resmap = {"8000":(320,240),"8001":(640,360),"8002":(640,480),
              "8004":(1280,960),"8005":(1600,1200),
              "8006":(1920,1080),"8007":(2560,1920)}
    key = os.environ.get("TARGET_KEY", "8002")
    if key not in resmap:
        print("unknown key"); sys.exit(1)
    bayer = get_block(data, key, "100000")
    blk = build_ir_block_from_bayer(bayer, key)
    out = "/tmp/rgbir_%s.xml" % key
    open(out, "w").write(blk)
    print("wrote %s" % out)
    print(blk)
