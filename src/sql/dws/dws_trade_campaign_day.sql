WITH ord AS (
    SELECT
        dt, promotion_id, sk_promotion, channel_id, sk_channel, channel_type,
        COUNT(*) AS order_cnt,
        SUM(CASE WHEN is_member = 1 THEN 1 ELSE 0 END) AS member_order_cnt,
        COUNT(DISTINCT CASE WHEN is_member = 1 THEN member_id END) AS buyer_cnt,
        SUM(paid_amount) AS gmv,
        SUM(discount_amount) AS discount_amount,
        SUM(shipping_fee) AS shipping_fee
    FROM dwd_order_info
    WHERE is_paid = 1 AND promotion_id IS NOT NULL
    GROUP BY dt, promotion_id, sk_promotion, channel_id, sk_channel, channel_type
),
det AS (
    SELECT
        o.dt, o.promotion_id, o.channel_id,
        SUM(d.quantity) AS sku_qty,
        SUM(d.line_amount) AS merchandise_sales,
        SUM(d.cost_amount) AS cogs
    FROM dwd_order_detail d
    INNER JOIN dwd_order_info o ON d.order_id = o.order_id
    WHERE d.is_paid = 1 AND o.promotion_id IS NOT NULL
    GROUP BY o.dt, o.promotion_id, o.channel_id
),
ref AS (
    SELECT dt, promotion_id, channel_id,
           COUNT(DISTINCT order_id) AS refund_order_cnt,
           SUM(refund_amount) AS refund_amount
    FROM dwd_refund
    WHERE refund_status = '已完成' AND promotion_id IS NOT NULL
    GROUP BY dt, promotion_id, channel_id
)
SELECT
    o.dt,
    o.promotion_id,
    o.sk_promotion,
    pm.promotion_name,
    pm.promo_type,
    pm.start_date,
    pm.end_date,
    o.channel_id,
    o.sk_channel,
    o.channel_type,
    o.order_cnt,
    o.member_order_cnt,
    o.buyer_cnt,
    CAST(o.gmv AS DECIMAL(16,2)) AS gmv,
    CAST(o.discount_amount AS DECIMAL(16,2)) AS discount_amount,
    CAST(o.shipping_fee AS DECIMAL(16,2)) AS shipping_fee,
    COALESCE(d.sku_qty, 0) AS sku_qty,
    CAST(COALESCE(d.merchandise_sales, 0) AS DECIMAL(16,2)) AS merchandise_sales,
    CAST(COALESCE(d.cogs, 0) AS DECIMAL(16,2)) AS cogs,
    COALESCE(r.refund_order_cnt, 0) AS refund_order_cnt,
    CAST(COALESCE(r.refund_amount, 0) AS DECIMAL(16,2)) AS refund_amount,
    CAST(o.gmv - COALESCE(r.refund_amount, 0) AS DECIMAL(16,2)) AS net_sales_amount,
    ROUND(o.gmv / NULLIF(o.order_cnt, 0), 2) AS avg_order_value,
    ROUND(o.member_order_cnt / NULLIF(o.order_cnt, 0), 4) AS member_order_ratio,
    ROUND(COALESCE(r.refund_amount, 0) / NULLIF(o.gmv, 0), 4) AS refund_rate,
    CURRENT_TIMESTAMP() AS etl_time
FROM ord o
LEFT JOIN det d ON o.dt = d.dt AND o.promotion_id = d.promotion_id AND o.channel_id = d.channel_id
LEFT JOIN ref r ON o.dt = r.dt AND o.promotion_id = r.promotion_id AND o.channel_id = r.channel_id
LEFT JOIN dim_promotion pm ON o.promotion_id = pm.promotion_id
