import ast
import unittest

import auditgym.eval.verify_independent as vi


class TestIndependence(unittest.TestCase):
    def test_verifier_does_not_import_generator_logic(self):
        src = open(vi.__file__, encoding="utf-8").read()
        tree = ast.parse(src)
        mods = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mods.add(("." * node.level) + (node.module or ""))
            elif isinstance(node, ast.Import):
                mods.update(a.name for a in node.names)
        forbidden = {m for m in mods if "gen.build" in m or "gen.history" in m or "gen.inject" in m or "rules" in m}
        self.assertEqual(forbidden, set())
        # the only allowed auditgym import is the file writer used by the adapter
        self.assertTrue(all(m in ("..gen.export",) or not m.startswith(".") for m in mods))


if __name__ == "__main__":
    unittest.main()
