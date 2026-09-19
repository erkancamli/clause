"""Async JSON-RPC client for a Rialo node.

Method naming
-------------
Three method names are taken straight from Rialo's published client SDK, where
they appear on the typed RPC client:

    get_subscription(subscriber_pubkey, nonce)
    get_triggered_transactions(subscription_account, limit)
    get_workflow_lineage(signature)

The chain reading methods are not pinned down by the public SDK surface, and
Rialo's runtime carries SVM compatibility, so both the snake case and camel
case spellings are plausible. Rather than guess once and fail at the worst
moment, the client resolves each logical call against a list of candidate
method names, remembers the one the node accepts, and reuses it. A node that
answers to none of them produces a clear error naming every spelling tried.

That resolution is also why the bundled simulator is a genuine test: it speaks
the same wire protocol, so nothing in this file is simulator specific.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

import httpx

logger = logging.getLogger("clause.rpc")

# Error codes a node returns when a method simply does not exist. Anything else
# is a real failure and must not be swallowed by the fallback walk.
_METHOD_NOT_FOUND = {-32601, -32000}


class RpcError(RuntimeError):
    """A node returned an error, or no candidate method name was accepted."""

    def __init__(self, message: str, *, code: int | None = None, method: str = ""):
        self.code = code
        self.method = method
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class MethodGroup:
    """One logical call and the wire spellings that may implement it."""

    name: str
    candidates: tuple[str, ...]


METHODS: dict[str, MethodGroup] = {
    # Confirmed against the published Rialo client SDK.
    "get_subscription": MethodGroup(
        "get_subscription", ("get_subscription", "getSubscription")
    ),
    "get_triggered_transactions": MethodGroup(
        "get_triggered_transactions",
        ("get_triggered_transactions", "getTriggeredTransactions"),
    ),
    "get_workflow_lineage": MethodGroup(
        "get_workflow_lineage", ("get_workflow_lineage", "getWorkflowLineage")
    ),
    # Chain reads, resolved at runtime.
    "get_block_height": MethodGroup(
        "get_block_height",
        ("get_block_height", "getBlockHeight", "get_slot", "getSlot"),
    ),
    "get_block": MethodGroup("get_block", ("get_block", "getBlock")),
    "get_subscriptions": MethodGroup(
        "get_subscriptions",
        ("get_subscriptions", "getSubscriptions", "get_program_subscriptions"),
    ),
    "get_health": MethodGroup("get_health", ("get_health", "getHealth")),
}


class RialoClient:
    """Minimal async client covering the reactive execution surface."""

    def __init__(
        self,
        endpoint: str,
        *,
        timeout: float = 15.0,
        max_retries: int = 3,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._counter = itertools.count(1)
        self._resolved: dict[str, str] = {}
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout), headers={"content-type": "application/json"}
        )

    # -- lifecycle --------------------------------------------------------

    async def __aenter__(self) -> "RialoClient":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # -- transport --------------------------------------------------------

    async def _post(self, method: str, params: Any) -> Any:
        """Send one request, retrying only transport failures."""
        payload = {
            "jsonrpc": "2.0",
            "id": next(self._counter),
            "method": method,
            "params": params,
        }

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = await self._client.post(self.endpoint, json=payload)
                response.raise_for_status()
                body = response.json()
                break
            except (httpx.TransportError, httpx.HTTPStatusError) as error:
                last_error = error
                if attempt == self.max_retries:
                    raise RpcError(
                        f"{method} failed after {attempt} attempts against "
                        f"{self.endpoint}: {error}",
                        method=method,
                    ) from error
                # Back off gently; a node under load recovers faster if the
                # indexer does not hammer it.
                await asyncio.sleep(0.25 * attempt)
        else:  # pragma: no cover - loop always breaks or raises
            raise RpcError(str(last_error), method=method)

        if isinstance(body, dict) and "error" in body and body["error"] is not None:
            error = body["error"]
            code = error.get("code") if isinstance(error, dict) else None
            message = (
                error.get("message") if isinstance(error, dict) else str(error)
            )
            raise RpcError(f"{method}: {message}", code=code, method=method)

        if not isinstance(body, dict) or "result" not in body:
            raise RpcError(f"{method}: malformed response {body!r}", method=method)

        return body["result"]

    async def call(self, logical: str, params: Any) -> Any:
        """Invoke a logical method, resolving its wire spelling once."""
        group = METHODS.get(logical)
        if group is None:
            # Allow direct passthrough for anything not modelled here.
            return await self._post(logical, params)

        known = self._resolved.get(logical)
        if known:
            return await self._post(known, params)

        attempted: list[str] = []
        for candidate in group.candidates:
            attempted.append(candidate)
            try:
                result = await self._post(candidate, params)
            except RpcError as error:
                if error.code in _METHOD_NOT_FOUND:
                    logger.debug("node does not implement %s", candidate)
                    continue
                raise
            self._resolved[logical] = candidate
            if candidate != group.candidates[0]:
                logger.info("resolved %s to node method %s", logical, candidate)
            return result

        raise RpcError(
            f"node at {self.endpoint} implements none of: {', '.join(attempted)}",
            code=-32601,
            method=logical,
        )

    # -- reactive surface -------------------------------------------------

    async def get_health(self) -> Any:
        return await self.call("get_health", [])

    async def get_block_height(self) -> int:
        result = await self.call("get_block_height", [])
        if isinstance(result, dict):
            for key in ("height", "block_height", "slot", "value"):
                if key in result:
                    return int(result[key])
            raise RpcError(f"cannot read a height from {result!r}")
        return int(result)

    async def get_block(self, height: int) -> dict[str, Any]:
        """Fetch one block with its reactive activity attached."""
        result = await self.call("get_block", [height])
        if not isinstance(result, dict):
            raise RpcError(f"get_block({height}) returned {type(result).__name__}")
        return result

    async def get_blocks(
        self, heights: Iterable[int], *, concurrency: int = 16
    ) -> list[dict[str, Any]]:
        """Fetch several blocks concurrently, preserving the requested order.

        Concurrency is bounded so a catch up pass does not open more sockets
        than the connection pool holds, which turns into queueing that looks
        like node latency but is entirely self inflicted.
        """
        ordered = list(heights)
        if not ordered:
            return []

        limiter = asyncio.Semaphore(max(1, concurrency))

        async def fetch(height: int) -> dict[str, Any]:
            async with limiter:
                return await self.get_block(height)

        results = await asyncio.gather(
            *(fetch(height) for height in ordered),
            return_exceptions=True,
        )
        blocks: list[dict[str, Any]] = []
        missing = 0
        for item in results:
            if isinstance(item, BaseException):
                missing += 1
                continue
            blocks.append(item)
        if missing:
            # One line per batch, not per block: a node that has pruned a
            # stretch of history would otherwise flood the log.
            logger.debug(
                "%s of %s blocks in %s..%s were unavailable",
                missing,
                len(ordered),
                ordered[0],
                ordered[-1],
            )
        return blocks

    async def earliest_retained(self, *, floor: int, head: int) -> int:
        """Find the lowest block the node still serves, within a range.

        A node keeps a rolling window of history. Asking for blocks below it
        is not an error worth reporting, it is simply the edge of what exists,
        and an indexer that walks that empty stretch one batch at a time wastes
        its first seconds doing nothing. A binary search settles it in about a
        dozen requests.
        """
        floor = max(0, floor)
        if floor >= head:
            return head

        low, high = floor, head
        while low < high:
            middle = (low + high) // 2
            try:
                await self.get_block(middle)
            except RpcError:
                low = middle + 1
            else:
                high = middle
        return low

    async def get_subscription(self, subscriber: str, nonce: int) -> dict[str, Any]:
        """Read one subscription by its subscriber and nonce."""
        result = await self.call("get_subscription", [subscriber, nonce])
        if not isinstance(result, dict):
            raise RpcError("get_subscription returned a non object")
        return result

    async def get_subscriptions(
        self, *, status: str | None = None, limit: int = 500
    ) -> list[dict[str, Any]]:
        """List subscriptions known to the node.

        Nodes that do not expose a bulk listing raise, and the indexer falls
        back to reconstructing the set from the blocks it has already walked.
        """
        params: list[Any] = [{"status": status, "limit": limit}]
        result = await self.call("get_subscriptions", params)
        if isinstance(result, dict):
            result = result.get("subscriptions", [])
        if not isinstance(result, list):
            raise RpcError("get_subscriptions returned a non list")
        return result

    async def get_triggered_transactions(
        self, subscription_account: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Transactions the protocol enqueued for one subscription."""
        result = await self.call(
            "get_triggered_transactions", [subscription_account, limit]
        )
        if isinstance(result, dict):
            result = result.get("transactions", [])
        if not isinstance(result, list):
            raise RpcError("get_triggered_transactions returned a non list")
        return result

    async def get_workflow_lineage(self, signature: str) -> dict[str, Any]:
        """The DAG of transactions descending from one signature."""
        result = await self.call("get_workflow_lineage", [signature])
        if not isinstance(result, dict):
            raise RpcError("get_workflow_lineage returned a non object")
        if "nodes" not in result:
            raise RpcError("workflow lineage carries no nodes")
        return result

    # -- convenience ------------------------------------------------------

    @property
    def resolved_methods(self) -> dict[str, str]:
        """Which wire spelling each logical call settled on."""
        return dict(self._resolved)


async def probe(endpoint: str, timeout: float = 8.0) -> dict[str, Any]:
    """Check an endpoint and report what it supports.

    Used by the command line to tell an operator, before indexing starts,
    whether the node in front of them exposes the reactive methods at all.
    """
    report: dict[str, Any] = {"endpoint": endpoint, "reachable": False, "methods": {}}
    async with RialoClient(endpoint, timeout=timeout, max_retries=1) as client:
        try:
            report["height"] = await client.get_block_height()
            report["reachable"] = True
        except RpcError as error:
            report["error"] = str(error)
            return report

        checks: Sequence[tuple[str, tuple[Any, ...]]] = (
            ("get_block", (report["height"],)),
            ("get_subscriptions", ()),
        )
        for logical, args in checks:
            try:
                if logical == "get_block":
                    await client.get_block(*args)
                else:
                    await client.get_subscriptions()
                report["methods"][logical] = True
            except RpcError as error:
                report["methods"][logical] = f"unavailable: {error}"

        report["resolved"] = client.resolved_methods
    return report
