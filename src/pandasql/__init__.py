import pathlib

import pandas as pd

from .sqldf import PandaSQL, PandaSQLException, sqldf

__all__ = ["PandaSQL", "PandaSQLException", "sqldf"]

_ROOT = pathlib.Path(__file__).absolute().parent


def get_data(path: str) -> pathlib.Path:
    return _ROOT.joinpath("data", path)


def load_meat() -> pd.DataFrame:
    filename = get_data("meat.csv")
    return pd.read_csv(filepath_or_buffer=filename, parse_dates=[0])


def load_births() -> pd.DataFrame:
    filename = get_data("births_by_month.csv")
    return pd.read_csv(filepath_or_buffer=filename, parse_dates=[0])
