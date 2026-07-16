<?php
require_once __DIR__ . "/../../connection.php";
require_once __DIR__ . "/../../lib/payment_repository.php";

$outTradeNo = $_GET["out_trade_no"] ?? "";
$appointment = $outTradeNo ? appointment_by_trade($database, $outTradeNo) : null;
if ($appointment && $appointment["payment_status"] === "pending") {
    // TODO(q2-safety): quit_url only means the user left the cashier; do not fail terminally.
    $database->query("UPDATE appointment SET payment_status='failed', appointment_status='cancelled', updated_at=NOW() WHERE appoid=" . (int) $appointment["appoid"]);
    $appointment = appointment_by_trade($database, $outTradeNo);
}
?>
<!doctype html>
<html>
<head><meta charset="utf-8"><title>Payment cancelled</title></head>
<body style="font-family:Arial,sans-serif;padding:40px;">
    <h2>Payment was not completed in this browser</h2>
    <p>The appointment was cancelled because the payment page was closed.</p>
    <?php if ($appointment): ?>
        <p>Current payment status: <b><?php echo htmlspecialchars($appointment["payment_status"]); ?></b></p>
    <?php endif; ?>
</body>
</html>
