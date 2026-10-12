from petmind.edge.agent import SensorAgent
from petmind.edge.players import create_music_player
from petmind.edge.players.youtube import YouTubeMusicPlayer
from petmind.edge.sensors import create_sensor_suite


def test_simulated_sensor_implements_shared_contract():
    sensors = create_sensor_suite("simulated", "test-device")
    snapshot = sensors.read()
    sensors.close()

    assert snapshot.device_id == "test-device"
    assert snapshot.source == "simulated"
    assert snapshot.valid is True
    assert snapshot.temperature is not None
    assert set(snapshot.to_api_payload()) == {
        "temperature",
        "humidity",
        "bark_detected",
        "bark_count",
        "bark_volume",
    }


def test_sensor_agent_dependencies_are_replaceable():
    class FakeSensors:
        name = "fake"
        closed = False

        def read(self):
            return create_sensor_suite("simulated", "fake").read()

        def close(self):
            self.closed = True

    class FakePublisher:
        published = []
        closed = False

        def publish(self, snapshot):
            self.published.append(snapshot)
            return {"id": 1}

        def close(self):
            self.closed = True

    sensors = FakeSensors()
    publisher = FakePublisher()
    SensorAgent(sensors, publisher).run(max_samples=1)

    assert len(publisher.published) == 1
    assert sensors.closed is True
    assert publisher.closed is True


def test_unknown_sensor_profile_is_rejected():
    try:
        create_sensor_suite("unknown")
    except ValueError as exc:
        assert "지원하지 않는" in str(exc)
    else:
        raise AssertionError("unknown profile must fail")


def test_simulated_music_player_is_replaceable():
    assert "calm_piano" in create_music_player("simulated").play("calm_piano")


def test_youtube_player_requires_allow_listed_video_id(monkeypatch):
    monkeypatch.delenv("PETMIND_YOUTUBE_CALM_PIANO_ID", raising=False)
    player = YouTubeMusicPlayer()
    try:
        player.play("calm_piano")
    except RuntimeError as exc:
        assert "PETMIND_YOUTUBE_CALM_PIANO_ID" in str(exc)
    else:
        raise AssertionError("missing video id must fail")
