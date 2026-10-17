WITH cat AS (
    SELECT
        dt,
        top_category_id,
        top_category_name,
        category_id,
        category_name,
        SUM(sales_amount) AS sales_amount,
        SUM(sale_qty) AS sale_qty,
        SUM(refund_amount) AS refund_amount,
        SUM(discount_amount) AS discount_amount,
        SUM(cogs) AS cogs
    FROM dws_trade_sku_day
    GROUP BY dt, top_category_id, top_category_name, category_id, category_name
)
SELECT
    dt,
    top_category_id,
    top_category_name,
    category_id,
    category_name,
    CAST(sales_amount AS DECIMAL(18,2)) AS sales_amount,
    sale_qty,
    CAST(refund_amount AS DECIMAL(18,2)) AS refund_amount,
    ROUND(sales_amount / NULLIF(SUM(sales_amount) OVER (PARTITION BY dt), 0), 4) AS sales_share,
    ROUND(discount_amount / NULLIF(sales_amount + discount_amount, 0), 4) AS discount_rate,
    ROUND(refund_amount / NULLIF(sales_amount, 0), 4) AS refund_rate,
    ROUND((sales_amount - cogs) / NULLIF(sales_amount, 0), 4) AS gross_margin_rate,
    CURRENT_TIMESTAMP() AS etl_time
FROM cat
