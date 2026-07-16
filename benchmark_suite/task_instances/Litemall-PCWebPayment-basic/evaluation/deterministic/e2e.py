#!/usr/bin/env python3
"""Playwright E2E tests E1-E2 for Alipay PC payment integration."""
import sys
import json
import os
import urllib.parse

WORKSPACE = sys.argv[1] if len(sys.argv) > 1 else "/workspace"
OUTPUT_DIR = sys.argv[2] if len(sys.argv) > 2 else "/output"
RESULTS_FILE = os.path.join(OUTPUT_DIR, "e2e_results.json")
BASE_URL = "http://localhost:8080"

results = []


def check_result(test_id, name, passed, evidence=""):
    status = "PASS" if passed else "FAIL"
    print(f"  {status}: [{test_id}] {name} -- {evidence[:200]}")
    results.append({"id": test_id, "name": name, "passed": passed, "evidence": evidence[:1000]})


def push_payment_route(page, order_id):
    page.goto(f"{BASE_URL}/vue/index.html")
    page.wait_for_selector("#app", timeout=10000)
    page.evaluate(
        """orderId => {
            const app = document.querySelector('#app') && document.querySelector('#app').__vue__;
            if (!app || !app.$router) {
                throw new Error('Vue root router not available');
            }
            return app.$router.push({ name: 'payment', params: { orderId } });
        }""",
        order_id,
    )
    page.wait_for_timeout(3000)


def set_payment_way_alipay(page):
    try:
        img = page.locator("img[src*='ali_pay']").first
        if img.is_visible():
            img.click()
            page.wait_for_timeout(300)
    except Exception:
        pass
    page.evaluate(
        """() => {
            const seen = new Set();
            function findPayment(vm) {
                if (!vm || seen.has(vm)) return null;
                seen.add(vm);
                if (vm.$options && vm.$options.name === 'payment') return vm;
                for (const child of (vm.$children || [])) {
                    const found = findPayment(child);
                    if (found) return found;
                }
                return null;
            }
            const root = document.querySelector('#app') && document.querySelector('#app').__vue__;
            const payment = findPayment(root);
            if (!payment) throw new Error('payment component not found');
            payment.payWay = 'ali';
        }"""
    )


def is_alipay_gateway_url(url):
    parsed = urllib.parse.urlparse(url or "")
    host = (parsed.hostname or "").lower()
    path = (parsed.path or "").lower()
    if host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        return False
    return (
        ("openapi-sandbox" in host and ("alipay" in host or "alipaydev" in host))
        or ((host.endswith("alipay.com") or host.endswith("alipaydev.com")) and "gateway.do" in path)
    )


def has_alipay_gateway_marker(text):
    lowered = (text or "").lower()
    return (
        "openapi-sandbox" in lowered
        or "alipaydev.com/gateway.do" in lowered
        or "alipay.com/gateway.do" in lowered
    )


def is_prepay_url(url):
    lowered = (url or "").lower()
    return "/order/alipay-prepay" in lowered or "/wx/order/alipay-prepay" in lowered


def is_navigation_in_progress_error(exc):
    lowered = str(exc).lower()
    return (
        "execution context was destroyed" in lowered
        or "page is navigating" in lowered
        or "page is navigating and changing the content" in lowered
        or "most likely because of a navigation" in lowered
    )


