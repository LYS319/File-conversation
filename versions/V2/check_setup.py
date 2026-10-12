"""Smoke-test .env credentials: Langfuse server + Anthropic + OpenAI keys."""
import base64
import os
import urllib.error
import urllib.request
from pathlib import Path


def load_env(path=Path(__file__).resolve().parents[2] / ".env"):      # .env 는 비밀이라 V1·V2 에 복사하지 않고 프로젝트 루트에 둔다
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"'))


def get(url, headers):
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except urllib.error.URLError as e:
        return None, str(e.reason)


def check_langfuse():
    host = os.environ["LANGFUSE_BASE_URL"]
    status, _ = get(f"{host}/api/public/health", {})
    print(f"[langfuse] 서버 응답       : {status}")
    cred = base64.b64encode(
        f"{os.environ['LANGFUSE_PUBLIC_KEY']}:{os.environ['LANGFUSE_SECRET_KEY']}".encode()
    ).decode()
    status, body = get(f"{host}/api/public/projects", {"Authorization": f"Basic {cred}"})
    print(f"[langfuse] 키 인증(200=성공) : {status} {body[:150]}")


def check_anthropic():
    status, body = get(
        "https://api.anthropic.com/v1/models",
        {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"},
    )
    print(f"[anthropic] 키 인증(200=성공): {status} {body[:150]}")


def check_openai():
    status, body = get(
        "https://api.openai.com/v1/models",
        {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
    )
    print(f"[openai] 키 인증(200=성공)   : {status} {body[:150]}")


if __name__ == "__main__":
    load_env()
    check_langfuse()
    check_anthropic()
    check_openai()
