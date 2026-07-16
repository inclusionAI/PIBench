<?php
require_once __DIR__ . "/../../connection.php";
require_once __DIR__ . "/../../lib/payment_repository.php";

require_admin($database);
$data = request_data();
$requestNo = $data["refund_request_no"] ?? "";
if ($requestNo === "") {
    json_response(["error" => "refund_request_no_required"], 422);
}

$stmt = $database->prepare("SELECT r.*, a.out_trade_no, a.amount AS appointment_amount, a.payment_status FROM appointment_refund r INNER JOIN appointment a ON a.appoid=r.appoid WHERE r.refund_request_no=?");
$stmt->bind_param("s", $requestNo);
$stmt->execute();
$refund = $stmt->get_result()->fetch_assoc();
if (!$refund) {
    json_response(["error" => "refund_not_found"], 404);
}
$appointment = appointment_by_trade($database, $refund["out_trade_no"]);
$query = alipay_refund_query($appointment, $requestNo, isset($refund["amount"]) ? (float) $refund["amount"] : null);
json_response(["refund" => $refund, "query" => $query]);
?>
