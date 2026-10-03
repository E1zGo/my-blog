"""Manual experiment ledger. Plans are evidence snapshots, never execution results."""
import html
import json
import re
from typing import Annotated, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, StringConstraints, model_validator

from .db import dump, now, uid
from .log_analysis import LogPointRef

STATUSES = {"planned": "待开始", "running": "进行中", "completed": "已结束", "blocked": "受阻"}
CHECKS = ["核对代码版本与运行入口", "记录依赖与硬件环境", "确认数据划分与权重来源", "完成小规模试运行", "保存评测协议、指标与日志"]
ShortKey = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
ParamValue = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]


class Input(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class CheckItem(Input):
    label: str = Field(min_length=1, max_length=200)
    done: bool = False


class Metric(Input):
    name: str = Field(min_length=1, max_length=80)
    value: FiniteFloat = Field(ge=-1e100, le=1e100)
    unit: str = Field(default="", max_length=40)
    split: str = Field(default="", max_length=120)
    protocol: str = Field(default="", max_length=500)
    origin: LogPointRef | None = None


class ExperimentFields(Input):
    name: str = Field(min_length=1, max_length=120)
    status: Literal["planned", "running", "completed", "blocked"] = "planned"
    objective: str = Field(default="", max_length=4000)
    environment: str = Field(default="", max_length=8000)
    dataset: str = Field(default="", max_length=500)
    code_ref: str = Field(default="", max_length=500)
    parameters: dict[ShortKey, ParamValue] = Field(default_factory=dict, max_length=40)
    checklist: list[CheckItem] = Field(default_factory=lambda: [CheckItem(label=s) for s in CHECKS], max_length=20)
    metrics: list[Metric] = Field(default_factory=list, max_length=20)
    conclusion: str = Field(default="", max_length=12000)
    log_source_ids: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="before")
    @classmethod
    def line_parameters(cls, data):
        parameters = data.get("parameters", {}) if isinstance(data, dict) else {}
        if isinstance(parameters, dict):
            seen = set()
            for key, value in parameters.items():
                if not isinstance(key, str) or not isinstance(value, str):
                    continue  # Field types report invalid non-string input.
                if any(c in key for c in "=\r\n") or any(c in value for c in "\r\n"):
                    raise ValueError("参数名称不能包含等号或换行，参数值必须为单行文本。")
                if key.strip() in seen:
                    raise ValueError("去除首尾空格后参数名称不能重复。")
                seen.add(key.strip())
        return data

    @model_validator(mode="after")
    def unique_metrics(self):
        names = [m.name.casefold() for m in self.metrics]
        if len(names) != len(set(names)):
            raise ValueError("同一次实验中指标名称不能重复；不同划分请使用不同名称。")
        if len(self.log_source_ids) != len(set(self.log_source_ids)):
            raise ValueError("关联日志不能重复。")
        return self


class ExperimentCreate(ExperimentFields):
    plan_task_id: str | None = Field(default=None, max_length=64)


class ExperimentUpdate(ExperimentFields):
    revision: int = Field(ge=1)


class Revision(Input):
    revision: int = Field(ge=1)


class Compare(Input):
    baseline_id: str = Field(min_length=1, max_length=64)
    candidate_id: str = Field(min_length=1, max_length=64)


def decode(row):
    if not row:
        raise HTTPException(404, "实验记录不存在或不属于当前项目。")
    row = dict(row)
    row.update(json.loads(row.pop("details")))
    row.setdefault("metric_evidence", {})
    row["plan"] = json.loads(row["plan"]) if row["plan"] else None
    row["logs"] = json.loads(row["logs"])
    row["log_source_ids"] = [s["id"] for s in row["logs"]]
    row["archived"] = bool(row["archived"])
    return row


def details(body):
    return {k: v for k, v in body.model_dump().items() if k not in {"name", "status", "revision", "plan_task_id", "log_source_ids"}}


