from decimal import Decimal
from typing import Union


def D(
    number: Union[float, Decimal, str], precision: Decimal = Decimal("0.0000")
) -> Decimal:
    number = Decimal(number)
    if Decimal(number) == Decimal("Infinity") or Decimal(number) == Decimal(
        "-Infinity"
    ):
        return number
    return Decimal("1") * Decimal(number).quantize(precision)
