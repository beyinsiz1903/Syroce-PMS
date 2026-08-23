"use strict";

// Jandarma KBS Tesis Web Servisi (WCF/SOAP 1.1) adapter.
// Official contract: SrvShsYtkTml.svc?wsdl. This file has no Chrome APIs so
// request/response behavior can be unit tested outside the extension.
(function initJandarmaSoap(root) {
  const SERVICE_NS = "http://tempuri.org/";
  const DATA_NS = "http://schemas.datacontract.org/2004/07/KBS_Tesis_Servis";
  const MODEL_NS = "http://schemas.datacontract.org/2004/07/KBS_Model";

  const COUNTRY_ALIASES = {
    TR: "TURKIYE", TUR: "TURKIYE", TC: "TURKIYE", TURKIYE: "TURKIYE", "TÜRKİYE": "TURKIYE",
    DE: "GERMANY", DEU: "GERMANY", ALMANYA: "GERMANY", GERMANY: "GERMANY",
    GB: "UNITED_KINGDOM", GBR: "UNITED_KINGDOM", INGILTERE: "UNITED_KINGDOM", "İNGİLTERE": "UNITED_KINGDOM", UNITEDKINGDOM: "UNITED_KINGDOM",
    US: "UNITED_STATES", USA: "UNITED_STATES", ABD: "UNITED_STATES", UNITEDSTATES: "UNITED_STATES",
    FR: "FRANCE", FRA: "FRANCE", FRANSA: "FRANCE", FRANCE: "FRANCE",
    RU: "RUSSIAN_FEDERATION", RUS: "RUSSIAN_FEDERATION", RUSYA: "RUSSIAN_FEDERATION", RUSSIA: "RUSSIAN_FEDERATION", RUSSIANFEDERATION: "RUSSIAN_FEDERATION",
    NL: "NETHERLANDS", NLD: "NETHERLANDS", HOLLANDA: "NETHERLANDS", NETHERLANDS: "NETHERLANDS",
    BE: "BELGIUM", BEL: "BELGIUM", BELCIKA: "BELGIUM", "BELÇİKA": "BELGIUM", BELGIUM: "BELGIUM",
    AT: "AUSTRIA", AUT: "AUSTRIA", AVUSTURYA: "AUSTRIA", AUSTRIA: "AUSTRIA",
    CH: "SWITZERLAND", CHE: "SWITZERLAND", ISVICRE: "SWITZERLAND", "İSVİÇRE": "SWITZERLAND", SWITZERLAND: "SWITZERLAND",
    IT: "ITALY", ITA: "ITALY", ITALYA: "ITALY", "İTALYA": "ITALY", ITALY: "ITALY",
    ES: "SPAIN", ESP: "SPAIN", ISPANYA: "SPAIN", "İSPANYA": "SPAIN", SPAIN: "SPAIN",
    UA: "UKRAINE", UKR: "UKRAINE", UKRAYNA: "UKRAINE", UKRAINE: "UKRAINE",
    IR: "IRAN", IRN: "IRAN", "İRAN": "IRAN", IRAN: "IRAN",
    IQ: "IRAQ", IRQ: "IRAQ", IRAK: "IRAQ", IRAQ: "IRAQ",
    SY: "SYRIAN_ARAB_REPUBLIC", SYR: "SYRIAN_ARAB_REPUBLIC", SURIYE: "SYRIAN_ARAB_REPUBLIC", "SURİYE": "SYRIAN_ARAB_REPUBLIC", SYRIA: "SYRIAN_ARAB_REPUBLIC", SYRIANARABREPUBLIC: "SYRIAN_ARAB_REPUBLIC",
    AZ: "AZERBAIJAN", AZE: "AZERBAIJAN", AZERBAYCAN: "AZERBAIJAN", AZERBAIJAN: "AZERBAIJAN",
    GE: "GEORGIA", GEO: "GEORGIA", GURCISTAN: "GEORGIA", "GÜRCİSTAN": "GEORGIA", GEORGIA: "GEORGIA",
  };

  function escapeXml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&apos;");
  }

  function normalizeText(value) {
    return String(value || "").trim().toUpperCase().replace(/[\s_-]+/g, "");
  }

  function countryEnum(value, customMap) {
    const key = normalizeText(value || "TC");
    const custom = customMap && customMap[key];
    // PMS already stores many nationalities with the official English enum
    // symbol (for example JAPAN). Let the service validate those; short ISO
    // codes must be explicitly mapped so an unknown code is never guessed.
    return custom || COUNTRY_ALIASES[key] || (key.length > 2 ? key : "");
  }

  function isTurkish(payload) {
    return countryEnum(payload.nationality) === "TURKIYE" && /^\d{11}$/.test(String(payload.id_number || ""));
  }

  function toIsoDateTime(value, fallback) {
    const d = new Date(value || fallback || Date.now());
    if (Number.isNaN(d.getTime())) throw new Error("invalid_date");
    return d.toISOString();
  }

  function splitName(fullName) {
    const parts = String(fullName || "").trim().split(/\s+/).filter(Boolean);
    if (parts.length < 2) throw new Error("foreign_guest_name_requires_surname");
    return { firstName: parts.slice(0, -1).join(" "), surname: parts.at(-1) };
  }

  function tag(name, value, prefix = "d") {
    return `<${prefix}:${name}>${escapeXml(value)}</${prefix}:${name}>`;
  }

  function buildRequest(payload, action, credentials, now = new Date()) {
    if (!credentials || !/^\d{11}$/.test(String(credentials.userTc || ""))) throw new Error("invalid_user_tc");
    if (!/^\d{6}$/.test(String(credentials.facilityCode || ""))) throw new Error("invalid_facility_code");
    if (!String(credentials.password || "").trim()) throw new Error("missing_web_service_password");
    if (!payload || !["checkin", "checkout"].includes(action)) throw new Error("invalid_action");

    const turkish = isTurkish(payload);
    const method = turkish
      ? (action === "checkin" ? "MusteriKimlikNoGiris" : "MusteriKimlikNoCikis")
      : (action === "checkin" ? "MusteriYabanciGiris" : "MusteriYabanciCikis");
    const identity = turkish ? String(payload.id_number) : String(payload.passport_number || "").trim();
    if (!identity) throw new Error("missing_guest_identity");

    let fields = "";
    if (turkish && action === "checkin") {
      fields = tag("GRSTRH", toIsoDateTime(payload.check_in, now))
        + tag("ILERITARIHLI", new Date(payload.check_in).getTime() > now.getTime() ? "true" : "false")
        + tag("KIMLIKNO", identity) + tag("KULLANIMSEKLI", "KONAKLAMA")
        + tag("ODANO", payload.room_number) + tag("PLKNO", payload.plate_number || "")
        + tag("TELNO", payload.phone || "") + tag("ULKKOD", "TURKIYE");
    } else if (turkish) {
      fields = tag("CKSTIP", "TESISTENCIKIS") + tag("CKSTRH", toIsoDateTime(payload.check_out, now))
        + tag("KIMLIKNO", identity);
    } else if (action === "checkin") {
      const country = countryEnum(payload.nationality, credentials.countryMap);
      if (!country || country === "TURKIYE") throw new Error("unsupported_foreign_country");
      const name = splitName(payload.guest_name);
      const rawGender = normalizeText(payload.gender);
      const female = rawGender === "F" || rawGender === "FEMALE" || rawGender === "K" || rawGender === "KADIN";
      const male = rawGender === "M" || rawGender === "MALE" || rawGender === "E" || rawGender === "ERKEK";
      if (!female && !male) throw new Error("unsupported_foreign_gender");
      const gender = female ? "KADIN" : "ERKEK";
      fields = tag("ADI", name.firstName) + tag("ANAADI", payload.mother_name || "")
        + tag("BABADI", payload.father_name || "") + tag("BELGENO", identity)
        + tag("CINSIYET", gender) + tag("DOGUMTARIHI", toIsoDateTime(payload.birth_date))
        + tag("GRSTRH", toIsoDateTime(payload.check_in, now))
        + tag("ILERITARIHLI", new Date(payload.check_in).getTime() > now.getTime() ? "true" : "false")
        + tag("KULLANIMSEKLI", "KONAKLAMA")
        + tag("ODANO", payload.room_number) + tag("PLKNO", payload.plate_number || "")
        + tag("SOYADI", name.surname) + tag("TELNO", payload.phone || "") + tag("ULKKOD", country);
    } else {
      fields = tag("BELGENO", identity) + tag("CKSTIP", "TESISTENCIKIS")
        + tag("CKSTRH", toIsoDateTime(payload.check_out, now));
    }

    const envelope = `<?xml version="1.0" encoding="utf-8"?>`
      + `<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">`
      + `<s:Body><${method} xmlns="${SERVICE_NS}">`
      + `<KullaniciTC>${escapeXml(credentials.userTc)}</KullaniciTC>`
      + `<TssKod>${escapeXml(credentials.facilityCode)}</TssKod>`
      + `<Sifre>${escapeXml(credentials.password)}</Sifre>`
      + `<musteri xmlns:d="${DATA_NS}" xmlns:m="${MODEL_NS}">${fields}</musteri>`
      + `</${method}></s:Body></s:Envelope>`;
    return { method, soapAction: `${SERVICE_NS}ISrvShsYtkTml/${method}`, envelope };
  }

  function firstTag(xml, name) {
    const match = new RegExp(`<(?:\\w+:)?${name}(?:\\s[^>]*)?>([\\s\\S]*?)<\\/(?:\\w+:)?${name}>`, "i").exec(xml || "");
    return match ? match[1].replace(/<[^>]+>/g, "").trim() : "";
  }

  function parseResponse(xml, method) {
    const fault = firstTag(xml, "faultstring") || firstTag(xml, "Reason");
    if (fault) return { ok: false, error: `soap_fault: ${fault}` };
    const successful = firstTag(xml, "Basarili").toLowerCase() === "true";
    const code = firstTag(xml, "HataKodu");
    const message = firstTag(xml, "Mesaj");
    if (!successful || (code && !["100", "Basarili"].includes(code))) {
      return { ok: false, error: `jandarma_${code || "unknown"}: ${message || "İşlem reddedildi"}` };
    }
    return { ok: true, code: code || "100", message, method };
  }

  root.SyroceJandarmaSoap = { buildRequest, parseResponse, countryEnum, escapeXml };
})(typeof self !== "undefined" ? self : globalThis);
