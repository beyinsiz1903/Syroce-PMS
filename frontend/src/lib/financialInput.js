import { isMoneyInput, parseMoneyInput } from './moneyInput';

// Financial forms deliberately keep their values as text until submit. This
// makes the decimal separator predictable in every browser locale and avoids
// native number steppers silently changing a monetary value.
const numericPattern = (scale) => new RegExp(`^\\d*(?:[.,]\\d{0,${scale}})?$`);

export const isFinancialDecimalInput = (value, { scale = 2 } = {}) => numericPattern(scale).test(String(value ?? '').trim());

export const parseFinancialDecimal = (value, { scale = 2 } = {}) => {
  const text = String(value ?? '').trim();
  const complete = new RegExp(`^\\d+(?:[.,]\\d{1,${scale}})?$`);
  if (!complete.test(text)) return null;
  const parsed = Number(text.replace(',', '.'));
  return Number.isFinite(parsed) ? parsed : null;
};

export const parseMoney = (value) => typeof value === 'number'
  ? (Number.isFinite(value) ? value : null)
  : parseMoneyInput(value);

export const isMoneyValueInput = (value) => isMoneyInput(value);

export const toMinorUnits = (value) => {
  const amount = parseMoney(value);
  return amount === null ? null : Math.round((amount + Number.EPSILON) * 100);
};

export const fromMinorUnits = (value) => Math.round(Number(value || 0)) / 100;

export const roundMoney = (value) => fromMinorUnits(Math.round((Number(value || 0) + Number.EPSILON) * 100));

export const parseQuantity = (value) => parseFinancialDecimal(value, { scale: 3 });
export const parseExchangeRate = (value) => parseFinancialDecimal(value, { scale: 6 });
export const parseTaxRate = (value) => parseFinancialDecimal(value, { scale: 2 });

export const calculateFinancialLine = ({
  unitAmount = 0,
  quantity = 1,
  discountAmount = 0,
  vatRate = 0,
  exchangeRate = 1,
}) => {
  const unit = parseMoney(unitAmount) ?? 0;
  const count = parseQuantity(quantity) ?? 0;
  const requestedDiscount = parseMoney(discountAmount) ?? 0;
  const rate = parseTaxRate(vatRate) ?? 0;
  const conversion = parseExchangeRate(exchangeRate) ?? 0;
  const subtotal = roundMoney(unit * count);
  const discount = Math.min(subtotal, Math.max(0, roundMoney(requestedDiscount)));
  const net = roundMoney(subtotal - discount);
  const vat = roundMoney(net * Math.max(0, rate) / 100);
  const total = roundMoney(net + vat);
  return {
    unitAmount: roundMoney(unit),
    quantity: count,
    discount,
    vatRate: Math.max(0, rate),
    subtotal,
    net,
    vat,
    total,
    exchangeRate: conversion,
    accountingTotal: conversion > 0 ? roundMoney(total * conversion) : null,
  };
};
