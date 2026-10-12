from datetime import datetime, timedelta
from types import SimpleNamespace

import providers


def context(**overrides):
    data = {
        "observed_behavior": "resting",
        "behavior_confidence": 0.9,
        "behavior_duration_seconds": 25,
        "bark_detected": False,
        "bark_count": 0,
        "bark_volume": 0,
        "temperature": 24,
        "humidity": 50,
        "feed_remaining_g": 300,
        "feeding_due": False,
    }
    data.update(overrides)
    return data


def test_normal_rest_creates_informational_suggestion(client):
    response = client.post("/care/evaluate", json={"context": context()})
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "normal"
    assert body["recommended_actions"] == []
    assert body["status"] == "informational"


def test_health_reports_database_and_action_mode(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["components"]["database"] == "ok"
    assert body["components"]["action_mode"] == "simulation"


def test_anxious_barking_recommends_and_approves_music(client):
    response = client.post(
        "/care/evaluate",
        json={
            "context": context(
                observed_behavior="anxious",
                bark_detected=True,
                bark_count=5,
                bark_volume=0.8,
            )
        },
    )
    suggestion = response.json()
    assert suggestion["state"] == "possible_stress"
    assert suggestion["recommended_actions"] == ["music"]

    approved = client.post(
        f"/care/{suggestion['id']}/approve", json={"action_type": "music"}
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "completed"
    assert approved.json()["request"]["style"] == "calm_piano"
    assert "track" not in approved.json()["request"]


def test_feeding_suggestion_is_subject_to_cooldown(client):
    payload = context(
        observed_behavior="alert",
        feeding_due=True,
        last_feeding_at=(datetime.utcnow() - timedelta(hours=7)).isoformat(),
    )
    first = client.post("/care/evaluate", json={"context": payload}).json()
    approved = client.post(
        f"/care/{first['id']}/approve", json={"action_type": "feeding"}
    )
    assert approved.status_code == 200

    second = client.post("/care/evaluate", json={"context": payload}).json()
    blocked = client.post(
        f"/care/{second['id']}/approve", json={"action_type": "feeding"}
    )
    assert blocked.status_code == 409
    assert "대기시간" in blocked.json()["detail"]


def test_database_context_uses_recent_analysis_and_sensor(client):
    for _ in range(3):
        client.post(
            "/analysis/",
            json={
                "behavior": "anxious",
                "behavior_conf": 0.88,
                "emotion": "neutral",
                "emotion_conf": 0.55,
            },
        )
    client.post(
        "/sensors/",
        json={
            "temperature": 25,
            "humidity": 50,
            "feed_remaining_g": 200,
            "bark_detected": True,
            "bark_count": 4,
            "bark_volume": 0.7,
        },
    )
    response = client.post("/care/evaluate", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["context"]["observed_behavior"] == "anxious"
    assert body["context"]["bark_count"] == 4
    assert body["recommended_actions"] == ["music"]


def test_direct_feeding_requires_care_approval(client):
    response = client.post("/feeding/", json={"amount_g": 50, "triggered_by": "manual"})
    assert response.status_code == 403


def test_device_ack_completes_feeding_with_actual_amount(client):
    payload = context(feeding_due=True, feed_remaining_g=300)
    suggestion = client.post("/care/evaluate", json={"context": payload}).json()
    action = client.post(
        f"/care/{suggestion['id']}/approve", json={"action_type": "feeding"}
    ).json()
    response = client.post(
        f"/care/actions/{action['command_id']}/ack",
        json={"status": "completed", "actual_amount_g": 48.5},
    )
    assert response.status_code == 200
    assert response.json()["result"]["actual_amount_g"] == 48.5


def test_multiple_recommended_actions_can_be_approved_individually(client):
    payload = context(
        observed_behavior="anxious",
        bark_detected=True,
        bark_count=5,
        feeding_due=True,
        feed_remaining_g=300,
    )
    suggestion = client.post("/care/evaluate", json={"context": payload}).json()
    assert set(suggestion["recommended_actions"]) == {"music", "feeding"}

    music = client.post(
        f"/care/{suggestion['id']}/approve", json={"action_type": "music"}
    )
    assert music.status_code == 200
    assert client.get("/care/latest").json()["status"] == "partially_approved"

    feeding = client.post(
        f"/care/{suggestion['id']}/approve", json={"action_type": "feeding"}
    )
    assert feeding.status_code == 200
    assert client.get("/care/latest").json()["status"] == "approved"


def test_gemini_provider_parses_structured_feedback(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": """{
                                      "state": "possible_stress",
                                      "summary": "반복 짖음이 있어 주변 자극을 확인해 주세요.",
                                      "reasons": ["짖음이 5회 감지됐습니다."],
                                      "recommended_actions": ["music"],
                                      "music_style": "calm_piano",
                                      "severity": "warning"
                                    }"""
                                }
                            ]
                        }
                    }
                ]
            }

    monkeypatch.setattr(
        providers,
        "settings",
        SimpleNamespace(
            gemini_api_key="test-key",
            gemini_model="gemini-test",
            gemini_timeout_seconds=1,
            feeding_enabled=False,
        ),
    )
    monkeypatch.setattr(providers.requests, "post", lambda *args, **kwargs: FakeResponse())
    draft = providers.GeminiProvider().suggest(
        providers.PetContext(
            observed_behavior="anxious",
            behavior_confidence=0.9,
            bark_detected=True,
            bark_count=5,
        )
    )
    assert draft.state == "possible_stress"
    assert draft.recommended_actions == [providers.CareActionType.music]


def test_provider_failure_falls_back_to_rules(client, monkeypatch):
    import services.care as care_service

    class BrokenProvider:
        name = "broken-test"

        def suggest(self, _context):
            raise TimeoutError("test timeout")

    monkeypatch.setattr(care_service, "get_provider", lambda: BrokenProvider())
    response = client.post("/care/evaluate", json={"context": context()})
    assert response.status_code == 200
    assert response.json()["provider"] == "rule-fallback"
