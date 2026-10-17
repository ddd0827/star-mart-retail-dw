# 星选生活 STAR-MART 连锁零售数据仓库

按真实连锁零售业务流程构建的数据开发项目：从模拟业务源系统出发，使用 **Spark / Spark SQL / Parquet** 构建分层数据仓库（ODS → DIM/DWD → DWS → ADS），配套数据质量校验、ETL 调度日志、ADS 导出与离线可打开的 HTML 经营看板。

> 数据均为模拟数据（虚构品牌、门店、商品、会员），不包含真实个人信息，仅用于数据开发与教学演示。

## 1. 项目亮点

- **真实业务链路驱动生成**：门店客流 → 线下订单；线上会话漏斗 → 线上订单；支付 → 退款/退货 → 库存回补；补货采购触发库存流水。不是各表独立造数。
- **完整数仓分层**：ODS / DIM / DWD / DWS / ADS，星型模型 + 代理键 + 事件粒度清晰。
- **Spark SQL 工程化**：DWD/DWS/ADS 核心逻辑外置为 SQL 文件；Parquet 按 dt 分区、幂等覆盖；本地 Spark 运行。
- **可对账的数据**：订单金额 = 行金额 + 运费 = 支付金额；退款 ≤ 行金额；支付会话 = 线上订单；库存期初 + 入库 − 销售 + 退货 ± 调整 = 期末。
- **数据质量规则引擎**：主键唯一、金额对账、流量约束、库存守恒、DWS/ADS 重算一致性；critical 失败阻断调度。
- **业务看板**：经营总览、销售趋势、渠道结构、品类结构、门店排行、线上漏斗、RFM、库存周转、促销效果；ECharts 本地资源，断网可打开。
- **真实感细节**：节假日/大促/会员日、周末效应、品类季节、商品长尾、会员等级、支付渠道、退款原因与延迟、门店铺货差异、混合时间格式与少量脏数据。

## 2. 技术栈

| 类别 | 技术 |
|---|---|
| 计算 | Apache Spark 3.5.9（PySpark，local 模式）、Spark SQL |
| 存储 | Parquet（Snappy）、Hive 风格分区 |
| 模拟数据 | Python 3.11、NumPy、pandas |
| 配置 / 模板 | YAML、Jinja2 |
| 可视化 | ECharts 5（本地 JS，离线） |
| 测试 | pytest |
| 运行环境 | Windows 11、项目内 JDK 17、Hadoop winutils |

## 3. 架构

```
raw CSV（模拟源系统）
  → ODS（Parquet，按 dt 分区）
  → DIM（日期/门店/商品/品类/品牌/会员/供应商/活动/渠道/目标）
  → DWD（订单/订单行/支付/退款/库存/客流/会话/行为/采购）
  → DWS（门店日/渠道日/SKU日/会员日/线上漏斗日/库存SKU日/活动日）
  → ADS（经营总览/门店/品类/商品/RFM/留存/复购/库存周转/漏斗/促销）
  → CSV/JSON + 静态看板
```

详见 [docs/architecture.md](docs/architecture.md)。

## 4. 数据范围与规模

| 项目 | 规模 |
|---|---|
| 时间窗口 | 2026-04-20 ~ 2026-10-16（180 天） |
| 门店 | 24 家线下门店 + 1 个线上履约仓 |
| 商品 | 1,500 个 SKU，52 个两级品类，80 个品牌 |
| 会员 | 100,000 |
| 有效支付订单 | 约 50 万 |
| 线上行为事件 | 约 1,000 万 |
| 库存日快照 | 约 450 万行（25 库位 × 铺货 SKU × 180 天） |
| 供应商 | 25 家 |

节假日：五一、端午、中秋、国庆；大促：五一、618、国庆；每月 8/18/28 会员日。

## 5. 快速开始（Windows）

> 本项目所有数据、虚拟环境与输出均位于 D 盘项目目录 `D:\DY\xm10.17` 下；不会写入系统目录或其他盘符。

