# Mini App — Higgsfield-style preset catalog & create screen

**Date:** 2026-06-17
**Status:** Approved (approach A), implementing.

## Goal

Bring the Telegram Mini App to Higgsfield-style UX: a catalog of video/photo
**effect presets** (Видео / Фото / Тренды), and a rich create screen where the
user uploads up to 10 photos, writes a prompt, picks the AI model, and sees the
dynamic 💎 cost. Everything is admin-controllable.

## Decisions (from brainstorming)

- **Home layout:** segmented tabs `Видео / Фото / Тренды` + category pills + a
  2-column card grid; each card shows preview, effect name and `by <author>`.
- **Effect (create) screen:** cover preview → multi-photo upload (≤10, ≤30 MB
  each) → prompt textarea → AI-model picker (recommended preselected, switch
  among compatible) → quality/ratio/duration controls (from the model spec) →
  sticky bottom bar with **dynamic 💎 cost + balance** and the Generate button.
- **Model selection:** recommended model preselected; user can switch among the
  preset's `compatible_models`.
- **Cost/credits:** single 💎 currency. Cost recomputed live from the chosen
  model + params via the existing `cost()` spec functions. Free weekly quota is
  auto-applied first for photo effects (existing behaviour).
- **Catalog:** seeded starter set (~24 presets) + admin CRUD. Preview media
  (image or short video/gif) uploaded via the admin panel; gradient placeholder
  with the name when absent.
- **Approach A:** extend the existing effect tables into presets; reuse the
  existing `PHOTO_SPECS`/`VIDEO_SPECS`, `GenerationJob`, workers, billing.

## Section 1 — Data model

Extend `mini_app_photo_effects` and `mini_app_video_effects` (all new columns
nullable / defaulted, so the migration is additive and safe):

| Column | Type | Purpose |
|--------|------|---------|
| `recommended_model` | `String(40)` | default model key into `*_SPECS` |
| `compatible_models` | `JSON` list[str] | switchable models on the screen |
| `prompt_template` | `Text` | hidden style template; `{prompt}` ← user text |
| `default_params` | `JSON` | starting quality/ratio/duration/mode |
| `max_photos` | `Integer` default 1 | accepted photo count (1…10) |
| `preview_url` | `String(500)` | card preview (photo table gains it too) |
| `is_trending` | `Boolean` default false | show in the Тренды tab |
| `enabled` | `Boolean` default true | on/off from admin |
| `author` | `String(40)` nullable | "by …" attribution |
| `sort_order` | `Integer` default 0 | manual ordering |

Existing columns kept: `effect_id`, `category`, `name_ru`, `name_i18n`,
`thumbnail_url`, `badge`, `gen_count`, `is_ad`, `provider` (video).

A preset is a **style wrapper** over an existing service spec: its
`recommended_model`/`compatible_models` are keys of `PHOTO_SPECS`/`VIDEO_SPECS`.
No spec duplication. Generation reuses `GenerationJob`
(`service`, `model_variant`, `params`, `cost_credits`, `pack_type`).

## Section 2 — API (`api/routers/miniapp.py`)

- `GET /effects?type=photo|video&category=&trending=` → unified list with
  `id, kind, name, author, category, badge, preview_url, recommended_model`.
- `GET /effects/{id}` → full detail: `compatible_models` (each: key, title,
  qualities/ratios/durations/modes from the spec), `default_params`,
  `max_photos`, `preview_url`, plus a `price` map for cost preview.
- `POST /effects/{id}/cost` (body: `{model, params}`) → `{cost, currency:"diamonds"}`
  computed via `spec.cost()`. Lets the UI show live price without spending.
- `POST /effects/{id}/generate` — multipart: `model`, `params` (JSON), `prompt`,
  and `photos[]` (≤ `max_photos`, ≤30 MB each). Server:
  1. validates count/size, model ∈ compatible, params ∈ spec options;
  2. composes final prompt = `prompt_template.format(prompt=user_prompt)`;
  3. charges: free weekly quota (photo) → else `diamonds.try_consume(cost)`;
  4. creates `GenerationJob(service=<spec.key>, model_variant=model, params=…,
     cost_credits=cost, pack_type="diamonds")`, stores uploaded photos;
  5. enqueues the existing worker for that service; returns `{job_id}`.
- Existing `/jobs`, `/jobs/{id}`, `/profile`, `/billing/invoice-link` unchanged.

## Section 3 — Effect (create) screen — `CreateSheet.tsx` rewrite

Vertical scroll sheet:
1. Header: back + effect name.
2. Cover preview (video/img/gradient).
3. Multi-photo strip: thumbnails + `+` tile, counter `n/max`, 30 MB guard,
   remove on tap. Hidden if `max_photos===0` (text-only presets).
4. Prompt `<textarea>` (optional or required per preset).
5. Model picker: chips of `compatible_models`, recommended preselected.
6. Param controls rendered from the chosen model's spec: quality, ratio,
   duration, mode, 4K toggle — only those the spec defines.
7. Sticky bottom bar: `Стоимость N💎 · баланс` + `✨ Сгенерировать N💎`
   (Telegram MainButton). Cost refreshed via `/effects/{id}/cost` (debounced)
   on model/param change.
8. Running → poll job; done → result + share + «создать ещё».

## Section 4 — Home / catalog — `Home.tsx` + new `EffectGrid`

- Segmented control `Видео / Фото / Тренды`.
- Category pills depend on tab (video: dance/emotion/effect/transform; photo:
  female/male/children/couple; trends: all).
- 2-column grid of `EffectCard`: preview (autoplay muted video if preview is a
  video, else img, else gradient), name overlay, `by author`, badge, 💎 hint.
- `Trends.tsx` folds into the Тренды tab (`trending=true`). History/Profile keep
  their tabs.

## Section 5 — Admin panel — Effects CRUD

New «Эффекты» section (mirrors existing admin CRUD pages):
- Table: preview, name, type, category, model, trending, enabled, sort, gens.
- Editor: name (+ i18n), category, provider/recommended_model, compatible_models
  (multi-select from spec keys), prompt_template, default_params (JSON),
  max_photos, author, badge, is_ad, is_trending, enabled, sort_order, and
  preview/thumbnail upload (multipart → stored; URL saved).
- Endpoints under `api/admin/…`: list/create/update/delete + preview upload.
  Guarded by the existing RBAC (moderator+ to edit).

## Section 6 — Migration, seed, i18n, tests

- **Migration** `0002_effect_presets.py`: `add_column` for every new field on
  both tables (additive, reversible `down`).
- **Seed** `scripts/seed_effects.py` (idempotent upsert): ~24 presets — video
  (Kling/Veo/Hailuo/Pika based) + photo (Nano Banana/Seedream/FLUX based) with
  names, categories, recommended/compatible models, prompt templates, default
  params, max_photos, trending flags. No real preview URLs (admin adds later).
- **i18n:** new Mini App keys (tabs, multi-photo hints, model, cost, balance) in
  all 8 locales; new bot/admin strings keep the 8-locale parity test green.
- **Tests:** extend `tests/` — effect list/detail/cost/generate endpoints
  (count/size/model validation, prompt composition, diamond charge + refund),
  seed idempotency, migration upgrade/downgrade. Keep `tsc` green for both SPAs.

## Out of scope / blocked

- **#4 real provider adapters** still stubbed (needs OmniRoute/provider
  contracts). Generation pipeline is exercised end-to-end with stubs.
- Auto-generated previews (rejected option) — admin uploads instead.
