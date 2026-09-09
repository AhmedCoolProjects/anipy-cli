import json
import socket
import urllib.request

__appname__ = "anipy-api"
__version__ = "3.10.0"

_orig_getaddrinfo = socket.getaddrinfo
_dns_cache = {}

def _doh_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    try:
        res = _orig_getaddrinfo(host, port, family, type, proto, flags)
        valid = [r for r in res if r[4][0] not in ("0.0.0.0", "::", "127.0.0.1")]
        if valid:
            return res
    except socket.gaierror:
        pass

    if not isinstance(host, str) or host.replace(".", "").isdigit():
        return _orig_getaddrinfo(host, port, family, type, proto, flags)

    if host in _dns_cache:
        return _orig_getaddrinfo(_dns_cache[host], port, family, type, proto, flags)

    for doh_url in (
        f"https://cloudflare-dns.com/dns-query?name={host}&type=A",
        f"https://dns.google/resolve?name={host}&type=A",
    ):
        try:
            req = urllib.request.Request(
                doh_url, headers={"accept": "application/dns-json", "User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for ans in data.get("Answer", []):
                    if ans.get("type") == 1:
                        ip = ans["data"]
                        _dns_cache[host] = ip
                        return _orig_getaddrinfo(ip, port, family, type, proto, flags)
        except Exception:
            continue

    return _orig_getaddrinfo(host, port, family, type, proto, flags)

socket.getaddrinfo = _doh_getaddrinfo
