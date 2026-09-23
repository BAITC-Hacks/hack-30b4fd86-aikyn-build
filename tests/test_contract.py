"""Adversarial checks using only the documented agent/environment interface."""
import unittest

from agent import Agent
from mock_environment import make_mock_env
from scoring_core import apply_filters
import pandas as pd


class PublicContractTests(unittest.TestCase):
    def _controlled_observations(self, positive_tariff):
        env, _ = make_mock_env(seed=42)
        real_run_pilot = env.run_pilot

        def run_pilot(**kwargs):
            result = real_run_pilot(**kwargs)
            # Replace only the public observation returned to Agent.act. Keep all
            # environment accounting and history updates performed by run_pilot.
            result = dict(result)
            result["observed_lift_ratio"] = 1.0 if kwargs["target_tariff"] == positive_tariff else 0.0
            return result

        env.run_pilot = run_pilot
        return env

    def test_pilot_observations_change_final_choice(self):
        # Both tariffs are among the hypotheses actually explored at seed 42.
        a = Agent().act(self._controlled_observations("tariff_9"))
        b = Agent().act(self._controlled_observations("tariff_8"))
        choices_a = {(c["target_tariff"], c.get("filter_current_tariff"), c.get("filter_arpu_segment")) for c in a}
        choices_b = {(c["target_tariff"], c.get("filter_current_tariff"), c.get("filter_arpu_segment")) for c in b}
        self.assertNotEqual(choices_a, choices_b, "final choices did not respond to changed pilot observations")

    def test_no_history_and_noisy_observations(self):
        env, _ = make_mock_env(seed=3)
        self.assertEqual(env.pilot_history, [])
        campaigns = Agent().act(env)
        self.assertTrue(1 <= len(campaigns) <= 10)
        self.assertTrue(env.pilot_history)
        self.assertTrue(all(pd.notna(p["observed_lift_ratio"]) for p in env.pilot_history))
        self.assertTrue(any(p["observed_lift_ratio"] < 0 for p in env.pilot_history))

    def test_negative_observations_are_consumed(self):
        env, _ = make_mock_env(seed=42)
        real_run_pilot = env.run_pilot
        returned = []

        def run_pilot(**kwargs):
            result = dict(real_run_pilot(**kwargs))
            result["observed_lift_ratio"] = -0.5
            returned.append(result["observed_lift_ratio"])
            return result

        env.run_pilot = run_pilot
        campaigns = Agent().act(env)
        self.assertTrue(returned)
        self.assertTrue(all(value < 0 for value in returned))
        self.assertTrue(1 <= len(campaigns) <= 10)

    def test_limited_resources_stay_within_actual_accounting(self):
        env, _ = make_mock_env(seed=42)
        env.remaining_budget = 160
        env.remaining_contacts = 500
        campaigns = Agent().act(env)
        pilot_cost = sum(p["cost"] for p in env.pilot_history)
        pilot_contacts = sum(p["n_customers"] for p in env.pilot_history)
        final_contacts = sum(len(apply_filters(env.customer_profile, pd.Series(c))) for c in campaigns)
        final_cost = sum(len(apply_filters(env.customer_profile, pd.Series(c))) * env.channels[c["channel"]]["cost_per_contact"] for c in campaigns)
        self.assertLessEqual(pilot_cost + final_cost, 160)
        self.assertLessEqual(pilot_contacts + final_contacts, 500)

    def test_pilot_errors_are_visible_as_contract_limitation(self):
        env, _ = make_mock_env(seed=42)
        env.run_pilot = lambda **kwargs: (_ for _ in ()).throw(RuntimeError("injected public API failure"))
        campaigns = Agent().act(env)
        # Current agent stops exploration after the first failed pilot. No tested
        # option then exists, so its output is empty and violates the 1-campaign
        # minimum. Keep this reproducer explicit until the agent owner fixes it.
        self.assertEqual(campaigns, [])

    def test_zero_contact_capacity_cannot_run_mandatory_pilot(self):
        env, _ = make_mock_env(seed=42)
        env.remaining_contacts = 0
        campaigns = Agent().act(env)
        self.assertEqual(env.pilot_history, [])
        self.assertEqual(campaigns, [])


if __name__ == "__main__":
    unittest.main()
