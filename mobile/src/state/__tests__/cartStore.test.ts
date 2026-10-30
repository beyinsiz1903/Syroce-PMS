import assert from 'node:assert/strict';
import { test } from 'node:test';
import { useCartStore } from '../cartStore';

const product = { id: 'food', name: 'QA soup', price: 120, currency: 'TRY' };

test('room-service retries retain the consented stay, time, currency and request identity', () => {
  useCartStore.getState().clear();
  useCartStore.getState().bindBooking('stay-one');
  useCartStore.getState().add(product);
  const key = useCartStore.getState().requestId;
  useCartStore.getState().markSubmitted();
  const time = useCartStore.getState().serviceAt;
  useCartStore.getState().markSubmitted();
  useCartStore.getState().add(product);
  useCartStore.getState().setQty('food', 4);
  useCartStore.getState().remove('food');
  assert.equal(useCartStore.getState().requestId, key);
  assert.equal(useCartStore.getState().serviceAt, time);
  assert.equal(useCartStore.getState().count(), 1);
  assert.equal(useCartStore.getState().total(), 120);
  assert.equal(useCartStore.getState().lines[0].currency, 'TRY');
  assert.throws(() => useCartStore.getState().bindBooking('stay-two'));
  useCartStore.getState().clear();
  assert.notEqual(useCartStore.getState().requestId, key);
  assert.equal(useCartStore.getState().bookingId, null);
});

test('unknown/mixed currency, changed price and invalid quantities cannot alter the consented cart', () => {
  useCartStore.getState().clear();
  assert.throws(() => useCartStore.getState().add({ ...product, currency: undefined }));
  assert.throws(() => useCartStore.getState().add({ ...product, price: NaN }));
  useCartStore.getState().add(product);
  assert.throws(() => useCartStore.getState().add({ ...product, id: 'eur', currency: 'EUR' }));
  assert.throws(() => useCartStore.getState().add({ ...product, price: 121 }));
  useCartStore.getState().setQty('food', 1.5);
  assert.equal(useCartStore.getState().count(), 1);
  useCartStore.getState().setQty('food', 20);
  assert.throws(() => useCartStore.getState().add(product));
  assert.equal(useCartStore.getState().count(), 20);
  useCartStore.getState().clear();
});
