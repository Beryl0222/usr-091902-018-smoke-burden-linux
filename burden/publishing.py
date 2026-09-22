"""报告发布：拆分披露、最小样本规则、不可变冻结与撤回影响标注。

发布单元（cell）维度：范围（国家/WHO区域/UN次区域/全球）× 疾病 × 年龄段 ×
性别 × 年份。每个单元指向一个结果节点哈希，数字即节点身份。

最小样本披露控制
----------------

1. 一级抑制：国家×性别单元所依赖的二手烟暴露调查，最小样本量低于阈值（默认 50），
   或样本量缺失时，抑制数值（"small_sample" / "sample_size_unknown"）。缺年估算
   取锚点调查的最小样本量。
2. 互补抑制：某国×疾病×年龄段×年仅一个性别被抑制时，两性合计也必须抑制，否则
   可由"合计−另一性别"反推（"complementary"）。
3. 区域/全球合计仍可发布（大样本合计不暴露小样本单元），但元数据注明所含被抑制
   组件数量。

报告一旦发布即冻结（cutoff_seq + 节点哈希）。论文或参数撤回后调用
``annotate_impacts`` 只追加"受影响结论"标注，绝不改写或删除旧单元；旧报告可用
当时 cutoff 原样重放复现。
"""

from __future__ import annotations

from .store import EventStore, content_hash

MIN_SAMPLE_DEFAULT = 50

PEDIATRIC_DISEASE_NOTE = "儿童疾病（LRI、哮喘）仅在儿童年龄段发布；成人疾病仅在成人段发布。"


def publish(store: EventStore, run_id: str, title: str, *,
            min_sample: int = MIN_SAMPLE_DEFAULT,
            report_id: str | None = None) -> dict:
    run = store.get_run(run_id)
    if run is None:
        raise KeyError(run_id)
    cutoff = run["manifest"]["cutoff_seq"]
    nodes = {n["node_hash"]: n for n in store.nodes_of_run(run_id)}

    cells: list[dict] = []
    suppressed_country_keys: set[tuple] = set()   # (code,did,band,year) 被抑制性别
    sex_components: dict[tuple, list[str | None]] = {}

    for node in sorted(nodes.values(), key=lambda n: n["node_key"]):
        kind = node.get("kind")
        cell = None
        if kind == "attributable_deaths":
            cell = _cell_from_country_sex(store, node, run_id, min_sample)
            if cell["status"] == "suppressed":
                suppressed_country_keys.add(
                    (node["country_code"], node["disease_id"],
                     node["band_id"], node["year"]))
            sex_components.setdefault(
                (node["country_code"], node["disease_id"],
                 node["band_id"], node["year"]), []).append(
                    cell["status"] if cell["status"] == "suppressed" else None)
        elif kind == "attributable_deaths_aggregate":
            cell = _cell_from_btsx(node, run_id)
        elif kind == "aggregate" and node.get("scope") in (
                "who_region", "un_subregion", "global", "global_total"):
            cell = _cell_from_region(node, run_id)
        if cell is not None:
            cells.append(cell)

    # 互补抑制：单个性别被抑制 → 该国 BTSX 单元抑制
    btsx_index = {(c["country_code"], c["disease_id"], c["age_band"], c["year"]): c
                  for c in cells if c.get("scope") == "country_btsx"}
    for (code, did, band, year), statuses in sex_components.items():
        suppressed_count = sum(1 for x in statuses if x == "suppressed")
        if suppressed_count == 0:
            continue
        key = (code, did, band, year)
        c = btsx_index.get(key)
        if c is None:
            continue
        if suppressed_count >= 1:
            reason = ("complementary:单个性别单元被抑制，合计可反推"
                      if suppressed_count == 1 else
                      "all_components_suppressed:两个性别单元均被抑制")
            _suppress(c, reason)
            suppressed_country_keys.add(key)

    # 区域/全球单元记录被抑制组件数（合计本身仍发布）
    for c in cells:
        if c.get("scope") not in ("who_region", "un_subregion", "global",
                                  "global_total"):
            continue
        node = nodes[c["node_hash"]]
        n_supp = _count_suppressed_components(store, node, {x["node_hash"]
                                                            for x in cells
                                                            if x["status"] == "suppressed"})
        c["suppressed_components"] = n_supp

    if report_id is None:
        report_id = "report_" + content_hash(
            {"run_id": run_id, "title": title, "cutoff_seq": cutoff,
             "min_sample": min_sample})[:16]
    for c in cells:
        c["report_id"] = report_id
    store.save_report(
        {"report_id": report_id, "run_id": run_id, "title": title,
         "cutoff_seq": cutoff, "min_sample": min_sample}, cells)
    return {"report_id": report_id, "run_id": run_id, "cutoff_seq": cutoff,
            "min_sample": min_sample, "cell_count": len(cells),
            "suppressed_count": sum(1 for c in cells
                                    if c["status"] == "suppressed")}


