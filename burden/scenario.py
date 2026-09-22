"""端到端场景：第一版全球结果发布后的证据演化。

时间线
------
T0  登记调查/模型来源；导入 12 个代表国家 2019-2021 的暴露与基线死亡数据
    （含重复导入合并、来源更正新快照、异源冲突与裁定、小样本单元）。
T1  第一版全球计算运行 RUN-1，发布报告 R1：按性别/儿童年龄段/疾病拆分，
    执行最小样本披露，缺年估算显式标注。
T2  迟到的中国 2019/2021 调查补入；撤回肺癌风险参数 RR_LUNGCA_ADULT。
T3  仅对受影响分支再运行 RUN-2：未受影响节点哈希不变（缓存命中）。
T4  发布 R2 并在 R1 上追加"受影响结论"标注；R1 不删除、数值不漂移，
    按当时 cutoff 可原样复现（run_id 完全一致）。

用法：``python3 -m burden.scenario``（内存演示）或
``python3 -m burden.scenario path/to/workspace.sqlite3``（持久化）。
"""

from __future__ import annotations

import sys

from .api import Workspace, open_workspace

YEARS = (2019, 2020, 2021)

# 成人二手烟暴露率（女, 男）与各疾病年基线死亡（千人，两性合计）
ADULT = {
    #      暴露F/M   IHD    STROKE COPD  LUNGCA  数据年份
    "CN": ((0.42, 0.47), 2050, 1620, 820, 430, (2020,)),
    "IN": ((0.34, 0.46), 1820, 1280, 620, 180, (2019, 2021)),
    "US": ((0.20, 0.24), 780, 520, 320, 240, (2019, 2020, 2021)),
    "ID": ((0.33, 0.42), 600, 460, 180, 60, (2019,)),
    "BR": ((0.24, 0.29), 420, 380, 160, 70, (2019, 2020, 2021)),
    "NG": ((0.13, 0.18), 340, 300, 120, 30, (2019, 2020, 2021)),
    "EG": ((0.37, 0.44), 300, 240, 90, 25, (2020,)),
    "DE": ((0.18, 0.22), 240, 200, 80, 60, (2019, 2020, 2021)),
    "PK": ((0.39, 0.49), 280, 220, 80, 20, (2019, 2020, 2021)),
    "BD": ((0.35, 0.45), 220, 180, 70, 15, (2019, 2020, 2021)),
    "JP": ((0.15, 0.20), 200, 170, 90, 80, (2019, 2020, 2021)),
    "RU": ((0.28, 0.36), 420, 360, 120, 55, (2019, 2020, 2021)),
}
ADULT_DISEASES = ("IHD", "STROKE", "COPD", "LUNGCA")

# 儿童：5岁以下 LRI（INF/TOD），儿童哮喘（CHILD/ADO）
LRI = {  # 国家: (INF暴露, TOD暴露, INF年死亡, TOD年死亡)
    "NG": (0.58, 0.46, 160_000, 80_000),
    "IN": (0.50, 0.40, 120_000, 60_000),
    "ET": (0.55, 0.45, 48_000, 22_000),
}
ASTHMA = {  # 国家: (CHILD暴露, ADO暴露, CHILD年死亡, ADO年死亡)
    "CN": (0.18, 0.12, 600, 400),
    "US": (0.12, 0.09, 200, 150),
}


def _survey_design(cc: str, n: int):
    return {"design": "stratified_multistage_cluster", "sample_size": n,
            "weighting": "post_stratification",
            "questions_version": "SHS-CORE-QUESTIONNAIRE v3"}


def _add_prevalence(ws, source, cc, year, sex, band, value, sample, *,
                    low=None, high=None):
    return ws.import_observation(source, {
        "country_code": cc, "year": year, "sex_id": sex, "band_id": band,
        "indicator_id": "SHS_PREV", "value": value,
        "unc_low": value - 0.04 if low is None else low,
        "unc_high": value + 0.04 if high is None else high,
        "sample_size": sample})


def _add_deaths(ws, source, cc, year, sex, band, disease_unused, value):
    return ws.import_observation(source, {
        "country_code": cc, "year": year, "sex_id": sex, "band_id": band,
        "indicator_id": "DEATHS_BASE", "value": value})


