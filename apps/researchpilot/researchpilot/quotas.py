"""Account admission limits; queued and cancelling workers retain their slots."""
import json
import shutil
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from threading import RLock


class QuotaExceeded(ValueError):
    def __init__(self, message, code="quota_exceeded", status=429):
        super().__init__(message)
        self.code, self.status = code, status


class Quotas:
    def __init__(self, db, settings):
        self.db, self.settings = db, settings
        self.lock = RLock()
        self.jobs = {"tasks": {}, "imports": {}}

    def owner(self, con, workspace):
        if self.settings.auth_mode == "local":
            return "local"
        row = con.execute("SELECT user_id FROM workspace_owners WHERE workspace_id=?", (workspace,)).fetchone()
        if not row:
            raise ValueError("项目尚未分配账号归属。")
        return row[0]

    def project_filter(self, owner):
        if owner == "local":
            return "SELECT id FROM workspaces", ()
        return "SELECT workspace_id FROM workspace_owners WHERE user_id=?", (owner,)

    def active(self, con, kind, owner=None):
        states = "'queued','running'" if kind == "tasks" else "'receiving','queued','parsing','indexing'"
        clause, args = "", ()
        if owner is not None:
            query, args = self.project_filter(owner)
            clause = f" AND workspace_id IN ({query})"
        ids = {r[0] for r in con.execute(f"SELECT id FROM {kind} WHERE status IN ({states}){clause}", args)}
        ids.update(key for key, job in self.jobs[kind].items() if owner is None or job["owner"] == owner)
        return len(ids)

    def daily(self, con, owner):
        projects, args = self.project_filter(owner)
        since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        return con.execute(f"SELECT COUNT(*) FROM tasks WHERE workspace_id IN ({projects}) AND created_at>=?", (*args, since)).fetchone()[0]

    def storage(self, con, owner):
        projects, args = self.project_filter(owner)
        originals = {}
        for row in con.execute(f"SELECT metadata FROM sources WHERE workspace_id IN ({projects})", args):
            meta = json.loads(row[0])
            if meta.get("original_id"):
                originals[meta["original_id"]] = max(0, int(meta.get("size_bytes", 0)))
        reserved = {row[0]: row[1] for row in con.execute(f"SELECT id,size_bytes FROM imports WHERE workspace_id IN ({projects}) AND source_id IS NULL AND status IN ('receiving','queued','parsing','indexing')", args)}
        for key, job in self.jobs["imports"].items():
            if job["owner"] == owner and key not in originals:
                reserved[key] = job["bytes"]
        return sum(originals.values()), sum(reserved.values())

    def check_project(self, con, owner):
        query, args = self.project_filter(owner)
        if con.execute(f"SELECT COUNT(*) FROM ({query})", args).fetchone()[0] >= self.settings.max_projects:
            raise QuotaExceeded(f"当前账号最多创建 {self.settings.max_projects} 个项目。", "project_quota")

    def check_job(self, con, kind, owner, size=0):
        maximum = self.settings.max_active_tasks if kind == "tasks" else self.settings.max_active_imports
        global_maximum = 10 if kind == "tasks" else 8
        label = "研究任务" if kind == "tasks" else "导入任务"
        if self.active(con, kind) >= global_maximum or self.active(con, kind, owner) >= maximum:
            raise QuotaExceeded(f"{label}名额已满，请等待已有任务结束。取消中的后台工作也会占用名额。", "active_" + kind)
        if kind == "tasks" and self.daily(con, owner) >= self.settings.max_tasks_daily:
            raise QuotaExceeded(f"最近 24 小时已达到 {self.settings.max_tasks_daily} 次研究任务上限，请稍后再试。", "daily_tasks")
        if kind == "imports":
            used, reserved = self.storage(con, owner)
            if used + reserved + size > self.settings.max_storage_mb * 1024**2:
                raise QuotaExceeded("账号原文件额度不足，请移除不需要的资料或联系管理员调整额度。", "storage_quota")

    def check_disk(self, additional=0):
        if shutil.disk_usage(self.settings.data_dir).free < self.settings.min_free_disk_mb * 1024**2 + additional:
            raise QuotaExceeded("服务器可用磁盘不足，已暂停新增数据；请联系管理员清理空间。", "disk_low", 507)

    def release(self, kind, identifier):
        with self.lock:
            self.jobs[kind].pop(identifier, None)

    @contextmanager
    def synchronous_import(self, workspace):
        """Legacy upload and repository routes share the same import capacity."""
        identifier = uuid.uuid4().hex
        with self.lock, self.db.connect() as con:
            owner = self.owner(con, workspace)
            self.check_job(con, "imports", owner)
            self.check_disk()
            self.jobs["imports"][identifier] = {"owner":owner, "bytes":0}
        try:
            yield
        finally:
            self.release("imports", identifier)

    def usage(self, owner):
        with self.lock, self.db.connect() as con:
            query, args = self.project_filter(owner)
            projects = [dict(row) for row in con.execute(f"SELECT w.id,w.name,COUNT(s.id) AS sources FROM workspaces w LEFT JOIN sources s ON s.workspace_id=w.id WHERE w.id IN ({query}) GROUP BY w.id ORDER BY w.created_at", args)]
            used, reserved = self.storage(con, owner)
            return {"projects": projects, "storage_bytes": used, "reserved_bytes": reserved,
                    "active_tasks": self.active(con, "tasks", owner), "active_imports": self.active(con, "imports", owner),
                    "tasks_last_24h": self.daily(con, owner),
                    "limits": {"projects":self.settings.max_projects,"sources_per_project":self.settings.max_sources,
                               "storage_bytes":self.settings.max_storage_mb * 1024**2,
                               "active_tasks":self.settings.max_active_tasks,"active_imports":self.settings.max_active_imports,
                               "tasks_daily":self.settings.max_tasks_daily}}
