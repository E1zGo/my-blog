"""Optional local accounts: opaque sessions, invitations and project ownership."""
import argparse
import getpass
import hashlib
import hmac
import re
import secrets
import sqlite3
import threading
import time

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from .db import now, uid

COOKIE = "rp_session"
SESSION_SECONDS = 12 * 60 * 60
INVITE_SECONDS = 24 * 60 * 60
_hash_slots = threading.BoundedSemaphore(2)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def csrf(token):
    return hmac.new(token.encode(), b"researchpilot-csrf-v1", hashlib.sha256).hexdigest()


def username(value):
    value = value.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{2,39}", value):
        raise ValueError("用户名须为 3–40 位英文字母、数字、点、横线或下划线，以字母或数字开头。")
    return value


def _derive(password, salt):
    # Bound concurrent 128 MiB scrypt allocations, including unknown-user checks.
    if not _hash_slots.acquire(timeout=1):
        raise HTTPException(503, "登录服务繁忙，请稍后重试。")
    try:
        return hashlib.scrypt(password.encode(), salt=salt, n=2**17, r=8, p=1, maxmem=256 * 1024**2, dklen=32)
    finally:
        _hash_slots.release()


def password_hash(password):
    if not 15 <= len(password) <= 128:
        raise ValueError("密码须为 15–128 个字符，可使用便于记忆的长句。")
    salt = secrets.token_bytes(16)
    return "scrypt-v1$" + salt.hex() + "$" + _derive(password, salt).hex()


def check_password(password, encoded):
    # Same expensive derivation when an account does not exist or is disabled.
    try:
        version, salt, expected = encoded.split("$")
        if version != "scrypt-v1" or len(salt) != 32 or len(expected) != 64:
            raise ValueError()
        salt, expected = bytes.fromhex(salt), bytes.fromhex(expected)
    except (ValueError, AttributeError):
        salt, expected = bytes(16), bytes(32)
    return hmac.compare_digest(_derive(password, salt), expected)


def public_user(user):
    return {key: user[key] for key in ("id", "username", "role", "active", "created_at")}


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=128)


class Registration(Credentials):
    invitation: str = Field(min_length=1, max_length=128)


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=15, max_length=128)


class MemberStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    active: bool


