WITH e AS (
    SELECT * FROM (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY update_time DESC, event_time DESC) AS rn
        FROM ods_behavior_event
        WHERE event_id IS NOT NULL
          AND event_type IN ('页面浏览', '搜索', '商品曝光', '商品点击', '加入购物车', '进入结算页', '支付成功')
    ) t WHERE rn = 1
),
ec AS (
    SELECT *,
           COALESCE(
               TRY_TO_TIMESTAMP(TRIM(event_time), 'yyyy-MM-dd HH:mm:ss'),
               TRY_TO_TIMESTAMP(TRIM(event_time), 'yyyy/MM/dd HH:mm:ss')
           ) AS event_ts
    FROM e
)
SELECT
    TRIM(ec.event_id) AS event_id,
    TRIM(ec.session_id) AS session_id,
    ec.dt,
    TO_DATE(ec.dt) AS event_date,
    ec.event_ts AS event_time,
    HOUR(ec.event_ts) AS event_hour,
    CAST(DATE_FORMAT(ec.event_ts, 'yyyyMMdd') AS INT) AS sk_date,
    TRIM(ec.member_id) AS member_id,
    COALESCE(m.sk_member, -1) AS sk_member,
    CASE WHEN ec.member_id IS NOT NULL AND m.sk_member IS NOT NULL THEN 1 ELSE 0 END AS is_member,
    COALESCE(TRIM(ec.user_type), '游客') AS user_type,
    TRIM(ec.channel_id) AS channel_id,
    COALESCE(c.sk_channel, -1) AS sk_channel,
    COALESCE(c.channel_type, '未知') AS channel_type,
    COALESCE(TRIM(ec.device_type), '未知') AS device_type,
    TRIM(ec.event_type) AS event_type,
    COALESCE(TRIM(ec.page_type), '未知') AS page_type,
    TRIM(ec.product_id) AS product_id,
    COALESCE(p.sk_product, -1) AS sk_product,
    COALESCE(p.category_id, '未知') AS category_id,
    COALESCE(p.top_category_id, '未知') AS top_category_id,
    TRIM(ec.search_keyword) AS search_keyword,
    TRIM(ec.order_id) AS order_id,
    TRIM(ec.promotion_id) AS promotion_id,
    COALESCE(pm.sk_promotion, -1) AS sk_promotion,
    CURRENT_TIMESTAMP() AS etl_time
FROM ec
LEFT JOIN dim_member m ON TRIM(ec.member_id) = m.member_id
LEFT JOIN dim_product p ON TRIM(ec.product_id) = p.product_id
LEFT JOIN dim_channel c ON TRIM(ec.channel_id) = c.channel_id
LEFT JOIN dim_promotion pm ON TRIM(ec.promotion_id) = pm.promotion_id
WHERE ec.event_ts IS NOT NULL
