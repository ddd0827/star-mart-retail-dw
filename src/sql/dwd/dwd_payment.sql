WITH p AS (
    SELECT * FROM (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY payment_id ORDER BY update_time DESC) AS rn
        FROM ods_payment_info
        WHERE payment_id IS NOT NULL
    ) t WHERE rn = 1
),
pc AS (
    SELECT *,
           COALESCE(
               TRY_TO_TIMESTAMP(TRIM(pay_time), 'yyyy-MM-dd HH:mm:ss'),
               TRY_TO_TIMESTAMP(TRIM(pay_time), 'yyyy/MM/dd HH:mm:ss')
           ) AS pay_ts
    FROM p
)
SELECT
    TRIM(pc.payment_id) AS payment_id,
    TRIM(pc.order_id) AS order_id,
    DATE_FORMAT(pc.pay_ts, 'yyyy-MM-dd') AS dt,
    pc.pay_ts AS pay_time,
    TRIM(pc.pay_channel) AS pay_channel,
    CAST(COALESCE(pc.pay_amount, 0) AS DECIMAL(14,2)) AS pay_amount,
    TRIM(pc.payment_status) AS payment_status,
    CASE WHEN TRIM(pc.payment_status) = '成功' AND CAST(COALESCE(pc.pay_amount, 0) AS DECIMAL(14,2)) > 0
         THEN 1 ELSE 0 END AS is_success,
    TRIM(pc.transaction_no) AS transaction_no,
    o.store_id,
    o.sk_store,
    o.store_type,
    o.city_id,
    o.region_id,
    o.is_offline,
    o.channel_id,
    o.sk_channel,
    o.channel_type,
    o.member_id,
    o.sk_member,
    o.is_member,
    o.promotion_id,
    o.sk_promotion,
    CURRENT_TIMESTAMP() AS etl_time
FROM pc
INNER JOIN dwd_order_info o ON TRIM(pc.order_id) = o.order_id
WHERE pc.pay_ts IS NOT NULL
