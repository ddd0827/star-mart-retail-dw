WITH sess AS (
    SELECT
        dt, channel_id, sk_channel, channel_type, device_type,
        COUNT(*) AS visit_sessions,
        SUM(is_browse) AS browse_sessions,
        SUM(is_search) AS search_sessions,
        SUM(is_cart) AS cart_sessions,
        SUM(is_checkout) AS checkout_sessions,
        SUM(is_paid) AS pay_sessions,
        SUM(is_member) AS member_sessions
    FROM dwd_online_session
    GROUP BY dt, channel_id, sk_channel, channel_type, device_type
),
ord AS (
    SELECT
        dt, channel_id, device_type,
        COUNT(*) AS online_order_cnt,
        SUM(paid_amount) AS online_gmv,
        COUNT(DISTINCT member_id) AS online_buyer_cnt
    FROM dwd_order_info
    WHERE is_paid = 1 AND channel_type = '线上'
    GROUP BY dt, channel_id, device_type
)
SELECT
    s.dt,
    s.channel_id,
    s.sk_channel,
    s.channel_type,
    s.device_type,
    s.visit_sessions,
    s.browse_sessions,
    s.search_sessions,
    s.cart_sessions,
    s.checkout_sessions,
    s.pay_sessions,
    s.member_sessions,
    COALESCE(o.online_order_cnt, 0) AS online_order_cnt,
    COALESCE(o.online_buyer_cnt, 0) AS online_buyer_cnt,
    CAST(COALESCE(o.online_gmv, 0) AS DECIMAL(16,2)) AS online_gmv,
    ROUND(s.browse_sessions / NULLIF(s.visit_sessions, 0), 4) AS visit_to_browse_rate,
    ROUND(s.cart_sessions / NULLIF(s.visit_sessions, 0), 4) AS visit_to_cart_rate,
    ROUND(s.checkout_sessions / NULLIF(s.cart_sessions, 0), 4) AS cart_to_checkout_rate,
    ROUND(s.pay_sessions / NULLIF(s.checkout_sessions, 0), 4) AS checkout_to_pay_rate,
    ROUND(s.pay_sessions / NULLIF(s.visit_sessions, 0), 4) AS visit_to_pay_rate,
    ROUND(COALESCE(o.online_gmv, 0) / NULLIF(s.pay_sessions, 0), 2) AS online_aov,
    CURRENT_TIMESTAMP() AS etl_time
FROM sess s
LEFT JOIN ord o ON s.dt = o.dt AND s.channel_id = o.channel_id AND s.device_type = o.device_type
