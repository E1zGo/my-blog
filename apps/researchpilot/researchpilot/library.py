import hashlib
import io
import json
from pathlib import PurePosixPath

from pypdf import PdfReader

from .db import dump, now, uid
from .provider import ModelProvider
from .retrieval import rank, split_text
from .papers import PAPER_INDEX_VERSION, paper_fragments
from .quotas import Quotas, QuotaExceeded

MAX_CHARS = 1_000_000


class UploadTooLarge(ValueError):
    """A byte-size rejection, distinct from document parsing failures."""


class Library:
    def __init__(self, db, settings):
        self.db, self.settings = db, settings
        self.quotas = Quotas(db, settings)

    def list(self, workspace, source_ids=None):
        rows = self.db.all("""SELECT s.*, COUNT(c.id) AS chunk_count FROM sources s
            LEFT JOIN chunks c ON s.id=c.source_id WHERE workspace_id=?
            GROUP BY s.id ORDER BY s.created_at""", (workspace,))
        for row in rows:
            row["metadata"] = json.loads(row["metadata"])
        return [row for row in rows if not source_ids or row["id"] in source_ids]

    def ingest(self, workspace, name, kind, pages, metadata=None, progress=None, on_commit=None, replace_source_id=None):
        metadata = metadata or {}
        pages = list(pages)
        log_text = "\n".join(text for _, text in pages) if kind == "log" else None
        if log_text is not None and len(log_text) > MAX_CHARS:
            raise ValueError("日志最多支持 100 万字符。")
        signature = dump([name, kind, pages, metadata.get("commit")])
        checksum = hashlib.sha256(signature.encode()).hexdigest()
        previous = self.db.one("SELECT id,metadata FROM sources WHERE workspace_id=? AND checksum=?", (workspace, checksum))
        source_id = replace_source_id or uid()
        fragments = []
        structured = kind == "paper" and metadata.get("filename", "").lower().endswith(".pdf")
        if structured:
            metadata["paper_index_version"] = PAPER_INDEX_VERSION
            for page, fragment, structure in paper_fragments(pages):
                fragments.append((uid(), fragment, page, f"第 {page} 页", structure))
        else:
            for page, text in pages:
                for fragment, start, end in split_text(text):
                    locator = f"第 {page} 页" if kind == "paper" else f"{name}:L{start}-L{end}"
                    fragments.append((uid(), fragment, page, locator, {}))
        if not fragments:
            raise ValueError("未发现可提取的文本。扫描版 PDF 请先完成 OCR 后再上传。")
        if progress:
            progress("indexing", 0, 0, f"文字提取完成，正在建立 {len(fragments)} 个检索片段。")
        vectors = []
        embedding_model = ""
        needs_upgrade = previous and structured and (replace_source_id or json.loads(previous["metadata"]).get("paper_index_version", 0) < PAPER_INDEX_VERSION)
        if (not previous or needs_upgrade) and self.settings.mode == "llm" and self.settings.embed_model:
            provider = ModelProvider(self.settings)
            for start in range(0, len(fragments), 32):
                if progress:
                    progress("indexing", 0, 0, f"正在建立语义索引：{start}/{len(fragments)} 个片段。")
                vectors.extend(provider.embed([f[1] for f in fragments[start:start + 32]]))
            embedding_model = self.settings.api_base + "|" + self.settings.embed_model
        metadata["retrieval"] = "hybrid" if vectors else "BM25"
        with self.db.connect() as con:
            # Capacity and deduplication are checked in the same write transaction.
            con.execute("BEGIN IMMEDIATE")
            previous = con.execute("SELECT id,metadata FROM sources WHERE workspace_id=? AND checksum=?", (workspace, checksum)).fetchone()
            if replace_source_id:
                target = con.execute("SELECT id,checksum FROM sources WHERE id=? AND workspace_id=?", (replace_source_id, workspace)).fetchone()
                if not target or target["checksum"] != checksum:
                    raise ValueError("原资料已移除或发生变化，已保留原索引；请刷新资料库。")
            upgrade = previous and structured and (replace_source_id or json.loads(previous["metadata"]).get("paper_index_version", 0) < PAPER_INDEX_VERSION)
            if previous and not upgrade:
                if log_text is not None:
                    con.execute("INSERT OR IGNORE INTO log_documents VALUES (?,?,?)", (previous["id"], log_text, hashlib.sha256(log_text.encode()).hexdigest()))
                result = {"id": previous["id"], "duplicate": True, "name": name, "metadata": json.loads(previous["metadata"])}
                if on_commit:
                    on_commit(con, result)
                return result
            if upgrade:
                source_id = previous["id"]
                metadata = {**json.loads(previous["metadata"]), **metadata}
                con.execute("DELETE FROM chunks WHERE source_id=?", (source_id,))
            else:
                if con.execute("SELECT COUNT(*) FROM sources WHERE workspace_id=?", (workspace,)).fetchone()[0] >= self.settings.max_sources:
                    raise QuotaExceeded(f"每个项目最多保存 {self.settings.max_sources} 份资料，请移除不需要的资料后重试。", "source_quota")
            self.quotas.check_disk()
            count = con.execute("SELECT COUNT(*) FROM chunks c JOIN sources s ON s.id=c.source_id WHERE s.workspace_id=?", (workspace,)).fetchone()[0]
            if count + len(fragments) > 5000:
                raise ValueError("单个项目最多保存 5000 个文本片段，请创建新的项目。")
            if upgrade:
                con.execute("UPDATE sources SET metadata=? WHERE id=?", (dump(metadata), source_id))
            else:
                con.execute("INSERT INTO sources VALUES (?,?,?,?,?,?,?)",
                            (source_id, workspace, name, kind, checksum, dump(metadata), now()))
            if log_text is not None:
                con.execute("INSERT INTO log_documents VALUES (?,?,?)", (source_id, log_text, hashlib.sha256(log_text.encode()).hexdigest()))
            for i, (chunk_id, text, page, locator, structure) in enumerate(fragments):
                con.execute("INSERT INTO chunks(id,source_id,text,page,locator,vector,embedding_model,structure) VALUES (?,?,?,?,?,?,?,?)",
                            (chunk_id, source_id, text, page, locator, dump(vectors[i]) if vectors else None, embedding_model, dump(structure)))
            result = {"id": source_id, "name": name, "chunk_count": len(fragments), "duplicate": False, "reindexed": bool(upgrade), "metadata": metadata}
            if on_commit:
                on_commit(con, result)
        return result

    def upload(self, workspace, name, data, kind="paper"):
        return self.upload_stream(workspace, name, io.BytesIO(data), kind)

    def upload_stream(self, workspace, name, stream, kind="paper", progress=None, on_commit=None, replace_source_id=None):
        """Read a seekable file directly; do not copy a 200 MB PDF into a bytes buffer."""
        name = PurePosixPath(name.replace("\\", "/")).name[:180]
        if not name:
            raise ValueError("文件名不能为空。")
        stream.seek(0, 2)
        size = stream.tell()
        stream.seek(0)
        if size > self.settings.max_upload_bytes:
            raise UploadTooLarge(f"文件超过当前 {self.settings.max_upload_mb} MB 上限。可在 .env 中调整 RP_MAX_UPLOAD_MB 后重启服务。")
        suffix = PurePosixPath(name).suffix.lower()
        metadata = {"filename": name, "warnings": [], "size_bytes": size}
        if suffix == ".pdf":
            if stream.read(5) != b"%PDF-":
                raise ValueError("文件内容不是有效的 PDF。")
            stream.seek(0)
            if progress:
                progress("parsing", 0, 0, "正在读取 PDF 页数与结构。")
            try:
                reader = PdfReader(stream)
                if reader.is_encrypted:
                    raise ValueError("请上传未加密的 PDF。")
                if len(reader.pages) > 300:
                    raise ValueError("PDF 最多支持 300 页。")
                pages = []
                total = 0
                empty_pages = 0
                for number, page in enumerate(reader.pages, 1):
                    if progress:
                        progress("parsing", number - 1, len(reader.pages), f"正在提取第 {number}/{len(reader.pages)} 页文字。")
                    text = page.extract_text() or ""
                    total += len(text)
                    if total > MAX_CHARS:
                        raise ValueError("文档文本过长，最多支持 100 万字符。")
                    if not text.strip():
                        empty_pages += 1
                        metadata["warnings"].append(f"第 {number} 页没有提取到文字，可能需要 OCR。")
                    pages.append((number, text))
                metadata["pages"] = len(reader.pages)
                metadata["text_pages"] = len(reader.pages) - empty_pages
                metadata["characters"] = total
            except ValueError:
                raise
            except Exception:
                raise ValueError("PDF 解析失败，请检查文件是否损坏。") from None
            kind = "paper"
        elif suffix in {".txt", ".md", ".log"}:
            if progress:
                progress("parsing", 0, 1, "正在解码 UTF-8 文本。")
            try:
                # UTF-8 characters use at most 4 bytes. Bound memory for non-PDF input too.
                data = stream.read(MAX_CHARS * 4 + 4)
                if len(data) > MAX_CHARS * 4 + 3:
                    raise ValueError("文档文本过长，最多支持 100 万字符。")
                text = data.decode("utf-8-sig")
            except UnicodeDecodeError:
                raise ValueError("文本文件请保存为 UTF-8 编码。") from None
            if len(text) > MAX_CHARS:
                raise ValueError("文档文本过长，最多支持 100 万字符。")
            if "\x00" in text:
                raise ValueError("不支持二进制文本文件。")
            kind = "log" if suffix == ".log" or kind == "log" else "paper"
            pages = [(1, text)]
            metadata["pages"] = 1
            metadata["characters"] = len(text)
        else:
            raise ValueError("支持 PDF、UTF-8 TXT、Markdown 和 LOG 文件。")
        if progress:
            progress("parsing", metadata["pages"], metadata["pages"], "文本提取完成。")
        return self.ingest(workspace, name, kind, pages, metadata, progress, on_commit, replace_source_id)

    def chunks(self, workspace, kind="all", source_id=None, source_ids=None, page_range=None):
        sql = """SELECT c.*, s.name, s.kind, s.metadata FROM chunks c
                 JOIN sources s ON c.source_id=s.id WHERE s.workspace_id=?"""
        args = [workspace]
        if kind != "all":
            sql += " AND s.kind=?"
            args.append(kind)
        if source_id:
            sql += " AND s.id=?"
            args.append(source_id)
        if source_ids:
            sql += " AND s.id IN (" + ",".join("?" for _ in source_ids) + ")"
            args.extend(source_ids)
        if page_range:
            sql += " AND c.page BETWEEN ? AND ?"
            args.extend((page_range["start"], page_range["end"]))
        rows = self.db.all(sql + " ORDER BY s.created_at,c.page,c.rowid", args)
        for row in rows:
            row["vector"] = json.loads(row["vector"]) if row["vector"] else None
            row["metadata"] = json.loads(row["metadata"])
            row["structure"] = json.loads(row["structure"])
        return rows

    def search(self, workspace, query, k=5, kind="all", source_ids=None, page_range=None):
        rows = self.chunks(workspace, kind, source_ids=source_ids, page_range=page_range)
        vector = None
        key = self.settings.api_base + "|" + self.settings.embed_model
        if self.settings.mode == "llm" and self.settings.embed_model and any(r["embedding_model"] == key for r in rows):
            vector = ModelProvider(self.settings).embed([query])[0]
            for row in rows:
                if row["embedding_model"] != key:
                    row["vector"] = None
        results = rank(query, rows, k=k, query_vector=vector)
        for result in results:
            result.pop("vector", None)
            result.pop("embedding_model", None)
        return results
