#!/usr/bin/env python3
import random
import time

from flask import Flask, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__)

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["100 per minute"]
)

users = {
    "testuser": "testpass123"
}

tokens = {}

@app.route("/api/health", methods=["GET"])
@limiter.exempt
def health():
    return jsonify({
        "status": "ok",
        "model": "mock-model",
        "timestamp": time.time()
    })

@app.route("/api/auth/login", methods=["POST"])
@limiter.limit("10 per minute")
def login():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    if username in users and users[username] == password:
        token = f"mock_token_{username}_{int(time.time())}"
        tokens[token] = username
        return jsonify({
            "token": token,
            "username": username,
            "message": "Login successful"
        })

    return jsonify({"error": "Invalid credentials"}), 401

@app.route("/api/generate", methods=["POST"])
@limiter.limit("30 per minute")
def generate_section():
    auth_header = request.headers.get("Authorization")

    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Unauthorized"}), 401

    token = auth_header.replace("Bearer ", "")
    if token not in tokens:
        return jsonify({"error": "Invalid token"}), 401

    data = request.get_json()
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
@limiter.limit("10 per minute")
def generate_full():
    auth_header = request.headers.get("Authorization")

    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Unauthorized"}), 401

    token = auth_header.replace("Bearer ", "")
    if token not in tokens:
        return jsonify({"error": "Invalid token"}), 401

    data = request.get_json()
    prompt = data.get("prompt", "")

    time.sleep(random.uniform(0.02, 0.08))

    return jsonify({
        "paper_id": f"paper_{int(time.time())}",
        "title": f"Mock Paper: {prompt}",
        "sections": {
            "abstract": "Mock abstract content",
            "introduction": "Mock introduction content",
            "methodology": "Mock methodology content",
            "results": "Mock results content",
            "conclusion": "Mock conclusion content"
        },
        "tokens": random.randint(1000, 3000),
        "model": "mock-model"
    })

@app.route("/api/papers", methods=["GET"])
@limiter.limit("50 per minute")
def list_papers():
    auth_header = request.headers.get("Authorization")

    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Unauthorized"}), 401

    token = auth_header.replace("Bearer ", "")
    if token not in tokens:
        return jsonify({"error": "Invalid token"}), 401

    time.sleep(random.uniform(0.005, 0.02))

    papers = [
        {
            "id": f"paper_{i}",
            "title": f"Mock Paper {i}",
            "created_at": time.time() - (i * 3600)
        }
        for i in range(1, 11)
    ]

    return jsonify({
        "papers": papers,
        "total": len(papers)
    })

if __name__ == "__main__":
    print("="*70)
    print("Mock Server for Performance Testing")
    print("="*70)
    print("Starting on http://localhost:5000")
    print("Endpoints:")
    print("  GET  /api/health")
    print("  POST /api/auth/login")
    print("  POST /api/generate")
    print("  POST /api/generate-full")
    print("  GET  /api/papers")
    print("="*70)

    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
