"""Admin UI authentication: allowlist + domain + company password + email OTP."""

from __future__ import annotations

import logging
import os
import secrets
import smtplib
import string
import threading
import time
from email.message import EmailMessage
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from passlib.hash import bcrypt
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

AUTH_GENERIC_REQUEST = (
    "If this address is authorized and credentials are correct, a code was sent."
)
AUTH_GENERIC_VERIFY = "Invalid email, code, or password."
OTP_TTL_SEC = 600
SESSION_MAX_AGE_SEC = 86400
_RL_WINDOW_SEC = 900
_RL_MAX_PER_EMAIL = 8
_RL_MAX_PER_IP = 40
_RL_MAX_PASSWORD_FAIL = 15

_otp_memory: dict[str, tuple[str, float]] = {}
_otp_lock = threading.Lock()


def _truthy_env(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in ("1", "true", "yes", "on")


def _parse_csv_emails(raw: str) -> set[str]:
    out: set[str] = set()
    for part in raw.split(","):
        e = part.strip().lower()
        if e:
            out.add(e)
    return out


def _parse_csv_domains(raw: str) -> tuple[str, ...]:
    doms: list[str] = []
    for part in raw.split(","):
        d = part.strip().lower().lstrip("@")
        if d:
            doms.append(d)
    return tuple(doms)


def redis_url() -> Optional[str]:
    for name in ("REDIS_URL", "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND"):
        raw = (os.environ.get(name) or "").strip()
        if raw.lower().startswith("redis"):
            return raw
    return None


def _redis_client():
    url = redis_url()
    if not url:
        return None
    try:
        import redis

        return redis.from_url(url)
    except Exception as exc:
        logger.warning("Admin auth: Redis unavailable (%s); using in-memory OTP store.", exc)
        return None


def normalize_email(email: str) -> str:
    return email.strip().lower()


def email_domain_ok(email: str, domains: tuple[str, ...]) -> bool:
    if "@" not in email:
        return False
    _, _, rest = email.partition("@")
    dom = rest.lower()
    return any(dom == d or dom.endswith("." + d) for d in domains)


def auth_disabled() -> bool:
    return _truthy_env("ADMIN_AUTH_DISABLED")


def auth_configured() -> bool:
    if auth_disabled():
        return True
    allow = _parse_csv_emails(os.getenv("ADMIN_EMAIL_ALLOWLIST") or "")
    if not allow:
        return False
    secret = (os.getenv("ADMIN_SESSION_SECRET") or "").strip()
    if len(secret) < 16:
        return False
    if (os.getenv("ADMIN_COMPANY_PASSWORD_HASH") or "").strip():
        return True
    if (os.getenv("ADMIN_COMPANY_PASSWORD") or "").strip():
        return True
    return False


def _verify_company_password(plain: str) -> bool:
    h = (os.getenv("ADMIN_COMPANY_PASSWORD_HASH") or "").strip()
    if h:
        try:
            return bcrypt.verify(plain, h)
        except Exception:
            return False
    p = os.getenv("ADMIN_COMPANY_PASSWORD")
    if p is None:
        return False
    return secrets.compare_digest(plain, p)


def _serializer() -> URLSafeTimedSerializer:
    secret = (os.getenv("ADMIN_SESSION_SECRET") or "").strip()
    return URLSafeTimedSerializer(secret, salt="graph-enterprise-admin")


def create_session_token(email: str) -> str:
    if auth_disabled():
        secret = (os.getenv("ADMIN_SESSION_SECRET") or "").strip() or "dev-insecure-admin-session-secret"
        return URLSafeTimedSerializer(secret, salt="graph-enterprise-admin").dumps(
            {"email": email}
        )
    return _serializer().dumps({"email": email})


def verify_session_token(token: str) -> str:
    try:
        data = _serializer().loads(token, max_age=SESSION_MAX_AGE_SEC)
    except SignatureExpired as e:
        raise HTTPException(status_code=401, detail="Session expired.") from e
    except BadSignature as e:
        raise HTTPException(status_code=401, detail="Invalid session.") from e
    email = data.get("email")
    if not isinstance(email, str) or not email:
        raise HTTPException(status_code=401, detail="Invalid session.")
    return normalize_email(email)


def client_ip(request: Request) -> str:
    ff = request.headers.get("x-forwarded-for")
    if ff:
        return ff.split(",")[0].strip() or "unknown"
    if request.client:
        return request.client.host
    return "unknown"


def _otp_key(email: str) -> str:
    return f"ge:admin_otp:{email}"


def _rl_key_ip(ip: str) -> str:
    return f"ge:admin_rl:ip:{ip}"


def _rl_key_email(email: str) -> str:
    return f"ge:admin_rl:email:{email}"


def _rl_key_pwd(ip: str) -> str:
    return f"ge:admin_rl:pwd:{ip}"


def _incr_rl(r: Any, key: str, limit: int) -> bool:
    try:
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, _RL_WINDOW_SEC)
        n, _ = pipe.execute()
        return int(n) <= limit
    except Exception as exc:
        logger.warning("Admin auth rate limit Redis error: %s", exc)
        return True


