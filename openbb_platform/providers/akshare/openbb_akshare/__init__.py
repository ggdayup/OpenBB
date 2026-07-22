"""AKShare provider module for OpenBB Platform."""

from openbb_core.provider.abstract.provider import Provider
from openbb_akshare.models.equity_margin import AKShareEquityMarginFetcher

akshare_provider = Provider(
    name="akshare",
    website="https://akshare.akfamily.xyz",
    description="""AKShare is an open-source Financial Data Interface library built for Python,
providing comprehensive data for Chinese markets including A-shares, margin trading (两融), futures, etc.""",
    fetcher_dict={
        "ChinaEquityMargin": AKShareEquityMarginFetcher,
    },
    repr_name="AKShare",
)
