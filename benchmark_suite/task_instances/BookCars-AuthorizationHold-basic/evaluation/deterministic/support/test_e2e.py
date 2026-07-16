#!/usr/bin/env python3
"""Playwright E2E tests for BookCars Alipay Preauthorization basic (E1-E2).

Checks that checkout flow renders a QR code with a real Alipay authorization entry.
"""
import json
import os
import sys
import time
from urllib.parse import urlparse

FRONTEND_URL = "http://localhost:9104"
TEST_USER_EMAIL = "driver1@bookcars.ma"
TEST_USER_PASSWORD = "B00kC4r5"

RESULTS = []


def record(rid, name, passed, message):
    RESULTS.append({
        "id": rid, "name": name,
        "type": "e2e",
        "passed": bool(passed),
        "score": 1 if passed else 0, "max_score": 1,
        "message": str(message)[:1000],
    })
    print(f"  [{'PASS' if passed else 'FAIL'}] {rid}: {name} -- {message[:200]}")


def load_test_ids(output_dir):
    path = os.path.join(output_dir, "test_ids.json")
    try:
        return json.loads(open(path).read())
    except (OSError, ValueError):
        return {}


def is_alipay_entry(value):
    if not isinstance(value, str):
        return False
    text = value.strip()
    if text.startswith("alipays://"):
        return True
    try:
        parsed = urlparse(text)
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and (parsed.hostname or "").lower() == "qr.alipay.com"
        and bool(parsed.path.strip("/"))
    )


QR_ELEMENT_SCRIPT = """() => {
    const visibleSize = (el) => {
        const rect = el.getBoundingClientRect();
        const width = rect.width || Number(el.getAttribute('width')) || el.naturalWidth || 0;
        const height = rect.height || Number(el.getAttribute('height')) || el.naturalHeight || 0;
        return { width, height };
    };
    const looksLargeEnough = (el) => {
        const { width, height } = visibleSize(el);
        return width >= 80 && height >= 80;
    };
    const hasQrHint = (el) => {
        const text = [
            el.getAttribute('aria-label'),
            el.getAttribute('title'),
            el.getAttribute('alt'),
            el.getAttribute('src'),
            el.getAttribute('data-value'),
            el.getAttribute('data-url'),
        ].filter(Boolean).join(' ');
        return /qr|qrcode|qr-code|alipay|alipays:\\/\\/|qr\\.alipay\\.com/i.test(text);
    };

    for (const svg of document.querySelectorAll('svg')) {
        const pathCount = svg.querySelectorAll('path, rect').length;
        if (looksLargeEnough(svg) && (pathCount >= 2 || hasQrHint(svg))) {
            return 'svg';
        }
    }
    for (const canvas of document.querySelectorAll('canvas')) {
        if (looksLargeEnough(canvas) || hasQrHint(canvas)) {
            return 'canvas';
        }
    }
    for (const img of document.querySelectorAll('img')) {
        if (hasQrHint(img) && looksLargeEnough(img)) {
            return 'img';
        }
    }
    return null;
}"""


def find_qr_payload(page):
    """Return (qr_found, desc, alipay_entry_payload)."""
    desc = page.evaluate(QR_ELEMENT_SCRIPT)

    payload = page.evaluate("""() => {
        const isAlipayEntry = (value) => {
            const text = String(value || '').trim();
            if (text.startsWith('alipays://')) return true;
            try {
                const url = new URL(text);
                return url.protocol === 'https:' && url.hostname === 'qr.alipay.com' && url.pathname.length > 1;
            } catch {
                return false;
            }
        };
        const el = document.querySelector('[data-value], [data-url]');
        if (el) {
            const v = el.getAttribute('data-value') || el.getAttribute('data-url');
            if (isAlipayEntry(v)) return v;
        }
        const html = document.documentElement.outerHTML;
        const candidates = [
            ...(html.match(/alipays:\\/\\/[^"'<>\\s\\\\]*/g) || []),
            ...(html.match(/https:\\/\\/qr\\.alipay\\.com\\/[^"'<>\\s\\\\]*/g) || []),
        ];
        return candidates.find(isAlipayEntry) || null;
    }""")
    return desc is not None, desc or "", payload


