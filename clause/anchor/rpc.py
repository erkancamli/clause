"""The few JSON-RPC calls a signer needs, over httpx.

Nothing clever: one request per call, the node's error surfaced as an
exception with its message, and the handful of methods that sending a
transaction and reading a receipt take. A test hands in an httpx transport
that answers like a node; the service never notices.
"""

from __future__ import annotations

import itertools
from typing import Any

import httpx


class RpcError(RuntimeError):
    pass


def hex_int(value: int) -> str:
    return hex(value)


def int_hex(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    return int(str(value), 16)


class Rpc:
    def __init__(self, url: str, *, transport: httpx.BaseTransport | None = None, timeout: float = 20.0) -> None:
        self.url = url
        self.client = httpx.Client(transport=transport, timeout=timeout)
        self._ids = itertools.count(1)

    def close(self) -> None:
        self.client.close()

    def call(self, method: str, params: list[Any] | None = None) -> Any:
        body = {"jsonrpc": "2.0", "id": next(self._ids), "method": method, "params": params or []}
        try:
            reply = self.client.post(self.url, json=body)
        except httpx.HTTPError as error:
            raise RpcError(f"{method}: {error.__class__.__name__}: {error}") from error
        if reply.status_code != 200:
            raise RpcError(f"{method}: HTTP {reply.status_code}")
        try:
            payload = reply.json()
        except ValueError as error:
            raise RpcError(f"{method}: the node did not answer with JSON") from error
        if "error" in payload and payload["error"]:
            err = payload["error"]
            raise RpcError(f"{method}: {err.get('message', err) if isinstance(err, dict) else err}")
        return payload.get("result")

    # -- reads ----------------------------------------------------------------

    def chain_id(self) -> int:
        return int_hex(self.call("eth_chainId"))

    def nonce(self, address: str) -> int:
        return int_hex(self.call("eth_getTransactionCount", [address, "pending"]))

    def balance(self, address: str) -> int:
        return int_hex(self.call("eth_getBalance", [address, "latest"]))

    def fees(self) -> tuple[int, int]:
        """(max fee, max priority fee) in wei: twice the base fee plus the tip
        the node suggests, so a fee spike between quote and inclusion does not
        leave the transaction stuck."""
        block = self.call("eth_getBlockByNumber", ["latest", False]) or {}
        base = int_hex(block.get("baseFeePerGas")) or 1_000_000
        try:
            tip = int_hex(self.call("eth_maxPriorityFeePerGas"))
        except RpcError:
            tip = 1_000_000
        tip = max(tip, 1_000)
        return base * 2 + tip, tip

    def estimate_gas(self, *, sender: str, to: str | None, data: bytes, value: int = 0) -> int:
        params: dict[str, Any] = {"from": sender, "data": "0x" + data.hex(), "value": hex_int(value)}
        if to:
            params["to"] = to
        return int_hex(self.call("eth_estimateGas", [params]))

    def eth_call(self, *, to: str, data: bytes) -> bytes:
        out = self.call("eth_call", [{"to": to, "data": "0x" + data.hex()}, "latest"]) or "0x"
        return bytes.fromhex(out[2:])

    def receipt(self, tx_hash: str) -> dict[str, Any] | None:
        return self.call("eth_getTransactionReceipt", [tx_hash])

    # -- writes ---------------------------------------------------------------

    def send_raw(self, raw: bytes) -> str:
        return str(self.call("eth_sendRawTransaction", ["0x" + raw.hex()]))
