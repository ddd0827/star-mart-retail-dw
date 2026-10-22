# Power BI 数据集与建模说明

本目录为项目提供 **Power BI 可直接导入的星型模型数据集**，包括维度表、事实表、主题、DAX 度量与建模步骤。Power BI Desktop 按本文导入后即可制作交互式报表。

> 数据为固定种子生成的模拟数据，不含真实个人信息。

## 1. 交付内容

| 路径 | 说明 |
|---|---|
| `output/powerbi/data/` | 7 张维度表 + 10 张事实表（CSV，UTF-8 BOM） |
| `output/powerbi/theme/star_mart_theme.json` | Power BI 主题（与 HTML 看板同一套配色） |
| `output/powerbi/measures.dax` | 经营、门店、会员、漏斗、库存、促销度量 |
| `output/powerbi/_manifest.json` | 行数、关系、文件清单 |
| `docs/powerbi.md` | 本文 |

首次生成或刷新：

```powershell
.venv\Scripts\python.exe -m src.report.powerbi
```

流水线全量/日增量运行时会自动执行 `POWERBI` 阶段；也可单独运行上述命令。

## 2. 数据模型

### 2.1 表清单

| 表 | 类型 | 粒度 | 行数（当前全量） |
|---|---|---|---:|
| `dim_date` | 维度 | 日 | 180 |
| `dim_month` | 维度 | 月（含留存未观测月份） | 12 |
| `dim_store` | 维度 | 门店/线上仓 | 25 |
| `dim_category` | 维度 | 品类（一、二级 + 未知） | 53 |
| `dim_product` | 维度 | SKU | 1,500 |
| `dim_channel` | 维度 | 渠道 | 4 |
| `dim_member` | 维度 | 会员 | 100,000 |
| `fact_operation_day` | 事实 | 公司 × 日 | 180 |
| `fact_store_day` | 事实 | 门店 × 日 | 4,320 |
| `fact_category_day` | 事实 | 品类 × 日 | 8,459 |
| `fact_product_snapshot` | 事实 | SKU × 快照日 | 1,500 |
| `fact_member_rfm` | 事实 | 会员 × 快照日 | 72,737 |
| `fact_retention` | 事实 | 首购月 × 月偏移 | 42 |
| `fact_repurchase` | 事实 | 统计月 | 7 |
| `fact_inventory_day` | 事实 | 库位 × 日 | 4,500 |
| `fact_funnel_day` | 事实 | 渠道 × 日 | 540 |
| `fact_promotion` | 事实 | 活动 × 渠道 | 88 |

### 2.2 关系

在 Power BI「模型」视图中按以下多对一关系连接（`_manifest.json` 中有同源清单）：

| 事实表 | 外键 | 维度表 | 维度键 |
|---|---|---|---|
| `fact_operation_day` | `dt` | `dim_date` | `date` |
| `fact_store_day` | `dt` | `dim_date` | `date` |
| `fact_store_day` | `store_id` | `dim_store` | `store_id` |
| `fact_category_day` | `dt` | `dim_date` | `date` |
| `fact_category_day` | `category_id` | `dim_category` | `category_id` |
| `fact_product_snapshot` | `dt` | `dim_date` | `date` |
| `fact_product_snapshot` | `product_id` | `dim_product` | `product_id` |
| `fact_member_rfm` | `dt` | `dim_date` | `date` |
| `fact_member_rfm` | `member_id` | `dim_member` | `member_id` |
| `fact_inventory_day` | `dt` | `dim_date` | `date` |
| `fact_inventory_day` | `location_id` | `dim_store` | `store_id` |
| `fact_funnel_day` | `dt` | `dim_date` | `date` |
| `fact_funnel_day` | `channel_id` | `dim_channel` | `channel_id` |
| `fact_promotion` | `channel_id` | `dim_channel` | `channel_id` |
| `fact_repurchase` | `stat_month` | `dim_month` | `month_key` |
| `fact_retention` | `stat_month` | `dim_month` | `month_key` |
| `dim_product` | `category_id` | `dim_category` | `category_id` |

`fact_retention` 同时有 `cohort_month` 与 `stat_month` 两个月份角色；如需按首购月分析，可在模型中使用 `USERELATIONSHIP` 或在 Power Query 中复制一份 `dim_month`。

## 3. 导入步骤

