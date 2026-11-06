"""Offline regression for CVE-2026-49272; no OAuth endpoint is contacted."""
from importlib.metadata import version
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest
from oauthlib.common import Request
from oauthlib.oauth2 import RequestValidator
from oauthlib.oauth2.rfc6749.errors import InvalidGrantError, InvalidRequestError
from oauthlib.oauth2.rfc8628.grant_types import DeviceCodeGrant
from packaging.version import Version


class SyntheticDeviceValidator(RequestValidator):
    def client_authentication_required(self, request, *args, **kwargs):
        return False

    def authenticate_client_id(self, client_id, request, *args, **kwargs):
        request.client = SimpleNamespace(client_id=client_id)
        return True

    def validate_grant_type(self, client_id, grant_type, client, request, *args, **kwargs):
        return True

    def validate_device_code(self, client_id, code, request):
        if code == "synthetic-authorized":
            request.user = SimpleNamespace(id="synthetic-user")
            request.scopes = ["synthetic.read"]
            return DeviceCodeGrant.DEVICE_CODE_AUTHORIZED
        return None

    def validate_scopes(self, client_id, scopes, client, request, *args, **kwargs):
        return scopes == ["synthetic.read"]

    def get_default_scopes(self, client_id, request, *args, **kwargs):
        raise AssertionError("Device authorization must supply scopes; no default scope fallback")


def device_request(code):
    values = {"grant_type": "urn:ietf:params:oauth:grant-type:device_code", "client_id": "synthetic-client"}
    if code is not None:
        values["device_code"] = code
    return Request("https://synthetic.invalid/token", http_method="POST", body=urlencode(values))


def test_common_runtime_pins_and_installs_the_device_code_validation_fix():
    requirements = Path(__file__).resolve().parents[2] / "requirements" / "base.txt"
    assert "oauthlib==4.0.1" in requirements.read_text()
    assert Version(version("oauthlib")) >= Version("4.0.1")


@pytest.mark.parametrize("code,error", [(None, InvalidRequestError), ("synthetic-bogus", InvalidGrantError)])
def test_known_client_id_cannot_authorize_missing_or_unknown_device_code(code, error):
    with pytest.raises(error):
        DeviceCodeGrant(SyntheticDeviceValidator()).validate_token_request(device_request(code))


def test_authorized_device_keeps_its_stored_identity_and_scopes():
    request = device_request("synthetic-authorized")
    DeviceCodeGrant(SyntheticDeviceValidator()).validate_token_request(request)
    assert request.user.id == "synthetic-user"
    assert request.scopes == ["synthetic.read"]
