/* eslint-disable no-undef */
const assert = require('assert');

const PaymentRepository = require('../src/repositories/payment.repository');
const BookingModel = require('../src/models/booking.model');
const PaymentModel = require('../src/models/payment.model');
const { DBService } = require('../src/db/db-service');

describe('Payment confirmation', () => {
    const originals = [];

    beforeEach(() => {
        [
            [DBService, 'beginTransaction'],
            [DBService, 'rollback'],
            [DBService, 'commit'],
            [PaymentModel, 'create'],
            [BookingModel, 'update']
        ].forEach(([object, key]) => {
            originals.push([object, key, object[key]]);
        });

        DBService.beginTransaction = async () => {};
        DBService.rollback = async () => {};
        DBService.commit = async () => {};
    });

    afterEach(() => {
        while (originals.length) {
            const [object, key, fn] = originals.pop();
            object[key] = fn;
        }
    });

    it('creates a payment and keeps the related bookings confirmed', async () => {
        const confirmedBookings = [];
        PaymentModel.create = async () => ({ payment_id: 10, affected_rows: 1 });
        BookingModel.update = async (params, bookingId) => {
            confirmedBookings.push({ params, bookingId });
            return { affectedRows: 1 };
        };

        const response = await PaymentRepository.create({
            amount: 800,
            payment_datetime: '2026-06-10T15:41:00.000',
            payment_method: 'cash',
            user_id: 2,
            show_id: 23,
            bookings: [181]
        });

        assert.strictEqual(response.headers.success, 1);
        assert.strictEqual(response.headers.message, 'Payment was created! Booking confirmed!');
        assert.deepStrictEqual(confirmedBookings, [{
            params: { booking_status: 'confirmed' },
            bookingId: 181
        }]);
    });
});
