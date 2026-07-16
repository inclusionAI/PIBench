<?php

namespace App\Services\Alipay;

use App\Models\AlipayJsapiOrder;
use Illuminate\Config\Repository as ConfigRepository;
use Illuminate\Http\Request;
use JsonException;
use RuntimeException;

class AlipayJsapiPaymentService
{
    private bool $sdkLoaded = false;

    public function __construct(
        private readonly ConfigRepository $config,
        private readonly Request $request,
    ) {
    }

    /**
     * Create an Alipay JSAPI trade and return the trade_no used by my.tradePay.
     *
     * @return array{trade_no:string, response:array<string, mixed>}
     *
     * @throws JsonException
     */
    public function createTrade(AlipayJsapiOrder $order): array
    {
        if ($this->isDemoMode()) {
            return [
                'trade_no' => 'DEMO'.now()->format('YmdHis').strtoupper(substr($order->out_trade_no, -8)),
                'response' => [
                    'code' => 'DEMO',
                    'msg' => 'Demo mode enabled',
                ],
            ];
        }

        if (! $order->buyer_id && ! $order->buyer_open_id) {
            throw new RuntimeException(__('Alipay JSAPI requires buyer_id or buyer_open_id in real mode.'));
        }

        $response = $this->withClient(function (object $client) use ($order) {
            $request = new \AlipayTradeCreateRequest();
            $request->setNotifyUrl($this->notifyUrl());
            $request->setBizContent(json_encode([
                'out_trade_no' => $order->out_trade_no,
                'total_amount' => number_format((float) $order->amount, 2, '.', ''),
                'subject' => $this->cleanSubject('Gym membership '.$order->plan->name),
                'product_code' => 'JSAPI_PAY',
                'op_app_id' => $this->miniAppId(),
                'buyer_id' => $order->buyer_id ?: null,
                'buyer_open_id' => $order->buyer_open_id ?: null,
                'timeout_express' => (string) $this->config->get('services.alipay_jsapi.timeout_express', '15m'),
            ], JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR));

            return $client->execute($request);
        });

        $payload = $this->responseToArray($response);
        $tradeResponse = $payload['alipay_trade_create_response'] ?? null;

        if (! is_array($tradeResponse) || ($tradeResponse['code'] ?? null) !== '10000') {
            $message = is_array($tradeResponse)
                ? ($tradeResponse['sub_msg'] ?? $tradeResponse['msg'] ?? __('Alipay JSAPI trade creation failed.'))
                : __('Alipay JSAPI trade creation failed.');

            throw new RuntimeException($message);
        }

        return [
            'trade_no' => (string) ($tradeResponse['trade_no'] ?? ''),
            'response' => $tradeResponse,
        ];
    }

    /**
     * Query Alipay for the current trade status.
     *
     * @return array<string, mixed>
     *
     * @throws JsonException
     */
    public function queryTrade(AlipayJsapiOrder $order): array
    {
        if ($this->isDemoMode()) {
            return [
                'code' => 'DEMO',
                'trade_status' => $order->status === AlipayJsapiOrder::STATUS_PAID ? 'TRADE_SUCCESS' : 'WAIT_BUYER_PAY',
            ];
        }

        $response = $this->withClient(function (object $client) use ($order) {
            $request = new \AlipayTradeQueryRequest();
            $request->setBizContent(json_encode([
                'out_trade_no' => $order->out_trade_no,
                'trade_no' => $order->trade_no,
            ], JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR));

            return $client->execute($request);
        });

        $payload = $this->responseToArray($response);
        $tradeResponse = $payload['alipay_trade_query_response'] ?? null;

        if (! is_array($tradeResponse) || ($tradeResponse['code'] ?? null) !== '10000') {
            $message = is_array($tradeResponse)
                ? ($tradeResponse['sub_msg'] ?? $tradeResponse['msg'] ?? __('Alipay JSAPI trade query failed.'))
                : __('Alipay JSAPI trade query failed.');

            throw new RuntimeException($message);
        }

        return $tradeResponse;
    }

