# 数据模型与表设计

## 1. 建模方式

采用星型模型 + 分层数仓：

- **维度**：门店、商品、品类、品牌、会员、供应商、活动、渠道、日期。
- **事实**：订单、订单行、支付、退款、库存快照、客流、线上会话、行为事件、采购。
- **粒度**：每个事实表在表名和文档中固定粒度；DWS/ADS 在 DWD 之上聚合，避免重复计数。
- **代理键**：`sk_xxx = xxhash64(自然键)`，跨表关联使用代理键；未知维度统一为 `-1`。
- **分区**：事实表按业务日期 `dt` 分区；维表与快照表全量覆盖。
- **SCD**：维表当前为 Type 1（保留最新一条）；生产可扩展为 SCD2，保留历史价格/等级变更。

## 2. 总线矩阵

| 业务过程 | 日期 | 门店 | 商品 | 会员 | 活动 | 渠道 | 供应商 | 事实表 |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|---|
| 线下/线上销售 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  | 订单、订单行 |
| 支付 | ✓ | ✓ |  | ✓ | ✓ | ✓ |  | 支付 |
| 退款/退货 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |  | 退款 |
| 库存变动 | ✓ | ✓ | ✓ |  |  |  | ✓ | 库存快照、采购 |
| 门店客流 | ✓ | ✓ |  |  |  |  |  | 客流 |
| 线上行为 | ✓ |  | ✓ | ✓ | ✓ | ✓ |  | 会话、行为事件 |

## 3. 维度表（DIM）

| 表 | 粒度 | 关键字段 |
|---|---|---|
| `dim_date` | 日 | `date_key`、`date`、年/季/月/周、星期、周末、节假日 |
| `dim_store` | 库位（含线上仓） | `sk_store`、`store_id`、店型、城市、大区、是否线下、面积、开业日 |
| `dim_product` | SKU | `sk_product`、`product_id`、品类、品牌、供应商、售价、成本、规格、保质期 |
| `dim_category` | 两级品类 | `sk_category`、`category_id`、父级、层级、品类路径、一级品类 |
| `dim_brand` | 品牌 | `sk_brand`、`brand_id`、品牌名、国家 |
| `dim_member` | 会员 | `sk_member`、`member_id`、等级、注册日期、渠道、城市、脱敏手机号 |
| `dim_supplier` | 供应商 | `sk_supplier`、`supplier_id`、主营品类、提前期 |
| `dim_promotion` | 活动 | `sk_promotion`、`promotion_id`、活动类型、起止日、折扣率、门槛 |
| `dim_channel` | 渠道 | `sk_channel`、渠道 ID、线下/线上 |
| `dim_store_target` | 门店 × 月 | `sk_target`、门店、目标月份、目标金额 |

## 4. DWD 事实表

### 4.1 `dwd_order_info`（订单头）

- 粒度：一行一个订单。
- 关键字段：`order_id`、`order_time`、`dt`、`store_id/sk_store`、`channel_id/sk_channel`、`member_id/sk_member`、`is_member`、`promotion_id/sk_promotion`、`order_status`、`total_amount`、`discount_amount`、`shipping_fee`、`payable_amount`、`paid_amount`、`is_paid`、`online_session_id`。
- 清洗：订单号去重；时间格式兼容 `yyyy-MM-dd HH:mm:ss` 与 `yyyy/MM/dd HH:mm:ss`；空门店映射 `__UNKNOWN__`；未知会员 `sk_member=-1, is_member=0`；`is_paid` 取决于是否存在成功支付。

### 4.2 `dwd_order_detail`（订单行）

- 粒度：一行一个订单行。
- 关键字段：`order_id`、`line_id`、`sk_product`、`quantity`、`list_price`、`sale_price`、`line_amount`、`discount_amount`、`cost_amount`、订单维度属性。
- 金额：`line_amount = ROUND(quantity × sale_price, 2)`；`cost_amount = quantity × cost_price`。
- 过滤：数量 ≤ 0、价格为负、无商品 ID 的行被清洗；被清洗行数体现在质量报告与生成清单。

### 4.3 `dwd_payment`（支付）

- 粒度：一行一次支付尝试。
- 关键字段：`payment_id`、`order_id`、`dt`、`pay_time`、`pay_channel`、`pay_amount`、`payment_status`、`is_success`。
- 失败支付保留，用于解释取消订单；销售分析只使用 `is_paid=1` 的订单。

### 4.4 `dwd_refund`（退款）

- 粒度：一行一条订单行退款。
- 关键字段：`refund_id`、`order_id`、`line_id`、`dt`、`refund_time`、`refund_amount`、`refund_reason`、`refund_type`、`refund_status`、`return_qty`、`product_id/sk_product`、门店/会员/渠道属性。
- 约束：退款金额不超过对应订单行实付金额；完成退款的退货数量用于库存回补。

