WITH s AS (
    SELECT
        dt, store_id, sk_store, store_name, store_type, city_id, region_id,
        gmv, net_sales_amount, order_cnt, buyer_cnt, avg_order_value,
        member_gmv_ratio, refund_rate, conversion_rate, traffic_in
    FROM dws_trade_store_day
    WHERE is_offline = 1
),
joined AS (
    SELECT
        s.*,
        t.target_amount,
        t.month_start,
        DAYOFMONTH(LAST_DAY(t.month_start)) AS days_in_month,
        DATEDIFF(TO_DATE(s.dt), GREATEST(t.month_start, TO_DATE('${start_date}'))) + 1 AS mtd_days
    FROM s
    LEFT JOIN dim_store_target t
      ON s.store_id = t.store_id
     AND t.target_month = SUBSTR(s.dt, 1, 7)
),
calc AS (
    SELECT
        j.*,
        ROUND(j.target_amount / NULLIF(j.days_in_month, 0), 2) AS daily_target,
        CAST(j.target_amount * j.mtd_days / NULLIF(j.days_in_month, 0) AS DECIMAL(18,2)) AS mtd_target,
        SUM(j.gmv) OVER (
            PARTITION BY j.store_id, SUBSTR(j.dt, 1, 7) ORDER BY j.dt
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS mtd_gmv
    FROM joined j
)
SELECT
    dt,
    store_id,
    sk_store,
    store_name,
    store_type,
    city_id,
    region_id,
    CAST(gmv AS DECIMAL(18,2)) AS gmv,
    CAST(net_sales_amount AS DECIMAL(18,2)) AS net_sales_amount,
    order_cnt,
    buyer_cnt,
    traffic_in,
    conversion_rate,
    avg_order_value,
    member_gmv_ratio,
    refund_rate,
    daily_target,
    CAST(mtd_gmv AS DECIMAL(18,2)) AS mtd_gmv,
    mtd_target,
    ROUND(mtd_gmv / NULLIF(mtd_target, 0), 4) AS mtd_completion_rate,
    ROUND(gmv / NULLIF(daily_target, 0), 4) AS daily_completion_rate,
    RANK() OVER (PARTITION BY dt ORDER BY gmv DESC) AS daily_rank,
    RANK() OVER (PARTITION BY dt, store_type ORDER BY gmv DESC) AS daily_type_rank,
    RANK() OVER (PARTITION BY dt ORDER BY mtd_gmv DESC) AS mtd_rank,
    CURRENT_TIMESTAMP() AS etl_time
FROM calc