def _base_cell(node: dict, run_id: str, scope: str, dim_key: list) -> dict:
    return {
        "report_id": None, "cell_key": node["node_key"], "run_id": run_id,
        "node_hash": node["node_hash"], "scope": scope, "dim_key": dim_key,
        "sex": node.get("sex_id") or "BTSX",
        "age_band": node.get("band_id") or "ALL",
        "disease_id": node.get("disease_id") or "ALL",
        "year": node.get("year"),
        "value": node.get("value"), "unc_low": node.get("unc_low"),
        "unc_high": node.get("unc_high"), "status": "published",
        "basis": node.get("basis"), "method": node.get("method"),
        "suppressed_reason": None}


def _cell_from_country_sex(store: EventStore, node: dict, run_id: str,
                           min_sample: int) -> dict:
    dim_key = [node["country_code"], node["disease_id"], node["band_id"],
               node["sex_id"], node["year"]]
    cell = _base_cell(node, run_id, "country", dim_key)
    cell["country_code"] = node["country_code"]
    reason = _primary_suppression_reason(store, node["node_hash"], min_sample)
    if reason:
        _suppress(cell, reason)
    return cell


def _cell_from_btsx(node: dict, run_id: str) -> dict:
    dim_key = [node["country_code"], node["disease_id"], node["band_id"],
               "BTSX", node["year"]]
    cell = _base_cell(node, run_id, "country_btsx", dim_key)
    cell["country_code"] = node["country_code"]
    return cell


def _cell_from_region(node: dict, run_id: str) -> dict:
    scope = node["scope"]
    if scope == "who_region":
        scope_id = node["who_region"]
    elif scope == "un_subregion":
        scope_id = node["un_subregion"]
    elif scope == "global_total":
        scope_id = "TOTAL"
    else:
        scope_id = "GLOBAL"
    dim_key = [scope, scope_id, node.get("disease_id") or "ALL",
               node.get("band_id") or "ALL",
               node.get("sex_id") or "BTSX", node["year"]]
    cell = _base_cell(node, run_id, scope, dim_key)
    cell["scope_id"] = scope_id
    return cell


def _suppress(cell: dict, reason: str) -> None:
    cell["status"] = "suppressed"
    cell["suppressed_reason"] = reason
    cell["value"] = None
    cell["unc_low"] = None
    cell["unc_high"] = None


def _prevalence_sample_sizes(store: EventStore, node_hash: str) -> list[int]:
    """沿血缘找到全部暴露主张叶节点的样本量（含插值锚点）。"""
    sizes = []
    for n in store.lineage(node_hash):
        if n.get("leaf_kind") == "claim" and n.get("indicator_id") == "SHS_PREV":
            if n.get("sample_size") is not None:
                sizes.append(n["sample_size"])
    return sizes


def _primary_suppression_reason(store: EventStore, node_hash: str,
                                min_sample: int) -> str | None:
    sizes = _prevalence_sample_sizes(store, node_hash)
    if not sizes:
        return "sample_size_unknown:暴露输入未携带调查样本量，无法核验最小样本规则"
    if min(sizes) < min_sample:
        return f"small_sample:最小调查样本量 {min(sizes)} < {min_sample}"
    return None