class Experiments:
    def __init__(self, db, log_analysis):
        self.db, self.log_analysis = db, log_analysis

    def _details(self, con, workspace, body, previous=None):
        result, evidence, cache = details(body), {}, {}
        retained = list((previous or {}).get("metric_evidence", {}).values())
        for metric in body.metrics:
            if metric.origin is None:
                continue
            ref = metric.origin.model_dump()
            snapshot = next((e for e in retained if all(e.get(k) == v for k, v in ref.items())), None)
            if snapshot is None:
                snapshot = self.log_analysis.resolve(workspace, metric.origin, con, cache)
            if metric.value != snapshot["value"]:
                raise HTTPException(422, "所选指标的数值与日志不一致。修改数值时请改为手动记录，或重新选择日志指标。")
            evidence[metric.name.casefold()] = snapshot
        result["metric_evidence"] = evidence
        return result

    def get(self, workspace, identifier):
        return decode(self.db.one("SELECT * FROM experiments WHERE workspace_id=? AND id=?", (workspace, identifier)))

    def list(self, workspace, archived=False):
        rows = self.db.all("SELECT id,name,status,details,revision,archived,updated_at FROM experiments WHERE workspace_id=? AND archived=? ORDER BY updated_at DESC", (workspace, int(archived)))
        # Lists stay light even when plans and logs contain large evidence snapshots.
        return [{**{k: v for k, v in r.items() if k != "details"}, "archived": bool(r["archived"]),
                 **{k: v for k, v in json.loads(r["details"]).items() if k in {"dataset", "code_ref", "metrics"}}} for r in rows]

    def _logs(self, con, workspace, identifiers, existing=()):
        retained = {s["id"]: s for s in existing}
        result = []
        for identifier in identifiers:
            if identifier in retained:
                result.append(retained[identifier])
                continue
            row = con.execute("SELECT id,name,metadata FROM sources WHERE id=? AND workspace_id=? AND kind='log'", (identifier, workspace)).fetchone()
            if not row:
                raise HTTPException(422, "请选择当前项目中已导入的日志资料。")
            chunks = con.execute("SELECT text,locator FROM chunks WHERE source_id=? ORDER BY rowid", (identifier,))
            excerpt, truncated = "", False
            for chunk in chunks:
                addition = f"{chunk['locator']}\n{chunk['text']}\n\n"
                remaining = 20000 - len(excerpt)
                excerpt += addition[:remaining]
                if len(addition) > remaining:
                    truncated = True
                    break
            result.append({"id": row["id"], "name": row["name"], "text": excerpt, "truncated": truncated,
                           "metadata": json.loads(row["metadata"]), "saved_at": now()})
        return result

    def _insert(self, con, workspace, body, plan=None, logs=None):
        if con.execute("SELECT COUNT(*) FROM experiments WHERE workspace_id=?", (workspace,)).fetchone()[0] >= 500:
            raise HTTPException(422, "每个项目最多保存 500 条实验记录（含回收站）。")
        identifier, timestamp = uid(), now()
        con.execute("""INSERT INTO experiments(id,workspace_id,name,status,details,plan,logs,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?)""", (identifier, workspace, body.name, body.status, dump(self._details(con, workspace, body)),
            dump(plan) if plan else None, dump(logs or []), timestamp, timestamp))
        return decode(con.execute("SELECT * FROM experiments WHERE id=?", (identifier,)).fetchone())

    def create(self, workspace, body):
        with self.db.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            plan = None
            if body.plan_task_id:
                task = con.execute("SELECT * FROM tasks WHERE id=? AND workspace_id=?", (body.plan_task_id, workspace)).fetchone()
                if not task:
                    raise HTTPException(404, "复现计划不存在或不属于当前项目。")
                if task["intent"] != "plan" or task["status"] not in {"completed", "needs_review"} or not task["answer"]:
                    raise HTTPException(422, "请选择已生成且有证据的复现计划。")
                plan = {k: task[k] for k in ("id", "prompt", "answer", "mode", "status", "created_at")}
                plan["citations"] = json.loads(task["citations"])
                if not plan["citations"]:
                    raise HTTPException(422, "复现计划缺少引用证据，请先补充资料。")
            return self._insert(con, workspace, body, plan, self._logs(con, workspace, body.log_source_ids))

    def update(self, workspace, identifier, body):
        with self.db.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            previous = decode(con.execute("SELECT * FROM experiments WHERE id=? AND workspace_id=?", (identifier, workspace)).fetchone())
            self._editable(previous, body.revision)
            logs = self._logs(con, workspace, body.log_source_ids, previous["logs"])
            con.execute("""UPDATE experiments SET name=?,status=?,details=?,logs=?,revision=revision+1,updated_at=?
                WHERE id=? AND workspace_id=?""", (body.name, body.status, dump(self._details(con, workspace, body, previous)), dump(logs), now(), identifier, workspace))
            return decode(con.execute("SELECT * FROM experiments WHERE id=?", (identifier,)).fetchone())

    @staticmethod
    def _editable(row, revision):
        if row["archived"]:
            raise HTTPException(409, "请先从回收站恢复实验记录。")
        if row["revision"] != revision:
            raise HTTPException(409, "记录已在其他页面更新。请复制需保留的草稿内容，再打开最新记录合并。")

    def clone(self, workspace, identifier, revision):
        with self.db.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            previous = decode(con.execute("SELECT * FROM experiments WHERE id=? AND workspace_id=?", (identifier, workspace)).fetchone())
            self._editable(previous, revision)
            fields = {k: previous[k] for k in ExperimentFields.model_fields}
            fields.update(name=previous["name"][:110] + " · 新一轮", status="planned", metrics=[], conclusion="", log_source_ids=[],
                          checklist=[{"label": c["label"], "done": False} for c in previous["checklist"]])
            return self._insert(con, workspace, ExperimentCreate(**fields), previous["plan"])

    def archive(self, workspace, identifier, revision, archived):
        with self.db.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = decode(con.execute("SELECT * FROM experiments WHERE id=? AND workspace_id=?", (identifier, workspace)).fetchone())
            if row["revision"] != revision:
                raise HTTPException(409, "实验记录已更新，请刷新后再操作。")
            con.execute("UPDATE experiments SET archived=?,revision=revision+1,updated_at=? WHERE id=?", (int(archived), now(), identifier))
            return decode(con.execute("SELECT * FROM experiments WHERE id=?", (identifier,)).fetchone())

    def compare(self, workspace, baseline, candidate):
        if baseline == candidate:
            raise HTTPException(422, "请选择两条不同的实验记录。")
        with self.db.connect() as con:
            con.execute("BEGIN")
            left, right = [decode(con.execute("SELECT * FROM experiments WHERE workspace_id=? AND id=?", (workspace, identifier)).fetchone())
                           for identifier in (baseline, candidate)]
        if left["archived"] or right["archived"]:
            raise HTTPException(409, "请先恢复回收站中的实验记录。")
        a, b = ({m["name"].casefold(): m for m in e["metrics"]} for e in (left, right))
        rows = []
        for key in dict.fromkeys([*a, *b]):
            lm, rm = a.get(key), b.get(key)
            reasons = []
            if not lm or not rm:
                reasons.append("仅一侧记录了该指标")
            else:
                if not left["dataset"] or not right["dataset"] or left["dataset"] != right["dataset"]:
                    reasons.append("数据集 / 版本未填写或不一致")
                for field, label in (("split", "评测划分"), ("protocol", "评测协议")):
                    if not lm[field] or not rm[field] or lm[field] != rm[field]:
                        reasons.append(label + "未填写或不一致")
                if lm["unit"] != rm["unit"]:
                    reasons.append("指标单位不一致")
            rows.append({"name": (lm or rm)["name"], "baseline": lm, "candidate": rm,
                         "comparable": not reasons, "reason": "；".join(reasons),
                         "delta": rm["value"] - lm["value"] if not reasons else None})
        changes = []
        for field, label in (("environment", "环境"), ("dataset", "数据集 / 版本"), ("code_ref", "代码版本"), ("objective", "实验目标")):
            if left[field] != right[field]:
                changes.append({"field": label, "baseline": left[field], "candidate": right[field]})
        for key in sorted(left["parameters"].keys() | right["parameters"].keys()):
            lv, rv = left["parameters"].get(key), right["parameters"].get(key)
            if lv != rv:
                changes.append({"field": "参数 · " + key, "baseline": lv, "candidate": rv})
        return {"baseline": {"id": left["id"], "name": left["name"], "status": left["status"]},
                "candidate": {"id": right["id"], "name": right["name"], "status": right["status"]},
                "metrics": rows, "changes": changes,
                "notice": "数值由用户填写或从日志确认；差值 = 对照 − 基准。条件匹配仅依据填写文字，未核验数据或执行评测，不自动判定提升。"}

    def export(self, workspace, identifier):
        e = self.get(workspace, identifier)
        def literal(value):
            return re.sub(r"([\\`*\[\]_#|])", r"\\\1", html.escape(str(value), quote=False))
        lines = ["# " + literal(e["name"]), "", "人工实验记录；系统未执行训练或验证指标。", "",
                 "状态：" + STATUSES[e["status"]], "更新时间：" + e["updated_at"], ""]
        for field, label in (("objective", "实验目标"), ("environment", "环境"), ("dataset", "数据集 / 版本"), ("code_ref", "代码版本")):
            lines += ["## " + label, "", literal(e[field]) or "（未填写）", ""]
        lines += ["## 参数", ""] + [f"- {literal(k)} = {literal(v)}" for k, v in e["parameters"].items()]
        lines += ["", "## 核对清单", ""] + [f"- [{'x' if c['done'] else ' '}] {literal(c['label'])}" for c in e["checklist"]]
        lines += ["", "## 实际指标（人工填写 / 日志确认）", ""]
        for m in e["metrics"]:
            lines += [f"- {literal(m['name'])}：{m['value']} {literal(m['unit'])}；划分：{literal(m['split']) or '未填'}；协议：{literal(m['protocol']) or '未填'}"]
            evidence = e["metric_evidence"].get(m["name"].casefold())
            if evidence:
                lines += ["", f"来源：{literal(evidence['source_name'])}:L{evidence['line']}；原指标：{literal(evidence['name'])}；文本 SHA256：{evidence['checksum']}",
                          "", "> " + literal(evidence["text"]), "", "单位、划分与评测协议由用户核对。", ""]
        if not e["metrics"]:
            lines += ["（尚未记录）"]
        lines += ["", "## 个人结论 / 下一步", "", literal(e["conclusion"]) or "（未填写）", "", "## 日志快照", ""]
        for log in e["logs"]:
            lines += ["### " + literal(log["name"]), "", "保存于：" + log["saved_at"], "", *["> " + literal(line) for line in log["text"].splitlines()], ""]
            if log["truncated"]:
                lines += ["（快照仅保留前 20000 字符；完整日志请查看原资料。）", ""]
        if e["plan"]:
            p = e["plan"]
            lines += ["## 复现计划快照（待人工核对）", "", "模式：" + p["mode"] + "；任务状态：" + p["status"], "", literal(p["answer"]), "", "### 引用证据", ""]
            for citation in p["citations"]:
                lines += [literal(f"[{citation['label']}] {citation['name']} · {citation['locator']}"), "",
                          *["> " + literal(line) for line in citation["text"].splitlines()], "", "来源元数据：" + literal(dump(citation.get("metadata", {}))), ""]
        return "\n".join(lines)
