WITH d AS (
    SELECT * FROM (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY order_id, line_id ORDER BY update_time DESC) AS rn
        FROM ods_order_detail
        WHERE order_id IS NOT NULL AND line_id IS NOT NULL
    ) t WHERE rn = 1
)
SELECT
    o.order_id,
    d.line_id,
    o.dt,
    o.order_date,
    o.sk_date,
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
    o.is_paid,
    o.order_status,
    d.product_id,
    COALESCE(p.sk_product, -1) AS sk_product,
    COALESCE(p.product_name, '未知商品') AS product_name,
    COALESCE(p.category_id, '未知') AS category_id,
    COALESCE(p.category_name, '未知品类') AS category_name,
    COALESCE(p.top_category_id, '未知') AS top_category_id,
    COALESCE(p.top_category_name, '未知') AS top_category_name,
    COALESCE(p.brand_id, '未知') AS brand_id,
    COALESCE(p.brand_name, '未知品牌') AS brand_name,
    CAST(d.quantity AS INT) AS quantity,
    CAST(COALESCE(d.list_price, p.list_price, 0) AS DECIMAL(12,2)) AS list_price,
    CAST(COALESCE(d.sale_price, 0) AS DECIMAL(12,2)) AS sale_price,
    CAST(ROUND(COALESCE(d.quantity, 0) * COALESCE(d.sale_price, 0), 2) AS DECIMAL(14,2)) AS line_amount,
    CAST(COALESCE(
        d.discount_amount,
        ROUND(COALESCE(d.quantity, 0) * (COALESCE(d.list_price, 0) - COALESCE(d.sale_price, 0)), 2)
    ) AS DECIMAL(14,2)) AS discount_amount,
    CAST(ROUND(COALESCE(d.quantity, 0) * COALESCE(p.cost_price, 0), 2) AS DECIMAL(14,2)) AS cost_amount,
    CURRENT_TIMESTAMP() AS etl_time
FROM d
INNER JOIN dwd_order_info o ON TRIM(d.order_id) = o.order_id
LEFT JOIN dim_product p ON TRIM(d.product_id) = p.product_id
WHERE CAST(d.quantity AS INT) > 0
  AND CAST(COALESCE(d.sale_price, 0) AS DECIMAL(12,2)) >= 0
  AND CAST(COALESCE(d.list_price, 0) AS DECIMAL(12,2)) >= 0