    /**
     * Exchange a Mini Program auth code for the user identity required by JSAPI pay.
     *
     * @return array{user_id:string, open_id:string, response:array<string, mixed>}
     */
    public function exchangeAuthCode(string $authCode): array
    {
        if ($this->isDemoMode()) {
            return [
                'user_id' => '2088-demo-user',
                'open_id' => '2088-demo-openid',
                'response' => [
                    'code' => 'DEMO',
                    'msg' => 'Demo mode enabled',
                ],
            ];
        }

        $response = $this->withClient(function (object $client) use ($authCode) {
            $request = new \AlipaySystemOauthTokenRequest();
            $request->setGrantType('authorization_code');
            $request->setCode($authCode);

            return $client->execute($request);
        });

        $payload = $this->responseToArray($response);
        $tokenResponse = $payload['alipay_system_oauth_token_response'] ?? null;

        if (! is_array($tokenResponse) || ($tokenResponse['code'] ?? null) !== '10000') {
            $message = is_array($tokenResponse)
                ? ($tokenResponse['sub_msg'] ?? $tokenResponse['msg'] ?? __('Alipay auth code exchange failed.'))
                : __('Alipay auth code exchange failed.');

            throw new RuntimeException($message);
        }

        return [
            'user_id' => (string) ($tokenResponse['user_id'] ?? ''),
            'open_id' => (string) ($tokenResponse['open_id'] ?? ''),
            'response' => $tokenResponse,
        ];
    }

    /**
     * @return array<string, mixed>
     *
     * @throws JsonException
     */
    public function refund(AlipayJsapiOrder $order, float $amount, string $refundRequestNo): array
    {
        if ($this->isDemoMode()) {
            return [
                'code' => 'DEMO',
                'out_trade_no' => $order->out_trade_no,
                'trade_no' => $order->trade_no,
                'refund_amount' => number_format($amount, 2, '.', ''),
                'out_request_no' => $refundRequestNo,
            ];
        }

        $response = $this->withClient(function (object $client) use ($order, $amount, $refundRequestNo) {
            $request = new \AlipayTradeRefundRequest();
            $request->setBizContent(json_encode([
                'out_trade_no' => $order->out_trade_no,
                'trade_no' => $order->trade_no,
                'refund_amount' => number_format($amount, 2, '.', ''),
                'refund_reason' => 'Gym membership refund',
                'out_request_no' => $refundRequestNo,
            ], JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR));

            return $client->execute($request);
        });

        $payload = $this->responseToArray($response);
        $refundResponse = $payload['alipay_trade_refund_response'] ?? null;

        if (! is_array($refundResponse) || ($refundResponse['code'] ?? null) !== '10000') {
            $message = is_array($refundResponse)
                ? ($refundResponse['sub_msg'] ?? $refundResponse['msg'] ?? __('Alipay JSAPI refund failed.'))
                : __('Alipay JSAPI refund failed.');

            throw new RuntimeException($message);
        }

        return $refundResponse;
    }

    public function verifyNotify(array $payload): bool
    {
        if (($payload['app_id'] ?? null) !== $this->requiredConfig('app_id')) {
            return false;
        }

        if (empty($payload['sign'])) {
            return false;
        }

        return $this->withClient(
            fn (object $client): bool => $client->rsaCheckV1($payload, null, 'RSA2') === true
        );
    }

    public function isDemoMode(): bool
    {
        return (bool) $this->config->get('services.alipay_jsapi.demo_mode')
            || ! $this->config->get('services.alipay_jsapi.app_id')
            || ! $this->config->get('services.alipay_jsapi.private_key')
            || ! $this->config->get('services.alipay_jsapi.public_key');
    }

    private function withClient(callable $callback): mixed
    {
        $this->loadSdk();

        $privateKeyPath = $this->writePrivateKeyFile($this->requiredConfig('private_key'));

        try {
            $client = new \AopClient();
            $client->gatewayUrl = $this->requiredConfig('gateway_url');
            $client->appId = $this->requiredConfig('app_id');
            $client->rsaPrivateKeyFilePath = $privateKeyPath;
            $client->alipayrsaPublicKey = $this->stripPem($this->requiredConfig('public_key'));
            $client->apiVersion = '1.0';
            $client->signType = 'RSA2';
            $client->postCharset = 'utf-8';
            $client->format = 'json';

            return $this->withoutSdkWarnings(fn () => $callback($client));
        } finally {
            @unlink($privateKeyPath);
        }
    }

