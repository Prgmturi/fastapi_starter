# Changelog

## [0.6.1](https://github.com/Prgmturi/fastapi_starter/compare/v0.6.0...v0.6.1) (2026-10-25)


### Features

* write every log line as JSON and tie it to the proxy's request id ([#46](https://github.com/Prgmturi/fastapi_starter/issues/46)) ([649cfa6](https://github.com/Prgmturi/fastapi_starter/commit/649cfa68f07bc72e9180d026838d055f04f903bc))

## [0.6.0](https://github.com/Prgmturi/fastapi_starter/compare/v0.5.0...v0.6.0) (2026-10-24)


### ⚠ BREAKING CHANGES

* BaseRepository.get_all() is replaced by get_page(), and DatabaseManager.get_session() is removed.

### Features

* harden the database lifecycle and check migrations in CI ([#42](https://github.com/Prgmturi/fastapi_starter/issues/42)) ([9fac5ee](https://github.com/Prgmturi/fastapi_starter/commit/9fac5ee4f4960c68b4710484bfbadfc932dcba65))

## [0.5.0](https://github.com/Prgmturi/fastapi_starter/compare/v0.4.0...v0.5.0) (2026-10-20)


### ⚠ BREAKING CHANGES

* refuse development values in production and add a public Keycloak URL ([#38](https://github.com/Prgmturi/fastapi_starter/issues/38))

### Features

* refuse development values in production and add a public Keycloak URL ([#38](https://github.com/Prgmturi/fastapi_starter/issues/38)) ([4ece56a](https://github.com/Prgmturi/fastapi_starter/commit/4ece56a492d229cbcc17c584dbf0f5d5aacb2ada))

## [0.4.0](https://github.com/Prgmturi/fastapi_starter/compare/v0.3.0...v0.4.0) (2026-10-17)


### ⚠ BREAKING CHANGES

* error bodies change shape. Clients read status, title and detail instead of message/details or detail.

### Features

* send every error as RFC 9457 and harden the HTTP contract ([#35](https://github.com/Prgmturi/fastapi_starter/issues/35)) ([66f534e](https://github.com/Prgmturi/fastapi_starter/commit/66f534e2d4a6967301df90945015ce6d193b5cc0))

## [0.3.0](https://github.com/Prgmturi/fastapi_starter/compare/v0.2.0...v0.3.0) (2026-10-16)


### ⚠ BREAKING CHANGES

* fastapi_starter.main no longer exposes `app`. Start the server with `uvicorn fastapi_starter.main:create_app --factory`.

### Bug Fixes

* prevent lost writes, reject foreign tokens, survive Keycloak outages ([#34](https://github.com/Prgmturi/fastapi_starter/issues/34)) ([fc81e6b](https://github.com/Prgmturi/fastapi_starter/commit/fc81e6b008853d7ef8c17c8490c558c02680a206))


### Code Refactoring

* build the app in create_app(settings) and make tests hermetic ([#32](https://github.com/Prgmturi/fastapi_starter/issues/32)) ([c50cd26](https://github.com/Prgmturi/fastapi_starter/commit/c50cd268a90b9a4c6b7eee78cee1523cc928c30a))

## [0.2.0](https://github.com/Prgmturi/fastapi_starter/compare/v0.1.0...v0.2.0) (2026-10-09)


### Features

* enhance Docker support and environment configuration ([#25](https://github.com/Prgmturi/fastapi_starter/issues/25)) ([8da4515](https://github.com/Prgmturi/fastapi_starter/commit/8da45152c706e711d4510884c0327fb55cc6cbff))

## 0.1.0 (2026-04-26)


### Features

* add MIT License ([c677f0d](https://github.com/Prgmturi/fastapi_starter/commit/c677f0de92260dbbb345aa76adb501c9ad28a0d2))
* initial release ([db8b328](https://github.com/Prgmturi/fastapi_starter/commit/db8b328e148696fd61738b8d3b568185fbf3001d))


### Bug Fixes

* **ci:** target master branch and silence ESM warning ([#13](https://github.com/Prgmturi/fastapi_starter/issues/13)) ([ac95d3d](https://github.com/Prgmturi/fastapi_starter/commit/ac95d3df9af672419e34f4f28407b9f6a559cc87))
* correct license badge URL in README.md ([8d23eee](https://github.com/Prgmturi/fastapi_starter/commit/8d23eee3210fe4aa029ef070dc25bef5166499ca))
