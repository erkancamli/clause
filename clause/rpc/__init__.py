"""JSON-RPC access to a Rialo node."""

from .client import RialoClient, RpcError

__all__ = ["RialoClient", "RpcError"]
