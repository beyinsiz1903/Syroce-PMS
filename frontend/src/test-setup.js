import '@testing-library/jest-dom';

const localStorageMock = (function() {
  let store = {};
  return {
    get length() { return Object.keys(store).length; },
    key: function(index) { return Object.keys(store)[index] ?? null; },
    getItem: function(key) { return store[key] || null; },
    setItem: function(key, value) { store[key] = value.toString(); },
    removeItem: function(key) { delete store[key]; },
    clear: function() { store = {}; }
  };
})();
Object.defineProperty(global, 'localStorage', { value: localStorageMock });
