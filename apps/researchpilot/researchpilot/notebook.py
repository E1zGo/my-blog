"""User notes plus immutable, server-resolved evidence snapshots."""
import html
import json
import re

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Literal

from .db import dump, now, uid
from .reading import validate_pages

CATEGORIES = {"general": "阅读笔记", "method": "方法与创新", "setup": "实验设置", "result": "结果与局限", "question": "待验证问题"}
Category = Literal["general", "method", "setup", "result", "question"]


class NoteCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    title: str = Field(default="", max_length=120)
    body: str = Field(default="", max_length=12000)
    category: Category = "general"
    source_id: str | None = Field(default=None, max_length=64)
    source_page: int | None = Field(default=None, ge=1, le=300, strict=True)
    chunk_id: str | None = Field(default=None, max_length=64)
    task_id: str | None = Field(default=None, max_length=64)
    citation_label: str | None = Field(default=None, pattern=r"^E[1-9]\d{0,5}$")

    @model_validator(mode="after")
    def origin(self):
        if bool(self.task_id) != bool(self.citation_label):
            raise ValueError("收藏任务证据时必须同时提供任务和引用编号。")
        if sum(bool(v) for v in (self.source_id, self.chunk_id, self.task_id)) > 1:
            raise ValueError("每条笔记只能关联一个资料或证据入口。")
        if self.source_page is not None and not self.source_id:
            raise ValueError("页级笔记必须关联一篇论文。")
        if not self.title and not self.chunk_id and not self.task_id:
            raise ValueError("请填写笔记标题。")
        return self


class NoteUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(default="", max_length=12000)
    category: Category = "general"
    revision: int = Field(ge=1)


class NoteRevision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)


def decode(row):
    if not row:
        raise HTTPException(404, "笔记不存在或不属于当前项目。")
    row = dict(row)
    row["evidence"] = json.loads(row["evidence"]) if row["evidence"] else None
    row["archived"] = bool(row["archived"])
    return row