    private function loadSdk(): void
    {
        if ($this->sdkLoaded) {
            return;
        }

        $aopPath = base_path('vendor/alipaysdk/openapi/v2/aop');
        if (! is_file($aopPath.'/AopClient.php')) {
            throw new RuntimeException(__('Alipay PHP SDK is not installed. Run composer install.'));
        }

        $previousIncludePath = get_include_path();
        set_include_path(implode(PATH_SEPARATOR, [
            app_path('Services/Alipay/AopCompat'),
            $aopPath,
            $previousIncludePath,
        ]));

        try {
            $this->withoutSdkWarnings(function () use ($aopPath): void {
                if (! class_exists(\AopClient::class, false)) {
                    require_once $aopPath.'/AopClient.php';
                }

                $requests = [
                    'AlipaySystemOauthTokenRequest',
                    'AlipayTradeCreateRequest',
                    'AlipayTradeQueryRequest',
                    'AlipayTradeRefundRequest',
                ];

                foreach ($requests as $requestClass) {
                    if (! class_exists($requestClass, false)) {
                        require_once $aopPath.'/request/'.$requestClass.'.php';
                    }
                }
            });
        } finally {
            set_include_path($previousIncludePath);
        }

        $this->sdkLoaded = true;
    }

    private function withoutSdkWarnings(callable $callback): mixed
    {
        $bufferLevel = ob_get_level();
        $previousReporting = error_reporting(
            error_reporting() & ~E_WARNING & ~E_DEPRECATED & ~E_USER_DEPRECATED
        );

        ob_start();

        try {
            return $callback();
        } finally {
            while (ob_get_level() > $bufferLevel) {
                ob_end_clean();
            }

            error_reporting($previousReporting);
        }
    }

    private function writePrivateKeyFile(string $key): string
    {
        $directory = storage_path('framework/cache');
        if (! is_dir($directory) && ! mkdir($directory, 0755, true) && ! is_dir($directory)) {
            $directory = sys_get_temp_dir();
        }

        $path = tempnam($directory, 'alipay_jsapi_');
        if ($path === false) {
            throw new RuntimeException(__('Unable to create temporary Alipay JSAPI private key file.'));
        }

        file_put_contents($path, $this->normalizePrivateKey($key));
        chmod($path, 0600);

        return $path;
    }

    private function normalizePrivateKey(string $key): string
    {
        $key = trim(str_replace('\n', "\n", $key));
        if (str_contains($key, 'BEGIN')) {
            return $key;
        }

        return "-----BEGIN RSA PRIVATE KEY-----\n"
            .chunk_split($key, 64, "\n")
            ."-----END RSA PRIVATE KEY-----";
    }

    private function stripPem(string $key): string
    {
        $key = trim(str_replace('\n', "\n", $key));
        $key = preg_replace('/-----BEGIN [^-]+-----|-----END [^-]+-----/', '', $key) ?? $key;

        return preg_replace('/\s+/', '', $key) ?? $key;
    }

    private function requiredConfig(string $key): string
    {
        $value = (string) $this->config->get("services.alipay_jsapi.{$key}");
        if ($value === '') {
            throw new RuntimeException(__('Missing Alipay JSAPI configuration: :key', ['key' => $key]));
        }

        return $value;
    }

    private function miniAppId(): string
    {
        return (string) ($this->config->get('services.alipay_jsapi.mini_app_id') ?: $this->requiredConfig('app_id'));
    }

    private function notifyUrl(): string
    {
        return $this->config->get('services.alipay_jsapi.notify_url')
            ?: $this->absoluteUrl('/alipay-jsapi/notify');
    }

    private function absoluteUrl(string $path): string
    {
        return rtrim($this->request->getSchemeAndHttpHost(), '/').$path;
    }

    private function cleanSubject(string $subject): string
    {
        $subject = preg_replace('/[\/=&]+/', ' ', $subject) ?? $subject;

        return mb_substr(trim($subject), 0, 256);
    }

    /**
     * @return array<string, mixed>
     *
     * @throws JsonException
     */
    private function responseToArray(mixed $response): array
    {
        if ($response === false) {
            throw new RuntimeException(__('Alipay JSAPI request failed.'));
        }

        return json_decode(json_encode($response, JSON_THROW_ON_ERROR), true, 512, JSON_THROW_ON_ERROR);
    }
}
