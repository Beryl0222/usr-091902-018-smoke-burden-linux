"""来源登记与观测数据导入。

三类来源：``literature``（文献结果）、``survey``（人口调查，含抽样设计元数据）、
``model``（外部模型输出）。

行为约定
--------

* 重复导入合并：同一来源、同一自然键、内容完全相同 → 返回既有事件，不产生新版本。
* 更正只产生新快照：同一来源同一自然键但值不同 → 追加新版本，旧快照永久保留。
* 竞争保留：不同来源对同一自然键给出不同值 → 各自保留，读模型状态为 ``conflict``，
  必须经 ``adjudicate`` 裁定后才会进入计算。
* 论文撤回：来源级撤回事件；其全部主张标记 ``retracted``，未来运行排除，
  旧报告不删除，只追加受影响标注。
"""

from __future__ import annotations

from .store import EventStore, content_hash

VALID_SOURCE_KINDS = ("literature", "survey", "model")

# 自然键：一条观测"在哪里"（与数值无关）
NATURAL_KEY_FIELDS = ("country_code", "year", "sex_id", "band_id", "indicator_id")


def _natural_key_hash(obs: dict) -> str:
    return content_hash({k: obs[k] for k in NATURAL_KEY_FIELDS})


def register_source(store: EventStore, source_id: str, kind: str, title: str,
                    *, citation: str | None = None, doi: str | None = None,
                    year: int | None = None,
                    survey_design: dict | None = None,
                    note: str | None = None) -> dict:
    """登记来源。调查必须提供抽样设计元数据（设计、样本量、加权、问题口径版本）。

    同内容重复登记幂等合并；字段变更产生新版本快照。
    """
    if kind not in VALID_SOURCE_KINDS:
        raise ValueError(f"未知来源类型：{kind}")
    if kind == "survey":
        survey_design = survey_design or {}
        for required in ("design", "sample_size", "weighting", "questions_version"):
            if not survey_design.get(required):
                raise ValueError(f"调查来源缺少抽样元数据字段：{required}")
    payload = {
        "source_id": source_id, "kind": kind, "title": title,
        "citation": citation, "doi": doi, "year": year,
        "survey_design": survey_design, "note": note,
    }
    ev = store.append("source_registered", f"source:{source_id}", payload)
    was_known = store.aggregate_has_hash(f"source:{source_id}", ev.payload_hash)
    return {"status": "merged" if was_known and ev.version > 1 else "recorded",
            "source_id": source_id, "seq": ev.seq, "version": ev.version,
            "payload_hash": ev.payload_hash}


