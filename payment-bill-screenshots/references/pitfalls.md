# 排错与已知坑

## 渲染结果不对

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 微信/支付宝图只有几百像素宽、右侧大片白 | 截到了内层元素但外层容器限宽（`min(100%, 390px)`/`min(100vw…)`），元素在视口外被裁 | 先固定外层壳宽高（微信 `#screenShell`、支付宝 `#viewport`、美团 `.frame`），再截元素 |
| 整图空白、高度塌成 0 | 为了「固定尺寸」改掉了预览壳的 `aspect-ratio/height`，壳内全是绝对定位 | 保留原壳比例，只隐藏编辑器、截根元素 |
| 图里带滚动条或缩放比例不对 | 用了整页 `page.screenshot()` | 必须用 `locator.screenshot()` 截手机根元素 |
| 微信图被缩小 | `fitScreen()` 按 shell 宽算出 `scale()` | 截图前置 `#screen.style.transform='none'` |

## 文字问题

- **支付宝商品说明过长**（如 `支付码:2899…(858105812015051)`）默认 `white-space:nowrap` 会冲出卡片右侧被切。脚本已改为允许换行，并把 `.shopping/.reward/.acquirer/.more` 按行数下移 50px/行；卡片底部有余量，最多 3 行仍不越界。若后续行仍压盖，检查是否被别的规则覆盖了 `line-height`（必须同步 50px，否则块高与行距不一致）。
- **微信商品**很长（美团外卖类可达 66 字）时会换行 3–4 行，`.details` 是流式布局会自动下推，无需手动移位。
- **微信商户名**超长时按模板自带的省略号截断（如「赛百味餐饮管理（深圳）有限公司广州天…」），属模板既有行为，不要为了「显示全」改字号，会破坏与其他行的字号一致性。
- **微信商户单号** 32 位会折成两行，属模板既有换行，保留。
- **首字符是「【」时首行看起来缩进约 0.6em**：Noto Sans CJK 把方头括号画在字身中间，属字体侧边距，不是排版错误；不要加 `text-indent` 补偿，否则整行会左移错位。

## 数据映射

- 复合表头必须按 `/` 分段**精确**匹配：`parts=[p.strip() for p in hh.split('/')]`，条件 `hh==alias or alias in parts`。用包含匹配会把「收付款方式」误配成「付款方式」。
- 每个标准字段只取首个命中列；命中冲突时按 `prep.py` 里的 `HEADER_ALIASES` 顺序优先。
- 金额保留负数前缀，两位小数；不要因为原始值为正数就漏掉负号。
- 美团商户名清洗只删「订单详情」与结尾 `-数字`，不要动括号、圆点等原名里的符号。

## 文件与交付

- 文件名里的 `/` 不能直接删（会丢层级含义），换「、」；同日同项目重复从第 2 条起加 `-2`。
- zip 用 UTF-8 文件名（`zipfile` 会自动置 0x800 标志位），Windows 资源管理器与 7-Zip 均可正常显示中文名。
- 临时目录（`workdir/tmp`）渲染完删掉；`manifest.json` 建议保留，便于复现与核对。

## 环境

- Playwright 报 `Executable doesn't exist at …/chromium_headless_shell-1234` 但机器上装的是别的版本目录：不要 `playwright install`，直接把 `executable_path` 指到已存在的 `chromium-*/chrome-linux/chrome`。
- 中文缺字/方框：确认有 `Noto Sans CJK SC`（`fc-list :lang=zh`）。