1. **打开 Power BI Desktop**，新建空白报表。
2. **导入 CSV**：`主页 → 获取数据 → 文本/CSV`，依次选择 `output/powerbi/data/` 下的 17 个文件；编码选择 **65001: Unicode (UTF-8)**。
3. **设置类型**（Power Query 或模型视图）：
   - `dim_date[date]`、所有事实表的 `dt`、`fact_promotion[start_date/end_date]`、`fact_retention[stat_month_end]`、`dim_member[register_date]` → **日期**；
   - 各类 `*_id`、`month_key`、`stat_month`、`cohort_month` → **文本**；
   - 金额、比率 → **小数**；订单数、人数、件数 → **整数**；
   - `is_weekend`、`is_holiday`、`is_offline`、`is_observed`、`is_complete` → **整数**（0/1）。
4. **关闭并应用**。
5. **建立关系**：按 2.2 节逐条创建，基数均为「多对一」，交叉筛选方向为「单一」。
6. **标记日期表**：选中 `dim_date` → 表工具 → 标记为日期表 → 日期列选择 `date`。
7. **导入主题**：`视图 → 主题 → 浏览主题`，选择 `output/powerbi/theme/star_mart_theme.json`。
8. **创建度量值**：`建模 → 新建度量值`，从 `output/powerbi/measures.dax` 逐条粘贴；也可用 Tabular Editor / DAX Studio 批量脚本化。
9. **隐藏技术列**：将 `sk_*`、`etl_time` 等列设为隐藏，保持报表字段列表整洁。
10. **保存**为 `output/powerbi/star-mart-retail.pbix`。

## 4. DAX 度量

`measures.dax` 已按主题分组，覆盖：

- 经营：`GMV`、`净销售额`、`退款率`、`订单数`、`客单价`、`毛利率`、`会员GMV占比`、`线上GMV占比`、`GMV日环比`、`MTD_GMV`
- 门店：`门店GMV`、`门店转化率`、`MTD目标达成率`
- 会员：`RFM会员数`、`高价值会员占比`、`次月留存率`、`复购率`、`复购率_30日`
- 漏斗：`访问会话`、`支付会话`、`访问支付转化率`
- 库存：`平均库存金额`、`COGS_30日`、`库存周转天数`、`缺货率`
- 促销：`活动增量GMV`、`促销让利`、`促销ROI`

口径与 [docs/metrics.md](metrics.md) 保持一致。

## 5. 建议报表页

| 页面 | 建议视觉对象 |
|---|---|
| 经营总览 | KPI 卡片（GMV、净销售额、客单价、退款率、会员占比）、GMV 趋势折线、日环比卡片、渠道占比环形图 |
| 门店达成 | 门店 GMV 条形图、客流 × 转化率散点、MTD 达成率矩阵、门店排名表 |
| 品类商品 | 一级品类销售额树图、二级品类条形图、商品 TopN 表、毛利率与退款率对比 |
| 会员运营 | RFM 分层柱状图、高价值会员占比、次月留存折线、复购率卡片 |
| 线上漏斗 | 访问→浏览→搜索→加购→结算→支付漏斗图、渠道转化率对比 |
| 库存促销 | 库位库存周转条形图、缺货率卡片、促销 ROI 散点/表 |

页面顶部放一个 `dim_date[date]` 日期切片器，所有关联事实表会同步筛选。

## 6. 刷新

重新生成数据并导出 Power BI 数据集：

```powershell
.venv\Scripts\python.exe -m src.etl.pipeline --mode full
.venv\Scripts\python.exe -m src.report.powerbi
```

然后在 Power BI Desktop 中 `主页 → 刷新`。若项目目录移动，需在 Power Query 数据源设置中更新 CSV 的绝对路径。

## 7. 口径与使用注意

- `fact_operation_day` 是公司级日汇总，`fact_store_day` 是门店级日汇总，**不要在同一视觉对象中同时求和**，否则 GMV 翻倍。
- `mtd_gmv`、`mtd_target`、`avg_stock_value_30d`、`cogs_30d`、`stockout_rate_30d` 等是快照/滚动指标；跨日期切片时使用 `measures.dax` 中带 `LASTDATE` 的度量，不要直接对列求和。
- 退款按退款日计入 `fact_operation_day[refund_amount]`，GMV 按支付日计入，两者日期口径不同。
- `fact_member_rfm` 为期末快照，`recency_days`、`monetary` 不随日期切片变化。
- `fact_promotion` 的 `incremental_gmv`、`promotion_roi` 为前后对比的观察性指标，不是因果推断。
- `fact_category_day` 中无法归属品类的退款行已归入 `__UNKNOWN__`（未知品类），退款金额保留，不会因空键丢失。
- `dim_month` 覆盖到 2027-03，以承接留存分析中尚未观测的 `stat_month`；这些月份 `is_observed = 0`。
- 本项目构建环境未安装 Power BI Desktop，因此仓库不包含 `.pbix` 文件；按本文步骤在装有 Power BI Desktop 的机器上导入即可。CSV、主题、DAX 与关系定义均已生成并校验。
