"""Knowing that a company is the company it says it is.

Anyone can type a name and a licence number into a form. What stops a
registration from being a claim is the work done on it before the company
is let in, and that work has three parts. Two are automatic and run the
moment a company registers; the third is a person's, and cannot be
anything else.

1. Identity, by LEI. Every insurer and reinsurer of any size holds a Legal
   Entity Identifier, and the Global LEI Foundation publishes the whole
   register with a free API. An LEI fixes the legal entity: its registered
   name, its status, and the country it is incorporated in. This module
   looks the LEI up and compares the name on the record with the name on the
   registration. A company without an LEI can still register, but the
   reviewer sees that nothing anchors the name.

2. Control of the company's domain. A licence number is public; anyone can
   copy it from the regulator's register. What a stranger cannot do is
   publish a file on the company's own website. So the registering address
   is asked to be placed at
       https://<domain>/.well-known/clause-insurer.txt
   and this module fetches it. A match shows that whoever registered can
   publish under the company's name on the internet, which is the same
   proof used for TLS certificates and domain ownership everywhere.

3. The licence itself, against the regulator's own register. No supervisor
   this protocol operates under offers an API a program could call for free
   (the UK's FCA comes closest); what every one of them offers is a public
   register a person can read. This module gives the reviewer the link to
   the right register, with the licence number where the register accepts a
   query, and the reviewer records what they saw. Documents the company
   uploads (its licence certificate, a register extract) are kept and shown
   to the reviewer as evidence, not taken as proof: a PDF can be edited, a
   register cannot.

Nothing here activates a company. The result of every check is written on
the registration for the reviewer, and a reviewer who activates a company
records which of these they confirmed.
"""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import re
import socket
import ssl
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

