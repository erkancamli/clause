"""Who owns the two contracts, and whether anybody can tell.

The contracts' constructors set owner and issuer to the deploying key, and
deploy() left both there. Its docstring said to "hand the owner role to a
safer key afterwards with setOwner", which is a step with no record of anybody
taking it, and nothing ever read the owner back, so a deployment where the hot
key owns everything looked exactly like one where it does not.

The two roles are not the same size. Issuer mints, burns and settles, and it
is hot by nature: it lives in the environment of a public web process. Owner
can change the issuer, and these contracts have no timelock, no guardian and
nothing upgradeable, so an owner that is taken is taken for good.

So the handover happens in the same run as the deployment, and the owner is
read off the chain afterwards and said on the operator's page.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from clause.anchor import Anchor, AnchorConfig
from clause.anchor.service import deploy
from clause.anchor.signing import (address_of_key, checksum, encode_call,
                                   private_key_of)

#: The published EIP-155 example key. Public, and used here only to derive an
#: address and to sign transactions that reach a fake node.
A_KEY = "0x4646464646464646464646464646464646464646464646464646464646464646"
SENDER = address_of_key(private_key_of(A_KEY))
SAFE = "0x" + "11" * 20
POLICY = "0x" + "aa" * 20
BOOK = "0x" + "bb" * 20


class FakeNode:
    """A node that records what it was sent and answers an owner() call."""

    def __init__(self, owner: str = SENDER) -> None:
        self.sent: list[bytes] = []
        self.calls: list[dict] = []
        self.owner = owner

    def chain_id(self) -> int:
        return 84532

    def nonce(self, _address: str) -> int:
        return 7

    def fees(self) -> tuple[int, int]:
        return 2_000_000_000, 1_000_000_000

    def estimate_gas(self, **_kw) -> int:
        return 1_000_000

    def send_raw(self, raw: bytes) -> str:
        self.sent.append(raw)
        return "0x" + "cd" * 32

    def eth_call(self, *, to: str, data: bytes) -> bytes:
        self.calls.append({"to": to, "data": data.hex()})
        return bytes(12) + bytes.fromhex(self.owner[2:])

    def balance(self, _address: str) -> int:
        return 10 ** 18


def anchor_with(node, **over) -> Anchor:
    config = AnchorConfig(chain_id=84532, rpc_url="http://node",
                          private_key=A_KEY, policy_contract=POLICY,
                          book_contract=BOOK, **over)
    return Anchor(config, pool=SimpleNamespace(policies={}), rpc=node)


# -- the handover ----------------------------------------------------------

def test_deploying_with_an_owner_hands_it_over() -> None:
    node = FakeNode()
    said: list[str] = []
    out = deploy(node, A_KEY, chain_id=84532, owner=SAFE, log=said.append)
    assert set(out) == {"ClausePolicy", "ClauseBook"}
    # Two deployments and two setOwner calls.
    assert len(node.sent) == 4, node.sent
    handed = [line for line in said if "setOwner" in line]
    assert len(handed) == 2, said
    assert all(checksum(SAFE) in line for line in handed)
    assert any("keeps the issuer role" in line for line in said)


def test_deploying_without_one_says_so_loudly() -> None:
    node = FakeNode()
    said: list[str] = []
    deploy(node, A_KEY, chain_id=84532, log=said.append)
    assert len(node.sent) == 2, "it should deploy and hand nothing over"
    warning = [line for line in said if line.startswith("WARNING")]
    assert len(warning) == 1, said
    assert "owns both contracts" in warning[0]
    assert "taken for good" in warning[0]


def test_handing_it_to_the_deploying_key_is_refused() -> None:
    """Which is the one owner value that changes nothing at all."""
    node = FakeNode()
    with pytest.raises(RuntimeError, match="the owner given is the deploying key"):
        deploy(node, A_KEY, chain_id=84532, owner=SENDER, log=lambda _m: None)


def test_the_base_uri_and_the_handover_do_not_collide() -> None:
    """Both are calls after the deployments, so the nonces have to advance."""
    node = FakeNode()
    deploy(node, A_KEY, chain_id=84532, base_uri="https://example/api/",
           owner=SAFE, log=lambda _m: None)
    assert len(node.sent) == 5, "two deployments, a base URI and two handovers"
    assert len(set(node.sent)) == 5, (
        "a repeated raw transaction means a repeated nonce, and the second "
        "would be rejected by a real node")


# -- and whether anybody can tell afterwards -------------------------------

def test_the_owner_is_read_off_the_chain() -> None:
    node = FakeNode(owner=SAFE)
    anchor = anchor_with(node)
    assert anchor.owner_of(POLICY) == checksum(SAFE)
    # Asked with owner(), which is the first caller Rpc.eth_call has ever had.
    assert node.calls and node.calls[0]["to"] == POLICY
    assert node.calls[0]["data"] == encode_call("owner()", []).hex()


def test_a_hot_key_owning_the_contracts_is_said() -> None:
    node = FakeNode(owner=SENDER)
    said = anchor_with(node, owner_address=SAFE).ownership()
    assert said["signer_is_owner"] is True
    assert said["contracts"]["policy"] == checksum(SENDER)
    assert said["contracts"]["book"] == checksum(SENDER)
    assert said["wanted"] == checksum(SAFE)
    assert "taken for good" in said["why_it_matters"]


def test_a_handed_over_deployment_says_nothing_alarming() -> None:
    node = FakeNode(owner=SAFE)
    said = anchor_with(node, owner_address=SAFE).ownership()
    assert said["signer_is_owner"] is False
    assert "why_it_matters" not in said


def test_one_contract_handed_over_and_one_not_is_still_said() -> None:
    """The failure mode of doing it by hand, one call at a time."""

    class Half(FakeNode):
        def eth_call(self, *, to: str, data: bytes) -> bytes:
            self.owner = SAFE if to == POLICY else SENDER
            return super().eth_call(to=to, data=data)

    said = anchor_with(Half()).ownership()
    assert said["contracts"]["policy"] == checksum(SAFE)
    assert said["contracts"]["book"] == checksum(SENDER)
    assert said["signer_is_owner"] is True


def test_the_operators_page_carries_it() -> None:
    status = anchor_with(FakeNode(owner=SENDER)).status()
    assert status["ownership"]["signer_is_owner"] is True


def test_a_node_that_cannot_be_asked_does_not_claim_an_owner() -> None:
    class Mute(FakeNode):
        def eth_call(self, **_kw):
            raise RuntimeError("no node")

    said = anchor_with(Mute()).ownership()
    assert said["contracts"] == {"policy": None, "book": None}
    assert said["signer_is_owner"] is False


def test_a_deployment_with_no_contracts_asks_nothing() -> None:
    node = FakeNode()
    config = AnchorConfig(chain_id=84532, rpc_url="http://node", private_key=A_KEY)
    anchor = Anchor(config, pool=SimpleNamespace(policies={}), rpc=node)
    said = anchor.ownership()
    assert said["contracts"] == {"policy": None, "book": None}
    assert not node.calls


def test_the_configuration_reads_the_owner_from_the_environment(monkeypatch) -> None:
    monkeypatch.setenv("CLAUSE_ANCHOR_OWNER", SAFE)
    assert AnchorConfig.from_env().owner_address == SAFE
    monkeypatch.delenv("CLAUSE_ANCHOR_OWNER")
    assert AnchorConfig.from_env().owner_address == ""


def test_the_deploy_script_offers_it() -> None:
    """A flag nobody can find is a step nobody takes, which is how this
    started."""
    from pathlib import Path

    script = (Path(__file__).resolve().parent.parent / "scripts"
              / "deploy_anchor.py").read_text(encoding="utf-8")
    assert '"--owner"' in script
    assert "CLAUSE_ANCHOR_OWNER" in script
    assert "owner=args.owner" in script
    # And it says what to write down, because nothing in the repository
    # records a deployed address.
    assert "write the two addresses down" in script


def test_the_deployed_addresses_are_written_down_correctly() -> None:
    """A transcribed address is the one thing here nothing else can check.

    The audit's finding was that nothing in the repository records an
    address, so the operator's page cannot tell a real deployment from a
    blank one. docs/anchor.md records them now, and a typo in one is
    invisible to every other test, so the checksum is read here.
    """
    import re
    from pathlib import Path

    doc = (Path(__file__).resolve().parent.parent / "docs" / "anchor.md"
           ).read_text(encoding="utf-8")
    where = doc.split("## What is deployed", 1)
    assert len(where) == 2, "the deployment is not recorded"
    found = set(re.findall(r"0x[0-9a-fA-F]{40}", where[1]))
    assert len(found) == 3, f"policy, book and signer; found {sorted(found)}"
    for address in found:
        assert checksum(address) == address, (
            f"{address} is not its own EIP-55 checksum, so a character is wrong")


# -- and the pair that is already deployed ---------------------------------

def run_handover(**env) -> tuple[int, str, str]:
    """The script, in a process of its own, as an operator would run it."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    args = []
    for flag in ("owner", "policy", "book", "rpc"):
        if flag in env:
            args += [f"--{flag}", env.pop(flag)]
    if env.pop("dry_run", False):
        args.append("--dry-run")
    where = dict(os.environ)
    for name in ("CLAUSE_ANCHOR_KEY", "CLAUSE_ANCHOR_OWNER", "CLAUSE_ANCHOR_POLICY",
                 "CLAUSE_ANCHOR_BOOK", "CLAUSE_ANCHOR_RPC"):
        where.pop(name, None)
    where.update(env)
    done = subprocess.run([sys.executable, str(root / "scripts" / "hand_over_owner.py"), *args],
                          capture_output=True, text=True, timeout=60, cwd=root, env=where)
    return done.returncode, done.stdout, done.stderr


