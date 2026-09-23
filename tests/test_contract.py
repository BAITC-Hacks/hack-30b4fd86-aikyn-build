import os
import sys
import unittest
from pathlib import Path


CHECKOUT = Path(os.environ.get(
	"AIKYN_REPO",
	Path(__file__).resolve().parents[2] / "published-main",
)).resolve()
VALIDATION_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VALIDATION_ROOT))

from verify_pass import (  # noqa: E402
	check_observation_dependency,
	check_raw_agent,
	load_target,
)


class PublicContractTests(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.repo, cls.modules = load_target(CHECKOUT)

	def test_raw_agent_respects_public_limits(self):
		rows = check_raw_agent(self.modules)
		self.assertEqual(len(rows), 10)
		self.assertTrue(all(row["campaigns"] <= 10 for row in rows))
		self.assertTrue(all(row["pilots"] <= 20 for row in rows))
		self.assertTrue(all(row["contacts"] <= 15000 for row in rows))
		self.assertTrue(all(row["cost"] <= 100000 for row in rows))

	def test_agent_uses_observations_and_handles_pilot_failure(self):
		result = check_observation_dependency(self.modules)
		self.assertNotEqual(result["positive_campaigns"], result["negative_campaigns"])
		self.assertEqual(result["error_case"], "completed")


if __name__ == "__main__":
	unittest.main()
