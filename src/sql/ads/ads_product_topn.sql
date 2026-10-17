WITH p AS (
    SELECT
        product_id,
        MAX(sk_product) AS sk_product,
        MAX(product_name) AS product_name,
        MAX(category_id) AS category_id,
        MAX(category_name) AS category_name,
        MAX(top_category_id) AS top_category_id,
        MAX(top_category_name) AS top_category_name,
        MAX(brand_id) AS brand_id,
        MAX(brand_name) AS brand_name,
        SUM(sales_amount) AS sales_amount,
        SUM(sale_qty) AS sale_qty,
        SUM(order_cnt) AS sku_order_cnt,
        SUM(refund_amount) AS refund_amount,
        SUM(cogs) AS cogs
    FROM dws_trade_sku_day
    WHERE dt BETWEEN DATE_FORMAT(DATE_SUB(TO_DATE('${end_date}'), 29), 'yyyy-MM-dd') AND '${end_date}'
    GROUP BY product_id
),
ranked AS (
    SELECT
        p.*,
        ROW_NUMBER() OVER (ORDER BY sales_amount DESC) AS overall_rank,
        ROW_NUMBER() OVER (PARTITION BY top_category_id ORDER BY sales_amount DESC) AS category_rank
    FROM p
    WHERE sales_amount > 0
)
SELECT
    '${end_date}' AS dt,
    product_id,
    sk_product,
    product_name,
    category_id,
    category_name,
    top_category_id,
    top_category_name,
    brand_id,
    brand_name,
    CAST(sales_amount AS DECIMAL(18,2)) AS sales_amount,
    sale_qty,
    sku_order_cnt,
    CAST(refund_amount AS DECIMAL(18,2)) AS refund_amount,
    ROUND(refund_amount / NULLIF(sales_amount, 0), 4) AS refund_rate,
    CAST(sales_amount - cogs AS DECIMAL(18,2)) AS gross_profit,
    ROUND((sales_amount - cogs) / NULLIF(sales_amount, 0), 4) AS gross_margin_rate,
    overall_rank,
    category_rank,
    CURRENT_TIMESTAMP() AS etl_time
FROM ranked
