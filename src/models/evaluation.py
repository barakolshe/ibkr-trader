from datetime import datetime
from pathlib import Path
from typing import Generator, Literal, Optional, Union
from consts.time_consts import TIMEZONE
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
    state: Union[
        Literal["Acquirer"],
        Literal["Acquiring"],
        Literal["Target"],
        Literal["Acquired"],
        Literal["Merging"],
        Literal["Other"],
    ]
    url: str

    def is_target(self) -> bool:
        return self.state == "Target" or self.state == "Acquired"

    def is_acquirer(self) -> bool:
        return self.state == "Acquirer" or self.state == "Acquiring"

    def is_merging(self) -> bool:
        return self.state == "Merging"

    def get_csv_directory_path(self) -> str:
        return f"data/stocks/{self.symbol}"

    def create_csv_path(self, start_date: datetime, end_date: datetime) -> str:
        return f"{self.get_csv_directory_path()}/{arrow.get(start_date).format('YYYYMMDDHHmmss')}-{arrow.get(end_date).format('YYYYMMDDHHmmss')}.csv"

    def create_stock_directory(self) -> None:
        directory_path = self.get_csv_directory_path()
        if not os.path.exists(directory_path):
            os.makedirs(directory_path)

    def get_all_existing_csv_files(self) -> Generator[str, None, None]:
        for file in os.listdir(self.get_csv_directory_path()):
            yield f"{self.get_csv_directory_path()}/{file}"

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

    def get_csv_dates(self, csv_path: str) -> tuple[datetime, datetime]:
        path = Path(csv_path)
        dates = path.stem.split("-")
        return (
            arrow.get(dates[0], "YYYYMMDDHHmmss", tzinfo=TIMEZONE).datetime,
            arrow.get(dates[1], "YYYYMMDDHHmmss", tzinfo=TIMEZONE).datetime,
        )

    def get_matching_csv(
        self, start_date: datetime, end_date: datetime
    ) -> Optional[str]:
        arrow_start_date = arrow.get(start_date)
        arrow_end_date = arrow.get(end_date)
        for file_name in self.get_all_existing_csv_files():
            file_start_date, file_end_date = self.get_csv_dates(file_name)
            file_start_date_arrow = arrow.get(file_start_date)
            file_end_date_arrow = arrow.get(file_end_date)
            if (
                file_start_date_arrow <= arrow_start_date
                and file_end_date_arrow
                >= min(
                    arrow_end_date.shift(hours=18),
                    arrow.now(tz=TIMEZONE).shift(hours=-2),
                )
            ):
                return file_name
        return None

    def load_df_from_csv(self, csv_file_path: str) -> DataFrame:
        return pd.read_csv(
            csv_file_path,
            index_col="t",
            parse_dates=True,
        )

    def save_invalid_stock(self) -> None:
        directory_path = self.get_csv_directory_path()
        if not os.path.exists(directory_path):
            os.makedirs(directory_path)
        with open(
            f"{directory_path}/INVALID",
            "w",
        ) as _:
            pass

        if len(list(self.get_all_existing_csv_files())) >= 2:
            raise Exception(f"Invalid and valid at the same time {self.symbol}")

    def _get_relevant_data(
        self,
        df: DataFrame,
        existing_data: DataFrame,
        start_date: datetime,
        end_date: datetime,
        existing_start_date: datetime,
        existing_end_date: datetime,
    ) -> DataFrame:

        if self._should_create_new_csv(
            start_date,
            end_date,
            existing_start_date,
            existing_end_date,
        ):
            relevant_data = df[
                (df.index < existing_start_date) | (df.index > existing_end_date)
            ]
            joined_data = pd.concat([existing_data, relevant_data])

            return joined_data
        else:
            return df

    def _should_create_new_csv(
        self,
        start_date: datetime,
        end_date: datetime,
        existing_start_date: datetime,
        existing_end_date: datetime,
    ) -> bool:
        return (
            (existing_start_date >= start_date and existing_start_date <= end_date)
            or (existing_end_date >= start_date and existing_end_date <= end_date)
            or (start_date >= existing_start_date and start_date <= existing_end_date)
            or (end_date >= existing_start_date and end_date <= existing_end_date)
        )

    def _replace_csv(
        self,
        df: DataFrame,
        existing_csv_path: str,
        start_date: datetime,
        end_date: datetime,
    ) -> tuple[datetime, datetime]:
        existing_start_date, existing_end_date = self.get_csv_dates(existing_csv_path)
        target_start_date = min(start_date, existing_start_date, df.index[0])
        target_end_date = max(end_date, existing_end_date, df.index[-1])

        os.remove(existing_csv_path)
        df.to_csv(
            self.create_csv_path(target_start_date, target_end_date),
            index=True,
        )
        return (target_start_date, target_end_date)

    def _save_new_csv(
        self, df: DataFrame, start_date: datetime, end_date: datetime
    ) -> None:
        target_start_date = min(start_date, df.index[0])
        target_end_date = max(end_date, df.index[-1])

        self.create_stock_directory()
        df.to_csv(
            self.create_csv_path(target_start_date, target_end_date),
            index=True,
        )

    def save_to_csv(
        self, df: DataFrame, start_date: datetime, end_date: datetime
    ) -> None:
        was_ever_replaced = False
        replaced = True
        self.create_stock_directory()
        while replaced:
            for csv_file_path in self.get_all_existing_csv_files():
                existing_start_date, existing_end_date = self.get_csv_dates(
                    csv_file_path
                )
                if self._should_create_new_csv(
                    start_date,
                    end_date,
                    existing_start_date,
                    existing_end_date,
                ):
                    existing_data = pd.read_csv(
                        csv_file_path, index_col="t", parse_dates=True
                    )
                    df = self._get_relevant_data(
                        df,
                        existing_data,
                        start_date,
                        end_date,
                        existing_start_date,
                        existing_end_date,
                    )
                    start_date, end_date = self._replace_csv(
                        df, csv_file_path, start_date, end_date
                    )
                    replaced = True
                    was_ever_replaced = True
                    break

            replaced = False
        if not was_ever_replaced:
            self._save_new_csv(df, start_date, end_date)


class TestEvaluationResults(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    evaluation: Evaluation
    df: DataFrame


class EvaluationResults(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    evaluation: Evaluation
    data: list[Extremum]
    df: DataFrame
    duration: int
