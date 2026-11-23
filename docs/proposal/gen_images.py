"""기획서 그림을 BizRouter 이미지 API로 다시 그려요(글자 없는 일러스트, 같은 화풍).

    BIZROUTER_API_KEY=... python docs/proposal/gen_images.py [이름 ...]

- 모델: google/gemini-3-pro-image (2K, 16:9). 화풍 참조: 모두의창업 신청서 그림(img/style-ref.png).
- 키는 환경 변수에서만 읽고 저장·출력하지 않아요. 결과는 img/gen/<이름>.png, 요청 기록은 img/gen/log.json.
"""
import base64
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "img" / "gen"
MODEL = "google/gemini-3-pro-image"
STYLE_REF = HERE / "img" / "style-ref.png"

STYLE = ("Style: match the reference image exactly — clean hand-drawn line illustration in deep navy ink (#23283C) "
         "with soft cornflower blue (#7FA1F0) fills and pale blue (#E4EBFC) accents on a pure white background, "
         "the same friendly white alpaca mascot with round glasses, generous white space, flat, no gradients, no photo realism. "
         "ABSOLUTELY NO TEXT: no letters, words, numbers, captions, logos or labels anywhere in the image. "
         "Use icons and symbols instead of words. Composition 16:9, centered, readable when printed small.")

PROMPTS = {
    "problem": "Story in one wide scene, left to right: (1) the alpaca author proudly holding a freshly published technical book "
               "with small confetti; (2) a thin timeline line with three round icons — a pen on paper, a gear on a document, a party popper; "
               "(3) the same alpaca now worried at a laptop showing a red error symbol, scratching its head, with a scribble cloud above; "
               "(4) two reader avatars (a young man with a laptop, a woman with a phone) each with an empty speech bubble containing only a red exclamation mark, "
               "plus small icons of an envelope with alert dot, a chat bubble and a coin with a return arrow.",
    "stakeholders": "Three equal panels side by side separated by white space, each a small vignette in a rounded frame: "
                    "left — a reader at a desk frustrated at a laptop with a red error symbol and coins slipping away with a clock; "
                    "middle — the alpaca author overwhelmed by many incoming complaint bubbles with red exclamation marks and a calendar with many pages flipping; "
                    "right — a publisher standing in a warehouse next to tall stacks of unsold books and a small recycling bin.",
    "solution": "The fix in one wide scene: on the left a technical book with a small red error mark on one page; in the center a friendly assistant "
                "drawn as a large cornflower-blue magnifying glass with a tiny spark, searching through a neat stack of official documentation pages "
                "(blank lines only), then a small test tube and a play button with a green check mark showing the example was run; "
                "on the right the alpaca author at a desk reviewing a neat envelope/document with a check mark and an approve stamp, "
                "and the same book now glowing softly with a circular refresh arrow. Dotted arrows connect the steps left to right.",
    "vivo": "A living book ecosystem: in the center an open book softly glowing with a circular refresh arrow around it; "
            "around it three circular vignettes connected by gentle curved arrows forming a loop: "
            "a happy reader holding a tablet with a refresh symbol, the happy alpaca author uploading an update to a small cloud with an up arrow, "
            "and a happy publisher next to a small printer printing one fresh book on demand. Calm, optimistic mood.",
}


def data_url(path):
    return "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode()


def generate(name):
    key = os.environ["BIZROUTER_API_KEY"]
    body = {"model": MODEL, "aspect_ratio": "16:9", "image_size": "2K",
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": data_url(STYLE_REF)}},
                {"type": "text", "text": PROMPTS[name] + "\n\n" + STYLE}]}]}
    req = urllib.request.Request("https://api.bizrouter.ai/v1/chat/completions", method="POST",
                                 data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    t = time.time()
    with urllib.request.urlopen(req, timeout=300) as r:
        resp = json.loads(r.read())
    msg = resp["choices"][0]["message"]
    parts = (msg.get("content") if isinstance(msg.get("content"), list) else []) + (msg.get("images") or [])
    for part in parts:
        url = (part.get("image_url") or {}).get("url", "") if isinstance(part, dict) else ""
        if url.startswith("data:image/"):
            head, payload = url.split(";base64,", 1)
            ext = {"data:image/png": ".png", "data:image/jpeg": ".jpg", "data:image/webp": ".webp"}[head]
            path = OUT / f"{name}{ext}"
            path.write_bytes(base64.b64decode(payload))
            return {"name": name, "file": path.name, "seconds": round(time.time() - t, 1),
                    "usage": resp.get("usage", {}), "model": resp.get("model", MODEL)}
    raise RuntimeError(f"{name}: 이미지가 응답에 없어요")


def main():
    names = sys.argv[1:] or list(PROMPTS)
    OUT.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(4) as ex:
        results = list(ex.map(lambda n: _safe(n), names))
    log = OUT / "log.json"
    history = json.loads(log.read_text()) if log.exists() else []
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    history += [{"at": stamp, "prompt": PROMPTS[r["name"]], **r} for r in results]
    log.write_text(json.dumps(history, ensure_ascii=False, indent=1))
    for r in results:
        print(r["name"], r.get("file") or r.get("error"), r.get("seconds"), r.get("usage", {}).get("cost") if isinstance(r.get("usage"), dict) else "")


def _safe(name):
    try:
        return generate(name)
    except Exception as exc:  # 한 장 실패가 나머지를 막지 않게
        return {"name": name, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}


if __name__ == "__main__":
    main()
