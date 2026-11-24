import ipaddress
import socket
from urllib.parse import urlparse, urlunparse


BLOCKED_HOST_SUFFIXES = (".local", ".internal", ".localhost", ".arpa")


class URLValidationError(ValueError):
    """Raised when a target URL is malformed or resolves to a non-public address."""


def _is_disallowed_ip(raw_ip: str) -> bool:
    addr = ipaddress.ip_address(raw_ip)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def validate_public_url(raw_url: str, resolve_dns: bool = True) -> str:
    """Normalize HTTP(S) URL and reject private/internal targets (SSRF guard)."""
    candidate = raw_url.strip()
    parsed = urlparse(candidate)

    if parsed.scheme.lower() not in ("http", "https"):
        raise URLValidationError("Only http:// and https:// URLs are supported.")

    if not parsed.hostname:
        raise URLValidationError("URL must include a valid hostname.")

    if parsed.username or parsed.password:
        raise URLValidationError("Credentials inside URLs are not allowed.")

    host = parsed.hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith(BLOCKED_HOST_SUFFIXES):
        raise URLValidationError("Local and internal hostnames are not permitted.")

    if parsed.port and parsed.port not in (80, 443, 8080, 8443):
        raise URLValidationError(f"Port {parsed.port} is not allowed.")

    try:
        ipaddress.ip_address(host)
        is_literal_ip = True
    except ValueError:
        is_literal_ip = False

    if is_literal_ip:
        if _is_disallowed_ip(host):
            raise URLValidationError("Access to private or reserved IP addresses is blocked.")
    else:
        if "." not in host:
            raise URLValidationError("Hostname must be a fully qualified public domain.")
        if resolve_dns:
            try:
                records = socket.getaddrinfo(host, parsed.port or 443, proto=socket.IPPROTO_TCP)
            except socket.gaierror as exc:
                raise URLValidationError(f"Could not resolve domain '{host}'.") from exc

            if not records:
                raise URLValidationError(f"No DNS records found for '{host}'.")

            for record in records:
                resolved_ip = record[4][0]
                if _is_disallowed_ip(resolved_ip):
                    raise URLValidationError(
                        "Domain resolves to a private or restricted network address."
                    )

    clean_path = parsed.path or "/"
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc,
            clean_path,
            "",
            parsed.query,
            "",
        )
    )
