WITH paid AS (
    SELECT DISTINCT
        member_id,
        DATE_FORMAT(order_date, 'yyyy-MM') AS order_month
    FROM dwd_order_info
    WHERE is_paid = 1 AND is_member = 1 AND member_id IS NOT NULL
),
firsts AS (
    SELECT member_id, MIN(order_month) AS first_month
    FROM paid
    GROUP BY member_id
),
cohort_sizes AS (
    SELECT first_month, COUNT(*) AS cohort_size
    FROM firsts
    GROUP BY first_month
),
activity AS (
    SELECT f.first_month, p.member_id,
           (CAST(SUBSTR(p.order_month, 1, 4) AS INT) * 12 + CAST(SUBSTR(p.order_month, 6, 2) AS INT))
           - (CAST(SUBSTR(f.first_month, 1, 4) AS INT) * 12 + CAST(SUBSTR(f.first_month, 6, 2) AS INT)) AS months_diff
    FROM firsts f
    INNER JOIN paid p ON f.member_id = p.member_id
),
retained AS (
    SELECT first_month, months_diff, COUNT(DISTINCT member_id) AS retained_members
    FROM activity
    WHERE months_diff BETWEEN 0 AND 5
    GROUP BY first_month, months_diff
),
offsets AS (
    SELECT EXPLODE(SEQUENCE(0, 5)) AS months_diff
),
all_rows AS (
    SELECT c.first_month, c.cohort_size, o.months_diff,
           ADD_MONTHS(TO_DATE(CONCAT(c.first_month, '-01')), o.months_diff) AS month_start
    FROM cohort_sizes c
    CROSS JOIN offsets o
)
SELECT
    '${end_date}' AS dt,
    a.first_month AS cohort_month,
    a.cohort_size,
    a.months_diff,
    DATE_FORMAT(a.month_start, 'yyyy-MM') AS stat_month,
    DATE_FORMAT(LAST_DAY(a.month_start), 'yyyy-MM-dd') AS stat_month_end,
    CASE WHEN a.month_start <= TO_DATE('${end_date}') THEN 1 ELSE 0 END AS is_observed,
    CASE WHEN LAST_DAY(a.month_start) <= TO_DATE('${end_date}')
              AND a.month_start >= TO_DATE('${start_date}')
         THEN 1 ELSE 0 END AS is_complete,
    CASE WHEN a.month_start <= TO_DATE('${end_date}')
         THEN COALESCE(r.retained_members, 0) ELSE NULL END AS retained_members,
    CASE WHEN a.month_start <= TO_DATE('${end_date}')
         THEN ROUND(COALESCE(r.retained_members, 0) / NULLIF(a.cohort_size, 0), 4)
         ELSE NULL END AS retention_rate,
    CURRENT_TIMESTAMP() AS etl_time
FROM all_rows a
LEFT JOIN retained r ON a.first_month = r.first_month AND a.months_diff = r.months_diff
ORDER BY a.first_month, a.months_diff
