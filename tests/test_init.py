import json
import unittest
from importlib.metadata import distribution
from importlib.resources import files

import mcp_pdf_ingestion


class TestInit(unittest.TestCase):
    def test_version(self):
        self.assertEqual(mcp_pdf_ingestion.__version__, "0.1.0")

    def test_distribution_entry_point_and_config_resource(self):
        dist = distribution("mcp-pdf-ingestion")
        self.assertEqual(dist.version, mcp_pdf_ingestion.__version__)
        entry = [e for e in dist.entry_points if e.group == "console_scripts"]
        self.assertEqual([(e.name, e.value) for e in entry], [("mcp-pdf-ingestion", "mcp_pdf_ingestion.server:main")])
        self.assertTrue(callable(entry[0].load()))
        config = json.loads(files(mcp_pdf_ingestion).joinpath("config.json").read_text(encoding="utf-8"))
        self.assertIn("heuristics", config)
        self.assertGreater(config["images"]["max_side"]["value"], 0)


if __name__ == "__main__":
    unittest.main()
