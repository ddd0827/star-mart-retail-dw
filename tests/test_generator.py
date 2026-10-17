import numpy as np
import pandas as pd

from src.common.config import Config
from src.generator.master_data import build_master
from src.generator.orders import _build_targets


def _cfg() -> Config:
    return Config(overrides={
        "dates": {"start": "2026-04-20", "end": "2026-10-16"},
        "scale": {"members": 1000, "skus": 200},
    })


def test_master_data_shape_and_keys():
    cfg = _cfg()
    master = build_master(cfg, np.random.default_rng(42))

    assert len(master["stores"]) == 25
    assert int(master["stores"]["is_offline"].sum()) == 24
    assert len(master["products"]) == 200
    assert len(master["members"]) == 1000
    assert len(master["categories"]) == 52
    assert len(master["brands"]) == 80
    assert master["products"]["product_id"].is_unique
    assert master["members"]["member_id"].is_unique
    assert (master["products"]["list_price"] > 0).all()
    assert (master["products"]["cost_price"] > 0).all()


def test_assortment_and_sampling_weights():
    cfg = _cfg()
    master = build_master(cfg, np.random.default_rng(7))
    assert set(master["assortment"].keys()) == set(master["stores"]["store_id"])
    for loc, indices in master["assortment"].items():
        assert len(indices) > 0
        assert indices.max() < len(master["products"])
        weights = master["sampling_weights"][(loc, 5)]
        assert len(weights) == len(indices)
        assert abs(float(weights.sum()) - 1.0) < 1e-6


def test_targets_extrapolate_partial_month():
    cfg = _cfg().with_overrides({"dates": {"start": "2026-04-20", "end": "2026-05-31"}})
    orders = pd.DataFrame({
        "store_id": ["S001", "S001", "S001"],
        "dt": ["2026-04-20", "2026-04-21", "2026-05-01"],
        "paid_amount": [1000.0, 2000.0, 3000.0],
        "_channel_type": ["线下", "线下", "线下"],
    })
    targets = _build_targets(cfg, orders, np.random.default_rng(1))
    assert set(targets["target_month"]) == {"2026-04", "2026-05"}
    april = targets[targets["target_month"] == "2026-04"].iloc[0]
    may = targets[targets["target_month"] == "2026-05"].iloc[0]
    # 4 月数据窗口覆盖 11 天（4/20–4/30），目标按全月 30 天外推
    assert 3000 / 11 * 30 * 0.90 <= april["target_amount"] <= 3000 / 11 * 30 * 1.12
    # 5 月窗口覆盖整月 31 天，目标不外推
    assert 3000 * 0.90 <= may["target_amount"] <= 3000 * 1.12
