# Changelog

## [0.8.0](https://github.com/Prgmturi/fastapi_starter/compare/v0.7.2...v0.8.0) (2026-10-28)


### ⚠ BREAKING CHANGES

* the refresh cookie settings and some modules have new names.
    - KEYCLOAK_COOKIE_NAME, KEYCLOAK_COOKIE_SECURE, KEYCLOAK_COOKIE_SAMESITE and KEYCLOAK_COOKIE_PATH are now AUTH_COOKIE_*: the app refuses to start while an old name is set, and names the new one.
    - setup.py is now bootstrap.py, and the Keycloak adapters moved from core/auth/ and features/auth/ to adapters/keycloak/.

### Features

* add the notes example, move the Keycloak adapters and rename the cookie settings ([#61](https://github.com/Prgmturi/fastapi_starter/issues/61)) ([24d4b5a](https://github.com/Prgmturi/fastapi_starter/commit/24d4b5a0d059969912544e1357816f43d3d82972))
* **database:** alembic/env.py finds the models of every feature by itself ([24d4b5a](https://github.com/Prgmturi/fastapi_starter/commit/24d4b5a0d059969912544e1357816f43d3d82972))


### Bug Fixes

* **build:** .python-version pins the Python of development and CI ([24d4b5a](https://github.com/Prgmturi/fastapi_starter/commit/24d4b5a0d059969912544e1357816f43d3d82972))
* **config:** settings errors no longer show the values of .env ([24d4b5a](https://github.com/Prgmturi/fastapi_starter/commit/24d4b5a0d059969912544e1357816f43d3d82972))

## [0.7.2](https://github.com/Prgmturi/fastapi_starter/compare/v0.7.1...v0.7.2) (2026-10-26)


### Bug Fixes

* **deps:** bump fastapi from 0.136.3 to 0.161.1 ([#54](https://github.com/Prgmturi/fastapi_starter/issues/54)) ([738a717](https://github.com/Prgmturi/fastapi_starter/commit/738a7176cbb7c08be6f79637239adeb074114a57))
* **deps:** bump sqlalchemy from 2.0.46 to 2.1.6 ([#53](https://github.com/Prgmturi/fastapi_starter/issues/53)) ([5b76376](https://github.com/Prgmturi/fastapi_starter/commit/5b7637685d207658dd8aecbce531fb89d947b2f4))

## [0.7.1](https://github.com/Prgmturi/fastapi_starter/compare/v0.7.0...v0.7.1) (2026-10-26)


### Bug Fixes

* **deps:** bump keycloak/keycloak ([#50](https://github.com/Prgmturi/fastapi_starter/issues/50)) ([8f680d1](https://github.com/Prgmturi/fastapi_starter/commit/8f680d104a28659eb0930231958bf28566be2c7b))
* **deps:** update pyjwt[crypto] requirement from &gt;=2.11.0 to &gt;=2.15.1 ([#52](https://github.com/Prgmturi/fastapi_starter/issues/52)) ([b59f4d4](https://github.com/Prgmturi/fastapi_starter/commit/b59f4d4a260b7d925246b529975e1d9fbb4a3437))

## [0.7.0](https://github.com/Prgmturi/fastapi_starter/compare/v0.6.1...v0.7.0) (2026-10-26)


### ⚠ BREAKING CHANGES

* the stack starts from compose.yaml, and the image from the SERVER_* settings.
    - docker/docker-compose.yaml, infra/docker-compose.yml and their .env.example files are gone: compose.yaml at the root replaces them, with volumes of its own.
    - the image reads SERVER_FORWARDED_ALLOW_IPS instead of FORWARDED_ALLOW_IPS, and takes its options from the SERVER_* variables: arguments after the image name, such as --port, now replace the command.

### Features

* run the whole stack with docker compose and publish the image of every release ([#48](https://github.com/Prgmturi/fastapi_starter/issues/48)) ([50cc6f9](https://github.com/Prgmturi/fastapi_starter/commit/50cc6f91dac18e300c0f693acadf167d3d151d4c))

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
