import json
import logging
import threading
import tempfile
import sqlite3
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form, Query
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from typing import Literal

from .agent import Agent
from .config import ROOT, Settings
from .db import Database, dump, now, uid
from .github import fetch_repository
from .library import Library, UploadTooLarge
from .imports import ImportManager, ImportQueueFull
from .preview import render_page
from .notebook import Notebook, NoteCreate, NoteUpdate, NoteRevision
from .experiments import Experiments, ExperimentCreate, ExperimentUpdate, Revision, Compare
from .log_analysis import LogAnalysis
from .query_terms import expand_query
from .reading import PageRange, validate_pages, page_label
from . import __version__
from .maintenance import create_backup, doctor, MaintenanceError
from .accounts import Accounts
from .quotas import QuotaExceeded
from .runtime import Runtime, RuntimeBoundary


class NameInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str = Field(min_length=1, max_length=80)


class RepoInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    url: str = Field(min_length=1, max_length=250)


class TaskInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    prompt: str = Field(min_length=1, max_length=6000)
    intent: Literal["qa", "plan", "diagnose"] = "qa"
    source_ids: list[str] = Field(default_factory=list, max_length=50)
    page_range: PageRange | None = None


class SearchInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    query: str = Field(min_length=1, max_length=2000)
    kind: Literal["all", "paper", "repository", "log"] = "all"
    k: int = Field(default=5, ge=1, le=10)
    source_ids: list[str] = Field(default_factory=list, max_length=50)
    page_range: PageRange | None = None


