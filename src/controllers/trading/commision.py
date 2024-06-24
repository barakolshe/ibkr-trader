# type: ignore
from backtrader import CommInfoBase


class IBKRCommission(CommInfoBase):
    params = (
        ("stocklike", True),
        ("commtype", CommInfoBase.COMM_PERC),
        ("percabs", True),
    )

    def _getcommission(self, size, price, pseudoexec) -> float:
        """Calculates the commission of an operation at a given price

        pseudoexec: if True the operation has not yet been executed
        """
        return abs(0.005 * size)
