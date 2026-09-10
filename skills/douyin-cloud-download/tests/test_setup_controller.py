from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[3] / "scripts" / "setup.py"
SPEC = importlib.util.spec_from_file_location("setup_controller", SCRIPT)
setup = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(setup)


class SetupControllerTests(unittest.TestCase):
    def test_fixed_versions(self):
        self.assertEqual(setup.PINNED_COMMIT, "df8aced70e476ae3330fa913186f3207b4843201")
        self.assertEqual(setup.QUARK_VERSION, "1.0.19")
        self.assertEqual(setup.BAIDU_SKILL_VERSION, "v1.7.5")

    def test_quark_host_allowlist(self):
        setup.validate_official_https("https://pdds.quark.cn/path/skill.zip")
        setup.validate_official_https("https://open-api-drive.quark.cn/path/skill.zip")
        with self.assertRaises(RuntimeError):
            setup.validate_official_https("https://example.com/skill.zip")
        with self.assertRaises(RuntimeError):
            setup.validate_official_https("http://pdds.quark.cn/skill.zip")

    def test_locate_quark_root_requires_expected_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "package"
            (root / "scripts").mkdir(parents=True)
            (root / "SKILL.md").write_text("version: 1.0.19\n", encoding="utf-8")
            (root / "scripts" / "install.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            (root / "scripts" / "quark-drive.cjs").write_text("// cli\n", encoding="utf-8")
            self.assertEqual(setup.locate_quark_root(Path(temp)), root.resolve())


if __name__ == "__main__":
    unittest.main()