def run_scenario(path: str = ":memory:") -> dict:
    ws = open_workspace(path)
    story: list[str] = []

    def log(msg):
        story.append(msg)

    # ── T0：来源登记与导入 ────────────────────────────────────────────────
    ws.register_source("MOD-GBD-DEATHS", "model", "全球疾病负担基线死亡模型输出",
                       citation="占位模型输出 v1", year=2024)
    for cc in list(ADULT) + ["ET"]:
        ws.register_source(f"SURV-{cc}", "survey", f"{cc} 全国成人/家庭烟草调查",
                           survey_design=_survey_design(cc, 4200))

    dup_seen = False
    for cc, ((pf, pm), ihd, stroke, copd, lungca, years) in ADULT.items():
        for sex, p in (("FMLE", pf), ("MLE", pm)):
            for y in years:
                r = _add_prevalence(ws, f"SURV-{cc}", cc, y, sex, "ADULT", p, 4200)
                if r["status"] == "recorded" and not dup_seen:
                    # 紧接着重复导入同一文件：应合并而非产生新记录
                    r2 = _add_prevalence(ws, f"SURV-{cc}", cc, y, sex, "ADULT", p, 4200)
                    dup_seen = r2["status"] == "merged"
        for y in YEARS:
            for sex, share in (("FMLE", 0.46), ("MLE", 0.54)):
                for did, deaths in zip(ADULT_DISEASES,
                                       (ihd, stroke, copd, lungca)):
                    _add_deaths(ws, "MOD-GBD-DEATHS", cc, y, sex, "ADULT",
                                did, deaths * 1000 * share)

    # 更正：印尼 2019 暴露率由 0.33 更正为 0.35（女）——新快照，旧值保留
    correction = _add_prevalence(ws, "SURV-ID", "ID", 2019, "FMLE", "ADULT",
                                 0.35, 4200, low=0.31, high=0.39)

    # 冲突：某模型输出对美国 2020 男性暴露给出 0.31，与调查 0.24 冲突
    ws.register_source("MOD-X-PREV", "model", "外部暴露模型估计 X", year=2024)
    conflict = _add_prevalence(ws, "MOD-X-PREV", "US", 2020, "MLE", "ADULT",
                               0.31, None, low=0.27, high=0.35)
    cell_before = ws.resolve_cell(indicator_id="SHS_PREV", country_code="US",
                                  year=2020, sex_id="MLE", band_id="ADULT")
    adjudication = ws.adjudicate(
        {"country_code": "US", "year": 2020, "sex_id": "MLE",
         "band_id": "ADULT", "indicator_id": "SHS_PREV"},
        winner_source_id="SURV-US",
        rationale="调查为直接观测且抽样设计完整，模型估计仅作参考",
        adjudicator="方法学负责人")
    cell_after = ws.resolve_cell(indicator_id="SHS_PREV", country_code="US",
                                 year=2020, sex_id="MLE", band_id="ADULT")

    # 儿童数据
    for cc, (pi, pt, di, dt) in LRI.items():
        for band, p, deaths in (("INF", pi, di), ("TOD", pt, dt)):
            for sex in ("FMLE", "MLE"):
                for y in YEARS:
                    _add_prevalence(ws, f"SURV-{cc}", cc, y, sex, band, p, 3000)
                    _add_deaths(ws, "MOD-GBD-DEATHS", cc, y, sex, band,
                                "LRI", deaths / 2)
    for cc, (pc, pa, dc, da) in ASTHMA.items():
        for band, p, deaths in (("CHILD", pc, dc), ("ADO", pa, da)):
            for sex in ("FMLE", "MLE"):
                for y in YEARS:
                    _add_prevalence(ws, f"SURV-{cc}", cc, y, sex, band, p, 3000)
                    _add_deaths(ws, "MOD-GBD-DEATHS", cc, y, sex, band,
                                "ASTHMA", deaths / 2)

    # 最小样本：佛得角小样本调查（男 30 人）触发抑制
    ws.register_source("SURV-CV", "survey", "CV 佛得角小型地方调查",
                       survey_design=_survey_design("CV", 30))
    _add_prevalence(ws, "SURV-CV", "CV", 2020, "MLE", "ADULT", 0.30, 30)
    _add_prevalence(ws, "SURV-CV", "CV", 2020, "FMLE", "ADULT", 0.26, 800)
    for sex in ("FMLE", "MLE"):
        _add_deaths(ws, "MOD-GBD-DEATHS", "CV", 2020, sex, "ADULT",
                    "IHD", 600)

    log(f"T0 证据库就绪：逻辑时钟 seq={ws.store.head_seq()}；"
        f"重复导入合并={dup_seen}；印尼更正状态={correction['status']}（旧哈希 "
        f"{correction['superseded_claim_hash'][:8]}… 仍保留）；"
        f"美国冲突检测={conflict.get('conflict')}，裁定前状态={cell_before['state']}，"
        f"裁定后采用={cell_after['claim']['source_id']}（竞争主张 "
        f"{len(cell_after['competitors'])} 条保留）。")

    # ── T1：第一版运行与发布 ──────────────────────────────────────────────
    run1 = ws.run(rationale="第一版全球二手烟归因死亡估算 2019-2021",
                  formula_version=1)
    total_2019 = ws.node(run1["run_id"], "global:total:2019")
    in2020 = ws.node(run1["run_id"], "prev:IN:MLE:ADULT:2020")
    pub1 = ws.publish(run1["run_id"], "全球二手烟疾病负担（第一版）", min_sample=50)
    r1 = ws.report(pub1["report_id"])
    suppressed = [c for c in r1["cells"] if c["status"] == "suppressed"]
    cv_male = next(c for c in suppressed if c["country_code"] == "CV"
                   and c["sex"] == "MLE")
    cv_btsx = next(c for c in r1["cells"] if c.get("country_code") == "CV"
                   and c["sex"] == "BTSX" and c["year"] == 2020)
    log(f"T1 运行 {run1['run_id']}（cutoff_seq={run1['cutoff_seq']}，"
        f"节点 {run1['node_count']} 个，未裁定冲突告警 "
        f"{len([w for w in run1['warnings'] if w['type']=='unadjudicated_conflict'])} 个）。")
    log(f"   头条：2019 年全球归因死亡 {total_2019['value']:,.0f} 人"
        f"（95% UI {total_2019['unc_low']:,.0f}–{total_2019['unc_high']:,.0f}），"
        f"节点哈希 {total_2019['node_hash'][:12]}…。")
    log(f"   缺年不冒充观测：印度男性 2020 暴露节点 basis={in2020['basis']}，"
        f"method={in2020['method']['name']}，锚点年={in2020['method']['anchor_years']}。")
    log(f"   报告 {pub1['report_id']} 发布：{pub1['cell_count']} 个拆分单元，"
        f"抑制 {pub1['suppressed_count']} 个。佛得角男性单元因 "
        f"{cv_male['suppressed_reason']} 被抑制；两性合计因 "
        f"{cv_btsx['suppressed_reason']} 一并抑制。")

    # ── T2：迟到调查 + 风险参数撤回 ───────────────────────────────────────
    ws.register_source("SURV-CN-LATE", "survey",
                       "中国家庭烟草调查（延迟归档，2026 年补入）",
                       survey_design=_survey_design("CN", 5100))
    for sex, p in (("FMLE", 0.40), ("MLE", 0.45)):
        for y in (2019, 2021):
            _add_prevalence(ws, "SURV-CN-LATE", "CN", y, sex, "ADULT", p, 5100)
    withdraw_seq = ws.withdraw_risk_param(
        "RR_LUNGCA_ADULT",
        reason="上游荟萃分析被发现误纳入两项重叠队列，RR 不再可用于归因计算",
        paper_ref="doi:10.0000/placeholder-retraction")
    log(f"T2 迟到调查补入；肺癌风险参数 RR_LUNGCA_ADULT 在 seq={withdraw_seq} 撤回"
        f"（旧参数值仍可在事件历史中查到，之后运行不再采用）。")

    # ── T3：仅依赖分支重算 ───────────────────────────────────────────────
    run2 = ws.rerun_for(run1["run_id"],
                        rationale="补入中国迟到调查并撤回肺癌风险参数后的增量再计算")
    diff = run2["diff_vs_parent"]
    changed_keys = set(diff["changed"]) | set(diff["added"]) | set(diff["removed"])
    lungca_changed = [k for k in changed_keys if ":LUNGCA:" in k]
    cn_changed = [k for k in changed_keys if k.startswith(("prev:CN", "paf:CN", "attr:CN"))]
    untouched = [k for k in diff["unchanged"]
                 if k.startswith("attr:") and ":LUNGCA:" not in k]
    sample_untouched = next(k for k in untouched if k.startswith("attr:IN:IHD"))
    log(f"T3 新运行 {run2['run_id']}：节点缓存命中 {run2['cache_hits']}/"
        f"{run2['node_count']}；与父运行相比变更/增删 {len(changed_keys)} 个节点，"
        f"其中肺癌分支 {len(lungca_changed)} 个、中国分支 {len(cn_changed)} 个；"
        f"未受影响节点 {len(diff['unchanged'])} 个哈希完全一致（例 {sample_untouched}）。")

    # ── T4：发布 R2，旧报告追加标注但原样保留 ────────────────────────────
    pub2 = ws.publish(run2["run_id"], "全球二手烟疾病负担（第二版）", min_sample=50)
    ws.supersede(pub1["report_id"], pub2["report_id"])
    impacts = ws.annotate_report(pub1["report_id"])
    intact = ws.verify_report(pub1["report_id"])
    repro = ws.reproduce_run(run1["run_id"])
    r1_after = ws.report(pub1["report_id"])
    affected_example = next(a for a in impacts["affected"]
                            if ":LUNGCA:" in a["cell_key"])
    total_2019_r2 = ws.node(run2["run_id"], "global:total:2019")
    explained = ws.explain(total_2019["node_hash"])
    log(f"T4 新报告 {pub2['report_id']} 发布；2019 全球归因死亡 "
        f"{total_2019_r2['value']:,.0f} 人（第一版 {total_2019['value']:,.0f}）。")
    log(f"   旧报告未删除/未改写：完整性核验 intact={intact['intact']}，"
        f"头条单元冻结值仍为 {total_2019['value']:,.0f}；"
        f"追加受影响标注 {impacts['new_annotations']} 条（例：{affected_example['cell_key']} "
        f"— {affected_example['reason'][:28]}…）。")
    log(f"   旧报告可按当时证据复现：cutoff_seq={run1['cutoff_seq']} 重放 run_id "
        f"一致={repro['identical']}（{repro['replayed_run_id']}）。")
    log(f"   每个数字可追溯：全球头条节点血缘含 {explained['lineage_size']} 个节点、"
        f"{len(explained['inputs']['claims'])} 条输入主张、"
        f"{len(explained['inputs']['risk_params'])} 个风险参数、"
        f"公式 {explained['inputs']['formulas'][0]['formula_id']}"
        f"@v{explained['inputs']['formulas'][0]['version']}。")

    return {
        "workspace": ws, "story": story,
        "run1": run1, "run2": run2,
        "report1": pub1["report_id"], "report2": pub2["report_id"],
        "total_2019_r1": total_2019["value"],
        "total_2019_r2": total_2019_r2["value"],
        "suppressed_cv_male": cv_male,
        "suppressed_cv_btsx": cv_btsx,
        "diff": diff, "impacts": impacts,
        "intact": intact, "reproduce": repro,
        "withdraw_seq": withdraw_seq,
        "correction": correction, "adjudication": adjudication,
        "dup_merged": dup_seen,
        "estimated_node": in2020,
        "explained": explained,
    }


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    path = argv[0] if argv else ":memory:"
    result = run_scenario(path)
    print("=" * 72)
    print("二手烟暴露与疾病负担：可追溯证据链端到端场景")
    print("=" * 72)
    for line in result["story"]:
        print("•", line)
    print("=" * 72)


if __name__ == "__main__":
    main()
