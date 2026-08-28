import os
import paho.mqtt.publish as publish

BROKER = os.getenv("MQTT_BROKER", "localhost")
PORT   = int(os.getenv("MQTT_PORT", 1883))

TOPIC_FEED   = "petmind/feeding/command"
TOPIC_STATUS = "petmind/status"


def publish_feed(amount_g: float):
    """라파에 급식 명령 전송."""
    try:
        publish.single(
            TOPIC_FEED,
            payload=str(amount_g),
            hostname=BROKER,
            port=PORT,
        )
    except Exception as e:
        print(f"[MQTT] 급식 명령 전송 실패: {e}")


def publish_status(data: dict):
    """분석 결과를 MQTT로 브로드캐스트."""
    import json
    try:
        publish.single(
            TOPIC_STATUS,
            payload=json.dumps(data),
            hostname=BROKER,
            port=PORT,
        )
    except Exception as e:
        print(f"[MQTT] 상태 전송 실패: {e}")
