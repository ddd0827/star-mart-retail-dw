"""库存日快照与补货采购模拟。"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

import numpy as np
import pandas as pd


def generate_inventory(
    config,
    master: dict,
    demand: pd.DataFrame,
    returns: pd.DataFrame,
    rng: np.random.Generator,
    writer,
) -> dict:
    stores = master["stores"].reset_index(drop=True)
    locations = stores["store_id"].to_numpy()
    products = master["products"].reset_index(drop=True)
    product_ids = products["product_id"].to_numpy()
    product_cost = products["cost_price"].to_numpy(dtype=float)
    n_loc, n_prod = len(locations), len(products)
    loc_index = {loc: i for i, loc in enumerate(locations)}
    prod_index = {pid: i for i, pid in enumerate(product_ids)}
    n_days = len(config.date_list())
    dates = [d.isoformat() for d in config.date_list()]

    # 铺货矩阵
    assort = np.zeros((n_loc, n_prod), dtype=bool)
    for loc, idx in master["assortment"].items():
        assort[loc_index[loc], idx] = True

    # 需求 / 退货按日聚合
    total_demand = np.zeros((n_loc, n_prod), dtype=np.float64)
    demand_by_day: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for dt, grp in demand.groupby("dt", sort=False):
        li = grp["location_id"].map(loc_index).to_numpy(dtype=int)
        pi = grp["product_id"].map(prod_index).to_numpy(dtype=int)
        qty = grp["qty"].to_numpy(dtype=np.int64)
        demand_by_day[dt] = (li, pi, qty)
        np.add.at(total_demand, (li, pi), qty)
    returns_by_day: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    if len(returns):
        for dt, grp in returns.groupby("dt", sort=False):
            li = grp["location_id"].map(loc_index).to_numpy(dtype=int)
            pi = grp["product_id"].map(prod_index).to_numpy(dtype=int)
            qty = grp["qty"].to_numpy(dtype=np.int64)
            returns_by_day[dt] = (li, pi, qty)

    avg_daily = total_demand / n_days

    # 供应商提前期
    suppliers = master["suppliers"].set_index("supplier_id")["lead_time_days"].to_dict()
    product_supplier = products.set_index("product_id")["supplier_id"].to_dict()
    lead_days = np.array([int(suppliers.get(product_supplier[pid], 3)) for pid in product_ids], dtype=int)

    stock = np.zeros((n_loc, n_prod), dtype=np.int64)
    on_order = np.zeros((n_loc, n_prod), dtype=np.int64)
    safety = np.zeros((n_loc, n_prod), dtype=np.int64)
    target_stock = np.zeros((n_loc, n_prod), dtype=np.int64)
    li_all, pi_all = np.nonzero(assort)
    for li, pi in zip(li_all, pi_all):
        avg = avg_daily[li, pi]
        initial = int(round(avg * rng.uniform(25, 40) + rng.uniform(3, 20)))
        initial = max(5, min(initial, 12000))
        safe = max(2, int(round(avg * rng.uniform(3, 6))) + int(rng.integers(1, 4)))
        target = max(initial, int(round(avg * rng.uniform(18, 28))) + safe, 10)
        stock[li, pi] = initial
        safety[li, pi] = safe
        target_stock[li, pi] = target

    arrivals: dict[int, list[tuple[int, int, int]]] = defaultdict(list)
    purchase_rows: list[dict] = []
    po_seq = 0
    emergency_count = 0
    snapshot_rows = 0
    stockout_cells = 0

    loc_arr = locations
    prod_arr = product_ids
    for day_idx, dt in enumerate(dates):
        begin = stock.copy()
        inbound = np.zeros_like(stock)
        # 到货
        for li, pi, qty in arrivals.get(day_idx, []):
            inbound[li, pi] += qty
            on_order[li, pi] -= qty
        stock += inbound

        sale = np.zeros_like(stock)
        if dt in demand_by_day:
            li, pi, qty = demand_by_day[dt]
            np.add.at(sale, (li, pi), qty)
        ret = np.zeros_like(stock)
        if dt in returns_by_day:
            li, pi, qty = returns_by_day[dt]
            np.add.at(ret, (li, pi), qty)

        stock -= sale
        stock += ret
        # 盘点损耗（极小比例）
        shrink_mask = (rng.random(stock.shape) < 0.0003) & (stock > 0) & assort
        adjustment = np.zeros_like(stock)
        adjustment[shrink_mask] = -1
        stock += adjustment
        # 负库存用紧急补货处理，保证账实一致并记录
        deficit = np.where(stock < 0, -stock, 0)
        if deficit.any():
            li_d, pi_d = np.nonzero(deficit)
            for li, pi in zip(li_d, pi_d):
                q = int(deficit[li, pi])
                stock[li, pi] += q
                inbound[li, pi] += q
                emergency_count += 1
                po_seq += 1
                poid = f"PO{dt.replace('-', '')}{po_seq:06d}"
                purchase_rows.append({
                    "po_id": poid, "location_id": loc_arr[li], "product_id": prod_arr[pi],
                    "supplier_id": product_supplier.get(prod_arr[pi], "SUP01"), "dt": dt,
                    "order_date": dt, "expected_arrival_date": dt, "arrival_date": dt,
                    "quantity": q, "unit_cost": round(float(product_cost[pi]), 2),
                    "total_amount": round(q * float(product_cost[pi]), 2),
                    "po_status": "紧急补货", "update_time": f"{dt} 23:00:00",
                })

        # 快照（仅铺货库位×SKU）
        end = stock
        snap = pd.DataFrame({
            "dt": dt,
            "location_id": loc_arr[li_all],
            "product_id": prod_arr[pi_all],
            "begin_qty": begin[li_all, pi_all],
            "purchase_in_qty": inbound[li_all, pi_all],
            "sale_qty": sale[li_all, pi_all],
            "return_qty": ret[li_all, pi_all],
            "adjustment_qty": adjustment[li_all, pi_all],
            "end_qty": end[li_all, pi_all],
            "safety_stock": safety[li_all, pi_all],
            "cost_price": np.round(product_cost[pi_all], 2),
            "stock_value": np.round(end[li_all, pi_all] * product_cost[pi_all], 2),
            "update_time": f"{dt} 23:59:59",
        })
        stockout_cells += int((snap["end_qty"] == 0).sum())
        snapshot_rows += len(snap)
        writer.write_daily("inventory_snapshot", snap, dt)

        # 补货：低于安全库存且未在途时触发
        reorder_mask = assort & (stock + on_order < safety)
        li_r, pi_r = np.nonzero(reorder_mask)
        today = date.fromisoformat(dt)
        for li, pi in zip(li_r, pi_r):
            qty = int(target_stock[li, pi] - stock[li, pi] - on_order[li, pi])
            if qty <= 0:
                continue
            lead = int(lead_days[pi])
            expected = today + timedelta(days=lead)
            if expected > config.end_date:
                status = "在途"
                arrival_date = None
            else:
                status = "已入库"
                arrival_date = expected.isoformat()
                arrivals[day_idx + lead].append((li, pi, qty))
            on_order[li, pi] += qty
            po_seq += 1
            poid = f"PO{dt.replace('-', '')}{po_seq:06d}"
            purchase_rows.append({
                "po_id": poid, "location_id": loc_arr[li], "product_id": prod_arr[pi],
                "supplier_id": product_supplier.get(prod_arr[pi], "SUP01"), "dt": dt,
                "order_date": dt, "expected_arrival_date": expected.isoformat(),
                "arrival_date": arrival_date, "quantity": qty,
                "unit_cost": round(float(product_cost[pi]), 2),
                "total_amount": round(qty * float(product_cost[pi]), 2),
                "po_status": status, "update_time": f"{dt} 23:00:00",
            })

        if purchase_rows:
            po_df = pd.DataFrame(purchase_rows)
            po_df = po_df[po_df["dt"] == dt]
            if len(po_df):
                writer.write_daily("purchase_order", po_df, dt)
            purchase_rows = [r for r in purchase_rows if r["dt"] != dt]

    stats = {
        "inventory_snapshot_rows": snapshot_rows,
        "stockout_cell_days": stockout_cells,
        "stockout_rate": round(stockout_cells / max(snapshot_rows, 1), 4),
        "emergency_replenishments": emergency_count,
    }
    return stats
