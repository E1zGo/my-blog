"""Validated, fixed page scopes for close reading and page-linked notes."""
import json

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PageRange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: int = Field(ge=1, le=300, strict=True)
    end: int = Field(ge=1, le=300, strict=True)

    @model_validator(mode="after")
    def ordered(self):
        if self.start > self.end:
            raise ValueError("起始页不能大于结束页。")
        return self


def validate_pages(db, workspace, source_ids, page_range):
    if page_range is None:
        return
    if len(source_ids) != 1:
        raise ValueError("限定页码时请只选择一篇论文。")
    row = db.one("SELECT kind,metadata FROM sources WHERE id=? AND workspace_id=?", (source_ids[0], workspace))
    if not row or row["kind"] != "paper":
        raise ValueError("页码范围必须属于当前项目中的论文。")
    total = json.loads(row["metadata"]).get("pages") or db.one("SELECT MAX(page) AS n FROM chunks WHERE source_id=?", (source_ids[0],))["n"] or 0
    if page_range["end"] > total:
        raise ValueError(f"所选论文仅有 {total} 页，请调整页码范围。")


def page_label(page_range):
    if not page_range:
        return "全文"
    if page_range["start"] == page_range["end"]:
        return f"第 {page_range['start']} 页"
    return f"第 {page_range['start']}–{page_range['end']} 页"
