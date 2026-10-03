"""Durable import status with bounded workers and atomically committed sources."""
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import PurePosixPath

from .db import dump, now, uid
from .library import UploadTooLarge

ACTIVE = ("receiving", "queued", "parsing", "indexing")


class ImportCancelled(ValueError):
    pass


class ImportQueueFull(ValueError):
    pass


class ImportManager:
    def __init__(self, db, library, settings):
        self.db, self.library, self.settings = db, library, settings
        self.directory = settings.data_dir / "originals"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="paper-import")
        self.quotas = library.quotas
        self.lock = self.quotas.lock

    def path(self, identifier):
        if not re.fullmatch(r"[a-f0-9]{32}", identifier):
            raise ValueError("无效的原文件编号。")
        return self.directory / (identifier + ".bin")

    def get(self, identifier):
        row = self.db.one("SELECT * FROM imports WHERE id=?", (identifier,))
        if row:
            row["result"] = json.loads(row["result"]) if row["result"] else None
        return row

    def list(self, workspace):
        ids = self.db.all("SELECT id FROM imports WHERE workspace_id=? ORDER BY created_at DESC LIMIT 100", (workspace,))
        return [self.get(row["id"]) for row in ids]

    def recover(self):
        # An import is either committed with its result in one transaction, or interrupted.
        self.db.execute("""UPDATE imports SET status='failed',error='服务重启中断了导入，请重新上传。',
                        message='导入中断',finished_at=? WHERE status IN ('receiving','queued','parsing','indexing')""", (now(),))
        retained = {json.loads(row["metadata"]).get("original_id") for row in self.db.all("SELECT metadata FROM sources")}
        # Also remove cancelled/duplicate staging files left by a process interruption.
        for path in self.directory.glob("*.bin"):
            if re.fullmatch(r"[a-f0-9]{32}", path.stem) and path.stem not in retained:
                path.unlink(missing_ok=True)

    def submit(self, workspace, name, stream, kind, source_id=None):
        name = PurePosixPath(name.replace("\\", "/")).name[:180]
        if PurePosixPath(name).suffix.lower() not in {".pdf", ".txt", ".md", ".log"}:
            raise ValueError("支持 PDF、UTF-8 TXT、Markdown 和 LOG 文件。")
        stream.seek(0, 2)
        expected_size = stream.tell()
        if expected_size > self.settings.max_upload_bytes:
            raise UploadTooLarge(f"文件超过当前 {self.settings.max_upload_mb} MB 上限。")
        with self.lock:
            if source_id:
                existing = self.db.one("SELECT id FROM imports WHERE source_id=? AND status IN ('receiving','queued','parsing','indexing')", (source_id,))
                if existing:
                    return self.get(existing["id"])
            count = self.db.one("SELECT COUNT(*) AS n FROM imports WHERE status IN ('receiving','queued','parsing','indexing')")["n"]
            if count >= 8:
                raise ImportQueueFull("导入队列已满，请等待已有文件处理完成。")
            identifier = uid()
            reserved_size = 0 if source_id else expected_size
            with self.db.connect() as con:
                con.execute("BEGIN IMMEDIATE")
                owner = self.quotas.owner(con, workspace)
                self.quotas.check_job(con, "imports", owner, reserved_size)
                self.quotas.check_disk(expected_size)
                con.execute("INSERT INTO imports(id,workspace_id,name,kind,status,created_at,source_id,size_bytes) VALUES (?,?,?,?,'receiving',?,?,?)",
                            (identifier, workspace, name, kind, now(), source_id, expected_size))
            self.quotas.jobs["imports"][identifier] = {"owner": owner, "bytes": reserved_size}
        try:
            stream.seek(0)
            size = 0
            with self.path(identifier).open("wb") as target:
                while block := stream.read(1024 * 1024):
                    size += len(block)
                    if size > self.settings.max_upload_bytes:
                        raise UploadTooLarge(f"文件超过当前 {self.settings.max_upload_mb} MB 上限。")
                    target.write(block)
            if size != expected_size:
                raise ValueError("上传文件在保存时发生变化，请重新上传。")
            self.db.execute("UPDATE imports SET status='queued',message='文件已保存，等待解析。',size_bytes=? WHERE id=?", (size, identifier))
            self.pool.submit(self.run, identifier)
            return self.get(identifier)
        except Exception as exc:
            try:
                self.path(identifier).unlink(missing_ok=True)
            finally:
                self.quotas.release("imports", identifier)
            error = str(exc) if isinstance(exc, ValueError) else "文件保存失败，请检查磁盘空间。"
            self.db.execute("UPDATE imports SET status='failed',error=?,finished_at=? WHERE id=?", (error, now(), identifier))
            raise

    def progress(self, identifier, phase, current, total, message):
        with self.db.connect() as con:
            if phase == "indexing":
                changed = con.execute("UPDATE imports SET status=?,message=? WHERE id=? AND status IN ('queued','parsing','indexing')", (phase, message, identifier)).rowcount
            else:
                changed = con.execute("UPDATE imports SET status=?,current_page=?,total_pages=?,message=? WHERE id=? AND status IN ('queued','parsing','indexing')",
                                      (phase, current, total, message, identifier)).rowcount
            if not changed:
                raise ImportCancelled("已取消导入。")

    def run(self, identifier):
        row = self.get(identifier)
        retained = False

        def commit(con, result):
            nonlocal retained
            status = con.execute("SELECT status FROM imports WHERE id=?", (identifier,)).fetchone()[0]
            if status == "cancelled":
                raise ImportCancelled("已取消导入。")
            metadata = result["metadata"]
            # Re-uploading an old source can attach the original without duplicating chunks.
            if not metadata.get("original_id") or not self.path(metadata["original_id"]).is_file():
                metadata["original_id"] = identifier
                metadata["filename"] = row["name"]
                metadata["size_bytes"] = row["size_bytes"]
                con.execute("UPDATE sources SET metadata=? WHERE id=?", (dump(metadata), result["id"]))
                retained = True
            con.execute("UPDATE imports SET status='completed',message=?,result=?,finished_at=? WHERE id=?",
                        ("论文索引已更新，历史证据快照保留。" if result.get("reindexed") else "资料已存在，原文件可用。" if result["duplicate"] else "解析完成，资料可以检索。", dump(result), now(), identifier))

        try:
            self.progress(identifier, "parsing", 0, 0, "正在打开文档。")
            with self.path(identifier).open("rb") as stream:
                self.library.upload_stream(row["workspace_id"], row["name"], stream, row["kind"],
                                           lambda *args: self.progress(identifier, *args), commit, replace_source_id=row.get("source_id"))
        except ImportCancelled:
            retained = False
        except Exception as exc:
            retained = False
            error = str(exc) if isinstance(exc, ValueError) else "文档处理失败，请检查文件与可用磁盘空间。"
            logging.getLogger("uvicorn.error").warning("Import failed: %s", error)
            self.db.execute("UPDATE imports SET status='failed',message='导入失败',error=?,finished_at=? WHERE id=? AND status!='cancelled'",
                            (error, now(), identifier))
        finally:
            try:
                if not retained:
                    self.path(identifier).unlink(missing_ok=True)
            finally:
                self.quotas.release("imports", identifier)

    def cancel(self, identifier):
        self.db.execute("UPDATE imports SET status='cancelled',message='已取消；当前页处理结束后停止。',finished_at=? WHERE id=? AND status IN ('queued','parsing','indexing')",
                        (now(), identifier))
        return self.get(identifier)

    def close(self):
        self.pool.shutdown(wait=True)
