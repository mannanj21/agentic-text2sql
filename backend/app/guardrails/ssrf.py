"""SSRF protection for user-supplied target database hosts."""

import ipaddress
import socket
from collections.abc import Callable, Sequence
from dataclasses import dataclass

Resolver = Callable[[str], Sequence[str]]


class UnsafeTargetError(ValueError):
    """Raised when a target database address is unsuitable for outbound access."""


@dataclass(frozen=True)
class ResolvedTarget:
    """A safe target with its DNS result pinned for the subsequent connection."""

    host: str
    hostaddr: str
    port: int

    def libpq_parameters(self) -> dict[str, str | int]:
        """Keep hostname for TLS SNI while pinning libpq to the validated address."""
        return {"host": self.host, "hostaddr": self.hostaddr, "port": self.port}


def resolve_target(
    host: str,
    port: int,
    *,
    allow_private_hosts: bool = False,
    resolver: Resolver | None = None,
) -> ResolvedTarget:
    """Resolve and validate a host, rejecting unsafe DNS answers before connecting.

    Every DNS answer must be safe.  The returned ``hostaddr`` must be passed to
    libpq/psycopg so a later DNS lookup cannot redirect the connection.
    """
    _validate_port(port)
    normalized_host = _validate_host(host)
    addresses = _resolve_addresses(normalized_host, resolver)
    if not addresses:
        raise UnsafeTargetError("Target hostname did not resolve to an IP address.")

    parsed_addresses = tuple(_parse_address(address) for address in addresses)
    if not allow_private_hosts:
        unsafe = [str(address) for address in parsed_addresses if not _is_public(address)]
        if unsafe:
            raise UnsafeTargetError(
                "Target hostname resolves to a disallowed address: " + ", ".join(unsafe)
            )

    # Using a resolved address, rather than the input hostname, prevents DNS rebinding.
    return ResolvedTarget(host=normalized_host, hostaddr=str(parsed_addresses[0]), port=port)


def _validate_port(port: int) -> None:
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise UnsafeTargetError("Target port must be an integer between 1 and 65535.")


def _validate_host(host: str) -> str:
    normalized = host.strip() if isinstance(host, str) else ""
    if not normalized or len(normalized) > 253 or any(char.isspace() for char in normalized):
        raise UnsafeTargetError("Target hostname must be a non-empty hostname or IP address.")
    if "\x00" in normalized or normalized.startswith("[") or normalized.endswith("]"):
        raise UnsafeTargetError("Target hostname is malformed.")
    return normalized


def _resolve_addresses(host: str, resolver: Resolver | None) -> Sequence[str]:
    try:
        if resolver is not None:
            return resolver(host)
        literal = ipaddress.ip_address(host)
        return (str(literal),)
    except ValueError:
        pass
    except OSError as exc:
        raise UnsafeTargetError("Target hostname could not be resolved.") from exc

    try:
        records = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeTargetError("Target hostname could not be resolved.") from exc
    return tuple(str(record[4][0]) for record in records)


def _parse_address(address: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    try:
        return ipaddress.ip_address(address)
    except ValueError as exc:
        raise UnsafeTargetError("Target hostname resolved to an invalid IP address.") from exc


def _is_public(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return true only for globally routable addresses.

    Address-class flags are explicit because Python's ``is_global`` considers
    multicast IPv4 addresses global on some supported Python versions.
    """
    return address.is_global and not any(
        (
            address.is_loopback,
            address.is_private,
            address.is_link_local,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        )
    )
