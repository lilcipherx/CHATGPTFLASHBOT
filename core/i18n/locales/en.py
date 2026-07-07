"""English locale — full translation of the user-facing screens.
Missing keys fall back to RU."""

MESSAGES: dict[str, str] = {
    "start.welcome": (
        "Hi! 👋\n\n"
        "I'm SUPER AI BOT, your AI assistant that helps you create text, images, video, music "
        "and much more with modern neural networks.\n\n"
        "🎁 FREE:\n"
        "100 requests per week for text, images and other AI tools.\n\n"
        "⭐️ PREMIUM:\n"
        "Extended access to the most powerful neural networks for text, photo, "
        "video, music and advanced tasks.\n\n"
        "How to use the bot?\n\n"
        "📝 TEXT\nJust write your question or task in the chat — I'll help right away.\n\n"
        "🔎 SEARCH\nUse /s to ask a question with internet search.\n\n"
        "🌅 IMAGES\nTap /photo to create or edit a picture.\n\n"
        "🎬 VIDEO\nTap /video to create a clip.\n\n"
        "🎸 MUSIC\nTap /music to create a song.\n\n"
        "⚙️ MODEL\n/model lets you pick the neural network.\n\n"
        "💎 PREMIUM\n/premium unlocks advanced features.\n\n"
        "Start right now — just send me any message 🚀"
    ),
    "account": (
        "👤 Your account\n\n"
        "Subscription: {sub}\n"
        "Selected model: {model_name} /model\n\n"
        "📊 Usage statistics\n\n"
        "Requests this week: {used}/{limit}\n"
        "✨ Extra requests: {credits} (from referrals and the daily bonus; spent once "
        "your weekly limit runs out)\n\n"
        "Available on the free plan:\n"
        "└ GPT-5 mini\n└ DeepSeek V4\n└ Gemini 3.1 Flash\n└ Perplexity\n"
        "└ GPT Image 2 AI photoshop\n└ Nano Banana 2 AI photoshop\n\n"
        "Need more? Get /premium\n\n"
        "🚀 Premium subscription:\n"
        "└ 100–200 requests per day\n└ GPT-5.5\n└ Gemini 3.5\n└ DeepSeek\n"
        "└ Claude 4.8 Opus and Sonnet\n└ Nano Banana Pro\n└ Document analysis\n\n"
        "🌅 Image pack: {image}\n"
        "└ Midjourney\n└ Midjourney Video\n└ Seedream\n└ Recraft\n└ Flux\n└ Face swap\n\n"
        "🎬 Video pack: {video}\n"
        "└ Kling\n└ Veo 3.1\n└ Seedance 2.0\n└ Grok Imagine\n└ Hailuo\n└ Pika\n\n"
        "🎸 Music pack: {music}\n└ Suno V5.5\n└ Lyria 3 Pro\n\n"
        "📞 Support: {support}"
    ),
    "account.sub_free": "Free ✔️",
    "account.role": "🎭 Role: {title}",
    "account.role_custom": "✍️ custom role",
    "account.sub_premium": "Premium ✔️",
    "account.sub_premium_x2": "Premium X2 ✔️",
    "photo.menu": (
        "🌅 Create and edit images\n\nChoose a service 👇\n\n"
        "🔴 Photo effects — ready-made templates for trendy photos, portraits and avatars.\n\n"
        "💬 GPT Image 2 — OpenAI AI photoshop to generate and edit images from your prompt.\n\n"
        "♊️ Nano Banana Pro — advanced Google AI photoshop for precise editing.\n\n"
        "🖼 Midjourney, Seedream, Recraft and FLUX — popular image generators.\n\n"
        "📸 Avatar pack — upload one photo and get 100 avatars in different styles.\n\n"
        "Pick a service below and start ✨"
    ),
    "video.menu": (
        "🎬 Create video\n\nChoose a service 👇\n\n"
        "🔴 Video effects — ready-made templates for trendy short videos.\n\n"
        "🌱 Seedance 2.0 — video from text, image, video and audio.\n\n"
        "♊ Veo 3.1, Pika and Hailuo — video from a prompt or an uploaded image.\n\n"
        "❎ Grok Imagine and Kling — create and edit videos.\n\n"
        "👨 Kling Effects — bring photos to life with visual effects.\n\n"
        "🎥 Kling Motion — animate an image repeating motion from a reference clip.\n\n"
        "Pick a service below and start ✨"
    ),
    "music.menu": (
        "🎸 Create music\n\nChoose a service 👇\n\n"
        "🎵 Suno V5.5 — full songs up to 8 minutes: music, vocals, lyrics and arrangement.\n\n"
        "♊ Lyria 3 Pro — Google's new service for songs and instrumental music up to 3 minutes.\n\n"
        "Use your own lyrics or let the AI write them ✨"
    ),
    "music.paywall": "🎵 To generate songs, buy a music pack. Tap “Top up” below 👇",
    "search.intro": (
        "🔎 Internet search\n\nPick a search model below or use the default.\n\n"
        "Then send your query — the bot will find fresh info online and prepare an answer 👇"
    ),
    "model.selected": "✅ Model “{name}” selected.",
    "model.premium_locked": "🔒 Model “{name}” is available in /premium only.",
    "settings.lang.choose": "Choose interface language:",
    "settings.lang.saved": "✅ Interface language changed.",
    "settings.context.on": "✅ Context support enabled.",
    "settings.context.off": "❌ Context support disabled.",
    "settings.role.saved": "✅ Role saved.",
    "settings.role.cleared": "Role removed.",
    "settings.role.too_long": "❌ Role too long (max {limit} characters). Please shorten it and send again.",
    "settings.role.current_none": "Current role: not set.",
    "settings.role.current": "Current role:\n{role}",
    "settings.role.prompt": "Send the role (system prompt) the AI should follow.",
    "settings.voice.intro": "Choose a voice for spoken replies (available in /premium):",
    "settings.voice.preview": "Listen to the selected voice",
    "privacy.btn_terms": "📄 Terms of Service",
    "privacy.btn_policy": "📄 Privacy Policy",
    "deletecontext.done": "Context cleared. By default the bot considers your previous question and its answer.",
    "gate.premium": "🔒 This feature is available in /premium only.",
    "gate.pack_empty": "You've run out of pack generations. Tap “Top up” to continue 👇",
    "quota.exceeded.free": "You've used all free requests this week ({used}/{limit}), and your ✨ are gone too.\nInvite friends /invite or claim the daily bonus /bonus for more ✨, or get /premium 🚀",
    "quota.exceeded.premium": "Daily request limit reached ({used}/{limit}) and your ✨ are gone too. It resets tomorrow, or top up ✨ via /invite and /bonus.",
    "docs.prompt": (
        "📄 Working with documents\n\n"
        "Send the bot a file and ask questions about its contents.\n\n"
        "Supported formats:\ndocx, pdf, xlsx, xls, csv, pptx, txt\n\n"
        "Max file size: up to 10 MB\n\n"
        "What you can do:\n"
        "└ get a summary of the document\n└ find specific information\n"
        "└ analyze tables and text\n└ ask questions about the file\n"
        "└ ask to explain, translate or structure the data\n\n"
        "💎 Working with documents requires a /premium subscription.\n\n"
        "⚠️ Each document request costs 3 generations."
    ),
    "ai.unavailable": "⚠️ The AI service is temporarily unavailable. Please try again a bit later.",
    "ai.rate_limit": "✨ The AI is a little busy — just send your message again. Your quota wasn't used.",
    "common.please_wait": "Please wait a moment •••",
    "common.cancelled": "Cancelled.",  # FIX: AUDIT13-L11
    "gdpr.export_ready": "📦 Your data is ready — see the attached file.",  # FIX: AUDIT13-M22
    "common.coming_soon": "🛠 This section is coming soon.",
    "common.banned": "Access to the bot is restricted.",
    # ----- Promo codes -----
    "promo.usage": "Usage: /promo CODE",
    "promo.invalid": "❌ This promo code is invalid or expired.",
    "promo.already": "You have already redeemed this promo code.",
    "promo.ok": "✅ Promo redeemed: +{amount} {reward}.",
    "promo.not_eligible": "❌ This promo code is only for new users.",
    # buttons
    "btn.model": "📝 Choose model",
    "btn.images": "🎨 Create image",
    "btn.search": "🔎 Internet search",
    "btn.search_model": "🔎 Search model: {name}",
    "search.choose_model": "Choose a model for internet search 👇",
    "search.model_set": "✅ Search model: {name}",
    "btn.video": "🎬 Create video",
    "btn.documents": "📄 Document",
    "btn.music": "🎸 Create song",
    "btn.premium": "🚀 Premium",
    "btn.account": "👤 My profile",
    "btn.translate": "🌐 Translate",
    "btn.close": "Close",
    "btn.back": "← Back",
    "btn.connect_premium": "🚀 Get Premium",
    "btn.topup": "🎵 Top up",
    "btn.set_model": "Choose model",
    "btn.set_role": "Role description",
    "btn.set_context": "Context support",
    "btn.set_voice": "Voice replies",
    "btn.set_lang": "Interface language",
    "premium.choose_duration": "Choose subscription period 👇",
    "premium.choose_gateway": "Choose payment method 👇",
    "premium.upgrade_warning": "⚠️ You have an active {current} plan. The remaining time will continue under the new {new} plan.",
    "premium.btn_premium": "⭐ Premium",
    "premium.btn_premium_x2": "🔥 Premium X2",
    "premium.btn_image": "🌅 Image pack",
    "premium.btn_video": "🎬 Video pack",
    "premium.btn_music": "🎸 Music pack",
    "unit.generations": "generations",
    "unit.sec": "sec",
    "vcfg.with_sound": "With sound",
    "vcfg.enhance": "Enhance prompt",
    "vcfg.seed_add": "Add seed",
    "vcfg.seed_set": "seed: {v}",
    "btn.instruction": "❤️ Guide",
    "btn.topup_pay": "💳 Top up",
    "video.image_saved": "🖼 Image added. Now send a description of the video ⚡",
    "video.effects_hint": "🎬 Video effects are available in the Mini App. Open it from the attachment menu 📎",
    "photo.effects_hint": "🎨 Photo effects are available in the Mini App. Open it from the attachments menu 📎",  # FIX: AUDIT13-L13
    "tts.unavailable": "⚠️ Voice playback is temporarily unavailable.",
    "tts.failed": "⚠️ Couldn't voice the reply.",
    "doc.unsupported": "Supported: pdf, docx, doc, xlsx, xls, csv, pptx, txt (up to 10 MB).",
    "doc.too_large": "File too large. Maximum 10 MB.",
    "doc.extract_failed": "Couldn't extract text from the file.",
    "doc.empty": "No text found in the file.",
    "doc.received": "📄 File «{name}» received. Ask questions about it — each request costs {cost} generations.",
    "btn.translate_hint": "🌐 Tap 🌐 under the AI reply to translate it.",
    "voice.selected": "Voice: {voice}",
    "voice.sample": "Hi! This is how the selected voice sounds.",
    "search.nothing": "Nothing found.",
    "btn.open_app": "🚀 Open app",
    # admin-triggered notifications
    "notify.premium_granted": "🎁 You've been gifted Premium for {months} month(s)! Enjoy 💎",
    "notify.premium_revoked": "ℹ️ Your Premium subscription was turned off by an administrator.",
    "notify.banned": "🚫 Your account has been blocked. If this is a mistake, contact support.",
    "notify.unbanned": "✅ Your account has been unblocked. You can use the bot again.",
    "contact.saved": "✅ Thanks! Your phone number was saved.",
    "btn.daily_bonus": "🎁 Daily bonus",
    "bonus.claimed": "🎁 Bonus claimed: +{amount} ✨\nDay streak: {streak} 🔥",
    "bonus.already": "✅ Already claimed today. Come back tomorrow!\nStreak: {streak} 🔥",
    "voice.on": "🔊 Voice: ON",
    "voice.off": "🔇 Voice: OFF",
    "throttle.flood": "⏳ Too many requests. Please wait a moment.",
    "srv.photoeffects": "🎨 Photo effects",
    "srv.videoeffects": "🎬 Video effects",
    "srv.avatar": "👤 Avatar pack",
    "srv.faceswap": "🔄 Face swap",
    "srv.upscale": "📐 Upscale X2/X4",
    "pack.label.popular": "POPULAR",
    "pack.label.best": "BEST VALUE",
    "product.premium": "Premium",
    "product.premium_x2": "Premium X2",
    "pack.name.image": "Image pack",
    "pack.name.video": "Video pack",
    "pack.name.music": "Music pack",
    "duration.1": "1 month",
    "duration.3": "3 months",
    "duration.6": "6 months",
    "duration.12": "1 year",
    "pack.choose": "Choose the «{name}» pack 👇",
    # ----- VIP / loyalty (ТЗ §4) -----
    "btn.vip": "🏅 VIP levels",
    "account.vip": "🏅 Level: {tier} · {left} ⭐ to {next}",
    "account.vip_top": "🏅 Level: {tier} (top)",
    "account.vip_none": "🏅 {left} ⭐ to level {next}",
    "vip.title": "🏅 VIP levels\nYour total spend: {spent} ⭐\n",
    "vip.row": "{mark} {name} — from {min} ⭐ · +{daily}/day, +{weekly}/wk",
    "vip.reached": "🎉 Congrats! You've reached VIP level {tier}!\nYou now get +{daily} generations/day and +{weekly}/week.",
    # ----- global sale (ТЗ §4) -----
    "sale.banner": "🔥 Sale −{percent}%",
    "sale.ends_in": "⏳ ends in: {time}",
    "sale.left_dh": "{d}d {h}h",
    "sale.left_hm": "{h}h {m}m",
    "sale.left_m": "{m}m",
    "pay.sub_invoice_desc": "Subscription: {title}",
    "pay.pack_invoice_desc": "Generation pack: {title}",
    "pay.sub_activated": "✅ Subscription «{title}» activated! Thanks for your purchase 🚀",
    "pay.pack_added": "✅ Pack topped up: +{qty} {unit} ({pack}). Thanks for your purchase!",
    "pay.avatar_paid": "✅ Paid! Send your best selfie — I'll create 100 avatars (~15 min).",
    "pay.link": "Open the link to pay. Access activates automatically after a successful payment 👇",
    "pay.link_btn": "💳 Pay — {title}",
    "pay.unavailable": "This payment method is currently unavailable.",
    "pay.failed": "Couldn't create the invoice. Try another method.",
    "gen.video_started": "🎬 Video generation started! It'll take a few minutes — I'll send the result when ready.",
    "gen.music_started": "🎶 Generating your song — I'll send the audio when ready!",
    "gen.photo_started": "🎨 Applying «{name}» — I'll send the video when ready!",
    "gen.unavailable": "⚠️ Service temporarily unavailable. Please try later.",
    "gen.unavailable_refund": "⚠️ Service temporarily unavailable. Credits refunded.",
    "gen.error_refund": "⚠️ Generation error. Credits refunded.",
    "mod.blocked": "🚫 The request violates the usage rules.",
    "seed.ask": "Enter a seed for generation (a numeric value):",
    "seed.saved": "✅ Seed saved.",
    "avatar.info": (
        "👤 AI avatars\n\nCreate 100 cool avatars for social media in different styles.\n"
        "Price: {price} ⭐ per pack. Resolution 1024×1440, no watermarks.\n"
        "After payment, upload your best selfie — generation ~15 minutes."
    ),
    "avatar.title": "Avatar pack",
    "avatar.buy_btn": "Buy for {price} ⭐",
    "avatar.started": (
        "🎨 Started generating 100 avatars! It'll take ~15 minutes — you can keep "
        "using the bot, I'll send the result when ready."
    ),
    "music.prompt": "🎵 {name}: send a description of the song (style, mood, lyrics).",
    "kling.effects_intro": (
        "🌊 Kling Effects\n\n1. Choose an effect from the options below.\n"
        "2. Send a photo to the bot to apply the chosen effect."
    ),
    "kling.effect_selected": "Effect: {name}\n\nSend a photo and the bot will apply your chosen effect!",
    "kling.motion_intro": (
        "💃 Kling Motion\n\nYour photo will come alive and repeat the motion from a "
        "reference video.\nChoose a template 👇"
    ),
    "kling.motion_selected": "Motion: 💃 {name}. Send a photo — Kling Motion will transfer the motion onto it.",
    "btn.voice": "🔊",
    "btn.view": "🔥 View",
    "gate.subscription": "To keep using the bot for free, subscribe to our channel 👇\nThen tap “I subscribed”.",
    "gate.subscription.ok": "✅ Thanks for subscribing! You can continue.",
    "gate.subscription.fail": "❌ It looks like you haven't subscribed yet.",
    "premium": (
        "🚀 Plans & bot features\n\n"
        "The bot combines popular AI services in one place: text, search, images, "
        "video, music and file analysis.\n\n"
        "🎁 FREE | every week\n\n100 requests of any kind:\n"
        "✅ GPT-5 mini\n✅ DeepSeek V4\n✅ Gemini 3.1 Flash\n✅ Perplexity\n✅ Image recognition\n\n"
        "25 image generations:\n♊️ Nano Banana 2\n✅ GPT Image 2\n\n"
        "💎 PREMIUM | 1 month\n\nLimit: 100 requests/day\n\nIncluded:\n"
        "✅ Everything in Free\n✅ GPT-5.5\n✅ Gemini 3.5 Flash\n✅ Claude 4.8 Opus and Sonnet\n"
        "✅ DeepSeek\n♊️ Nano Banana Pro\n✅ GPT Image 2\n✅ Document analysis\n✅ Voice replies\n✅ No ads\n\n"
        "Price: {p_premium}⭐️\n\n"
        "💎 PREMIUM X2 | 1 month\n\nLimit: 200 requests/day\n\nIncluded:\n"
        "✅ Everything in Premium\n✅ Higher daily limit\n✅ More requests for heavy AI use\n\n"
        "Price: {p_premium_x2}⭐️\n\n"
        "🌅 IMAGES | pack\n\n50 to 500 generations\n\nServices:\n🌅 Midjourney\n🎬 Midjourney Video\n"
        "🌱 Seedream\n🎨 Recraft\n⚡ Flux\n✅ Face swap\n\nFrom {p_image_from}⭐️\n\n"
        "🎬 VIDEO | pack\n\n2 to 50 generations\n\nServices:\n📼 Kling\n🎥 Veo 3.1\n🚀 Seedance 2.0\n"
        "❎ Grok Imagine\n🎞 Hailuo\n✨ Pika\n\nPlus:\n✅ Video editing\n✅ Creative video effects\n\nFrom {p_video_from}⭐️\n\n"
        "🎸 MUSIC | pack\n\n20 to 100 generations\n\nServices:\n🎸 Suno V5.5\n🎼 Lyria 3 Pro\n\n"
        "Features:\n✅ Songs from your own lyrics\n✅ AI-generated lyrics\n\nFrom {p_music_from}⭐️\n\n"
        "⭐️ All prices are in Stars — Telegram's currency.\n\n"
        "💬 Payment & access questions:\n{support}"
    ),
    "model.intro": (
        "🤖 Choose an AI model\n\n"
        "The bot offers leading models for text, code, analysis, math, ideas and complex tasks.\n\n"
        "Choose a model below 👇\n\n"
        "💬 GPT-5.5 — OpenAI's top model for complex tasks. Costs 3 generations per request.\n\n"
        "💬 GPT-5.4 — versatile model for coding and text.\n\n"
        "💬 GPT-5 mini — fast model for everyday questions. Free.\n\n"
        "🌥 Claude 4.8 Opus — Anthropic's top model. Costs 5 generations per request.\n\n"
        "🌥 Claude 4.6 Sonnet — strong for text, coding and math.\n\n"
        "🐳 DeepSeek V4 — fast and powerful for text and code. Free.\n\n"
        "🐳 DeepSeek V4 Pro — advanced DeepSeek for harder tasks.\n\n"
        "♊️ Gemini 3.5 Flash — Google's top model.\n\n"
        "♊️ Gemini 3.1 Flash — fast, smart Google model. Free.\n\n"
        "📌 Documents: in Premium you can send files up to 10 MB and ask about them. Costs 3 generations.\n\n"
        "🎁 Free: GPT-5 mini, Gemini 3.1 Flash, DeepSeek V4\n💎 Other models in Premium: /premium\n\n"
        "Choose a model below 👇"
    ),
    "settings.intro": (
        "⚙️ Bot settings\n\nHere you can tailor the AI to yourself 👇\n\n"
        "1️⃣ Choose model — pick the network that answers you.\n\n"
        "2️⃣ Set role — e.g. assistant, copywriter, programmer, teacher or domain expert.\n\n"
        "3️⃣ Dialogue context — enable/disable. When on, the bot considers its previous answer.\n\n"
        "4️⃣ Voice replies — set up spoken answers and pick a voice. Available in /premium.\n\n"
        "5️⃣ Interface language — choose a comfortable language for menus and messages.\n\n"
        "Choose an item below 👇"
    ),
    "help": (
        "📚 Bot help\n\nMain commands and features.\n\n"
        "📝 Text generation\nJust write your request in the chat. /premium users can also send voice messages.\n\n"
        "Main commands:\n└ /deletecontext — start a new dialogue\n└ /s — internet search\n"
        "└ /settings — model, role, language and context\n└ /model — choose ChatGPT, Claude, Gemini or DeepSeek\n\n"
        "💡 Tip: the more detail you give, the better the answer.\n\n"
        "📄 Documents (Premium)\nUpload a file up to 10 MB and ask about it.\nFormats: docx, pdf, xlsx, xls, csv, pptx, txt.\nEach request costs 3 generations.\n\n"
        "🌅 Images\n└ Nano Banana 2 / Pro\n└ GPT Image 2\n└ Midjourney\n└ Flux\n└ Seedream\n└ Recraft\nCommands: /photo, /midjourney\n\n"
        "🎬 Video\n└ Kling\n└ Seedance 2.0\n└ Pika\n└ Veo 3.1\n└ Hailuo\n└ Grok Imagine\nCommand: /video\n\n"
        "🎸 Music\n└ Suno V5.5\n└ Lyria 3 Pro\nCommands: /music, /suno\n\n"
        "⚙️ Other\n└ /start\n└ /account\n└ /premium\n└ /privacy\n\n"
        "💬 Questions: {support}"
    ),
    "privacy": (
        "🔐 Legal documents\n\nBefore using the bot, please read the rules and data terms:\n\n"
        "1️⃣ Terms of Service\n2️⃣ Privacy Policy\n\n"
        "By continuing to use the bot you confirm that you have read and accept the terms."
    ),
    "gate.channel": "To keep using the bot for free, subscribe to the channel(s) below.\n\nThanks to subscriptions you get 100 free weekly requests to ChatGPT, DeepSeek, Gemini, Perplexity, image generators and more.\n\nWant everything ad-free? Tap Premium.",
    "gate.btn_subscribe": "Subscribe to {channel}",
    "gate.btn_check": "Check subscription",
    "gate.btn_premium": "Premium",
    "gate.ok": "Thanks for subscribing! You can continue.",
    "gate.not_subscribed": "You are not subscribed to all channels yet.",
    "gate.premium_voice": "To send voice requests, get a /premium subscription.",
    "faceswap.step1": "[Step 1/2] Send the image where the face will be changed.",
    "faceswap.step2": "[Step 2/2] Now send the photo with the donor face.",
    "upscale.intro": "This tool increases image resolution. Choose a factor.",
    "upscale.x2": "Upscale X2",
    "upscale.x4": "Upscale X4",
    "upscale.send_image": "Send an image (max 1024x1024). {cost} generations will be charged.",
    "vision.coming_soon": "Image recognition is coming soon.",
    "vision.failed": "Could not process the image. Please try again.",
    "photo.choose": "What should I do with this photo?",
    "photo.btn_describe": "🔎 Describe",
    "photo.btn_edit": "🎨 Edit per caption",
    "photo.edit_working": "🎨 Editing the photo…",
    "photo.edit_done": "✅ Done!",
    "photo.edit_unavailable": "🛠 Photo editing is coming soon.",
    "photo.edit_failed": "Could not edit the photo. Please try again.",
    "photo.edit_no_caption": "Add a caption describing the edit, and I'll change the image.",
    "voice_in.coming_soon": "Voice input is coming soon.",
    "voice_in.heard": "🎙 Heard: «{text}»",
    "voice_in.empty": "Couldn't recognize any speech. Please try recording again.",
    "voice_in.failed": "Couldn't process the voice message. Please try again.",
    "gen.image_started": "Request received! I will send the result when it is ready.",
    "pay.credits_added": "✨ {qty} credits added! Use them in the Mini App.",
    "img.more": "🔄 More",
    "img.upscale": "🔍 Upscale",
    "img.file": "📎 Full quality",
    "img.no_prompt": "Pick a service and send a prompt first.",
    # --- bot UI strings (handlers sweep) ---
    "fb.thanks": "Thanks for the feedback!",
    "report.usage": "Usage: <code>/report description of the problem</code>",
    "report.thanks": "Thank you! Your report has been received.",
    "roles.btn_off": "🚫 Turn off role",
    "roles.btn_custom": "✍️ Custom role",
    "roles.unavailable": "Preset roles are currently unavailable.",
    "roles.choose": "🎭 Choose a preset role for the assistant.",
    "roles.choose_active": "\n\nA custom role is currently active — pick a new one or turn it off.",
    "roles.not_found": "Role not found",
    "roles.enabled": "Role “{title}” enabled ✅",
    "roles.enabled_full": "Done — the assistant now acts as “{title}”. To turn it off, send /roles → “Turn off role”.",
    "roles.disabled": "Role turned off",
    "roles.disabled_full": "Assistant role turned off — normal mode.",
    "contest.none": "No active contests right now. Check back later!",
    "contest.entrants": "Participants: {count}",
    "contest.btn_enter": "Enter",
    "contest.ended": "This contest has already ended.",
    "contest.entered": "You're entered in the contest! Good luck! 🍀",
    "contest.already": "You're already entered in this contest.",
    "gift.btn_premium": "🎁 Premium · 1 mo.",
    "gift.btn_pack": "🎁 Image pack · 50",
    "gift.btn_sub": "🎁 Gift a subscription",
    "gift.btn_pack_menu": "📦 Gift a pack",
    "gift.pack_none": "Packs are unavailable right now.",
    "gift.choose": "🎁 Gift a subscription or pack to a friend.\nChoose what to gift:",
    "gift.invoice_title_sub": "🎁 {product} · {value} mo.",
    "gift.invoice_desc": "Gift: {title}",
    "gift.paid": "🎁 Gift paid!\n\nCode: <code>{code}</code>\n\nSend your friend the command <code>/redeem {code}</code> or this link:\n{link}",
    "redeem.usage": "Usage: <code>/redeem CODE</code>",
    "inline.hint_title": "Enter a question…",
    "inline.hint_text": "Type a question after the bot name to get an AI answer.",
    "inline.error_title": "Error",
    "inline.error_text": "Couldn't get an answer. Please try again later.",
    "inline.throttle_title": "Too frequent",
    "inline.throttle_text": "Too many requests in a row. Wait a moment and try again.",
    "support.usage": "Usage: <code>/support your question</code>\nDescribe the problem — your message will reach support.",
    "support.sent": "Message sent to support, we'll reply soon.",
    "pay.precheckout_unavailable": "Payment unavailable",
    "pay.activate_failed": "⚠️ Couldn't activate the purchase. Your payment (⭐) was refunded. Try again or contact support.",
    "invite.summary": "🔗 Your referral link:\n{link}\n\n👥 Users invited: {count}\n✨ Reward per invite: {reward}\n💰 Total earned: ✨ {earned}",
    "links.none": "No links configured yet.",
    "links.title": "Useful links:",
    "avatar.invoice_desc": "100 AI avatars 1024×1440",
    "promo.reward.credits": "credits",
    "promo.reward.image": "image generations",
    "promo.reward.video": "videos",
    "promo.reward.music": "music tracks",
    "promo.reward.premium": "Premium days",
    "pay.success": "✅ Payment successful! Your access is activated. Thank you for your purchase 🚀",
    "gen.video_ready": "✅ Your video is ready!",
    "gen.song_ready": "✅ Your song is ready!",
    "gen.photo_ready": "✅ Your photo is ready!",
    "gen.avatar_unavailable_refund": "⚠️ The Avatars service is temporarily unavailable. Your payment (⭐) was fully refunded to your Telegram balance. We apologize!",
    "spec.desc.gpt_image2": "Create and edit images right in the chat.\n\nReady to start?\nSend 1 to 4 images you want to edit, or type what you'd like to create.",
    "spec.desc.nano_banana": "Gemini Images — Brighter. Smarter!\n\nCreate and edit images right in the chat. Send 1 to 10 images or type what you'd like to create.",
    "spec.desc.seedream": "Create and edit images right in the chat. Send 1 to 10 images or type what you'd like to create.",
    "spec.desc.midjourney": "Type what image you'd like to create.\n\nThe bot supports all of Midjourney's main parameters and features.",
    "spec.desc.flux2": "Pick an aspect ratio and a Flux model. The Flex and Max models cost 2 generations.\n\nTo start, type what image you'd like to create 🐝",
    "spec.desc.recraft": "Recraft — vector graphics and design. Type what image you'd like to create.",
    "spec.desc.seedance": "Generate video from text, images, video and audio.\n\nSet the options and send a prompt to start ⚡",
    "spec.desc.veo": "Veo 3.1 — cinematic video by Google. Send a prompt ⚡",
    "spec.desc.grok": "Create and edit video. The editor costs 2 generations.\n18+, violence and deepfakes are forbidden. Send a prompt ⚡",
    "spec.desc.kling_ai": "Create and edit video. Send a prompt ⚡",
    "spec.desc.hailuo": "Hailuo — video from a description and an image. Send a prompt ⚡",
    "spec.desc.pika": "Pika Labs — video from a description and images. Send a prompt ⚡",
    "spec.desc.mj_video": "Midjourney Video — image animation. Send a photo and/or a prompt ⚡\nCharged from the image pack.",
    "spec.mode.create": "Create",
    "spec.mode.edit": "Editor",
    "gen.ready_generic": "✅ Your generation ({service}) is ready.",
    "refund.stars": "⚠️ The order could not be completed. Your payment (⭐) was refunded to your Telegram balance. We apologize!",
    "notify.premium_expiry": "⏳ Your Premium expires in {days} day(s). Renew your subscription so you don't lose your higher limits.",
    "notify.low_balance": "✨ Your balance is almost empty — {balance} ✨ left. Top up to keep generating without pauses.",
    "notify.winback": "👋 It's been a while! Come back — we've got new models and effects. Send a request and let's continue 🙌",
    "notify.bonus_available": "🎁 Your daily bonus is ready! Claim it today to keep your streak and earn more ✨.",
    "notify.btn.renew": "⭐ Renew Premium",
    "notify.btn.topup": "✨ Top up",
    "notify.btn.open": "🚀 View plans",
    "notify.btn.bonus": "🎁 Claim bonus",
    "notify.abandoned_cart": "🛒 You were one step from your purchase! Finish it — it takes a minute.",
    "notify.btn.cart": "🛒 Complete purchase",
    "ref.earned_register": "🎉 A new user signed up through your referral link! You earned ✨ {amount}.",
    "ref.welcome_bonus": "🎁 Welcome bonus for joining via a referral link: +✨ {amount}!",
    "promo.welcome_bonus": "🎁 Welcome bonus for a new user: +✨ {amount}!",
    "promo.purchase_bonus": "🎁 Purchase bonus: +✨ {amount}!",
    "promo.applied": "🏷 Promo code applied: −{percent}% on your next purchase!",
    "promo.applied_banner": "🏷 Promo −{percent}% applied",
    "ad.remove_btn": "⭐ Remove ads",
    "ref.milestone": "🏆 You've invited {count} users! Bonus: +✨ {amount}.",
    "ref.earned_purchase": "🎉 A purchase was made through your referral link! You earned ✨ {amount}.",
    "contest.won": "🎉 Congratulations! You won the giveaway!",
    "contest.won_credits": "🎉 Congratulations! You won the giveaway — you got ✨ {amount}!",
    "contest.won_pack": "🎉 Congratulations! You won the giveaway — you got {amount} {unit}!",
    "gift.not_found": "❌ No gift found with that code.",
    "gift.already_used": "❌ This gift has already been activated.",
    "gift.own_gift": "🎁 You can't activate your own gift — share it with a friend.",
    "gift.redeemed_sub": "🎁 Gift activated: {product} for {months} mo.",
    "gift.redeemed_pack": "🎁 Gift activated: {product} pack (+{qty}).",
    "gift.redeemed_credits": "🎁 Gift activated: +{qty} ✨.",
    "gift.unknown_kind": "❌ Unknown gift type.",
}