def create_app(settings=None):
    settings = settings or Settings.from_env()
    db = Database(settings.data_dir)
    accounts = Accounts(db, settings)
    library = Library(db, settings)
    quotas = library.quotas
    runtime = Runtime(db, settings, quotas)
    imports = ImportManager(db, library, settings)
    notebook = Notebook(db)
    log_analysis = LogAnalysis(db, imports)
    experiments = Experiments(db, log_analysis)
    pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="researchpilot")
    task_lock = quotas.lock
    backup_lock = threading.Lock()

    @asynccontextmanager
    async def lifespan(app):
        # This is a single-process local service. A restart must not leave zombie jobs.
        db.execute("UPDATE tasks SET status='failed',error='服务已重启，请重新发起任务。',finished_at=? WHERE status IN ('queued','running')", (now(),))
        imports.recover()
        runtime.ready = True
        yield
        runtime.ready = False
        pool.shutdown(wait=True, cancel_futures=True)
        imports.close()

    app = FastAPI(title="ResearchPilot", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.db, app.state.library, app.state.settings = db, library, settings
    app.state.imports = imports
    app.state.notebook = notebook
    app.state.experiments = experiments
    app.state.log_analysis = log_analysis
    app.state.accounts = accounts
    app.state.quotas, app.state.runtime = quotas, runtime
    app.include_router(accounts.router())

    @app.middleware("http")
    async def local_boundary(request, call_next):
        if settings.public_origin and request.url.path not in {"/api/health", "/api/ready"}:
            if str(request.base_url).rstrip("/") != settings.public_origin:
                return JSONResponse({"detail":"请通过已配置的 HTTPS 站点访问。"}, status_code=400)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if (origin and origin != str(request.base_url).rstrip("/")) or request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail": "不允许跨站写入请求。"}, status_code=403)
        try:
            length = int(request.headers.get("content-length", "0"))
        except ValueError:
            return JSONResponse({"detail": "无效 Content-Length。"}, status_code=400)
        if length > settings.max_upload_bytes + 100_000:
            return JSONResponse({"detail": f"上传请求超过当前单文件 {settings.max_upload_mb} MB 上限。请调整 RP_MAX_UPLOAD_MB 后重启服务，或缩小文件。",
                                 "code": "upload_too_large", "limit_bytes": settings.max_upload_bytes}, status_code=413)
        if request.url.path.startswith(("/api/auth/", "/api/admin/")) and length > 16_384:
            return JSONResponse({"detail": "账号请求过大。"}, status_code=413)
        try:
            await run_in_threadpool(accounts.guard, request)
        except HTTPException as exc:
            response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        else:
            response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "no-cache"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'"
        return response

    app.add_middleware(RuntimeBoundary, runtime=runtime)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)

    @app.exception_handler(QuotaExceeded)
    async def quota_error(request, exc):
        return JSONResponse({"detail":str(exc),"code":exc.code},status_code=exc.status)

    @app.exception_handler(ValueError)
    async def validation_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(RequestValidationError)
    async def request_validation_error(request, exc):
        if request.url.path.startswith(("/api/auth/", "/api/admin/")):
            # Pydantic errors otherwise echo rejected passwords and invitation tokens.
            return JSONResponse({"detail": "账号输入格式不正确。请检查用户名；新密码须为 15–128 个字符，且不能提交额外字段。"}, status_code=422)
        return await request_validation_exception_handler(request, exc)

    @app.exception_handler(UploadTooLarge)
    async def upload_size_error(request, exc):
        return JSONResponse({"detail": str(exc), "code": "upload_too_large",
                             "limit_bytes": settings.max_upload_bytes}, status_code=413)

    @app.exception_handler(ImportQueueFull)
    async def import_queue_full(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=429)

    def workspace_or_404(workspace):
        if not db.one("SELECT id FROM workspaces WHERE id=?", (workspace,)):
            raise HTTPException(404, "项目不存在。")

    def task_or_404(task_id):
        task = db.task(task_id)
        if not task:
            raise HTTPException(404, "任务不存在。")
        return task

    def validate_scope(workspace, source_ids):
        known = {s["id"] for s in library.list(workspace)}
        if any(identifier not in known for identifier in source_ids):
            raise HTTPException(422, "选择的资料不属于当前项目或已被移除，请重新选择研究范围。")
        return sorted(set(source_ids))

    @app.get("/api/health")
    def health(request: Request):
        if settings.auth_mode == "accounts" and not request.state.user:
            return {"status": "ok", "version": __version__, "auth_mode": "accounts"}
        return {"status": "ok", "mode": settings.mode, "model": settings.model or None,
                "retrieval": "hybrid" if settings.mode == "llm" and settings.embed_model else "BM25",
                "model_configured": bool(settings.model), "version": __version__,
                "limits": {"max_upload_mb": settings.max_upload_mb, "max_upload_bytes": settings.max_upload_bytes,
                           "max_pdf_pages": 300, "max_text_chars": 1_000_000}}

    @app.get("/api/maintenance/status")
    def maintenance_status():
        return doctor(settings.data_dir, settings.mode, settings.auth_mode)

    @app.get("/api/ready")
    def ready():
        healthy = runtime.readiness()
        return JSONResponse({"status":"ready" if healthy else "not_ready"}, status_code=200 if healthy else 503)

    @app.get("/api/resources")
    def resource_usage(request: Request):
        return quotas.usage(request.state.user["id"] if request.state.user else "local")

    @app.get("/api/maintenance/runtime")
    def runtime_status():
        return runtime.snapshot()

    @app.get("/api/maintenance/backup")
    def download_backup(request: Request):
        if request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "请从本机工作台下载备份。")
        if not backup_lock.acquire(blocking=False):
            raise HTTPException(409, "已有备份正在生成，请稍后重试。")
        temporary = None
        try:
            with quotas.lock, db.connect() as con:
                if quotas.active(con,"tasks") or quotas.active(con,"imports"):
                    raise MaintenanceError("仍有任务在后台执行或取消收尾，请等待结束后再备份。")
            temporary = tempfile.TemporaryDirectory(prefix="researchpilot-download-")
            path = Path(temporary.name) / "backup.zip"
            create_backup(settings.data_dir, path)
            filename = f"researchpilot-backup-{now()[:10]}-{uid()[:8]}.zip"
            return FileResponse(path, filename=filename, media_type="application/zip", background=BackgroundTask(temporary.cleanup))
        except (MaintenanceError, OSError, sqlite3.Error) as exc:
            if temporary:
                temporary.cleanup()
            if isinstance(exc, MaintenanceError):
                raise HTTPException(409, str(exc)) from None
            raise HTTPException(503, "备份未完成，请检查磁盘空间、目录权限或稍后重试。") from None
        finally:
            backup_lock.release()

    @app.get("/api/workspaces")
    def workspaces(request: Request):
        if settings.auth_mode == "accounts":
            return db.all("SELECT w.* FROM workspaces w JOIN workspace_owners o ON o.workspace_id=w.id WHERE o.user_id=? ORDER BY w.created_at DESC", (request.state.user["id"],))
        return db.all("SELECT * FROM workspaces ORDER BY created_at DESC")

    @app.post("/api/workspaces", status_code=201)
    def create_workspace(body: NameInput, request: Request):
        identifier = uid()
        with db.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            quotas.check_disk()
            quotas.check_project(con, request.state.user["id"] if request.state.user else "local")
            con.execute("INSERT INTO workspaces VALUES (?,?,?)", (identifier, body.name, now()))
            if settings.auth_mode == "accounts":
                con.execute("INSERT INTO workspace_owners VALUES (?,?)", (identifier, request.state.user["id"]))
        return db.one("SELECT * FROM workspaces WHERE id=?", (identifier,))

    @app.get("/api/workspaces/{workspace}/sources")
    def sources(workspace: str):
        workspace_or_404(workspace)
        return library.list(workspace)

    @app.post("/api/workspaces/{workspace}/upload", status_code=201)
    def upload(workspace: str, file: UploadFile = File(...), kind: Literal["paper", "log"] = Form("paper")):
        workspace_or_404(workspace)
        try:
            with quotas.synchronous_import(workspace):
                return library.upload_stream(workspace, file.filename or "upload", file.file, kind)
        except ValueError as exc:
            # Record the reason, not document text, file name, or credentials.
            logging.getLogger("uvicorn.error").warning("Upload rejected: %s", str(exc))
            raise
        finally:
            file.file.close()

    @app.post("/api/workspaces/{workspace}/imports", status_code=202)
    def start_import(workspace: str, file: UploadFile = File(...), kind: Literal["paper", "log"] = Form("paper")):
        workspace_or_404(workspace)
        try:
            return imports.submit(workspace, file.filename or "upload", file.file, kind)
        finally:
            file.file.close()

    @app.get("/api/workspaces/{workspace}/imports")
    def import_history(workspace: str):
        workspace_or_404(workspace)
        return imports.list(workspace)

    @app.get("/api/imports/{identifier}")
    def import_status(identifier: str):
        result = imports.get(identifier)
        if not result:
            raise HTTPException(404, "导入任务不存在。")
        return result

    @app.post("/api/imports/{identifier}/cancel")
    def cancel_import(identifier: str):
        import_status(identifier)
        return imports.cancel(identifier)

    @app.post("/api/sources/{source_id}/reindex", status_code=202)
    def reindex_source(source_id: str):
        row = db.one("SELECT * FROM sources WHERE id=?", (source_id,))
        if not row:
            raise HTTPException(404, "资料不存在。")
        metadata = json.loads(row["metadata"])
        if row["kind"] != "paper" or not metadata.get("filename", "").lower().endswith(".pdf"):
            raise HTTPException(422, "仅 PDF 论文支持重建段落索引。")
        identifier = metadata.get("original_id")
        if not identifier or not imports.path(identifier).is_file():
            raise HTTPException(404, "请重新上传原 PDF 后更新索引。")
        with imports.path(identifier).open("rb") as stream:
            return imports.submit(row["workspace_id"], row["name"], stream, "paper", source_id=source_id)

    @app.post("/api/workspaces/{workspace}/repository", status_code=201)
    def repository(workspace: str, body: RepoInput):
        workspace_or_404(workspace)
        with quotas.synchronous_import(workspace):
            result = fetch_repository(body.url, settings.github_token)
            imported = []
            metadata = {k: result[k] for k in ("repo", "url", "commit", "branch", "warnings")}
            for file in result["files"]:
                source_meta = {**metadata, "path": file["path"], "url": result["url"] + "/blob/" + result["commit"] + "/" + file["path"]}
                imported.append(library.ingest(workspace, file["path"], "repository", [(None, file["text"])], source_meta))
            return {"sources": imported, "commit": result["commit"], "warnings": result["warnings"], "tree": result["tree"]}

    @app.post("/api/workspaces/{workspace}/demo", status_code=201)
    def demo(workspace: str):
        workspace_or_404(workspace)
        fixture = json.loads((ROOT / "examples" / "demo.json").read_text(encoding="utf-8"))
        metadata = {"demo": True, "notice": fixture["notice"]}
        imported = [library.ingest(workspace, "TinyRestore · 示例论文", "paper", list(enumerate(fixture["paper"], 1)), metadata.copy())]
        for name, text in fixture["files"].items():
            imported.append(library.ingest(workspace, name, "repository", [(None, text)],
                            {**metadata, "repo": "local/tinyrestore-demo", "commit": "demo-v1（合成快照）", "path": name}))
        imported.append(library.ingest(workspace, "example-error.log", "log", [(None, fixture["log"])], metadata.copy()))
        return {"sources": imported, "notice": fixture["notice"]}

    @app.get("/api/sources/{source_id}")
    def source(source_id: str):
        row = db.one("SELECT * FROM sources WHERE id=?", (source_id,))
        if not row:
            raise HTTPException(404, "资料不存在。")
        row["metadata"] = json.loads(row["metadata"])
        original_id = row["metadata"].get("original_id")
        row["has_original"] = bool(original_id and imports.path(original_id).is_file())
        row["chunks"] = [{k: c[k] for k in ("id", "text", "page", "locator", "structure")} for c in library.chunks(row["workspace_id"], source_id=source_id)]
        return row

    @app.get("/api/sources/{source_id}/original")
    def original(source_id: str, download: bool = False):
        row = db.one("SELECT * FROM sources WHERE id=?", (source_id,))
        metadata = json.loads(row["metadata"]) if row else {}
        identifier = metadata.get("original_id")
        if not identifier or not imports.path(identifier).is_file():
            raise HTTPException(404, "原文件未保存或已被移除。早期导入的资料可重新上传以补充原文件。")
        filename = metadata.get("filename", row["name"])
        is_pdf = filename.lower().endswith(".pdf")
        return FileResponse(imports.path(identifier), filename=filename,
                            media_type="application/pdf" if is_pdf else "text/plain; charset=utf-8",
                            content_disposition_type="attachment" if download or not is_pdf else "inline")

    @app.delete("/api/sources/{source_id}", status_code=204)
    def remove_source(source_id: str):
        with db.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT metadata FROM sources WHERE id=?", (source_id,)).fetchone()
            if not row:
                raise HTTPException(404, "资料不存在。")
            con.execute("DELETE FROM sources WHERE id=?", (source_id,))
        identifier = json.loads(row["metadata"]).get("original_id")
        if identifier:
            try:
                imports.path(identifier).unlink(missing_ok=True)
            except OSError:
                # Windows can hold a file during an active download; startup sweeps orphans.
                logging.getLogger("uvicorn.error").warning("Original cleanup deferred until restart: file is in use.")

    @app.get("/api/sources/{source_id}/pages/{page}")
    def preview_page(source_id: str, page: int, width: int = Query(default=1200, ge=400, le=2200)):
        row = db.one("SELECT name,metadata FROM sources WHERE id=?", (source_id,))
        metadata = json.loads(row["metadata"]) if row else {}
        identifier = metadata.get("original_id")
        if not identifier or not imports.path(identifier).is_file():
            raise HTTPException(404, "没有可预览的原文件，请重新上传原 PDF。")
        if not metadata.get("filename", row["name"]).lower().endswith(".pdf"):
            raise HTTPException(422, "仅 PDF 支持逐页原文预览。")
        if not 1 <= page <= metadata.get("pages", 300):
            raise HTTPException(422, "页码超出原文件范围。")
        try:
            content = render_page(imports.path(identifier), page, width)
        except OSError:
            raise HTTPException(404, "原文件已移除或暂时无法读取。") from None
        return Response(content, media_type="image/png")

    @app.post("/api/workspaces/{workspace}/search")
    def search(workspace: str, body: SearchInput):
        workspace_or_404(workspace)
        body.source_ids = validate_scope(workspace, body.source_ids)
        validate_pages(db, workspace, body.source_ids, body.page_range.model_dump() if body.page_range else None)
        if body.page_range and body.kind not in {"all", "paper"}:
            raise ValueError("限定论文页码时只能检索论文类型。")
        return library.search(workspace, **body.model_dump())

    @app.get("/api/query-terms")
    def query_terms(query: str = Query(min_length=1, max_length=2000)):
        return {"expansion": expand_query(query)}

    @app.get("/api/workspaces/{workspace}/tasks")
    def tasks(workspace: str):
        workspace_or_404(workspace)
        rows = db.all("SELECT id,prompt,intent,mode,status,created_at,page_range FROM tasks WHERE workspace_id=? ORDER BY created_at DESC LIMIT 100", (workspace,))
        for row in rows:
            row["page_range"] = json.loads(row["page_range"])
        return rows

    @app.get("/api/workspaces/{workspace}/notes")
    def notes(workspace: str, archived: bool = False):
        workspace_or_404(workspace)
        return notebook.list(workspace, archived)

    @app.post("/api/workspaces/{workspace}/notes", status_code=201)
    def create_note(workspace: str, body: NoteCreate):
        workspace_or_404(workspace)
        return notebook.create(workspace, body)

    @app.get("/api/workspaces/{workspace}/notes/export")
    def export_notes(workspace: str):
        workspace_or_404(workspace)
        return Response(notebook.export(workspace), media_type="text/markdown; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="research-notes-{workspace[:8]}.md"'})

    @app.get("/api/workspaces/{workspace}/notes/{identifier}")
    def note(workspace: str, identifier: str):
        workspace_or_404(workspace)
        return notebook.get(workspace, identifier)

    @app.patch("/api/workspaces/{workspace}/notes/{identifier}")
    def update_note(workspace: str, identifier: str, body: NoteUpdate):
        workspace_or_404(workspace)
        return notebook.update(workspace, identifier, body)

    @app.post("/api/workspaces/{workspace}/notes/{identifier}/trash")
    def trash_note(workspace: str, identifier: str, body: NoteRevision):
        workspace_or_404(workspace)
        return notebook.archive(workspace, identifier, body.revision, True)

    @app.post("/api/workspaces/{workspace}/notes/{identifier}/restore")
    def restore_note(workspace: str, identifier: str, body: NoteRevision):
        workspace_or_404(workspace)
        return notebook.archive(workspace, identifier, body.revision, False)

    @app.get("/api/workspaces/{workspace}/experiments")
    def experiment_list(workspace: str, archived: bool = False):
        workspace_or_404(workspace)
        return experiments.list(workspace, archived)

    @app.post("/api/workspaces/{workspace}/logs/{source_id}/analysis")
    def analyze_log(workspace: str, source_id: str):
        workspace_or_404(workspace)
        return log_analysis.analyze(workspace, source_id)

    @app.post("/api/workspaces/{workspace}/logs/demo", status_code=201)
    def demo_log(workspace: str):
        workspace_or_404(workspace)
        text = (ROOT / "examples" / "training-demo.log").read_text(encoding="utf-8")
        return library.ingest(workspace, "合成训练曲线示例.log", "log", [(1, text)], {"demo": True, "notice": "合成日志，仅验证软件流程；未运行训练，不是真实模型成绩。"})

    @app.post("/api/workspaces/{workspace}/experiments", status_code=201)
    def create_experiment(workspace: str, body: ExperimentCreate):
        workspace_or_404(workspace)
        return experiments.create(workspace, body)

    @app.post("/api/workspaces/{workspace}/experiments/compare")
    def compare_experiments(workspace: str, body: Compare):
        workspace_or_404(workspace)
        return experiments.compare(workspace, body.baseline_id, body.candidate_id)

    @app.get("/api/workspaces/{workspace}/experiments/{identifier}")
    def experiment(workspace: str, identifier: str):
        workspace_or_404(workspace)
        return experiments.get(workspace, identifier)

    @app.patch("/api/workspaces/{workspace}/experiments/{identifier}")
    def update_experiment(workspace: str, identifier: str, body: ExperimentUpdate):
        workspace_or_404(workspace)
        return experiments.update(workspace, identifier, body)

    @app.post("/api/workspaces/{workspace}/experiments/{identifier}/clone", status_code=201)
    def clone_experiment(workspace: str, identifier: str, body: Revision):
        workspace_or_404(workspace)
        return experiments.clone(workspace, identifier, body.revision)

    @app.post("/api/workspaces/{workspace}/experiments/{identifier}/trash")
    def trash_experiment(workspace: str, identifier: str, body: Revision):
        workspace_or_404(workspace)
        return experiments.archive(workspace, identifier, body.revision, True)

    @app.post("/api/workspaces/{workspace}/experiments/{identifier}/restore")
    def restore_experiment(workspace: str, identifier: str, body: Revision):
        workspace_or_404(workspace)
        return experiments.archive(workspace, identifier, body.revision, False)

    @app.get("/api/workspaces/{workspace}/experiments/{identifier}/export")
    def export_experiment(workspace: str, identifier: str):
        workspace_or_404(workspace)
        return Response(experiments.export(workspace, identifier), media_type="text/markdown; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="experiment-{identifier[:8]}.md"'})

    @app.post("/api/workspaces/{workspace}/tasks", status_code=202)
    def start_task(workspace: str, body: TaskInput):
        workspace_or_404(workspace)
        source_ids = validate_scope(workspace, body.source_ids)
        page_range = body.page_range.model_dump() if body.page_range else None
        validate_pages(db, workspace, source_ids, page_range)
        if page_range and body.intent != "qa":
            raise ValueError("页码限定只用于论文问答，生成计划或诊断日志前请恢复全文范围。")
        with task_lock:
            if db.one("SELECT COUNT(*) AS n FROM tasks WHERE status IN ('queued','running')")["n"] >= 10:
                raise HTTPException(429, "待处理任务过多，请稍后重试。")
            agent = Agent(db, library, settings)
            identifier = uid()
            with db.connect() as con:
                con.execute("BEGIN IMMEDIATE")
                owner = quotas.owner(con, workspace)
                quotas.check_disk()
                quotas.check_job(con, "tasks", owner)
                con.execute("INSERT INTO tasks(id,workspace_id,prompt,intent,mode,status,created_at,source_ids,page_range) VALUES (?,?,?,?,?,'queued',?,?,?)",
                            (identifier, workspace, body.prompt, body.intent, settings.mode, now(), dump(source_ids), dump(page_range)))
            quotas.jobs["tasks"][identifier] = {"owner":owner}
            def run_task():
                try:
                    agent.run(identifier)
                finally:
                    quotas.release("tasks", identifier)
            try:
                pool.submit(run_task)
            except RuntimeError:
                quotas.release("tasks", identifier)
                db.execute("UPDATE tasks SET status='failed',error='服务正在关闭，请稍后重试。',finished_at=? WHERE id=?", (now(), identifier))
                raise HTTPException(503, "服务正在关闭，请稍后重试。") from None
        return {"id": identifier, "status": "queued"}

    @app.get("/api/tasks/{task_id}")
    def task(task_id: str):
        return task_or_404(task_id)

    @app.post("/api/tasks/{task_id}/cancel")
    def cancel(task_id: str):
        task_or_404(task_id)
        db.execute("UPDATE tasks SET status='cancelled',finished_at=? WHERE id=? AND status IN ('queued','running')", (now(), task_id))
        return task_or_404(task_id)

    @app.get("/api/tasks/{task_id}/report")
    def report(task_id: str):
        task = task_or_404(task_id)
        references = "\n\n".join(f"### [{e['label']}] {e['name']} · {e['locator']}\n{e['text']}\n\n来源元数据：{dump(e.get('metadata', {}))}" for e in task["citations"])
        scope = "指定资料 ID：" + (", ".join(task["source_ids"]) or "全部资料") + " · " + page_label(task["page_range"])
        content = f"# ResearchPilot 任务报告\n\n创建时间：{task['created_at']}\n\n模式：{task['mode']} · 状态：{task['status']}\n\n用户请求：{task['prompt']}\n\n{task['answer']}\n\n## 引用原文\n\n{references}\n\n## 运行指标\n\n```json\n{dump(task['usage'])}\n```\n"
        content = "研究范围：" + scope + "\n\n" + content
        return Response(content, media_type="text/markdown; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="researchpilot-{task_id[:8]}.md"'})

    app.mount("/static", StaticFiles(directory=ROOT / "frontend"), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(ROOT / "frontend" / "index.html")

    @app.get("/docs", include_in_schema=False)
    def api_docs():
        return FileResponse(ROOT / "frontend" / "api.html")

    return app


app = create_app()
