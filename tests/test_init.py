import unittest

import reviewer_mcp


class TestInit(unittest.TestCase):
    def test_version(self):
        self.assertEqual(reviewer_mcp.__version__, "0.1.0")


if __name__ == "__main__":
    unittest.main()