def find_alipay_entry_value(obj):
    """Find a valid Alipay authorization entry anywhere in a JSON-like object."""
    if isinstance(obj, dict):
        for key in ("schemeUrl", "scheme_url", "schemeURL", "url"):
            value = obj.get(key)
            if is_alipay_entry(value):
                return value
        for value in obj.values():
            found = find_alipay_entry_value(value)
            if found:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = find_alipay_entry_value(value)
            if found:
                return found
    elif is_alipay_entry(obj):
        return obj
    return None


def latest_freeze_payload(freeze_responses):
    for item in reversed(freeze_responses):
        payload = find_alipay_entry_value(item.get("json"))
        if payload:
            return payload
    return None


def select_alipay_payment(page):
    """Best-effort select an Alipay payment option if the checkout exposes one."""
    return page.evaluate("""() => {
        const textOf = (el) => [
            el.getAttribute && el.getAttribute('aria-label'),
            el.getAttribute && el.getAttribute('title'),
            el.getAttribute && el.getAttribute('value'),
            el.getAttribute && el.getAttribute('name'),
            el.id,
            el.innerText,
            el.textContent,
        ].filter(Boolean).join(' ');
        const isAlipay = (text) => /alipay|支付宝/i.test(text || '');

        const inputs = Array.from(document.querySelectorAll('input[type="radio"], input[type="checkbox"]'));
        for (const input of inputs) {
            const explicit = input.id
                ? Array.from(document.querySelectorAll('label')).find((label) => label.htmlFor === input.id)
                : null;
            const label = input.closest('label') || explicit || input.parentElement;
            const text = [textOf(input), label ? textOf(label) : ''].join(' ');
            if (!isAlipay(text)) continue;
            input.click();
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            return text.trim().slice(0, 120) || 'alipay input';
        }

        const controls = Array.from(document.querySelectorAll('button, [role="button"], label'));
        for (const el of controls) {
            const text = textOf(el);
            if (!isAlipay(text)) continue;
            el.click();
            return text.trim().slice(0, 120) || 'alipay control';
        }
        return '';
    }""")


