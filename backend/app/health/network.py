"""
Outbound network diagnostic for the backend process.

Answers one question: can *this* process resolve and reach the external
providers Content OS depends on? Sends no credentials and never returns
response bodies.
"""
import socket
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

import httpx

NETWORK_CHECK_HOSTS = ("api.buffer.com", "openrouter.ai", "github.com")
NETWORK_CHECK_TIMEOUT_SECONDS = 5.0


def _resolve(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    return sorted({info[4][0] for info in infos})


def check_host(host: str) -> dict:
    started = time.monotonic()
    result = {
        "host": host,
        "resolved": False,
        "ip_count": 0,
        "http_status": None,
        "error": None,
        "ms": 0,
    }

    # getaddrinfo has no timeout of its own, so bound it from the outside.
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        ips = executor.submit(_resolve, host).result(timeout=NETWORK_CHECK_TIMEOUT_SECONDS)
        result["resolved"] = True
        result["ip_count"] = len(ips)
    except FutureTimeoutError:
        result["error"] = f"DNS lookup timed out after {NETWORK_CHECK_TIMEOUT_SECONDS:.0f}s"
    except socket.gaierror as err:
        result["error"] = f"DNS resolution failed: {err.strerror or err}"
    except OSError as err:
        result["error"] = f"DNS lookup error: {type(err).__name__}"
    finally:
        executor.shutdown(wait=False)

    if result["resolved"]:
        try:
            with httpx.Client(timeout=NETWORK_CHECK_TIMEOUT_SECONDS, follow_redirects=False) as client:
                response = client.head(f"https://{host}/")
            result["http_status"] = response.status_code
        except httpx.TimeoutException:
            result["error"] = f"HTTP request timed out after {NETWORK_CHECK_TIMEOUT_SECONDS:.0f}s"
        except httpx.HTTPError as err:
            result["error"] = f"HTTP error: {type(err).__name__}"

    result["ms"] = round((time.monotonic() - started) * 1000)
    return result


def check_network() -> dict:
    checks = [check_host(host) for host in NETWORK_CHECK_HOSTS]
    return {
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "all_resolved": all(c["resolved"] for c in checks),
        "checks": checks,
    }
