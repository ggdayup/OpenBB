"""AKShare Equity Margin Trading Model for OpenBB Platform."""

import datetime as dt
from datetime import datetime
from typing import Any, Optional
import akshare as ak
from pandas import DataFrame
from pydantic import Field

from openbb_core.provider.abstract.data import Data
from openbb_core.provider.abstract.fetcher import Fetcher
from openbb_core.provider.abstract.query_params import QueryParams
from openbb_core.provider.utils.errors import EmptyDataError


class AKShareEquityMarginQueryParams(QueryParams):
    """AKShare Equity Margin Trading Query Parameters."""

    start_date: Optional[dt.date] = Field(
        default=None,
        description="Start date for margin trading data (YYYY-MM-DD or YYYYMMDD).",
    )
    end_date: Optional[dt.date] = Field(
        default=None,
        description="End date for margin trading data (YYYY-MM-DD or YYYYMMDD).",
    )


class AKShareEquityMarginData(Data):
    """AKShare Equity Margin Trading Data Output."""

    date: dt.date = Field(description="Trading date.")
    margin_balance: float = Field(description="Margin balance in RMB (融资余额).")
    margin_buy_amount: float = Field(description="Margin buy amount in RMB (融资买入额).")
    short_balance_amount: float = Field(description="Short selling balance in RMB (融券余量金额).")
    short_sell_volume: float = Field(description="Short selling volume in shares (融券卖出量).")
    total_margin_balance: float = Field(description="Total margin trading balance in RMB (融资融券余额).")


class AKShareEquityMarginFetcher(
    Fetcher[
        AKShareEquityMarginQueryParams,
        list[AKShareEquityMarginData],
    ]
):
    """AKShare Equity Margin Trading Fetcher."""

    @staticmethod
    def transform_query(params: dict[str, Any]) -> AKShareEquityMarginQueryParams:
        """Transform input query parameters."""
        return AKShareEquityMarginQueryParams(**params)

    @staticmethod
    def extract_data(
        query: AKShareEquityMarginQueryParams,
        credentials: Optional[dict[str, str]] = None,
        **kwargs: Any,
    ) -> DataFrame:
        """Extract margin trading data using AKShare."""
        today = datetime.now().date()
        start = query.start_date.strftime("%Y%m%d") if query.start_date else (today - dt.timedelta(days=365 * 5)).strftime("%Y%m%d")
        end = query.end_date.strftime("%Y%m%d") if query.end_date else today.strftime("%Y%m%d")

        try:
            df = ak.stock_margin_sse(start_date=start, end_date=end)
        except Exception as e:
            raise EmptyDataError(f"Error fetching AKShare margin data: {e}")

        if df.empty:
            raise EmptyDataError("No margin trading data returned from AKShare.")

        return df

    @staticmethod
    def transform_data(
        query: AKShareEquityMarginQueryParams,
        data: DataFrame,
        **kwargs: Any,
    ) -> list[AKShareEquityMarginData]:
        """Transform raw DataFrame into OpenBB Data models."""
        results: list[AKShareEquityMarginData] = []
        for _, row in data.iterrows():
            d_str = str(row["信用交易日期"])
            d_val = datetime.strptime(d_str, "%Y%m%d").date()
            results.append(
                AKShareEquityMarginData(
                    date=d_val,
                    margin_balance=float(row["融资余额"]),
                    margin_buy_amount=float(row["融资买入额"]),
                    short_balance_amount=float(row["融券余量金额"]),
                    short_sell_volume=float(row["融券卖出量"]),
                    total_margin_balance=float(row["融资融券余额"]),
                )
            )
        return results