class Notebook:
    def __init__(self, db):
        self.db = db

    def get(self, workspace, identifier):
        return decode(self.db.one("SELECT * FROM notes WHERE id=? AND workspace_id=?", (identifier, workspace)))

    def list(self, workspace, archived=False):
        return [decode(row) for row in self.db.all("SELECT * FROM notes WHERE workspace_id=? AND archived=? ORDER BY updated_at DESC", (workspace, int(archived)))]

    def create(self, workspace, body):
        evidence, source, key = None, None, None
        if body.chunk_id:
            evidence = self.db.one("""SELECT c.id,c.source_id,c.text,c.page,c.locator,s.name,s.kind,s.metadata
                FROM chunks c JOIN sources s ON c.source_id=s.id WHERE c.id=? AND s.workspace_id=?""", (body.chunk_id, workspace))
            if not evidence:
                raise HTTPException(404, "该证据不存在或不属于当前项目。")
            evidence["metadata"] = json.loads(evidence["metadata"])
        elif body.task_id:
            task = self.db.task(body.task_id)
            if not task or task["workspace_id"] != workspace:
                raise HTTPException(404, "该任务不存在或不属于当前项目。")
            evidence = next((e for e in task["citations"] if e["label"] == body.citation_label), None)
            if not evidence:
                raise HTTPException(404, "任务中没有这条引用证据。")
        elif body.source_id:
            source = self.db.one("SELECT id,name FROM sources WHERE id=? AND workspace_id=?", (body.source_id, workspace))
            if not source:
                raise HTTPException(404, "关联资料不存在或不属于当前项目。")
            if body.source_page is not None:
                validate_pages(self.db, workspace, [body.source_id], {"start": body.source_page, "end": body.source_page})
        if evidence:
            evidence = {k: evidence[k] for k in ("id", "source_id", "name", "kind", "text", "page", "locator", "metadata") if k in evidence}
            key = evidence["id"]
            source = {"id": evidence["source_id"], "name": evidence["name"]}
        title = body.title or (evidence["name"] + " · " + evidence["locator"])[:120]
        timestamp, identifier = now(), uid()
        with self.db.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            existing = con.execute("SELECT * FROM notes WHERE workspace_id=? AND evidence_key=?", (workspace, key)).fetchone() if key else None
            if existing:
                restored = bool(existing["archived"])
                if restored:
                    con.execute("UPDATE notes SET archived=0,revision=revision+1,updated_at=? WHERE id=?", (timestamp, existing["id"]))
                result = decode(con.execute("SELECT * FROM notes WHERE id=?", (existing["id"],)).fetchone())
                return {**result, "duplicate": True, "restored": restored}
            count = con.execute("SELECT COUNT(*) FROM notes WHERE workspace_id=?", (workspace,)).fetchone()[0]
            if count >= 1000:
                raise ValueError("单个项目最多保存 1000 条笔记（含回收站），请创建新的研究项目。")
            con.execute("""INSERT INTO notes(id,workspace_id,title,category,body,source_id,source_name,evidence_key,evidence,created_at,updated_at,source_page)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", (identifier, workspace, title, body.category, body.body,
                source["id"] if source else None, source["name"] if source else None, key, dump(evidence) if evidence else None, timestamp, timestamp, body.source_page))
        return {**self.get(workspace, identifier), "duplicate": False, "restored": False}

    def update(self, workspace, identifier, body):
        with self.db.connect() as con:
            row = decode(con.execute("SELECT * FROM notes WHERE id=? AND workspace_id=?", (identifier, workspace)).fetchone())
            if row["archived"]:
                raise HTTPException(409, "请先从回收站恢复这条笔记。")
            changed = con.execute("""UPDATE notes SET title=?,category=?,body=?,updated_at=?,revision=revision+1
                WHERE id=? AND workspace_id=? AND revision=? AND archived=0""",
                (body.title, body.category, body.body, now(), identifier, workspace, body.revision)).rowcount
            if not changed:
                raise HTTPException(409, "笔记已在其他页面更新。输入已保留为本机草稿，请先复制所需内容，再打开最新笔记合并。")
            result = decode(con.execute("SELECT * FROM notes WHERE id=?", (identifier,)).fetchone())
        return result

    def archive(self, workspace, identifier, revision, archived):
        with self.db.connect() as con:
            decode(con.execute("SELECT * FROM notes WHERE id=? AND workspace_id=?", (identifier, workspace)).fetchone())
            changed = con.execute("UPDATE notes SET archived=?,updated_at=?,revision=revision+1 WHERE id=? AND workspace_id=? AND revision=?",
                (int(archived), now(), identifier, workspace, revision)).rowcount
            if not changed:
                raise HTTPException(409, "笔记已更新，请刷新列表后再操作。")
            result = decode(con.execute("SELECT * FROM notes WHERE id=?", (identifier,)).fetchone())
        return result

    def export(self, workspace):
        name = self.db.one("SELECT name FROM workspaces WHERE id=?", (workspace,))["name"]
        def literal(text):
            return re.sub(r"([\\`*\[\]_#])", r"\\\1", html.escape(text, quote=False))
        lines = ["# " + literal(name) + " · 研究笔记", "", "原文证据为保存时的快照；个人分析由用户撰写，不代表已验证结论。", ""]
        for note in self.list(workspace):
            lines += ["## " + literal(note["title"]), "", "类别：" + CATEGORIES[note["category"]], "", "更新时间：" + note["updated_at"], ""]
            if note["source_name"]:
                lines += ["关联资料：" + literal(note["source_name"]), ""]
            if note["source_page"]:
                lines += [f"阅读位置：第 {note['source_page']} 页（页级个人笔记，未自动摘录原文）", ""]
            if note["evidence"]:
                evidence = note["evidence"]
                lines += ["### 原文证据", "", literal(evidence["locator"]), ""]
                lines += ["> " + literal(line) for line in evidence["text"].splitlines()]
                if evidence.get("metadata", {}).get("commit"):
                    lines += ["", "代码版本：" + literal(evidence["metadata"]["commit"])]
                lines += [""]
            lines += ["### 个人分析 / 待办", "", literal(note["body"]) if note["body"] else "（尚未填写）", ""]
        return "\n".join(lines)
