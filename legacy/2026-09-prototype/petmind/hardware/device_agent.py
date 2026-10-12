"""Raspberry Pi MQTT action worker.

The backend publishes commands, while this process owns hardware access and reports
acknowledged/completed/failed states to the backend. Set PETMIND_DEVICE_SIMULATE=true
to exercise the same flow without GPIO hardware.
"""

import json
import os
import time

import paho.mqtt.client as mqtt
import requests

from petmind.edge.players import create_music_player


BROKER = os.getenv("MQTT_BROKER", "localhost")
PORT = int(os.getenv("MQTT_PORT", "1883"))
API_BASE = os.getenv("PETMIND_API_BASE", "http://localhost:8000").rstrip("/")
SIMULATE = os.getenv("PETMIND_DEVICE_SIMULATE", "false").lower() == "true"
MUSIC_PLAYER = create_music_player(
    "simulated" if SIMULATE else os.getenv("PETMIND_MUSIC_PLAYER", "youtube")
)

FEED_TOPIC = "petmind/feeding/command"
MUSIC_TOPIC = "petmind/music/command"


def report(command_id: str, status: str, **extra) -> None:
    response = requests.post(
        f"{API_BASE}/care/actions/{command_id}/ack",
        json={"status": status, **extra},
        timeout=5,
    )
    response.raise_for_status()


def run_feeding(amount_g: float) -> float:
    if SIMULATE:
        time.sleep(0.3)
        return amount_g

    from petmind.hardware.loadcell import LoadCell
    from petmind.hardware.servo import ServoMotor

    with ServoMotor() as servo:
        scale = LoadCell()
        try:
            start = scale.read_weight()
            servo.open_gate()
            deadline = time.monotonic() + 15
            actual = 0.0
            while time.monotonic() < deadline:
                actual = max(0.0, scale.read_weight() - start)
                if actual >= amount_g:
                    break
                time.sleep(0.15)
            servo.close_gate()
            if actual < amount_g * 0.8:
                raise RuntimeError(f"목표 급식량 미달: {actual:.1f}g / {amount_g:.1f}g")
            return actual
        finally:
            scale.cleanup()


def run_music(style: str) -> str:
    return MUSIC_PLAYER.play(style)


def on_connect(client, _userdata, _flags, reason_code, _properties=None):
    if reason_code != 0:
        print(f"[device] MQTT 연결 실패: {reason_code}")
        return
    client.subscribe([(FEED_TOPIC, 1), (MUSIC_TOPIC, 1)])
    print("[device] MQTT 명령 대기 중")


def on_message(_client, _userdata, message):
    command_id = ""
    try:
        payload = json.loads(message.payload.decode("utf-8"))
        command_id = str(payload["command_id"])
        report(command_id, "acknowledged")
        if message.topic == FEED_TOPIC:
            actual = run_feeding(float(payload["amount_g"]))
            report(command_id, "completed", actual_amount_g=actual)
        elif message.topic == MUSIC_TOPIC:
            detail = run_music(str(payload["style"]))
            report(command_id, "completed", detail=detail)
    except Exception as exc:
        print(f"[device] 명령 실패: {exc}")
        if command_id:
            try:
                report(command_id, "failed", detail=str(exc))
            except Exception as report_exc:
                print(f"[device] 실패 보고 오류: {report_exc}")


def main() -> None:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER, PORT, keepalive=60)
    client.loop_forever()


if __name__ == "__main__":
    main()