def check_rate_limits(request: Request, email: str, *, pwd_fail: bool = False) -> None:
    r = _redis_client()
    ip = client_ip(request)
    if r:
        if not _incr_rl(r, _rl_key_ip(ip), _RL_MAX_PER_IP):
            raise HTTPException(status_code=429, detail="Too many requests. Try later.")
        if not _incr_rl(r, _rl_key_email(email), _RL_MAX_PER_EMAIL):
            raise HTTPException(status_code=429, detail="Too many requests. Try later.")
        if pwd_fail and not _incr_rl(r, _rl_key_pwd(ip), _RL_MAX_PASSWORD_FAIL):
            raise HTTPException(status_code=429, detail="Too many requests. Try later.")


def _generate_otp() -> str:
    return "".join(secrets.choice(string.digits) for _ in range(6))


def _otp_store(email: str, code: str) -> None:
    hashed = bcrypt.hash(code)
    r = _redis_client()
    if r:
        try:
            r.set(_otp_key(email), hashed, ex=OTP_TTL_SEC)
            return
        except Exception as exc:
            logger.warning("Admin auth OTP Redis set failed, using memory: %s", exc)
    exp = time.monotonic() + OTP_TTL_SEC
    with _otp_lock:
        _otp_memory[email] = (hashed, exp)


def _otp_consume(email: str, code: str) -> bool:
    r = _redis_client()
    if r:
        try:
            raw = r.get(_otp_key(email))
            if not raw:
                return False
            stored = raw.decode() if isinstance(raw, bytes) else str(raw)
            ok = bcrypt.verify(code, stored)
            if ok:
                r.delete(_otp_key(email))
            return ok
        except Exception as exc:
            logger.warning("Admin auth OTP Redis consume failed, trying memory: %s", exc)
    with _otp_lock:
        entry = _otp_memory.pop(email, None)
    if not entry:
        return False
    stored, exp = entry
    if time.monotonic() > exp:
        return False
    return bcrypt.verify(code, stored)


def _send_otp_email(to_addr: str, code: str) -> None:
    if _truthy_env("ADMIN_OTP_LOG_TO_CONSOLE"):
        logger.warning("ADMIN_OTP_LOG_TO_CONSOLE: OTP for %s is %s", to_addr, code)
        return
    host = (os.getenv("SMTP_HOST") or "").strip()
    if not host:
        raise RuntimeError("SMTP_HOST is not set (or enable ADMIN_OTP_LOG_TO_CONSOLE=1 for dev).")
    port = int((os.getenv("SMTP_PORT") or "587").strip() or "587")
    user = (os.getenv("SMTP_USER") or "").strip()
    password = (os.getenv("SMTP_PASSWORD") or "").strip()
    from_addr = (os.getenv("SMTP_FROM") or user or "").strip()
    if not from_addr:
        raise RuntimeError("SMTP_FROM or SMTP_USER must be set for sending mail.")
    use_tls = not _truthy_env("SMTP_DISABLE_TLS")
    msg = EmailMessage()
    msg["Subject"] = "Admin sign-in code"
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(
        f"Your admin sign-in code is: {code}\n\n"
        f"It expires in {OTP_TTL_SEC // 60} minutes. If you did not request this, ignore this email."
    )
    with smtplib.SMTP(host, port, timeout=30) as smtp:
        if use_tls:
            smtp.starttls()
        if user and password:
            smtp.login(user, password)
        smtp.send_message(msg)


