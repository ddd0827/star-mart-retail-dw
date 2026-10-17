WITH ord AS (
    SELECT
        dt, store_id, sk_store, store_name, store_type, city_id, region_id, is_offline,
        COUNT(*) AS order_cnt,
        SUM(CASE WHEN is_member = 1 THEN 1 ELSE 0 END) AS member_order_cnt,
        COUNT(DISTINCT CASE WHEN is_member = 1 THEN member_id END) AS buyer_cnt,
        SUM(paid_amount) AS gmv,
        SUM(CASE WHEN is_member = 1 THEN paid_amount ELSE 0 END) AS member_gmv,
        SUM(discount_amount) AS discount_amount,
        SUM(shipping_fee) AS shipping_fee
    FROM dwd_order_info
    WHERE is_paid = 1
    GROUP BY dt, store_id, sk_store, store_name, store_type, city_id, region_id, is_offline
),
det AS (
    SELECT dt, store_id,
           COUNT(*) AS line_cnt,
           COUNT(DISTINCT product_id) AS sku_cnt,
           SUM(quantity) AS sku_qty,
           SUM(line_amount) AS merchandise_sales,
           SUM(cost_amount) AS cogs
    FROM dwd_order_detail
    WHERE is_paid = 1
    GROUP BY dt, store_id
),
ref AS (
    SELECT dt, store_id,
           COUNT(DISTINCT order_id) AS refund_order_cnt,
           SUM(refund_amount) AS refund_amount,
           SUM(return_qty) AS refund_qty
    FROM dwd_refund
    WHERE refund_status = '已完成'
    GROUP BY dt, store_id
),
tr AS (
    SELECT dt, store_id, SUM(traffic_in) AS traffic_in
    FROM dwd_store_traffic
    GROUP BY dt, store_id
)
SELECT
    o.dt,
    o.store_id,
    o.sk_store,
    o.store_name,
    o.store_type,
    o.city_id,
    o.region_id,
    o.is_offline,
    o.order_cnt,
    o.member_order_cnt,
    o.buyer_cnt,
    CAST(o.gmv AS DECIMAL(16,2)) AS gmv,
    CAST(o.member_gmv AS DECIMAL(16,2)) AS member_gmv,
    CAST(o.discount_amount AS DECIMAL(16,2)) AS discount_amount,
    CAST(o.shipping_fee AS DECIMAL(16,2)) AS shipping_fee,
    COALESCE(d.line_cnt, 0) AS line_cnt,
    COALESCE(d.sku_cnt, 0) AS sku_cnt,
    COALESCE(d.sku_qty, 0) AS sku_qty,
    CAST(COALESCE(d.merchandise_sales, 0) AS DECIMAL(16,2)) AS merchandise_sales,
    CAST(COALESCE(d.cogs, 0) AS DECIMAL(16,2)) AS cogs,
    CAST(COALESCE(d.merchandise_sales, 0) - COALESCE(d.cogs, 0) AS DECIMAL(16,2)) AS gross_profit,
    COALESCE(r.refund_order_cnt, 0) AS refund_order_cnt,
    CAST(COALESCE(r.refund_amount, 0) AS DECIMAL(16,2)) AS refund_amount,
    COALESCE(r.refund_qty, 0) AS refund_qty,
    CAST(o.gmv - COALESCE(r.refund_amount, 0) AS DECIMAL(16,2)) AS net_sales_amount,
    ROUND(o.gmv / NULLIF(o.order_cnt, 0), 2) AS avg_order_value,
    ROUND(o.member_gmv / NULLIF(o.gmv, 0), 4) AS member_gmv_ratio,
    ROUND(COALESCE(r.refund_amount, 0) / NULLIF(o.gmv, 0), 4) AS refund_rate,
    ROUND(COALESCE(r.refund_order_cnt, 0) / NULLIF(o.order_cnt, 0), 4) AS refund_order_rate,
    ROUND((COALESCE(d.merchandise_sales, 0) - COALESCE(d.cogs, 0)) / NULLIF(d.merchandise_sales, 0), 4) AS gross_margin_rate,
    COALESCE(t.traffic_in, 0) AS traffic_in,
    CASE WHEN o.is_offline = 1
         THEN ROUND(o.order_cnt / NULLIF(t.traffic_in, 0), 4)
         ELSE NULL END AS conversion_rate,
    CURRENT_TIMESTAMP() AS etl_time
FROM ord o
LEFT JOIN det d ON o.dt = d.dt AND o.store_id = d.store_id
LEFT JOIN ref r ON o.dt = r.dt AND o.store_id = r.store_id
LEFT JOIN tr t ON o.dt = t.dt AND o.store_id = t.store_id
