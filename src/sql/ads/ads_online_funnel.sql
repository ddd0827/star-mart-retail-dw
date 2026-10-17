WITH f AS (
    SELECT
        dt,
        channel_id,
        sk_channel,
        channel_type,
        SUM(visit_sessions) AS visit_sessions,
        SUM(browse_sessions) AS browse_sessions,
        SUM(search_sessions) AS search_sessions,
        SUM(cart_sessions) AS cart_sessions,
        SUM(checkout_sessions) AS checkout_sessions,
        SUM(pay_sessions) AS pay_sessions,
        SUM(member_sessions) AS member_sessions,
        SUM(online_order_cnt) AS online_order_cnt,
        SUM(online_buyer_cnt) AS online_buyer_cnt,
        SUM(online_gmv) AS online_gmv
    FROM dws_online_funnel_day
    GROUP BY dt, channel_id, sk_channel, channel_type
)
SELECT
    dt,
    channel_id,
    sk_channel,
    channel_type,
    visit_sessions,
    browse_sessions,
    search_sessions,
    cart_sessions,
    checkout_sessions,
    pay_sessions,
    member_sessions,
    online_order_cnt,
    online_buyer_cnt,
    CAST(online_gmv AS DECIMAL(18,2)) AS online_gmv,
    ROUND(browse_sessions / NULLIF(visit_sessions, 0), 4) AS visit_to_browse_rate,
    ROUND(cart_sessions / NULLIF(visit_sessions, 0), 4) AS visit_to_cart_rate,
    ROUND(checkout_sessions / NULLIF(cart_sessions, 0), 4) AS cart_to_checkout_rate,
    ROUND(pay_sessions / NULLIF(checkout_sessions, 0), 4) AS checkout_to_pay_rate,
    ROUND(pay_sessions / NULLIF(visit_sessions, 0), 4) AS visit_to_pay_rate,
    ROUND(online_gmv / NULLIF(pay_sessions, 0), 2) AS online_aov,
    CURRENT_TIMESTAMP() AS etl_time
FROM f