def test_the_handover_needs_the_key_from_the_environment() -> None:
    code, _out, said = run_handover(owner=SAFE, policy=POLICY, book=BOOK)
    assert code == 2
    assert "CLAUSE_ANCHOR_KEY" in said


def test_the_handover_needs_somewhere_to_hand_it_to() -> None:
    code, _out, said = run_handover(CLAUSE_ANCHOR_KEY=A_KEY, policy=POLICY, book=BOOK)
    assert code == 2
    assert "offline" in said


def test_handing_it_to_the_signing_key_is_refused_there_too() -> None:
    code, _out, said = run_handover(CLAUSE_ANCHOR_KEY=A_KEY, owner=SENDER,
                                    policy=POLICY, book=BOOK)
    assert code == 2
    assert "the signing key itself" in said


def test_it_says_where_the_addresses_are_written_down() -> None:
    """Because nothing in the code holds one."""
    code, _out, said = run_handover(CLAUSE_ANCHOR_KEY=A_KEY, owner=SAFE)
    assert code == 2
    assert "docs/anchor.md" in said


def test_the_calldata_is_the_same_call_the_deployment_makes() -> None:
    """One encoding of setOwner, so the two paths cannot drift apart."""
    from pathlib import Path

    script = (Path(__file__).resolve().parent.parent / "scripts"
              / "hand_over_owner.py").read_text(encoding="utf-8")
    assert 'encode_call("setOwner(address)", [wanted])' in script
    assert 'encode_call("owner()", [])' in script, "it reads the owner before it writes one"
    assert "--dry-run" in script
