from __future__ import annotations

import json
import socket
import threading
from dataclasses import dataclass
from typing import Callable

DISCOVERY_MAGIC = b"CARTORIO_GESTAO_DISCOVER_V1"


def _is_usable_ipv4(ip: str) -> bool:
    return bool(ip) and not ip.startswith("127.") and not ip.startswith("169.254.") and ip != "0.0.0.0"


def lan_ipv4_addresses() -> list[str]:
    found: set[str] = set()
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_STREAM):
            ip = item[4][0]
            if _is_usable_ipv4(ip):
                found.add(ip)
    except OSError:
        pass
    # Descobre o IP da interface da rota padrao sem enviar trafego real.
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("192.0.2.1", 9))
        ip = probe.getsockname()[0]
        probe.close()
        if _is_usable_ipv4(ip):
            found.add(ip)
    except OSError:
        pass
    return sorted(found)


def best_local_ip_for(client_ip: str) -> str:
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect((client_ip, 9))
        ip = probe.getsockname()[0]
        probe.close()
        if _is_usable_ipv4(ip):
            return ip
    except OSError:
        pass
    ips = lan_ipv4_addresses()
    return ips[0] if ips else "127.0.0.1"


@dataclass
class DiscoveryResponder:
    port: int
    payload_factory: Callable[[str], dict]
    enabled: bool = True

    def start(self) -> threading.Thread | None:
        if not self.enabled:
            return None
        thread = threading.Thread(target=self._run, name="cartorio-network-discovery", daemon=True)
        thread.start()
        return thread

    def _run(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("0.0.0.0", int(self.port)))
        except OSError:
            sock.close()
            return
        while True:
            try:
                data, addr = sock.recvfrom(4096)
                if data.strip() != DISCOVERY_MAGIC:
                    continue
                client_ip = addr[0]
                payload = self.payload_factory(client_ip)
                payload.setdefault("product", "CartorioGestao")
                payload.setdefault("discovery", 1)
                sock.sendto(json.dumps(payload, ensure_ascii=False).encode("utf-8"), addr)
            except OSError:
                break
            except Exception:
                continue
