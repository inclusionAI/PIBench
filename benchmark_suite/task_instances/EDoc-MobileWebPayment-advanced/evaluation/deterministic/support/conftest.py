import os
import time
from dataclasses import dataclass

import pytest
import requests


@dataclass
class EdocClient:
    base_url: str

    def health(self):
        return requests.get(f"{self.base_url}/health.php", timeout=10)

    def login(self, email: str, password: str) -> requests.Session:
        session = requests.Session()
        response = session.post(
            f"{self.base_url}/login.php",
            data={"useremail": email, "userpassword": password},
            allow_redirects=False,
            timeout=10,
        )
        assert response.status_code in (302, 303), response.text[:500]
        return session

    def create_appointment(self, session: requests.Session, apponum: int = 801, promo_code: str = "") -> str:
        response = session.post(
            f"{self.base_url}/patient/booking-complete.php",
            data={
                "scheduleid": "1",
                "apponum": str(apponum),
                "date": time.strftime("%Y-%m-%d"),
                "promo_code": promo_code,
                "booknow": "Book and pay",
            },
            allow_redirects=False,
            timeout=10,
        )
        assert response.status_code in (302, 303), response.text[:500]
        location = response.headers.get("Location", "")
        assert "out_trade_no=" in location, location
        return location.split("out_trade_no=", 1)[1]

    def payment_entry(self, session: requests.Session, out_trade_no: str):
        return session.post(
            f"{self.base_url}/patient/alipay-h5/payment.php",
            data={"out_trade_no": out_trade_no},
            timeout=10,
        )

    def sync(self, session: requests.Session, out_trade_no: str, status: str = "TRADE_SUCCESS"):
        return session.post(
            f"{self.base_url}/patient/alipay-h5/sync.php",
            data={"out_trade_no": out_trade_no, "mock_trade_status": status},
            timeout=10,
        )

    def notify(self, expected_out_trade_no: str, **overrides):
        payload = {
            "app_id": "edoc-h5-sandbox-app",
            "seller_id": "edoc-clinic",
            "out_trade_no": expected_out_trade_no,
            "trade_no": f"MOCK{expected_out_trade_no}",
            "trade_status": "TRADE_SUCCESS",
            "total_amount": "99.00",
            "sign": "mock-valid",
            "sign_type": "RSA2",
        }
        payload.update(overrides)
        return requests.post(f"{self.base_url}/alipay/h5/notify.php", data=payload, timeout=10)

    def refund(self, admin: requests.Session, appoid: int, amount: str, request_no: str, **extra):
        payload = {"appoid": str(appoid), "amount": amount, "refund_request_no": request_no}
        payload.update(extra)
        return admin.post(f"{self.base_url}/admin/alipay-h5/refund.php", data=payload, timeout=10)

    def refund_query(self, admin: requests.Session, request_no: str):
        return admin.post(
            f"{self.base_url}/admin/alipay-h5/refund-query.php",
            data={"refund_request_no": request_no},
            timeout=10,
        )


@pytest.fixture(scope="session")
def base_url():
    return os.environ.get("EDOC_BASE_URL", "http://localhost:8136").rstrip("/")


@pytest.fixture(scope="session")
def client(base_url):
    client = EdocClient(base_url)
    for _ in range(30):
        try:
            if client.health().status_code == 200:
                return client
        except requests.RequestException:
            pass
        time.sleep(1)
    pytest.fail(f"service is not ready: {base_url}")


@pytest.fixture()
def patient(client):
    return client.login("patient@edoc.com", "123")


@pytest.fixture()
def admin(client):
    return client.login("admin@edoc.com", "123")
