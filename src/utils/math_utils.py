from decimal import Decimal
import math
from typing import Union
import numpy


def closest_divisor_below(x: Decimal, divisor: Decimal) -> Decimal:
    if x > 0:
        # Divide by 0.05 and take the floor
        closest_divisor = math.floor(x / divisor)
        # Multiply back by 0.05
        result = closest_divisor * divisor
    else:
        # Divide by 0.05 and take the ceil
        closest_divisor = math.ceil(x / divisor)
        # Multiply back by 0.05
        result = closest_divisor * divisor
    return result


def D(
    number: Union[float, Decimal, str], precision: Decimal = Decimal("0.0001")
) -> Decimal:
    if type(number) == numpy.int64 or type(number) == numpy.float64:  # type: ignore
        number = float(number)
    number = Decimal(number)
    if Decimal(number) == Decimal("Infinity") or Decimal(number) == Decimal(
        "-Infinity"
    ):
        return number
    value = Decimal("1") * Decimal(number).quantize(precision)
    return closest_divisor_below(value, precision)
