"""Quota-free platform load scenarios for the nginx deployment.

Set LOADTEST_EMAIL and LOADTEST_PASSWORD to an existing account before running.
The guarded query intentionally fails before an LLM call, exercising the
authenticated SSE/rate-limit path without provider usage.
"""

from __future__ import annotations

import os

from locust import HttpUser, between, task


class PlatformUser(HttpUser):
    wait_time = between(0.2, 1.0)

    def on_start(self) -> None:
        email = os.environ["LOADTEST_EMAIL"]
        password = os.environ["LOADTEST_PASSWORD"]
        with self.client.post(
            "/auth/login",
            json={"email": email, "password": password},
            name="login",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"login returned {response.status_code}")
        with self.client.post(
            "/connections",
            json={
                "name": f"load-{id(self)}",
                "host": os.getenv("LOADTEST_DB_HOST", "demo-ecommerce"),
                "port": 5432,
                "database": "ecommerce",
                "username": "readonly_demo",
                "password": "readonly_pass",
                "schemas": ["public"],
            },
            name="connection_create",
            catch_response=True,
        ) as response:
            if response.status_code != 201:
                response.failure(f"connection creation returned {response.status_code}")
                return
            connection_id = response.json()["id"]
        with self.client.post(
            "/conversations",
            json={"connection_id": connection_id, "title": "load"},
            name="conversation_create",
            catch_response=True,
        ) as response:
            if response.status_code != 201:
                response.failure(f"conversation creation returned {response.status_code}")
                return
            self.conversation_id = response.json()["id"]

    @task(8)
    def health(self) -> None:
        self.client.get("/health", name="health")

    @task(3)
    def connections(self) -> None:
        self.client.get("/connections", name="connections")

    @task(2)
    def history(self) -> None:
        self.client.get("/history", name="history")

    @task(1)
    def conversations(self) -> None:
        self.client.get("/conversations", name="conversations")

    @task(1)
    def query(self) -> None:
        if hasattr(self, "conversation_id"):
            self.client.post(
                f"/conversations/{self.conversation_id}/query",
                json={"question": "Return the synthetic platform test value"},
                name="query_sse",
            )
