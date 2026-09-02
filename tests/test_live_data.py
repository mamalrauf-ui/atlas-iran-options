"""
تست واحد core/live_data.py با یک نمونه واقعی از پاسخ API رسمی TSETMC
(دقیقاً همان رکوردی که هنگام تست دستی از سایت دریافت شد).

این تست به اینترنت نیاز ندارد — requests.get را Mock می‌کند.
اجرا: python -m pytest tests/test_live_data.py -v
"""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import live_data  # noqa: E402

SAMPLE_RECORD = {
    "insCode_P": "52631478606575330",
    "insCode_C": "52724381011699987",
    "contractSize": 1000,
    "uaInsCode": "17914401175772326",
    "lVal18AFC_P": "طهرم6040",
    "lVal30_P": "اختيارف اهرم-26000-1405/06/25",
    "zTotTran_P": 67,
    "qTotTran5J_P": 22055,
    "qTotCap_P": 193549000.0,
    "notionalValue_P": 1298642510000.0,
    "pClosing_P": 9,
    "priceYesterday_P": 10,
    "oP_P": 129517,
    "pDrCotVal_P": 13,
    "lval30_UA": "اهرم",
    "pClosing_UA": 58889,
    "pDrCotVal_UA": 59032,
    "priceYesterday_UA": 56762,
    "beginDate": "20260620",
    "endDate": "20260916",
    "strikePrice": 26000,
    "remainedDay": 18,
    "pDrCotVal_C": 33110,
    "oP_C": 27671,
    "pClosing_C": 33006,
    "priceYesterday_C": 32346,
    "notionalValue_C": 25027825000.0,
    "qTotCap_C": 14027608000.0,
    "qTotTran5J_C": 425,
    "zTotTran_C": 53,
    "lVal30_C": "اختيارخ اهرم-26000-1405/06/25",
    "lVal18AFC_C": "ضهرم6040",
    "pMeDem_P": 8,
    "qTitMeDem_P": 3643,
    "pMeOf_P": 13,
    "qTitMeOf_P": 203,
    "pMeDem_C": 32001,
    "qTitMeDem_C": 2,
    "pMeOf_C": 33132,
    "qTitMeOf_C": 10,
    "yesterdayOP_C": 27828,
    "yesterdayOP_P": 128351,
}

# رکورد دوم با دارایی پایه متفاوت، برای تست فیلتر
SAMPLE_RECORD_OTHER_UA = dict(SAMPLE_RECORD)
SAMPLE_RECORD_OTHER_UA["lval30_UA"] = "خودرو"
SAMPLE_RECORD_OTHER_UA["lVal18AFC_C"] = "ضخود1234"
SAMPLE_RECORD_OTHER_UA["lVal18AFC_P"] = "طخود1234"


def _mock_response(records):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"instrumentOptMarketWatch": records}
    resp.raise_for_status = MagicMock()
    return resp


def test_fetch_option_chain_maps_fields_correctly():
    with patch("core.live_data.requests.get", return_value=_mock_response([SAMPLE_RECORD])):
        options_df, underlying_df, report = live_data.fetch_option_chain()

    assert len(options_df) == 2, "باید دقیقاً یک ردیف Call و یک ردیف Put تولید شود"
    assert report["call_count"] == 1
    assert report["put_count"] == 1
    assert report["skipped_rows"] == 0

    call_row = options_df[options_df["option_type"] == "call"].iloc[0]
    put_row = options_df[options_df["option_type"] == "put"].iloc[0]

    # --- بررسی نگاشت صحیح فیلدها ---
    assert call_row["symbol"] == "ضهرم6040"
    assert put_row["symbol"] == "طهرم6040"
    assert call_row["underlying"] == "اهرم"
    assert call_row["strike"] == 26000.0
    assert call_row["expiry"] == "2026-09-16"  # از endDate=20260916
    assert call_row["dte"] == 18
    assert call_row["close"] == 33006.0          # pClosing_C
    assert call_row["bid"] == 32001.0            # pMeDem_C
    assert call_row["ask"] == 33132.0            # pMeOf_C
    assert call_row["volume"] == 425.0           # qTotTran5J_C
    assert call_row["open_interest"] == 27671.0  # oP_C

    assert put_row["close"] == 9.0     # pClosing_P
    assert put_row["bid"] == 8.0       # pMeDem_P
    assert put_row["ask"] == 13.0      # pMeOf_P

    # Greeks/IV نباید ساخته شوند — باید None باشند تا core/pricing.py محاسبه‌شان کند
    assert call_row["iv"] is None
    assert call_row["delta"] is None

    # --- بررسی underlying_df ---
    assert len(underlying_df) == 1
    assert underlying_df.iloc[0]["underlying"] == "اهرم"
    assert underlying_df.iloc[0]["close"] == 58889.0  # pClosing_UA


def test_fetch_option_chain_filters_by_underlying():
    with patch("core.live_data.requests.get",
               return_value=_mock_response([SAMPLE_RECORD, SAMPLE_RECORD_OTHER_UA])):
        options_df, underlying_df, report = live_data.fetch_option_chain(underlying_filter="اهرم")

    assert report["underlyings_found"] == 1
    assert set(options_df["underlying"].unique()) == {"اهرم"}


def test_fetch_option_chain_no_filter_returns_all():
    with patch("core.live_data.requests.get",
               return_value=_mock_response([SAMPLE_RECORD, SAMPLE_RECORD_OTHER_UA])):
        options_df, underlying_df, report = live_data.fetch_option_chain()

    assert report["underlyings_found"] == 2
    assert set(options_df["underlying"].unique()) == {"اهرم", "خودرو"}


def test_fetch_raw_option_chain_raises_on_network_error():
    import requests as real_requests
    with patch("core.live_data.requests.get",
               side_effect=real_requests.exceptions.ConnectionError("boom")):
        try:
            live_data.fetch_raw_option_chain()
            assert False, "باید LiveDataError پرتاب شود"
        except live_data.LiveDataError:
            pass


def test_fetch_raw_option_chain_raises_on_empty_records():
    with patch("core.live_data.requests.get", return_value=_mock_response([])):
        try:
            live_data.fetch_raw_option_chain()
            assert False, "باید LiveDataError پرتاب شود چون هیچ رکوردی نیست"
        except live_data.LiveDataError:
            pass


if __name__ == "__main__":
    test_fetch_option_chain_maps_fields_correctly()
    test_fetch_option_chain_filters_by_underlying()
    test_fetch_option_chain_no_filter_returns_all()
    test_fetch_raw_option_chain_raises_on_network_error()
    test_fetch_raw_option_chain_raises_on_empty_records()
    print("همه تست‌ها موفق بودند ✅")
