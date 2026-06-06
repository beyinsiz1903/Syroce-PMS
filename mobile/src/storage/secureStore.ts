// Native secure storage — passthrough to expo-secure-store.
//
// Metro/Expo resolves `secureStore.web.ts` for the web build instead of this
// file, so native (iOS/Android) token storage behaviour is unchanged: it
// keeps using the OS keychain/keystore via expo-secure-store.
export { getItemAsync, setItemAsync, deleteItemAsync } from 'expo-secure-store';
