<?php
require_once __DIR__ . "/../connection.php";
require_once __DIR__ . "/../lib/payment_repository.php";

$outTradeNo = $_GET["out_trade_no"] ?? "";
$appointment = $outTradeNo ? appointment_by_trade($database, $outTradeNo) : null;
if (!$appointment) {
    http_response_code(404);
    echo "Mock payment not found.";
    exit;
}

$config = alipay_h5_config();
$notifyParams = [
    "app_id" => $config["app_id"],
    "seller_id" => $config["seller_id"],
    "out_trade_no" => $appointment["out_trade_no"],
    "trade_no" => "MOCK" . $appointment["out_trade_no"],
    "trade_status" => "TRADE_SUCCESS",
    "total_amount" => money((float) $appointment["amount"]),
    "sign" => "mock-valid",
    "sign_type" => "RSA2",
];
?>
<!doctype html>
<html>
<head><meta charset="utf-8"><title>Mock Alipay cashier</title></head>
<body style="font-family:Arial,sans-serif;padding:40px;">
    <h2>Mock Alipay cashier</h2>
    <p>out_trade_no: <?php echo htmlspecialchars($appointment["out_trade_no"]); ?></p>
    <p>Amount: CNY <?php echo htmlspecialchars(money((float) $appointment["amount"])); ?></p>
    <form method="post" action="../alipay/h5/notify.php">
        <?php foreach ($notifyParams as $key => $value): ?>
            <input type="hidden" name="<?php echo htmlspecialchars($key); ?>" value="<?php echo htmlspecialchars($value); ?>">
        <?php endforeach; ?>
        <button type="submit">Pay successfully</button>
    </form>
    <p><a href="../patient/alipay-h5/quit.php?out_trade_no=<?php echo rawurlencode($appointment["out_trade_no"]); ?>">Cancel and return</a></p>
</body>
</html>
