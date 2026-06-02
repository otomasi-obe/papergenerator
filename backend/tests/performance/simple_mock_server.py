#!/usr/bin/env python3
import random
import time

from flask import Flask, jsonify, request

app = Flask(__name__)

users = {"testuser": "testpass123"}
tokens = {}

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "model": "mock-model", "timestamp": time.time()})

@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    username = data.get("username")
    password = data.get("password")

    if username in users and users[username] == password:
        token = f"mock_token_{username}_{int(time.time())}"
        tokens[token] = username
        return jsonify({"token": token, "username": username, "message": "Login successful"})

    return jsonify({"error": "Invalid credentials"}), 401

@app.route("/api/generate", methods=["POST"])
def generate_section():
    auth_header = request.headers.get("Authorization", "")

    if not auth_header.startswith("Bearer "):
        return jsonify({"error": "Unauthorized"}), 401

    token = auth_header.replace("Bearer ", "")
    if token not in tokens:
        return jsonify({"error": "Invalid token"}), 401

    data = request.get_json() or {}
    prompt = data.get("prompt", "")
    section = data.get("section", "abstract")

    time.sleep(random.uniform(0.01, 0.05))

    return jsonify({
        "section": section,
        "content": f"Mock generated content for: {prompt}",
        "tokens": random.randint(100, 500),
        "model": "mock-model"
    })

@app.route("/api/generate-full", methods=["POST"])
def generate_full():
    auth_header = request.headers.get("Authorization", "")

    if not auth_header.startswith("Bearer "):
        return jsonify({"error": "Unauthorized"}), 401

    token = auth_header.replace("Bearer ", "")
    if token not in tokens:
        return jsonify({"error": "Invalid token"}), 401

    data = request.get_json() or {}
    prompt = data.get("prompt", "")

    time.sleep(random.uniform(0.02, 0.08))

    return jsonify({
        "paper_id": f"paper_{int(time.time())}",
        "title": f"Mock Paper: {prompt}",
        "sections": {
            "abstract": "Mock abstract",
            "introduction": "Mock intro",
            "methodology": "Mock method",
            "results": "Mock results",
            "conclusion": "Mock conclusion"
        },
        "tokens": random.randint(1000, 3000),
        "model": "mock-model"
    })

@app.route("/api/papers", methods=["GET"])
def list_papers():
    auth_header = request.headers.get("Authorization", "")

    if not auth_header.startswith("Bearer "):
        return jsonify({"error": "Unauthorized"}), 401

    token = auth_header.replace("Bearer ", "")
    if token not in tokens:
        return jsonify({"error": "Invalid token"}), 401

    time.sleep(random.uniform(0.005, 0.02))

    papers = [{"id": f"paper_{i}", "title": f"Mock Paper {i}", "created_at": time.time() - (i * 3600)} for i in range(1, 11)]

    return jsonify({"papers": papers, "total": len(papers)})

if __name__ == "__main__":
    import sys
    print("="*70, file=sys.stderr, flush=True)
    print("Mock Server for Performance Testing", file=sys.stderr, flush=True)
    print("="*70, file=sys.stderr, flush=True)
    print("Starting on http://0.0.0.0:5000", file=sys.stderr, flush=True)
    print("="*70, file=sys.stderr, flush=True)
    sys.stderr.flush()

    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True, use_reloader=False)
