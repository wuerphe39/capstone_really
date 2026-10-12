import time
import RPi.GPIO as GPIO

SERVO_PIN = 18
FREQ = 50

# MG996R: 0도=2.5%, 90도=7.5%, 180도=12.5%
DUTY_MIN = 2.5
DUTY_MAX = 12.5


class ServoMotor:
    def __init__(self, pin: int = SERVO_PIN):
        self.pin = pin
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.pin, GPIO.OUT)
        self.pwm = GPIO.PWM(self.pin, FREQ)
        self.pwm.start(0)
        self._angle = 0

    def _angle_to_duty(self, angle: float) -> float:
        return DUTY_MIN + (angle / 180.0) * (DUTY_MAX - DUTY_MIN)

    def set_angle(self, angle: float, delay: float = 0.5):
        angle = max(0, min(180, angle))
        self.pwm.ChangeDutyCycle(self._angle_to_duty(angle))
        time.sleep(delay)
        self.pwm.ChangeDutyCycle(0)  # 떨림 방지
        self._angle = angle

    def open_gate(self):
        self.set_angle(90)

    def close_gate(self):
        self.set_angle(0)

    def cleanup(self):
        self.pwm.stop()
        GPIO.cleanup(self.pin)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.cleanup()
