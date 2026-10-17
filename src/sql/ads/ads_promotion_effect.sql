WITH promo_dates AS (
    SELECT
        pm.promotion_id,
        pm.promotion_name,
        pm.promo_type,
        pm.start_date,
        pm.end_date,
        EXPLODE(SEQUENCE(
            GREATEST(pm.start_date, TO_DATE('${start_date}')),
            LEAST(pm.end_date, TO_DATE('${end_date}')),
            INTERVAL 1 DAY
        )) AS activity_date
    FROM dim_promotion pm
    WHERE pm.start_date <= TO_DATE('${end_date}')
      AND pm.end_date >= TO_DATE('${start_date}')
),
activity AS (
    SELECT
        pd.promotion_id,
        c.channel_id,
        COUNT(DISTINCT pd.activity_date) AS activity_days,
        COALESCE(SUM(d.gmv), 0) AS activity_gmv,
        COALESCE(SUM(d.order_cnt), 0) AS activity_orders
    FROM promo_dates pd
    CROSS JOIN dim_channel c
    LEFT JOIN dws_trade_channel_day d
      ON d.channel_id = c.channel_id AND TO_DATE(d.dt) = pd.activity_date
    GROUP BY pd.promotion_id, c.channel_id
),
baseline AS (
    SELECT
        pm.promotion_id,
        c.channel_id,
        COUNT(DISTINCT d.dt) AS baseline_days,
        COALESCE(SUM(d.gmv), 0) AS baseline_gmv,
        COALESCE(SUM(d.merchandise_sales), 0) AS baseline_sales,
        COALESCE(SUM(d.cogs), 0) AS baseline_cogs
    FROM dim_promotion pm
    CROSS JOIN dim_channel c
    INNER JOIN dws_trade_channel_day d
      ON d.channel_id = c.channel_id
     AND TO_DATE(d.dt) BETWEEN DATE_SUB(pm.start_date, 14) AND DATE_SUB(pm.start_date, 1)
     AND TO_DATE(d.dt) >= TO_DATE('${start_date}')
    WHERE pm.start_date <= TO_DATE('${end_date}')
      AND pm.end_date >= TO_DATE('${start_date}')
    GROUP BY pm.promotion_id, c.channel_id
),
discount AS (
    SELECT promotion_id, channel_id, SUM(discount_amount) AS promo_discount
    FROM dws_trade_campaign_day
    GROUP BY promotion_id, channel_id
),
spine AS (
    SELECT pm.promotion_id, pm.promotion_name, pm.promo_type, pm.start_date, pm.end_date,
           c.channel_id, c.channel_name
    FROM dim_promotion pm
    CROSS JOIN dim_channel c
    WHERE pm.start_date <= TO_DATE('${end_date}')
      AND pm.end_date >= TO_DATE('${start_date}')
),
calc AS (
    SELECT
        s.*,
        COALESCE(a.activity_days, 0) AS activity_days,
        COALESCE(a.activity_gmv, 0) AS activity_gmv,
        COALESCE(b.baseline_days, 0) AS baseline_days,
        COALESCE(b.baseline_gmv, 0) AS baseline_gmv,
        COALESCE(d.promo_discount, 0) AS promo_discount,
        COALESCE(b.baseline_sales, 0) AS baseline_sales,
        COALESCE(b.baseline_cogs, 0) AS baseline_cogs
    FROM spine s
    LEFT JOIN activity a ON s.promotion_id = a.promotion_id AND s.channel_id = a.channel_id
    LEFT JOIN baseline b ON s.promotion_id = b.promotion_id AND s.channel_id = b.channel_id
    LEFT JOIN discount d ON s.promotion_id = d.promotion_id AND s.channel_id = d.channel_id
),
metrics AS (
    SELECT
        *,
        activity_gmv / NULLIF(activity_days, 0) AS activity_avg_gmv,
        baseline_gmv / NULLIF(baseline_days, 0) AS baseline_avg_gmv,
        (baseline_sales - baseline_cogs) / NULLIF(baseline_sales, 0) AS baseline_gross_margin_rate
    FROM calc
)
SELECT
    '${end_date}' AS dt,
    promotion_id,
    promotion_name,
    promo_type,
    start_date,
    end_date,
    channel_id,
    channel_name,
    activity_days,
    CAST(activity_gmv AS DECIMAL(18,2)) AS activity_gmv,
    ROUND(activity_avg_gmv, 2) AS activity_avg_gmv,
    baseline_days,
    CAST(baseline_gmv AS DECIMAL(18,2)) AS baseline_gmv,
    ROUND(baseline_avg_gmv, 2) AS baseline_avg_gmv,
    ROUND((activity_avg_gmv - baseline_avg_gmv) / NULLIF(baseline_avg_gmv, 0), 4) AS gmv_lift_rate,
    CAST((activity_avg_gmv - baseline_avg_gmv) * activity_days AS DECIMAL(18,2)) AS incremental_gmv,
    CAST(promo_discount AS DECIMAL(18,2)) AS promo_discount,
    ROUND(baseline_gross_margin_rate, 4) AS baseline_gross_margin_rate,
    CAST((activity_avg_gmv - baseline_avg_gmv) * activity_days * baseline_gross_margin_rate AS DECIMAL(18,2)) AS incremental_gross_profit,
    ROUND(
        ((activity_avg_gmv - baseline_avg_gmv) * activity_days * baseline_gross_margin_rate)
        / NULLIF(promo_discount, 0), 2
    ) AS promotion_roi,
    CURRENT_TIMESTAMP() AS etl_time
FROM metrics
WHERE activity_days > 0 OR baseline_days > 0
