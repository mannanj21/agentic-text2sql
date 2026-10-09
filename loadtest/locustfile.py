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
