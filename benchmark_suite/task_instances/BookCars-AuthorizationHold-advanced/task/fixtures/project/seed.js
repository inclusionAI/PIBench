// BookCars MongoDB seed script — run via: mongosh <uri> seed.js
// Creates: LocationValues, Country, Location, Supplier, Driver, Cars
// Idempotent: skips if Car collection already has data

const DB = db.getSiblingDB("bookcars");

if (DB.getCollection("Car").countDocuments() > 0) {
  print("SEED: data already exists, skipping");
  quit(0);
}

print("SEED: inserting demo data...");

// --- bcrypt hash for "B00kC4r5" (pre-computed, cost=10) ---
const DRIVER_PW_HASH = "$2b$10$JLQBT/VItcnxrXduvnIP7eLBXmsX/anNAiZTV1CcKekMEhVc55jby";
// --- bcrypt hash for "Admin@12345" ---
const ADMIN_PW_HASH = "$2b$10$JLQBT/VItcnxrXduvnIP7eLBXmsX/anNAiZTV1CcKekMEhVc55jby";

// ── LocationValues (en/fr/es for country + locations) ──
const lvMoroccoEn = DB.LocationValue.insertOne({ language: "en", value: "Morocco", createdAt: new Date(), updatedAt: new Date() }).insertedId;
const lvMoroccoFr = DB.LocationValue.insertOne({ language: "fr", value: "Maroc", createdAt: new Date(), updatedAt: new Date() }).insertedId;
const lvMoroccoEs = DB.LocationValue.insertOne({ language: "es", value: "Marruecos", createdAt: new Date(), updatedAt: new Date() }).insertedId;

const lvCasaEn = DB.LocationValue.insertOne({ language: "en", value: "Casablanca", createdAt: new Date(), updatedAt: new Date() }).insertedId;
const lvCasaFr = DB.LocationValue.insertOne({ language: "fr", value: "Casablanca", createdAt: new Date(), updatedAt: new Date() }).insertedId;
const lvCasaEs = DB.LocationValue.insertOne({ language: "es", value: "Casablanca", createdAt: new Date(), updatedAt: new Date() }).insertedId;

const lvMarrakechEn = DB.LocationValue.insertOne({ language: "en", value: "Marrakech", createdAt: new Date(), updatedAt: new Date() }).insertedId;
const lvMarrakechFr = DB.LocationValue.insertOne({ language: "fr", value: "Marrakech", createdAt: new Date(), updatedAt: new Date() }).insertedId;
const lvMarrakechEs = DB.LocationValue.insertOne({ language: "es", value: "Marrakech", createdAt: new Date(), updatedAt: new Date() }).insertedId;

// ── Country ──
const countryId = DB.Country.insertOne({
  values: [lvMoroccoEn, lvMoroccoFr, lvMoroccoEs],
  createdAt: new Date(), updatedAt: new Date()
}).insertedId;

// ── Locations ──
const locCasa = DB.Location.insertOne({
  country: countryId,
  values: [lvCasaEn, lvCasaFr, lvCasaEs],
  latitude: 33.5731,
  longitude: -7.5898,
  parkingSpots: [],
  createdAt: new Date(), updatedAt: new Date()
}).insertedId;

const locMarrakech = DB.Location.insertOne({
  country: countryId,
  values: [lvMarrakechEn, lvMarrakechFr, lvMarrakechEs],
  latitude: 31.6295,
  longitude: -7.9811,
  parkingSpots: [],
  createdAt: new Date(), updatedAt: new Date()
}).insertedId;

// ── Supplier (User type=supplier) ──
const supplierId = DB.User.insertOne({
  fullName: "Demo Rental",
  email: "supplier@bookcars.ma",
  phone: "+212600000001",
  password: ADMIN_PW_HASH,
  type: "supplier",
  verified: true,
  active: true,
  language: "en",
  avatar: "supplier_avatar.png",
  payLater: true,
  licenseRequired: false,
  blacklisted: false,
  enabledLocations: [locCasa, locMarrakech],
  createdAt: new Date(), updatedAt: new Date()
}).insertedId;

// Link supplier to country
DB.Country.updateOne({ _id: countryId }, { $set: { supplier: supplierId } });

// ── Admin user (auto-created by backend, but seed a known one) ──
DB.User.updateOne(
  { email: "admin@bookcars.ma", type: "admin" },
  { $setOnInsert: {
      fullName: "Admin",
      email: "admin@bookcars.ma",
      phone: "+212600000000",
      password: ADMIN_PW_HASH,
      type: "admin",
      verified: true,
      active: true,
      language: "en",
      createdAt: new Date(), updatedAt: new Date()
  }},
  { upsert: true }
);

// ── Driver (frontend test user) ──
DB.User.updateOne(
  { email: "driver1@bookcars.ma" },
  { $setOnInsert: {
      fullName: "Test Driver",
      email: "driver1@bookcars.ma",
      phone: "+212600000002",
      password: DRIVER_PW_HASH,
      type: "user",
      verified: true,
      active: true,
      language: "en",
      birthDate: new Date("1990-01-15"),
      avatar: "driver_avatar.png",
      createdAt: new Date(), updatedAt: new Date()
  }},
  { upsert: true }
);

// ── Cars (3 vehicles with deposit > 0 for preauth testing) ──
const carBase = {
  supplier: supplierId,
  locations: [locCasa, locMarrakech],
  minimumAge: 21,
  available: true,
  fullyBooked: false,
  comingSoon: false,
  aircon: true,
  fuelPolicy: "likeForLike",
  mileage: -1,
  cancellation: -1,
  amendments: -1,
  theftProtection: -1,
  collisionDamageWaiver: -1,
  fullInsurance: -1,
  additionalDriver: -1,
  trips: 0,
  createdAt: new Date(),
  updatedAt: new Date()
};

DB.Car.insertOne({
  ...carBase,
  name: "Toyota Corolla 2024",
  licensePlate: "MA-12345-A",
  dailyPrice: 50,
  deposit: 200,
  type: "gasoline",
  gearbox: "automatic",
  seats: 5,
  doors: 4,
  image: "car_corolla.png",
  range: "midi",
  multimedia: ["bluetooth", "touchscreen"],
  rating: 4,
});

DB.Car.insertOne({
  ...carBase,
  name: "Dacia Duster 2024",
  licensePlate: "MA-67890-B",
  dailyPrice: 35,
  deposit: 150,
  type: "diesel",
  gearbox: "manual",
  seats: 5,
  doors: 4,
  image: "car_duster.png",
  range: "midi",
  multimedia: ["bluetooth"],
  rating: 3,
});

DB.Car.insertOne({
  ...carBase,
  name: "Mercedes C-Class 2024",
  licensePlate: "MA-11111-C",
  dailyPrice: 120,
  deposit: 500,
  type: "gasoline",
  gearbox: "automatic",
  seats: 5,
  doors: 4,
  image: "car_mercedes.png",
  range: "maxi",
  multimedia: ["bluetooth", "touchscreen", "appleCarPlay", "androidAuto"],
  rating: 5,
});

print("SEED: inserted", DB.Car.countDocuments(), "cars,",
  DB.Location.countDocuments(), "locations,",
  DB.Country.countDocuments(), "countries,",
  DB.User.countDocuments(), "users");
print("SEED: done");