### 5.1 安装环境（首次）

```powershell
python scripts\setup_env.py
```

脚本会：

1. 创建 `.venv` 并安装 `requirements.txt`（含 PySpark 3.5.9）；
2. 下载免安装 JDK 17 到 `env/jdk17`；
3. 下载 Hadoop `winutils.exe` / `hadoop.dll` 到 `env/hadoop/bin`（SHA256 校验）；
4. 运行 Spark Parquet 读写冒烟测试。

环境全部在项目目录内，不修改系统 `JAVA_HOME`/`HADOOP_HOME`。也可以直接使用已经准备好的 `.venv`。

### 5.2 生成模拟数据

```powershell
.venv\Scripts\python.exe -m src.generator.generate
```

快速小样本（用于开发调试）：

```powershell
.venv\Scripts\python.exe -m src.generator.generate --sample-days 5 --members 3000 --skus 300 --sessions-per-day 800
```

### 5.3 运行数仓

```powershell
.venv\Scripts\python.exe -m src.etl.pipeline --mode full
```

或使用封装脚本：

```powershell
scripts\run_pipeline.ps1 --mode full
```

日增量模式：

```powershell
.venv\Scripts\python.exe -m src.etl.pipeline --mode daily --date 2026-10-16
```

### 5.4 查看结果

- 经营看板：`output/dashboard.html`（双击打开，无需启动服务；ECharts 本地加载，可离线）
- ADS 结果：`output/ads_export/`（每张表同时输出 CSV 与 JSON；CSV 为 UTF-8 BOM，Excel 可直接打开）
- 质量报告：`output/quality/dq_report_latest.csv`
- 调度日志：`output/run_log/etl_run_latest.json` 与 `pipeline_*.log`

## 6. 项目结构

```
.
├── config/
│   ├── project.yml               # 日期、规模、Spark、脏数据比例
│   └── quality_rules.yml         # 数据质量规则（SQL）
├── scripts/
│   ├── setup_env.py/.ps1         # 一键环境安装
│   ├── run_pipeline.ps1          # 调度入口
│   └── setup_env.sh              # Git Bash 环境安装
├── src/
│   ├── common/                   # 配置、SparkSession、日志、质量、IO、Schema
│   ├── generator/                # 业务数据模拟：主数据/客流/线上/订单/库存/脏数据
│   ├── etl/                      # ODS/DIM/DWD/DWS/ADS/流水线调度
│   ├── sql/                      # DWD/DWS/ADS Spark SQL
│   └── report/                   # ADS 导出、看板生成、ECharts 资源
├── docs/
│   ├── business_process.md       # 业务流程与模拟规则
│   ├── architecture.md           # 架构、分区、调度、生产化
│   ├── data_model.md             # 总线矩阵、表设计、关系
│   └── metrics.md                # 指标口径唯一权威定义
├── data/
│   ├── raw/                      # 模拟源系统（生成）
│   └── warehouse/                # ODS/DIM/DWD/DWS/ADS Parquet
├── output/                       # 看板、CSV、质量报告、运行日志
├── tests/
└── requirements.txt
```

## 7. 数据质量与验收

- 质量规则与严重级别见 `config/quality_rules.yml`；运行后查看 `output/quality/dq_report_latest.csv`。
- 核心对账：订单金额/支付、订单行 + 运费、退款行金额、线上支付会话 = 线上订单、库存守恒、DWS/ADS 重算一致。
- 重跑同一日期结果一致（幂等覆盖）。
- `pytest`：

```powershell
.venv\Scripts\python.exe -m pytest tests -q
.venv\Scripts\python.exe scriptserify_outputs.py
```

`verify_outputs.py` 会检查 10 张 ADS 表 CSV/JSON 是否齐全、ADS GMV/订单量是否与生成清单一致、质量报告是否 0 个 critical 失败，以及看板与本地 ECharts 是否可用。

## 8. 指标口径

完整口径见 [docs/metrics.md](docs/metrics.md)，包括：

