const { AlipaySdk } = require('alipay-sdk');
const { Config } = require('../configs/config');
const { InternalServerException } = require('../utils/exceptions/api.exception');

const requireAlipayConfig = () => {
    const required = ['ALIPAY_APP_ID', 'ALIPAY_PRIVATE_KEY', 'ALIPAY_PUBLIC_KEY', 'ALIPAY_GATEWAY'];
    const missing = required.filter((key) => !Config[key]);
    if (missing.length) {
        throw new InternalServerException(`Missing Alipay configuration: ${missing.join(', ')}`);
    }
};

const wrapKey = (key, label) => {
    const normalized = key.replace(/\\n/g, '\n').trim();
    if (normalized.includes('BEGIN ')) return normalized;
    const chunks = normalized.match(/.{1,64}/g) || [];
    return `-----BEGIN ${label}-----\n${chunks.join('\n')}\n-----END ${label}-----`;
};

const normalizeTradeResult = (result) => {
    if (!result) return result;
    return {
        ...result,
        out_trade_no: result.out_trade_no || result.outTradeNo,
        trade_no: result.trade_no || result.tradeNo,
        trade_status: result.trade_status || result.tradeStatus,
        total_amount: result.total_amount || result.totalAmount
    };
};

class AlipayService {
    getSdk = () => {
        requireAlipayConfig();
        return new AlipaySdk({
            appId: Config.ALIPAY_APP_ID,
            privateKey: wrapKey(Config.ALIPAY_PRIVATE_KEY, 'RSA PRIVATE KEY'),
            alipayPublicKey: wrapKey(Config.ALIPAY_PUBLIC_KEY, 'PUBLIC KEY'),
            gateway: Config.ALIPAY_GATEWAY,
            charset: 'utf-8',
            signType: 'RSA2'
        });
    }

    createAppPayOrder = async ({ outTradeNo, totalAmount, subject }) => {
        if (Config.ALIPAY_DEV_AUTO_CONFIRM) {
            return `DEV_ALIPAY_AUTO_CONFIRM:${outTradeNo}:${totalAmount}:${subject}`;
        }

        const sdk = this.getSdk();
        const payload = {
            bizContent: {
                out_trade_no: outTradeNo,
                total_amount: totalAmount,
                subject: subject.replace(/[=/&]/g, ' ').slice(0, 128),
                product_code: 'QUICK_MSECURITY_PAY'
            }
        };
        if (Config.ALIPAY_NOTIFY_URL) {
            payload.notify_url = Config.ALIPAY_NOTIFY_URL;
        }

        if (typeof sdk.sdkExecute === 'function') {
            return await sdk.sdkExecute('alipay.trade.app.pay', payload);
        }
        return await sdk.sdkExec('alipay.trade.app.pay', payload);
    }

    queryTrade = async (outTradeNo) => {
        if (Config.ALIPAY_DEV_AUTO_CONFIRM) {
            return {
                out_trade_no: outTradeNo,
                trade_no: `DEV${outTradeNo}`,
                trade_status: 'TRADE_SUCCESS'
            };
        }

        const sdk = this.getSdk();
        const result = await sdk.exec('alipay.trade.query', {
            bizContent: { out_trade_no: outTradeNo }
        });
        return normalizeTradeResult(result);
    }

    verifyNotify = (params) => {
        if (Config.ALIPAY_DEV_AUTO_CONFIRM) return false;

        const sdk = this.getSdk();
        if (typeof sdk.checkNotifySignV2 === 'function') {
            return sdk.checkNotifySignV2(params);
        }
        return sdk.checkNotifySign(params);
    }
}

module.exports = new AlipayService();
