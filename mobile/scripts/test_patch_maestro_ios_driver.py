import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location("patch_driver", Path(__file__).with_name("patch-maestro-ios-driver.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DriverPinTests(unittest.TestCase):
    def test_checksum_rejects_tampered_download(self):
        with self.assertRaises(ValueError):
            module.verified(b"tampered", "0" * 64)

    def test_checksum_does_not_accept_non_archive(self):
        payload = b"not a driver zip"
        with self.assertRaises(zipfile.BadZipFile):
            module.verified(payload, hashlib.sha256(payload).hexdigest())

    def test_valid_archive(self):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("Runner.app/Info.plist", b"fixture")
        data = payload.getvalue()
        self.assertEqual(module.verified(data, hashlib.sha256(data).hexdigest()), data)

    def test_patch_preserves_cli_and_device_resources(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            (home / "lib").mkdir()
            jar = home / "lib/driver.jar"
            with zipfile.ZipFile(jar, "w") as output:
                for name in module.PINS:
                    output.writestr(module.PREFIX + name, b"old")
                output.writestr("Driver.class", b"unchanged CLI")
                output.writestr("driver-iphoneos/device.zip", b"unchanged device")
            module.patch(home, {name: b"fixed" for name in module.PINS})
            with zipfile.ZipFile(jar) as result:
                self.assertEqual(result.read("Driver.class"), b"unchanged CLI")
                self.assertEqual(result.read("driver-iphoneos/device.zip"), b"unchanged device")
                for name in module.PINS:
                    self.assertEqual(result.read(module.PREFIX + name), b"fixed")

    def test_unknown_install_layout_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                module.patch(Path(temporary), {name: b"fixed" for name in module.PINS})


if __name__ == "__main__":
    unittest.main()
