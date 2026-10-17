WITH inv AS (
    SELECT
        dt,
        location_id,
        sk_location,
        location_name,
        store_type,
        is_offline,
        SUM(stock_value) AS stock_value,
        COUNT(*) AS sku_cnt,
        SUM(is_stockout) AS stockout_sku_cnt,
        SUM(sale_qty) AS sale_qty,
        SUM(available_qty) AS available_qty
    FROM dws_inventory_sku_day
    GROUP BY dt, location_id, sk_location, location_name, store_type, is_offline
),
store_day AS (
    SELECT dt, store_id, cogs
    FROM dws_trade_store_day
),
joined AS (
    SELECT i.*, COALESCE(s.cogs, 0) AS cogs
    FROM inv i
    LEFT JOIN store_day s ON i.dt = s.dt AND i.location_id = s.store_id
),
windowed AS (
    SELECT
        *,
        COUNT(*) OVER w AS days_observed,
        AVG(stock_value) OVER w AS avg_stock_value_30d,
        SUM(cogs) OVER w AS cogs_30d,
        SUM(stockout_sku_cnt) OVER w AS stockout_sku_cnt_30d,
        SUM(sku_cnt) OVER w AS sku_cnt_30d,
        SUM(sale_qty) OVER w AS sale_qty_30d,
        SUM(available_qty) OVER w AS available_qty_30d
    FROM joined
    WINDOW w AS (PARTITION BY location_id ORDER BY dt ROWS BETWEEN 29 PRECEDING AND CURRENT ROW)
)
SELECT
    dt,
    location_id,
    sk_location,
    location_name,
    store_type,
    is_offline,
    CAST(avg_stock_value_30d AS DECIMAL(18,2)) AS avg_stock_value_30d,
    CAST(cogs_30d AS DECIMAL(18,2)) AS cogs_30d,
    CASE WHEN days_observed >= 30 AND cogs_30d > 0
         THEN ROUND(avg_stock_value_30d * 30 / cogs_30d, 2) ELSE NULL END AS turnover_days,
    ROUND(stockout_sku_cnt_30d / NULLIF(sku_cnt_30d, 0), 4) AS stockout_rate_30d,
    ROUND(sale_qty_30d / NULLIF(available_qty_30d, 0), 4) AS sell_through_rate_30d,
    CAST(stock_value AS DECIMAL(18,2)) AS ending_stock_value,
    sku_cnt,
    stockout_sku_cnt,
    days_observed,
    CURRENT_TIMESTAMP() AS etl_time
FROM windowed
