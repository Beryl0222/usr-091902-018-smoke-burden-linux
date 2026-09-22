"""领域目录与版本化定义登记。

所有目录/定义都是事件流里的版本化聚合：

* 国家地区目录（240 个 ISO 3166 条目）与地区映射各自带版本；
* 疾病、性别、儿童年龄段为受控词表；
* 指标定义（暴露率的口径、分母、适用年龄/性别）带版本；
* 风险参数（相对危险度 RR 及不确定区间）带版本，可被撤回且永不物理删除；
* 负担计算公式带版本，运行清单锁定具体公式版本。
"""

from __future__ import annotations

from .catalog_data import COUNTRY_ROWS
from .store import EventStore, content_hash

# 受控词表
SEXES = [
    {"sex_id": "FMLE", "label": "女性"},
    {"sex_id": "MLE", "label": "男性"},
    {"sex_id": "BTSX", "label": "两性合计"},
]

# 儿童年龄段按发布拆分要求单列；成人段用于成人疾病结局
AGE_BANDS = [
    {"band_id": "INF", "label": "0-1岁", "min_age": 0, "max_age": 1, "pediatric": True},
    {"band_id": "TOD", "label": "2-4岁", "min_age": 2, "max_age": 4, "pediatric": True},
    {"band_id": "CHILD", "label": "5-11岁", "min_age": 5, "max_age": 11, "pediatric": True},
    {"band_id": "ADO", "label": "12-17岁", "min_age": 12, "max_age": 17, "pediatric": True},
    {"band_id": "ADULT", "label": "18岁及以上", "min_age": 18, "max_age": None, "pediatric": False},
]

DISEASES = [
    {"disease_id": "LRI", "label": "下呼吸道感染", "pediatric": True,
     "icd": "J09-J22"},
    {"disease_id": "ASTHMA", "label": "哮喘", "pediatric": True,
     "icd": "J45-J46"},
    {"disease_id": "IHD", "label": "缺血性心脏病", "pediatric": False,
     "icd": "I20-I25"},
    {"disease_id": "STROKE", "label": "脑卒中", "pediatric": False,
     "icd": "I60-I69"},
    {"disease_id": "COPD", "label": "慢性阻塞性肺疾病", "pediatric": False,
     "icd": "J40-J44"},
    {"disease_id": "LUNGCA", "label": "肺癌", "pediatric": False,
     "icd": "C33-C34"},
]

INDICATORS = [
    {
        "indicator_id": "SHS_PREV",
        "version": 1,
        "label": "二手烟家庭暴露率",
        "unit": "proportion",
        "definition": "调查时点前 30 天内，家庭中每日有人在室内吸烟的非吸烟者占比。",
        "numerator": "过去30天家中室内暴露于烟草烟雾的非吸烟者人数",
        "denominator": "同口径受访非吸烟者人数",
        "eligible_sex": ["FMLE", "MLE"],
        "eligible_bands": ["INF", "TOD", "CHILD", "ADO", "ADULT"],
        "survey_questions": ["HH_SMOKER_INDOOR_30D"],
    },
    {
        "indicator_id": "POP",
        "version": 1,
        "label": "年中人口（分母）",
        "unit": "persons",
        "definition": "联合国人口估计口径的年中常住人口，按性别与年龄段拆分。",
        "numerator": "年中人口数",
        "denominator": None,
        "eligible_sex": ["FMLE", "MLE", "BTSX"],
        "eligible_bands": ["INF", "TOD", "CHILD", "ADO", "ADULT"],
        "survey_questions": [],
    },
    {
        "indicator_id": "DEATHS_BASE",
        "version": 1,
        "label": "疾病基线死亡数",
        "unit": "deaths",
        "definition": "归因计算所使用的疾病全因死亡基线数（未经二手烟归因调整）。",
        "numerator": "年度疾病死亡数",
        "denominator": None,
        "eligible_sex": ["FMLE", "MLE", "BTSX"],
        "eligible_bands": ["INF", "TOD", "CHILD", "ADO", "ADULT"],
        "survey_questions": [],
    },
]

