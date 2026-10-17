WITH daily AS (
    SELECT
        dt,
        SUM(gmv) AS gmv,
        SUM(member_gmv) AS member_gmv,
        SUM(order_cnt) AS order_cnt,
        SUM(member_order_cnt) AS member_order_cnt,
        SUM(refund_amount) AS refund_amount,
        SUM(refund_order_cnt) AS refund_order_cnt,
        SUM(merchandise_sales) AS merchandise_sales,
        SUM(cogs) AS cogs,
        SUM(discount_amount) AS discount_amount
    FROM dws_trade_store_day
    GROUP BY dt
),
online AS (
    SELECT dt,
           SUM(gmv) AS online_gmv,
           SUM(order_cnt) AS online_order_cnt
    FROM dws_trade_channel_day
    WHERE channel_type = '线上'
    GROUP BY dt
),
members AS (
    SELECT dt, COUNT(*) AS active_member_cnt
    FROM dws_member_day
    GROUP BY dt
),
new_members AS (
    SELECT CAST(register_date AS STRING) AS dt, COUNT(*) AS new_member_cnt
    FROM dim_member
    WHERE register_date IS NOT NULL
    GROUP BY CAST(register_date AS STRING)
),
base AS (
    SELECT
        d.dt,
        d.gmv,
        d.member_gmv,
        d.order_cnt,
        d.member_order_cnt,
        d.refund_amount,
        d.refund_order_cnt,
        d.merchandise_sales,
        d.cogs,
        d.discount_amount,
        COALESCE(o.online_gmv, 0) AS online_gmv,
        COALESCE(o.online_order_cnt, 0) AS online_order_cnt,
        COALESCE(m.active_member_cnt, 0) AS active_member_cnt,
        COALESCE(n.new_member_cnt, 0) AS new_member_cnt,
        d.gmv - d.refund_amount AS net_sales_amount,
        d.merchandise_sales - d.cogs AS gross_profit
    FROM daily d
    LEFT JOIN online o ON d.dt = o.dt
    LEFT JOIN members m ON d.dt = m.dt
    LEFT JOIN new_members n ON d.dt = n.dt
)
SELECT
    dt,
    CAST(gmv AS DECIMAL(18,2)) AS gmv,
    CAST(net_sales_amount AS DECIMAL(18,2)) AS net_sales_amount,
    CAST(refund_amount AS DECIMAL(18,2)) AS refund_amount,
    ROUND(refund_amount / NULLIF(gmv, 0), 4) AS refund_rate,
    ROUND(refund_order_cnt / NULLIF(order_cnt, 0), 4) AS refund_order_rate,
    order_cnt,
    member_order_cnt,
    active_member_cnt,
    new_member_cnt,
    ROUND(gmv / NULLIF(order_cnt, 0), 2) AS avg_order_value,
    ROUND(member_gmv / NULLIF(gmv, 0), 4) AS member_gmv_ratio,
    CAST(online_gmv AS DECIMAL(18,2)) AS online_gmv,
    ROUND(online_gmv / NULLIF(gmv, 0), 4) AS online_gmv_ratio,
    online_order_cnt,
    CAST(gross_profit AS DECIMAL(18,2)) AS gross_profit,
    ROUND(gross_profit / NULLIF(merchandise_sales, 0), 4) AS gross_margin_rate,
    ROUND(discount_amount / NULLIF(merchandise_sales + discount_amount, 0), 4) AS discount_rate,
    ROUND(AVG(gmv) OVER (ORDER BY dt ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 2) AS avg_gmv_7d,
    ROUND((gmv - LAG(gmv) OVER (ORDER BY dt)) / NULLIF(LAG(gmv) OVER (ORDER BY dt), 0), 4) AS dod_rate,
    CAST(SUM(gmv) OVER (PARTITION BY SUBSTR(dt, 1, 7) ORDER BY dt ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS DECIMAL(18,2)) AS mtd_gmv,
    CURRENT_TIMESTAMP() AS etl_time
FROM base