def run_tests():
    print("--- Playwright E2E Tests ---")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        check_result("E1", "Payment page shows Alipay option", False,
                     "INFRA: playwright not installed in image")
        check_result("E2", "Alipay payment redirect", False,
                     "INFRA: playwright not installed in image")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context()
        page = context.new_page()

        # ---- E1: login -> cart -> order -> payment page shows alipay option ----
        e1_passed = False
        e1_evidence = ""
        order_id = None
        try:
            resp = page.request.post(f"{BASE_URL}/wx/auth/login", data={
                "username": "user123", "password": "user123"})
            token = resp.json().get("data", {}).get("token", "")
            if not token:
                e1_evidence = f"Login failed: {resp.text()[:200]}"
            else:
                page.goto(f"{BASE_URL}/vue/index.html")
                page.evaluate(
                    "t => { localStorage.setItem('Authorization', t); "
                    "localStorage.setItem('token', t); }", token)

                page.request.post(f"{BASE_URL}/wx/cart/add", data={
                    "goodsId": 1006002, "productId": 7, "number": 1
                }, headers={"X-Litemall-Token": token})

                order_resp = page.request.post(f"{BASE_URL}/wx/order/submit", data={
                    "cartId": 0, "addressId": 1, "couponId": 0,
                    "grouponRulesId": 0, "message": "e2e"
                }, headers={"X-Litemall-Token": token})
                order_id = order_resp.json().get("data", {}).get("orderId")

                if order_id:
                    push_payment_route(page, order_id)
                    page.screenshot(path=os.path.join(OUTPUT_DIR, "e2e_payment_page.png"))
                    content = page.content()
                    if "支付宝" in content or "alipay" in content.lower() or "ali_pay" in content:
                        e1_passed = True
                        e1_evidence = "Payment page shows Alipay option"
                    else:
                        e1_evidence = "Payment page rendered but no Alipay option found (see e2e_payment_page.png)"
                else:
                    e1_evidence = f"Order creation failed: {order_resp.text()[:200]}"
        except Exception as e:
            e1_evidence = f"Error: {e}"
        check_result("E1", "Payment page shows Alipay option", e1_passed, e1_evidence)

        # ---- E2: select alipay -> pay -> redirect/form injection ----
        e2_passed = False
        e2_evidence = ""
        try:
            if e1_passed:
                set_payment_way_alipay(page)
                alipay_requests = []
                prepay_responses = []

                def on_request(request):
                    if is_alipay_gateway_url(request.url) and not is_prepay_url(request.url):
                        alipay_requests.append(request.url)

                def on_response(response):
                    if is_prepay_url(response.url):
                        prepay_responses.append(response)

                page.on("request", on_request)
                page.on("response", on_response)

                pay_btn = page.locator("text=去支付").first
                clicked = False
                if pay_btn.is_visible():
                    pay_btn.click()
                    clicked = True
                    try:
                        confirm = page.locator(".van-dialog__confirm").first
                        if confirm.is_visible(timeout=3000):
                            confirm.click()
                        else:
                            page.locator("text=确认").first.click(timeout=3000)
                    except Exception:
                        pass
                if clicked:
                    for _ in range(20):
                        if alipay_requests:
                            break
                        page.wait_for_timeout(250)

                prepay_status = None
                prepay_has_form = False
                for response in prepay_responses:
                    prepay_status = response.status
                    try:
                        body = response.text()
                    except Exception:
                        body = ""
                    lowered = body.lower()
                    if response.status == 200 and "<form" in lowered and has_alipay_gateway_marker(lowered):
                        prepay_has_form = True
                        break

                new_url = page.url
                if alipay_requests:
                    e2_passed = True
                    e2_evidence = f"Browser requested Alipay gateway: {alipay_requests[0]}"
                elif is_alipay_gateway_url(new_url):
                    e2_passed = True
                    e2_evidence = f"Redirected to alipay: {new_url}"
                else:
                    try:
                        forms = page.locator(
                            "form[action*='openapi-sandbox'], "
                            "form[action*='alipaydev.com/gateway.do'], "
                            "form[action*='alipay.com/gateway.do']"
                        ).count()
                        content = page.content()
                        if forms > 0:
                            e2_passed = True
                            e2_evidence = "Form with alipay action injected into page"
                        elif "<form" in content.lower() and has_alipay_gateway_marker(content):
                            e2_passed = True
                            e2_evidence = "Page contains alipay form after pay click"
                        else:
                            e2_evidence = (
                                f"No redirect or alipay form detected. URL: {new_url}, "
                                f"prepay_status={prepay_status}, prepay_has_form={prepay_has_form}"
                            )
                            page.screenshot(path=os.path.join(OUTPUT_DIR, "e2e_after_pay_click.png"))
                    except Exception as dom_exc:
                        if prepay_has_form and is_navigation_in_progress_error(dom_exc):
                            e2_passed = True
                            e2_evidence = (
                                "prepay returned Alipay form and page started navigation: "
                                f"{str(dom_exc)[:160]}"
                            )
                        else:
                            raise
            else:
                e2_evidence = "Skipped: E1 failed"
        except Exception as e:
            try:
                if is_alipay_gateway_url(page.url):
                    e2_passed = True
                    e2_evidence = f"Redirected to alipay: {page.url}"
                else:
                    e2_evidence = f"Error during E2: {e}"
            except Exception:
                e2_evidence = f"Error during E2: {e}"
        check_result("E2", "Alipay payment redirect", e2_passed, e2_evidence)

        browser.close()

    passed = sum(1 for r in results if r["passed"])
    print(f"\nE2E tests: {passed} passed, {len(results) - passed} failed out of {len(results)}")


if __name__ == "__main__":
    try:
        run_tests()
    finally:
        with open(RESULTS_FILE, "w") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
