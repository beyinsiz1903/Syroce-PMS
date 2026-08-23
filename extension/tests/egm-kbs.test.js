const test = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
const path = require("node:path");

const context = { globalThis: {} };
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(__dirname, "..", "egm-kbs.js"), "utf8"), context);
const egm = context.globalThis.SyroceEgmKbs;

test("builds the current EGM Turkish guest contract", () => {
  const req = egm.buildCheckin({
    nationality: "TR", id_number: "10000000146", room_number: "101", phone: "555",
  });
  assert.equal(req.operation, "KonaklayanTurkVatandasiEkle");
  assert.equal(req.payload.kimlikNo, 10000000146);
  assert.equal(req.payload.verilenOda, "101");
  assert.equal(req.payload.gunuBirlikId, "00000000-0000-0000-0000-000000000000");
});

test("builds a foreign guest contract with strict country and gender mapping", () => {
  const countries = [{ id: 44, kisaAdi: "DE", adi: "ALMANYA" }];
  const req = egm.buildCheckin({
    nationality: "DE", passport_number: "C01X", guest_name: "Ada Lovelace",
    gender: "female", birth_date: "1990-01-02", room_number: "4",
  }, countries);
  assert.equal(req.operation, "KonaklayanYabanciEkle");
  assert.equal(req.payload.adi, "Ada");
  assert.equal(req.payload.soyAdi, "Lovelace");
  assert.equal(req.payload.ulkeKodu, 44);
  assert.equal(req.payload.cinsiyet, 1);
});

test("fails closed for incomplete or ambiguous foreign identity data", () => {
  assert.throws(() => egm.buildCheckin({ nationality: "DE", passport_number: "P1", guest_name: "A B", birth_date: "1990-01-01", room_number: "1" }, [{ id: 1, kisaAdi: "DE" }]), /gender_required/);
  assert.throws(() => egm.buildCheckin({ nationality: "XX", passport_number: "P1", guest_name: "A B", gender: "male", birth_date: "1990-01-01", room_number: "1" }, []), /country_unsupported/);
});

test("selects checkout guest by identity and room from supported response shapes", () => {
  const response = { data: { items: [
    { konaklayanId: "wrong", kimlikNo: 10000000146, verilenOda: "9" },
    { konaklayanId: "right", kimlikNo: 10000000146, verilenOda: "8" },
  ] } };
  assert.equal(egm.selectActiveGuest(response, { id_number: "10000000146", room_number: "8" }).konaklayanId, "right");
  assert.equal(egm.selectActiveGuest(response, { id_number: "10000000146", room_number: "7" }), null);
});
