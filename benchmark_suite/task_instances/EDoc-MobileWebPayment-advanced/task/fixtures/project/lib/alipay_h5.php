<?php

function edoc_base_url(): string
{
    $configured = getenv("APP_BASE_URL");
    if ($configured) {
        return rtrim($configured, "/");
    }

    $scheme = (!empty($_SERVER["HTTPS"]) && $_SERVER["HTTPS"] !== "off") ? "https" : "http";
    $host = $_SERVER["HTTP_HOST"] ?? "localhost:8133";
    return $scheme . "://" . $host;
}

function alipay_h5_config(): array
{
    return [
        "app_id" => getenv("ALIPAY_APP_ID") ?: "edoc-h5-sandbox-app",
        "gateway" => getenv("ALIPAY_GATEWAY") ?: "https://openapi-sandbox.dl.alipaydev.com/gateway.do",
        "private_key" => getenv("ALIPAY_PRIVATE_KEY") ?: "",
        "alipay_public_key" => getenv("ALIPAY_PUBLIC_KEY") ?: "",
        "seller_id" => getenv("ALIPAY_SELLER_ID") ?: "edoc-clinic",
        "mock_mode" => (getenv("ALIPAY_MOCK_MODE") ?: "true") !== "false",
        "return_url" => edoc_base_url() . "/patient/alipay-h5/return.php",
        "notify_url" => edoc_base_url() . "/alipay/h5/notify.php",
        "quit_url" => edoc_base_url() . "/patient/alipay-h5/quit.php",
    ];
}

function alipay_encode_key(string $key, string $type): string
{
    if (strpos($key, "BEGIN") !== false) {
        return $key;
    }

    $body = chunk_split(trim($key), 64, "\n");
    return "-----BEGIN " . $type . "-----\n" . $body . "-----END " . $type . "-----";
}

function alipay_sorted_query(array $params, bool $includeSign = false): string
{
    ksort($params);
    $pairs = [];
    foreach ($params as $key => $value) {
        if ($value === "" || $value === null) {
            continue;
        }
        if (!$includeSign && ($key === "sign" || $key === "sign_type")) {
            continue;
        }
        $pairs[] = $key . "=" . $value;
    }
    return implode("&", $pairs);
}

function alipay_sign(array $params, string $privateKey): string
{
    if (!$privateKey) {
        return "mock-signature";
    }

    $key = openssl_pkey_get_private(alipay_encode_key($privateKey, "PRIVATE KEY"));
    if (!$key) {
        throw new RuntimeException("Invalid ALIPAY_PRIVATE_KEY");
    }

    openssl_sign(alipay_sorted_query($params), $signature, $key, OPENSSL_ALGO_SHA256);
    return base64_encode($signature);
}

function alipay_verify(array $params, string $publicKey): bool
{
    if (($params["sign"] ?? "") === "mock-valid") {
        return true;
    }
    if (!$publicKey || empty($params["sign"])) {
        return false;
    }

    $signature = base64_decode($params["sign"], true);
    if ($signature === false) {
        return false;
    }

    $key = openssl_pkey_get_public(alipay_encode_key($publicKey, "PUBLIC KEY"));
    if (!$key) {
        return false;
    }

    return openssl_verify(alipay_sorted_query($params), $signature, $key, OPENSSL_ALGO_SHA256) === 1;
}

function alipay_h5_gateway_url(array $appointment): string
{
    $config = alipay_h5_config();
    if ($config["mock_mode"]) {
        return edoc_base_url() . "/mock-alipay/cashier.php?out_trade_no=" . rawurlencode($appointment["out_trade_no"]);
    }

    $bizContent = [
        "out_trade_no" => $appointment["out_trade_no"],
        "total_amount" => number_format((float) $appointment["amount"], 2, ".", ""),
        "subject" => "eDoc doctor appointment #" . $appointment["appoid"],
        "product_code" => "QUICK_WAP_WAY",
        "quit_url" => $config["quit_url"],
    ];
    $params = [
        "app_id" => $config["app_id"],
        "method" => "alipay.trade.wap.pay",
        "format" => "JSON",
        "charset" => "utf-8",
        "sign_type" => "RSA2",
        "timestamp" => date("Y-m-d H:i:s"),
        "version" => "1.0",
        "return_url" => $config["return_url"],
        "notify_url" => $config["notify_url"],
        "biz_content" => json_encode($bizContent, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE),
    ];
    $params["sign"] = alipay_sign($params, $config["private_key"]);

    return $config["gateway"] . "?" . http_build_query($params);
}

function alipay_query_trade(array $appointment, ?string $mockStatus = null): array
{
    $config = alipay_h5_config();
    if ($config["mock_mode"]) {
        $status = $mockStatus ?: ($appointment["payment_status"] === "paid" ? "TRADE_SUCCESS" : "WAIT_BUYER_PAY");
        return [
            "ok" => true,
            "trade_status" => $status,
            "out_trade_no" => $appointment["out_trade_no"],
            "trade_no" => $appointment["alipay_trade_no"] ?: "MOCK" . $appointment["out_trade_no"],
            "total_amount" => number_format((float) $appointment["amount"], 2, ".", ""),
            "seller_id" => $config["seller_id"],
        ];
    }

    return ["ok" => false, "trade_status" => "UNKNOWN", "message" => "Real query transport should be configured by the runner."];
}

function alipay_refund_trade(array $appointment, string $requestNo, float $amount, ?string $mockStatus = null): array
{
    $config = alipay_h5_config();
    if ($config["mock_mode"]) {
        if ($mockStatus === "unknown") {
            return ["ok" => false, "code" => "20000", "status" => "unknown", "message" => "mock unknown refund"];
        }
        $response = [
            "ok" => true,
            "code" => "10000",
            "fund_change" => "Y",
            "out_trade_no" => $appointment["out_trade_no"],
            "trade_no" => $appointment["alipay_trade_no"] ?: "MOCK" . $appointment["out_trade_no"],
            "refund_fee" => number_format($amount, 2, ".", ""),
            "out_request_no" => $requestNo,
        ];
        if ($mockStatus === "no_fund_change") {
            $response["fund_change"] = "N";
        } elseif ($mockStatus === "amount_mismatch") {
            $response["refund_fee"] = number_format($amount + 1, 2, ".", "");
        } elseif ($mockStatus === "request_mismatch") {
            $response["out_request_no"] = $requestNo . "-other";
        }
        return $response;
    }

    return ["ok" => false, "status" => "unknown", "message" => "Real refund transport should be configured by the runner."];
}

function alipay_refund_query(array $appointment, string $requestNo, ?float $amount = null): array
{
    $config = alipay_h5_config();
    if ($config["mock_mode"]) {
        $refundAmount = $amount ?? (float) ($appointment["paid_amount"] ?: $appointment["amount"]);
        return [
            "ok" => true,
            "code" => "10000",
            "refund_status" => "REFUND_SUCCESS",
            "fund_change" => "Y",
            "out_trade_no" => $appointment["out_trade_no"],
            "trade_no" => $appointment["alipay_trade_no"] ?: "MOCK" . $appointment["out_trade_no"],
            "refund_fee" => number_format($refundAmount, 2, ".", ""),
            "out_request_no" => $requestNo,
        ];
    }

    return ["ok" => false, "status" => "unknown"];
}
?>