def _count_suppressed_components(store: EventStore, node: dict,
                                 suppressed_hashes: set[str]) -> int:
    count = 0
    for dep in store.lineage(node["node_hash"]):
        if dep["node_hash"] in suppressed_hashes:
            count += 1
    return count


# ---------------------------------------------------------------------------
# 撤回影响标注（只追加，不删改）
# ---------------------------------------------------------------------------

def annotate_impacts(store: EventStore, report_id: str) -> dict:
    """根据当前未决的撤回标志，标出报告中血缘受污染的单元。

    返回新增的受影响标注数。重复执行幂等（同一单元同一原因只标一次）。
    """
    report = store.get_report(report_id)
    if report is None:
        raise KeyError(report_id)
    cells = store.report_cells(report_id)

    retraction_flags = [f for f in store.flags(include_resolved=False)
                        if f["kind"] in ("source_retracted",
                                         "parameter_withdrawn")]
    if not retraction_flags:
        return {"report_id": report_id, "new_annotations": 0, "affected": []}

    added, affected = 0, []
    for cell in cells:
        chain = store.lineage(cell["node_hash"])
        claim_hashes = {n["node_hash"] for n in chain
                        if n.get("leaf_kind") == "claim"}
        risk_ids = set()
        for n in chain:
            if n.get("leaf_kind") == "risk_param":
                rid = n.get("risk_id") or n.get("payload", {}).get("risk_id")
                if rid:
                    risk_ids.add(rid)
        for flag in retraction_flags:
            reason_hit = None
            if (flag["kind"] == "source_retracted"
                    and flag["payload"].get("claim_hash") in claim_hashes):
                reason_hit = f"输入来源已撤回：{flag['reason']}"
            elif (flag["kind"] == "parameter_withdrawn"
                  and flag["target_id"] in risk_ids):
                reason_hit = f"风险参数已撤回：{flag['reason']}"
            if reason_hit is None:
                continue
            existing = any(f["flag_id"] == f"impact:{report_id}:{cell['cell_key']}:{flag['flag_id']}"
                           for f in store.flags())
            if existing:
                continue
            ev = store.append("report_annotation", f"report:{report_id}", {
                "report_id": report_id, "cell_key": cell["cell_key"],
                "node_hash": cell["node_hash"],
                "source_flag": flag["flag_id"],
                "dimensions": {"disease_id": cell["disease_id"],
                               "sex": cell["sex"],
                               "age_band": cell["age_band"],
                               "year": cell["year"]},
                "reason": reason_hit})
            store.add_flag({
                "flag_id": f"impact:{report_id}:{cell['cell_key']}:{flag['flag_id']}",
                "kind": "affected_conclusion",
                "target_type": "report_cell", "target_id": cell["cell_key"],
                "reason": reason_hit, "report_id": report_id,
                "run_id": report["run_id"], "node_key": cell["cell_key"],
                "created_seq": ev.seq,
                "payload": {"source_flag": flag["flag_id"],
                            "annotation_seq": ev.seq,
                            "node_hash": cell["node_hash"],
                            "dimensions": {"disease_id": cell["disease_id"],
                                           "sex": cell["sex"],
                                           "age_band": cell["age_band"],
                                           "year": cell["year"]}}})
            added += 1
            affected.append({"cell_key": cell["cell_key"], "seq": ev.seq,
                             "reason": reason_hit,
                             "node_hash": cell["node_hash"]})
    return {"report_id": report_id, "new_annotations": added,
            "affected": affected}


def report_view(store: EventStore, report_id: str) -> dict:
    """读取报告视图：不可变单元 + 追加的影响标注（旧报告永不被改写）。"""
    report = store.get_report(report_id)
    if report is None:
        raise KeyError(report_id)
    cells = store.report_cells(report_id)
    flags = [f for f in store.flags(target_type="report_cell")
             if f["report_id"] == report_id]
    flags_by_cell: dict[str, list[dict]] = {}
    for f in flags:
        flags_by_cell.setdefault(f["node_key"], []).append(
            {"kind": f["kind"], "reason": f["reason"],
             "created_seq": f["created_seq"]})
    for c in cells:
        c["annotations"] = flags_by_cell.get(c["cell_key"], [])
        c["affected_by_retraction"] = bool(c["annotations"])
    return {**report, "cells": cells,
            "annotation_count": len(flags),
            "affected_cell_count": len(flags_by_cell)}


