const test = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
const path = require("node:path");

const context = { globalThis: {} };
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(__dirname, "..", "jandarma-soap.js"), "utf8"), context);
const soap = context.globalThis.SyroceJandarmaSoap;
const credentials = { userTc: "11111111110", facilityCode: "198564", password: "secret&safe" };

test("builds official Turkish check-in SOAP contract and escapes credentials", () => {
  const req = soap.buildRequest({
    action: "checkin", nationality: "TR", id_number: "10000000146", room_number: "12",
    check_in: "2026-08-23T10:00:00+03:00",
  }, "checkin", credentials, new Date("2026-08-23T06:00:00Z"));
  assert.equal(req.method, "MusteriKimlikNoGiris");
  assert.match(req.soapAction, /MusteriKimlikNoGiris$/);
  assert.match(req.envelope, /<d:KULLANIMSEKLI>KONAKLAMA<\/d:KULLANIMSEKLI>/);
  assert.match(req.envelope, /secret&amp;safe/);
});

test("builds Turkish checkout with actual checkout type", () => {
  const req = soap.buildRequest({ nationality: "TURKIYE", id_number: "10000000146", check_out: "2026-08-23T12:00:00Z" }, "checkout", credentials);
  assert.equal(req.method, "MusteriKimlikNoCikis");
  assert.match(req.envelope, /<d:CKSTIP>TESISTENCIKIS<\/d:CKSTIP>/);
});

test("builds foreign check-in and rejects unknown country", () => {
  const req = soap.buildRequest({ nationality: "DE", passport_number: "C01X", guest_name: "Ada Lovelace", gender: "female", birth_date: "1990-01-02", check_in: "2026-08-23", room_number: "4" }, "checkin", credentials);
  assert.equal(req.method, "MusteriYabanciGiris");
  assert.match(req.envelope, /<d:ULKKOD>GERMANY<\/d:ULKKOD>/);
  assert.throws(() => soap.buildRequest({ nationality: "XX", passport_number: "P1", guest_name: "A B", birth_date: "1990-01-01", check_in: "2026-08-23" }, "checkin", credentials), /unsupported_foreign_country/);
});

test("uses exact official enum symbols and never guesses foreign gender", () => {
  assert.equal(soap.countryEnum("GB"), "UNITED_KINGDOM");
  assert.equal(soap.countryEnum("Rusya"), "RUSSIAN_FEDERATION");
  assert.throws(() => soap.buildRequest({ nationality: "DE", passport_number: "P1", guest_name: "A B", gender: "", birth_date: "1990-01-01", check_in: "2026-08-23" }, "checkin", credentials), /unsupported_foreign_gender/);
});

test("accepts only Basarili response and exposes official error", () => {
  assert.deepEqual(JSON.parse(JSON.stringify(soap.parseResponse("<x><Basarili>true</Basarili><HataKodu>Basarili</HataKodu><Mesaj>Basarili</Mesaj></x>", "MusteriKimlikNoGiris"))), { ok: true, code: "Basarili", message: "Basarili", method: "MusteriKimlikNoGiris" });
  const failed = soap.parseResponse("<x><Basarili>false</Basarili><HataKodu>YetkiHatasi</HataKodu><Mesaj>IP gecersiz</Mesaj></x>", "MusteriKimlikNoGiris");
  assert.equal(failed.ok, false);
  assert.match(failed.error, /YetkiHatasi.*IP gecersiz/);
});
