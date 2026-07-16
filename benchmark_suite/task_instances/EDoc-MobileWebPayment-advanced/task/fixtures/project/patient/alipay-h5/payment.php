<?php
require_once __DIR__ . "/../../connection.php";
require_once __DIR__ . "/../../lib/payment_repository.php";

$patient = require_patient($database);
$data = request_data();
$appointment = null;

if (!empty($data["out_trade_no"])) {
    $appointment = appointment_by_trade($database, $data["out_trade_no"]);
} elseif (!empty($data["appoid"])) {
    $appointment = appointment_by_id($database, (int) $data["appoid"]);
}

if (!$appointment || (int) $appointment["pid"] !== (int) $patient["pid"]) {
    json_response(["error" => "appointment_not_found"], 404);
}
if (!in_array($appointment["payment_status"], ["pending", "unknown"], true)) {
    json_response(["error" => "appointment_not_payable", "payment_status" => $appointment["payment_status"]], 409);
}

$payment = create_or_reuse_payment($database, $appointment);
json_response([
    "appoid" => (int) $appointment["appoid"],
    "out_trade_no" => $appointment["out_trade_no"],
    "amount" => money((float) $appointment["amount"]),
    "currency" => $appointment["currency"],
    "payment_url" => $payment["payment_url"],
    "payment_status" => $appointment["payment_status"],
]);
?>