def import_observation(store: EventStore, source_id: str, obs: dict) -> dict:
    """导入一条观测值。

    ``obs`` 必须含自然键字段与 ``value``；可选 ``unc_low``/``unc_high``/
    ``sample_size``。返回状态：``merged``（重复导入合并）/``recorded``（首次）/
    ``corrected``（更正，新快照）。
    """
    source = _source(store, source_id)
    if source is None:
        raise KeyError(f"来源未登记：{source_id}")
    for k in NATURAL_KEY_FIELDS:
        if obs.get(k) is None:
            raise ValueError(f"观测缺少自然键字段：{k}")
    if "value" not in obs:
        raise ValueError("观测缺少 value")

    payload = {
        "source_id": source_id,
        "natural_key_hash": _natural_key_hash(obs),
        "country_code": obs["country_code"], "year": int(obs["year"]),
        "sex_id": obs["sex_id"], "band_id": obs["band_id"],
        "indicator_id": obs["indicator_id"],
        "value": obs["value"],
        "unc_low": obs.get("unc_low"), "unc_high": obs.get("unc_high"),
        "sample_size": obs.get("sample_size"),
        "source_kind": source["kind"],
        "source_version_hash": _source_version_hash(store, source_id),
        "sampling": source.get("survey_design") if source["kind"] == "survey" else None,
        "basis": "observed",
    }
    aggregate = f"claim:{source_id}:{payload['natural_key_hash']}"
    prior = [e for e in store.aggregate_versions(aggregate)
             if e.event_type == "claim_imported"]
    payload_hash = content_hash(payload)
    was_known = store.aggregate_has_hash(aggregate, payload_hash)
    ev = store.append("claim_imported", aggregate, payload)
    if was_known:
        status = "merged"
    elif prior:
        status = "corrected"
    else:
        status = "recorded"
    result = {"status": status, "source_id": source_id,
              "claim_aggregate": aggregate, "seq": ev.seq, "version": ev.version,
              "claim_hash": ev.payload_hash,
              "natural_key_hash": payload["natural_key_hash"]}
    if status == "corrected":
        result["superseded_claim_hash"] = prior[-1].payload_hash
        result["new_claim_hash"] = ev.payload_hash

    # 异源同键且值不同 → 竞争关系，挂待裁定标志（裁定后解除）
    active = [c for c in _claims_for(store, payload["natural_key_hash"])
              if c["status"] == "active"]
    others = {c["source_id"] for c in active if c["source_id"] != source_id}
    if others and len({c["value"] for c in active}) > 1:
        store.add_flag({
            "flag_id": f"conflict:{payload['natural_key_hash']}",
            "kind": "conflict_pending", "target_type": "claim_set",
            "target_id": payload["natural_key_hash"],
            "reason": "不同来源对同一指标单元给出不同数值，等待裁定",
            "node_key": None, "run_id": None, "report_id": None,
            "created_seq": ev.seq,
            "payload": {"source_ids": sorted(others | {source_id})}})
        result["conflict"] = True
    return result


def retract_paper(store: EventStore, source_id: str, reason: str) -> dict:
    """撤回文献来源（论文撤稿）。追加撤回事件并对其全部主张打标，不删除任何数据。"""
    if _source(store, source_id) is None:
        raise KeyError(f"来源未登记：{source_id}")
    ev = store.append("paper_retracted", f"source:{source_id}",
                      {"source_id": source_id, "reason": reason})
    affected = [e for e in store.events("claim_imported")
                if e.payload["source_id"] == source_id]
    for c in affected:
        store.add_flag({
            "flag_id": f"retraction:{source_id}:{c.payload_hash}",
            "kind": "source_retracted", "target_type": "claim",
            "target_id": c.aggregate,
            "reason": f"来源论文撤回：{reason}",
            "node_key": None, "run_id": None, "report_id": None,
            "created_seq": ev.seq,
            "payload": {"source_id": source_id, "claim_hash": c.payload_hash}})
    return {"status": "retracted", "source_id": source_id, "seq": ev.seq,
            "affected_claims": len(affected)}


def adjudicate(store: EventStore, natural_key: dict, winner_source_id: str,
               rationale: str, adjudicator: str) -> dict:
    """对同一自然键上的竞争主张做出裁定。裁定本身版本化，可再次裁定。"""
    nkh = _natural_key_hash(natural_key)
    claims = _claims_for(store, nkh)
    active = [c for c in claims if c["status"] == "active"]
    winner = next((c for c in active if c["source_id"] == winner_source_id), None)
    if winner is None:
        raise ValueError(f"来源 {winner_source_id} 对该自然键没有有效主张")
    competing = [c["claim_hash"] for c in active if c["source_id"] != winner_source_id]
    payload = {"natural_key": {k: natural_key[k] for k in NATURAL_KEY_FIELDS},
               "natural_key_hash": nkh,
               "winner_claim_hash": winner["claim_hash"],
               "winner_source_id": winner_source_id,
               "superseded_claim_hashes": competing,
               "rationale": rationale, "adjudicator": adjudicator}
    ev = store.append("claim_adjudicated", f"adjudication:{nkh}", payload)
    store.resolve_flags("claim_set", nkh)
    return {"status": "adjudicated", "seq": ev.seq, "version": ev.version,
            "winner_source_id": winner_source_id,
            "winner_claim_hash": winner["claim_hash"],
            "superseded_claim_hashes": competing}


# —— 读模型 ——

