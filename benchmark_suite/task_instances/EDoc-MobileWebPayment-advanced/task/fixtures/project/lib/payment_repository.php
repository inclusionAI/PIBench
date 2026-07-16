<?php

require_once __DIR__ . "/alipay_h5.php";

function json_response(array $payload, int $status = 200): void
{
    http_response_code($status);
    header("Content-Type: application/json");
    echo json_encode($payload, JSON_UNESCAPED_SLASHES);
    exit;
}

function request_data(): array
{
    $raw = file_get_contents("php://input");
    $json = json_decode($raw ?: "", true);
    return array_merge($_GET, $_POST, is_array($json) ? $json : []);
}

function require_patient(mysqli $database): array
{
    session_start();
    if (empty($_SESSION["user"]) || ($_SESSION["usertype"] ?? "") !== "p") {
        json_response(["error" => "patient_login_required"], 401);
    }
    $stmt = $database->prepare("SELECT * FROM patient WHERE pemail=?");
    $stmt->bind_param("s", $_SESSION["user"]);
    $stmt->execute();
    $row = $stmt->get_result()->fetch_assoc();
    if (!$row) {
        json_response(["error" => "patient_not_found"], 401);
    }
    return $row;
}

function require_admin(mysqli $database): array
{
    session_start();
    if (empty($_SESSION["user"]) || ($_SESSION["usertype"] ?? "") !== "a") {
        json_response(["error" => "admin_login_required"], 401);
    }
    $stmt = $database->prepare("SELECT * FROM admin WHERE aemail=?");
    $stmt->bind_param("s", $_SESSION["user"]);
    $stmt->execute();
    $row = $stmt->get_result()->fetch_assoc();
    if (!$row) {
        json_response(["error" => "admin_not_found"], 401);
    }
    return $row;
}

function money(float $amount): string
{
    return number_format($amount, 2, ".", "");
}

function appointment_by_trade(mysqli $database, string $outTradeNo): ?array
{
    $stmt = $database->prepare("SELECT * FROM appointment WHERE out_trade_no=?");
    $stmt->bind_param("s", $outTradeNo);
    $stmt->execute();
    return $stmt->get_result()->fetch_assoc() ?: null;
}

function appointment_by_id(mysqli $database, int $appoid): ?array
{
    $stmt = $database->prepare("SELECT * FROM appointment WHERE appoid=?");
    $stmt->bind_param("i", $appoid);
    $stmt->execute();
    return $stmt->get_result()->fetch_assoc() ?: null;
}

function payment_by_trade(mysqli $database, string $outTradeNo): ?array
{
    $stmt = $database->prepare("SELECT * FROM appointment_payment WHERE out_trade_no=? ORDER BY id DESC LIMIT 1");
    $stmt->bind_param("s", $outTradeNo);
    $stmt->execute();
    return $stmt->get_result()->fetch_assoc() ?: null;
}

function create_pending_appointment(mysqli $database, int $pid, int $apponum, int $scheduleid, string $date, string $promoCode = ""): array
{
    $baseAmount = 99.00;
    $discount = 0.00;
    if ($promoCode !== "") {
        $stmt = $database->prepare("SELECT discount_amount FROM promo_code WHERE code=? AND active=1");
        $stmt->bind_param("s", $promoCode);
        $stmt->execute();
        $promo = $stmt->get_result()->fetch_assoc();
        if ($promo) {
            $discount = min($baseAmount, (float) $promo["discount_amount"]);
        }
    }
    $amount = $baseAmount - $discount;
    $outTradeNo = "EDOC" . date("YmdHis") . random_int(1000, 9999);
    $appointmentStatus = "pending_payment";
    $paymentStatus = "pending";
    $currency = "CNY";
    $paidAmount = 0.00;
    $refundedAmount = 0.00;

    $stmt = $database->prepare(
        "INSERT INTO appointment(pid, apponum, scheduleid, appodate, appointment_status, payment_status, out_trade_no, amount, currency, discount_amount, paid_amount, refunded_amount, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NOW())"
    );
    $stmt->bind_param(
        "iiissssdsddd",
        $pid,
        $apponum,
        $scheduleid,
        $date,
        $appointmentStatus,
        $paymentStatus,
        $outTradeNo,
        $amount,
        $currency,
        $discount,
        $paidAmount,
        $refundedAmount
    );
    $stmt->execute();

    return appointment_by_id($database, (int) $database->insert_id);
}

function create_or_reuse_payment(mysqli $database, array $appointment): array
{
    $existing = payment_by_trade($database, $appointment["out_trade_no"]);
    if ($existing) {
        return $existing;
    }

    $handoffUrl = edoc_base_url() . "/patient/alipay-h5/pay.php?out_trade_no=" . rawurlencode($appointment["out_trade_no"]);
    $status = "pending";
    $provider = "alipay_h5";
    $raw = json_encode(["handoff_url" => $handoffUrl]);
    $stmt = $database->prepare(
        "INSERT INTO appointment_payment(appoid, out_trade_no, provider, amount, currency, status, payment_url, raw_response, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NOW())"
    );
    $amount = (float) $appointment["amount"];
    $stmt->bind_param("issdssss", $appointment["appoid"], $appointment["out_trade_no"], $provider, $amount, $appointment["currency"], $status, $handoffUrl, $raw);
    $stmt->execute();

    return payment_by_trade($database, $appointment["out_trade_no"]);
}

