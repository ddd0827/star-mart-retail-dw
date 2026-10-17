# 数仓架构设计

## 1. 总体架构

```
                         ┌─────────────────────────────────────────────┐
                         │          模拟业务源系统（raw CSV）           │
                         │ 门店/商品/会员/供应商/活动/订单/支付/退款   │
                         │ 客流/线上会话/行为日志/库存/采购            │
                         └──────────────────┬──────────────────────────┘
                                            │ PySpark CSV 装载 + Schema
                                            ▼
                         ┌─────────────────────────────────────────────┐
                         │ ODS 原始数据层（Parquet，按 dt 分区）        │
                         └──────────────────┬──────────────────────────┘
                                            │ 清洗 / 去重 / 类型修复 / 维度补全
                                            ▼
        ┌───────────────────────────────────────────────────────────────────┐
        │ DIM 维度层：日期、门店、商品、品类、品牌、会员、供应商、活动、渠道 │
        │ DWD 明细事实：订单、订单行、支付、退款、库存、客流、会话、行为、采购 │
        └──────────────────────────────────┬────────────────────────────────┘
                                            │ Spark SQL 主题聚合
                                            ▼
        ┌───────────────────────────────────────────────────────────────────┐
        │ DWS 汇总层：门店日、渠道日、SKU日、会员日、线上漏斗日、库存SKU日、活动日 │
        └──────────────────────────────────┬────────────────────────────────┘
                                            │ Spark SQL 指标计算
                                            ▼
        ┌───────────────────────────────────────────────────────────────────┐
        │ ADS 应用层（10 张）：经营总览、门店达成、品类结构、商品TopN、RFM、   │
        │ 留存、复购、库存周转、线上漏斗、促销效果                           │
        └──────────────────────────────────┬────────────────────────────────┘
                                            │ CSV / JSON 导出
                                            ▼
                         ┌─────────────────────────────────────────────┐
                         │ 质量报告 / 运行日志 / 静态 HTML 经营看板     │
                         └─────────────────────────────────────────────┘
```

## 2. 技术栈

| 层次 | 技术 |
|---|---|
| 计算引擎 | Apache Spark 3.5.9（PySpark，local 模式） |
| SQL | Spark SQL |
| 存储 | Parquet（Snappy 压缩），Hive 风格 `dt=YYYY-MM-DD` 分区 |
| 数据模拟 | Python 3.11 + NumPy + pandas |
| 配置 | YAML |
| 看板 | Jinja2 + ECharts（本地 JS，离线打开） |
| 测试 | pytest |
| 运行环境 | Windows 11 + 项目内 JDK 17 + winutils |

## 3. 数据分层

### 3.1 ODS

- 保持源系统字段和明细，只做 CSV → Parquet 与类型读取。
- 事实表按 `dt` 分区；维表为全量快照。
- 保留脏数据，便于演示清洗过程。
- 代码：`src/etl/ods.py`；Schema：`src/common/schemas.py`。

### 3.2 DIM

- 清洗、去重、去空格、负价格修复。
- 代理键：`xxhash64(自然键)`，未知维度统一映射 `-1`。
- 日期维覆盖 2025–2026，包含节假日、周末、周几等属性。
- 价格异常（负值）使用绝对值修复；无法修复的记录被过滤并在质量报告中体现。
- 代码：`src/etl/dim.py`。

### 3.3 DWD

- 事实粒度：
  - `dwd_order_info`：订单头粒度。
  - `dwd_order_detail`：订单行粒度。
  - `dwd_payment`：支付尝试粒度（成功与失败均保留）。
  - `dwd_refund`：退款行粒度。
  - `dwd_inventory_snapshot`：日 × 库位 × SKU。
  - `dwd_online_session`：会话粒度。
  - `dwd_behavior_event`：行为事件粒度。
  - `dwd_store_traffic`：日 × 门店。
  - `dwd_purchase_order`：采购单行粒度。
- 清洗：主键去重、混合时间格式兼容、非法数量过滤、未知会员映射、空门店映射为 `__UNKNOWN__`。
- 维度补全：门店/渠道/商品/会员/活动代理键与业务属性。
- 代码：`src/etl/dwd.py` + `src/sql/dwd/*.sql`。

### 3.4 DWS

| 表 | 粒度 | 主要用途 |
|---|---|---|
| `dws_trade_store_day` | dt × 门店 | 门店经营、目标达成、转化 |
| `dws_trade_channel_day` | dt × 渠道 | 渠道结构、会员/线上占比 |
| `dws_trade_sku_day` | dt × SKU × 渠道 | 商品/品类分析、毛利、退款 |
| `dws_member_day` | dt × 会员 | 会员消费、RFM/留存/复购输入 |
| `dws_online_funnel_day` | dt × 渠道 × 设备 | 线上转化漏斗 |
| `dws_inventory_sku_day` | dt × 库位 × SKU | 库存周转、缺货、售罄 |
| `dws_trade_campaign_day` | dt × 活动 × 渠道 | 活动销售与让利 |

代码：`src/etl/dws.py` + `src/sql/dws/*.sql`。

### 3.5 ADS

