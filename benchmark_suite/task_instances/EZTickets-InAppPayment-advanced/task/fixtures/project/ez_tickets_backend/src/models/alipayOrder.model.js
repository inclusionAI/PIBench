const { DBService } = require('../db/db-service');
const { multipleColumnSet } = require('../utils/common.utils');
const { tables } = require('../utils/tableNames.utils');

class AlipayOrderModel {
    findByOutTradeNo = async (outTradeNo) => {
        const sql = `SELECT * FROM ${tables.AlipayOrders} WHERE out_trade_no = ?`;
        const result = await DBService.query(sql, [outTradeNo]);
        return result[0];
    }

    findSuccessfulByBookingId = async (bookingId) => {
        const sql = `SELECT * FROM ${tables.AlipayOrders}
        WHERE JSON_CONTAINS(booking_ids, ?)
        AND trade_status IN ('TRADE_SUCCESS', 'TRADE_FINISHED')
        AND payment_id IS NOT NULL
        ORDER BY created_at DESC
        LIMIT 1`;
        const result = await DBService.query(sql, [JSON.stringify(Number(bookingId))]);
        return result[0];
    }

    create = async (order) => {
        const sql = `INSERT INTO ${tables.AlipayOrders}
        (out_trade_no, order_string, amount, alipay_amount, trade_status, user_id, show_id, booking_ids, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,NOW(),NOW())`;
        const result = await DBService.query(sql, [
            order.out_trade_no,
            order.order_string,
            order.amount,
            order.alipay_amount,
            order.trade_status,
            order.user_id,
            order.show_id,
            JSON.stringify(order.booking_ids)
        ]);
        return result ? result.insertId : 0;
    }

    updateByOutTradeNo = async (outTradeNo, params) => {
        const { columnSet, values } = multipleColumnSet({...params, updated_at: new Date()});
        const sql = `UPDATE ${tables.AlipayOrders} SET ${columnSet} WHERE out_trade_no = ?`;
        return await DBService.query(sql, [...values, outTradeNo]);
    }
}

module.exports = new AlipayOrderModel();
