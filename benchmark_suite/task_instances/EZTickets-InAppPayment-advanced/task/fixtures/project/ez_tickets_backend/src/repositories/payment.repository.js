const crypto = require('crypto');
const { structureResponse } = require('../utils/common.utils');
const { Config } = require('../configs/config');
const { DBService } = require('../db/db-service');

const AlipayService = require('../services/alipay.service');
const AlipayOrderModel = require('../models/alipayOrder.model');
const BookingModel = require('../models/booking.model');
const PaymentModel = require('../models/payment.model');
const PaymentMethods = require('../utils/enums/paymentMethods.utils');
const {
    NotFoundException,
    CreateFailedException,
    UpdateFailedException,
    UnexpectedException
} = require('../utils/exceptions/database.exception');
const { InternalServerException } = require('../utils/exceptions/api.exception');

const SUCCESS_STATUSES = ['TRADE_SUCCESS'];

class PaymentRepository {
    findAll = async (params = {}) => {
        const hasParams = Object.keys(params).length !== 0;
        let payments = await PaymentModel.findAll(hasParams ? params : {});
        if (!payments.length) {
            throw new NotFoundException('Payments not found');
        }

        return structureResponse(payments, 1, "Success");
    };

    findOne = async (params) => {
        let payment = await PaymentModel.findOne(params);
        if (!payment) {
            throw new NotFoundException('Payment not found');
        }

        return structureResponse(payment, 1, "Success");
    };

    findAllByUser = async (id, query = {}) => {
        let payments = await PaymentModel.findAllByUser(id, query);
        if (!payments.length) {
            throw new NotFoundException('Payments for this user not found');
        }

        payments = payments.map((payment, _i, _payments) => {
            const {title, poster_url, ...paymentDetails} = payment;
            payment = paymentDetails;
            payment.movie = {title, poster_url};
            return payment;
        });

        return structureResponse(payments, 1, "Success");
    };

    create = async (body) => {
        const { bookings, ...reqBody } = body;

        await DBService.beginTransaction();
        
        const result = await PaymentModel.create(reqBody);

        if (!result) {
            await DBService.rollback();
            throw new CreateFailedException('Payment failed to be created');
        }

        for (const booking_id of bookings) {
            const success = await BookingModel.update({ booking_status: "confirmed" }, booking_id);
            
            if (!success) {
                await DBService.rollback();
                throw new UpdateFailedException('One of the bookings failed to be confirmed');
            }

            const { affectedRows } = success;

            if (!affectedRows) {
                await DBService.rollback();
                throw new NotFoundException(`Booking ID: ${booking_id} not found`);
            }
        }

        await DBService.commit();

        return structureResponse(result, 1, 'Payment was created! Booking confirmed!');
    };

    createAlipayPayment = async (body, currentUser) => {
        const { booking_ids, show_id } = body;
        if (!show_id || !Array.isArray(booking_ids) || !booking_ids.length) {
            throw new InternalServerException('booking_ids and show_id are required');
        }

        const userId = currentUser.user_id;
        const reservedBookings = await BookingModel.findReservedByIds({
            bookingIds: booking_ids,
            userId,
            showId: show_id
        });
        if (reservedBookings.length !== booking_ids.length) {
            throw new NotFoundException('Some selected bookings are no longer reserved');
        }

        const serverAmount = reservedBookings.reduce((sum, booking) => sum + Number(booking.price), 0);
        const outTradeNo = `EZT${Date.now()}${crypto.randomBytes(4).toString('hex')}`;
        const alipayAmount = (serverAmount / Config.ALIPAY_AMOUNT_DIVISOR).toFixed(2);
        const orderString = await AlipayService.createAppPayOrder({
            outTradeNo,
            totalAmount: alipayAmount,
            subject: `EZ Tickets show ${show_id}`
        });

        await AlipayOrderModel.create({
            out_trade_no: outTradeNo,
            order_string: orderString,
            amount: serverAmount,
            alipay_amount: alipayAmount,
            trade_status: 'WAIT_BUYER_PAY',
            user_id: userId,
            show_id,
            booking_ids: booking_ids
        });
        let order = await AlipayOrderModel.findByOutTradeNo(outTradeNo);
        if (Config.ALIPAY_DEV_AUTO_CONFIRM) {
            await this.applyAlipayTradeStatus(order, 'TRADE_SUCCESS', {
                out_trade_no: order.out_trade_no,
                trade_no: `DEV${order.out_trade_no}`,
                trade_status: 'TRADE_SUCCESS'
            });
            order = await AlipayOrderModel.findByOutTradeNo(order.out_trade_no);
        }
        return structureResponse(this.toAlipayOrderResponse(order), 1, 'Alipay order string created');
    };