class Accounts:
    def __init__(self, db, settings):
        self.db, self.settings = db, settings

    def enabled(self):
        if self.settings.auth_mode != "accounts":
            raise HTTPException(409, "账号模式尚未开启，请按本机账号说明配置并重启。")

    def admin(self, request):
        if not request.state.user or request.state.user["role"] != "admin":
            raise HTTPException(403, "此操作仅对管理员开放。")

    def guard(self, request):
        """Run before request bodies, including PDF multipart uploads, are consumed."""
        path, method = request.url.path, request.method
        request.state.user = None
        if not (path.startswith("/api/") or path in {"/docs", "/openapi.json"}):
            return
        configured = bool(self.db.one("SELECT id FROM users LIMIT 1"))
        public = path in {"/api/auth/status", "/api/health", "/api/ready"}
        if self.settings.auth_mode == "local":
            if configured and not public:
                raise HTTPException(503, "此数据目录已有账号。请设置 RP_AUTH_MODE=accounts 后重启服务。")
            return
        token = request.cookies.get(COOKIE, "")
        if token and len(token) <= 128:
            user = self.db.one("SELECT u.* FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.token_hash=? AND s.expires_at>? AND u.active=1", (digest(token), int(time.time())))
            if user:
                request.state.user = public_user(user)
        if public or path in {"/api/auth/login", "/api/auth/register"}:
            return
        if not request.state.user:
            raise HTTPException(401, "请先登录；会话过期后需要重新登录。")
        if method not in {"GET", "HEAD", "OPTIONS"}:
            supplied = request.headers.get("x-csrf-token", "")
            if not hmac.compare_digest(supplied.encode(), csrf(token).encode()):
                raise HTTPException(403, "登录状态已变化，请刷新页面后重试。")
        parts = path.strip("/").split("/")
        if len(parts) >= 2 and parts[1] in {"maintenance", "admin"}:
            self.admin(request)
        if len(parts) < 3 or parts[0] != "api":
            return
        kind, identifier = parts[1:3]
        queries = {
            "workspaces": "SELECT id AS workspace_id FROM workspaces WHERE id=?",
            "sources": "SELECT workspace_id FROM sources WHERE id=?",
            "tasks": "SELECT workspace_id FROM tasks WHERE id=?",
            "imports": "SELECT workspace_id FROM imports WHERE id=?",
        }
        if kind in queries:
            row = self.db.one(queries[kind], (identifier,))
            if not row or not self.db.one("SELECT 1 FROM workspace_owners WHERE workspace_id=? AND user_id=?", (row["workspace_id"], request.state.user["id"])):
                raise HTTPException(404, "项目或资料不存在。")

    def throttle(self, *keys):
        timestamp = int(time.time())
        with self.db.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            con.execute("DELETE FROM auth_attempts WHERE window_start<=?", (timestamp - 900,))
            if con.execute("SELECT COUNT(*) FROM auth_attempts").fetchone()[0] > 5000:
                raise HTTPException(429, "尝试过于频繁，请 15 分钟后重试。")
            for key, limit in keys:
                row = con.execute("SELECT attempts FROM auth_attempts WHERE key=?", (digest(key),)).fetchone()
                if row and row[0] >= limit:
                    raise HTTPException(429, "尝试过于频繁，请 15 分钟后重试。")
            for key, _ in keys:
                con.execute("INSERT INTO auth_attempts VALUES (?,1,?) ON CONFLICT(key) DO UPDATE SET attempts=attempts+1", (digest(key), timestamp))

    def issue_session(self, user, response, *, revoke_all=False, old_token=""):
        token, timestamp = secrets.token_urlsafe(32), int(time.time())
        with self.db.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            current = con.execute("SELECT password_hash,active FROM users WHERE id=?", (user["id"],)).fetchone()
            if not current or not current["active"] or current["password_hash"] != user["password_hash"]:
                raise HTTPException(401, "账号已变化，请重新登录。")
            con.execute("DELETE FROM sessions WHERE expires_at<=?", (timestamp,))
            if revoke_all:
                con.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
            elif old_token:
                con.execute("DELETE FROM sessions WHERE token_hash=?", (digest(old_token),))
            # Avoid accumulating unlimited sessions per account.
            con.execute("DELETE FROM sessions WHERE token_hash IN (SELECT token_hash FROM sessions WHERE user_id=? ORDER BY expires_at DESC LIMIT -1 OFFSET 9)", (user["id"],))
            con.execute("INSERT INTO sessions VALUES (?,?,?)", (digest(token), user["id"], timestamp + SESSION_SECONDS))
        response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True, secure=self.settings.cookie_secure, samesite="strict", path="/")
        return {"user": public_user(user), "csrf_token": csrf(token)}

    def create_admin(self, name, password):
        name, encoded, identifier = username(name), password_hash(password), uid()
        with self.db.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            if con.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                raise ValueError("已有账号，不能再次初始化。忘记密码请使用 reset-password。")
            con.execute("INSERT INTO users VALUES (?,?,?,'admin',1,?)", (identifier, name, encoded, now()))
            con.execute("INSERT INTO workspace_owners SELECT id,? FROM workspaces", (identifier,))
        return identifier

    def reset_password(self, name, password):
        name, encoded = username(name), password_hash(password)
        with self.db.connect() as con:
            user = con.execute("SELECT id FROM users WHERE username=?", (name,)).fetchone()
            if not user:
                raise ValueError("账号不存在。")
            con.execute("UPDATE users SET password_hash=? WHERE id=?", (encoded, user[0]))
            con.execute("DELETE FROM sessions WHERE user_id=?", (user[0],))

    def router(self):
        router = APIRouter()

        @router.get("/api/auth/status")
        def status(request: Request):
            configured = bool(self.db.one("SELECT id FROM users LIMIT 1"))
            user = request.state.user
            return {"mode": self.settings.auth_mode, "setup_required": not configured and self.settings.auth_mode == "accounts",
                    "configuration_error": configured and self.settings.auth_mode == "local", "user": user,
                    "csrf_token": csrf(request.cookies[COOKIE]) if user else None}

        @router.post("/api/auth/login")
        def login(body: Credentials, request: Request, response: Response):
            self.enabled()
            name = body.username.strip().lower()
            self.throttle(("login-ip:" + request.client.host, 30), ("login-user:" + name, 10))
            user = self.db.one("SELECT * FROM users WHERE username=?", (name,))
            valid = check_password(body.password, user["password_hash"] if user else None)
            if not valid or not user or not user["active"]:
                raise HTTPException(401, "用户名或密码错误，或账号已停用。")
            self.db.execute("DELETE FROM auth_attempts WHERE key=?", (digest("login-user:" + name),))
            return self.issue_session(user, response, old_token=request.cookies.get(COOKIE, ""))

        @router.post("/api/auth/logout", status_code=204)
        def logout(request: Request, response: Response):
            self.enabled()
            self.db.execute("DELETE FROM sessions WHERE token_hash=?", (digest(request.cookies.get(COOKIE, "")),))
            response.delete_cookie(COOKIE, path="/", secure=self.settings.cookie_secure, httponly=True, samesite="strict")

        @router.post("/api/auth/password")
        def change_password(body: PasswordChange, request: Request, response: Response):
            self.enabled()
            user_id = request.state.user["id"]
            self.throttle(("password:" + user_id, 10))
            user = self.db.one("SELECT * FROM users WHERE id=?", (user_id,))
            if not check_password(body.current_password, user["password_hash"]):
                raise HTTPException(403, "当前密码不正确。")
            encoded = password_hash(body.new_password)
            with self.db.connect() as con:
                # A concurrent password reset must not be overwritten.
                changed = con.execute("UPDATE users SET password_hash=? WHERE id=? AND password_hash=? AND active=1", (encoded, user_id, user["password_hash"])).rowcount
                if not changed:
                    raise HTTPException(409, "账号已变化，请重新登录。")
                con.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
            user["password_hash"] = encoded
            return self.issue_session(user, response)

        @router.post("/api/admin/invitations", status_code=201)
        def invite(request: Request):
            self.enabled()
            self.admin(request)
            self.throttle(("invite-create:" + request.state.user["id"], 30))
            token, expires = secrets.token_urlsafe(32), int(time.time()) + INVITE_SECONDS
            with self.db.connect() as con:
                con.execute("DELETE FROM invitations WHERE expires_at<=?", (int(time.time()),))
                con.execute("INSERT INTO invitations VALUES (?,?,?)", (digest(token), request.state.user["id"], expires))
            return {"invitation": token, "expires_at": expires}

        @router.post("/api/auth/register", status_code=201)
        def register(body: Registration, request: Request, response: Response):
            self.enabled()
            self.throttle(("register-ip:" + request.client.host, 10))
            name = username(body.username)
            encoded, identifier = password_hash(body.password), uid()
            with self.db.connect() as con:
                con.execute("BEGIN IMMEDIATE")
                invitation = con.execute("SELECT 1 FROM invitations i JOIN users u ON u.id=i.issuer_id WHERE i.token_hash=? AND i.expires_at>? AND u.active=1 AND u.role='admin'", (digest(body.invitation.strip()), int(time.time()))).fetchone()
                if not invitation:
                    raise HTTPException(400, "邀请码无效、已使用或已过期。")
                if con.execute("SELECT 1 FROM users WHERE username=?", (name,)).fetchone():
                    raise HTTPException(409, "该用户名不可用，请换一个。")
                con.execute("INSERT INTO users VALUES (?,?,?,'member',1,?)", (identifier, name, encoded, now()))
                con.execute("DELETE FROM invitations WHERE token_hash=?", (digest(body.invitation.strip()),))
            user = self.db.one("SELECT * FROM users WHERE id=?", (identifier,))
            return self.issue_session(user, response, old_token=request.cookies.get(COOKIE, ""))

        @router.get("/api/admin/users")
        def users(request: Request):
            self.enabled()
            self.admin(request)
            return self.db.all("SELECT id,username,role,active,created_at FROM users ORDER BY created_at")

        @router.patch("/api/admin/users/{user_id}")
        def member_status(user_id: str, body: MemberStatus, request: Request):
            self.enabled()
            self.admin(request)
            with self.db.connect() as con:
                row = con.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
                if not row:
                    raise HTTPException(404, "账号不存在。")
                if row["role"] == "admin":
                    raise HTTPException(422, "不能通过此入口停用管理员。")
                con.execute("UPDATE users SET active=? WHERE id=?", (int(body.active), user_id))
                if not body.active:
                    con.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
            return public_user(self.db.one("SELECT * FROM users WHERE id=?", (user_id,)))

        return router


