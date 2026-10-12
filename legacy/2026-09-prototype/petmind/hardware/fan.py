import RPi.GPIO as GPIO

FAN_PIN = 24
TEMP_THRESHOLD = 28.0
HUMIDITY_THRESHOLD = 70.0


class CoolingFan:
    def __init__(self, pin: int = FAN_PIN):
        self.pin = pin
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.pin, GPIO.OUT)
        self._on = False

    def on(self):
        GPIO.output(self.pin, GPIO.HIGH)
        self._on = True

    def off(self):
        GPIO.output(self.pin, GPIO.LOW)
        self._on = False

    def auto_control(self, temperature: float, humidity: float):
        should_run = temperature > TEMP_THRESHOLD or humidity > HUMIDITY_THRESHOLD
        if should_run and not self._on:
            self.on()
        elif not should_run and self._on:
            self.off()

    @property
    def is_on(self) -> bool:
        return self._on

    def cleanup(self):
        self.off()
        GPIO.cleanup(self.pin)
