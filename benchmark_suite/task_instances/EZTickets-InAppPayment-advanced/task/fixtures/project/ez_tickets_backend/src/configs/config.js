const fs = require('fs');
const path = require('path');

const sandboxKeysPath = path.resolve(__dirname, '../../..', 'alipay-sandbox-keys.json');

const readSandboxKeys = () => {
    try {
        if (!fs.existsSync(sandboxKeysPath)) return {};
        return JSON.parse(fs.readFileSync(sandboxKeysPath, 'utf8'));
    } catch (_error) {
        return {};
    }
};

const sandboxKeys = readSandboxKeys();
const pickSandboxValue = (...keys) => {
    for (const key of keys) {
        if (sandboxKeys[key]) return sandboxKeys[key];
    }
    return "";
};

module.exports.Config = {
    NODE_ENV: process.env.NODE_ENV || 'development',
    PORT: process.env.PORT || 3331,
    HOST: process.env.HOST || '0.0.0.0',
    DB_HOST: process.env.DB_HOST || 'localhost',
    DB_PORT: Number(process.env.DB_PORT || 3306),
    DB_USER: process.env.DB_USER || 'root',
    DB_PASS: process.env.DB_PASS || '',
    DB_DATABASE: process.env.DB_DATABASE || 'test',
    SECRET_JWT: process.env.SECRET_JWT || "",
    SENDGRID_API_KEY: process.env.SENDGRID_API_KEY || "SENDGRID_API_KEY",
    SENDGRID_SENDER: process.env.SENDGRID_SENDER || "FROM_EMAIL",
    ALIPAY_APP_ID: process.env.ALIPAY_APP_ID || pickSandboxValue('ALIPAY_APP_ID', 'appId', 'app_id'),
    ALIPAY_PRIVATE_KEY: process.env.ALIPAY_PRIVATE_KEY || pickSandboxValue('ALIPAY_PRIVATE_KEY', 'appPrivatePkcsKey', 'privateKey'),
    ALIPAY_PUBLIC_KEY: process.env.ALIPAY_PUBLIC_KEY || pickSandboxValue('ALIPAY_PUBLIC_KEY', 'alipayPublicKey', 'publicKey'),
    ALIPAY_GATEWAY: process.env.ALIPAY_GATEWAY || pickSandboxValue('ALIPAY_GATEWAY', 'gateway', 'gatewayUrl'),
    ALIPAY_NOTIFY_URL: process.env.ALIPAY_NOTIFY_URL || pickSandboxValue('ALIPAY_NOTIFY_URL', 'notifyUrl'),
    ALIPAY_AMOUNT_DIVISOR: Number(process.env.ALIPAY_AMOUNT_DIVISOR || 100),
    ALIPAY_DEV_AUTO_CONFIRM: process.env.ALIPAY_DEV_AUTO_CONFIRM === 'true'
};
