WITH ord AS (
    SELECT
        dt, channel_id, sk_channel, channel_name, channel_type,
        COUNT(*) AS order_cnt,
        SUM(CASE WHEN is_member = 1 THEN 1 ELSE 0 END) AS member_order_cnt,
        COUNT(DISTINCT CASE WHEN is_member = 1 THEN member_id END) AS buyer_cnt,
        SUM(paid_amount) AS gmv,
        SUM(CASE WHEN is_member = 1 THEN paid_amount ELSE 0 END) AS member_gmv,
        SUM(discount_amount) AS discount_amount,
        SUM(shipping_fee) AS shipping_fee
    FROM dwd_order_info
    WHERE is_paid = 1
    GROUP BY dt, channel_id, sk_channel, channel_name, channel_type
),
det AS (
    SELECT dt, channel_id,
           SUM(quantity) AS sku_qty,
           SUM(line_amount) AS merchandise_sales,
           SUM(cost_amount) AS cogs,
           COUNT(DISTINCT product_id) AS sku_cnt
    FROM dwd_order_detail
    WHERE is_paid = 1
    GROUP BY dt, channel_id
),
ref AS (
    SELECT dt, channel_id,
           COUNT(DISTINCT order_id) AS refund_order_cnt,
           SUM(refund_amount) AS refund_amount
    FROM dwd_refund
    WHERE refund_status = '已完成'
    GROUP BY dt, channel_id
)
SELECT
    o.dt,
    o.channel_id,
    o.sk_channel,
    o.channel_name,
    o.channel_type,
    o.order_cnt,
    o.member_order_cnt,
    o.buyer_cnt,
    CAST(o.gmv AS DECIMAL(16,2)) AS gmv,
    CAST(o.member_gmv AS DECIMAL(16,2)) AS member_gmv,
    CAST(o.discount_amount AS DECIMAL(16,2)) AS discount_amount,
    CAST(o.shipping_fee AS DECIMAL(16,2)) AS shipping_fee,
    COALESCE(d.sku_qty, 0) AS sku_qty,
    COALESCE(d.sku_cnt, 0) AS sku_cnt,
    CAST(COALESCE(d.merchandise_sales, 0) AS DECIMAL(16,2)) AS merchandise_sales,
    CAST(COALESCE(d.cogs, 0) AS DECIMAL(16,2)) AS cogs,
    CAST(COALESCE(d.merchandise_sales, 0) - COALESCE(d.cogs, 0) AS DECIMAL(16,2)) AS gross_profit,
    COALESCE(r.refund_order_cnt, 0) AS refund_order_cnt,
    CAST(COALESCE(r.refund_amount, 0) AS DECIMAL(16,2)) AS refund_amount,
    CAST(o.gmv - COALESCE(r.refund_amount, 0) AS DECIMAL(16,2)) AS net_sales_amount,
    ROUND(o.gmv / NULLIF(o.order_cnt, 0), 2) AS avg_order_value,
    ROUND(o.member_gmv / NULLIF(o.gmv, 0), 4) AS member_gmv_ratio,
    ROUND(COALESCE(r.refund_amount, 0) / NULLIF(o.gmv, 0), 4) AS refund_rate,
    ROUND((COALESCE(d.merchandise_sales, 0) - COALESCE(d.cogs, 0)) / NULLIF(d.merchandise_sales, 0), 4) AS gross_margin_rate,
    CURRENT_TIMESTAMP() AS etl_time
FROM ord o
LEFT JOIN det d ON o.dt = d.dt AND o.channel_id = d.channel_id
LEFT JOIN ref r ON o.dt = r.dt AND o.channel_id = r.channel_id
