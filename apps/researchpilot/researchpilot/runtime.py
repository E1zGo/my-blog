"""Bounded process metrics and streaming HTTP body limits (no request content)."""
from collections import Counter, deque
import math
import shutil
import sqlite3
import threading
import time
import uuid

from starlette.formparsers import MultiPartException
from starlette.responses import JSONResponse


class Runtime:
    def __init__(self, db, settings, quotas):
        self.db, self.settings, self.quotas = db, settings, quotas
        self.started = time.monotonic()
        self.ready = False
        self.lock = threading.Lock()
        self.active = 0
        self.counts = Counter()
        self.recent = deque(maxlen=512)

    def readiness(self):
        try:
            with self.db.connect() as con:
                users = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
                admins = con.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]
            free = shutil.disk_usage(self.settings.data_dir).free
            account_ok = bool(admins) if self.settings.auth_mode == "accounts" else users == 0
            return self.ready and account_ok and free >= self.settings.min_free_disk_mb * 1024**2
        except (OSError, sqlite3.Error):
            return False

    def snapshot(self):
        timestamp = time.monotonic()
        with self.lock:
            recent = [row for row in self.recent if row[0] >= timestamp - 300]
            durations = sorted(row[2] for row in recent)
            result = {"uptime_seconds": round(timestamp - self.started), "active_requests":self.active,
                      "request_counts":dict(self.counts), "recent_requests":len(recent),
                      "recent_errors":sum(row[1] >= 500 for row in recent),
                      "p95_ms":durations[max(0, math.ceil(len(durations) * .95) - 1)] if durations else None}
        with self.quotas.lock, self.db.connect() as con:
            result.update({"tasks_in_flight":self.quotas.active(con,"tasks"), "imports_in_flight":self.quotas.active(con,"imports")})
        result.update({"ready":self.readiness(), "disk_free_bytes":shutil.disk_usage(self.settings.data_dir).free,
                       "disk_floor_bytes":self.settings.min_free_disk_mb * 1024**2,
                       "public_origin":self.settings.public_origin or None})
        return result


class RuntimeBoundary:
    def __init__(self, app, runtime):
        self.app, self.runtime = app, runtime

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        runtime, started = self.runtime, time.monotonic()
        request_id = uuid.uuid4().hex
        status, received, exceeded, replaced = 500, 0, False, False
        path = scope["path"]
        upload = path.endswith(("/upload", "/imports"))
        cap = (runtime.settings.max_upload_bytes + 100_000 if upload
               else 16_384 if path.startswith(("/api/auth/", "/api/admin/")) else 1024**2)
        with runtime.lock:
            overloaded = runtime.active >= 32 and path not in {"/api/health", "/api/ready"}
            runtime.active += 1
        rejection = JSONResponse({
            "detail":f"上传请求过大，当前单文件上限为 {runtime.settings.max_upload_mb} MB。" if upload else "请求内容超过允许的大小。",
            "code":"upload_too_large" if upload else "request_too_large",
            "limit_bytes":runtime.settings.max_upload_bytes if upload else cap}, status_code=413)

        async def bounded_receive():
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > cap:
                    exceeded = True
                    # Starlette's multipart parser closes partial spooled files for this exception.
                    raise MultiPartException("请求内容超过允许的大小。")
            return message

        async def tracked_send(message):
            nonlocal status, replaced
            if message["type"] == "http.response.start":
                if exceeded:
                    replaced = True
                    status = 413
                    await rejection(scope, receive, final_send)
                    return
                status = message["status"]
            if not replaced:
                await final_send(message)

        async def final_send(message):
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message.get("headers", [])
                           if k.lower() not in {b"cache-control", b"x-request-id"}]
                headers.extend([(b"x-request-id",request_id.encode()),(b"cache-control",b"no-store")])
                message = {**message, "headers": headers}
            await send(message)

        try:
            if overloaded:
                status = 503
                return await JSONResponse({"detail":"服务繁忙，请稍后重试。"},503,headers={"Retry-After":"5"})(scope,receive,final_send)
            lengths = [value for name, value in scope["headers"] if name.lower() == b"content-length"]
            if lengths:
                try:
                    if len(lengths) != 1 or not lengths[0].isdigit():
                        raise ValueError()
                    length = int(lengths[0])
                except ValueError:
                    status = 400
                    return await JSONResponse({"detail":"无效 Content-Length。"},400)(scope,receive,final_send)
                if length > cap:
                    status = 413
                    return await rejection(scope,receive,final_send)
            await self.app(scope, bounded_receive, tracked_send)
        finally:
            with runtime.lock:
                runtime.active -= 1
                runtime.counts[str(status // 100) + "xx"] += 1
                runtime.recent.append((time.monotonic(),status,round((time.monotonic()-started)*1000,1)))