    confirmAlipayPayment = async (body, currentUser) => {
        const { out_trade_no } = body;
        if (!out_trade_no) {
            throw new InternalServerException('out_trade_no is required');
        }

        return await this.getAlipayOrderStatus(out_trade_no, currentUser);
    };

    getAlipayOrderStatus = async (outTradeNo, currentUser = null) => {
        const order = await AlipayOrderModel.findByOutTradeNo(outTradeNo);
        if (!order) throw new NotFoundException('Alipay order not found');
        if (currentUser && order.user_id !== currentUser.user_id) {
            throw new NotFoundException('Alipay order not found');
        }

        const result = await AlipayService.queryTrade(outTradeNo);
        if (result && result.trade_status) {
            await this.applyAlipayTradeStatus(order, result.trade_status, result);
        }

        const updatedOrder = await AlipayOrderModel.findByOutTradeNo(outTradeNo);
        return structureResponse(this.toAlipayOrderResponse(updatedOrder), 1, 'Alipay payment status');
    };

    handleAlipayNotify = async (payload) => {
        const verified = AlipayService.verifyNotify(payload);
        if (!verified) return false;

        const order = await AlipayOrderModel.findByOutTradeNo(payload.out_trade_no);
        if (!order) return false;
        await this.applyAlipayTradeStatus(order, payload.trade_status, payload);
        return true;
    };

    applyAlipayTradeStatus = async (order, tradeStatus, rawPayload) => {
        const updates = {
            trade_status: tradeStatus,
            trade_no: rawPayload.trade_no || order.trade_no || null,
            raw_status_payload: JSON.stringify(rawPayload)
        };
        await AlipayOrderModel.updateByOutTradeNo(order.out_trade_no, updates);

        if (!order.payment_id && SUCCESS_STATUSES.includes(tradeStatus)) {
            await this.finalizeSuccessfulAlipayPayment(order.out_trade_no);
        }
    };

    finalizeSuccessfulAlipayPayment = async (outTradeNo) => {
        const order = await AlipayOrderModel.findByOutTradeNo(outTradeNo);
        if (!order) throw new NotFoundException('Alipay order not found');
        if (order.payment_id) return order.payment_id;

        const bookingIds = JSON.parse(order.booking_ids);
        const response = await this.create({
            amount: order.amount,
            payment_datetime: new Date(),
            payment_method: PaymentMethods.Alipay,
            user_id: order.user_id,
            show_id: order.show_id,
            bookings: bookingIds
        });
        const paymentId = response.body.payment_id;
        await AlipayOrderModel.updateByOutTradeNo(outTradeNo, { payment_id: paymentId });
        return paymentId;
    };

    toAlipayOrderResponse = (order) => ({
        out_trade_no: order.out_trade_no,
        order_str: order.order_string,
        trade_status: order.trade_status,
        trade_no: order.trade_no,
        payment_id: order.payment_id,
        outTradeNo: order.out_trade_no,
        orderStr: order.order_string,
        tradeStatus: order.trade_status,
        tradeNo: order.trade_no,
        amount: order.amount,
        alipayAmount: order.alipay_amount,
        paymentId: order.payment_id
    });

    update = async (body, id) => {
        const result = await PaymentModel.update(body, id);

        if (!result) {
            throw new UnexpectedException('Something went wrong');
        }

        const { affectedRows, changedRows, info } = result;

        if (!affectedRows) throw new NotFoundException('Payment not found');
        else if (affectedRows && !changedRows) throw new UpdateFailedException('Payment update failed');
        
        return structureResponse(info, 1, 'Payment updated successfully');
    };

    delete = async (id) => {
        const result = await PaymentModel.delete(id);
        
        if (!result) {
            throw new NotFoundException('Payment not found');
        }

        return structureResponse({}, 1, 'Payment has been deleted');
    };
}

module.exports = new PaymentRepository;