| 表 | 粒度 | 主要内容 |
|---|---|---|
| `ads_operation_overview` | 日 | GMV、净销售额、订单、客单价、会员/线上占比、退款率、毛利、7日均、环比、MTD |
| `ads_store_performance` | 日 × 门店 | 门店 GMV、客流转化、目标达成、排名 |
| `ads_category_structure` | 日 × 品类 | 一级/二级品类销售额、占比、折扣、退款、毛利 |
| `ads_product_topn` | 快照 × SKU | 近30天商品销售、毛利、退款、全站/品类排名 |
| `ads_member_rfm` | 快照 × 会员 | R/F/M 原始值、1–5 分、8 大客群、建议动作 |
| `ads_member_retention` | 快照 × 首购月 × 月偏移 | 会员留存 cohort |
| `ads_member_repurchase` | 月 | 月度复购率、30日复购 |
| `ads_inventory_turnover` | 日 × 库位 | 30日库存周转、缺货率、售罄率 |
| `ads_online_funnel` | 日 × 渠道 | 访问→支付漏斗、转化率、线上 GMV |
| `ads_promotion_effect` | 快照 × 活动 × 渠道 | 活动日均、基线、增量、让利、ROI（观察性） |

代码：`src/etl/ads.py` + `src/sql/ads/*.sql`。

## 4. 存储与分区

```
data/
├── raw/<table>/dt=YYYY-MM-DD/*.csv        # 模拟源系统
└── warehouse/
    ├── ods/<table>/dt=YYYY-MM-DD/          # 事实表分区
    ├── dim/<table>/                        # 全量快照
    ├── dwd/<table>/dt=YYYY-MM-DD/
    ├── dws/<table>/dt=YYYY-MM-DD/
    └── ads/<table>/dt=YYYY-MM-DD/
output/
├── ads_export/<table>.csv                 # Excel 可读（UTF-8 BOM）
├── ads_export/<table>.json                # 下游系统/接口可读
├── quality/dq_report_*.csv
├── run_log/etl_run_*.json + pipeline_*.log
├── dashboard.html                         # 离线看板
└── dashboard_assets/echarts.min.js
```

- 事实表按 `dt` 幂等覆盖：先删除目标日期分区，再 append，避免全表重写。
- 空结果写入 `dt=1900-01-01` 的占位行以保留 Schema；读取时按日期过滤排除。
- 待生产化时可替换为 Hive/Delta Lake，代理键与分层 SQL 不需要改。

## 5. 调度与增量

### 5.1 全量模式

```bash
.venv/Scripts/python.exe -m src.etl.pipeline --mode full
```

依次执行 ODS → DIM → DWD → 质量 → DWS → 质量 → ADS → 质量 → 导出 → 看板。各阶段耗时、行数、状态写入 `output/run_log/etl_run_*.json`。

### 5.2 日增量模式

```bash
.venv/Scripts/python.exe -m src.etl.pipeline --mode daily --date 2026-10-16
```

- 默认输出窗口 21 天（`pipeline.lookback_days_daily`），并向前多取 14 天作为 DWD 订单输入窗口：退款最长延迟约 14 天，退款日当天可能要关联更早的订单行；DWS/ADS 仍只重算输出窗口的 21 天。这样既能正确回算退款，又不会把边界日期写坏。
- ADS 快照（RFM、留存、促销效果）会读取完整历史 DWD/DWS 重新计算。
- ADS 日汇总只写入目标日期分区；其他历史分区保留。
- DIM 全量重建（维表规模小）。
- 生产中建议由 Airflow/调度器在每日 02:00 触发，并配置失败重试与告警。

### 5.3 Airflow 示例

```python
from airflow import DAG
from airflow.operators.bash import BashOperator
from datetime import datetime, timedelta

with DAG(
    dag_id="retail_dw_daily",
    start_date=datetime(2026, 4, 20),
    schedule="0 2 * * *",
    catchup=False,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
) as dag:
    run = BashOperator(
        task_id="run_daily",
        bash_command=(
            "cd /opt/retail_dw && "
            ".venv/bin/python -m src.etl.pipeline "
            "--mode daily --date {{ ds }}"
        ),
    )
```

Windows 本地可用「任务计划程序」调用 `scripts/run_pipeline.ps1 --mode daily`。

## 6. 数据质量

- 规则文件：`config/quality_rules.yml`。
- 规则类型：SQL 违规行数、最小行数。
- 严重级别：`critical` 阻断流程，`warning` 记录不阻断。
- 报告：`output/quality/dq_report_<run_id>.csv` 和 `dq_report_latest.csv`。
- 核心规则：
  - 各事实表主键唯一；
  - 订单金额与成功支付一致；
  - 订单行金额 + 运费 = 实付；
  - 退款 ≤ 行金额；
  - 线上支付会话 = 线上有效订单；
  - 线下订单 ≤ 客流；
  - 库存守恒且非负；
  - DWS GMV = DWD 重算；ADS GMV = DWS 重算。

## 7. 运行环境（Windows）

项目在 `env/` 内自带：

- Temurin/Microsoft OpenJDK 17（免安装，不修改系统环境变量）
- Hadoop `winutils.exe` / `hadoop.dll`（Hadoop 3.3.6）

`src/common/env.py` 会在导入 PySpark 前自动设置 `JAVA_HOME`、`HADOOP_HOME`、`PATH`、`PYSPARK_PYTHON`、`SPARK_LOCAL_IP`，因此无需手动配置环境变量。Spark 以 `local[4]`、driver 5GB、shuffle 32 启动，关闭 Spark UI，避免本地端口与内存问题。

生产环境应使用 Linux + YARN/Kubernetes + Hive Metastore/Delta Lake；当前 Windows 单机配置仅用于开发和演示。

## 8. 工程化扩展方向

- 存储：Parquet → Delta Lake/Hudi，支持 ACID、时间旅行与 MERGE。
- 调度：Airflow + SLA 告警；元数据落 DataHub/Atlas。
- 采集：DataX/Flink CDC 替代 CSV 模拟源。
- 服务：Trino/ClickHouse 支撑 BI；Superset/Metabase 替代静态看板。
- 质量：Great Expectations / Deequ 接入规则引擎。
- 模型：会员流失预测、需求预测、智能补货（在 ADS 之上扩展）。
