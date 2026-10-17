WITH orders AS (
    SELECT
        member_id,
        order_id,
        order_time,
        DATE_FORMAT(order_date, 'yyyy-MM') AS stat_month
    FROM dwd_order_info
    WHERE is_paid = 1 AND is_member = 1 AND member_id IS NOT NULL
),
ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (PARTITION BY member_id, stat_month ORDER BY order_time) AS rn,
        MIN(order_time) OVER (PARTITION BY member_id, stat_month) AS first_order_time
    FROM orders
),
repeat30 AS (
    SELECT stat_month, COUNT(DISTINCT member_id) AS repeat_30d_buyers
    FROM ranked
    WHERE rn = 2 AND DATEDIFF(order_time, first_order_time) <= 30
    GROUP BY stat_month
),
member_month AS (
    SELECT member_id, stat_month, COUNT(*) AS order_cnt
    FROM orders
    GROUP BY member_id, stat_month
),
monthly AS (
    SELECT
        stat_month,
        COUNT(*) AS monthly_buyers,
        SUM(CASE WHEN order_cnt >= 2 THEN 1 ELSE 0 END) AS repeat_buyers
    FROM member_month
    GROUP BY stat_month
)
SELECT
    DATE_FORMAT(LEAST(LAST_DAY(TO_DATE(CONCAT(m.stat_month, '-01'))), TO_DATE('${end_date}')), 'yyyy-MM-dd') AS dt,
    m.stat_month,
    m.monthly_buyers,
    m.repeat_buyers,
    ROUND(m.repeat_buyers / NULLIF(m.monthly_buyers, 0), 4) AS repurchase_rate,
    COALESCE(r.repeat_30d_buyers, 0) AS repeat_30d_buyers,
    ROUND(COALESCE(r.repeat_30d_buyers, 0) / NULLIF(m.monthly_buyers, 0), 4) AS repeat_30d_rate,
    CASE WHEN LAST_DAY(TO_DATE(CONCAT(m.stat_month, '-01'))) <= TO_DATE('${end_date}')
              AND TO_DATE(CONCAT(m.stat_month, '-01')) >= TO_DATE('${start_date}')
         THEN 1 ELSE 0 END AS is_complete,
    CURRENT_TIMESTAMP() AS etl_time
FROM monthly m
LEFT JOIN repeat30 r ON m.stat_month = r.stat_month
ORDER BY m.stat_month