def _source(store: EventStore, source_id: str, until_seq: int | None = None):
    versions = [e for e in store.aggregate_versions(f"source:{source_id}")
                if e.event_type == "source_registered"
                and (until_seq is None or e.seq <= until_seq)]
    return versions[-1].payload if versions else None


def _source_version_hash(store: EventStore, source_id: str) -> str:
    versions = [e for e in store.aggregate_versions(f"source:{source_id}")
                if e.event_type == "source_registered"]
    return versions[-1].payload_hash


def is_source_retracted(store: EventStore, source_id: str,
                        until_seq: int | None = None) -> bool:
    return any(e.seq <= until_seq if until_seq else True
               for e in store.events("paper_retracted", until_seq)
               if e.payload["source_id"] == source_id)


def _claims_for(store: EventStore, natural_key_hash: str,
                until_seq: int | None = None) -> list[dict]:
    out = []
    for ev in store.events("claim_imported", until_seq):
        if ev.payload["natural_key_hash"] != natural_key_hash:
            continue
        latest_version = max(
            e.version for e in store.aggregate_versions(ev.aggregate)
            if e.event_type == "claim_imported"
            and (until_seq is None or e.seq <= until_seq))
        if ev.version != latest_version:
            status = "superseded"
        elif is_source_retracted(store, ev.payload["source_id"], until_seq):
            status = "retracted"
        else:
            status = "active"
        out.append({**ev.payload, "claim_hash": ev.payload_hash,
                    "claim_aggregate": ev.aggregate, "seq": ev.seq,
                    "version": ev.version, "status": status})
    return out


def _adjudication(store: EventStore, natural_key_hash: str,
                  until_seq: int | None = None):
    versions = [e for e in store.aggregate_versions(f"adjudication:{natural_key_hash}")
                if (until_seq is None or e.seq <= until_seq)]
    return versions[-1].payload if versions else None


def observations(store: EventStore, *, indicator_id: str, country_code: str,
                 sex_id: str, band_id: str,
                 until_seq: int | None = None) -> list[dict]:
    """列出某单元（各年份）的全部主张视图。"""
    result = []
    for ev in store.events("claim_imported", until_seq):
        p = ev.payload
        if (p["indicator_id"], p["country_code"], p["sex_id"], p["band_id"]) != (
                indicator_id, country_code, sex_id, band_id):
            continue
        claims = _claims_for(store, p["natural_key_hash"], until_seq)
        result.extend(c for c in claims if c["claim_hash"] == ev.payload_hash)
    return result


def resolve_cell(store: EventStore, *, indicator_id: str, country_code: str, year: int,
                 sex_id: str, band_id: str, until_seq: int | None = None) -> dict:
    """解析单个自然键的证据状态。

    返回：
      {state: observed|conflict|none|retracted, claim?, competitors?, adjudication?}
    """
    nkh = content_hash({"country_code": country_code, "year": year,
                        "sex_id": sex_id, "band_id": band_id,
                        "indicator_id": indicator_id})
    claims = _claims_for(store, nkh, until_seq)
    if not claims:
        return {"state": "none", "natural_key_hash": nkh, "year": year}
    active = [c for c in claims if c["status"] == "active"]
    if not active:
        return {"state": "retracted", "natural_key_hash": nkh, "year": year,
                "claims": claims}
    adjudication = _adjudication(store, nkh, until_seq)
    if adjudication:
        winner = next((c for c in active
                       if c["claim_hash"] == adjudication["winner_claim_hash"]), None)
        if winner is not None:
            return {"state": "observed", "natural_key_hash": nkh, "year": year,
                    "claim": winner, "adjudication": adjudication,
                    "competitors": [c for c in active if c is not winner]}
        # 胜方主张已被更正或撤回 → 旧裁定失效，回到待裁定
        return {"state": "conflict", "natural_key_hash": nkh, "year": year,
                "competitors": active,
                "adjudication_stale": adjudication}
    if len(active) == 1:
        return {"state": "observed", "natural_key_hash": nkh, "year": year,
                "claim": active[0]}
    return {"state": "conflict", "natural_key_hash": nkh, "year": year,
            "competitors": active}
