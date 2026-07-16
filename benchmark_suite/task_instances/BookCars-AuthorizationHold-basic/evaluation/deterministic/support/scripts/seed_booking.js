// Seed a test booking for integration tests.
// Run via: mongosh <uri> --quiet --file seed_booking.js
// Prints: BOOKING_ID:<hex id> on success.

const DB = db.getSiblingDB("bookcars");

const driver = DB.User.findOne({ email: "driver1@bookcars.ma" });
const supplier = DB.User.findOne({ email: "supplier@bookcars.ma" });
const car = DB.Car.findOne({ deposit: { $gt: 0 } });
const loc = DB.Location.findOne({});

if (!driver || !supplier || !car || !loc) {
  print("SEED_BOOKING_ERROR: missing seed data (driver/supplier/car/location)");
  quit(1);
}

const now = new Date();
const from = new Date(now.getTime() + 1 * 86400000);
const to = new Date(now.getTime() + 3 * 86400000);
const cleanBooking = {
  supplier: supplier._id,
  car: car._id,
  driver: driver._id,
  pickupLocation: loc._id,
  dropOffLocation: loc._id,
  from: from,
  to: to,
  status: "pending",
  cancellation: false,
  amendments: false,
  theftProtection: false,
  collisionDamageWaiver: false,
  fullInsurance: false,
  additionalDriver: false,
  isDeposit: false,
  isPayedInFull: false,
  cancelRequest: false,
  price: car.dailyPrice * 2,
  updatedAt: now,
};
const clearAlipayState = {
  alipayOutOrderNo: "",
  alipayOutRequestNo: "",
  alipayAuthNo: "",
  alipayAuthStatus: "",
  alipayFreezeAmount: "",
  alipayPaidAmount: "",
  alipayUnfrozenAmount: "",
  alipayTotalPaidAmount: "",
  alipayTotalUnfreezeAmount: "",
  depositAuthStatus: "",
  depositAuthAmount: "",
  preauthStatus: "",
  preAuthStatus: "",
  authStatus: "",
  authNo: "",
  expireAt: "",
};

let booking = DB.Booking.findOne({ driver: driver._id, car: car._id });
if (booking) {
  DB.Booking.updateOne(
    { _id: booking._id },
    { $set: cleanBooking, $unset: clearAlipayState }
  );
} else {
  const insertedId = DB.Booking.insertOne({
    ...cleanBooking,
    createdAt: now,
  }).insertedId;
  booking = { _id: insertedId };
}

booking = DB.Booking.findOne({ _id: booking._id });

print("BOOKING_ID:" + booking._id.toHexString());
print("CAR_ID:" + car._id.toHexString());
print("LOCATION_ID:" + loc._id.toHexString());
