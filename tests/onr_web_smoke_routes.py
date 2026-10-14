"""Resolve Flask paths for smoke tests (endpoint name → @app.route)."""
from __future__ import annotations

import re
from pathlib import Path

def _instalar_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "ri_web.py").is_file() and (parent / "app.py").is_file():
            return parent
    return here.parents[1]


INSTALAR = _instalar_root()

DEFAULTS: dict[str, str] = {
    "ri_indicador_real": "/registro-imoveis/indicador-real",
    "ri_indicador_pessoal": "/registro-imoveis/indicador-pessoal",
    "ri_onr": "/registro-imoveis/onr",
    "ri_onr_next_cloud": "/registro-imoveis/onr/next-cloud-sas",
}

MODULES = (
    "ri_web.py",
    "ri_onr_web.py",
    "ri_onr.py",
    "onr_endereco_web.py",
    "app.py",
)


def discover_routes(endpoints: list[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for mod in MODULES:
        path = INSTALAR / mod
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for ep in endpoints:
            if ep in found:
                continue
            m = re.search(
                rf"@app\.route\(\s*[\"']([^\"']+)[\"'][^)]*\)\s*(?:@[^\n]+\n\s*)*def\s+{re.escape(ep)}\b",
                text,
                re.MULTILINE,
            )
            if m:
                found[ep] = m.group(1)
                continue
            dm = re.search(rf"def\s+{re.escape(ep)}\s*\(", text)
            if not dm:
                continue
            chunk = text[max(0, dm.start() - 1200) : dm.start()]
            routes = re.findall(r"@app\.route\(\s*[\"']([^\"']+)[\"']", chunk)
            if routes:
                found[ep] = routes[-1]
    return found


def path_for(endpoint: str) -> str:
    return discover_routes([endpoint]).get(endpoint, DEFAULTS[endpoint])
