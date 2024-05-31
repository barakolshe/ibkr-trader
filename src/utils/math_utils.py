from decimal import Decimal
from typing import Union
import numpy


def D(
    number: Union[float, Decimal, str], precision: Decimal = Decimal("0.0000")
) -> Decimal:
    if type(number) == numpy.int64 or type(number) == numpy.float64:  # type: ignore
        number = float(number)
    number = Decimal(number)
    if Decimal(number) == Decimal("Infinity") or Decimal(number) == Decimal(
        "-Infinity"
    ):
        return number
    return Decimal("1") * Decimal(number).quantize(precision)
