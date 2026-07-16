<?php

return [

    /*
    |--------------------------------------------------------------------------
    | Third Party Services
    |--------------------------------------------------------------------------
    |
    | This file is for storing the credentials for third party services such
    | as Mailgun, Postmark, AWS and more. This file provides the de facto
    | location for this type of information, allowing packages to have
    | a conventional file to locate the various service credentials.
    |
    */

    'postmark' => [
        'token' => env('POSTMARK_TOKEN'),
    ],

    'ses' => [
        'key' => env('AWS_ACCESS_KEY_ID'),
        'secret' => env('AWS_SECRET_ACCESS_KEY'),
        'region' => env('AWS_DEFAULT_REGION', 'us-east-1'),
    ],

    'resend' => [
        'key' => env('RESEND_KEY'),
    ],

    'alipay_jsapi' => [
        'demo_mode' => env('ALIPAY_JSAPI_DEMO_MODE', true),
        'gateway_url' => env('ALIPAY_JSAPI_GATEWAY_URL', 'https://openapi.alipay.com/gateway.do'),
        'app_id' => env('ALIPAY_JSAPI_APP_ID'),
        'mini_app_id' => env('ALIPAY_JSAPI_MINI_APP_ID'),
        'seller_id' => env('ALIPAY_JSAPI_SELLER_ID'),
        'private_key' => env('ALIPAY_JSAPI_PRIVATE_KEY'),
        'public_key' => env('ALIPAY_JSAPI_PUBLIC_KEY'),
        'notify_url' => env('ALIPAY_JSAPI_NOTIFY_URL'),
        'timeout_express' => env('ALIPAY_JSAPI_TIMEOUT_EXPRESS', '15m'),
        'refund_token' => env('ALIPAY_JSAPI_REFUND_TOKEN'),
    ],

    'slack' => [
        'notifications' => [
            'bot_user_oauth_token' => env('SLACK_BOT_USER_OAUTH_TOKEN'),
            'channel' => env('SLACK_BOT_USER_DEFAULT_CHANNEL'),
        ],
    ],

];
