WITH refunds AS (
    SELECT member_id, SUM(refund_amount) AS refund_amount
    FROM dwd_refund
    WHERE refund_status = '已完成' AND member_id IS NOT NULL
    GROUP BY member_id
),
rfm_base AS (
    SELECT
        o.member_id,
        MAX(o.sk_member) AS sk_member,
        DATEDIFF(TO_DATE('${end_date}'), MAX(o.order_date)) AS recency_days,
        COUNT(*) AS frequency,
        GREATEST(SUM(o.paid_amount) - COALESCE(MAX(r.refund_amount), 0), 0) AS monetary,
        MAX(o.order_date) AS last_order_date
    FROM dwd_order_info o
    LEFT JOIN refunds r ON o.member_id = r.member_id
    WHERE o.is_paid = 1 AND o.is_member = 1 AND o.member_id IS NOT NULL
    GROUP BY o.member_id
),
scored AS (
    SELECT
        *,
        NTILE(5) OVER (ORDER BY recency_days DESC) AS r_score,
        NTILE(5) OVER (ORDER BY frequency ASC) AS f_score,
        NTILE(5) OVER (ORDER BY monetary ASC) AS m_score
    FROM rfm_base
)
SELECT
    '${end_date}' AS dt,
    member_id,
    sk_member,
    recency_days,
    frequency,
    CAST(monetary AS DECIMAL(18,2)) AS monetary,
    last_order_date,
    r_score,
    f_score,
    m_score,
    CONCAT(r_score, f_score, m_score) AS rfm_score,
    CASE
        WHEN r_score >= 4 AND f_score >= 4 AND m_score >= 4 THEN '重要价值客户'
        WHEN r_score < 4 AND f_score >= 4 AND m_score >= 4 THEN '重要保持客户'
        WHEN r_score >= 4 AND f_score < 4 AND m_score >= 4 THEN '重要发展客户'
        WHEN r_score < 4 AND f_score < 4 AND m_score >= 4 THEN '重要挽留客户'
        WHEN r_score >= 4 AND f_score >= 4 AND m_score < 4 THEN '一般价值客户'
        WHEN r_score < 4 AND f_score >= 4 AND m_score < 4 THEN '一般保持客户'
        WHEN r_score >= 4 AND f_score < 4 AND m_score < 4 THEN '一般发展客户'
        ELSE '一般挽留客户'
    END AS rfm_segment,
    CASE
        WHEN r_score >= 4 AND f_score >= 4 AND m_score >= 4 THEN '重点维护，提供专属权益与优先服务'
        WHEN r_score < 4 AND f_score >= 4 AND m_score >= 4 THEN '高价值流失预警，安排专属客服召回'
        WHEN r_score >= 4 AND f_score < 4 AND m_score >= 4 THEN '提升购买频次，做品类交叉销售'
        WHEN r_score < 4 AND f_score < 4 AND m_score >= 4 THEN '定向优惠与一对一挽留'
        WHEN r_score >= 4 AND f_score >= 4 AND m_score < 4 THEN '保持互动，推荐高毛利商品'
        WHEN r_score < 4 AND f_score >= 4 AND m_score < 4 THEN '会员日触达，恢复活跃'
        WHEN r_score >= 4 AND f_score < 4 AND m_score < 4 THEN '培育首复购，发放新人券'
        ELSE '低成本批量触达，控制营销成本'
    END AS suggested_action,
    CURRENT_TIMESTAMP() AS etl_time
FROM scored
