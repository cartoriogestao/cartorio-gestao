from __future__ import annotations

import hashlib
import json
import socket
import time
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from network_discovery import DISCOVERY_MAGIC, DiscoveryResponder
from update_manager import (
    UpdateError,
    inspect_staged,
    load_staged,
    mark_approved,
    revalidate_staged,
    validate_and_stage,
)


def write_package(root: Path, manifest: dict, payload: dict[str, bytes],
                  extras: dict[str, bytes] | None = None) -> tuple[Path, str]:
    package = root / "u.cgu"
    with zipfile.ZipFile(package, "w") as zf:
        zf.writestr("update_manifest.json", json.dumps(manifest))
        for rel, content in payload.items():
            zf.writestr(f"payload/{rel}", content)
        for rel, content in (extras or {}).items():
            zf.writestr(f"payload/{rel}", content)
    return package, hashlib.sha256(package.read_bytes()).hexdigest()


def manifest_for(version: str, payload: dict[str, bytes],
                 *, delete=None) -> dict:
    return {
        "product": "CartorioGestao", "format": 1,
        "version": version, "min_version": "3.2.0",
        "files": [
            {"path": rel, "sha256": hashlib.sha256(content).hexdigest()}
            for rel, content in payload.items()
        ],
        "delete": [] if delete is None else delete,
    }


