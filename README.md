# payment-bill-screenshots

把「加班日期清单支付表」类 Excel 逐行导出为微信 / 支付宝 / 美团账单详情截图，并按单文件夹打包 zip。

- 只处理 `支付来源 = 微信支付 / 支付宝 / 美团`，其他来源自动跳过
- 一条记录渲染完成后再处理下一条
- 输出：`MM-DD 项目名.png`，同日同项目重复自动 `-2`、`-3`

## 安装到任意支持 Skills 的平台

```bash
git clone --depth 1 <本仓库地址> /tmp/skill-src
cp -R /tmp/skill-src/payment-bill-screenshots ~/.claude/skills/   # 换成目标平台的 skills 根目录
```

Windows PowerShell：

```powershell
git clone --depth 1 <本仓库地址> $env:TEMP\skill-src
Copy-Item -Recurse $env:TEMP\skill-src\payment-bill-screenshots "$env:USERPROFILE\.claude\skills\"
```

或直接在仓库页面 **Code → Download ZIP**，解压后把 `payment-bill-screenshots` 整个文件夹放进 skills 根目录。**目录名必须保持 `payment-bill-screenshots`**，且与 SKILL.md 里的 `name` 一致。

## 依赖

```bash
pip install openpyxl playwright
playwright install chromium
```

渲染依赖 Chromium 与中文字体（macOS 用苹方最佳，Windows 会回落到系统默认中文字体）。美团模板字体已内嵌，不受影响。

## 用法

```bash
cd payment-bill-screenshots
python3 scripts/prep.py   --xlsx "加班日期清单支付表.xlsx" --workdir ./work
python3 scripts/render.py --workdir ./work --templates assets/templates \
        --out ./images --zip ./支付截图.zip
```

细节与字段映射见 `payment-bill-screenshots/SKILL.md`，排错见 `payment-bill-screenshots/references/pitfalls.md`。
