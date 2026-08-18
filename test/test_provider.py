import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from provider.omniseed_provider import OmniSeedProvider, ProviderError, PROTOCOL


class FakeClient:
    def __init__(self, company="omniseed_ecosystem", resources=None, fail=False):
        self.company = company
        self.resources = resources if resources is not None else [{"family": "policies", "id": "review_policy"}]
        self.fail = fail

    def get(self, path):
        if self.fail:
            raise ProviderError("unreachable", "remote_unreachable")
        return {"company": {"id": self.company}, "instance": {"desiredRevision": "a" * 40}, "resources": self.resources, "history": [{"type": "plan.created"}]}


def action(family="policies", resource_id="review_policy", offers=None):
    values = offers or {"policies": ["required_review"], "skills": ["company_reasoning"], "observations": ["company_state_observation"]}[family]
    return {"id": "action-1", "family": family, "resourceId": resource_id, "desired": {"offers": values}}


class ProviderTests(unittest.TestCase):
    def provider(self, client=None):
        subject = OmniSeedProvider({"operationEndpoint": "https://omniseed.example", "desiredRevision": "a" * 40}, client or FakeClient())
        subject.company_id = "omniseed_ecosystem"
        return subject

    def test_manifest_and_runtime_consolidate_one_omniseed_provider(self):
        result = self.provider().initialize({"protocolVersion": PROTOCOL, "configuration": {"operationEndpoint": "https://omniseed.example", "desiredRevision": "a" * 40}, "context": {"companyId": "omniseed_ecosystem"}})
        manifest = json.loads(Path("provider-package.json").read_text())
        self.assertEqual(result["provider"]["id"], "omniseed")
        self.assertEqual(result["primitiveFamilies"], ["skills", "policies", "observations"])
        self.assertEqual(result["primitiveFamilies"], manifest["primitiveFamilies"])
        self.assertEqual(result["operations"], manifest["operations"])

    def test_validate_accepts_only_declared_families_and_offerings(self):
        for family in ["skills", "policies", "observations"]:
            self.assertTrue(self.provider().validate(action(family, family + "_resource"))["valid"])
        self.assertFalse(self.provider().validate(action("policies", offers=["invented_policy"]))["valid"])
        self.assertFalse(self.provider().validate({"family": "agents", "resourceId": "lily", "desired": {"offers": []}})["valid"])

    def test_apply_binds_primitive_without_claiming_capability_success(self):
        result = self.provider().apply(action())
        self.assertEqual(result["status"], "bound")
        self.assertEqual(result["attributes"]["family"], "policies")
        self.assertNotIn("capability", json.dumps(result).lower())

    def test_observe_requires_matching_engine_projection_resource(self):
        binding = self.provider().apply(action())
        observed = self.provider().observe(binding)
        self.assertEqual(observed["status"], "healthy")
        self.assertEqual(observed["evidence"][0]["desiredRevision"], "a" * 40)
        degraded = self.provider(FakeClient(resources=[])).observe(binding)
        self.assertEqual(degraded["status"], "degraded")

    def test_status_separates_configuration_connection_and_health(self):
        self.assertEqual(self.provider().status(), {"implementation_available": True, "configured": True, "connected": True, "healthy": True})
        unhealthy = self.provider(FakeClient(company="other")).status()
        self.assertTrue(unhealthy["connected"])
        self.assertFalse(unhealthy["healthy"])
        stale = self.provider()
        stale.configuration["desiredRevision"] = "b" * 40
        self.assertFalse(stale.status()["healthy"])

    def test_activity_and_projection_operations_are_read_only(self):
        provider = self.provider()
        self.assertEqual(provider.invoke("engine.activity.inspect", {}, {"actorId": "operator"})["activity"][0]["type"], "plan.created")
        self.assertEqual(provider.invoke("engine.projection.inspect", {}, {"actorId": "operator"})["company"]["id"], "omniseed_ecosystem")
        with self.assertRaises(ProviderError):
            provider.invoke("provider.mutate.anything", {}, {"actorId": "operator"})

    def test_protocol_process_never_echoes_operation_token(self):
        messages = [
            {"jsonrpc": "2.0", "id": 1, "method": "provider.initialize", "params": {"protocolVersion": PROTOCOL, "configuration": {}, "context": {"companyId": "omniseed_ecosystem"}}},
            {"jsonrpc": "2.0", "id": 2, "method": "provider.status", "params": {}},
            {"jsonrpc": "2.0", "id": 3, "method": "provider.shutdown", "params": {}}
        ]
        with patch.dict(os.environ, {"OMNISEED_PROVIDER_OPERATION_TOKEN": "must-not-appear"}, clear=True):
            process = subprocess.run([sys.executable, "provider/omniseed_provider.py"], input="\n".join(json.dumps(item) for item in messages) + "\n", text=True, capture_output=True, check=True)
        self.assertNotIn("must-not-appear", process.stdout + process.stderr)


if __name__ == "__main__":
    unittest.main()
