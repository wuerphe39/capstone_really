import json
import paho.mqtt.publish as publish
from settings import settings

BROKER = settings.mqtt_broker
PORT = settings.mqtt_port

TOPIC_FEED   = "petmind/feeding/command"
TOPIC_STATUS = "petmind/status"
TOPIC_MUSIC  = "petmind/music/command"
TOPIC_ACK    = "petmind/actions/ack"


def _publish_json(topic: str, data: dict) -> bool:
    publish.single(
        topic,
        payload=json.dumps(data, ensure_ascii=False),
        hostname=BROKER,
        port=PORT,
    )
    return True


def publish_feed(command_id: str, amount_g: float) -> bool:
    """라파에 급식 명령 전송."""
    try:
        return _publish_json(TOPIC_FEED, {"command_id": command_id, "amount_g": amount_g})
    except Exception as e:
        print(f"[MQTT] 급식 명령 전송 실패: {e}")
        return False


def publish_music(command_id: str, style: str) -> bool:
    """라즈베리파이에 허용된 YouTube 음악 유형 재생 명령 전송."""
    try:
        return _publish_json(
            TOPIC_MUSIC,
            {"command_id": command_id, "style": style},
        )
    except Exception as e:
        print(f"[MQTT] 음악 명령 전송 실패: {e}")
        return False


def publish_status(data: dict):
    """분석 결과를 MQTT로 브로드캐스트."""
    try:
        return _publish_json(TOPIC_STATUS, data)
    except Exception as e:
        print(f"[MQTT] 상태 전송 실패: {e}")
        return False
