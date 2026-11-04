# decode-uri-component CommonJS compatibility build

Source: https://github.com/SamVerschueren/decode-uri-component/blob/v0.5.1/index.js
License: upstream MIT license in `license`.
Upstream source SHA-256: `6a86ac891edf15c5efa0841ebb31935e3669d58b98318b57d7b08a4530317cb0`.

This is the official 0.5.1 implementation, including the linear-time malformed
percent-encoding fix for GHSA-qr28-fpjm-wq7f. The **only source change** is replacing
`export default function decodeUriComponent` with
`module.exports = function decodeUriComponent`. The algorithm is not rewritten.

Expo Router 57 uses CommonJS query-string 7, which requires a callable CommonJS
decoder. Upstream 0.5.1 is ESM-only; a blind dependency override breaks that
contract. A local package plus an npm override routes every decoder consumer to
this reviewed implementation without changing query-string's API.

The dependency test checks the normalized upstream-source hash, actual
query-string resolution, valid/malformed Unicode, single decoding and a
time-bounded large malformed-input regression in a child process. Do not change
the version or hash merely to satisfy audit. Revisit this compatibility package
when Expo's supported router can consume the patched upstream ESM version.
