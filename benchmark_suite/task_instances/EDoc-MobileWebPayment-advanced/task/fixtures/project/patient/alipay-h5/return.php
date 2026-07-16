<?php
require_once __DIR__ . "/../../connection.php";
require_once __DIR__ . "/../../lib/payment_repository.php";

$outTradeNo = $_GET["out_trade_no"] ?? "";
$appointment = $outTradeNo ? appointment_by_trade($database, $outTradeNo) : null;
if ($appointment && $appointment["payment_status"] === "pending") {
    // TODO(q2-safety): browser return is not trustworthy and must not mark paid.
    mark_appointment_paid($database, $appointment, "RETURN" . $appointment["out_trade_no"], ["source" => "return_url"]);
    $appointment = appointment_by_trade($database, $outTradeNo);
}
?>
<!doctype html>
<html>
<head><meta charset="utf-8"><title>Payment returned</title></head>
<body style="font-family:Arial,sans-serif;padding:40px;">
    <h2>Payment return received</h2>
    <p>The browser returned from payment.</p>
    <?php if ($appointment): ?>
        <p>Current payment status: <b><?php echo htmlspecialchars($appointment["payment_status"]); ?></b></p>
        <form method="post" action="sync.php">
            <input type="hidden" name="out_trade_no" value="<?php echo htmlspecialchars($appointment["out_trade_no"]); ?>">
            <button type="submit">Verify on server</button>
        </form>
    <?php endif; ?>
</body>
</html>
