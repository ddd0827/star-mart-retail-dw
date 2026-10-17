WITH s AS (
    SELECT * FROM (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY session_id ORDER BY update_time DESC) AS rn
        FROM ods_online_session
        WHERE session_id IS NOT NULL
    ) t WHERE rn = 1
),
sc AS (
    SELECT *,
           COALESCE(
               TRY_TO_TIMESTAMP(TRIM(session_start_time), 'yyyy-MM-dd HH:mm:ss'),
               TRY_TO_TIMESTAMP(TRIM(session_start_time), 'yyyy/MM/dd HH:mm:ss')
           ) AS start_ts
    FROM s
),
flags AS (
    SELECT *,
           GREATEST(CAST(COALESCE(is_browse, 0) AS INT), CAST(COALESCE(is_search, 0) AS INT),
                    CAST(COALESCE(is_cart, 0) AS INT), CAST(COALESCE(is_checkout, 0) AS INT),
                    CAST(COALESCE(is_paid, 0) AS INT)) AS f_browse,
           GREATEST(CAST(COALESCE(is_cart, 0) AS INT), CAST(COALESCE(is_checkout, 0) AS INT),
                    CAST(COALESCE(is_paid, 0) AS INT)) AS f_cart,
           GREATEST(CAST(COALESCE(is_checkout, 0) AS INT), CAST(COALESCE(is_paid, 0) AS INT)) AS f_checkout,
           CAST(COALESCE(is_paid, 0) AS INT) AS f_paid
    FROM sc
)
SELECT
    TRIM(sc.session_id) AS session_id,
    sc.dt,
    TO_DATE(sc.dt) AS session_date,
    sc.start_ts AS session_start_time,
    HOUR(sc.start_ts) AS start_hour,
    CAST(DATE_FORMAT(sc.start_ts, 'yyyyMMdd') AS INT) AS sk_date,
    TRIM(sc.member_id) AS member_id,
    COALESCE(m.sk_member, -1) AS sk_member,
    CASE WHEN sc.member_id IS NOT NULL AND m.sk_member IS NOT NULL THEN 1 ELSE 0 END AS is_member,
    TRIM(sc.visitor_id) AS visitor_id,
    TRIM(sc.channel_id) AS channel_id,
    COALESCE(c.sk_channel, -1) AS sk_channel,
    COALESCE(c.channel_type, '未知') AS channel_type,
    COALESCE(TRIM(sc.device_type), '未知') AS device_type,
    TRIM(sc.promotion_id) AS promotion_id,
    COALESCE(pm.sk_promotion, -1) AS sk_promotion,
    COALESCE(TRIM(sc.entry_page), '未知') AS entry_page,
    sc.f_browse AS is_browse,
    CAST(COALESCE(sc.is_search, 0) AS INT) AS is_search,
    sc.f_cart AS is_cart,
    sc.f_checkout AS is_checkout,
    sc.f_paid AS is_paid,
    TRIM(sc.order_id) AS order_id,
    CURRENT_TIMESTAMP() AS etl_time
FROM flags sc
LEFT JOIN dim_member m ON TRIM(sc.member_id) = m.member_id
LEFT JOIN dim_channel c ON TRIM(sc.channel_id) = c.channel_id
LEFT JOIN dim_promotion pm ON TRIM(sc.promotion_id) = pm.promotion_id
WHERE sc.start_ts IS NOT NULL