# 风险参数：相对危险度（来自荟萃分析，带 95% CI）。参数可按疾病/性别/年龄段差异化。
RISK_PARAMS = [
    {
        "risk_id": "RR_LRI_UNDER5",
        "version": 1,
        "disease_id": "LRI", "sex_id": "BTSX", "bands": ["INF", "TOD"],
        "rr": 1.56, "ci_low": 1.32, "rrtp": "RR_OR_META",
        "source_citation": "荟萃分析占位参数 v1（联调用）",
        "note": "5岁以下儿童下呼吸道感染",
    },
    {
        "risk_id": "RR_ASTHMA_CHILD",
        "version": 1,
        "disease_id": "ASTHMA", "sex_id": "BTSX", "bands": ["CHILD", "ADO"],
        "rr": 1.21, "ci_low": 1.10, "rrtp": "RR_OR_META",
        "source_citation": "荟萃分析占位参数 v1（联调用）",
        "note": "儿童哮喘新发/加重",
    },
    {
        "risk_id": "RR_IHD_ADULT",
        "version": 1,
        "disease_id": "IHD", "sex_id": "BTSX", "bands": ["ADULT"],
        "rr": 1.27, "ci_low": 1.10, "rrtp": "RR_META",
        "source_citation": "荟萃分析占位参数 v1（联调用）",
        "note": "成人缺血性心脏病",
    },
    {
        "risk_id": "RR_STROKE_ADULT",
        "version": 1,
        "disease_id": "STROKE", "sex_id": "BTSX", "bands": ["ADULT"],
        "rr": 1.25, "ci_low": 1.08, "rrtp": "RR_META",
        "source_citation": "荟萃分析占位参数 v1（联调用）",
        "note": "成人脑卒中",
    },
    {
        "risk_id": "RR_COPD_ADULT",
        "version": 1,
        "disease_id": "COPD", "sex_id": "BTSX", "bands": ["ADULT"],
        "rr": 1.40, "ci_low": 1.20, "rrtp": "RR_META",
        "source_citation": "荟萃分析占位参数 v1（联调用）",
        "note": "成人慢阻肺",
    },
    {
        "risk_id": "RR_LUNGCA_ADULT",
        "version": 1,
        "disease_id": "LUNGCA", "sex_id": "BTSX", "bands": ["ADULT"],
        "rr": 1.20, "ci_low": 1.05, "rrtp": "RR_META",
        "source_citation": "荟萃分析占位参数 v1（联调用）",
        "note": "成人肺癌",
    },
]

# 公式定义（版本化）。V1 为经典 Levin 公式 + CI 解析传播；V2 改为蒙特卡洛传播。
FORMULAS = [
    {
        "formula_id": "PAF_LEVIN",
        "version": 1,
        "label": "Levin PAF，解析不确定度传播",
        "expression": "PAF = P*(RR-1) / (1 + P*(RR-1))",
        "uncertainty": "delta_method_log",
        "requires": ["prevalence", "rr", "ci_low"],
    },
    {
        "formula_id": "PAF_LEVIN",
        "version": 2,
        "label": "Levin PAF，蒙特卡洛不确定度传播",
        "expression": "PAF = P*(RR-1) / (1 + P*(RR-1)); RR~lognormal, 10000 次抽样",
        "uncertainty": "monte_carlo_10000",
        "requires": ["prevalence", "rr", "ci_low", "seed"],
    },
]


def bootstrap(store: EventStore) -> dict:
    """写入首版目录与定义。重复执行幂等（同内容事件会被合并）。"""
    refs = {}

    ev = store.append("catalog_version", "catalog:countries", {
        "catalog": "countries", "version": 1, "rows": COUNTRY_ROWS,
        "content_hash": content_hash(COUNTRY_ROWS)})
    refs["countries"] = ev.payload_hash

    mapping_rows = [{"code": c, "un_subregion": u, "who_region": w}
                    for (c, _n, u, w) in COUNTRY_ROWS]
    ev = store.append("mapping_version", "mapping:country_region", {
        "mapping": "country_to_un_subregion_and_who_region",
        "version": 1, "based_on_catalog_hash": refs["countries"],
        "rows": mapping_rows, "content_hash": content_hash(mapping_rows)})
    refs["mapping"] = ev.payload_hash

    for vocab, agg in ((DISEASES, "vocab:diseases"), (SEXES, "vocab:sexes"),
                       (AGE_BANDS, "vocab:age_bands")):
        ev = store.append("vocab_version", agg,
                          {"version": 1, "rows": vocab,
                           "content_hash": content_hash(vocab)})
        refs[agg] = ev.payload_hash

    for ind in INDICATORS:
        ev = store.append("indicator_version", f"indicator:{ind['indicator_id']}", ind)
        refs[f"indicator:{ind['indicator_id']}"] = ev.payload_hash

    for rp in RISK_PARAMS:
        ev = store.append("risk_param_version", f"risk_param:{rp['risk_id']}", rp)
        refs[rp["risk_id"]] = ev.payload_hash

    for f in FORMULAS:
        ev = store.append("formula_version", f"formula:{f['formula_id']}", f)
        refs[f"formula:{f['formula_id']}:v{f['version']}"] = ev.payload_hash

    return refs