def run_e2e(workspace, output_dir):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        msg = "INFRA: Playwright not installed"
        record("E1", "预订流程二维码", False, msg)
        record("E2", "二维码内容 alipays://", False, msg)
        return

    ids = load_test_ids(output_dir)
    car_id = ids.get("carId", "")
    loc_id = ids.get("locationId", "")

    e1_passed, e1_msg = False, ""
    e2_passed, e2_msg = False, ""
    freeze_responses = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            page = context.new_page()
            page.set_default_timeout(20000)

            def capture_freeze_response(response):
                if "/api/alipay/freeze" not in response.url:
                    return
                item = {"url": response.url, "status": response.status, "json": None, "error": ""}
                try:
                    item["json"] = response.json()
                except Exception as e:
                    item["error"] = str(e)
                freeze_responses.append(item)

            page.on("response", capture_freeze_response)

            # Sign in
            print("  E2E: signing in...")
            page.goto(f"{FRONTEND_URL}/sign-in", timeout=60000)
            page.wait_for_load_state("networkidle", timeout=30000)
            page.fill('input[type="email"], input[name="email"]', TEST_USER_EMAIL)
            page.fill('input[type="password"], input[name="password"]', TEST_USER_PASSWORD)
            page.click('button[type="submit"]')
            page.wait_for_load_state("networkidle", timeout=30000)
            time.sleep(2)
            page.screenshot(path=os.path.join(output_dir, "e2e_1_signin.png"))
            signin_failed = not page.evaluate("""() => !!window.localStorage.getItem('bc-fe-user')""")
            if signin_failed:
                error_text = page.evaluate("""() => {
                    const body = document.body ? document.body.innerText : '';
                    if (/incorrect email or password/i.test(body)) return 'Incorrect email or password';
                    if (/not allowed by cors/i.test(body)) return 'CORS blocked frontend origin';
                    return body.slice(0, 160);
                }""")
                e1_msg = f"Sign-in failed before checkout: {error_text}"
                e2_msg = e1_msg

            # Navigate to checkout
            checkout_loaded = False
            if signin_failed:
                pass
            elif car_id and loc_id:
                print("  E2E: navigating to checkout...")
                page.goto(f"{FRONTEND_URL}/", timeout=60000)
                page.wait_for_load_state("networkidle", timeout=30000)
                page.evaluate("""([carId, locId]) => {
                    const from = new Date(Date.now() + 86400000);
                    const to = new Date(Date.now() + 3 * 86400000);
                    const usr = { carId, pickupLocationId: locId, dropOffLocationId: locId, from, to };
                    const st = { usr, key: 'e2e-test', idx: (window.history.state && window.history.state.idx || 0) + 1 };
                    window.history.pushState(st, '', '/checkout');
                    window.dispatchEvent(new PopStateEvent('popstate', { state: st }));
                }""", [car_id, loc_id])
                try:
                    page.wait_for_selector(".checkout-form, form", timeout=30000)
                    checkout_loaded = True
                except Exception:
                    pass
                page.wait_for_load_state("networkidle", timeout=30000)
                time.sleep(2)
                selected = select_alipay_payment(page)
                if selected:
                    print(f"  E2E: selected Alipay option: {selected}")
                    page.wait_for_load_state("networkidle", timeout=30000)
                    time.sleep(1)
            else:
                page.goto(f"{FRONTEND_URL}/checkout", timeout=60000)
                page.wait_for_load_state("networkidle", timeout=30000)
                selected = select_alipay_payment(page)
                if selected:
                    print(f"  E2E: selected Alipay option: {selected}")
                    time.sleep(1)

            page.screenshot(path=os.path.join(output_dir, "e2e_2_checkout.png"))

            # Submit form
            if checkout_loaded:
                print("  E2E: submitting booking form...")
                try:
                    tos = page.query_selector('.checkout-tos input[type="checkbox"]')
                    if tos:
                        tos.check()
                    submit = page.query_selector('form button[type="submit"]')
                    if submit:
                        submit.click()
                except Exception as e:
                    print(f"  E2E: form issue: {e}")
                for _ in range(12):
                    time.sleep(5)
                    _, _, payload = find_qr_payload(page)
                    if payload or latest_freeze_payload(freeze_responses):
                        break
                page.screenshot(path=os.path.join(output_dir, "e2e_3_after_submit.png"))

            # Evaluate
            if not signin_failed:
                qr_found, qr_desc, payload = find_qr_payload(page)
                freeze_payload = latest_freeze_payload(freeze_responses)
                alipay_payload = payload or freeze_payload
                if is_alipay_entry(alipay_payload):
                    e1_passed = True
                    e1_msg = (
                        f"Alipay entry found: page_payload={'yes' if payload else 'no'}, "
                        f"freeze_payload={'yes' if freeze_payload else 'no'}, qr={qr_desc or 'none'}"
                    )
                else:
                    e1_msg = f"No valid Alipay entry found; qr={qr_desc or 'none'}"

                if is_alipay_entry(payload):
                    e2_passed = True
                    e2_msg = f"QR data contains valid Alipay entry: {payload[:80]}"
                elif is_alipay_entry(freeze_payload):
                    e2_passed = True
                    e2_msg = f"freeze response contains valid Alipay entry: {freeze_payload[:80]}"
                elif e1_passed:
                    e2_msg = "QR element found but no valid Alipay entry in DOM or freeze response"
                else:
                    e2_msg = "No QR found (E1 failed)"

            browser.close()
    except Exception as e:
        if not e1_msg:
            e1_msg = f"E2E error: {e}"
        if not e2_msg:
            e2_msg = f"E2E error: {e}"

    record("E1", "预订流程支付宝入口/二维码", e1_passed, e1_msg)
    record("E2", "二维码内容为支付宝预授权入口", e2_passed, e2_msg)


def main():
    workspace = sys.argv[1] if len(sys.argv) > 1 else "/workspace"
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "/output"

    run_e2e(workspace, output_dir)

    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "e2e_results.json"), "w") as f:
        json.dump(RESULTS, f, indent=2, ensure_ascii=False)

    passed_count = sum(1 for r in RESULTS if r["passed"])
    print(f"\nE2E tests: {passed_count}/{len(RESULTS)} passed")


if __name__ == "__main__":
    main()
