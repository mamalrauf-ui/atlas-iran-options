"""
تست یکپارچه کل مسیر جدید: TSETMCProvider -> run_manual_sync ->
validator -> snapshot -> database -> sync_log.
از یک دیتابیس موقت استفاده می‌کند تا داده واقعی کاربر دست‌نخورده بماند.
"""
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import core.database as db
db.DB_PATH = Path(tempfile.NamedTemporaryFile(suffix=".db", delete=False).name)

from core.data.providers.tsetmc import TSETMCProvider  # noqa: E402
from core.data.sync import run_manual_sync  # noqa: E402
from core.live_data import TSETMC_OPTION_CHAIN_URL  # noqa: E402

SAMPLE_RECORD = {
    "insCode_P": "1", "insCode_C": "2", "contractSize": 1000, "uaInsCode": "9",
    "lVal18AFC_P": "طتست1", "lVal30_P": "اختيارف تست-1000-1405/09/01",
    "zTotTran_P": 5, "qTotTran5J_P": 50, "qTotCap_P": 1000.0, "notionalValue_P": 1000.0,
    "pClosing_P": 10, "priceYesterday_P": 11, "oP_P": 100, "pDrCotVal_P": 9,
    "lval30_UA": "تست", "pClosing_UA": 5000, "pDrCotVal_UA": 5010, "priceYesterday_UA": 4990,
    "beginDate": "20260101", "endDate": "20270101", "strikePrice": 1000, "remainedDay": 100,
    "pDrCotVal_C": 60, "oP_C": 200, "pClosing_C": 61, "priceYesterday_C": 59,
    "notionalValue_C": 2000.0, "qTotCap_C": 2000.0, "qTotTran5J_C": 80, "zTotTran_C": 8,
    "lVal30_C": "اختيارخ تست-1000-1405/09/01", "lVal18AFC_C": "ضتست1",
    "pMeDem_P": 8, "qTitMeDem_P": 10, "pMeOf_P": 11, "qTitMeOf_P": 10,
    "pMeDem_C": 60, "qTitMeDem_C": 5, "pMeOf_C": 62, "qTitMeOf_C": 5,
    "yesterdayOP_C": 190, "yesterdayOP_P": 95,
}


def _mock_response():
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"instrumentOptMarketWatch": [SAMPLE_RECORD]}
    resp.raise_for_status = MagicMock()
    return resp


def test_end_to_end_sync_and_save():
    provider = TSETMCProvider()
    with patch("core.live_data.requests.get", return_value=_mock_response()):
        result = run_manual_sync(provider, dataset_name="TEST_E2E")

    assert result["status"] == "SUCCESS", result
    assert result["snapshot_report"]["records_valid"] == 2  # یک Call + یک Put

    # داده واقعاً در دیتابیس موقت نشسته؟
    loaded = db.load_data(dataset_name="TEST_E2E")
    assert len(loaded) == 2
    assert set(loaded["option_type"]) == {"call", "put"}
    assert loaded["instrument_id"].notna().all()
    assert loaded["source"].iloc[0] == "TSETMC_LIVE"
    assert loaded["data_quality"].iloc[0] == "LIVE"

    # sync_log ثبت شده؟
    log = db.list_sync_log()
    assert len(log) >= 1
    assert log.iloc[0]["provider"] == "TSETMC_LIVE"
    assert log.iloc[0]["status"] == "SUCCESS"
    assert int(log.iloc[0]["records_valid"]) == 2

    db.delete_dataset("TEST_E2E")
    print("✅ End-to-end pipeline test passed")


if __name__ == "__main__":
    test_end_to_end_sync_and_save()
