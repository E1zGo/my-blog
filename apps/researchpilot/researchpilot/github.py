"""Read-only GitHub importer; no cloning, execution, or arbitrary outbound URLs."""
import base64
import re
import time
from pathlib import PurePosixPath
from urllib.parse import quote, urlparse

import httpx


def parse_repo(url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != "github.com" or parsed.query or parsed.fragment:
        raise ValueError("请输入 https://github.com/owner/repository 格式的公开仓库地址。")
    parts = parsed.path.strip("/").split("/")
    if len(parts) != 2 or any(not re.fullmatch(r"[A-Za-z0-9_.-]+", p) or p in {".", ".."} for p in parts):
        raise ValueError("请填写仓库主页，不要填写分支或文件页面。")
    return parts[0], parts[1].removesuffix(".git")


def priority(path):
    name = PurePosixPath(path).name.lower()
    if name.startswith("readme"):
        return 0
    if name in {"requirements.txt", "pyproject.toml", "environment.yml", "environment.yaml", "setup.py"}:
        return 1
    if any(word in name for word in ("infer", "train", "eval", "demo", "sample", "test")):
        return 2
    return 3


def allowed_file(item):
    path = item.get("path", "")
    parts = PurePosixPath(path).parts
    return (item.get("type") == "blob" and item.get("mode") != "120000"
            and 0 < item.get("size", 0) <= 200_000
            and len(path) < 250 and not any(p.startswith(".") or p in {"node_modules", "vendor", "venv"} for p in parts)
            and PurePosixPath(path).suffix.lower() in {".md", ".txt", ".py", ".toml", ".yaml", ".yml", ".sh"}
            and not any(w in path.lower() for w in ("secret", "credential", "token")))


def fetch_repository(url, token="", client=None):
    owner, repo = parse_repo(url)
    prefix = f"https://api.github.com/repos/{owner}/{repo}"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "ResearchPilot/0.1"}
    if token:
        headers["Authorization"] = "Bearer " + token
    owned = client is None
    client = client or httpx.Client(timeout=20, follow_redirects=False)

    def get(path):
        try:
            response = client.get(prefix + path, headers=headers)
            if response.status_code in {403, 429}:
                raise ValueError("GitHub 限流或访问被拒绝，请稍后重试，或在 .env 配置 GitHub Token。")
            if response.status_code == 404:
                raise ValueError("仓库不存在或不可访问；请检查地址和仓库可见性。")
            if response.status_code != 200:
                raise ValueError(f"GitHub 返回 HTTP {response.status_code}，未跟随重定向。")
            return response.json()
        except httpx.HTTPError:
            raise ValueError("GitHub 网络连接失败。离线时可使用内置示例资料。") from None

    try:
        metadata = get("")
        if metadata.get("private"):
            raise ValueError("当前导入器仅支持公开仓库。")
        commit = get("/commits/" + quote(metadata["default_branch"], safe=""))
        sha = commit["sha"]
        tree = get("/git/trees/" + commit["commit"]["tree"]["sha"] + "?recursive=1")
        eligible = sorted((i for i in tree["tree"] if allowed_file(i)), key=lambda i: (priority(i["path"]), i["path"]))
        warnings = []
        if tree.get("truncated"):
            warnings.append("GitHub 返回的目录树被截断，分析不覆盖全部文件。")
        if len(eligible) > 20:
            warnings.append(f"找到 {len(eligible)} 个符合条件的文件，本次按优先级读取前 20 个。")
        files, started = [], time.monotonic()
        for item in eligible[:20]:
            if time.monotonic() - started > 75:
                warnings.append("已达到导入时间上限，仅保存已读取文件。")
                break
            try:
                blob = get("/git/blobs/" + item["sha"])
                if blob.get("encoding") != "base64" or blob.get("size", 0) > 200_000:
                    warnings.append(f"跳过不支持的文件：{item['path']}")
                    continue
                raw = base64.b64decode(blob["content"])
                if len(raw) > 200_000:
                    continue
                text = raw.decode("utf-8")
                if text.strip() and "\x00" not in text:
                    files.append({"path": item["path"], "text": text})
            except (UnicodeDecodeError, ValueError):
                warnings.append(f"未能读取文件：{item['path']}")
        if not files:
            raise ValueError("没有读取到可分析的文本文件。")
        return {"repo": f"{owner}/{repo}", "url": f"https://github.com/{owner}/{repo}",
                "commit": sha, "branch": metadata["default_branch"], "files": files,
                "tree": [i["path"] for i in tree["tree"][:500]], "warnings": warnings}
    except (KeyError, TypeError):
        raise ValueError("GitHub 响应格式不完整，无法解析仓库。") from None
    finally:
        if owned:
            client.close()
