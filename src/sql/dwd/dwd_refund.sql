WITH r AS (
    SELECT * FROM (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY refund_id ORDER BY update_time DESC) AS rn
        FROM ods_refund_info
        WHERE refund_id IS NOT NULL
    ) t WHERE rn = 1
),
rc AS (
    SELECT *,
           COALESCE(
               TRY_TO_TIMESTAMP(TRIM(refund_time), 'yyyy-MM-dd HH:mm:ss'),
               TRY_TO_TIMESTAMP(TRIM(refund_time), 'yyyy/MM/dd HH:mm:ss')
           ) AS refund_ts
    FROM r
)
SELECT
    TRIM(rc.refund_id) AS refund_id,
    TRIM(rc.order_id) AS order_id,
    TRIM(rc.line_id) AS line_id,
    DATE_FORMAT(rc.refund_ts, 'yyyy-MM-dd') AS dt,
    rc.refund_ts AS refund_time,
    CAST(COALESCE(rc.refund_amount, 0) AS DECIMAL(14,2)) AS refund_amount,
    TRIM(rc.refund_reason) AS refund_reason,
    TRIM(rc.refund_type) AS refund_type,
    TRIM(rc.refund_channel) AS refund_channel,
    TRIM(rc.refund_status) AS refund_status,
    CAST(COALESCE(rc.return_qty, 0) AS INT) AS return_qty,
    o.store_id,
    o.sk_store,
    o.store_type,
    o.city_id,
    o.region_id,
    o.is_offline,
    o.channel_id,
    o.sk_channel,
    o.channel_type,
    o.member_id,
    o.sk_member,
    o.is_member,
    o.promotion_id,
    o.sk_promotion,
    d.product_id,
    COALESCE(p.sk_product, -1) AS sk_product,
    COALESCE(p.category_id, '未知') AS category_id,
    COALESCE(p.category_name, '未知品类') AS category_name,
    COALESCE(p.top_category_id, '未知') AS top_category_id,
    COALESCE(p.top_category_name, '未知品类') AS top_category_name,
    CAST(ROUND(COALESCE(d.quantity, 0) * COALESCE(d.sale_price, 0), 2) AS DECIMAL(14,2)) AS line_amount,
    CURRENT_TIMESTAMP() AS etl_time
FROM rc
INNER JOIN dwd_order_info o ON TRIM(rc.order_id) = o.order_id
LEFT JOIN dwd_order_detail d ON TRIM(rc.order_id) = d.order_id AND TRIM(rc.line_id) = d.line_id
LEFT JOIN dim_product p ON d.product_id = p.product_id
WHERE rc.refund_ts IS NOT NULL
  AND CAST(COALESCE(rc.refund_amount, 0) AS DECIMAL(14,2)) > 0
  AND TRIM(rc.refund_status) IN ('已完成', '处理中')