# —— 解析（支持 cutoff 时间旅行） ——

def _latest(store: EventStore, aggregate: str, until_seq: int | None):
    versions = [e for e in store.aggregate_versions(aggregate)
                if until_seq is None or e.seq <= until_seq]
    return versions[-1] if versions else None


def countries(store: EventStore, until_seq: int | None = None) -> dict[str, dict]:
    ev = _latest(store, "catalog:countries", until_seq)
    if ev is None:
        return {}
    return {code: {"code": code, "name": name, "un_subregion": unr,
                   "who_region": who}
            for code, name, unr, who in ev.payload["rows"]}


def region_mapping(store: EventStore, until_seq: int | None = None) -> dict[str, dict]:
    ev = _latest(store, "mapping:country_region", until_seq)
    return {r["code"]: r for r in ev.payload["rows"]} if ev else {}


def vocab(store: EventStore, name: str, until_seq: int | None = None) -> list[dict]:
    ev = _latest(store, f"vocab:{name}", until_seq)
    return ev.payload["rows"] if ev else []


def indicator(store: EventStore, indicator_id: str,
              until_seq: int | None = None) -> dict | None:
    ev = _latest(store, f"indicator:{indicator_id}", until_seq)
    return ev.payload if ev else None


def risk_param(store: EventStore, risk_id: str,
               until_seq: int | None = None) -> dict | None:
    """返回 cutoff 时点有效（未撤回）的风险参数版本；已撤回则返回 None。"""
    versions = [e for e in store.aggregate_versions(f"risk_param:{risk_id}")
                if e.event_type == "risk_param_version"
                and (until_seq is None or e.seq <= until_seq)]
    if not versions:
        return None
    payload = versions[-1].payload
    withdrawn = any(
        e.event_type == "risk_param_withdrawn"
        and e.payload.get("risk_id") == risk_id
        and e.payload.get("version") == payload["version"]
        and (until_seq is None or e.seq <= until_seq)
        for e in store.events("risk_param_withdrawn", until_seq))
    return None if withdrawn else payload


def risk_params_for(store: EventStore, disease_id: str, sex_id: str, band_id: str,
                    until_seq: int | None = None) -> list[dict]:
    out = []
    for ev in store.events("risk_param_version", until_seq):
        p = ev.payload
        if p["disease_id"] != disease_id:
            continue
        if p["sex_id"] not in (sex_id, "BTSX"):
            continue
        if band_id not in p["bands"]:
            continue
        active = risk_param(store, p["risk_id"], until_seq)
        if active and active["version"] == p["version"]:
            out.append(active)
    return out


def formula(store: EventStore, formula_id: str, version: int,
            until_seq: int | None = None) -> dict | None:
    for ev in store.aggregate_versions(f"formula:{formula_id}"):
        if ev.payload["version"] == version and (until_seq is None or ev.seq <= until_seq):
            return ev.payload
    return None


def withdraw_risk_param(store: EventStore, risk_id: str, reason: str,
                        paper_ref: str | None = None) -> int:
    """撤回风险参数当前版本。追加撤回事件，返回其 seq。旧值与历史仍完整保留。"""
    versions = [e for e in store.aggregate_versions(f"risk_param:{risk_id}")
                if e.event_type == "risk_param_version"]
    if not versions:
        raise KeyError(risk_id)
    current = versions[-1].payload
    ev = store.append("risk_param_withdrawn", f"risk_param:{risk_id}", {
        "risk_id": risk_id, "version": current["version"],
        "reason": reason, "paper_ref": paper_ref,
        "withdrawn_definition_hash": versions[-1].payload_hash})
    store.add_flag({
        "flag_id": f"withdraw-{risk_id}-v{current['version']}",
        "kind": "parameter_withdrawn", "target_type": "risk_param",
        "target_id": risk_id, "reason": reason,
        "report_id": None, "run_id": None, "node_key": None,
        "created_seq": ev.seq, "payload": {"paper_ref": paper_ref}})
    return ev.seq
