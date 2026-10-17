"""模拟源系统 / ODS 表的显式 Schema。"""
from __future__ import annotations

from pyspark.sql.types import (
    DecimalType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)

S = StringType
I = IntegerType
M = lambda p=14, s=2: DecimalType(p, s)  # noqa: E731

RAW_SCHEMAS: dict[str, StructType] = {
    "store_info": StructType([
        StructField("store_id", S()), StructField("store_name", S()),
        StructField("store_type", S()), StructField("city_id", S()),
        StructField("city_name", S()), StructField("province", S()),
        StructField("region_id", S()), StructField("region_name", S()),
        StructField("address", S()), StructField("open_date", S()),
        StructField("area_sqm", I()), StructField("manager_name", S()),
        StructField("is_offline", I()), StructField("status", S()),
        StructField("update_time", S()),
    ]),
    "supplier_info": StructType([
        StructField("supplier_id", S()), StructField("supplier_name", S()),
        StructField("main_category", S()), StructField("province", S()),
        StructField("contact_phone", S()), StructField("lead_time_days", I()),
        StructField("status", S()), StructField("update_time", S()),
    ]),
    "brand_info": StructType([
        StructField("brand_id", S()), StructField("brand_name", S()),
        StructField("brand_country", S()), StructField("status", S()),
        StructField("update_time", S()),
    ]),
    "category_info": StructType([
        StructField("category_id", S()), StructField("category_name", S()),
        StructField("parent_id", S()), StructField("level", I()),
        StructField("category_path", S()), StructField("season_profile", S()),
        StructField("perishable", I()), StructField("update_time", S()),
    ]),
    "product_info": StructType([
        StructField("product_id", S()), StructField("product_name", S()),
        StructField("category_id", S()), StructField("brand_id", S()),
        StructField("supplier_id", S()), StructField("list_price", M(12)),
        StructField("cost_price", M(12)), StructField("unit", S()),
        StructField("spec", S()), StructField("shelf_life_days", I()),
        StructField("launch_date", S()), StructField("status", S()),
        StructField("update_time", S()),
    ]),
    "member_info": StructType([
        StructField("member_id", S()), StructField("phone_masked", S()),
        StructField("gender", S()), StructField("birth_date", S()),
        StructField("age_group", S()), StructField("city_id", S()),
        StructField("register_date", S()), StructField("register_channel", S()),
        StructField("member_level", S()), StructField("points", I()),
        StructField("member_status", S()), StructField("update_time", S()),
    ]),
    "promotion_info": StructType([
        StructField("promotion_id", S()), StructField("promotion_name", S()),
        StructField("promo_type", S()), StructField("channel_scope", S()),
        StructField("start_date", S()), StructField("end_date", S()),
        StructField("discount_rate", M(6, 4)), StructField("min_amount", M(12)),
        StructField("status", S()), StructField("update_time", S()),
    ]),
    "store_sales_target": StructType([
        StructField("target_id", S()), StructField("store_id", S()),
        StructField("target_month", S()), StructField("target_amount", M(14)),
        StructField("update_time", S()),
    ]),
    "channel_info": StructType([
        StructField("channel_id", S()), StructField("channel_name", S()),
        StructField("channel_type", S()), StructField("update_time", S()),
    ]),
    "store_traffic_daily": StructType([
        StructField("dt", S()), StructField("store_id", S()),
        StructField("traffic_in", I()), StructField("update_time", S()),
    ]),
    "order_info": StructType([
        StructField("order_id", S()), StructField("order_time", S()),
        StructField("dt", S()), StructField("store_id", S()),
        StructField("channel_id", S()), StructField("member_id", S()),
        StructField("device_type", S()), StructField("online_session_id", S()),
        StructField("promotion_id", S()), StructField("order_status", S()),
        StructField("total_amount", M(14)), StructField("discount_amount", M(14)),
        StructField("shipping_fee", M(10)), StructField("payable_amount", M(14)),
        StructField("paid_amount", M(14)), StructField("create_time", S()),
        StructField("update_time", S()),
    ]),
    "order_detail": StructType([
        StructField("order_id", S()), StructField("line_id", S()),
        StructField("product_id", S()), StructField("quantity", I()),
        StructField("list_price", M(12)), StructField("sale_price", M(12)),
        StructField("discount_amount", M(14)), StructField("line_amount", M(14)),
        StructField("cost_amount", M(14)), StructField("dt", S()),
        StructField("update_time", S()),
    ]),
    "payment_info": StructType([
        StructField("payment_id", S()), StructField("order_id", S()),
        StructField("dt", S()), StructField("pay_time", S()),
        StructField("pay_channel", S()), StructField("pay_amount", M(14)),
        StructField("payment_status", S()), StructField("transaction_no", S()),
        StructField("update_time", S()),
    ]),
    "refund_info": StructType([
        StructField("refund_id", S()), StructField("order_id", S()),
        StructField("line_id", S()), StructField("dt", S()),
        StructField("refund_time", S()), StructField("refund_amount", M(14)),
        StructField("refund_reason", S()), StructField("refund_type", S()),
        StructField("refund_channel", S()), StructField("refund_status", S()),
        StructField("return_qty", I()), StructField("update_time", S()),
    ]),
    "online_session": StructType([
        StructField("session_id", S()), StructField("dt", S()),
        StructField("session_start_time", S()), StructField("member_id", S()),
        StructField("visitor_id", S()), StructField("channel_id", S()),
        StructField("device_type", S()), StructField("promotion_id", S()),
        StructField("entry_page", S()), StructField("is_browse", I()),
        StructField("is_search", I()), StructField("is_cart", I()),
        StructField("is_checkout", I()), StructField("is_paid", I()),
        StructField("order_id", S()), StructField("update_time", S()),
    ]),
    "behavior_event": StructType([
        StructField("event_id", S()), StructField("session_id", S()),
        StructField("dt", S()), StructField("event_time", S()),
        StructField("member_id", S()), StructField("user_type", S()),
        StructField("channel_id", S()), StructField("device_type", S()),
        StructField("event_type", S()), StructField("page_type", S()),
        StructField("product_id", S()), StructField("search_keyword", S()),
        StructField("order_id", S()), StructField("promotion_id", S()),
        StructField("update_time", S()),
    ]),
    "inventory_snapshot": StructType([
        StructField("dt", S()), StructField("location_id", S()),
        StructField("product_id", S()), StructField("begin_qty", I()),
        StructField("purchase_in_qty", I()), StructField("sale_qty", I()),
        StructField("return_qty", I()), StructField("adjustment_qty", I()),
        StructField("end_qty", I()), StructField("safety_stock", I()),
        StructField("cost_price", M(12)), StructField("stock_value", M(14)),
        StructField("update_time", S()),
    ]),
    "purchase_order": StructType([
        StructField("po_id", S()), StructField("location_id", S()),
        StructField("product_id", S()), StructField("supplier_id", S()),
        StructField("dt", S()), StructField("order_date", S()),
        StructField("expected_arrival_date", S()),
        StructField("arrival_date", S()), StructField("quantity", I()),
        StructField("unit_cost", M(12)), StructField("total_amount", M(14)),
        StructField("po_status", S()), StructField("update_time", S()),
    ]),
}

# 源系统/ODS 中按 dt 分区的事实表
RAW_FACT_TABLES = [
    "store_traffic_daily",
    "order_info",
    "order_detail",
    "payment_info",
    "refund_info",
    "online_session",
    "behavior_event",
    "inventory_snapshot",
    "purchase_order",
]

RAW_DIM_TABLES = [
    "store_info",
    "supplier_info",
    "brand_info",
    "category_info",
    "product_info",
    "member_info",
    "promotion_info",
    "store_sales_target",
    "channel_info",
]
