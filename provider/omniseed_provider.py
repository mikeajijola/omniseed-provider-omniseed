#!/usr/bin/env python3
"""Engine-native primitive implementations supplied by OmniSeed."""

import datetime
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

PROTOCOL = "omniseed.provider.protocol/1.0"
PROVIDER_ID = "omniseed"
VERSION = "0.1.0-alpha.1"
FAMILIES = ["skills", "policies", "observations"]
METHODS = [
    "provider.initialize", "provider.status", "provider.validate", "provider.plan",
    "provider.apply", "provider.observe", "provider.invoke", "provider.shutdown"
]
OPERATIONS = ["engine.projection.inspect", "engine.activity.inspect"]
OFFERINGS = {
    "skills": ["company_reasoning", "software_engineering", "conformance_skill"],
    "policies": ["stewardship_authority", "required_review", "invariant_policy", "interface_authority", "reconciliation_authority"],
    "observations": ["company_state_observation", "change_observation", "conformance_observation", "interface_health_observation", "reconciliation_observation"]
}


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


class ProviderError(RuntimeError):
    def __init__(self, message, code="provider_error", details=None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


class OperationClient:
    def __init__(self, endpoint, token=None, timeout=10):
        self.endpoint = str(endpoint or "").rstrip("/")
        self.token = token
        self.timeout = timeout

    def get(self, path):
        headers = {"Accept": "application/json", "User-Agent": "omniseed-provider-omniseed/0.1"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        request = urllib.request.Request(self.endpoint + path, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raise ProviderError("OmniSeed endpoint returned an error", "remote_http_error", {"status": error.code, "path": path}) from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise ProviderError("OmniSeed endpoint is unreachable", "remote_unreachable", {"path": path}) from error
        except json.JSONDecodeError as error:
            raise ProviderError("OmniSeed endpoint returned invalid JSON", "invalid_remote_response", {"path": path}) from error


class OmniSeedProvider:
    def __init__(self, configuration=None, client=None):
        self.configuration = configuration or {}
        self.client = client or self._client()
        self.company_id = None

    def _client(self):
        credential = self.configuration.get("credentialEnvironment", "OMNISEED_PROVIDER_OPERATION_TOKEN")
        return OperationClient(self.configuration.get("operationEndpoint"), os.environ.get(credential), self.configuration.get("timeoutSeconds", 10))

    def initialize(self, params):
        if params.get("protocolVersion") != PROTOCOL:
            raise ProviderError("Unsupported protocol version", "protocol_mismatch", {"supported": PROTOCOL})
        self.configuration = params.get("configuration") or {}
        self.company_id = (params.get("context") or {}).get("companyId")
        if isinstance(self.client, OperationClient):
            self.client = self._client()
        offerings = [{"family": family, "id": offering, "products": ["engine", "operation_registry", "company_projection"]} for family, values in OFFERINGS.items() for offering in values]
        return {
            "protocolVersion": PROTOCOL,
            "provider": {"id": PROVIDER_ID, "name": "OmniSeed", "organisation": "OmniSeed", "version": VERSION},
            "primitiveFamilies": FAMILIES,
            "configurationSchema": "./provider-configuration.schema.json",
            "offerings": offerings,
            "operations": OPERATIONS,
            "methods": METHODS
        }

    @property
    def projection_path(self):
        return self.configuration.get("companyProjectionPath", "/api/company")

    def projection(self):
        return self.client.get(self.projection_path)

    @staticmethod
    def projection_revision(projection):
        return (projection.get("instance") or {}).get("desiredRevision") or projection.get("desiredRevision")

    def status(self):
        configured = bool(self.configuration.get("operationEndpoint"))
        connected = healthy = False
        if configured:
            try:
                projection = self.projection()
                actual = projection.get("companyId") or (projection.get("company") or {}).get("id")
                connected = True
                healthy = actual == self.company_id and self.projection_revision(projection) == self.configuration.get("desiredRevision")
            except ProviderError:
                pass
        return {"implementation_available": True, "configured": configured, "connected": connected, "healthy": healthy}

    def validate(self, action):
        family = action.get("family")
        desired = action.get("desired") or {}
        offered = desired.get("offers") or []
        issues = []
        if family not in FAMILIES:
            issues.append({"code": "unsupported_family", "message": "OmniSeed supports skills, policies, and observations only"})
        if not action.get("resourceId"):
            issues.append({"code": "missing_resource", "message": "resourceId is required"})
        unsupported = [value for value in offered if value not in OFFERINGS.get(family, [])]
        if unsupported:
            issues.append({"code": "unsupported_offering", "message": "Resource requests unsupported OmniSeed offerings", "offerings": unsupported})
        return {"valid": not issues, "issues": issues}

    def plan(self, action):
        validation = self.validate(action)
        return {
            "deterministic": True,
            "actionId": action.get("id"),
            "valid": validation["valid"],
            "issues": validation["issues"],
            "binding": {"companyId": self.company_id, "family": action.get("family"), "resourceId": action.get("resourceId")},
            "expectedEvidence": ["omniseed_projection_evidence"]
        }

    def apply(self, action):
        validation = self.validate(action)
        if not validation["valid"]:
            raise ProviderError("Action is invalid", "invalid_action", {"issues": validation["issues"]})
        attributes = {
            "companyId": self.company_id,
            "family": action["family"],
            "resourceId": action["resourceId"],
            "offers": list((action.get("desired") or {}).get("offers") or [])
        }
        return {"providerResourceId": f"omniseed://{self.company_id}/{action['family']}/{action['resourceId']}", "status": "bound", "attributes": attributes}

    @staticmethod
    def _resources(projection):
        resources = projection.get("resources") or []
        if isinstance(resources, dict):
            return [{**item, "family": family} for family, items in resources.items() for item in (items or [])]
        return resources

    def observe(self, resource):
        attributes = resource.get("attributes") or {}
        projection = self.projection()
        actual_company = projection.get("companyId") or (projection.get("company") or {}).get("id")
        match = next((item for item in self._resources(projection) if item.get("id") == attributes.get("resourceId") and item.get("family") == attributes.get("family")), None)
        checked = now()
        revision = self.projection_revision(projection)
        healthy = actual_company == self.company_id and revision == self.configuration.get("desiredRevision") and match is not None
        evidence = {
            "type": "omniseed_projection_evidence",
            "source": PROVIDER_ID,
            "companyId": actual_company,
            "family": attributes.get("family"),
            "resourceId": attributes.get("resourceId"),
            "resourcePresent": match is not None,
            "desiredRevision": revision,
            "revisionMatches": revision == self.configuration.get("desiredRevision"),
            "observedAt": checked
        }
        return {"status": "healthy" if healthy else "degraded", "checkedAt": checked, "providerResourceId": resource.get("providerResourceId"), "evidence": [evidence], "snapshot": evidence}

    def invoke(self, operation, input_value, actor):
        if operation not in OPERATIONS:
            raise ProviderError("Unsupported operation", "unsupported_operation", {"operation": operation})
        projection = self.projection()
        if operation == "engine.activity.inspect":
            return {"companyId": self.company_id, "activity": projection.get("history") or projection.get("activity") or []}
        return projection


def respond(request_id, result=None, error=None):
    message = {"jsonrpc": "2.0", "id": request_id}
    message["error" if error is not None else "result"] = error if error is not None else result
    sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def main():
    provider = OmniSeedProvider()
    for line in sys.stdin:
        try:
            request = json.loads(line)
            request_id = request.get("id")
            method = request.get("method")
            params = request.get("params") or {}
            try:
                if method == "provider.initialize": result = provider.initialize(params)
                elif method == "provider.status": result = provider.status()
                elif method == "provider.validate": result = provider.validate(params.get("action") or {})
                elif method == "provider.plan": result = provider.plan(params.get("action") or {})
                elif method == "provider.apply": result = provider.apply(params.get("action") or {})
                elif method == "provider.observe": result = provider.observe(params.get("resource") or {})
                elif method == "provider.invoke": result = provider.invoke(params.get("operation"), params.get("input"), params.get("actor"))
                elif method == "provider.shutdown": result = {"shutdown": True}
                else:
                    respond(request_id, error={"code": -32601, "message": "Method not found"})
                    continue
                respond(request_id, result=result)
            except ProviderError as error:
                respond(request_id, error={"code": -32000, "message": str(error), "data": {"code": error.code, **error.details}})
        except Exception as error:
            respond(None, error={"code": -32603, "message": "Internal error", "data": {"type": type(error).__name__}})


if __name__ == "__main__":
    main()
