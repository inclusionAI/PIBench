<?php
require_once __DIR__ . "/../../connection.php";
require_once __DIR__ . "/../../lib/payment_repository.php";

session_start();
$outTradeNo = $_GET["out_trade_no"] ?? "";
$appointment = appointment_by_trade($database, $outTradeNo);
if (!$appointment) {
    http_response_code(404);
    echo "Appointment payment not found.";
    exit;
}

$cashierUrl = alipay_h5_gateway_url($appointment);
$ua = strtolower($_SERVER["HTTP_USER_AGENT"] ?? "");
$isMobile = preg_match("/mobile|iphone|android|alipayclient|micromessenger/", $ua);
if ($isMobile && empty($_GET["desktop"])) {
    header("Location: " . $cashierUrl, true, 302);
    exit;
}
?>
<!doctype html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Alipay mobile payment</title>
    <link rel="stylesheet" href="../../css/main.css">
</head>
<body style="padding:40px;font-family:Arial,sans-serif;">
    <h2>Continue on mobile</h2>
    <p>Appointment #<?php echo htmlspecialchars($appointment["appoid"]); ?> is waiting for payment.</p>
    <p>Amount: CNY <?php echo htmlspecialchars(money((float) $appointment["amount"])); ?></p>
    <p>Open this link in a mobile browser or Alipay:</p>
    <p><a href="<?php echo htmlspecialchars($cashierUrl); ?>"><?php echo htmlspecialchars($cashierUrl); ?></a></p>
    <form method="post" action="sync.php">
        <input type="hidden" name="out_trade_no" value="<?php echo htmlspecialchars($appointment["out_trade_no"]); ?>">
        <input type="hidden" name="mock_trade_status" value="TRADE_SUCCESS">
        <button class="login-btn btn-primary btn" type="submit">Mock successful payment and sync</button>
    </form>
</body>
</html>
