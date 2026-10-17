WITH inv AS (
    SELECT * FROM (
        SELECT *, ROW_NUMBER() OVER (
            PARTITION BY dt, location_id, product_id ORDER BY update_time DESC
        ) AS rn
        FROM ods_inventory_snapshot
        WHERE dt IS NOT NULL AND location_id IS NOT NULL AND product_id IS NOT NULL
    ) t WHERE rn = 1
)
SELECT
    inv.dt,
    TO_DATE(inv.dt) AS dt_date,
    TRIM(inv.location_id) AS location_id,
    COALESCE(s.sk_store, -1) AS sk_location,
    COALESCE(s.store_name, '未知门店') AS location_name,
    COALESCE(s.store_type, '未知') AS store_type,
    COALESCE(s.city_id, '未知') AS city_id,
    COALESCE(s.region_id, '未知') AS region_id,
    COALESCE(s.is_offline, 0) AS is_offline,
    TRIM(inv.product_id) AS product_id,
    COALESCE(p.sk_product, -1) AS sk_product,
    COALESCE(p.product_name, '未知商品') AS product_name,
    COALESCE(p.category_id, '未知') AS category_id,
    COALESCE(p.category_name, '未知品类') AS category_name,
    COALESCE(p.top_category_id, '未知') AS top_category_id,
    COALESCE(p.top_category_name, '未知品类') AS top_category_name,
    CAST(COALESCE(inv.begin_qty, 0) AS INT) AS begin_qty,
    CAST(COALESCE(inv.purchase_in_qty, 0) AS INT) AS purchase_in_qty,
    CAST(COALESCE(inv.sale_qty, 0) AS INT) AS sale_qty,
    CAST(COALESCE(inv.return_qty, 0) AS INT) AS return_qty,
    CAST(COALESCE(inv.adjustment_qty, 0) AS INT) AS adjustment_qty,
    CAST(COALESCE(inv.end_qty, 0) AS INT) AS end_qty,
    CAST(COALESCE(inv.safety_stock, 0) AS INT) AS safety_stock,
    CAST(COALESCE(inv.cost_price, 0) AS DECIMAL(12,2)) AS cost_price,
    CAST(COALESCE(inv.stock_value, 0) AS DECIMAL(14,2)) AS stock_value,
    CASE
        WHEN CAST(COALESCE(inv.end_qty, 0) AS INT) <= 0 THEN '缺货'
        WHEN CAST(COALESCE(inv.end_qty, 0) AS INT) < CAST(COALESCE(inv.safety_stock, 0) AS INT) THEN '低库存'
        ELSE '正常'
    END AS stock_status,
    CURRENT_TIMESTAMP() AS etl_time
FROM inv
LEFT JOIN dim_store s ON TRIM(inv.location_id) = s.store_id
LEFT JOIN dim_product p ON TRIM(inv.product_id) = p.product_id