- GMV / 净销售额 / 退款率 / 客单价 / 会员占比 / 线上占比；
- 门店客流转化与 MTD 目标达成；
- RFM 分值与 8 大客群、Cohort 留存、月度复购与 30 日复购；
- 线上会话漏斗；
- 30 日库存周转、缺货率、售罄率；
- 促销增量与 ROI（观察性，非因果推断）。

## 9. 运行说明与限制

- 项目面向 Windows 单机演示：Spark `local[4]`、driver 5GB，避免占满本机内存。
- 生产环境建议迁移到 Linux + YARN/Kubernetes，使用 Hive Metastore / Delta Lake、Airflow 调度、Trino/ClickHouse + BI 工具。
- 模拟数据不代表真实业务结论；促销 ROI 仅作观察性对比；数据窗口末期存在退款右删失。
- 看板只读取 ADS 导出文件，不直接访问 DWD，保证展示口径与 ADS 一致。

## 10. 实测结果

见下方「运行记录」（每次全量运行后由实际输出更新）：

<!-- RESULTS_START -->
### 10.1 全量运行实测（2026-10-17，run_id `20261017_221737`）

| 项目 | 实测值 |
|---|---|
| 数据生成耗时 | 266 秒（主数据 1.5s / 线上 104.7s / 订单 139.7s / 库存 18.5s） |
| 数仓全流程耗时 | 605.6 秒（含 CSV 导出；JSON 导出补充运行约 14.7 秒） |
| 有效支付订单 | 506,922（线下 346,434 + 线上 160,488） |
| GMV | ¥78,175,160.70 |
| 客单价 | ¥154.22 |
| 会员 GMV 占比 | 64.5% |
| 退款订单 / 退款额 | 28,697 单 / ¥3,857,782.85 |
| 行为事件（DWD） | 11,288,615 |
| 线上会话（DWD） | 1,897,668 |
| 库存快照（DWD） | 4,517,460 |
| 采购单行（DWD） | 61,010 |
| 质量规则 | 26 条全部通过，critical 失败 0 |
| 门店 MTD 达成率范围 | 91.3% – 108.4% |

各阶段耗时：ODS 91.0s、DIM 19.2s、DWD 213.8s、DWS 85.1s、ADS 66.8s、导出 14.6s、看板 1.3s。

ADS 行数：

| 表 | 行数 |
|---|---:|
| `ads_operation_overview` | 180 |
| `ads_store_performance` | 4,320 |
| `ads_category_structure` | 8,459 |
| `ads_product_topn` | 1,500 |
| `ads_member_rfm` | 72,737 |
| `ads_member_retention` | 42 |
| `ads_member_repurchase` | 7 |
| `ads_inventory_turnover` | 4,500 |
| `ads_online_funnel` | 540 |
| `ads_promotion_effect` | 88 |

运行产物：

- 看板：[`output/dashboard.html`](output/dashboard.html)
- 看板预览图：[`output/dashboard_preview.png`](output/dashboard_preview.png)
- 质量报告：[`output/quality/dq_report_latest.csv`](output/quality/dq_report_latest.csv)
- 调度日志：[`output/run_log/etl_run_latest.json`](output/run_log/etl_run_latest.json)
- 日增量验收：[`output/run_log/etl_run_latest_daily.json`](output/run_log/etl_run_latest_daily.json)
- ADS 导出：[`output/ads_export/`](output/ads_export/)（CSV + JSON）

**幂等与增量验收**：对目标日 2026-10-16 执行 `--mode daily`（run_id `20261017_223914`），重算最近 21 天并向前多取 14 天订单用于退款回挂；与全量结果对比，GMV、订单量、退款额、净销售额、客单价、MTD 逐日差异均为 0，品类结构行数恢复为 8,459 行。full 与 daily 的调度日志分别写入 `etl_run_latest.json` / `etl_run_latest_daily.json`。生产化部署与 Airflow 示例见 [docs/architecture.md](docs/architecture.md)。
<!-- RESULTS_END -->
