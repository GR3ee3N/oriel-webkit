import codecs
import json
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch

from tools import enable
from .repository import RepositoryTests


class DeployTests(RepositoryTests):
    def setUp(self):
        super().setUp()
        self.env.update(BOX="test-target", TEST_STATE=str(self.temporary))
        self.executable("ssh", '''#!/usr/bin/env python3
import os,sys
from pathlib import Path
root = Path(os.environ['TEST_STATE'])
if sys.argv[2:4] == ['python3', '-']:
    source = sys.stdin.read()
    compile(source, '<remote enable>', 'exec')
    with (root/'enable-calls').open('a') as f: f.write(sys.argv[-1]+'\\n')
    if (root/'fail-enable').exists(): sys.exit(1)
''')
        self.executable("rsync", '''#!/usr/bin/env python3
import os,sys
from pathlib import Path
root=Path(os.environ['TEST_STATE'])
(root/'installed').touch()
if (root/'fail-transfer').exists(): sys.exit(1)
''')
        addon = self.root / ".cache/runtime/script.module.oriel.webkit"
        addon.mkdir(parents=True)
        (addon / "addon.xml").write_text("add-on")

    def test_retry_after_failed_activation_enables_existing_installation(self):
        failure = self.temporary / "fail-enable"
        failure.touch()
        self.command("tools/deploy.sh", success=False)
        self.assertTrue((self.temporary / "installed").exists())
        failure.unlink()
        self.assertIn("installed script.module.oriel.webkit", self.command("tools/deploy.sh"))
        self.assertEqual((self.temporary / "enable-calls").read_text().splitlines(), ["script.module.oriel.webkit"] * 2)

    def test_failed_transfer_does_not_enable_or_report_success(self):
        (self.temporary / "fail-transfer").touch()
        output = self.command("tools/deploy.sh", success=False)
        self.assertNotIn("installed script.module.oriel.webkit", output)
        self.assertFalse((self.temporary / "enable-calls").exists())

    def test_enable_waits_for_registration_and_confirms_enabled_state(self):
        client = Mock()
        client.call.side_effect = [RuntimeError("not registered"), {"addon": {"enabled": False}}, "OK", {"addon": {"enabled": True}}]
        with patch.object(enable, "Kodi", return_value=client), patch.object(enable.time, "sleep") as sleep:
            enable.enable("script.test")
        self.assertEqual(sleep.call_count, 2)
        self.assertEqual(client.call.call_args.args, ("Addons.GetAddonDetails", {"addonid": "script.test", "properties": ["enabled"]}))
        client.sock.close.assert_called_once()

    def test_already_enabled_addon_needs_no_change(self):
        client = Mock(call=Mock(return_value={"addon": {"enabled": True}}))
        with patch.object(enable, "Kodi", return_value=client):
            enable.enable("script.test")
        client.call.assert_called_once_with("Addons.GetAddonDetails", {"addonid": "script.test", "properties": ["enabled"]})

    def test_timeout_fails_instead_of_reporting_installation_success(self):
        client = Mock(call=Mock(side_effect=RuntimeError("not registered")))
        with patch.object(enable, "Kodi", return_value=client), patch.object(enable.time, "monotonic", side_effect=[0, 11]):
            with self.assertRaisesRegex(RuntimeError, "did not enable"):
                enable.enable("script.test")
        client.sock.close.assert_called_once()

    def test_notifications_and_split_tcp_replies_do_not_hide_rpc_errors(self):
        client = enable.Kodi.__new__(enable.Kodi)
        client.buf = ""
        client.decoder = json.JSONDecoder()
        client.utf8 = codecs.getincrementaldecoder("utf-8")()
        client.next_id = 1
        client.sock = Mock(recv=Mock(side_effect=[b'{"method":"OnUpdate"}{"id":1,"error":{"message":"caf\xc3', b'\xa9"}}']))
        with self.assertRaisesRegex(RuntimeError, "café"):
            client.call("Addons.GetAddonDetails", {})

    def test_stdin_helper_waits_for_registration_and_verifies_activation_over_tcp(self):
        calls = []
        with socket.socket() as server, ThreadPoolExecutor(max_workers=1) as executor:
            server.bind(("127.0.0.1", 0))
            server.listen()
            server.settimeout(5)
            def kodi():
                conn, _ = server.accept()
                with conn, conn.makefile("rb") as requests:
                    conn.settimeout(5)
                    decoder, text = json.JSONDecoder(), ""
                    enabled = False
                    while chunk := requests.read1(65536):
                        text += chunk.decode()
                        try:
                            request, end = decoder.raw_decode(text)
                        except json.JSONDecodeError:
                            continue
                        text = text[end:]
                        calls.append(request)
                        response = {"jsonrpc": "2.0", "id": request["id"]}
                        if len(calls) == 1:
                            response["error"] = {"code": -32602, "message": "not registered"}
                        elif request["method"] == "Addons.SetAddonEnabled":
                            enabled = request["params"]["enabled"]
                            response["result"] = "OK"
                        else:
                            response["result"] = {"addon": {"enabled": enabled}}
                        conn.sendall(b'{"jsonrpc":"2.0","method":"Addons.OnInstalled"}' + json.dumps(response).encode())
            task = executor.submit(kodi)
            source = (self.root / "tools/enable.py").read_text().replace("9090", str(server.getsockname()[1]))
            result = subprocess.run([sys.executable, "-", "script.test"], input=source, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            task.result(timeout=5)
        self.assertEqual([call["method"] for call in calls],
                         ["Addons.GetAddonDetails", "Addons.GetAddonDetails", "Addons.SetAddonEnabled", "Addons.GetAddonDetails"])
        self.assertTrue(all(call["params"]["addonid"] == "script.test" for call in calls))
