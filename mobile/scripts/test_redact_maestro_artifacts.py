import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("redactor", Path(__file__).with_name("redact-maestro-artifacts.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RedactMaestroArtifactsTest(unittest.TestCase):
    def test_uploaded_command_metadata_and_default_env_values_are_redacted(self):
        data = {"command": {"inputTextCommand": {"text": "typed-private-value"}},
                "metadata": {"evaluatedCommand": {"inputTextCommand": {"text": "typed-private-value"}},
                             "env": {"LOGIN_PASSWORD": "fixture-private-default"}, "status": "FAILED"}}
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "commands.json"
            path.write_text(json.dumps(data))
            module.sanitize(root, [])
            output = path.read_text()
            self.assertNotIn("typed-private-value", output)
            self.assertNotIn("fixture-private-default", output)
            self.assertEqual(json.loads(output)["metadata"]["status"], "FAILED")

    def test_raw_json_escaped_and_url_encoded_credentials_in_logs(self):
        from urllib.parse import quote
        secret = 'fixture-p@ss"\\ü'
        content = secret + " " + json.dumps(secret)[1:-1] + " " + quote(secret, safe="")
        self.assertEqual(module.redact_text(content, [secret]), "[REDACTED] [REDACTED] [REDACTED]")

    def test_sanitized_json_remains_valid_for_escaped_password(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / "metadata.json"
            p.write_text(json.dumps({"message": 'fixture-"password"'}))
            module.sanitize(root, ['fixture-"password"'])
            self.assertEqual(json.loads(p.read_text())["message"], module.MASK)

    def test_images_are_preserved(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / "screen.png"
            p.write_bytes(b"\x89PNG\xff")
            self.assertEqual(module.sanitize(root, ["fixture-secret"]), 0)
            self.assertEqual(p.read_bytes(), b"\x89PNG\xff")

    def test_unknown_binary_is_not_silently_published(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / "unexpected.bin").write_bytes(b"\xff\xfe")
            with self.assertRaises(UnicodeDecodeError):
                module.sanitize(root, [])

    def test_symlink_cannot_lead_outside_artifact_directory(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / "outside").symlink_to("/tmp")
            with self.assertRaises(ValueError):
                module.sanitize(root, [])


if __name__ == "__main__":
    unittest.main()