GLEIF = "https://api.gleif.org/api/v1/lei-records/"
USER_AGENT = "Clause/0.1 (+https://clause.insure)"
LEI_PATTERN = re.compile(r"^[A-Z0-9]{18}[0-9]{2}$")
DOMAIN_PATTERN = re.compile(r"^(?=.{4,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
WELL_KNOWN = "/.well-known/clause-insurer.txt"

EVIDENCE_KINDS = ("licence_certificate", "register_extract", "authorisation_letter", "other")
EVIDENCE_TYPES = {"application/pdf": ".pdf", "image/png": ".png", "image/jpeg": ".jpg"}
EVIDENCE_MAX_BYTES = 3_000_000
EVIDENCE_MAX_FILES = 4


# ---------------------------------------------------------------------------
# The public registers, by country: where a person checks a licence number.
# Only the supervisor's own register or the industry body's list, never a
# commercial directory. Where the register accepts a query in its address,
# the licence number or name is put in; otherwise the link opens the search.
# ---------------------------------------------------------------------------

REGISTERS: dict[str, list[tuple[str, str]]] = {
    "TR": [
        ("SEDDK, Sigortacılık ve Özel Emeklilik Düzenleme ve Denetleme Kurumu", "https://www.seddk.gov.tr/"),
        ("Türkiye Sigorta Birliği, üye şirketler", "https://www.tsb.org.tr/"),
    ],
    "GB": [
        ("FCA Financial Services Register", "https://register.fca.org.uk/s/search?q={reference}&type=Companies"),
        ("PRA authorised insurers", "https://www.bankofengland.co.uk/prudential-regulation/authorisations/which-firms-does-the-pra-regulate"),
    ],
    "DE": [("BaFin Unternehmensdatenbank", "https://portal.mvp.bafin.de/database/InstInfo/")],
    "AT": [("FMA Unternehmensdatenbank", "https://www.fma.gv.at/unternehmensdatenbank/")],
    "FR": [("ACPR, REGAFI", "https://www.regafi.fr/")],
    "ES": [("DGSFP, registros públicos", "https://dgsfp.mineco.gob.es/")],
    "IT": [("IVASS, albo delle imprese", "https://www.ivass.it/")],
    "NL": [("DNB, openbaar register", "https://www.dnb.nl/openbaar-register/")],
    "JP": [("金融庁, 免許・登録業者一覧", "https://www.fsa.go.jp/menkyo/menkyo.html")],
    "US": [("NAIC Consumer Information Source", "https://content.naic.org/consumer/cis")],
    "MX": [("CNSF, instituciones autorizadas", "https://www.gob.mx/cnsf")],
    "CH": [("FINMA, bewilligte Institute", "https://www.finma.ch/de/bewilligung/")],
}
EU_EEA = frozenset({
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT",
    "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE", "IS", "LI", "NO",
})


def register_links(country: str, *, reference: str = "", name: str = "", lei: str = "") -> list[dict[str, str]]:
    code = (country or "").upper()
    links = [{"name": n, "url": u.format(reference=urllib.parse.quote(reference), name=urllib.parse.quote(name))}
             for n, u in REGISTERS.get(code, [])]
    if code in EU_EEA:
        links.append({"name": "EIOPA register of insurance undertakings (all EU and EEA)",
                      "url": "https://register.eiopa.europa.eu/"})
    if lei:
        links.append({"name": "GLEIF, the LEI record", "url": f"https://search.gleif.org/#/record/{lei}"})
    if not links:
        links.append({"name": "IAIS members, to find the supervisor", "url": "https://www.iaisweb.org/about-the-iais/iais-members/"})
    return links


# ---------------------------------------------------------------------------
# Names
# ---------------------------------------------------------------------------

_NOISE = frozenset({
    "a", "as", "ag", "sa", "se", "nv", "bv", "ltd", "limited", "plc", "inc", "llc", "lp", "co",
    "company", "corp", "corporation", "gmbh", "spa", "srl", "sas", "kk", "the", "of", "and",
    "sigorta", "insurance", "assurance", "assurances", "versicherung", "seguros", "assicurazioni",
    "reinsurance", "reasurans", "re", "ltda", "anonim", "sirketi", "şirketi", "ti",
})


def normalise(name: str) -> list[str]:
    text = name.replace("ı", "i").replace("İ", "i")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    tokens = re.findall(r"[a-z0-9]+", text)
    return [t for t in tokens if t not in _NOISE] or tokens


def name_match(a: str, b: str) -> float:
    """How much of the registered name the record shares, 0 to 1."""
    x, y = set(normalise(a)), set(normalise(b))
    if not x or not y:
        return 0.0
    return len(x & y) / len(x | y)


# ---------------------------------------------------------------------------
# The checks
# ---------------------------------------------------------------------------

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A proof file that redirects elsewhere proves nothing about the domain
    it was asked from, and a redirect is how a fetch is pointed at an
    internal address; so none are followed."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _public_host(url: str) -> bool:
    host = urllib.parse.urlparse(url).hostname or ""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return bool(infos)


def _get(url: str, *, timeout: float = 10.0, limit: int = 200_000) -> tuple[int, bytes]:
    if not url.startswith("https://") or not _public_host(url):
        raise OSError("only public https hosts are fetched")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json, text/plain"})
    try:
        with _OPENER.open(request, timeout=timeout) as reply:  # noqa: S310
            return reply.status, reply.read(limit + 1)[:limit]
    except urllib.error.HTTPError as error:
        return error.code, b""


def check_lei(lei: str, name: str, *, fetch=None, country: str = "") -> dict[str, Any]:
    """Look the LEI up at GLEIF and compare the record with the registration.
    ``country`` is where the company says it is domiciled; a record in
    another country does not anchor it."""
    fetch = fetch or _get
    lei = (lei or "").strip().upper()
    if not lei:
        return {"given": False, "ok": False, "summary": "no LEI given; nothing anchors the legal name"}
    if not LEI_PATTERN.match(lei):
        return {"given": True, "ok": False, "lei": lei, "summary": "not a well formed LEI (20 characters, ISO 17442)"}
    try:
        status, body = fetch(GLEIF + lei)
    except (OSError, ValueError) as error:
        return {"given": True, "ok": False, "lei": lei, "unreachable": True,
                "summary": f"GLEIF could not be reached ({type(error).__name__}); try again"}
    if status == 404:
        return {"given": True, "ok": False, "lei": lei, "summary": "no such LEI at GLEIF"}
    if status != 200:
        return {"given": True, "ok": False, "lei": lei, "unreachable": True, "summary": f"GLEIF answered {status}; try again"}
    try:
        attrs = json.loads(body)["data"]["attributes"]
        entity, registration = attrs["entity"], attrs["registration"]
        legal_name = entity["legalName"]["name"]
        country_ = (entity.get("legalAddress") or {}).get("country", "")
        entity_status = entity.get("status", "")
        reg_status = registration.get("status", "")
    except (KeyError, TypeError, ValueError):
        return {"given": True, "ok": False, "lei": lei, "summary": "GLEIF answered something this build cannot read"}
    score = name_match(name, legal_name)
    same_country = not country or not (country_given := (country or "").upper()) or country_given == (country_ or "")
    ok = (entity_status == "ACTIVE" and reg_status in ("ISSUED", "PENDING_TRANSFER", "PENDING_ARCHIVAL")
          and score >= 0.5 and same_country)
    parts = [f"LEI names {legal_name} ({country_}), entity {entity_status.lower()}, registration {reg_status.lower()}",
             f"name match {score:.0%}"]
    if not same_country:
        parts.append(f"incorporated in {country_}, not {country_given} as registered")
    return {"given": True, "ok": ok, "lei": lei, "legal_name": legal_name, "country": country_,
            "entity_status": entity_status, "registration_status": reg_status, "name_match": round(score, 2),
            "summary": "; ".join(parts)}


def check_domain(domain: str, address: str | None, *, fetch=None) -> dict[str, Any]:
    """Fetch the proof file from the company's own domain."""
    fetch = fetch or _get
    domain = (domain or "").strip().lower().removeprefix("https://").removeprefix("http://").rstrip("/")
    if not domain:
        return {"given": False, "ok": False, "summary": "no domain given; control of the company's name online is unproven"}
    if not DOMAIN_PATTERN.match(domain):
        return {"given": True, "ok": False, "domain": domain, "summary": "not a domain name"}
    if not address:
        return {"given": True, "ok": False, "domain": domain, "summary": "the registration was not signed by an address, so there is nothing to prove"}
    url = f"https://{domain}{WELL_KNOWN}"
    try:
        status, body = fetch(url, limit=4_000)
    except (OSError, ValueError, ssl.SSLError) as error:
        return {"given": True, "ok": False, "domain": domain, "url": url, "unreachable": True,
                "summary": f"{url} could not be fetched ({type(error).__name__})"}
    if status != 200:
        return {"given": True, "ok": False, "domain": domain, "url": url,
                "summary": f"{url} answered {status}; the file is not there yet"}
    lines = {line.strip() for line in body.decode("utf-8", "replace").splitlines()}
    # Base58 is case sensitive; the older hex form is not.
    if address.startswith("0x"):
        lines = {line.lower() for line in lines}
        address = address.lower()
    found = address in lines or f"clause-insurer={address}" in lines
    return {"given": True, "ok": found, "domain": domain, "url": url,
            "summary": (f"{domain} publishes the registering address: whoever registered controls the domain"
                        if found else f"{url} exists but does not name the registering address")}


def expected_proof(address: str) -> str:
    return f"clause-insurer={address}"


def verify(*, name: str, lei: str, domain: str, address: str | None, country: str,
           reference: str, fetch=None, domicile: str = "") -> dict[str, Any]:
    """Every automatic check, and the links for the manual one."""
    lei_result = check_lei(lei, name, fetch=fetch, country=domicile)
    domain_result = check_domain(domain, address, fetch=fetch)
    return {
        "checked_at": time.time(),
        "lei": lei_result,
        "domain": domain_result,
        "registers": register_links(country, reference=reference, name=name, lei=lei_result.get("lei", "")),
        "licence": {"ok": None, "summary": "a person checks the licence number against the register linked here; nothing automatic can"},
    }


# ---------------------------------------------------------------------------
# Evidence: documents the company uploads, kept for the reviewer
# ---------------------------------------------------------------------------

def store_evidence(root: Path | None, carrier_id: str, files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Save uploaded documents and return their records.

    With no state directory (a test) the bytes are dropped and only the
    record is kept, which is enough for the reviewer to see what was claimed.
    """
    out: list[dict[str, Any]] = []
    for n, item in enumerate(files[:EVIDENCE_MAX_FILES]):
        kind = item.get("kind") if item.get("kind") in EVIDENCE_KINDS else "other"
        content_type = str(item.get("content_type", ""))
        ext = EVIDENCE_TYPES.get(content_type)
        if ext is None:
            raise ValueError("evidence is a PDF, PNG or JPEG")
        try:
            raw = base64.b64decode(str(item.get("data", "")), validate=True)
        except (ValueError, TypeError) as error:
            raise ValueError("evidence is sent base64 encoded") from error
        if not raw or len(raw) > EVIDENCE_MAX_BYTES:
            raise ValueError(f"each document is at most {EVIDENCE_MAX_BYTES // 1_000_000} MB")
        if ext == ".pdf" and not raw.startswith(b"%PDF"):
            raise ValueError("that is not a PDF")
        digest = hashlib.sha256(raw).hexdigest()
        stored = ""
        if root is not None:
            folder = root / "evidence" / carrier_id
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"{n}{ext}"
            path.write_bytes(raw)
            stored = str(path.relative_to(root))
        out.append({"n": n, "kind": kind, "filename": str(item.get("filename", ""))[:120],
                    "content_type": content_type, "bytes": len(raw), "sha256": digest,
                    "stored": stored, "uploaded_at": time.time()})
    return out
