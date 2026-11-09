#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第 1 步：读取「加班日期清单支付表」Excel，按支付来源分组，映射为三个账单模板的状态字段。

用法：
    python3 prep.py --xlsx <表格路径> --workdir <工作目录>
输出：
    <workdir>/manifest.json  每条记录一份：来源/模板/文件名/template 状态字段
"""
import argparse
import json
import os
import re
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP

import openpyxl

# 标准字段 -> 可能的表头（复合表头按 "/" 分段后精确匹配，避免包含匹配误配）
HEADER_ALIASES = {
    "source": ["支付来源", "支付渠道", "来源"],
    "date": ["支付日期", "日期"],
    "pay_time": ["支付时间", "交易时间", "订单时间"],
    "project": ["项目", "项目名称", "任务"],
    "merchant": ["交易对方", "对方账号", "订单标题", "商户名称", "收款方"],
    "product": ["商品", "商品说明", "交易内容", "商品名称"],
    "amount": ["金额", "交易金额", "实付金额"],
    "method": ["支付方式", "交易方式", "付款方式"],
    "transaction": ["交易单号", "交易订单号", "订单号", "交易流水号"],
    "merchant_id": ["商户单号", "商家订单号", "商家单号"],
}

SUPPORTED = ("微信支付", "支付宝", "美团")


def norm(v, keep_slash=False):
    if v is None:
        return ""
    t = str(v).replace("\u3000", " ").strip()
    if not keep_slash and t == "/":
        return ""
    return t


def money(v):
    """金额 -> 负数、两位小数（-12.30）"""
    try:
        d = Decimal(str(v).strip().replace(",", "").replace("￥", "").replace("¥", ""))
    except Exception:
        return "-0.00"
    if d < 0:
        d = -d
    return "-" + str(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def wx_time(v):
    """2026-02-01 13:12:48 -> 2026年2月1日 13:12:48（微信详情页写法，月日不补零）"""
    t = norm(v)
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})\s*(\d{2}:\d{2}:\d{2})?", t)
    if not m:
        return t
    return "%s年%d月%d日 %s" % (m.group(1), int(m.group(2)), int(m.group(3)), m.group(4) or "")


def clean_meituan_merchant(v):
    """去掉「订单详情」、去掉结尾的「-数字」长串"""
    t = re.sub(r"\s*订单详情\s*", "", norm(v))
    t = re.sub(r"\s*[-－—]\s*\d{6,}\s*$", "", t)
    t = re.sub(r"\s*[-－—]\s*\d+\s*$", "", t)
    return t.strip()


def pick_logo(merchant, product):
    """01 美团-大众点评 / 02 店铺-超市-餐饮 / 03 个人转账-群收款 / 04 其他支付"""
    blob = merchant + " " + product
    if "美团" in blob or "大众点评" in blob:
        return "01"
    if "收款方备注" in product or "转账" in product or "群收款" in product:
        return "03"
    if any(k in blob for k in ["缴费", "话费", "充值", "停车", "水电", "燃气",
                               "物业", "快递", "打车", "加油", "保险"]):
        return "04"
    return "02"


def map_header(row):
    """把表头行映射为标准字段 -> 列号（每个标准字段取首个精确命中列）"""
    out = {}
    for idx, raw in enumerate(row):
        if raw is None:
            continue
        hh = str(raw).strip()
        parts = [p.strip() for p in hh.split("/")]
        for key, aliases in HEADER_ALIASES.items():
            if key in out:
                continue
            if any(hh == a or a in parts for a in aliases):
                out[key] = idx
    missing = [k for k in HEADER_ALIASES if k not in out]
    return out, missing


def build_record(row, col):
    g = lambda k: row[col[k]] if col.get(k) is not None and col[k] < len(row) else None
    return {
        "source": norm(g("source")),
        "date": norm(g("date"))[:10],
        "project": norm(g("project")),
        "merchant": norm(g("merchant")),
        "product": norm(g("product"), keep_slash=True),
        "amount": money(g("amount")),
        "method": norm(g("method")),
        "transaction": norm(g("transaction")),
        "merchant_id": norm(g("merchant_id")),
        "pay_time": norm(g("pay_time")) or norm(g("date")),
    }


def safe_name(s):
    for a, b in [("/", "、"), ("\\", "、"), (":", "："), ("*", ""), ("?", "？"),
                 ('"', "”"), ("<", "＜"), (">", "＞"), ("|", "｜")]:
        s = s.replace(a, b)
    return s


def build_manifest(xlsx):
    wb = openpyxl.load_workbook(xlsx, data_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    header = rows[0]
    col, missing = map_header(header)
    if "source" not in col:
        raise SystemExit("未找到「支付来源」列，请检查表格表头：%s" % header)
    records = []
    for row in rows[1:]:
        if row is None or all(v is None or str(v).strip() == "" for v in row):
            continue
        r = build_record(row, col)
        if r["source"]:
            records.append(r)
    records.sort(key=lambda x: (x["pay_time"], x["source"]))

    used = {}

    def filename(x):
        mmdd = x["date"][5:7] + "-" + x["date"][8:10]
        base = "%s %s" % (mmdd, safe_name(x["project"]))
        used[base] = used.get(base, 0) + 1
        return base if used[base] == 1 else "%s-%d" % (base, used[base])

    manifest, skipped = [], []
    for x in records:
        if x["source"] == "微信支付":
            tpl, group = "wechat01.html", "wechat"
            state = {
                "logo": pick_logo(x["merchant"], x["product"]),
                "merchantName": x["merchant"],
                "amount": x["amount"],
                "status": "支付成功",
                "time": wx_time(x["pay_time"]),
                "product": x["product"],
                "org": "微信支付",
                "method": x["method"],
                "transaction": x["transaction"],
                "merchantId": x["merchant_id"],
                "miniapp": "在线点单",
            }
        elif x["source"] == "支付宝":
            tpl, group = "alipay02.html", "alipay"
            state = {
                "merchant": x["merchant"],
                "amount": x["amount"],
                "time": x["pay_time"],
                "payment": x["method"],
                "description": x["product"],
                "category": "其他",
                "tag": "请选择",
            }
        elif x["source"] == "美团":
            tpl, group = "meituan03.html", "meituan"
            state = {
                "merchant": clean_meituan_merchant(x["merchant"]),
                "amount": x["amount"],
                "payment": x["method"],
                "time": x["pay_time"],
                "transaction": x["transaction"],
                "merchantOrder": x["merchant_id"],
            }
        else:
            skipped.append(x)
            continue
        x.update({"template": tpl, "group": group, "state": state,
                  "filename": filename(x) + ".png"})
        manifest.append(x)
    return manifest, skipped, col, missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", required=True)
    ap.add_argument("--workdir", required=True)
    args = ap.parse_args()
    os.makedirs(args.workdir, exist_ok=True)
    manifest, skipped, col, missing = build_manifest(args.xlsx)
    out = os.path.join(args.workdir, "manifest.json")
    json.dump(manifest, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({
        "manifest": out,
        "total": len(manifest),
        "by_source": Counter(m["source"] for m in manifest),
        "skipped": [{"source": s["source"], "date": s["date"], "project": s["project"]} for s in skipped],
        "missing_columns": missing,
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
