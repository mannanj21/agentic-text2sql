import pytest

from app.guardrails.ssrf import UnsafeTargetError, resolve_target


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "::1",
        "10.1.2.3",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",
        "::ffff:127.0.0.1",
        "0.0.0.0",
        "224.0.0.1",
        "240.0.0.1",
        "fe80::1",
        "fd00:ec2::254",
    ],
)
def test_resolve_target_rejects_non_public_addresses(address: str) -> None:
    with pytest.raises(UnsafeTargetError, match="disallowed"):
        resolve_target("db.example", 5432, resolver=lambda _: [address])


@pytest.mark.parametrize("host", ["2130706433", "0x7f000001", "0177.0.0.1"])
def test_resolve_target_rejects_obfuscated_private_ip_encodings(host: str) -> None:
    with pytest.raises(UnsafeTargetError, match="disallowed"):
        resolve_target(host, 5432, resolver=lambda _: ["127.0.0.1"])


def test_resolve_target_rejects_mixed_public_and_private_dns_answers() -> None:
    with pytest.raises(UnsafeTargetError, match="disallowed"):
        resolve_target("db.example", 5432, resolver=lambda _: ["8.8.8.8", "10.0.0.1"])


def test_resolve_target_pins_the_validated_ip_for_dns_rebinding_protection() -> None:
    calls = 0

    def rebinding_resolver(_: str) -> list[str]:
        nonlocal calls
        calls += 1
        return ["8.8.8.8"] if calls == 1 else ["127.0.0.1"]

    target = resolve_target("db.example", 5432, resolver=rebinding_resolver)
    assert calls == 1
    assert target.libpq_parameters() == {"host": "db.example", "hostaddr": "8.8.8.8", "port": 5432}


def test_resolve_target_allows_private_addresses_only_with_explicit_override() -> None:
    target = resolve_target(
        "demo-db", 5432, allow_private_hosts=True, resolver=lambda _: ["172.18.0.5"]
    )
    assert target.hostaddr == "172.18.0.5"


@pytest.mark.parametrize("port", [0, -1, 65536, True])
def test_resolve_target_rejects_invalid_ports(port: int) -> None:
    with pytest.raises(UnsafeTargetError, match="port"):
        resolve_target("db.example", port, resolver=lambda _: ["8.8.8.8"])


@pytest.mark.parametrize("host", ["", " ", "db example", "[::1]", "db\x00example"])
def test_resolve_target_rejects_malformed_hostnames(host: str) -> None:
    with pytest.raises(UnsafeTargetError):
        resolve_target(host, 5432, resolver=lambda _: ["8.8.8.8"])
