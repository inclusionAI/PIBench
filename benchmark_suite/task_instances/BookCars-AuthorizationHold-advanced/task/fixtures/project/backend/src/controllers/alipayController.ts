import { Request, Response } from 'express'
import * as logger from '../utils/logger'
import * as bookcarsTypes from ':bookcars-types'
import Booking from '../models/Booking'
import { freeze as alipayFreeze, query as alipayQuery } from '../payment/alipay'

const buildOrderNo = (bookingId: string): string =>
  `BCDEP${bookingId.slice(-8)}${Date.now().toString().slice(-6)}`

/**
 * GET /api/alipay/freeze/:bookingId
 */
export const freeze = async (req: Request, res: Response) => {
  try {
    const { bookingId } = req.params
    const booking = await Booking.findById(bookingId).populate<{ car: any }>('car')
    if (!booking) {
      res.status(404).json({ error: 'Booking not found' })
      return
    }

    const car: any = booking.car
    const deposit = car && typeof car.deposit === 'number' && car.deposit > 0 ? car.deposit : 1
    const amount = deposit.toFixed(2)

    const outOrderNo = buildOrderNo(bookingId)
    const outRequestNo = outOrderNo

    const result = alipayFreeze({
      outOrderNo,
      outRequestNo,
      orderTitle: `BookCars deposit ${bookingId}`,
      amount,
    });

    (booking as any).alipayOutOrderNo = outOrderNo;
    (booking as any).alipayOutRequestNo = outRequestNo;
    (booking as any).alipayAuthStatus = 'INIT'
    booking.status = bookcarsTypes.BookingStatus.Deposit
    await booking.save()

    res.json({
      bookingId,
      schemeUrl: result.schemeUrl,
      amount,
      outOrderNo,
    })
  } catch (err) {
    logger.error('[alipay.freeze] error', err)
    res.status(500).json({ error: String(err) })
  }
}

/**
 * GET /api/alipay/query/:bookingId
 */
export const query = async (req: Request, res: Response) => {
  try {
    const { bookingId } = req.params
    const booking = await Booking.findById(bookingId)
    if (!booking || !(booking as any).alipayOutOrderNo) {
      res.status(404).json({ error: 'No alipay order for this booking' })
      return
    }

    const r = await alipayQuery((booking as any).alipayOutOrderNo, (booking as any).alipayOutRequestNo)
    if (r && r.code === '10000' && r.authNo) {
      (booking as any).alipayAuthNo = r.authNo;
      (booking as any).alipayAuthStatus = r.status || 'AUTHORIZED'
      await booking.save()
    }

    res.json({
      bookingId,
      authNo: (booking as any).alipayAuthNo || null,
      status: (booking as any).alipayAuthStatus || 'INIT',
      raw: r,
    })
  } catch (err) {
    logger.error('[alipay.query] error', err)
    res.status(500).json({ error: String(err) })
  }
}

/**
 * POST /api/alipay/notify
 */
export const notify = async (req: Request, res: Response) => {
  try {
    const body: any = req.body || {}
    logger.info('[alipay.notify] payload', JSON.stringify(body))
    const outOrderNo = body.out_order_no
    const authNo = body.auth_no
    if (outOrderNo && authNo) {
      const booking = await Booking.findOne({ alipayOutOrderNo: outOrderNo })
      if (booking) {
        (booking as any).alipayAuthNo = authNo;
        (booking as any).alipayAuthStatus = body.status || 'AUTHORIZED'
        await booking.save()
      }
    }
    res.send('success')
  } catch (err) {
    logger.error('[alipay.notify] error', err)
    res.send('failure')
  }
}
