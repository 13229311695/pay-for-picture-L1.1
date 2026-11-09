#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第 2 步：把 manifest.json 逐条注入三个账单 HTML 模板，导出 PNG，并打包成单个文件夹的 zip。

用法：
    python3 render.py --workdir <工作目录> --templates <模板目录> --out <输出目录> --zip <zip 路径>
逐条串行执行（一条记录渲染完成后再处理下一条）。
"""
import argparse
import glob
import json
import os
import shutil
import zipfile

from playwright.sync_api import sync_playwright

# 模板 -> (截图元素, 画布宽, 画布高, 浏览器视口, 设备像素比)
SETUP = {
    "wechat": ("#screen", 955, 2048, 1500, 2600, 2),
    "alipay": ("#phone", 958, 2048, 1500, 2600, 2),
    "meituan": ("#bill", 1284, 2778, 1400, 2950, 1),
}


def find_chrome():
    """优先用 playwright 自带浏览器，找不到则退回系统 chromium（避免版本目录不匹配报错）"""
    cands = sorted(glob.glob("/opt/vm/preinstall/ms-playwright/chromium-*/chrome-linux/chrome"),
                   reverse=True)
    cands += ["/usr/local/bin/chromium", "/usr/bin/chromium", "/usr/bin/chromium-browser",
              "/usr/bin/google-chrome"]
    for c in cands:
        if os.path.exists(c):
            return c
    return None  # 交给 playwright 默认解析


def apply_wechat(page, st):
    page.evaluate(
        """(p) => {
             Object.assign(state, p); render();
             const shell = document.getElementById('screenShell');
             shell.style.width = '955px'; shell.style.height = '2048px';
             shell.style.aspectRatio = 'auto'; shell.style.borderRadius = '0';
             shell.style.boxShadow = 'none';
             document.getElementById('screen').style.transform = 'none';
           }""", st)


def apply_meituan(page, st):
    page.evaluate(
        """(p) => {
             Object.assign(state, p); render();
             const f = document.querySelector('.frame');
             f.style.width = '1284px'; f.style.maxWidth = 'none'; f.style.boxShadow = 'none';
             const svg = document.getElementById('bill');
             svg.style.width = '1284px'; svg.style.height = '2778px';
           }""", st)


def apply_alipay(page):
    page.evaluate(
        """() => {
             const vp = document.getElementById('viewport');
             vp.style.width = '958px'; vp.style.height = '2048px';
             vp.style.boxShadow = 'none';
             document.getElementById('phone').style.transform = 'none';

             // 商户名过长逐级缩小字号，保持单行
             const m = document.querySelector('.merchant');
             let fs = 36;
             while (m.scrollWidth > 828 && fs > 24) { fs -= 2; m.style.fontSize = fs + 'px'; }

             // 商品说明允许换行；按实际行数下移「查看购物详情/支付奖励/收单机构/更多」，
             // 卡片底部留有余量，不下移会与上一行压盖
             const d = document.querySelector('.description .value');
             d.style.whiteSpace = 'normal';
             d.style.wordBreak = 'break-all';
             d.style.lineHeight = '50px';
             const lines = Math.max(1, Math.round(d.scrollHeight / 50));
             const delta = (lines - 1) * 50;
             if (delta > 0) {
               ['.shopping', '.reward', '.acquirer', '.more'].forEach((sel) => {
                 const el = document.querySelector(sel);
                 el.style.top = (parseFloat(getComputedStyle(el).top) + delta) + 'px';
               });
             }
           }""")


APPLY = {"wechat": apply_wechat, "meituan": apply_meituan}
# 支付宝模板的 state 封在 IIFE 内（外部拿不到），只能把 payload 写进 #saved-state 后重新加载
ALI_TAG = '<script id="saved-state" type="application/json">null</script>'


def alipay_page(browser, tpl_path, st, idx, tmpdir):
    src = open(tpl_path, encoding="utf-8").read()
    if ALI_TAG not in src:
        raise SystemExit("alipay02.html 结构变化：#saved-state 占位标签未找到")
    payload = json.dumps(st, ensure_ascii=False).replace("<", "\\u003c")
    tmp = os.path.join(tmpdir, "alipay_%03d.html" % idx)
    os.makedirs(tmpdir, exist_ok=True)
    open(tmp, "w", encoding="utf-8").write(
        src.replace(ALI_TAG, '<script id="saved-state" type="application/json">%s</script>' % payload))
    ctx = browser.new_context(viewport={"width": 1500, "height": 2600}, device_scale_factor=2)
    pg = ctx.new_page()
    pg.goto("file://" + tmp)
    pg.wait_for_timeout(300)
    pg.evaluate("document.fonts.ready")
    apply_alipay(pg)
    pg.wait_for_timeout(120)
    return ctx, pg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--templates", required=True)
    ap.add_argument("--out", required=True, help="图片输出目录")
    ap.add_argument("--zip", default="", help="打包 zip 路径；留空则不打包")
    ap.add_argument("--folder", default="支付截图", help="zip 内的文件夹名")
    args = ap.parse_args()

    manifest = json.load(open(os.path.join(args.workdir, "manifest.json"), encoding="utf-8"))
    if not manifest:
        raise SystemExit("manifest.json 为空，没有可渲染的记录")
    os.makedirs(args.out, exist_ok=True)
    tmpdir = os.path.join(args.workdir, "tmp")

    chrome = find_chrome()
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chrome,
                                    args=["--no-sandbox", "--force-color-profile=srgb"])
        pages = {}
        for g in ("wechat", "meituan"):
            sel, w, h, vw, vh, dsf = SETUP[g]
            tpl = [m["template"] for m in manifest if m["group"] == g]
            if not tpl:
                continue
            ctx = browser.new_context(viewport={"width": vw, "height": vh}, device_scale_factor=dsf)
            pg = ctx.new_page()
            pg.goto("file://" + os.path.join(args.templates, tpl[0]))
            pg.wait_for_timeout(400)
            pg.evaluate("document.fonts.ready")
            pages[g] = pg

        for i, it in enumerate(manifest, 1):
            g = it["group"]
            if g == "alipay":
                ctx, pg = alipay_page(browser, os.path.join(args.templates, it["template"]),
                                     it["state"], i, tmpdir)
            else:
                pg = pages[g]
                APPLY[g](pg, it["state"])
                pg.wait_for_timeout(120)
            sel = SETUP[g][0]
            pg.locator(sel).screenshot(path=os.path.join(args.out, it["filename"]))
            if g == "alipay":
                ctx.close()
            print("[%d/%d] %s %s" % (i, len(manifest), g, it["filename"]), flush=True)

        browser.close()

    shutil.rmtree(tmpdir, ignore_errors=True)

    if args.zip:
        if os.path.exists(args.zip):
            os.remove(args.zip)
        files = sorted(f for f in os.listdir(args.out) if f.lower().endswith(".png"))
        with zipfile.ZipFile(args.zip, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for f in files:
                z.write(os.path.join(args.out, f), os.path.join(args.folder, f))
        print("ZIP: %s (%d 张, %.1f MB)" % (args.zip, len(files),
                                           os.path.getsize(args.zip) / 1024 / 1024))


if __name__ == "__main__":
    main()
