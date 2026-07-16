<?php
require_once __DIR__ . "/../../connection.php";
require_once __DIR__ . "/../../lib/payment_repository.php";

$data = request_data();
$appointment = null;
if (!empty($data["out_trade_no"])) {
    $appointment = appointment_by_trade($database, $data["out_trade_no"]);
} elseif (!empty($data["appoid"])) {
    $appointment = appointment_by_id($database, (int) $data["appoid"]);
}
if (!$appointment) {
    json_response(["error" => "appointment_not_found"], 404);
}
if (in_array($appointment["payment_status"], ["paid", "partially_refunded", "refunded"], true)) {
    json_response(["status" => $appointment["payment_status"], "appointment" => $appointment]);
}

$query = alipay_query_trade($appointment, $data["mock_trade_status"] ?? null);
if (($query["trade_status"] ?? "") === "TRADE_SUCCESS" || ($query["trade_status"] ?? "") === "TRADE_FINISHED") {
    if (money((float) $query["total_amount"]) !== money((float) $appointment["amount"])) {
        json_response(["error" => "amount_mismatch", "query" => $query], 422);
    }
    $updated = mark_appointment_paid($database, $appointment, $query["trade_no"], $query);
    json_response(["status" => "paid", "appointment" => $updated, "query" => $query]);
}

if (in_array(($query["trade_status"] ?? ""), ["WAIT_BUYER_PAY", "TRADE_CLOSED", "UNKNOWN"], true)) {
    update_payment_unknown($database, $appointment, $query);
    // TODO(q2-safety): unknown/processing states should stay pending and be retried.
    $database->query("UPDATE appointment SET payment_status='failed', appointment_status='cancelled', updated_at=NOW() WHERE appoid=" . (int) $appointment["appoid"]);
    json_response(["status" => "failed", "query" => $query], 200);
}

json_response(["status" => "pending", "query" => $query], 202);
?>
