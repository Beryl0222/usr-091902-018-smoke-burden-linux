"""版本化计算引擎：证据序列 → 暴露估算 → PAF → 归因死亡。

每个数字都是一个**内容寻址节点**：

* 叶节点直接采用事件的 ``payload_hash`` 作为节点哈希（观测主张、风险参数、指标
  定义、公式、地区映射）——证据身份即节点身份；
* 计算节点哈希覆盖全部输入哈希与计算口径，输入不变则哈希不变；
* 缺年份的插值/外推节点 ``basis='estimated'`` 并写明方法与锚点，永不标成观测值；
* 运行清单（manifest）锁定 cutoff、公式版本、指标/映射版本与全部输入，运行 id 即
  清单内容哈希——同样的证据与公式必然得到同一 run_id 与同一批节点哈希。

两阶段执行：先在内存中构建完整 DAG（此时不依赖 run_id），算出清单与 run_id 后再
统一把节点挂到本次运行。因此"撤回参数后只重算依赖分支"可直接验证：新运行与父运行
逐键比较，未受影响的节点哈希完全一致（缓存命中），变化的只有依赖了变更输入的分支。
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from . import registry
from .sources import resolve_cell
from .store import EventStore, canonical_dumps, content_hash

DEFAULT_YEARS = tuple(range(2019, 2022))  # 第一版覆盖 2019-2021
MC_DRAWS = 10000
MC_SEED = 20260922


@dataclass
class RunConfig:
    rationale: str = "常规计算"
    formula_id: str = "PAF_LEVIN"
    formula_version: int = 1
    years: tuple[int, ...] = DEFAULT_YEARS
    country_codes: tuple[str, ...] | None = None  # None = 目录全部
    parent_run_id: str | None = None
    trigger_seq: int | None = None
    notes: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 缺年份估算：显式标注，绝不冒充观测
# ---------------------------------------------------------------------------

def fill_series(observed: dict[int, dict], years: tuple[int, ...]) -> dict[int, dict]:
    """把观测年份映射补成完整年份序列。

    * ``basis='observed'``：直接采用当年主张；
    * ``basis='estimated'``：
        - 两侧都有锚点 → ``linear_interpolation``（区间同步线性插值）；
        - 仅一侧有锚点 → ``nearest_extrapolation``（就近持平，区间沿用锚点）；
    * ``basis='missing'``：全段无任何观测，明确留空，禁止伪造数值。
    """
    out: dict[int, dict] = {}
    obs_years = sorted(observed)
    for year in years:
        if year in observed:
            out[year] = {"basis": "observed", "value": observed[year]["value"],
                         "unc_low": observed[year].get("unc_low"),
                         "unc_high": observed[year].get("unc_high"),
                         "claim": observed[year], "anchor_years": [year]}
            continue
        if not obs_years:
            out[year] = {"basis": "missing", "anchor_years": []}
            continue
        before = [y for y in obs_years if y < year]
        after = [y for y in obs_years if y > year]
        if before and after:
            y0, y1 = before[-1], after[0]
            a, b = observed[y0], observed[y1]
            t = (year - y0) / (y1 - y0)
            out[year] = {
                "basis": "estimated", "method": "linear_interpolation",
                "value": a["value"] + t * (b["value"] - a["value"]),
                "unc_low": _lerp_optional(a.get("unc_low"), b.get("unc_low"), t),
                "unc_high": _lerp_optional(a.get("unc_high"), b.get("unc_high"), t),
                "anchor_years": [y0, y1]}
        else:
            anchor_year = before[-1] if before else after[0]
            a = observed[anchor_year]
            out[year] = {
                "basis": "estimated", "method": "nearest_extrapolation",
                "value": a["value"], "unc_low": a.get("unc_low"),
                "unc_high": a.get("unc_high"), "anchor_years": [anchor_year]}
    return out


def _lerp_optional(a, b, t):
    if a is None or b is None:
        return None
    return a + t * (b - a)


# ---------------------------------------------------------------------------
# 版本化公式
# ---------------------------------------------------------------------------

def levin_paf(p: float, rr: float) -> float:
    return p * (rr - 1.0) / (1.0 + p * (rr - 1.0))


def paf_with_uncertainty(p: float, p_low: float | None, p_high: float | None,
                         rr: float, rr_low: float, rr_high: float,
                         version: int) -> tuple[float, float, float]:
    """按公式版本计算 PAF 与 95% 区间。

    v1：解析法——对 RR 的对数对称区间逐界代入 Levin 公式取包络；
    v2：蒙特卡洛——RR 取对数正态、P 取正态（有区间时），10000 次抽样取
    2.5/97.5 分位数，固定随机种子保证可复现。
    """
    p_low = p if p_low is None else p_low
    p_high = p if p_high is None else p_high
    if version == 1:
        vals = [levin_paf(x, y) for x in (p_low, p, p_high)
                for y in (rr_low, rr, rr_high)]
        return levin_paf(p, rr), min(vals), max(vals)
    if version == 2:
        rng = random.Random(MC_SEED)
        se_log_rr = (math.log(rr) - math.log(rr_low)) / 1.96
        se_p = (p_high - p_low) / (2 * 1.96) if p_high > p_low else 0.0
        draws = []
        for _ in range(MC_DRAWS):
            rr_d = math.exp(rng.gauss(math.log(rr), se_log_rr))
            p_d = min(1.0, max(0.0, rng.gauss(p, se_p)))
            draws.append(levin_paf(p_d, rr_d))
        draws.sort()
        return (levin_paf(p, rr), draws[int(0.025 * MC_DRAWS)],
                draws[int(0.975 * MC_DRAWS)])
    raise ValueError(f"不支持的公式版本：{version}")


# ---------------------------------------------------------------------------
# 引擎
# ---------------------------------------------------------------------------

class Engine:
    def __init__(self, store: EventStore):
        self.store = store
        self.cache_hits = 0

    def run(self, config: RunConfig, *, cutoff_seq: int | None = None) -> dict:
        store = self.store
        cutoff = store.head_seq() if cutoff_seq is None else cutoff_seq
        self.cache_hits = 0

        country_map = registry.countries(store, cutoff)
        mapping = registry.region_mapping(store, cutoff)
        codes = config.country_codes or tuple(sorted(country_map))
        diseases = registry.vocab(store, "diseases", cutoff)
        bands = registry.vocab(store, "age_bands", cutoff)
        formula_def = registry.formula(store, config.formula_id,
                                       config.formula_version, cutoff)
        if formula_def is None:
            raise ValueError("指定的公式版本在 cutoff 时点不存在")
        indicator_defs = {i: registry.indicator(store, i, cutoff)
                          for i in ("SHS_PREV", "POP", "DEATHS_BASE")}

        warnings: list[dict] = []
        nodes: dict[str, dict] = {}       # node_hash -> node（本次 DAG）
        leaves: dict[str, str] = {}       # 输入引用键 -> leaf_hash（清单用）
        attr_index: dict[tuple, str] = {} # (code,dis,band,sex,year) -> attr hash

        evidence = self._build_evidence_index(cutoff)
        # 风险参数按 (疾病,性别,年龄段) 预取一次（含其版本事件哈希）
        risk_cache: dict[tuple, tuple[dict, str] | None] = {}

        def risk_for(did, sex_id, band_id):
            key = (did, sex_id, band_id)
            if key not in risk_cache:
                params = registry.risk_params_for(store, did, sex_id, band_id,
                                                  until_seq=cutoff)
                if not params:
                    risk_cache[key] = None
                else:
                    rp = params[0]
                    ev = next(e for e in store.aggregate_versions(
                        f"risk_param:{rp['risk_id']}")
                        if e.event_type == "risk_param_version"
                        and e.payload["version"] == rp["version"]
                        and e.seq <= cutoff)
                    risk_cache[key] = (rp, ev.payload_hash)
            return risk_cache[key]

        formula_hash = self._definition_leaf(
            nodes, "formula", f"formula:{config.formula_id}:v{config.formula_version}",
            formula_hash_=content_hash(formula_def), payload=formula_def,
            ref_key="formula", leaves=leaves)
        mapping_hash = self._definition_leaf(
            nodes, "region_mapping", "mapping:country_region",
            content_hash(mapping), {"rows_hash": content_hash(mapping)},
            ref_key="region_mapping", leaves=leaves)
        ind_hashes = {}
        for iid, idef in indicator_defs.items():
            ind_hashes[iid] = self._definition_leaf(
                nodes, "indicator", f"indicator:{iid}", content_hash(idef), idef,
                ref_key=f"indicator:{iid}", leaves=leaves)

        for code in codes:
            if code not in country_map:
                warnings.append({"type": "unknown_country", "country_code": code})
                continue
            for disease in diseases:
                did = disease["disease_id"]
                eligible = [b["band_id"] for b in bands
                            if b["pediatric"] == disease["pediatric"]]
                for band_id in eligible:
                    for sex_id in ("FMLE", "MLE"):
                        self._cell(code, did, band_id, sex_id, config, cutoff,
                                   formula_hash, ind_hashes, nodes, leaves,
                                   attr_index, warnings, evidence, risk_for)

        # 聚合：两性合计 → WHO 区域 → 全球（均为内容寻址节点，依赖映射版本）
        rollups = self._aggregate(codes, country_map, config.years, diseases, bands,
                                  mapping_hash, nodes, attr_index)

        manifest = {
            "parent_run_id": config.parent_run_id,
            "rationale": config.rationale,
            "trigger_seq": config.trigger_seq,
            "cutoff_seq": cutoff,
            "formula": {"formula_id": config.formula_id,
                        "version": config.formula_version, "hash": formula_hash},
            "indicators": [{"indicator_id": i, "version": d["version"],
                            "hash": ind_hashes[i]} for i, d in indicator_defs.items()],
            "mapping_hash": mapping_hash,
            "years": list(config.years), "countries": list(codes),
            "inputs": sorted(leaves.items()),
            "warnings": warnings,
            "nodes": sorted((n["node_key"], h) for h, n in nodes.items()),
            "rollups": rollups,
            "notes": config.notes,
        }
        run_id = "run_" + content_hash(manifest)[:16]
        store.save_run(run_id, config.parent_run_id, config.rationale,
                       config.trigger_seq, f"{config.formula_id}@v{config.formula_version}",
                       "completed", manifest)
        for node in nodes.values():
            store.save_node(node, run_id)
        return {"run_id": run_id, "cutoff_seq": cutoff,
                "node_count": len(nodes), "cache_hits": self.cache_hits,
                "warnings": warnings, "manifest": manifest,
                "global_node_keys": rollups["global"]}

    # ------------------------------------------------------------------

    def _definition_leaf(self, nodes, kind, node_key, formula_hash_, payload,
                         ref_key, leaves):
        if formula_hash_ in nodes:
            leaves[ref_key] = formula_hash_
            return formula_hash_
        existing = self.store.node_by_hash(formula_hash_)
        if existing is not None:
            self.cache_hits += 1
            nodes[formula_hash_] = existing
        else:
            nodes[formula_hash_] = {
                "node_hash": formula_hash_, "node_key": f"leaf:{kind}:{formula_hash_[:12]}",
                "kind": "leaf", "leaf_kind": kind, "basis": "definition",
                "method": None, "deps": [], "payload": payload}
        leaves[ref_key] = formula_hash_
        return formula_hash_

    def _claim_leaf(self, nodes, leaves, claim) -> str:
        h = claim["claim_hash"]
        if h not in nodes:
            existing = self.store.node_by_hash(h)
            if existing is not None:
                self.cache_hits += 1
                nodes[h] = existing
            else:
                nodes[h] = {
                    "node_hash": h,
                    "node_key": f"leaf:claim:{h[:12]}",
                    "kind": "leaf", "leaf_kind": "claim", "basis": "observed",
                    "method": None, "deps": [],
                    "source_id": claim["source_id"],
                    "source_kind": claim["source_kind"],
                    "indicator_id": claim["indicator_id"],
                    "country_code": claim["country_code"], "year": claim["year"],
                    "sex_id": claim["sex_id"], "band_id": claim["band_id"],
                    "value": claim["value"], "unc_low": claim.get("unc_low"),
                    "unc_high": claim.get("unc_high"),
                    "sample_size": claim.get("sample_size"),
                    "claim_seq": claim["seq"]}
        leaves[f"claim:{h}"] = h
        return h

    def _make(self, nodes, node_key, kind, content: dict, deps: list[str]) -> str:
        node = {"node_key": node_key, "kind": kind, **content,
                "deps": sorted(set(deps))}
        nh = content_hash(node)
        if nh not in nodes:
            existing = self.store.node_by_hash(nh)
            if existing is not None:
                self.cache_hits += 1
                nodes[nh] = existing
            else:
                nodes[nh] = {"node_hash": nh, **node}
        return nh

    def _build_evidence_index(self, cutoff: int) -> dict:
        """一次性构建 cutoff 时点的证据快照，避免逐单元扫描事件。

        返回 {"claims": {(indicator,country,sex,band,year): [claim_view...]},
              "retracted_sources": set, "adjudications": {nkh: payload}}
        """
        store = self.store
        retracted = {e.payload["source_id"]
                     for e in store.events("paper_retracted", cutoff)}
        claims_by_key: dict[tuple, list] = {}
        # 同一聚合只取 cutoff 内最新版本（更正链），旧快照仍在事件历史中
        latest_by_agg: dict[str, dict] = {}
        for ev in store.events("claim_imported", cutoff):
            latest_by_agg[ev.aggregate] = {
                "payload": ev.payload, "hash": ev.payload_hash,
                "aggregate": ev.aggregate, "seq": ev.seq}
        for view in latest_by_agg.values():
            p = view["payload"]
            status = ("retracted" if p["source_id"] in retracted else "active")
            claim = {**p, "claim_hash": view["hash"],
                     "claim_aggregate": view["aggregate"],
                     "seq": view["seq"], "version": 1, "status": status}
            key = (p["indicator_id"], p["country_code"], p["sex_id"],
                   p["band_id"], p["year"])
            claims_by_key.setdefault(key, []).append(claim)
        adjudications = {}
        for ev in store.events("claim_adjudicated", cutoff):
            adjudications[ev.payload["natural_key_hash"]] = ev.payload
        return {"claims": claims_by_key, "retracted": retracted,
                "adjudications": adjudications}

    def _resolve(self, evidence, *, indicator_id, country_code, year, sex_id,
                 band_id) -> dict:
        """基于证据快照解析自然键（与 sources.resolve_cell 语义一致，O(1)）。"""
        key = (indicator_id, country_code, sex_id, band_id, year)
        active = [c for c in evidence["claims"].get(key, [])
                  if c["status"] == "active"]
        if not active:
            return {"state": "retracted" if evidence["claims"].get(key) else "none",
                    "year": year}
        nkh = active[0]["natural_key_hash"]
        adjudication = evidence["adjudications"].get(nkh)
        if adjudication:
            winner = next((c for c in active
                           if c["claim_hash"] == adjudication["winner_claim_hash"]),
                          None)
            if winner is not None:
                return {"state": "observed", "year": year, "claim": winner,
                        "adjudication": adjudication,
                        "competitors": [c for c in active if c is not winner]}
            # 胜方主张已被更正/撤回：旧裁定失效，按冲突处理（不静默取值）
            return {"state": "conflict", "year": year, "competitors": active,
                    "adjudication_stale": adjudication}
        if len(active) == 1:
            return {"state": "observed", "year": year, "claim": active[0]}
        return {"state": "conflict", "year": year, "competitors": active}

    def _observed_series(self, evidence, code, indicator_id, sex_id, band_id,
                         years, warnings):
        observed = {}
        for year in years:
            cell = self._resolve(evidence, indicator_id=indicator_id,
                                 country_code=code, year=year, sex_id=sex_id,
                                 band_id=band_id)
            if cell["state"] == "observed":
                observed[year] = cell["claim"]
            elif cell["state"] == "conflict":
                warnings.append({"type": "unadjudicated_conflict",
                                 "country_code": code, "indicator_id": indicator_id,
                                 "sex_id": sex_id, "band_id": band_id, "year": year,
                                 "sources": [c["source_id"]
                                             for c in cell["competitors"]]})
        return observed

    def _cell(self, code, did, band_id, sex_id, config, cutoff, formula_hash,
              ind_hashes, nodes, leaves, attr_index, warnings, evidence, risk_for):
        years = config.years
        prev_obs = self._observed_series(evidence, code, "SHS_PREV", sex_id, band_id,
                                         years, warnings)
        if not prev_obs:
            return
        series = fill_series(prev_obs, years)

        risk_entry = risk_for(did, sex_id, band_id)
        if risk_entry is None:
            return
        risk, risk_param_hash = risk_entry
        risk_hash = self._definition_leaf(
            nodes, "risk_param", f"risk_param:{risk['risk_id']}:v{risk['version']}",
            risk_param_hash, risk,
            ref_key=f"risk_param:{risk['risk_id']}:v{risk['version']}", leaves=leaves)
        rr_high = risk["rr"] ** 2 / risk["ci_low"]

        for year in years:
            point = series[year]
            if point["basis"] == "missing":
                continue

            if point["basis"] == "observed":
                prev_hash = self._claim_leaf(nodes, leaves, point["claim"])
                prev_deps = [prev_hash]
            else:
                anchor_hashes = [self._claim_leaf(nodes, leaves, prev_obs[y])
                                 for y in point["anchor_years"]]
                prev_deps = anchor_hashes + [ind_hashes["SHS_PREV"]]
                prev_hash = self._make(
                    nodes, f"prev:{code}:{sex_id}:{band_id}:{year}", "prevalence",
                    {"country_code": code, "year": year, "sex_id": sex_id,
                     "band_id": band_id, "indicator_id": "SHS_PREV",
                     "basis": "estimated",
                     "method": {"name": point["method"],
                                "anchor_years": point["anchor_years"]},
                     "value": point["value"], "unc_low": point.get("unc_low"),
                     "unc_high": point.get("unc_high")}, prev_deps)

            paf, paf_lo, paf_hi = paf_with_uncertainty(
                point["value"], point.get("unc_low"), point.get("unc_high"),
                risk["rr"], risk["ci_low"], rr_high, config.formula_version)
            paf_hash = self._make(
                nodes, f"paf:{code}:{did}:{band_id}:{sex_id}:{year}", "paf",
                {"country_code": code, "year": year, "sex_id": sex_id,
                 "band_id": band_id, "disease_id": did,
                 "basis": point["basis"],
                 "method": {"name": point["method"],
                            "anchor_years": point["anchor_years"]}
                 if point["basis"] == "estimated" else None,
                 "risk_id": risk["risk_id"], "risk_version": risk["version"],
                 "rr": risk["rr"], "rr_ci_low": risk["ci_low"],
                 "rr_ci_high": rr_high,
                 "value": paf, "unc_low": paf_lo, "unc_high": paf_hi},
                prev_deps + [risk_hash, formula_hash, ind_hashes["SHS_PREV"]])

            death_cell = self._resolve(evidence, indicator_id="DEATHS_BASE",
                                       country_code=code, year=year, sex_id=sex_id,
                                       band_id=band_id)
            if death_cell["state"] == "conflict":
                warnings.append({"type": "unadjudicated_conflict",
                                 "country_code": code, "indicator_id": "DEATHS_BASE",
                                 "sex_id": sex_id, "band_id": band_id, "year": year,
                                 "sources": [c["source_id"]
                                             for c in death_cell["competitors"]]})
            if death_cell["state"] != "observed":
                continue
            death_hash = self._claim_leaf(nodes, leaves, death_cell["claim"])
            deaths = death_cell["claim"]["value"]
            attr, attr_lo, attr_hi = paf * deaths, paf_lo * deaths, paf_hi * deaths
            attr_hash = self._make(
                nodes, f"attr:{code}:{did}:{band_id}:{sex_id}:{year}",
                "attributable_deaths",
                {"country_code": code, "year": year, "sex_id": sex_id,
                 "band_id": band_id, "disease_id": did,
                 "basis": point["basis"],
                 "method": {"name": point["method"],
                            "anchor_years": point["anchor_years"]}
                 if point["basis"] == "estimated" else None,
                 "baseline_deaths": deaths,
                 "value": attr, "unc_low": attr_lo, "unc_high": attr_hi},
                [paf_hash, death_hash, ind_hashes["DEATHS_BASE"], formula_hash])
            attr_index[(code, did, band_id, sex_id, year)] = attr_hash

    def _aggregate(self, codes, country_map, years, diseases, bands, mapping_hash,
                   nodes, attr_index) -> dict:
        region_year, subregion_year, global_year = {}, {}, {}
        btsx_keys = []

        # 先按国家×疾病×年龄段×年聚齐分性别节点，每组合计节点只构建一次
        grouped: dict[tuple, dict[str, str]] = {}
        for (code, did, band_id, sex_id, year), h in attr_index.items():
            grouped.setdefault((code, did, band_id, year), {})[sex_id] = h

        for (code, did, band_id, year), by_sex in sorted(grouped.items()):
            sex_hashes = [by_sex[s] for s in ("FMLE", "MLE") if s in by_sex]
            kids = [nodes[h] for h in sex_hashes]
            basis = "estimated" if any(k.get("basis") == "estimated"
                                       for k in kids) else "observed"
            btsx = self._make(
                nodes, f"attr:{code}:{did}:{band_id}:BTSX:{year}",
                "attributable_deaths_aggregate",
                {"scope": "country_btsx", "country_code": code,
                 "disease_id": did, "band_id": band_id,
                 "sex_id": "BTSX", "year": year, "basis": basis,
                 "value": sum(k["value"] for k in kids),
                 "unc_low": sum(k["unc_low"] for k in kids),
                 "unc_high": sum(k["unc_high"] for k in kids)},
                sex_hashes)
            btsx_keys.append(btsx)
            who = country_map[code]["who_region"] or "OTHER"
            subr = country_map[code]["un_subregion"]
            region_year.setdefault((who, did, band_id, year), []).append(btsx)
            subregion_year.setdefault((subr, did, band_id, year), []).append(btsx)
            global_year.setdefault((did, band_id, year), []).append(btsx)

        who_keys, sub_keys, glob_keys = [], [], []
        for (who, did, band_id, year), deps in sorted(region_year.items()):
            kids = [nodes[h] for h in dict.fromkeys(deps)]
            h = self._make(nodes, f"region:{who}:{did}:{band_id}:{year}",
                           "aggregate",
                           {"scope": "who_region", "who_region": who,
                            "disease_id": did, "band_id": band_id, "year": year,
                            "basis": "estimated"
                            if any(k.get("basis") == "estimated" for k in kids)
                            else "observed",
                            "value": sum(k["value"] for k in kids),
                            "unc_low": sum(k["unc_low"] for k in kids),
                            "unc_high": sum(k["unc_high"] for k in kids),
                            "mapping_hash": mapping_hash},
                            list(dict.fromkeys(deps)) + [mapping_hash])
            who_keys.append(h)
        for (subr, did, band_id, year), deps in sorted(subregion_year.items()):
            kids = [nodes[h] for h in dict.fromkeys(deps)]
            h = self._make(nodes, f"subregion:{subr}:{did}:{band_id}:{year}",
                           "aggregate",
                           {"scope": "un_subregion", "un_subregion": subr,
                            "disease_id": did, "band_id": band_id, "year": year,
                            "basis": "estimated"
                            if any(k.get("basis") == "estimated" for k in kids)
                            else "observed",
                            "value": sum(k["value"] for k in kids),
                            "unc_low": sum(k["unc_low"] for k in kids),
                            "unc_high": sum(k["unc_high"] for k in kids),
                            "mapping_hash": mapping_hash},
                            list(dict.fromkeys(deps)) + [mapping_hash])
            sub_keys.append(h)
        for (did, band_id, year), deps in sorted(global_year.items()):
            kids = [nodes[h] for h in dict.fromkeys(deps)]
            h = self._make(nodes, f"global:{did}:{band_id}:{year}", "aggregate",
                           {"scope": "global", "disease_id": did,
                            "band_id": band_id, "year": year,
                            "basis": "estimated"
                            if any(k.get("basis") == "estimated" for k in kids)
                            else "observed",
                            "value": sum(k["value"] for k in kids),
                            "unc_low": sum(k["unc_low"] for k in kids),
                            "unc_high": sum(k["unc_high"] for k in kids),
                            "mapping_hash": mapping_hash},
                           list(dict.fromkeys(deps)) + [mapping_hash])
            glob_keys.append(h)

        # 年度全球全病因合计（对外头条数字）
        global_total_keys = []
        for year in years:
            deps = [h for h in glob_keys
                    if nodes[h].get("year") == year]
            kids = [nodes[h] for h in deps]
            if not kids:
                continue
            h = self._make(nodes, f"global:total:{year}", "aggregate",
                           {"scope": "global_total", "year": year,
                            "basis": "estimated"
                            if any(k.get("basis") == "estimated" for k in kids)
                            else "observed",
                            "value": sum(k["value"] for k in kids),
                            "unc_low": sum(k["unc_low"] for k in kids),
                            "unc_high": sum(k["unc_high"] for k in kids),
                            "mapping_hash": mapping_hash},
                           deps + [mapping_hash])
            global_total_keys.append(h)

        return {"country_btsx": sorted(set(btsx_keys)),
                "who_region": sorted(who_keys), "subregion": sorted(sub_keys),
                "global": sorted(glob_keys),
                "global_total": sorted(global_total_keys)}


# ---------------------------------------------------------------------------
# 运行对比 / 影响面
# ---------------------------------------------------------------------------

def run_diff(store: EventStore, old_run_id: str, new_run_id: str) -> dict:
    """逐节点键比较两次运行。节点键稳定、值由内容哈希标识。"""
    old = {n["node_key"]: n["node_hash"] for n in store.nodes_of_run(old_run_id)}
    new = {n["node_key"]: n["node_hash"] for n in store.nodes_of_run(new_run_id)}
    changed, unchanged, added, removed = {}, [], [], []
    for key in sorted(set(old) | set(new)):
        if key not in old:
            added.append(key)
        elif key not in new:
            removed.append(key)
        elif old[key] != new[key]:
            changed[key] = {"old": old[key], "new": new[key]}
        else:
            unchanged.append(key)
    return {"changed": changed, "unchanged": unchanged,
            "added": added, "removed": removed}


def affected_node_keys(store: EventStore, run_id: str, leaf_hashes: set[str]) -> set[str]:
    """返回某次运行中血缘包含任一指定叶哈希的全部节点键（影响面）。"""
    affected = set()
    for node in store.nodes_of_run(run_id):
        chain = store.lineage(node["node_hash"])
        if any(h in leaf_hashes for h in (n["node_hash"] for n in chain)):
            affected.add(node["node_key"])
    return affected
