<?php
require_once __DIR__ . "/../../connection.php";
require_once __DIR__ . "/../../lib/payment_repository.php";

require_admin($database);
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
if (!in_array($appointment["payment_status"], ["paid", "partially_refunded"], true)) {
    json_response(["error" => "appointment_not_refundable", "payment_status" => $appointment["payment_status"]], 409);
}

$amount = isset($data["amount"]) ? (float) $data["amount"] : refundable_amount($appointment);
if ($amount <= 0 || $amount > refundable_amount($appointment)) {
    json_response(["error" => "invalid_refund_amount", "refundable_amount" => money(refundable_amount($appointment))], 422);
}
// TODO(q2-safety): same logical refund retry should reuse the same request number.
$requestNo = $data["refund_request_no"] ?? ("RF" . $appointment["out_trade_no"] . date("YmdHis") . random_int(100, 999));

$response = alipay_refund_trade($appointment, $requestNo, $amount, $data["mock_refund_status"] ?? null);
$refund = record_refund_result($database, $appointment, $requestNo, $amount, $response);
$updated = appointment_by_id($database, (int) $appointment["appoid"]);

json_response([
    "refund" => $refund,
    "appointment" => $updated,
    "refundable_amount" => money(refundable_amount($updated)),
]);
?>
