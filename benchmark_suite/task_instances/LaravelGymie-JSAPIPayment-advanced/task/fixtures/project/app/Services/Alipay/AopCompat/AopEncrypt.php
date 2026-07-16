<?php

declare(strict_types=1);

/*
 * The official Alipay v2 AOP SDK declares global encrypt()/decrypt() helpers.
 * Laravel already owns those names, so this compatibility file is loaded first
 * and keeps the SDK usable without redeclaring framework helpers.
 */

if (! function_exists('encrypt')) {
    function encrypt($str, $screct_key)
    {
        $screct_key = base64_decode($screct_key);
        $str = trim($str);
        $str = addPKCS7Padding($str);

        $iv = str_repeat("\0", 16);
        $encrypt_str = openssl_encrypt($str, 'aes-128-cbc', $screct_key, OPENSSL_NO_PADDING, $iv);

        return base64_encode($encrypt_str);
    }
}

if (! function_exists('decrypt')) {
    function decrypt($str, $screct_key)
    {
        $str = base64_decode($str);
        $screct_key = base64_decode($screct_key);

        $iv = str_repeat("\0", 16);
        $decrypt_str = openssl_decrypt($str, 'aes-128-cbc', $screct_key, OPENSSL_NO_PADDING, $iv);

        return stripPKSC7Padding($decrypt_str);
    }
}

if (! function_exists('addPKCS7Padding')) {
    function addPKCS7Padding($source)
    {
        $source = trim($source);
        $block = 16;
        $pad = $block - (strlen($source) % $block);

        if ($pad <= $block) {
            $source .= str_repeat(chr($pad), $pad);
        }

        return $source;
    }
}

if (! function_exists('stripPKSC7Padding')) {
    function stripPKSC7Padding($source)
    {
        $char = substr($source, -1);
        $num = ord($char);

        if ($num === 62) {
            return $source;
        }

        return substr($source, 0, -$num);
    }
}
