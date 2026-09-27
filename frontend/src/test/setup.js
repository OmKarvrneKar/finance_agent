import '@testing-library/jest-dom';

// Mock fetch globally for tests
global.fetch = global.fetch || (() => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }));

// Mock localStorage
const localStorageMock = (() => {
  let store = {};
  return {
    getItem: (key) => store[key] || null,
    setItem: (key, value) => { store[key] = String(value); },
    removeItem: (key) => { delete store[key]; },
    clear: () => { store = {}; },
  };
})();
Object.defineProperty(global, 'localStorage', { value: localStorageMock });

// Mock window.location
delete window.location;
window.location = { href: 'http://localhost:5173/', pathname: '/', origin: 'http://localhost:5173' };
