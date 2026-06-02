import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(env_path)

API_URL = os.getenv("AIOTOMASI_API")
API_KEY = os.getenv("AIOTOMASI_APIKEY")
MODEL = os.getenv("MODELCHAT", "VIOLA-CHAT")

prompt_path = Path(__file__).resolve().parents[1] / "prompt" / "systemPrompt.txt"
SYSTEM_PROMPT = prompt_path.read_text(encoding="utf-8").strip() or "You are a helpful assistant."

messages_history = [{"role": "system", "content": SYSTEM_PROMPT}]


def parse_response(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for i in range(len(text), 0, -1):
        try:
            return json.loads(text[:i])
        except json.JSONDecodeError:
            continue
    raise ValueError(f"Cannot parse response: {text[:200]}")


def chat(user_message: str):
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    messages_history.append({"role": "user", "content": user_message})

    payload = {
        "model": MODEL,
        "messages": messages_history,
        "stream": False,
    }

    start = time.time()
    resp = requests.post(f"{API_URL}/chat/completions", headers=headers, json=payload, timeout=180)
    elapsed = time.time() - start

    resp.raise_for_status()
    data = parse_response(resp.text)

    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    input_tokens = usage.get("prompt_tokens", 0)
    output_tokens = usage.get("completion_tokens", 0)

    messages_history.append({"role": "assistant", "content": content})

    print(f"\n{'='*60}")
    print(f"Model: {MODEL}")
    print(f"{'='*60}")
    print(f"\n{content}\n")
    print(f"{'─'*60}")
    print(f"Input tokens : {input_tokens}")
    print(f"Output tokens: {output_tokens}")
    print(f"Total tokens : {input_tokens + output_tokens}")
    print(f"Time         : {elapsed:.2f}s")
    print(f"{'─'*60}")


if __name__ == "__main__":
    print("Paper Builder Chat (ketik 'q' untuk keluar)")
    print(f"Model: {MODEL}")
    print(f"API: {API_URL}")
    print("─" * 60)

    while True:
        try:
            user_input = input("\nYou: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                break
            chat(user_input)
        except KeyboardInterrupt:
            print("\nBye!")
            break
