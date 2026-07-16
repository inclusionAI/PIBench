/* eslint-disable no-undef */
const assert = require('assert');

const PaymentRepository = require('../src/repositories/payment.repository');
const AlipayService = require('../src/services/alipay.service');
const AlipayOrderModel = require('../src/models/alipayOrder.model');
const BookingModel = require('../src/models/booking.model');
const PaymentModel = require('../src/models/payment.model');
const { DBService } = require('../src/db/db-service');
const { Config } = require('../src/configs/config');

describe('Alipay App Pay basic integration', () => {
    const originals = [];

    beforeEach(() => {
        [
            [AlipayService, 'createAppPayOrder'],
            [AlipayService, 'queryTrade'],
            [AlipayService, 'getSdk'],
            [AlipayOrderModel, 'findByOutTradeNo'],
            [AlipayOrderModel, 'create'],
            [AlipayOrderModel, 'updateByOutTradeNo'],
            [BookingModel, 'findReservedByIds'],
            [BookingModel, 'update'],
            [PaymentModel, 'create'],
            [DBService, 'beginTransaction'],
            [DBService, 'commit'],
            [DBService, 'rollback']
        ].forEach(([object, key]) => originals.push([object, key, object[key]]));

        Config.ALIPAY_APP_ID = 'app_123';
        Config.ALIPAY_PRIVATE_KEY = 'private_key';
        Config.ALIPAY_PUBLIC_KEY = 'public_key';
        Config.ALIPAY_GATEWAY = 'https://example.com/gateway.do';
        Config.ALIPAY_NOTIFY_URL = 'https://example.com/api/payments/alipay/notify';
        Config.ALIPAY_AMOUNT_DIVISOR = 100;
        Config.ALIPAY_DEV_AUTO_CONFIRM = false;
        DBService.beginTransaction = async () => {};
        DBService.commit = async () => {};
        DBService.rollback = async () => {};
    });

    afterEach(() => {
        while (originals.length) {
            const [object, key, value] = originals.pop();
            object[key] = value;
        }
    });

    it('creates an App Pay order string from reserved booking amounts on the server', async () => {
        let createdOrder;
        BookingModel.findReservedByIds = async () => [
            { booking_id: 181, price: 2400 }
        ];
        AlipayService.createAppPayOrder = async ({ outTradeNo, totalAmount, subject }) => {
            assert.ok(outTradeNo.startsWith('EZT'));
            assert.strictEqual(totalAmount, '24.00');
            assert.strictEqual(subject, 'EZ Tickets show 27');
            return 'signed_order_string';
        };
        AlipayOrderModel.create = async (order) => {
            createdOrder = order;
            return 1;
        };
        AlipayOrderModel.findByOutTradeNo = async () => ({
            ...createdOrder,
            trade_no: null,
            payment_id: null
        });

        const response = await PaymentRepository.createAlipayPayment({
            booking_ids: [181],
            show_id: 27
        }, { user_id: 10 });

        assert.strictEqual(createdOrder.amount, 2400);
        assert.deepStrictEqual(createdOrder.booking_ids, [181]);
        assert.strictEqual(response.body.order_str, 'signed_order_string');
        assert.strictEqual(response.body.out_trade_no, createdOrder.out_trade_no);
    });

    it('does not accept client-provided amount when creating an Alipay payment', async () => {
        BookingModel.findReservedByIds = async () => [
            { booking_id: 181, price: 2400 }
        ];
        AlipayService.createAppPayOrder = async ({ totalAmount }) => {
            assert.strictEqual(totalAmount, '24.00');
            return 'signed_order_string';
        };
        AlipayOrderModel.create = async () => 1;
        AlipayOrderModel.findByOutTradeNo = async (outTradeNo) => ({
            out_trade_no: outTradeNo,
            order_string: 'signed_order_string',
            amount: 2400,
            alipay_amount: '24.00',
            trade_status: 'WAIT_BUYER_PAY',
            trade_no: null,
            payment_id: null
        });

        const response = await PaymentRepository.createAlipayPayment({
            booking_ids: [181],
            show_id: 27,
            amount: 1
        }, { user_id: 10 });

        assert.strictEqual(response.body.amount, 2400);
    });

    it('confirms successful Alipay trades and creates a local payment', async () => {
        const order = {
            out_trade_no: 'EZT123',
            order_string: 'signed_order_string',
            amount: 2400,
            alipay_amount: '24.00',
            trade_status: 'WAIT_BUYER_PAY',
            trade_no: null,
            user_id: 10,
            show_id: 27,
            booking_ids: JSON.stringify([181]),
            payment_id: null
        };
        let paymentCreated;
        let bookingConfirmed;
        let statusUpdated;
        AlipayOrderModel.findByOutTradeNo = async () => order;
        AlipayService.queryTrade = async () => ({
            out_trade_no: 'EZT123',
            trade_no: '202606152200',
            trade_status: 'TRADE_SUCCESS'
        });
        AlipayOrderModel.updateByOutTradeNo = async (_outTradeNo, params) => {
            if (params.trade_status) statusUpdated = params;
            if (params.payment_id) order.payment_id = params.payment_id;
            if (params.trade_status) order.trade_status = params.trade_status;
            return { affectedRows: 1 };
        };
        PaymentModel.create = async (payment) => {
            paymentCreated = payment;
            return { payment_id: 99, affected_rows: 1 };
        };
        BookingModel.update = async (params, bookingId) => {
            bookingConfirmed = { params, bookingId };
            return { affectedRows: 1 };
        };

        const response = await PaymentRepository.confirmAlipayPayment({
            out_trade_no: 'EZT123'
        }, { user_id: 10 });

        assert.strictEqual(statusUpdated.trade_status, 'TRADE_SUCCESS');
        assert.strictEqual(paymentCreated.payment_method, 'alipay');
        assert.strictEqual(bookingConfirmed.params.booking_status, 'confirmed');
        assert.strictEqual(bookingConfirmed.bookingId, 181);
        assert.strictEqual(response.body.trade_status, 'TRADE_SUCCESS');
    });

    it('creates App Pay order strings with required SDK method and payload fields', async () => {
        let capturedMethod;
        let capturedPayload;
        AlipayService.getSdk = () => ({
            sdkExecute: async (method, payload) => {
                capturedMethod = method;
                capturedPayload = payload;
                return 'app_id=app_123&method=alipay.trade.app.pay&sign=fake_sign';
            }
        });

        const orderString = await AlipayService.createAppPayOrder({
            outTradeNo: 'order_1',
            totalAmount: '12.34',
            subject: 'EZ Tickets show 2'
        });

        assert.strictEqual(capturedMethod, 'alipay.trade.app.pay');
        assert.strictEqual(capturedPayload.notify_url, Config.ALIPAY_NOTIFY_URL);
        assert.deepStrictEqual(capturedPayload.bizContent, {
            out_trade_no: 'order_1',
            total_amount: '12.34',
            subject: 'EZ Tickets show 2',
            product_code: 'QUICK_MSECURITY_PAY'
        });
        assert.ok(orderString.includes('method=alipay.trade.app.pay'));
    });

    it('fails clearly when required Alipay configuration is missing', () => {
        Config.ALIPAY_APP_ID = '';
        Config.ALIPAY_PRIVATE_KEY = '';
        Config.ALIPAY_PUBLIC_KEY = '';
        Config.ALIPAY_GATEWAY = '';

        assert.throws(
            () => AlipayService.getSdk(),
            /Missing Alipay configuration: ALIPAY_APP_ID, ALIPAY_PRIVATE_KEY, ALIPAY_PUBLIC_KEY, ALIPAY_GATEWAY/
        );
    });
});