def supersede(store: EventStore, old_report_id: str, new_report_id: str) -> None:
    """标注新旧报告替代关系；旧报告仍然保留、可读、可复现。"""
    store.mark_superseded(old_report_id, new_report_id)


# ---------------------------------------------------------------------------
# 数字血缘与完整性核验
# ---------------------------------------------------------------------------

def explain_number(store: EventStore, node_hash: str) -> dict:
    """给出某个数字的完整可追溯说明：公式版本、风险参数、输入主张、估算方法。"""
    chain = store.lineage(node_hash)
    claims, risks, formulas, indicators, mapping_nodes = [], [], [], [], []
    for n in chain:
        kind = n.get("leaf_kind")
        if kind == "claim":
            claims.append({"claim_hash": n["node_hash"], "source_id": n.get("source_id"),
                           "source_kind": n.get("source_kind"),
                           "indicator_id": n.get("indicator_id"),
                           "country_code": n.get("country_code"),
                           "year": n.get("year"), "sex_id": n.get("sex_id"),
                           "band_id": n.get("band_id"), "value": n.get("value"),
                           "sample_size": n.get("sample_size"),
                           "seq": n.get("claim_seq")})
        elif kind == "risk_param":
            p = n.get("payload", {})
            risks.append({"risk_id": p.get("risk_id"),
                          "version": p.get("version"), "rr": p.get("rr"),
                          "hash": n["node_hash"]})
        elif kind == "formula":
            p = n.get("payload", {})
            formulas.append({"formula_id": p.get("formula_id"),
                             "version": p.get("version"),
                             "expression": p.get("expression"),
                             "hash": n["node_hash"]})
        elif kind == "indicator":
            p = n.get("payload", {})
            indicators.append({"indicator_id": p.get("indicator_id"),
                               "version": p.get("version"),
                               "hash": n["node_hash"]})
        elif kind == "region_mapping":
            mapping_nodes.append(n["node_hash"])
    target = store.node_by_hash(node_hash)
    return {"node_hash": node_hash, "node_key": target["node_key"],
            "value": target.get("value"), "unc_low": target.get("unc_low"),
            "unc_high": target.get("unc_high"), "basis": target.get("basis"),
            "method": target.get("method"),
            "lineage_size": len(chain),
            "inputs": {"claims": claims, "risk_params": _dedupe(risks),
                       "formulas": _dedupe(formulas),
                       "indicators": _dedupe(indicators),
                       "mapping_hashes": sorted(set(mapping_nodes))}}


def _dedupe(items: list[dict]) -> list[dict]:
    seen, out = set(), []
    for it in items:
        key = it.get("hash")
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def verify_report(store: EventStore, report_id: str) -> dict:
    """完整性核验：每个单元的节点哈希仍存在且数值与冻结时一致。"""
    report = store.get_report(report_id)
    if report is None:
        raise KeyError(report_id)
    ok, bad = True, []
    for cell in store.report_cells(report_id):
        node = store.node_by_hash(cell["node_hash"])
        if node is None:
            ok = False
            bad.append({"cell_key": cell["cell_key"], "problem": "node_missing"})
            continue
        if cell["status"] == "published":
            if (node.get("value") != cell["value"]
                    or node.get("unc_low") != cell["unc_low"]
                    or node.get("unc_high") != cell["unc_high"]):
                ok = False
                bad.append({"cell_key": cell["cell_key"],
                            "problem": "value_drift",
                            "stored": {"value": cell["value"],
                                       "unc_low": cell["unc_low"],
                                       "unc_high": cell["unc_high"]},
                            "current": {"value": node.get("value"),
                                        "unc_low": node.get("unc_low"),
                                        "unc_high": node.get("unc_high")}})
    return {"report_id": report_id, "intact": ok, "problems": bad}