def gates_pass(email_norm: str) -> bool:
    allow = _parse_csv_emails(os.getenv("ADMIN_EMAIL_ALLOWLIST") or "")
    if not allow:
        return False
    if email_norm not in allow:
        return False
    domains = _parse_csv_domains(os.getenv("ALLOWED_EMAIL_DOMAINS") or "")
    if not domains:
        return False
    return email_domain_ok(email_norm, domains)


async def require_admin(authorization: Optional[str] = Header(None)) -> str:
    if auth_disabled():
        return "dev@auth-disabled.local"
    if not auth_configured():
        raise HTTPException(
            status_code=503,
            detail="Admin authentication is not configured on the server.",
        )
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated.")
    token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    email = verify_session_token(token)
    allow = _parse_csv_emails(os.getenv("ADMIN_EMAIL_ALLOWLIST") or "")
    if email not in allow:
        raise HTTPException(status_code=403, detail="Forbidden.")
    return email


class RequestCodeBody(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)
    company_password: str = Field(..., min_length=1, max_length=500)


class VerifyBody(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)
    company_password: str = Field(..., min_length=1, max_length=500)
    code: str = Field(..., min_length=4, max_length=32)


auth_router = APIRouter(tags=["auth"])


@auth_router.post("/auth/request-code")
def auth_request_code(body: RequestCodeBody, request: Request) -> dict[str, str]:
    if auth_disabled():
        return {"status": "accepted"}
    if not auth_configured():
        raise HTTPException(
            status_code=503,
            detail="Admin authentication is not configured on the server.",
        )
    email = normalize_email(body.email)
    check_rate_limits(request, email)
    generic = {"status": "accepted", "message": AUTH_GENERIC_REQUEST}

    if not gates_pass(email):
        return generic
    if not _verify_company_password(body.company_password):
        check_rate_limits(request, email, pwd_fail=True)
        return generic

    code = _generate_otp()
    _otp_store(email, code)
    try:
        _send_otp_email(email, code)
    except Exception as exc:
        logger.exception("Failed to send admin OTP email: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Could not send sign-in email. Check SMTP settings or server logs.",
        ) from exc
    return generic


@auth_router.post("/auth/verify")
def auth_verify(body: VerifyBody, request: Request) -> dict[str, Any]:
    if auth_disabled():
        token = create_session_token("dev@auth-disabled.local")
        return {"access_token": token, "token_type": "bearer", "email": "dev@auth-disabled.local"}
    if not auth_configured():
        raise HTTPException(
            status_code=503,
            detail="Admin authentication is not configured on the server.",
        )
    email = normalize_email(body.email)
    check_rate_limits(request, email)

    if not gates_pass(email):
        raise HTTPException(status_code=401, detail=AUTH_GENERIC_VERIFY)
    if not _verify_company_password(body.company_password):
        check_rate_limits(request, email, pwd_fail=True)
        raise HTTPException(status_code=401, detail=AUTH_GENERIC_VERIFY)

    code = body.code.strip().replace(" ", "")
    if not _otp_consume(email, code):
        raise HTTPException(status_code=401, detail=AUTH_GENERIC_VERIFY)

    token = create_session_token(email)
    return {"access_token": token, "token_type": "bearer", "email": email}


@auth_router.get("/auth/me")
def auth_me(authorization: Optional[str] = Header(None)) -> dict[str, Any]:
    if auth_disabled():
        return {"email": "dev@auth-disabled.local", "auth_disabled": True}
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated.")
    email = verify_session_token(authorization[7:].strip())
    return {"email": email}