### 4.5 `dwd_inventory_snapshot`（库存日快照）

- 粒度：dt × 库位 × SKU。
- 关键字段：`begin_qty`、`purchase_in_qty`、`sale_qty`、`return_qty`、`adjustment_qty`、`end_qty`、`safety_stock`、`cost_price`、`stock_value`、`stock_status`。
- 守恒：`begin + purchase_in − sale + return + adjustment = end`，且 `end ≥ 0`。

### 4.6 其他事实表

| 表 | 粒度 | 说明 |
|---|---|---|
| `dwd_store_traffic` | dt × 门店 | 门店日客流 |
| `dwd_online_session` | 会话 | 线上访问、浏览、加购、结算、支付阶段标记 |
| `dwd_behavior_event` | 事件 | 页面浏览、搜索、曝光、点击、加购、结算、支付 |
| `dwd_purchase_order` | 采购单行 | 补货触发、供应商、预计/实际到货 |

## 5. DWS 汇总表

| 表 | 粒度 | 主要字段 |
|---|---|---|
| `dws_trade_store_day` | dt × 门店 | 订单数、会员订单数、买家数、GMV、会员 GMV、折扣、运费、件数、SKU 数、商品销售额、COGS、退款额、净销售额、客单价、会员占比、退款率、毛利率、客流、转化率 |
| `dws_trade_channel_day` | dt × 渠道 | 同上门店指标（按渠道） |
| `dws_trade_sku_day` | dt × SKU × 渠道 | 销量、销售额、订单数、行数、折扣、COGS、毛利、退款量/额、净销售额、退款率、毛利率 |
| `dws_member_day` | dt × 会员 | 订单数、GMV、折扣、件数、SKU/品类数、退款、净消费、客单价、最近下单时间、会员属性 |
| `dws_online_funnel_day` | dt × 渠道 × 设备 | 访问/浏览/搜索/加购/结算/支付会话数、会员会话、线上订单、线上买家、线上 GMV、各阶段转化率 |
| `dws_inventory_sku_day` | dt × 库位 × SKU | 库存数量流水、库存金额、缺货、售罄、可售量、售罄率、库存天数 |
| `dws_trade_campaign_day` | dt × 活动 × 渠道 | 活动订单、会员订单、买家数、GMV、折扣、运费、件数、商品销售额、COGS、退款、净销售额、客单价、会员占比、退款率 |

## 6. ADS 应用表

| 表 | 粒度 | 说明 |
|---|---|---|
| `ads_operation_overview` | 日 | 全公司经营总览与环比/7日均/MTD |
| `ads_store_performance` | 日 × 门店 | 门店 GMV、客流、转化、目标达成、排名 |
| `ads_category_structure` | 日 × 一级/二级品类 | 销售额、占比、折扣、退款、毛利率 |
| `ads_product_topn` | 快照 × SKU | 近30天商品销售与排名 |
| `ads_member_rfm` | 快照 × 会员 | R/F/M 分值与 8 大客群 |
| `ads_member_retention` | 快照 × 首购月 × 月偏移 | Cohort 留存 |
| `ads_member_repurchase` | 月 | 月度复购与 30 日复购 |
| `ads_inventory_turnover` | 日 × 库位 | 30 日库存周转、缺货率、售罄率 |
| `ads_online_funnel` | 日 × 渠道 | 线上各阶段会话与转化率 |
| `ads_promotion_effect` | 快照 × 活动 × 渠道 | 活动增量、让利与 ROI（观察性） |

## 7. 关联关系

```
dim_date ─────────────┐
dim_store ────────────┤
dim_product ──────────┼── dwd_order_detail ── dws_trade_sku_day ── ads_category_structure / ads_product_topn
dim_member ───────────┤
dim_promotion ────────┤
dim_channel ──────────┘
        │
        └── dwd_order_info ── dws_trade_store_day / dws_trade_channel_day / dws_member_day
                                  │
                                  └── ads_operation_overview / ads_store_performance

dwd_payment ── dwd_order_info（有效性）
dwd_refund  ── dwd_order_detail（行级退款）
dwd_inventory_snapshot ── dim_product/dim_store
dwd_online_session ── dim_member/dim_channel/dim_promotion
dwd_behavior_event ── dim_product/dim_member/dim_channel/dim_promotion
```

## 8. 设计约定

- 所有金额使用 `DECIMAL(14,2)` / `DECIMAL(16,2)`，避免浮点误差。
- 所有事实表包含 `dt`；所有维表使用稳定自然键 + 代理键。
- 未知维度统一 `-1`，不生成虚假维度行；门店空值映射为 `__UNKNOWN__`。
- 日汇总表按 `dt` 幂等覆盖；快照表每次全量重算。
- 生成器与 ETL 都使用固定随机种子/稳定哈希，保证多次运行结果一致。
