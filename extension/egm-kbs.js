"use strict";

// EGM KBS'nin 2026 Konaklayan Bildirim API'si icin bagimsiz adapter.
// Kimlik bilgisi veya EGMSEC sirri saklamaz; yalnizca tarayicida kullanicinin
// kendisinin actigi mevcut kbs.egm.gov.tr oturumunu kullanir.
(function initEgmKbs(root) {
  const API_BASE = "https://kbs.egm.gov.tr/KbsApiGateway";
  const ZERO_UUID = "00000000-0000-0000-0000-000000000000";

  function text(v) { return String(v == null ? "" : v).trim(); }

  function isTurkish(nationality) {
    const n = text(nationality).toLocaleUpperCase("tr-TR").replace(/[^A-ZÇĞİÖŞÜ]/g, "");
    return ["TR", "TC", "TUR", "TURKIYE", "TÜRKİYE", "TURKEY"].includes(n);
  }

  function splitName(fullName) {
    const parts = text(fullName).split(/\s+/).filter(Boolean);
    if (parts.length < 2) throw new Error("egm_foreign_name_required");
    return { firstName: parts.slice(0, -1).join(" "), lastName: parts.at(-1) };
  }

  function genderCode(gender) {
    const g = text(gender).toLocaleLowerCase("tr-TR");
    if (["male", "m", "erkek", "e", "2"].includes(g)) return 2;
    if (["female", "f", "kadın", "kadin", "k", "1"].includes(g)) return 1;
    throw new Error("egm_foreign_gender_required");
  }

  function countryCode(countries, nationality) {
    const needle = text(nationality).toLocaleUpperCase("tr-TR");
    const row = (Array.isArray(countries) ? countries : []).find((c) => {
      const values = [c.id, c.kod, c.kisaAdi, c.adi, c.ulkeKodu]
        .map((v) => text(v).toLocaleUpperCase("tr-TR"));
      return values.includes(needle);
    });
    const value = row && (row.id ?? row.ulkeKodu ?? row.kod);
    if (value === undefined || value === null || value === "") {
      throw new Error("egm_foreign_country_unsupported");
    }
    return value;
  }

  function buildCheckin(body, countries = []) {
    const room = text(body.room_number);
    if (!room) throw new Error("egm_room_required");
    if (isTurkish(body.nationality) && text(body.id_number)) {
      const id = text(body.id_number);
      if (!/^\d{11}$/.test(id)) throw new Error("egm_tckn_invalid");
      return {
        operation: "KonaklayanTurkVatandasiEkle",
        payload: {
          kimlikNo: Number(id), verilenOda: room, aracPlaka: "",
          adresIlKodu: 0, adresIlceKodu: 0, cepTelefonu: text(body.phone),
          gecerliBelge: text(body.passport_number), gunuBirlikId: ZERO_UUID,
        },
      };
    }
    const passport = text(body.passport_number);
    if (!passport) throw new Error("egm_passport_required");
    const name = splitName(body.guest_name);
    if (!text(body.birth_date)) throw new Error("egm_foreign_birth_date_required");
    return {
      operation: "KonaklayanYabanciEkle",
      payload: {
        gecerliBelge: passport, adi: name.firstName, soyAdi: name.lastName,
        anaAdi: text(body.mother_name), babaAdi: text(body.father_name),
        ulkeKodu: countryCode(countries, body.nationality),
        cinsiyet: genderCode(body.gender), dogumTarihi: text(body.birth_date),
        dogumYeri: text(body.birth_place) || text(body.nationality),
        verilenOda: room, aracPlaka: "", cepTelefonu: text(body.phone),
        adresIlKodu: 0, adresIlceKodu: 0, gunuBirlikId: ZERO_UUID,
      },
    };
  }

  function unwrapList(response) {
    const d = response && response.data;
    if (Array.isArray(d)) return d;
    for (const value of [d?.items, d?.list, d?.data, response?.items, response?.list]) {
      if (Array.isArray(value)) return value;
    }
    return [];
  }

  function selectActiveGuest(response, body) {
    const id = text(body.id_number);
    const passport = text(body.passport_number).toLocaleUpperCase("tr-TR");
    const room = text(body.room_number);
    return unwrapList(response).find((row) => {
      const identityMatch = id
        ? text(row.kimlikNo) === id
        : text(row.gecerliBelge).toLocaleUpperCase("tr-TR") === passport;
      return identityMatch && (!room || text(row.verilenOda) === room);
    }) || null;
  }

  function localReceipt(operation) {
    const a = new Uint8Array(8);
    crypto.getRandomValues(a);
    const suffix = Array.from(a, (b) => b.toString(16).padStart(2, "0")).join("").toUpperCase();
    return `EGM-${operation}-${Date.now()}-${suffix}`;
  }

  root.SyroceEgmKbs = {
    API_BASE, buildCheckin, countryCode, genderCode, isTurkish, localReceipt,
    selectActiveGuest, splitName, unwrapList,
  };
})(globalThis);
