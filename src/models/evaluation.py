from datetime import datetime
from pathlib import Path
from typing import Optional
from consts.time_consts import TIMEZONE
from logger.logger import logger
import arrow
from pandas import DataFrame
import pandas as pd
from pydantic import BaseModel, ConfigDict
import os

from models.math import Extremum


class Evaluation(BaseModel):
    timestamp: datetime
    # score: Decimal
    symbol: str
    exchange: str
    url: str

    def get_csv_directory_path(self) -> str:
        return f"data/stocks/{self.symbol}"

    def get_csv_path(self, start_date: datetime, end_date: datetime) -> str:
        return f"{self.get_csv_directory_path()}/{arrow.get(start_date).format('YYYYMMDDHHmmss')}-{arrow.get(end_date).format('YYYYMMDDHHmmss')}.csv"

    def create_stock_directory(self) -> None:
        directory_path = self.get_csv_directory_path()
        if not os.path.exists(directory_path):
            os.makedirs(directory_path)

    def assume_csv_path(self) -> Optional[str]:
        for file in os.listdir(self.get_csv_directory_path()):
            return f"{self.get_csv_directory_path()}/{file}"
        return None

    def does_csv_file_exist(self) -> bool:
        try:
            for _ in os.listdir(self.get_csv_directory_path()):
                return True
            return False
        except:
            return False

    def is_stock_known_invalid(self) -> bool:
        for file in os.listdir(self.get_csv_directory_path()):
            return file == "INVALID"
        return False

    def get_csv_dates(self) -> tuple[Optional[datetime], Optional[datetime]]:
        for file in os.listdir(self.get_csv_directory_path()):
            path = Path(file)
            dates = path.stem.split("-")
            return (
                arrow.get(dates[0], "YYYYMMDDHHmmss", tzinfo=TIMEZONE).datetime,
                arrow.get(dates[1], "YYYYMMDDHHmmss", tzinfo=TIMEZONE).datetime,
            )
        return None, None

    def should_load_from_file(self, start_date: datetime, end_date: datetime) -> bool:
        arrow_start_date = arrow.get(start_date)
        arrow_end_date = arrow.get(end_date)
        for file in os.listdir(self.get_csv_directory_path()):
            file_start_date, file_end_date = self.get_csv_dates()
            if file_start_date is None or file_end_date is None:
                logger.error("Error getting csv dates")
                raise ValueError("Error getting csv dates")
            file_start_date_arrow = arrow.get(file_start_date)
            file_end_date_arrow = arrow.get(file_end_date)
            if (
                file_start_date_arrow <= arrow_start_date
                and file_end_date_arrow >= arrow_end_date.shift(hours=18)
            ):
                return True
        return False

    def load_df_from_csv(self) -> DataFrame:
        for file in os.listdir(self.get_csv_directory_path()):
            return pd.read_csv(
                f"{self.get_csv_directory_path()}/{file}",
                index_col="t",
                parse_dates=True,
            )
        raise ValueError("No file found")

    def save_invalid_stock(self) -> None:
        directory_path = self.get_csv_directory_path()
        if not os.path.exists(directory_path):
            os.makedirs(directory_path)
        with open(
            f"{directory_path}/INVALID",
            "w",
        ) as _:
            pass

    def save_to_csv(
        self, df: DataFrame, start_date: datetime, end_date: datetime
    ) -> None:
        existing_csv_path = None
        if self.does_csv_file_exist():
            existing_csv_path = self.assume_csv_path()
            if existing_csv_path is None:
                logger.error("Error getting csv path")
                raise ValueError("Error getting csv path")
            existing_data = pd.read_csv(
                existing_csv_path, index_col="t", parse_dates=True
            )
            existing_start_date, existing_end_date = self.get_csv_dates()
            if existing_start_date is None or existing_end_date is None:
                logger.error("Error getting csv dates")
                raise ValueError("Error getting csv dates")

            relevant_data = df[
                (df.index < existing_start_date) | (df.index > existing_end_date)
            ]
            joined_data = pd.concat([existing_data, relevant_data])
        else:
            joined_data = df

        curr_start_date = min(start_date, df.index[0])
        curr_end_date = max(end_date, df.index[-1])

        self.create_stock_directory()
        if existing_csv_path is not None:
            os.remove(existing_csv_path)
        with open(
            self.get_csv_path(curr_start_date, curr_end_date),
            "w",
        ) as file:
            joined_data.to_csv(
                file,
                index=True,
            )


class EvaluationResults(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    evaluation: Evaluation
    data: list[Extremum]
    df: DataFrame