def main(argv=None):
    parser = argparse.ArgumentParser(description="ResearchPilot 本机账号管理；请先停止服务。密码不会显示或写入命令行历史。")
    parser.add_argument("command", choices=["create-admin", "reset-password"])
    parser.add_argument("--username", required=True)
    args = parser.parse_args(argv)
    from .config import Settings
    from .db import Database
    try:
        # Refuse getpass's echoed-input fallback (e.g. a pipe).
        import sys
        if not sys.stdin.isatty():
            raise ValueError("请在交互式终端运行，以隐藏密码输入。")
        secret = getpass.getpass("密码（15–128 个字符，不显示）: ")
        if secret != getpass.getpass("再次输入密码: "):
            raise ValueError("两次密码不一致。")
        settings = Settings.from_env()
        accounts = Accounts(Database(settings.data_dir), settings)
        if args.command == "create-admin":
            accounts.create_admin(args.username, secret)
            print("管理员已创建，原有项目已归属该账号。请在 .env 中设置 RP_AUTH_MODE=accounts，再启动服务。")
        else:
            accounts.reset_password(args.username, secret)
            print("密码已重置，该账号的所有旧登录会话已失效。")
        return 0
    except (ValueError, sqlite3.Error, HTTPException) as exc:
        print(str(exc.detail if isinstance(exc, HTTPException) else exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
