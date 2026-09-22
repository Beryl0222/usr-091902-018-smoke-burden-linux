# 二手烟负担证据计算

维护**文献结果、人口调查、模型输出 → 二手烟暴露 → 风险参数 → 疾病负担估算 → 发布报告**
全链路的可追溯性。覆盖 241 个国家/地区，每个数字都能回答四个问题：

1. **用了哪些输入？** — 内容寻址的只追加事件日志（观测主张、来源版本、抽样元数据）；
2. **用的是什么公式与口径？** — 指标定义、地区映射、风险参数、PAF 公式全部版本化并写入运行清单；
3. **是观测还是估算？** — 插值/外推结果显式标注 `basis=estimated`、方法名与锚点年份，绝不冒充观测值；
4. **当时的证据长什么样？** — 每次运行锁定 `cutoff_seq`，旧报告可按当时证据逐位复现（run_id 即清单哈希）。

## 需求 → 机制对照

| 方法学要求 | 实现机制 |
| --- | --- |
| 文献版本、调查抽样、指标定义、地区映射、风险参数、每次运行互相追溯 | 只追加事件流（`burden/store.py`）+ 内容寻址 DAG（节点哈希覆盖全部输入哈希） |
| 原始数据更正只产生新快照 | 同来源同自然键值变更 → `claim_imported` 新版本；旧版本永不覆盖 |
| 缺失年份估算必须明示 | `linear_interpolation` / `nearest_extrapolation` 节点携带方法与锚点；无锚点则 `missing`，禁止造数 |
| 同一来源重复导入合并 | 同聚合同内容哈希幂等返回（`merged`） |
| 冲突数据保留竞争关系待裁定 | 异源同键不同值 → 双方主张保留、挂 `conflict_pending` 标志；`adjudicate` 后采用胜者但竞争主张仍在 |
| 按性别、儿童年龄段、疾病拆分发布 | 报告单元维度：范围×疾病×年龄段（INF/TOD/CHILD/ADO/ADULT）×性别×年份；儿童疾病只出现在儿童段 |
| 最小样本披露规则 | 样本量低于阈值或缺样本量 → 单元抑制；单性别被抑制时两性合计**互补抑制**防反推 |
| 论文撤回标出受影响结论但不删旧报告 | `paper_retracted` / `risk_param_withdrawn` 事件 + `report_annotation` 只追加标注；报告单元冻结不可变 |
| 补入迟到调查、撤回参数后只重算依赖分支 | 节点内容寻址：未受影响节点哈希不变（缓存命中）；`run_diff` 逐键验证变化仅限依赖分支 |
| 每个数字找到输入与公式版本 | `GET /api/explain/{node_hash}` / `Workspace.explain`：完整血缘（主张、风险参数、公式、指标、映射） |
| 旧报告按当时证据原样复现 | `reproduce_run`：按历史 `cutoff_seq` 与原始清单重放，run_id 逐位一致 |

## 目录结构

```
burden/
  store.py       # 只追加事件存储（sqlite3，内容哈希，逻辑时钟 seq）
  catalog_data.py# 241 个 ISO 3166 国家/地区 + UN 次区域 + WHO 区域
  registry.py    # 版本化目录：疾病/性别/年龄段词表、指标定义、风险参数（可撤回）、PAF 公式 v1/v2
  sources.py     # 来源登记（调查强制抽样元数据）、导入合并/更正/冲突/裁定、论文撤回
  engine.py      # 缺年估算、Levin PAF（解析/蒙特卡洛两版公式）、内容寻址运行、分支 diff
  publishing.py  # 拆分发布、最小样本与互补抑制、不可变报告、撤回影响标注、完整性核验、血缘解释
  api.py         # 门面 Workspace、增量再运行、按 cutoff 复现
  scenario.py    # 端到端场景：v1 发布 → 迟到调查 + 参数撤回 → 分支重算 → 旧报告复现
service.py       # HTTP JSON API + /health
tests/           # 46 个 unittest（存储/目录/来源/引擎/发布/场景/HTTP）
```

## 快速开始

```bash
python3 service.py --check        # 基础自检（241 个地区目录）
python3 -m burden.scenario        # 端到端演示（内存库，打印完整时间线）
python3 -m burden.scenario ws.sqlite3   # 持久化演示
python3 service.py --port 8000    # 启动 JSON API（SMOKE_BURDEN_DB 可指定库路径）
npm test                          # 运行全部测试（= python3 -m unittest discover -s tests）
```

### 端到端时间线（`python3 -m burden.scenario`）

- **T0** 登记调查/模型来源（调查必须含抽样设计、样本量、加权、问题口径版本）；导入数据，
  验证重复导入合并、来源更正留旧快照、异源冲突挂起并经裁定（竞争主张保留）。
- **T1** 第一版运行（公式 `PAF_LEVIN@v1`），发布报告：按性别/儿童年龄段/疾病拆分，
  最小样本抑制 + 互补抑制；缺年（如印度男性 2020）标注 `linear_interpolation` 与锚点年。
- **T2** 补入迟到的中国 2019/2021 调查；撤回肺癌风险参数 `RR_LUNGCA_ADULT`（旧值留档）。
- **T3** 增量再运行：绝大多数节点缓存命中、哈希不变；变化节点严格限于中国分支、
  肺癌分支及其上层聚合。
- **T4** 发布第二版并标注第一版受影响结论；第一版报告完整性核验通过、数值零漂移，
  按历史 cutoff 重放得到完全相同的 run_id。

## HTTP API 摘要

```
GET  /health
GET  /api/catalog/countries | /api/vocab?name=diseases|sexes|age_bands
GET  /api/resolve?indicator_id&country_code&year&sex_id&band_id   # 观测/冲突/撤回状态
POST /api/sources            # 登记来源（survey 必须带 survey_design）
POST /api/observations       # 导入观测（自动合并/更正/冲突检测）
POST /api/adjudications      # 对竞争主张裁定
POST /api/retractions/paper  # 论文撤回
POST /api/risk-params/withdraw
POST /api/runs               # {parent_run_id} 触发增量再运行
POST /api/reports            # 发布（min_sample 阈值）
POST /api/reports/{id}/annotate   # 追加撤回影响标注
GET  /api/reports/{id}       # 冻结单元 + annotations；/verify 完整性核验
GET  /api/explain/{node_hash}     # 数字血缘：输入主张 + 风险参数 + 公式版本 + 映射
POST /api/reproduce/{run_id}      # 按历史 cutoff 逐位复现
```

## 设计要点

- **只追加，不删除**：所有变化（更正、裁定、撤回、标注）都是新事件；删除只在逻辑意义上发生。
- **两层身份**：事件用 `payload_hash` 标识内容；计算节点哈希覆盖其全部依赖哈希。
  任何输入或公式改动必然沿 DAG 传播，影响面可机械判定。
- **运行即清单**：`run_id = hash(cutoff + 公式版本 + 指标/映射版本 + 全部输入)`，
  因此重放等价、跨运行节点可缓存复用。
- **发布即冻结**：报告单元拷贝当时节点哈希与数值；撤回只追加标注，永不改写旧报告。

`fixtures/domain.json` 保存领域名词与状态样例（待导入/待裁定/可计算/已发布/已失效），
业务记录均由上述正式接口产生。
