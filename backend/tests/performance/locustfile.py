import os

from locust import HttpUser, between, task


class PaperGeneratorUser(HttpUser):
    wait_time = between(1, 3)
    token = None

    def on_start(self):
        os.environ['MOCK_AI_RESPONSES'] = '1'
        response = self.client.post("/api/auth/login", json={
            "username": "testuser",
            "password": "testpass123"
        }, catch_response=True)

        if response.status_code == 200:
            try:
                data = response.json()
                self.token = data.get("token")
                response.success()
            except:
                response.failure("Failed to parse login response")
        else:
            response.failure(f"Login failed with status {response.status_code}")

    @task(10)
    def health_check(self):
        with self.client.get("/api/health", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Health check failed: {response.status_code}")

    @task(5)
    def generate_section(self):
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        with self.client.post("/api/generate",
            json={"prompt": "Write an abstract about AI", "section": "abstract"},
            headers=headers,
            catch_response=True
        ) as response:
            if response.status_code in [200, 429]:
                response.success()
            else:
                response.failure(f"Generate failed: {response.status_code}")

    @task(2)
    def generate_full(self):
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        with self.client.post("/api/generate-full",
            json={"prompt": "AI in healthcare"},
            headers=headers,
            catch_response=True
        ) as response:
            if response.status_code in [200, 429]:
                response.success()
            else:
                response.failure(f"Generate-full failed: {response.status_code}")

    @task(3)
    def list_papers(self):
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        with self.client.get("/api/papers",
            headers=headers,
            catch_response=True
        ) as response:
            if response.status_code in [200, 401]:
                response.success()
            else:
                response.failure(f"List papers failed: {response.status_code}")
