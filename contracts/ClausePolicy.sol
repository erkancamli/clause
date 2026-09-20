// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title Clause policy token
/// @notice One token per policy, minted to the holder when the policy is
/// issued and burned when it is cancelled. It cannot be moved: cover belongs
/// to the person with an interest in what it insures, and a policy sold on to
/// someone else would be cover for nothing. ERC-721 for wallets and explorers
/// to show it; ERC-5192 so they know it is locked before they try.
///
/// The token id is the Keccak-256 of the policy id, so anyone holding a policy
/// number can find its token without asking. The URI points at the protocol's
/// own metadata for the policy, which carries the certificate image.
contract ClausePolicy {
    string public constant name = "Clause Policy";
    string public constant symbol = "CLAUSE";

    address public owner;
    address public issuer;
    string public baseURI;

    mapping(uint256 => address) private _owners;
    mapping(address => uint256) private _balances;
    mapping(uint256 => string) public policyIdOf;
    mapping(uint256 => bytes32) public termsOf;
    mapping(uint256 => bytes32) public holderHashOf;
    uint256 public minted;
    uint256 public burned;

    event Transfer(address indexed from, address indexed to, uint256 indexed tokenId);
    event Approval(address indexed owner, address indexed approved, uint256 indexed tokenId);
    event ApprovalForAll(address indexed owner, address indexed operator, bool approved);
    event Locked(uint256 tokenId);
    event Issued(uint256 indexed tokenId, string policyId, bytes32 holderHash, bytes32 termsHash);
    event Burned(uint256 indexed tokenId, string policyId, string reason);
    event IssuerChanged(address indexed issuer);

    error NonTransferable();
    error NotIssuer();
    error NotOwner();
    error AlreadyMinted();
    error NoSuchToken();
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

    // -- administration -----------------------------------------------------

    function setIssuer(address next) external onlyOwner {
        if (next == address(0)) revert ZeroAddress();
        issuer = next;
        emit IssuerChanged(next);
    }

    function setOwner(address next) external onlyOwner {
        if (next == address(0)) revert ZeroAddress();
        owner = next;
    }

    function setBaseURI(string calldata uri) external onlyOwner {
        baseURI = uri;
    }

    // -- issuing and burning ------------------------------------------------

    function tokenIdOf(string memory policyId) public pure returns (uint256) {
        return uint256(keccak256(bytes(policyId)));
    }

    function mint(address to, string calldata policyId, bytes32 holderHash, bytes32 termsHash)
        external onlyIssuer returns (uint256 tokenId)
    {
        if (to == address(0)) revert ZeroAddress();
        tokenId = tokenIdOf(policyId);
        if (_owners[tokenId] != address(0)) revert AlreadyMinted();
        _owners[tokenId] = to;
        _balances[to] += 1;
        policyIdOf[tokenId] = policyId;
        termsOf[tokenId] = termsHash;
        holderHashOf[tokenId] = holderHash;
        minted += 1;
        emit Transfer(address(0), to, tokenId);
        emit Locked(tokenId);
        emit Issued(tokenId, policyId, holderHash, termsHash);
    }

    function burn(string calldata policyId, string calldata reason) external onlyIssuer {
        uint256 tokenId = tokenIdOf(policyId);
        address from = _owners[tokenId];
        if (from == address(0)) revert NoSuchToken();
        delete _owners[tokenId];
        _balances[from] -= 1;
        burned += 1;
        emit Transfer(from, address(0), tokenId);
        emit Burned(tokenId, policyId, reason);
    }

    // -- ERC-721 reads ------------------------------------------------------

    function balanceOf(address account) external view returns (uint256) {
        if (account == address(0)) revert ZeroAddress();
        return _balances[account];
    }

    function ownerOf(uint256 tokenId) public view returns (address) {
        address holder = _owners[tokenId];
        if (holder == address(0)) revert NoSuchToken();
        return holder;
    }

    function exists(uint256 tokenId) external view returns (bool) {
        return _owners[tokenId] != address(0);
    }

    function tokenURI(uint256 tokenId) external view returns (string memory) {
        if (_owners[tokenId] == address(0)) revert NoSuchToken();
        return string(abi.encodePacked(baseURI, policyIdOf[tokenId], "/token"));
    }

    function getApproved(uint256) external pure returns (address) {
        return address(0);
    }

    function isApprovedForAll(address, address) external pure returns (bool) {
        return false;
    }

    // -- ERC-5192 -----------------------------------------------------------

    function locked(uint256 tokenId) external view returns (bool) {
        if (_owners[tokenId] == address(0)) revert NoSuchToken();
        return true;
    }

    // -- ERC-165 ------------------------------------------------------------

    function supportsInterface(bytes4 interfaceId) external pure returns (bool) {
        return interfaceId == 0x01ffc9a7   // ERC-165
            || interfaceId == 0x80ac58cd   // ERC-721
            || interfaceId == 0x5b5e139f   // ERC-721 metadata
            || interfaceId == 0xb45a3c0e;  // ERC-5192
    }

    // -- every way of moving a token, refused ---------------------------------

    function approve(address, uint256) external pure {
        revert NonTransferable();
    }

    function setApprovalForAll(address, bool) external pure {
        revert NonTransferable();
    }

    function transferFrom(address, address, uint256) external pure {
        revert NonTransferable();
    }

    function safeTransferFrom(address, address, uint256) external pure {
        revert NonTransferable();
    }

    function safeTransferFrom(address, address, uint256, bytes calldata) external pure {
        revert NonTransferable();
    }
}
