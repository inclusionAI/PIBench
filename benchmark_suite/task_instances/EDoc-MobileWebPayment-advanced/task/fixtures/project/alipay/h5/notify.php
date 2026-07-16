<?php
require_once __DIR__ . "/../../connection.php";
require_once __DIR__ . "/../../lib/payment_repository.php";

$params = request_data();
$outTradeNo = $params["out_trade_no"] ?? "";
$appointment = $outTradeNo ? appointment_by_trade($database, $outTradeNo) : null;
if (!$appointment) {
    http_response_code(400);
    echo "fail";
    exit;
}

[$valid, $reason] = validate_paid_notify($params, $appointment);
if (!$valid) {
    http_response_code(400);
    echo "fail";
    exit;
}

mark_appointment_paid($database, $appointment, $params["trade_no"] ?? ("MOCK" . $outTradeNo), $params);
echo "success";
?>
