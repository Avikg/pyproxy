"""
tests/test_proxy.py – Unit tests for filters, cache, bandwidth, and HTTP parser.
"""
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from proxy.config import FilterConfig, CacheConfig, BandwidthConfig
from proxy.filters import IPFilter, DomainFilter
from proxy.cache import ResponseCache
from proxy.bandwidth import BandwidthManager, TokenBucket
from proxy.http_parser import parse_request


# ---------------------------------------------------------------------------
# IPFilter
# ---------------------------------------------------------------------------

class TestIPFilter:
    def test_none_mode_allows_all(self):
        f = IPFilter(FilterConfig(mode="none", list=[]))
        assert f.is_allowed("1.2.3.4")

    def test_allowlist_permits_listed_ip(self):
        f = IPFilter(FilterConfig(mode="allowlist", list=["192.168.1.10"]))
        assert f.is_allowed("192.168.1.10")

    def test_allowlist_blocks_unlisted_ip(self):
        f = IPFilter(FilterConfig(mode="allowlist", list=["192.168.1.10"]))
        assert not f.is_allowed("10.0.0.1")

    def test_blocklist_blocks_listed_ip(self):
        f = IPFilter(FilterConfig(mode="blocklist", list=["10.0.0.0/8"]))
        assert not f.is_allowed("10.5.5.5")

    def test_blocklist_allows_unlisted_ip(self):
        f = IPFilter(FilterConfig(mode="blocklist", list=["10.0.0.0/8"]))
        assert f.is_allowed("192.168.1.1")

    def test_cidr_range(self):
        f = IPFilter(FilterConfig(mode="allowlist", list=["192.168.0.0/24"]))
        assert f.is_allowed("192.168.0.100")
        assert not f.is_allowed("192.168.1.1")


# ---------------------------------------------------------------------------
# DomainFilter
# ---------------------------------------------------------------------------

class TestDomainFilter:
    def test_none_mode_allows_all(self):
        f = DomainFilter(FilterConfig(mode="none", list=[]))
        assert f.is_allowed("example.com")

    def test_blocklist_exact(self):
        f = DomainFilter(FilterConfig(mode="blocklist", list=["ads.example.com"]))
        assert not f.is_allowed("ads.example.com")
        assert f.is_allowed("example.com")

    def test_blocklist_wildcard(self):
        f = DomainFilter(FilterConfig(mode="blocklist", list=["*.tracker.net"]))
        assert not f.is_allowed("click.tracker.net")
        assert f.is_allowed("tracker.net")

    def test_allowlist(self):
        f = DomainFilter(FilterConfig(mode="allowlist", list=["safe.com"]))
        assert f.is_allowed("safe.com")
        assert not f.is_allowed("unsafe.com")

    def test_case_insensitive(self):
        f = DomainFilter(FilterConfig(mode="blocklist", list=["Bad.COM"]))
        assert not f.is_allowed("bad.com")


# ---------------------------------------------------------------------------
# ResponseCache
# ---------------------------------------------------------------------------

class TestResponseCache:
    def _make_cache(self, max_size=10, ttl=60):
        return ResponseCache(CacheConfig(enabled=True, max_size=max_size, ttl=ttl))

    def test_store_and_retrieve(self):
        c = self._make_cache()
        c.put("GET|host|/", b"HTTP/1.1 200 OK", b"Content-Type: text/html", b"<html/>")
        e = c.get("GET|host|/")
        assert e is not None
        assert e.body == b"<html/>"

    def test_miss_returns_none(self):
        c = self._make_cache()
        assert c.get("GET|missing|/") is None

    def test_ttl_expiry(self):
        c = ResponseCache(CacheConfig(enabled=True, max_size=10, ttl=0))
        c.put("k", b"HTTP/1.1 200 OK", b"", b"data")
        time.sleep(0.01)
        assert c.get("k") is None

    def test_lru_eviction(self):
        c = self._make_cache(max_size=2)
        c.put("k1", b"HTTP/1.1 200 OK", b"", b"1")
        c.put("k2", b"HTTP/1.1 200 OK", b"", b"2")
        c.put("k3", b"HTTP/1.1 200 OK", b"", b"3")   # evicts k1
        assert c.get("k1") is None
        assert c.get("k2") is not None
        assert c.get("k3") is not None

    def test_disabled_cache(self):
        c = ResponseCache(CacheConfig(enabled=False))
        c.put("k", b"HTTP/1.1 200 OK", b"", b"data")
        assert c.get("k") is None


# ---------------------------------------------------------------------------
# TokenBucket / BandwidthManager
# ---------------------------------------------------------------------------

class TestTokenBucket:
    def test_unlimited_bucket(self):
        b = TokenBucket(0)
        start = time.monotonic()
        b.consume(1_000_000)
        assert time.monotonic() - start < 0.1

    def test_rate_limiting(self):
        b = TokenBucket(8)           # 8 KB/s = 8192 B/s
        b.consume(8192)              # drain the initially-full bucket (free)
        start = time.monotonic()
        b.consume(8192)              # now must wait ~1 second to refill
        elapsed = time.monotonic() - start
        assert elapsed >= 0.9

class TestBandwidthManager:
    def test_get_bucket_unlimited(self):
        cfg = BandwidthConfig(enabled=True, default_kbps=0)
        m = BandwidthManager(cfg)
        assert m.get_bucket("1.2.3.4") is None

    def test_get_bucket_per_ip(self):
        cfg = BandwidthConfig(enabled=True, default_kbps=0, per_ip={"1.2.3.4": 512})
        m = BandwidthManager(cfg)
        assert m.get_bucket("1.2.3.4") is not None
        assert m.get_bucket("9.9.9.9") is None

    def test_disabled(self):
        cfg = BandwidthConfig(enabled=False, default_kbps=512)
        m = BandwidthManager(cfg)
        assert m.get_bucket("1.2.3.4") is None


# ---------------------------------------------------------------------------
# HTTP Parser
# ---------------------------------------------------------------------------

class TestHTTPParser:
    def test_get_absolute(self):
        raw = b"GET http://example.com/path?q=1 HTTP/1.1\r\nHost: example.com\r\n\r\n"
        r = parse_request(raw)
        assert r.method == "GET"
        assert r.host == "example.com"
        assert r.port == 80
        assert r.path == "/path?q=1"

    def test_connect(self):
        raw = b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n"
        r = parse_request(raw)
        assert r.is_connect
        assert r.host == "example.com"
        assert r.port == 443

    def test_host_header_fallback(self):
        raw = b"GET /index.html HTTP/1.1\r\nHost: mysite.com:8080\r\n\r\n"
        r = parse_request(raw)
        assert r.host == "mysite.com"
        assert r.port == 8080
        assert r.path == "/index.html"

    def test_bad_request_returns_none(self):
        assert parse_request(b"NOT VALID HTTP") is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
