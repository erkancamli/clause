// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title Clause book
/// @notice Two kinds of record about the protocol's book, written by its
/// signer. A settlement: which policy, what the outcome was and what it paid,
/// as an event anyone can read back. And, on a timer, the root of a Merkle
/// tree over every policy in the book, so that a policy's place in it on that
/// day can be proven from a handful of hashes. Roots are numbered by epoch and
/// only ever move forward.
contract ClauseBook {
    address public owner;
    address public issuer;

    uint64 public latestEpoch;
    bytes32 public latestRoot;
    uint64 public latestCount;
    mapping(uint64 => bytes32) public roots;
    mapping(uint64 => uint64) public counts;
    mapping(uint64 => uint64) public anchoredAt;
    uint256 public settlements;

    event RootAnchored(uint64 indexed epoch, bytes32 root, uint64 leafCount, bytes32 previousRoot);
    event Settled(bytes32 indexed policyHash, string policyId, uint8 status, uint256 payoutCents,
                  bytes32 readingHash, uint64 when);
    event IssuerChanged(address indexed issuer);

    error NotIssuer();
    error NotOwner();
    error EpochNotAfterLatest();
    error ZeroAddress();

    constructor() {
        owner = msg.sender;
        issuer = msg.sender;
    }

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    modifier onlyIssuer() {
        if (msg.sender != issuer) revert NotIssuer();
        _;
    }

    function setIssuer(address next) external onlyOwner {
        if (next == address(0)) revert ZeroAddress();
        issuer = next;
        emit IssuerChanged(next);
    }

    function setOwner(address next) external onlyOwner {
        if (next == address(0)) revert ZeroAddress();
        owner = next;
    }

    /// @notice The root of the book at this epoch. Epochs are the protocol's
    /// own numbering (its Unix time when the tree was built) and must rise.
    function anchor(bytes32 root, uint64 leafCount, uint64 epoch) external onlyIssuer {
        if (epoch <= latestEpoch) revert EpochNotAfterLatest();
        bytes32 previous = latestRoot;
        roots[epoch] = root;
        counts[epoch] = leafCount;
        anchoredAt[epoch] = uint64(block.timestamp);
        latestEpoch = epoch;
        latestRoot = root;
        latestCount = leafCount;
        emit RootAnchored(epoch, root, leafCount, previous);
    }

    /// @notice One settlement: the status the policy ended in (2 paid,
    /// 3 lapsed, 4 expired), what it paid in cents, and the hash of the
    /// reading it settled on.
    function settle(string calldata policyId, uint8 status, uint256 payoutCents, bytes32 readingHash, uint64 when)
        external onlyIssuer
    {
        settlements += 1;
        emit Settled(keccak256(bytes(policyId)), policyId, status, payoutCents, readingHash, when);
    }

    /// @notice Is this leaf under this root, given the sibling hashes? Pairs
    /// are hashed in sorted order, so the proof needs no left/right flags.
    function verify(bytes32 root, bytes32[] calldata proof, bytes32 leaf) external pure returns (bool) {
        bytes32 node = leaf;
        for (uint256 i = 0; i < proof.length; i++) {
            bytes32 sibling = proof[i];
            node = node <= sibling ? keccak256(abi.encodePacked(node, sibling))
                                   : keccak256(abi.encodePacked(sibling, node));
        }
        return node == root;
    }

    /// @notice The same check against the latest root the contract holds.
    function verifyLatest(bytes32[] calldata proof, bytes32 leaf) external view returns (bool) {
        bytes32 node = leaf;
        for (uint256 i = 0; i < proof.length; i++) {
            bytes32 sibling = proof[i];
            node = node <= sibling ? keccak256(abi.encodePacked(node, sibling))
                                   : keccak256(abi.encodePacked(sibling, node));
        }
        return node == latestRoot;
    }
}
