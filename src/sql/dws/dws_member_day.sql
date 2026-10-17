WITH ord AS (
    SELECT
        dt, member_id, sk_member,
        COUNT(*) AS order_cnt,
        SUM(paid_amount) AS gmv,
        SUM(discount_amount) AS discount_amount,
        MAX(order_time) AS last_order_time
    FROM dwd_order_info
    WHERE is_paid = 1 AND is_member = 1 AND member_id IS NOT NULL
    GROUP BY dt, member_id, sk_member
),
det AS (
    SELECT
        o.dt, o.member_id,
        SUM(d.quantity) AS sku_qty,
        COUNT(DISTINCT d.top_category_id) AS category_cnt,
        COUNT(DISTINCT d.product_id) AS sku_cnt
    FROM dwd_order_detail d
    INNER JOIN dwd_order_info o
       ON d.order_id = o.order_id
    WHERE d.is_paid = 1 AND o.is_member = 1
    GROUP BY o.dt, o.member_id
),
ref AS (
    SELECT
        dt, member_id,
        COUNT(DISTINCT order_id) AS refund_order_cnt,
        SUM(refund_amount) AS refund_amount
    FROM dwd_refund
    WHERE refund_status = '已完成' AND is_member = 1 AND member_id IS NOT NULL
    GROUP BY dt, member_id
)
SELECT
    o.dt,
    o.member_id,
    o.sk_member,
    m.member_level,
    m.gender,
    m.age_group,
    m.city_id,
    m.register_date,
    o.order_cnt,
    CAST(o.gmv AS DECIMAL(16,2)) AS gmv,
    CAST(o.discount_amount AS DECIMAL(16,2)) AS discount_amount,
    COALESCE(d.sku_qty, 0) AS sku_qty,
    COALESCE(d.sku_cnt, 0) AS sku_cnt,
    COALESCE(d.category_cnt, 0) AS category_cnt,
    COALESCE(r.refund_order_cnt, 0) AS refund_order_cnt,
    CAST(COALESCE(r.refund_amount, 0) AS DECIMAL(16,2)) AS refund_amount,
    CAST(o.gmv - COALESCE(r.refund_amount, 0) AS DECIMAL(16,2)) AS net_sales_amount,
    ROUND(o.gmv / NULLIF(o.order_cnt, 0), 2) AS avg_order_value,
    o.last_order_time,
    CURRENT_TIMESTAMP() AS etl_time
FROM ord o
LEFT JOIN det d ON o.dt = d.dt AND o.member_id = d.member_id
LEFT JOIN ref r ON o.dt = r.dt AND o.member_id = r.member_id
LEFT JOIN dim_member m ON o.sk_member = m.sk_member
