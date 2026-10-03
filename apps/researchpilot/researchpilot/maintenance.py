"""Local data snapshots and recovery. Never overwrite an existing data directory."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import sys
import tempfile
import time
import zipfile

from . import __version__

DATABASE = "researchpilot.sqlite3"
TABLES = ("workspaces", "sources", "chunks", "tasks", "events", "imports", "notes", "experiments", "log_documents")
AUTH_TABLES = ("users", "workspace_owners", "sessions", "invitations", "auth_attempts")
MAX_FILES = 10_000
MAX_BYTES = 10 * 1024**3
MAX_MANIFEST = 4 * 1024**2
ORIGINAL = re.compile(r"originals/[a-f0-9]{32}\.bin\Z")
DEPENDENCIES = ("fastapi", "uvicorn", "pypdf", "pypdfium2", "Pillow", "httpx", "python-dotenv", "python-multipart")


class MaintenanceError(ValueError):
    pass


def _readonly(path):
    con = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    con.execute("PRAGMA query_only=ON")
    con.execute("PRAGMA trusted_schema=OFF")
    return con


def _inventory(con):
    if con.execute("PRAGMA quick_check").fetchall() != [("ok",)] or con.execute("PRAGMA foreign_key_check").fetchone():
        raise MaintenanceError("数据库完整性检查未通过，请保留现有数据并排查。")
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not set(TABLES) <= tables:
        raise MaintenanceError("数据库缺少必需的表，请先用兼容版本打开项目。")
    counts = {table: con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in TABLES}
    if set(AUTH_TABLES) & tables:
        if not set(AUTH_TABLES) <= tables:
            raise MaintenanceError("账号表不完整，请检查数据库版本。")
        counts.update({table: con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in AUTH_TABLES})
        if counts["users"] and counts["workspace_owners"] != counts["workspaces"]:
            raise MaintenanceError("存在未分配归属的项目，请先检查账号迁移。")
    originals, legacy = set(), 0
    for (metadata,) in con.execute("SELECT metadata FROM sources"):
        try:
            meta = json.loads(metadata)
            identifier = meta.get("original_id")
        except (ValueError, AttributeError):
            raise MaintenanceError("资料元数据损坏，无法确认原文件清单。") from None
        if identifier is None:
            legacy += 1
        elif not isinstance(identifier, str) or not re.fullmatch(r"[a-f0-9]{32}", identifier):
            raise MaintenanceError("资料包含无效的原文件编号。")
        else:
            originals.add(f"originals/{identifier}.bin")
    active = con.execute("SELECT COUNT(*) FROM tasks WHERE status IN ('queued','running')").fetchone()[0]
    active += con.execute("SELECT COUNT(*) FROM imports WHERE status IN ('receiving','queued','parsing','indexing')").fetchone()[0]
    return {"counts": counts, "originals": sorted(originals), "without_original": legacy, "active_jobs": active}


def _file_in(directory, name):
    path = directory / name
    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
        raise MaintenanceError("原文件不允许使用链接，请检查数据目录。")
    if not path.is_file() or path.resolve().parent != (directory / "originals").absolute():
        raise MaintenanceError("缺少或无法访问已登记的原文件；请补齐原文件后再备份。")
    return path


def _copy_hash(source, target, limit):
    digest, size = hashlib.sha256(), 0
    while block := source.read(1024 * 1024):
        size += len(block)
        if size > limit:
            raise MaintenanceError("文件实际大小超过清单或备份容量限制。")
        digest.update(block)
        target.write(block)
    return {"size": size, "sha256": digest.hexdigest()}


def create_backup(data_dir, destination):
    """SQLite backup snapshot first; package only its referenced immutable files."""
    directory, destination = Path(data_dir).resolve(), Path(destination).absolute()
    if not (directory / DATABASE).is_file():
        raise MaintenanceError("尚未找到项目数据库，请先启动一次 ResearchPilot。")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        raise MaintenanceError("备份目标已存在，请使用新的文件名。")
    with tempfile.TemporaryDirectory(prefix="rp-backup-", dir=destination.parent) as staging:
        stage = Path(staging)
        deadline = time.monotonic() + 30

        def progress(status, remaining, total):
            if time.monotonic() > deadline:
                raise MaintenanceError("数据库正在持续写入，请稍后重试备份。")

        with closing(_readonly(directory / DATABASE)) as source, closing(sqlite3.connect(stage / DATABASE)) as snapshot:
            source.backup(snapshot, pages=256, progress=progress)
            snapshot.execute("PRAGMA journal_mode=DELETE")
            tables = {r[0] for r in snapshot.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if set(AUTH_TABLES) <= tables:
                snapshot.execute("PRAGMA secure_delete=ON")
                for table in ("sessions", "invitations", "auth_attempts"):
                    snapshot.execute(f"DELETE FROM {table}")
                snapshot.commit()
                snapshot.execute("VACUUM")
            inventory = _inventory(snapshot)
        if inventory["active_jobs"]:
            raise MaintenanceError("仍有导入或研究任务未结束，请完成或取消后再备份。")
        if len(inventory["originals"]) + 2 > MAX_FILES:
            raise MaintenanceError("备份文件数超过当前上限。")
        manifest = {"format": "researchpilot-backup", "format_version": 1, "app_version": __version__,
                    "created_at": datetime.now(timezone.utc).isoformat(), "inventory": inventory, "files": {}}
        remaining = MAX_BYTES - MAX_MANIFEST
        archive = stage / "backup.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as bundle:
            for name in [DATABASE, *inventory["originals"]]:
                path = stage / DATABASE if name == DATABASE else _file_in(directory, name)
                with path.open("rb") as src, bundle.open(name, "w", force_zip64=True) as dst:
                    item = _copy_hash(src, dst, remaining)
                manifest["files"][name] = item
                remaining -= item["size"]
            encoded = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
            if len(encoded) > MAX_MANIFEST:
                raise MaintenanceError("备份清单超过当前上限。")
            bundle.writestr("manifest.json", encoded)
        # Exclusive creation preserves any file another process created meanwhile.
        created = False
        try:
            with destination.open("xb") as output, archive.open("rb") as source:
                created = True
                shutil.copyfileobj(source, output, 1024 * 1024)
        except BaseException:
            if created:
                destination.unlink(missing_ok=True)
            raise
    return manifest


def _unpack_verified(archive, directory):
    with zipfile.ZipFile(archive) as bundle:
        entries = bundle.infolist()
        names = [entry.filename for entry in entries]
        if len(entries) > MAX_FILES or len(names) != len(set(names)) or "manifest.json" not in names:
            raise MaintenanceError("备份清单缺失、存在重复路径或文件数超限。")
        if sum(entry.file_size for entry in entries) > MAX_BYTES:
            raise MaintenanceError("备份展开大小超过 10 GB 上限。")
        for entry in entries:
            if entry.filename not in {DATABASE, "manifest.json"} and not ORIGINAL.fullmatch(entry.filename):
                raise MaintenanceError("备份包含不允许的文件路径。")
            mode = (entry.external_attr >> 16) & 0o170000
            if entry.is_dir() or mode not in (0, stat.S_IFREG) or entry.flag_bits & 1:
                raise MaintenanceError("备份不允许目录、链接或加密条目。")
        info = bundle.getinfo("manifest.json")
        if info.file_size > MAX_MANIFEST:
            raise MaintenanceError("备份清单过大。")
        try:
            manifest = json.loads(bundle.read(info))
            valid = manifest["format"] == "researchpilot-backup" and type(manifest["format_version"]) is int and manifest["format_version"] == 1
            release = manifest["app_version"]
            valid = valid and isinstance(release, str) and bool(re.fullmatch(r"\d+\.\d+\.\d+", release))
            valid = valid and tuple(map(int, release.split("."))) <= tuple(map(int, __version__.split(".")))
            files = manifest["files"]
            valid = valid and isinstance(files, dict) and set(files) == set(names) - {"manifest.json"} and DATABASE in files
        except (KeyError, TypeError, ValueError):
            valid = False
        if not valid:
            raise MaintenanceError("备份清单无效或来自更新版本，请核对版本后重试。")
        for name, expected in files.items():
            if not isinstance(expected, dict) or type(expected.get("size")) is not int or expected["size"] < 0 or not isinstance(expected.get("sha256"), str):
                raise MaintenanceError("备份文件校验信息无效。")
            info = bundle.getinfo(name)
            if info.file_size != expected["size"]:
                raise MaintenanceError("备份文件大小与清单不一致。")
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(info) as src, path.open("xb") as dst:
                actual = _copy_hash(src, dst, info.file_size)
            if actual != expected:
                raise MaintenanceError("备份文件校验失败，可能已损坏或被修改。")
        with closing(_readonly(directory / DATABASE)) as con:
            inventory = _inventory(con)
        if set(files) != {DATABASE, *inventory["originals"]} or inventory != manifest.get("inventory") or inventory["active_jobs"]:
            raise MaintenanceError("数据库与备份清单不一致或包含未结束任务。")
        return manifest


def verify_backup(archive):
    with tempfile.TemporaryDirectory(prefix="rp-verify-") as staging:
        return _unpack_verified(archive, Path(staging))


def restore_backup(archive, destination):
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise MaintenanceError("恢复目标必须是尚不存在的新目录，现有数据不会被覆盖。")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="rp-restore-", dir=destination.parent) as staging:
        stage = Path(staging)
        manifest = _unpack_verified(archive, stage)
        # Reserve the name only after all validation, and never replace an existing directory.
        destination.mkdir()
        try:
            for item in stage.iterdir():
                item.rename(destination / item.name)
        except BaseException:
            shutil.rmtree(destination)
            raise
    return manifest


def doctor(data_dir, mode="offline", auth_mode="local"):
    directory = Path(data_dir).resolve()
    checks = [{"name": "Python", "area": "environment", "status": "ok" if sys.version_info >= (3, 11) else "error", "message": sys.version.split()[0]}]
    for dependency in DEPENDENCIES:
        try:
            message, status = version(dependency), "ok"
        except PackageNotFoundError:
            message, status = "未安装，请按 requirements-lock.txt 安装依赖。", "error"
        checks.append({"name": dependency, "area": "environment", "status": status, "message": message})
    inventory = None
    if not (directory / DATABASE).exists():
        checks.append({"name": "项目数据", "status": "warning", "message": "尚未初始化；首次启动后会创建空数据库。"})
    else:
        try:
            with closing(_readonly(directory / DATABASE)) as con:
                con.execute("BEGIN")
                inventory = _inventory(con)
            for name in inventory["originals"]:
                _file_in(directory, name)
            checks.append({"name": "数据库与原文件", "status": "ok", "message": f"完整性检查通过，{len(inventory['originals'])} 份已保存原文件可访问。"})
            has_users = bool(inventory["counts"].get("users"))
            if has_users and auth_mode != "accounts":
                checks.append({"name": "账号配置", "status": "error", "message": "此目录已有账号，请设置 RP_AUTH_MODE=accounts 后重启；服务已拒绝匿名访问。"})
            elif auth_mode == "accounts" and not has_users:
                checks.append({"name": "账号配置", "status": "warning", "message": "尚未创建管理员，请使用本机 accounts create-admin 命令初始化。"})
            else:
                checks.append({"name": "账号配置", "status": "ok", "message": "账号登录与项目隔离已启用。" if has_users else "本机单人模式，无需登录。"})
            if inventory["without_original"]:
                checks.append({"name": "仅有提取文本的资料", "status": "warning", "message": f"{inventory['without_original']} 份资料无原文件副本（可包括教学示例）；备份会保留现有文本。"})
            if inventory["active_jobs"]:
                checks.append({"name": "后台任务", "status": "warning", "message": "有未结束任务，请完成或取消后再备份。"})
        except (MaintenanceError, sqlite3.Error, OSError) as exc:
            checks.append({"name": "数据库与原文件", "status": "error", "message": str(exc) if isinstance(exc, MaintenanceError) else "无法检查，请核对数据目录、权限和数据库文件。"})
    ancestor = directory
    while not ancestor.exists():
        ancestor = ancestor.parent
    free = shutil.disk_usage(ancestor).free
    checks.append({"name": "可用磁盘", "status": "ok" if free >= 1024**3 else "warning", "message": f"{free / 1024**3:.1f} GB；备份与恢复还需要容纳数据库和全部原文件的空间。"})
    return {"version": __version__, "mode": mode, "auth_mode": auth_mode, "ok": not any(c["status"] == "error" for c in checks), "checks": checks,
            "counts": inventory["counts"] if inventory else None, "backup_ready": bool(inventory) and not inventory["active_jobs"] and not any(c["status"] == "error" for c in checks)}


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure") and not stream.isatty():
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="ResearchPilot 本机自检、完整备份、校验与恢复")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("doctor", "backup"):
        command = commands.add_parser(name)
        command.add_argument("--data-dir", type=Path)
        if name == "backup":
            command.add_argument("--output", type=Path, required=True)
    for name in ("verify", "restore"):
        command = commands.add_parser(name)
        command.add_argument("archive", type=Path)
        if name == "restore":
            command.add_argument("--to", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command in {"doctor", "backup"}:
            try:
                from .config import Settings
            except ImportError:
                if args.command != "doctor":
                    raise MaintenanceError("缺少运行依赖，请先按 requirements-lock.txt 安装。") from None
                result = doctor(args.data_dir or Path(__file__).resolve().parent.parent / "data")
            else:
                settings = Settings.from_env()
                directory = args.data_dir if args.data_dir is not None else settings.data_dir
                result = doctor(directory, settings.mode, settings.auth_mode) if args.command == "doctor" else create_backup(directory, args.output)
        else:
            result = verify_backup(args.archive) if args.command == "verify" else restore_backup(args.archive, args.to)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if args.command == "doctor" and not result["ok"] else 0
    except (ValueError, OSError, sqlite3.Error, zipfile.BadZipFile, RuntimeError) as exc:
        message = str(exc) if isinstance(exc, MaintenanceError) else "操作失败，请核对文件、磁盘空间、目录权限及本机配置。"
        print(json.dumps({"ok": False, "error": message}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
