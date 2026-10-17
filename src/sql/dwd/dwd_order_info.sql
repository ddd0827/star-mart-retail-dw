WITH o AS (
    SELECT * FROM (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY update_time DESC, order_time DESC) AS rn
        FROM ods_order_info
        WHERE order_id IS NOT NULL
    ) t WHERE rn = 1
),
oc AS (
    SELECT *,
           COALESCE(
               TRY_TO_TIMESTAMP(TRIM(order_time), 'yyyy-MM-dd HH:mm:ss'),
               TRY_TO_TIMESTAMP(TRIM(order_time), 'yyyy/MM/dd HH:mm:ss')
           ) AS order_ts
    FROM o
),
pay_dedup AS (
    SELECT * FROM (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY payment_id ORDER BY update_time DESC) AS rn
        FROM ods_payment_info
        WHERE payment_id IS NOT NULL
    ) t WHERE rn = 1
),
pay_agg AS (
    SELECT order_id,
           SUM(CASE WHEN TRIM(payment_status) = '成功' AND CAST(pay_amount AS DECIMAL(14,2)) > 0
                    THEN CAST(pay_amount AS DECIMAL(14,2)) ELSE 0 END) AS success_pay_amount,
           SUM(CASE WHEN TRIM(payment_status) = '成功' AND CAST(pay_amount AS DECIMAL(14,2)) > 0
                    THEN 1 ELSE 0 END) AS success_cnt
    FROM pay_dedup
    GROUP BY order_id
)
SELECT
    TRIM(o.order_id) AS order_id,
    o.order_ts AS order_time,
    DATE_FORMAT(o.order_ts, 'yyyy-MM-dd') AS dt,
    TO_DATE(o.order_ts) AS order_date,
    HOUR(o.order_ts) AS order_hour,
    WEEKDAY(TO_DATE(o.order_ts)) + 1 AS order_weekday,
    CAST(DATE_FORMAT(o.order_ts, 'yyyyMMdd') AS INT) AS sk_date,
    COALESCE(TRIM(o.store_id), '__UNKNOWN__') AS store_id,
    COALESCE(s.sk_store, -1) AS sk_store,
    COALESCE(s.store_name, '未知门店') AS store_name,
    COALESCE(s.store_type, '未知') AS store_type,
    COALESCE(s.city_id, '未知') AS city_id,
    COALESCE(s.city_name, '未知') AS city_name,
    COALESCE(s.region_id, '未知') AS region_id,
    COALESCE(s.region_name, '未知') AS region_name,
    COALESCE(s.is_offline, 0) AS is_offline,
    COALESCE(TRIM(o.channel_id), '__UNKNOWN__') AS channel_id,
    COALESCE(c.sk_channel, -1) AS sk_channel,
    COALESCE(c.channel_name, '未知渠道') AS channel_name,
    COALESCE(c.channel_type, '未知') AS channel_type,
    TRIM(o.member_id) AS member_id,
    COALESCE(m.sk_member, -1) AS sk_member,
    CASE WHEN o.member_id IS NOT NULL AND m.sk_member IS NOT NULL THEN 1 ELSE 0 END AS is_member,
    COALESCE(TRIM(o.device_type), '未知') AS device_type,
    TRIM(o.online_session_id) AS online_session_id,
    TRIM(o.promotion_id) AS promotion_id,
    COALESCE(pm.sk_promotion, -1) AS sk_promotion,
    TRIM(o.order_status) AS order_status,
    CAST(COALESCE(o.total_amount, 0) AS DECIMAL(14,2)) AS total_amount,
    CAST(COALESCE(o.discount_amount, 0) AS DECIMAL(14,2)) AS discount_amount,
    CAST(COALESCE(o.shipping_fee, 0) AS DECIMAL(10,2)) AS shipping_fee,
    CAST(COALESCE(o.payable_amount, 0) AS DECIMAL(14,2)) AS payable_amount,
    CASE WHEN COALESCE(pa.success_cnt, 0) > 0 AND TRIM(o.order_status) <> '已取消'
         THEN CAST(COALESCE(o.paid_amount, pa.success_pay_amount, 0) AS DECIMAL(14,2))
         ELSE CAST(0 AS DECIMAL(14,2)) END AS paid_amount,
    CASE WHEN COALESCE(pa.success_cnt, 0) > 0 AND TRIM(o.order_status) <> '已取消' THEN 1 ELSE 0 END AS is_paid,
    CURRENT_TIMESTAMP() AS etl_time
FROM oc o
LEFT JOIN pay_agg pa ON TRIM(o.order_id) = pa.order_id
LEFT JOIN dim_store s ON COALESCE(TRIM(o.store_id), '__UNKNOWN__') = s.store_id
LEFT JOIN dim_channel c ON COALESCE(TRIM(o.channel_id), '__UNKNOWN__') = c.channel_id
LEFT JOIN dim_member m ON TRIM(o.member_id) = m.member_id
LEFT JOIN dim_promotion pm ON TRIM(o.promotion_id) = pm.promotion_id
WHERE o.order_ts IS NOT NULL
