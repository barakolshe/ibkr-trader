def round_decimal(number: float, precision: int = 4) -> float:
    number_string = str(number)
    parts = number_string.split(".")
    if len(parts) == 1:
        return number
    rounded_number = float(parts[0] + "." + parts[1][0:precision])
    return rounded_number
