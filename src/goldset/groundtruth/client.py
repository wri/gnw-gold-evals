"""The analytics API client: a two-hop async job, not a plain GET.

    1. POST the payload            -> {"status", "data": {"link": ...}}
    2. status == "pending"         -> re-POST the IDENTICAL payload (there is no
                                      GET-status endpoint), honouring Retry-After
    3. status in ("success","saved") -> GET data.link
                                      -> {"data": {"result": {col: [values]},
                                                   "metadata": {...}}}

Mirrors ``AnalyticsHandler`` in project-zeno so the harness asks the same
question the agent does.

Two things worth knowing. The host is the **same** for staging and production —
only the ``X-environment`` header differs, so getting it wrong grades a staging
run against production data with no visible symptom. And the result resource id
is a UUID5 over the payload, so identical requests reuse one cached result; the
API exposes no cache headers and no data-version field, which is why the ledger
records a digest of the fetched values instead.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

BASE_URL = "https://analytics.globalnaturewatch.org"
DEFAULT_TIMEOUT = 120.0
MAX_POLLS = 10
DONE = ("success", "saved")
FAILED = ("failed", "error")


class AnalyticsError(Exception):
    """The analytics API could not answer. A run must abort loudly (AC #2)."""


@dataclass(frozen=True)
class AnalyticsResult:
    """One fetched response, plus what is needed to audit the verdict."""

    result: dict[str, list[Any]]
    # The server's own echo of what it computed — better evidence than our
    # reconstruction of the request. Carries provider/version for the boundaries.
    metadata: dict[str, Any]
    link: str

    @property
    def resource_id(self) -> str:
        return self.link.rstrip("/").split("/")[-1]


class AnalyticsClient:
    """Synchronous client. Prefetch runs before any trial, so it is not on the
    async trial path and does not need to share the runner's event loop."""

    def __init__(
        self,
        token: str,
        environment: str = "staging",
        base_url: str = BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        max_polls: int = MAX_POLLS,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.environment = environment
        self.max_polls = max_polls
        self._headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-environment": environment,
            "Authorization": f"Bearer {token}",
        }
        self._timeout = timeout
        self._transport = transport

    def fetch(self, endpoint: str, payload: dict[str, Any]) -> AnalyticsResult:
        url = self.base_url + endpoint
        with httpx.Client(timeout=self._timeout, follow_redirects=True,
                          transport=self._transport) as client:
            body = self._submit(client, url, payload)
            link = (body.get("data") or {}).get("link")
            if not link:
                raise AnalyticsError(f"{endpoint}: no data.link in {body!r}")
            response = client.get(link, headers=self._headers)
            response.raise_for_status()
            data = response.json().get("data") or {}

        result = data.get("result")
        if not result:
            # an empty result is a failed fetch, never an empty expectation.
            raise AnalyticsError(f"{endpoint}: empty result at {link}")
        return AnalyticsResult(result, data.get("metadata") or {}, link)

    def _submit(
        self, client: httpx.Client, url: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        for _ in range(self.max_polls):
            try:
                response = client.post(url, json=payload, headers=self._headers)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise AnalyticsError(f"{url}: {exc}") from exc
            body = response.json()
            status = str(body.get("status") or "").lower()
            if status in DONE:
                return body
            if status in FAILED:
                raise AnalyticsError(f"{url}: job {status}: {body.get('message')}")
            if status != "pending":
                raise AnalyticsError(f"{url}: unexpected status {status!r}")
            time.sleep(float(response.headers.get("Retry-After", 1)))
        raise AnalyticsError(f"{url}: still pending after {self.max_polls} polls")
