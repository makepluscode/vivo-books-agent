"""Liner API 얇은 래퍼 + 호출 추적(trace).

모든 호출은 TRACE 에 남아 보고서의 '처리 과정' 화면과 비용 추정에 쓰여요.
"""
import json
import os
import threading
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
BASE = "https://platform.liner.com/api/v1"
ROUTER_MODEL = os.environ.get("DRIFT_ROUTER_MODEL", "liner-claude-router")

TRACE = []
ON_LOG = None  # 웹 데모: 호출 기록을 실시간 전달하는 콜백
_lock = threading.Lock()


def _key():
    key = os.environ.get("LINER_API_KEY")
    if not key:
        raise SystemExit("LINER_API_KEY 가 없어요. .env 에 설정하세요 (.env.example 참고).")
    return key


def _log(entry):
    with _lock:
        TRACE.append(entry)
    if ON_LOG:
        try:
            ON_LOG(entry)
        except Exception:
            pass


def _post(path, body, timeout, retries=2):
    """429/5xx 는 제한적으로 재시도해요."""
    for attempt in range(retries + 1):
        r = requests.post(f"{BASE}{path}", headers={"x-api-key": _key()}, json=body, timeout=timeout)
        if (r.status_code == 429 or r.status_code >= 500) and attempt < retries:
            time.sleep(float(r.headers.get("Retry-After", 2 * (attempt + 1))))
            continue
        r.raise_for_status()
        return r.json(), attempt


def search(query, max_results=5, item_id=None):
    t = time.perf_counter()
    js, retries = _post("/tools/search/web",
                        {"query": query, "max_results": max_results, "include_knowledge": False}, 60)
    results = [{"title": x.get("title"), "url": x.get("url"), "description": x.get("description"),
                "date": x.get("date")} for x in js.get("results", [])]
    _log({"api": "search", "item": item_id, "query": query, "seconds": round(time.perf_counter() - t, 2),
          "retries": retries, "n": len(results), "urls": [x["url"] for x in results],
          "cost_usd": 0.001})
    return results


def search_agent(question, item_id=None, lang="ko"):
    t = time.perf_counter()
    js, retries = _post("/agents/search",
                        {"messages": [{"role": "user", "content": question}], "lang": lang, "stream": False}, 180)
    refs = [{"title": x.get("title"), "url": x.get("url"), "description": x.get("description")}
            for x in (js.get("references") or [])]
    _log({"api": "search_agent", "item": item_id, "question": question,
          "seconds": round(time.perf_counter() - t, 2), "retries": retries,
          "n": len(refs), "answer_chars": len(js.get("answer") or ""), "cost_usd": 0.02})
    return js.get("answer") or "", refs


_client = None


def router_json(system, user, item_id=None, step="router"):
    """라우터 호출 → JSON 파싱. 실제 응답 모델·토큰을 기록해요."""
    global _client
    _client = _client or OpenAI(base_url=BASE, api_key=_key())
    t = time.perf_counter()
    resp = _client.chat.completions.create(
        model=ROUTER_MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    text = resp.choices[0].message.content or ""
    u = resp.usage
    _log({"api": step, "item": item_id, "router": ROUTER_MODEL, "served_model": resp.model,
          "seconds": round(time.perf_counter() - t, 2),
          "prompt_tokens": u.prompt_tokens if u else None,
          "completion_tokens": u.completion_tokens if u else None})
    return parse_json(text), text


# Router 실제 응답 모델별 단가(USD / 1M 토큰, 입력·출력). 2026-11-22 가격 문서 기준.
PRICES = {"claude-haiku-5.5": (0.1, 0.5), "claude-sonnet-5.5": (2, 10), "claude-opus-5.5": (4, 20),
          "claude-fable-5.1": (10, 50), "gpt-6-luna": (0.1, 0.5), "gpt-6.1-terra": (1, 5),
          "gpt-6.1-sol": (2, 10), "gpt-6-astra": (10, 50), "gemini-3.5-flash-lite": (0.3, 2.5),
          "gemini-3.8-flash": (0.75, 3.75), "gemini-4-argon": (2, 10)}


def router_chat(messages, tools, item_id=None, step="agent-router"):
    """도구 호출(tool calling) 한 턴. 어시스턴트 메시지를 OpenAI 형식 dict로 돌려줘요."""
    return router_chat_ex(messages, tools, item_id, step)[0]


def router_chat_ex(messages, tools, item_id=None, step="agent-router"):
    """router_chat + 실제 응답 모델 이름. (병렬 실행에서도 TRACE 순서에 기대지 않아요.)"""
    global _client
    _client = _client or OpenAI(base_url=BASE, api_key=_key())
    t = time.perf_counter()
    resp = _client.chat.completions.create(model=ROUTER_MODEL, messages=messages, tools=tools)
    m = resp.choices[0].message
    message = {"role": "assistant", "content": m.content or ""}
    if m.tool_calls:
        message["tool_calls"] = [{"id": c.id, "type": "function",
                                  "function": {"name": c.function.name, "arguments": c.function.arguments}}
                                 for c in m.tool_calls]
    u = resp.usage
    price = PRICES.get(resp.model)
    cost = (round((u.prompt_tokens * price[0] + u.completion_tokens * price[1]) / 1e6, 5)
            if u and price else None)
    _log({"api": step, "item": item_id, "router": ROUTER_MODEL, "served_model": resp.model,
          "seconds": round(time.perf_counter() - t, 2),
          "prompt_tokens": u.prompt_tokens if u else None,
          "completion_tokens": u.completion_tokens if u else None, "cost_usd": cost})
    return message, resp.model


def parse_json(text):
    s = text.strip()
    start = min([i for i in (s.find("{"), s.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise ValueError(f"JSON 없음: {text[:200]}")
    end = max(s.rfind("}"), s.rfind("]"))
    return json.loads(s[start:end + 1])