class UpdateNetworkTests(unittest.TestCase):
    def test_discovery_responder(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        DiscoveryResponder(port, lambda ip: {"url": "http://127.0.0.1:8765"}).start()
        time.sleep(0.05)
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client.settimeout(1)
        client.sendto(DISCOVERY_MAGIC, ("127.0.0.1", port))
        payload = json.loads(client.recvfrom(4096)[0].decode("utf-8"))
        client.close()
        self.assertEqual(payload["product"], "CartorioGestao")

    def test_update_validation_and_hash(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            package = root / "u.cgu"
            content = b"nova versao"
            manifest = {
                "product": "CartorioGestao", "format": 1, "version": "3.2.1", "min_version": "3.2.0",
                "files": [{"path": "app_test.txt", "sha256": hashlib.sha256(content).hexdigest()}], "delete": []
            }
            with zipfile.ZipFile(package, "w") as zf:
                zf.writestr("update_manifest.json", json.dumps(manifest))
                zf.writestr("payload/app_test.txt", content)
            package_hash = hashlib.sha256(package.read_bytes()).hexdigest()
            info = validate_and_stage(package, root / "stage", "3.2.0", package_hash)
            self.assertEqual(info["version"], "3.2.1")
            self.assertTrue((Path(info["stage_dir"]) / "payload" / "app_test.txt").exists())

    def test_update_rejects_unsafe_path(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            package = root / "u.cgu"
            content = b"x"
            manifest = {
                "product": "CartorioGestao", "format": 1, "version": "3.2.1", "min_version": "3.2.0",
                "files": [{"path": "C:/Windows/evil.txt", "sha256": hashlib.sha256(content).hexdigest()}], "delete": []
            }
            with zipfile.ZipFile(package, "w") as zf:
                zf.writestr("update_manifest.json", json.dumps(manifest))
                zf.writestr("payload/C:/Windows/evil.txt", content)
            with self.assertRaises(UpdateError):
                validate_and_stage(package, root / "stage", "3.2.0")

    def test_update_requires_hash_from_separate_channel(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            payload = {"VERSAO.txt": b"3.2.1"}
            package, _digest = write_package(
                root, manifest_for("3.2.1", payload), payload
            )
            with self.assertRaisesRegex(UpdateError, "canal separado"):
                validate_and_stage(
                    package, root / "stage", "3.2.0",
                    require_expected_hash=True,
                )

    def test_update_rejects_unsafe_version_and_hidden_payload(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            payload = {"VERSAO.txt": b"3.2.1"}
            unsafe, digest = write_package(
                root, manifest_for("../3.2.1", payload), payload
            )
            with self.assertRaisesRegex(UpdateError, "Versao de destino"):
                validate_and_stage(unsafe, root / "stage", "3.2.0", digest)

        with TemporaryDirectory() as td:
            root = Path(td)
            payload = {"VERSAO.txt": b"3.2.1"}
            package, digest = write_package(
                root, manifest_for("3.2.1", payload), payload,
                {"oculto.py": b"print('nao declarado')"},
            )
            with self.assertRaisesRegex(UpdateError, "arquivo oculto"):
                validate_and_stage(package, root / "stage", "3.2.0", digest)

    def test_static_inspection_approval_and_replay_protection(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            install = root / "install"
            install.mkdir()
            (install / "VERSAO.txt").write_text("3.2.0", encoding="utf-8")
            (install / "app.py").write_text(
                "VERSION = '3.2.0'\nprint('antiga')\n", encoding="utf-8"
            )
            payload = {
                "VERSAO.txt": b"3.2.1",
                "app.py": b"VERSION = '3.2.1'\nprint('nova')\n",
                "templates/css_valido.html": b"<style>.barra{width:100%}</style>",
            }
            package, digest = write_package(
                root, manifest_for("3.2.1", payload), payload
            )
            info = validate_and_stage(
                package, root / "stage", "3.2.0", digest,
                require_expected_hash=True,
            )
            inspection = inspect_staged(Path(info["stage_dir"]), install)
            self.assertTrue(inspection["ok"])
            self.assertFalse(inspection["executed_code"])
            self.assertIn("Arquivo critico alterado: app.py", inspection["warnings"])
            self.assertEqual(
                load_staged(Path(info["stage_dir"]))["state"],
                "READY_FOR_APPROVAL",
            )
            backup = root / "backup.zip"
            backup.write_bytes(b"backup valido")
            approved = mark_approved(
                Path(info["stage_dir"]), approved_by="admin",
                approved_at="2026-09-01T10:00:00", backup=str(backup),
            )
            self.assertEqual(approved["state"], "APPROVED")
            with self.assertRaisesRegex(UpdateError, "preservar a auditoria"):
                validate_and_stage(
                    package, root / "stage", "3.2.0", digest,
                    require_expected_hash=True,
                )
            with self.assertRaisesRegex(UpdateError, "nao esta pronta"):
                mark_approved(
                    Path(info["stage_dir"]), approved_by="admin",
                    approved_at="2026-09-01T10:01:00", backup=str(backup),
                )

    def test_inspection_rejects_syntax_error_and_tampering(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            install = root / "install"
            install.mkdir()
            (install / "VERSAO.txt").write_text("3.2.0", encoding="utf-8")
            (install / "app.py").write_text(
                "VERSION = '3.2.0'\n", encoding="utf-8"
            )
            payload = {
                "VERSAO.txt": b"3.2.1",
                "rotas.py": b"def quebrado(:\n    pass\n",
            }
            package, digest = write_package(
                root, manifest_for("3.2.1", payload), payload
            )
            info = validate_and_stage(package, root / "stage", "3.2.0", digest)
            inspection = inspect_staged(Path(info["stage_dir"]), install)
            self.assertFalse(inspection["ok"])
            self.assertEqual(load_staged(Path(info["stage_dir"]))["state"], "REJECTED")
            self.assertTrue(any("erro de sintaxe" in p for p in inspection["problems"]))
            self.assertTrue(any(
                "app.py declara 3.2.0" in p for p in inspection["problems"]
            ))

        with TemporaryDirectory() as td:
            root = Path(td)
            install = root / "install"
            install.mkdir()
            (install / "VERSAO.txt").write_text("3.2.0", encoding="utf-8")
            (install / "app.py").write_text(
                "VERSION = '3.2.0'\n", encoding="utf-8"
            )
            payload = {
                "VERSAO.txt": b"3.2.1",
                "app.py": b"VERSION = '3.2.1'\n",
            }
            package, digest = write_package(
                root, manifest_for("3.2.1", payload), payload
            )
            info = validate_and_stage(package, root / "stage", "3.2.0", digest)
            inspect_staged(Path(info["stage_dir"]), install)
            (Path(info["stage_dir"]) / "payload" / "VERSAO.txt").write_bytes(b"adulterada")
            with self.assertRaisesRegex(UpdateError, "alterada"):
                revalidate_staged(Path(info["stage_dir"]))


if __name__ == "__main__":
    unittest.main()
