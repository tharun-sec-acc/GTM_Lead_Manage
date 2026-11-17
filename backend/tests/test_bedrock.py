import json
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError, NoCredentialsError

from app import bedrock


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(bedrock.settings, "aws_region", "us-east-1")
    monkeypatch.setattr(bedrock.settings, "bedrock_model_id", "test-model")


def test_fenced_json_generates_threaded_drafts(configured, monkeypatch):
    emails = [{"subject": "Introduction", "body": "Hello."}, {"subject": "Follow-up", "body": "Following up."}]
    calls = []

    def converse(**kwargs):
        calls.append(kwargs)
        return {"stopReason": "end_turn", "output": {"message": {
            "content": [{"text": f"```json\n{json.dumps({'emails': emails})}\n```"}],
        }}}

    monkeypatch.setattr(bedrock.boto3, "client", lambda *args, **kwargs: SimpleNamespace(converse=converse))
    result = bedrock.generate_sequence("Example", "Approved product facts", 2)
    assert result[1]["subject"] == "Re: Introduction"
    assert calls[0]["modelId"] == "test-model"


def test_explicit_profile_is_used_without_changing_server_default(configured, monkeypatch):
    calls = []

    def converse(**kwargs):
        calls.append(kwargs)
        return {"output": {"message": {"content": [{"text": json.dumps({
            "emails": [{"subject": "Introduction", "body": "Hello."}],
        })}]}}}

    monkeypatch.setattr(bedrock.boto3, "client", lambda *args, **kwargs: SimpleNamespace(converse=converse))
    bedrock.generate_sequence("Example", "Approved facts", 1, inference_profile_id="approved-profile")
    assert calls[0]["modelId"] == "approved-profile"
    assert bedrock.settings.bedrock_model_id == "test-model"


def test_model_rejecting_temperature_uses_default_sampling(configured, monkeypatch):
    def converse(**kwargs):
        if "temperature" in kwargs["inferenceConfig"]:
            raise ClientError({"Error": {
                "Code": "ValidationException", "Message": "temperature is deprecated for this model",
            }}, "Converse")
        return {"output": {"message": {"content": [{"text": '{"ok": true}'}]}}}

    monkeypatch.setattr(bedrock.boto3, "client", lambda *args, **kwargs: SimpleNamespace(converse=converse))
    assert bedrock.converse_json(
        "Return JSON.", {}, model_id="us.anthropic.claude-sonnet-5-5",
    ) == {"ok": True}


def test_inference_profile_discovery_preserves_pagination_and_routing_regions(configured, monkeypatch):
    calls = []

    def profiles(**kwargs):
        calls.append(kwargs)
        return {"inferenceProfileSummaries": [{
            "inferenceProfileId": "profile-1", "inferenceProfileArn": "profile-arn",
            "inferenceProfileName": "Approved profile", "type": "SYSTEM_DEFINED", "status": "ACTIVE",
            "models": [
                {"modelArn": "arn:aws:bedrock:us-east-1::foundation-model/test"},
                {"modelArn": "arn:aws:bedrock:us-west-2::foundation-model/test"},
            ],
        }], "nextToken": "next-page"}

    monkeypatch.setattr(bedrock.boto3, "client", lambda *args, **kwargs: SimpleNamespace(list_inference_profiles=profiles))
    result = bedrock.list_inference_profiles("previous-page")
    assert calls == [{"maxResults": 100, "nextToken": "previous-page"}]
    assert result["next_token"] == "next-page"
    assert result["profiles"][0]["regions"] == ["us-east-1", "us-west-2"]


@pytest.mark.parametrize("code,hint", [
    ("AccessDeniedException", "bedrock:InvokeModel"),
    ("ValidationException", "inference profile"),
    ("ExpiredTokenException", "expired"),
    ("ThrottlingException", "quotas"),
])
def test_aws_errors_are_actionable_without_echoing_service_payload(configured, monkeypatch, code, hint):
    def converse(**kwargs):
        raise ClientError({"Error": {"Code": code, "Message": "Sensitive provider details"}}, "Converse")

    monkeypatch.setattr(bedrock.boto3, "client", lambda *args, **kwargs: SimpleNamespace(converse=converse))
    with pytest.raises(RuntimeError) as error:
        bedrock.generate_sequence("Example", "Approved facts", 1)
    assert hint in str(error.value)
    assert "Sensitive provider details" not in str(error.value)


def test_missing_credentials_are_reported(configured, monkeypatch):
    def missing(*args, **kwargs):
        raise NoCredentialsError()

    monkeypatch.setattr(bedrock.boto3, "client", missing)
    with pytest.raises(RuntimeError, match="credentials are missing"):
        bedrock.generate_sequence("Example", "Approved facts", 1)


@pytest.mark.parametrize("response,expected", [
    ({"stopReason": "max_tokens"}, "truncated"),
    ({"stopReason": "guardrail_intervened"}, "blocked"),
    ({"output": {"message": {"content": [{"text": "No JSON here"}]}}}, "invalid JSON"),
])
def test_incomplete_or_invalid_model_output_is_not_a_success(configured, monkeypatch, response, expected):
    monkeypatch.setattr(bedrock.boto3, "client", lambda *args, **kwargs: SimpleNamespace(
        converse=lambda **params: response,
    ))
    with pytest.raises(RuntimeError, match=expected):
        bedrock.generate_sequence("Example", "Approved facts", 1)
