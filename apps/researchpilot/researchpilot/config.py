from dataclasses import dataclass
from pathlib import Path
import os
from urllib.parse import urlsplit

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    data_dir: Path = ROOT / "data"
    mode: str = "offline"
    api_base: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = ""
    embed_model: str = ""
    github_token: str = ""
    max_tool_calls: int = 8
    max_upload_mb: int = 200
    auth_mode: str = "local"
    cookie_secure: bool = False
    public_origin: str = ""
    max_projects: int = 20
    max_sources: int = 200
    max_storage_mb: int = 2048
    max_active_tasks: int = 3
    max_active_imports: int = 2
    max_tasks_daily: int = 100
    min_free_disk_mb: int = 512

    def __post_init__(self):
        if self.auth_mode not in {"local", "accounts"}:
            raise ValueError("RP_AUTH_MODE 必须是 local 或 accounts。")
        if not isinstance(self.max_upload_mb, int) or not 1 <= self.max_upload_mb <= 512:
            raise ValueError("RP_MAX_UPLOAD_MB 必须是 1–512 之间的整数。")
        for name, maximum in {"max_projects":1000,"max_sources":5000,"max_storage_mb":1_048_576,
                              "max_active_tasks":10,"max_active_imports":8,"max_tasks_daily":10000,
                              "min_free_disk_mb":1_048_576}.items():
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError(f"RP_{name.upper()} 必须是 1–{maximum} 之间的整数。")
        if self.public_origin:
            origin = urlsplit(self.public_origin)
            try:
                valid_port = origin.port is None or 1 <= origin.port <= 65535
            except ValueError:
                valid_port = False
            if (origin.scheme != "https" or not origin.hostname or origin.username or origin.password
                    or origin.path or origin.query or origin.fragment or not valid_port
                    or any(c.isspace() or c in '*\\' for c in self.public_origin)
                    or not self.public_origin.isascii()):
                raise ValueError("RP_PUBLIC_ORIGIN 须为完整 HTTPS 站点来源，例如 https://research.example.com，不能含路径、通配符或凭据。")
            if self.auth_mode != "accounts" or not self.cookie_secure:
                raise ValueError("配置 HTTPS 站点时须同时设置 RP_AUTH_MODE=accounts 和 RP_COOKIE_SECURE=true。")

    @property
    def max_upload_bytes(self):
        return self.max_upload_mb * 1024 * 1024

    @property
    def allowed_hosts(self):
        return ["localhost", "127.0.0.1", "[::1]", "testserver"] + ([urlsplit(self.public_origin).hostname] if self.public_origin else [])

    @classmethod
    def from_env(cls):
        load_dotenv(ROOT / ".env")
        mode = os.getenv("RP_MODE", "offline")
        if mode not in {"offline", "llm"}:
            raise ValueError("RP_MODE must be offline or llm")
        data_dir = Path(os.getenv("RP_DATA_DIR", str(ROOT / "data"))).expanduser()
        if not data_dir.is_absolute():
            data_dir = ROOT / data_dir
        secure = os.getenv("RP_COOKIE_SECURE", "false").lower()
        if secure not in {"true", "false"}:
            raise ValueError("RP_COOKIE_SECURE 必须为 true 或 false。")
        return cls(
            data_dir=data_dir.resolve(),
            mode=mode,
            api_base=os.getenv("RP_API_BASE", "https://api.openai.com/v1").rstrip("/"),
            api_key=os.getenv("RP_API_KEY", ""),
            model=os.getenv("RP_MODEL", ""),
            embed_model=os.getenv("RP_EMBED_MODEL", ""),
            github_token=os.getenv("RP_GITHUB_TOKEN", ""),
            max_tool_calls=max(1, min(16, int(os.getenv("RP_MAX_TOOL_CALLS", "8")))),
            max_upload_mb=int(os.getenv("RP_MAX_UPLOAD_MB", "200")),
            auth_mode=os.getenv("RP_AUTH_MODE", "local"),
            cookie_secure=secure == "true",
            public_origin=os.getenv("RP_PUBLIC_ORIGIN", "").rstrip("/"),
            **{name: int(os.getenv("RP_" + name.upper(), str(default))) for name, default in {
                "max_projects":20,"max_sources":200,"max_storage_mb":2048,"max_active_tasks":3,
                "max_active_imports":2,"max_tasks_daily":100,"min_free_disk_mb":512}.items()},
        )