function mark_appointment_paid(mysqli $database, array $appointment, string $tradeNo, array $raw = []): array
{
    if (in_array($appointment["payment_status"], ["paid", "partially_refunded", "refunded"], true)) {
        return appointment_by_id($database, (int) $appointment["appoid"]);
    }

    $paidAmount = (float) $appointment["amount"];
    $paymentStatus = "paid";
    $appointmentStatus = "confirmed";
    $stmt = $database->prepare(
        "UPDATE appointment SET payment_status=?, appointment_status=?, paid_amount=?, alipay_trade_no=?, paid_at=NOW(), updated_at=NOW() WHERE appoid=?"
    );
    $stmt->bind_param("ssdsi", $paymentStatus, $appointmentStatus, $paidAmount, $tradeNo, $appointment["appoid"]);
    $stmt->execute();

    $rawText = json_encode($raw, JSON_UNESCAPED_SLASHES);
    $stmt = $database->prepare("UPDATE appointment_payment SET status='paid', trade_no=?, raw_response=?, updated_at=NOW() WHERE out_trade_no=?");
    $stmt->bind_param("sss", $tradeNo, $rawText, $appointment["out_trade_no"]);
    $stmt->execute();

    return appointment_by_id($database, (int) $appointment["appoid"]);
}

function update_payment_unknown(mysqli $database, array $appointment, array $raw): void
{
    $rawText = json_encode($raw, JSON_UNESCAPED_SLASHES);
    $stmt = $database->prepare("UPDATE appointment_payment SET status='unknown', raw_response=?, updated_at=NOW() WHERE out_trade_no=?");
    $stmt->bind_param("ss", $rawText, $appointment["out_trade_no"]);
    $stmt->execute();
}

function validate_paid_notify(array $params, array $appointment): array
{
    // TODO(q2-safety): verify signature and all critical fields before accepting.
    if (!in_array(($params["trade_status"] ?? ""), ["TRADE_SUCCESS", "TRADE_FINISHED"], true)) {
        return [false, "not_paid_status"];
    }
    return [true, "ok"];
}

function refundable_amount(array $appointment): float
{
    return max(0.0, (float) $appointment["paid_amount"] - (float) $appointment["refunded_amount"]);
}

function validate_refund_response(array $response, array $appointment, string $requestNo, float $amount): array
{
    // TODO(q2-safety): do not rely on code alone. Validate fund_change, request no,
    // refund amount, out_trade_no and trade_no before changing local accounting.
    if (($response["code"] ?? "") !== "10000") {
        return [false, "refund_code_not_success"];
    }
    return [true, "ok"];
}

function record_refund_result(mysqli $database, array $appointment, string $requestNo, float $amount, array $response): array
{
    $existing = null;
    $stmt = $database->prepare("SELECT * FROM appointment_refund WHERE refund_request_no=?");
    $stmt->bind_param("s", $requestNo);
    $stmt->execute();
    $existing = $stmt->get_result()->fetch_assoc();
    // TODO(q2-safety): make retry idempotent. This currently returns the old row
    // but callers may already have generated a new request number for the same action.
    if ($existing) {
        return $existing;
    }

    [$valid, $reason] = validate_refund_response($response, $appointment, $requestNo, $amount);
    $status = $valid ? "succeeded" : (($response["status"] ?? "") === "unknown" ? "unknown" : "failed");
    $fundChange = (($response["fund_change"] ?? "N") === "Y") ? 1 : 0;
    $raw = json_encode(["response" => $response, "reason" => $reason], JSON_UNESCAPED_SLASHES);
    $payment = payment_by_trade($database, $appointment["out_trade_no"]);
    $paymentId = $payment ? (int) $payment["id"] : null;

    $stmt = $database->prepare(
        "INSERT INTO appointment_refund(appoid, payment_id, refund_request_no, amount, status, fund_change, raw_response, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, NOW())"
    );
    $stmt->bind_param("iisdsis", $appointment["appoid"], $paymentId, $requestNo, $amount, $status, $fundChange, $raw);
    $stmt->execute();

    if ($valid) {
        $newRefunded = (float) $appointment["refunded_amount"] + $amount;
        $paymentStatus = money($newRefunded) >= money((float) $appointment["paid_amount"]) ? "refunded" : "partially_refunded";
        $appointmentStatus = $paymentStatus === "refunded" ? "cancelled" : $appointment["appointment_status"];
        $stmt = $database->prepare("UPDATE appointment SET refunded_amount=?, payment_status=?, appointment_status=?, updated_at=NOW() WHERE appoid=?");
        $stmt->bind_param("dssi", $newRefunded, $paymentStatus, $appointmentStatus, $appointment["appoid"]);
        $stmt->execute();
    }

    $stmt = $database->prepare("SELECT * FROM appointment_refund WHERE refund_request_no=?");
    $stmt->bind_param("s", $requestNo);
    $stmt->execute();
    return $stmt->get_result()->fetch_assoc();
}
?>
