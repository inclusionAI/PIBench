/* eslint-disable no-undef */
const assert = require('assert');

const BookingsRepository = require('../src/repositories/bookings.repository');
const BookingModel = require('../src/models/booking.model');
const AlipayOrderModel = require('../src/models/alipayOrder.model');

describe('Booking cancellation', () => {
    const originals = {};

    beforeEach(() => {
        [
            [BookingModel, 'findOneForUser'],
            [BookingModel, 'cancelForUser'],
            [AlipayOrderModel, 'findSuccessfulByBookingId']
        ].forEach(([object, key]) => {
            originals[key] = originals[key] || [];
            originals[key].push([object, object[key]]);
        });
        AlipayOrderModel.findSuccessfulByBookingId = async () => null;
    });

    afterEach(() => {
        while (Object.keys(originals).length) {
            const key = Object.keys(originals).pop();
            originals[key].forEach(([object, fn]) => {
                object[key] = fn;
            });
            delete originals[key];
        }
    });

    it('cancels an active booking owned by the authenticated user', async () => {
        let cancelled = false;
        BookingModel.findOneForUser = async () => cancelled
            ? { booking_id: 1, user_id: 2, booking_status: 'cancelled' }
            : { booking_id: 1, user_id: 2, booking_status: 'confirmed' };
        BookingModel.cancelForUser = async () => {
            cancelled = true;
            return { affectedRows: 1 };
        };

        const response = await BookingsRepository.cancelForUser({
            bookingId: 1,
            userId: 2
        });

        assert.strictEqual(response.headers.success, 1);
        assert.strictEqual(response.headers.message, 'Booking cancelled successfully');
        assert.strictEqual(response.body.booking_status, 'cancelled');
    });

    it('treats an already cancelled booking as idempotent', async () => {
        let updateCalled = false;
        BookingModel.findOneForUser = async () => ({
            booking_id: 1,
            user_id: 2,
            booking_status: 'cancelled'
        });
        BookingModel.cancelForUser = async () => {
            updateCalled = true;
        };

        const response = await BookingsRepository.cancelForUser({
            bookingId: 1,
            userId: 2
        });

        assert.strictEqual(response.headers.message, 'Booking already cancelled');
        assert.strictEqual(updateCalled, false);
    });

    it('does not cancel bookings outside the authenticated user scope', async () => {
        BookingModel.findOneForUser = async () => null;

        await assert.rejects(
            () => BookingsRepository.cancelForUser({ bookingId: 1, userId: 2 }),
            /Booking not found/
        );
    });
});
