WITH t AS (
    SELECT * FROM (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY dt, store_id ORDER BY update_time DESC) AS rn
        FROM ods_store_traffic_daily
        WHERE dt IS NOT NULL AND store_id IS NOT NULL
    ) x WHERE rn = 1
)
SELECT
    t.dt,
    TO_DATE(t.dt) AS dt_date,
    TRIM(t.store_id) AS store_id,
    COALESCE(s.sk_store, -1) AS sk_store,
    COALESCE(s.store_name, '未知门店') AS store_name,
    COALESCE(s.store_type, '未知') AS store_type,
    COALESCE(s.city_id, '未知') AS city_id,
    COALESCE(s.region_id, '未知') AS region_id,
    CAST(COALESCE(t.traffic_in, 0) AS INT) AS traffic_in,
    CURRENT_TIMESTAMP() AS etl_time
FROM t
LEFT JOIN dim_store s ON TRIM(t.store_id) = s.store_id
WHERE CAST(COALESCE(t.traffic_in, 0) AS INT) >= 0
