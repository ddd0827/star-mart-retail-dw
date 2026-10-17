WITH sales AS (
    SELECT
        dt, channel_id, sk_channel, channel_type,
        product_id, sk_product, product_name, category_id, category_name,
        top_category_id, top_category_name, brand_id, brand_name,
        COUNT(DISTINCT order_id) AS order_cnt,
        COUNT(*) AS line_cnt,
        SUM(quantity) AS sale_qty,
        SUM(line_amount) AS sales_amount,
        SUM(discount_amount) AS discount_amount,
        SUM(cost_amount) AS cogs
    FROM dwd_order_detail
    WHERE is_paid = 1
    GROUP BY dt, channel_id, sk_channel, channel_type, product_id, sk_product, product_name,
             category_id, category_name, top_category_id, top_category_name, brand_id, brand_name
),
ref AS (
    SELECT
        dt, channel_id, product_id,
        COUNT(DISTINCT order_id) AS refund_order_cnt,
        SUM(return_qty) AS refund_qty,
        SUM(refund_amount) AS refund_amount
    FROM dwd_refund
    WHERE refund_status = '已完成'
    GROUP BY dt, channel_id, product_id
)
SELECT
    COALESCE(s.dt, r.dt) AS dt,
    COALESCE(s.channel_id, r.channel_id) AS channel_id,
    s.sk_channel,
    s.channel_type,
    COALESCE(s.product_id, r.product_id) AS product_id,
    s.sk_product,
    s.product_name,
    s.category_id,
    s.category_name,
    s.top_category_id,
    s.top_category_name,
    s.brand_id,
    s.brand_name,
    COALESCE(s.order_cnt, 0) AS order_cnt,
    COALESCE(s.line_cnt, 0) AS line_cnt,
    COALESCE(s.sale_qty, 0) AS sale_qty,
    CAST(COALESCE(s.sales_amount, 0) AS DECIMAL(16,2)) AS sales_amount,
    CAST(COALESCE(s.discount_amount, 0) AS DECIMAL(16,2)) AS discount_amount,
    CAST(COALESCE(s.cogs, 0) AS DECIMAL(16,2)) AS cogs,
    CAST(COALESCE(s.sales_amount, 0) - COALESCE(s.cogs, 0) AS DECIMAL(16,2)) AS gross_profit,
    COALESCE(r.refund_order_cnt, 0) AS refund_order_cnt,
    COALESCE(r.refund_qty, 0) AS refund_qty,
    CAST(COALESCE(r.refund_amount, 0) AS DECIMAL(16,2)) AS refund_amount,
    CAST(COALESCE(s.sales_amount, 0) - COALESCE(r.refund_amount, 0) AS DECIMAL(16,2)) AS net_sales_amount,
    ROUND(COALESCE(r.refund_amount, 0) / NULLIF(s.sales_amount, 0), 4) AS refund_rate,
    ROUND((COALESCE(s.sales_amount, 0) - COALESCE(s.cogs, 0)) / NULLIF(s.sales_amount, 0), 4) AS gross_margin_rate,
    CURRENT_TIMESTAMP() AS etl_time
FROM sales s
FULL OUTER JOIN ref r
  ON s.dt = r.dt AND s.channel_id = r.channel_id AND s.product_id = r.product_id
