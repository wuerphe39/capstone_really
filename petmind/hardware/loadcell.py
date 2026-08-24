import time
import statistics
from hx711 import HX711

DOUT_PIN = 5
SCK_PIN = 6
REFERENCE_UNIT = 1  # 캘리브레이션 후 갱신


class LoadCell:
    def __init__(self, dout: int = DOUT_PIN, sck: int = SCK_PIN):
        self.hx = HX711(dout, sck)
        self.hx.set_reading_format("MSB", "MSB")
        self.hx.set_reference_unit(REFERENCE_UNIT)
        self.hx.reset()
        self.hx.tare()

    def calibrate(self, known_weight_g: float, samples: int = 20):
        readings = [self.hx.get_weight(5) for _ in range(samples)]
        avg = statistics.mean(readings)
        self.hx.set_reference_unit(avg / known_weight_g)
        print(f"Reference unit set: {avg / known_weight_g:.2f}")

    def read_weight(self, samples: int = 5) -> float:
        readings = [self.hx.get_weight(5) for _ in range(samples)]
        weight = statistics.median(readings)
        self.hx.power_down()
        self.hx.power_up()
        return max(0.0, weight)

    def tare(self):
        self.hx.tare()

    def cleanup(self):
        self.hx.power_down()
