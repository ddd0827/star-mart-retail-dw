WITH po AS (
    SELECT * FROM (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY po_id ORDER BY update_time DESC) AS rn
        FROM ods_purchase_order
        WHERE po_id IS NOT NULL
    ) t WHERE rn = 1
)
SELECT
    TRIM(po.po_id) AS po_id,
    po.dt,
    TRIM(po.location_id) AS location_id,
    COALESCE(s.sk_store, -1) AS sk_location,
    COALESCE(s.store_name, '未知门店') AS location_name,
    TRIM(po.product_id) AS product_id,
    COALESCE(p.sk_product, -1) AS sk_product,
    TRIM(po.supplier_id) AS supplier_id,
    COALESCE(sp.sk_supplier, -1) AS sk_supplier,
    CAST(po.order_date AS DATE) AS order_date,
    CAST(po.expected_arrival_date AS DATE) AS expected_arrival_date,
    CAST(po.arrival_date AS DATE) AS arrival_date,
    CAST(COALESCE(po.quantity, 0) AS INT) AS quantity,
    CAST(COALESCE(po.unit_cost, 0) AS DECIMAL(12,2)) AS unit_cost,
    CAST(COALESCE(po.total_amount, 0) AS DECIMAL(14,2)) AS total_amount,
    TRIM(po.po_status) AS po_status,
    CURRENT_TIMESTAMP() AS etl_time
FROM po
LEFT JOIN dim_store s ON TRIM(po.location_id) = s.store_id
LEFT JOIN dim_product p ON TRIM(po.product_id) = p.product_id
LEFT JOIN dim_supplier sp ON TRIM(po.supplier_id) = sp.supplier_id
