"""Uzbek locale — user-facing screens; long legal/help fall back to RU."""

MESSAGES: dict[str, str] = {
    "start.welcome": (
        "Salom! 👋\n\n"
        "Men SUPER AI BOT, sizning AI-yordamchingizman: zamonaviy neyron tarmoqlar yordamida "
        "matn, rasm, video, musiqa va boshqa koʻp narsalarni yaratishga yordam beraman.\n\n"
        "🎁 BEPUL:\nHaftasiga 100 ta soʻrov — matn, rasm va boshqa AI-vositalar uchun.\n\n"
        "⭐️ PREMIUM:\nEng kuchli neyron tarmoqlarga kengaytirilgan kirish.\n\n"
        "Botdan qanday foydalanish kerak?\n\n"
        "📝 MATN\nSavolingiz yoki vazifangizni chatga yozing — darhol yordam beraman.\n\n"
        "🔎 QIDIRUV\nInternetdan qidirish uchun /s buyrugʻidan foydalaning.\n\n"
        "🌅 RASMLAR\nRasm yaratish yoki tahrirlash uchun /photo bosing.\n\n"
        "🎬 VIDEO\nVideo yaratish uchun /video bosing.\n\n"
        "🎸 MUSIQA\nQoʻshiq yaratish uchun /music bosing.\n\n"
        "⚙️ MODEL\n/model neyron tarmoqni tanlash imkonini beradi.\n\n"
        "💎 PREMIUM\n/premium kengaytirilgan imkoniyatlarni ochadi.\n\n"
        "Hoziroq boshlang — menga istalgan xabar yozing 🚀"
    ),
    "account": (
        "👤 Hisobingiz\n\nObuna: {sub}\nTanlangan model: {model_name} /model\n\n"
        "📊 Foydalanish statistikasi\n\nHaftalik soʻrovlar: {used}/{limit}\n"
        "✨ Qoʻshimcha soʻrovlar: {credits} (referal va kunlik bonusdan; haftalik limit tugagach sarflanadi)\n\n"
        "Bepul rejada mavjud:\n└ GPT-5 mini\n└ DeepSeek V4\n└ Gemini 3.1 Flash\n"
        "└ Perplexity\n└ GPT Image 2\n└ Nano Banana 2\n\n"
        "Koʻproq kerakmi? /premium ulang\n\n"
        "🚀 Premium obuna:\n└ kuniga 100–200 soʻrov\n└ GPT-5.5\n└ Gemini 3.5\n"
        "└ DeepSeek\n└ Claude 4.8 Opus va Sonnet\n└ Nano Banana Pro\n└ Hujjatlar bilan ishlash\n\n"
        "🌅 Rasm paketi: {image}\n🎬 Video paketi: {video}\n🎸 Musiqa paketi: {music}\n\n"
        "📞 Qoʻllab-quvvatlash: {support}"
    ),
    "account.sub_free": "Bepul ✔️",
    "account.role": "🎭 Rol: {title}",
    "account.role_custom": "✍️ o'z roli",
    "account.sub_premium": "Premium ✔️",
    "account.sub_premium_x2": "Premium X2 ✔️",
    "photo.menu": (
        "🌅 Rasm yaratish va tahrirlash\n\nKerakli xizmatni tanlang 👇\n\n"
        "🔴 Foto effektlar\nTrend foto, portret, avatar va kreativ rasmlar uchun tayyor shablonlar.\n\n"
        "💬 GPT Image 2\nOpenAI dan AI-fotoshop: tavsifingiz boʻyicha rasm yaratish va tahrirlash.\n\n"
        "♊️ Nano Banana Pro\nGoogle dan ilgʻor AI-fotoshop: aniq tahrirlash, detallarni almashtirish va rasm sifatini yaxshilash.\n\n"
        "🖼 Midjourney, Seedream, Recraft va FLUX\nArt, realistik foto, dizayn va illyustratsiyalar uchun mashhur generatorlar.\n\n"
        "📸 Avatarlar toʻplami\nBitta foto yuklang — bot turli uslubdagi 100 ta avatar yaratadi.\n\n"
        "Quyidan xizmatni tanlab, rasm yaratishni boshlang ✨"
    ),
    "video.menu": (
        "🎬 Video yaratish\n\nRolik yaratish uchun xizmatni tanlang 👇\n\n"
        "🔴 Video effektlar\nTrend roliklar, qisqa videolar va kreativ effektlar uchun tayyor shablonlar.\n\n"
        "🌱 Seedance 2.0\nMatn, rasm, video va audio asosida video yaratadi.\n\n"
        "♊ Veo 3.1, Pika va Hailuo\nTavsif yoki yuklangan rasm asosida video yaratadi.\n\n"
        "❎ Grok Imagine va Kling\nVideo yaratadi, shuningdek tayyor roliklarni tahrirlashga yordam beradi.\n\n"
        "👨 Kling Effects\nFotolaringizni jonlantiradi va ularga vizual effektlar qoʻshadi.\n\n"
        "🎥 Kling Motion\nVideo-namunadagi harakatlarni takrorlab, rasmni jonlantiradi.\n\n"
        "Quyidan kerakli xizmatni tanlab, video yaratishni boshlang ✨"
    ),
    "music.menu": (
        "🎸 Musiqa yaratish\n\nQoʻshiq yoki musiqa yaratish uchun xizmatni tanlang 👇\n\n"
        "🎵 Suno V5.5\n8 daqiqagacha toʻliq qoʻshiqlar yaratadi: musiqa, vokal, matn va aranjirovka tayyor holda.\n\n"
        "♊ Lyria 3 Pro\nGoogle ning yangi xizmati: 3 daqiqagacha qoʻshiq va instrumental musiqa.\n\n"
        "Oʻz qoʻshiq matningizdan foydalanishingiz yoki AI dan oʻylab topishini soʻrashingiz mumkin ✨"
    ),
    "search.intro": (
        "🔎 Internet qidiruvi\n\n"
        "Quyidan qidiruv modelini tanlang yoki standart modeldan foydalaning.\n\n"
        "Soʻngra chatga soʻrovingizni yozing — bot internetdan dolzarb maʼlumot topib, javob tayyorlaydi 👇"
    ),
    "model.selected": "✅ «{name}» modeli tanlandi.",
    "model.premium_locked": "🔒 «{name}» modeli faqat /premium da mavjud.",
    "settings.lang.choose": "Interfeys tilini tanlang:",
    "settings.lang.saved": "✅ Til oʻzgartirildi.",
    "settings.context.on": "✅ Kontekst yoqildi.",
    "settings.context.off": "❌ Kontekst oʻchirildi.",
    "privacy.btn_terms": "📄 Foydalanuvchi shartnomasi",
    "privacy.btn_policy": "📄 Maxfiylik siyosati",
    "gate.premium": "🔒 Bu funksiya faqat /premium da mavjud.",
    "gate.pack_empty": "Paketdagi generatsiyalar tugadi. «Toʻldirish» tugmasini bosing 👇",
    "quota.exceeded.free": "Bu haftalik bepul soʻrovlaringiz ({used}/{limit}) va ✨ ham tugadi.\nDoʻstlarni taklif qiling /invite yoki kunlik bonus oling /bonus — ✨ koʻpayadi, yoki /premium 🚀",
    "quota.exceeded.premium": "Kunlik limitga yetdingiz ({used}/{limit}), ✨ ham tugadi. Ertaga yangilanadi yoki /invite va /bonus orqali ✨ toʻldiring.",
    "docs.prompt": (
        "📄 Hujjatlar bilan ishlash\n\n"
        "Botga fayl yuboring va uning mazmuni boʻyicha savol bering.\n\n"
        "Qoʻllab-quvvatlanadigan formatlar:\ndocx, pdf, xlsx, xls, csv, pptx, txt\n\n"
        "Maksimal fayl hajmi: 10 MB gacha\n\n"
        "Nima qilish mumkin:\n"
        "└ hujjatning qisqacha mazmunini olish\n└ kerakli maʼlumotni qidirish\n"
        "└ jadval va matnlarni tahlil qilish\n└ fayl boʻyicha savol berish\n"
        "└ maʼlumotlarni tushuntirish, tarjima qilish yoki tuzilmalashtirish\n\n"
        "💎 Hujjatlar bilan ishlash uchun /premium obunasi kerak.\n\n"
        "⚠️ Hujjat boʻyicha har bir soʻrov 3 generatsiya sarflaydi."
    ),
    "ai.unavailable": "⚠️ AI xizmati vaqtincha mavjud emas. Birozdan soʻng urinib koʻring.",
    "ai.rate_limit": "✨ AI biroz band — xabaringizni qayta yuboring. Limit yechilmadi.",
    "common.please_wait": "Biroz kuting •••",
    "common.cancelled": "Bekor qilindi.",  # FIX: AUDIT13-L11
    "gdpr.export_ready": "📦 Ma'lumotlaringiz tayyor — fayl ilova qilindi.",  # FIX: AUDIT13-M22
    "common.coming_soon": "🛠 Bu boʻlim tez orada ishga tushadi.",
    "common.banned": "Botdan foydalanish cheklangan.",
    "btn.model": "📝 Modelni tanlash",
    "btn.images": "🎨 Rasm yaratish",
    "btn.search": "🔎 Internet qidiruv",
    "btn.search_model": "🔎 Qidiruv modeli: {name}",
    "search.choose_model": "Internet qidiruvi uchun modelni tanlang 👇",
    "search.model_set": "✅ Qidiruv modeli: {name}",
    "btn.video": "🎬 Video yaratish",
    "btn.documents": "📄 Hujjat",
    "btn.music": "🎸 Qoʻshiq yaratish",
    "btn.premium": "🚀 Premium",
    "btn.account": "👤 Mening profilim",
    "btn.translate": "🌐 Tarjima",
    "btn.close": "Yopish",
    "btn.back": "← Orqaga",
    "btn.connect_premium": "🚀 Premium ulash",
    "btn.topup": "🎵 Toʻldirish",
    "btn.set_model": "Modelni tanlash",
    "btn.set_role": "Rol tavsifi",
    "btn.set_context": "Kontekst qoʻllab-quvvatlash",
    "btn.set_voice": "Ovozli javoblar",
    "btn.set_lang": "Interfeys tili",
    "premium.choose_duration": "Obuna muddatini tanlang 👇",
    "premium.choose_gateway": "Toʻlov usulini tanlang 👇",
    "premium.upgrade_warning": "⚠️ Sizda {current} tarifi faol. Qolgan vaqt yangi {new} tarifida davom etadi.",
    "premium.btn_premium": "⭐ Premium",
    "premium.btn_premium_x2": "🔥 Premium X2",
    "premium.btn_image": "🌅 Rasm paketi",
    "premium.btn_video": "🎬 Video paketi",
    "premium.btn_music": "🎸 Musiqa paketi",
    "unit.generations": "generatsiya",
    "unit.sec": "son.",
    "vcfg.with_sound": "Ovoz bilan",
    "vcfg.enhance": "Promptni yaxshilash",
    "vcfg.seed_add": "Seed qoʻshish",
    "vcfg.seed_set": "seed: {v}",
    "btn.instruction": "❤️ Qoʻllanma",
    "btn.topup_pay": "💳 Toʻldirish",
    "video.image_saved": "🖼 Rasm qoʻshildi. Endi video tavsifini yuboring ⚡",
    "video.effects_hint": "🎬 Video effektlar Mini App'da mavjud. Uni biriktirma menyusidan oching 📎",
    "photo.effects_hint": "🎨 Foto effektlar Mini App'da mavjud. Uni biriktirmalar menyusidan oching 📎",  # FIX: AUDIT13-L13
    "tts.unavailable": "⚠️ Ovozlashtirish vaqtincha mavjud emas.",
    "tts.failed": "⚠️ Javobni ovozlashtirib boʻlmadi.",
    "doc.unsupported": "Qoʻllab-quvvatlanadi: pdf, docx, doc, xlsx, xls, csv, pptx, txt (10 MB gacha).",
    "doc.too_large": "Fayl juda katta. Maksimum 10 MB.",
    "doc.extract_failed": "Fayldan matn ajratib boʻlmadi.",
    "doc.empty": "Faylda matn topilmadi.",
    "doc.received": "📄 «{name}» fayli qabul qilindi. Savol bering — har bir soʻrov {cost} generatsiya sarflaydi.",
    "btn.translate_hint": "🌐 Tarjima qilish uchun AI javobi ostidagi 🌐 tugmasini bosing.",  # FIX: F37 - was untranslated Cyrillic ИИ
    "voice.selected": "Ovoz: {voice}",
    "voice.sample": "Salom! Tanlangan ovoz shunday eshitiladi.",
    "search.nothing": "Hech narsa topilmadi.",
    "btn.daily_bonus": "🎁 Kunlik bonus",
    "bonus.claimed": "🎁 Bonus olindi: +{amount} ✨ · Seriya: {streak} 🔥",
    "bonus.already": "✅ Bugun allaqachon olingan. Ertaga qayting! · Seriya: {streak} 🔥",
    "notify.premium_granted": "🎁 Sizga {months} oyga Premium sovgʻa qilindi! Yoqimli foydalanish 💎",
    "notify.premium_revoked": "ℹ️ Premium obunangiz administrator tomonidan oʻchirildi.",
    "notify.banned": "🚫 Hisobingiz bloklandi. Agar bu xato boʻlsa — qoʻllab-quvvatlashga murojaat qiling.",
    "notify.unbanned": "✅ Hisobingiz blokdan chiqarildi. Botdan yana foydalanishingiz mumkin.",
    "contact.saved": "✅ Rahmat! Telefon raqamingiz saqlandi.",
    "btn.open_app": "🚀 Ilovani ochish",
    "voice.on": "🔊 Ovoz: YONIQ",
    "voice.off": "🔇 Ovoz: OʻCHIQ",
    "throttle.flood": "⏳ Juda koʻp soʻrov. Biroz kuting.",
    "srv.photoeffects": "🎨 Foto effektlar",
    "srv.videoeffects": "🎬 Video effektlar",
    "srv.avatar": "👤 Avatarlar toʻplami",
    "srv.faceswap": "🔄 Yuzni almashtirish",
    "srv.upscale": "📐 Kattalashtirish X2/X4",
    "pack.label.popular": "OMMABOP",
    "pack.label.best": "ENG YAXSHI TANLOV",
    "product.premium": "Premium",
    "product.premium_x2": "Premium X2",
    "pack.name.image": "Rasm paketi",
    "pack.name.video": "Video paketi",
    "pack.name.music": "Musiqa paketi",
    "duration.1": "1 oy",
    "duration.3": "3 oy",
    "duration.6": "6 oy",
    "duration.12": "1 yil",
    "pack.choose": "«{name}» paketini tanlang 👇",
    # ----- VIP / loyalty (ТЗ §4) -----
    "btn.vip": "🏅 VIP darajalar",
    "account.vip": "🏅 Daraja: {tier} · {next} gacha {left} ⭐",
    "account.vip_top": "🏅 Daraja: {tier} (eng yuqori)",
    "account.vip_none": "🏅 {next} darajasiga {left} ⭐ qoldi",
    "vip.title": "🏅 VIP darajalar\nXaridlaringiz jami: {spent} ⭐\n",
    "vip.row": "{mark} {name} — {min} ⭐ dan · +{daily}/kun, +{weekly}/hafta",
    "vip.reached": "🎉 Tabriklaymiz! Siz {tier} VIP darajasiga yetdingiz.\nEndi sizda +{daily} generatsiya/kun va +{weekly}/hafta.",
    # ----- global sale (ТЗ §4) -----
    "sale.banner": "🔥 Chegirma −{percent}%",
    "sale.ends_in": "⏳ tugashiga: {time}",
    "sale.left_dh": "{d}k {h}s",
    "sale.left_hm": "{h}s {m}d",
    "sale.left_m": "{m}d",
    "pay.sub_invoice_desc": "Obuna: {title}",
    "pay.pack_invoice_desc": "Generatsiya paketi: {title}",
    "pay.sub_activated": "✅ «{title}» obunasi faollashtirildi! Xaridingiz uchun rahmat 🚀",
    "pay.pack_added": "✅ Paket toʻldirildi: +{qty} {unit} ({pack}). Xaridingiz uchun rahmat!",
    "pay.avatar_paid": "✅ Toʻlandi! Eng yaxshi selfingizni yuboring — 100 ta avatar yarataman (~15 daqiqa).",
    "pay.link": "Toʻlash uchun havolani oching. Muvaffaqiyatli toʻlovdan soʻng kirish avtomatik faollashadi 👇",
    "pay.link_btn": "💳 Toʻlash — {title}",
    "pay.unavailable": "Bu toʻlov usuli hozir mavjud emas.",
    "pay.failed": "Hisob-faktura yaratib boʻlmadi. Boshqa usulni sinab koʻring.",
    "gen.video_started": "🎬 Video generatsiyasi boshlandi! Bir necha daqiqa vaqt oladi — tayyor boʻlganda natijani yuboraman.",
    "gen.music_started": "🎶 Qoʻshiq yaratyapman — tayyor boʻlganda audio yuboraman!",
    "gen.photo_started": "🎨 «{name}» qoʻllanyapti — tayyor boʻlganda video yuboraman!",
    "gen.unavailable": "⚠️ Xizmat vaqtincha mavjud emas. Keyinroq urinib koʻring.",
    "gen.unavailable_refund": "⚠️ Xizmat vaqtincha mavjud emas. Kreditlar qaytarildi.",
    "gen.error_refund": "⚠️ Generatsiya xatosi. Kreditlar qaytarildi.",
    "mod.blocked": "🚫 Soʻrov foydalanish qoidalarini buzadi.",
    "seed.ask": "Generatsiya uchun seed kiriting (raqamli qiymat):",
    "seed.saved": "✅ Seed saqlandi.",
    "avatar.info": (
        "👤 AI-avatarlar\n\nIjtimoiy tarmoqlar uchun turli uslublardagi 100 ta avatar yarating.\n"
        "Narxi: {price} ⭐ paket uchun. Oʻlcham 1024×1440, suv belgilarisiz.\n"
        "Toʻlovdan soʻng eng yaxshi selfingizni yuklang — generatsiya ~15 daqiqa."
    ),
    "avatar.title": "Avatarlar toʻplami",
    "avatar.buy_btn": "{price} ⭐ ga sotib olish",
    "avatar.started": (
        "🎨 100 ta avatar generatsiyasi boshlandi! ~15 daqiqa vaqt oladi — botdan "
        "foydalanishda davom etishingiz mumkin, tayyor boʻlganda natijani yuboraman."
    ),
    "music.prompt": "🎵 {name}: qoʻshiq tavsifini yuboring (uslub, kayfiyat, matn).",
    "kling.effects_intro": (
        "🌊 Kling Effects\n\n1. Quyidagi variantlardan effektni tanlang.\n"
        "2. Tanlangan effektni qoʻllash uchun botga rasm yuboring."
    ),
    "kling.effect_selected": "Effekt: {name}\n\nBotga rasm yuboring va u tanlangan effektni qoʻllaydi!",
    "kling.motion_intro": (
        "💃 Kling Motion\n\nFotongiz jonlanadi va video-namunadagi harakatni takrorlaydi.\n"
        "Shablonni tanlang 👇"
    ),
    "kling.motion_selected": "Harakat: 💃 {name}. Rasm yuboring — Kling Motion harakatni unga koʻchiradi.",
    "btn.voice": "🔊",
    "btn.view": "🔥 Koʻrish",
    "deletecontext.done": "Kontekst tozalandi. Bot odatda oldingi savolingiz va javobini hisobga oladi.",
    "music.paywall": "🎵 Qoʻshiq yaratish uchun musiqa paketini sotib oling. «Toʻldirish» tugmasini bosing 👇",
    "gate.subscription": "Botdan bepul foydalanishda davom etish uchun kanalimizga obuna boʻling 👇\nSoʻng «Obuna boʻldim» tugmasini bosing.",
    "gate.subscription.ok": "✅ Obuna uchun rahmat! Davom etishingiz mumkin.",
    "gate.subscription.fail": "❌ Hali obuna boʻlmaganga oʻxshaysiz.",
    "settings.role.prompt": "AI rioya qiladigan rol (tizim prompti) matnini yuboring.",
    "settings.role.current_none": "Joriy rol: oʻrnatilmagan.",
    "settings.role.current": "Joriy rol:\n{role}",
    "settings.role.saved": "✅ Rol saqlandi.",
    "settings.role.cleared": "Rol oʻchirildi.",
    "settings.role.too_long": "❌ Rol juda uzun (koʻpi bilan {limit} belgi). Qisqartirib qayta yuboring.",
    "settings.voice.intro": "Ovozli javoblar uchun ovozni tanlang (/premium da mavjud):",
    "settings.voice.preview": "Tanlangan ovozni tinglash",
    "settings.intro": (
        "⚙️ Bot sozlamalari\n\nBu boʻlimda AI ishini oʻzingizga moslaysiz 👇\n\n"
        "1️⃣ Modelni tanlash — soʻrovlaringizga javob beradigan tarmoq.\n\n"
        "2️⃣ Rol belgilash — masalan: yordamchi, kopirayter, dasturchi, oʻqituvchi yoki ekspert.\n\n"
        "3️⃣ Dialog konteksti — yoqing yoki oʻchiring. Yoqilgan boʻlsa, bot oldingi javobini hisobga oladi.\n\n"
        "4️⃣ Ovozli javoblar — ovozlashtirishni sozlang va ovozni tanlang. /premium da mavjud.\n\n"
        "5️⃣ Interfeys tili — qulay tilni tanlang.\n\n"
        "Quyidan bandni tanlang 👇"
    ),
    "model.intro": (
        "🤖 AI modelini tanlash\n\nMatn, kod, tahlil va murakkab vazifalar uchun yetakchi modellar.\n\n"
        "Quyidan modelni tanlang 👇\n\n"
        "💬 GPT-5.5 — OpenAI top modeli. Har soʻrov 3 generatsiya sarflaydi.\n\n"
        "💬 GPT-5.4 — kod va matnlar uchun universal model.\n\n"
        "💬 GPT-5 mini — kundalik savollar uchun tez model. Bepul.\n\n"
        "🌥 Claude 4.8 Opus — Anthropic top modeli. Har soʻrov 5 generatsiya sarflaydi.\n\n"
        "🌥 Claude 4.6 Sonnet — matn, kod va matematika uchun kuchli.\n\n"
        "🐳 DeepSeek V4 — tez va kuchli. Bepul.\n\n"
        "🐳 DeepSeek V4 Pro — DeepSeek ning kengaytirilgan versiyasi.\n\n"
        "♊️ Gemini 3.5 Flash — Google top modeli.\n\n"
        "♊️ Gemini 3.1 Flash — tez va aqlli Google modeli. Bepul.\n\n"
        "📌 Hujjatlar: Premium da 10 MB gacha fayl yuborishingiz mumkin. 3 generatsiya sarflaydi.\n\n"
        "🎁 Bepul: GPT-5 mini, Gemini 3.1 Flash, DeepSeek V4\n💎 Boshqa modellar Premium da: /premium\n\n"
        "Quyidan modelni tanlang 👇"
    ),
    "help": (
        "📚 Bot yordami\n\nAsosiy buyruqlar va imkoniyatlar.\n\n"
        "📝 Matn yaratish\nSoʻrovingizni chatga yozing. /premium foydalanuvchilari ovozli xabar ham yuborishi mumkin.\n\n"
        "Buyruqlar:\n└ /deletecontext — yangi dialog\n└ /s — internetdan qidirish\n"
        "└ /settings — model, rol, til va kontekst\n└ /model — modelni tanlash\n\n"
        "💡 Qanchalik batafsil yozsangiz, javob shunchalik aniq boʻladi.\n\n"
        "📄 Hujjatlar (Premium)\n10 MB gacha fayl yuklang va savol bering.\nFormatlar: docx, pdf, xlsx, xls, csv, pptx, txt.\nHar soʻrov 3 generatsiya sarflaydi.\n\n"
        "🌅 Rasmlar\n└ Nano Banana 2 / Pro\n└ GPT Image 2\n└ Midjourney\n└ Flux\n└ Seedream\n└ Recraft\nBuyruqlar: /photo, /midjourney\n\n"
        "🎬 Video\n└ Kling\n└ Seedance 2.0\n└ Pika\n└ Veo 3.1\n└ Hailuo\n└ Grok Imagine\nBuyruq: /video\n\n"
        "🎸 Musiqa\n└ Suno V5.5\n└ Lyria 3 Pro\nBuyruqlar: /music, /suno\n\n"
        "⚙️ Boshqa\n└ /start\n└ /account\n└ /premium\n└ /privacy\n\n"
        "💬 Savollar: {support}"
    ),
    "privacy": (
        "🔐 Huquqiy hujjatlar\n\nBotdan foydalanishdan oldin qoidalar va maʼlumotlarni qayta ishlash shartlari bilan tanishing:\n\n"
        "1️⃣ Foydalanuvchi shartnomasi\n2️⃣ Maxfiylik siyosati\n\n"
        "Botdan foydalanishni davom ettirib, siz ular bilan tanishganingizni va qabul qilganingizni tasdiqlaysiz."
    ),
    "premium": (
        "🚀 Tariflar va imkoniyatlar\n\nBot mashhur AI-xizmatlarni birlashtiradi: matn, qidiruv, rasm, video, musiqa va fayllar.\n\n"
        "🎁 BEPUL | har hafta\n\n100 ta soʻrov:\n✅ GPT-5 mini\n✅ DeepSeek V4\n✅ Gemini 3.1 Flash\n✅ Perplexity\n✅ Rasmni tanish\n\n"
        "25 ta rasm generatsiyasi:\n♊️ Nano Banana 2\n✅ GPT Image 2\n\n"
        "💎 PREMIUM | 1 oy\n\nLimit: kuniga 100 soʻrov\n\n✅ Bepul tarifning hammasi\n✅ GPT-5.5\n✅ Gemini 3.5 Flash\n✅ Claude 4.8 Opus va Sonnet\n✅ DeepSeek\n♊️ Nano Banana Pro\n✅ GPT Image 2\n✅ Hujjatlar\n✅ Ovozli javoblar\n✅ Reklamasiz\n\nNarxi: {p_premium}⭐️\n\n"
        "💎 PREMIUM X2 | 1 oy\n\nLimit: kuniga 200 soʻrov\n\n✅ Premium ning hammasi\n✅ Kattaroq kunlik limit\n\nNarxi: {p_premium_x2}⭐️\n\n"
        "🌅 RASMLAR | paket\n\n50 dan 500 gacha generatsiya tanlovi\n\nMavjud xizmatlar:\n"
        "🌅 Midjourney\n🎬 Midjourney Video\n🌱 Seedream\n🎨 Recraft\n⚡ Flux\n✅ Fotoda yuzni almashtirish\n\nNarxi: {p_image_from}⭐️ dan\n\n"
        "🎬 VIDEO | paket\n\n2 dan 50 gacha generatsiya tanlovi\n\nMavjud xizmatlar:\n"
        "📼 Kling\n🎥 Veo 3.1\n🚀 Seedance 2.0\n❎ Grok Imagine\n🎞 Hailuo\n✨ Pika\n\n"
        "Qoʻshimcha:\n✅ Video tahrirlash\n✅ Kreativ video effektlar\n\nNarxi: {p_video_from}⭐️ dan\n\n"
        "🎸 MUSIQA | paket\n\n20 dan 100 gacha generatsiya tanlovi\n\nMavjud xizmatlar:\n"
        "🎸 Suno V5.5\n🎼 Lyria 3 Pro\n\nImkoniyatlar:\n✅ Oʻz sheʼringiz boʻyicha qoʻshiq\n✅ AI yordamida qoʻshiq matni\n\nNarxi: {p_music_from}⭐️ dan\n\n"
        "⭐️ Barcha narxlar Stars — Telegram valyutasida.\n\n💬 Toʻlov va ulanish:\n{support}"
    ),
    "gate.channel": "Botdan bepul foydalanishni davom ettirish uchun quyidagi kanallarga obuna boling.\n\nObunalar tufayli har hafta ChatGPT, DeepSeek, Gemini, Perplexity, rasm generatorlari va boshqalarga 100 ta bepul sorov olasiz.\n\nHammasini reklamasiz xohlaysizmi? Premium tugmasini bosing.",
    "gate.btn_subscribe": "{channel} ga obuna bolish",
    "gate.btn_check": "Obunani tekshirish",
    "gate.btn_premium": "Premium",
    "gate.ok": "Obuna uchun rahmat! Davom etishingiz mumkin.",
    "gate.not_subscribed": "Siz hali barcha kanallarga obuna bolmagansiz.",
    "gate.premium_voice": "Ovozli sorovlar yuborish uchun /premium obunasini ulang.",
    "faceswap.step1": "[1/2-qadam] Yuzi ozgartiriladigan rasmni yuboring.",
    "faceswap.step2": "[2/2-qadam] Endi donor yuzli rasmni yuboring.",
    "upscale.intro": "Ushbu vosita rasm olchamini oshiradi. Koeffitsientni tanlang.",
    "upscale.x2": "X2 kattalashtirish",
    "upscale.x4": "X4 kattalashtirish",
    "upscale.send_image": "Rasm yuboring (maksimal 1024x1024). {cost} generatsiya hisobdan yechiladi.",
    "vision.coming_soon": "Rasmni tanib olish tez orada ishga tushadi.",
    "vision.failed": "Rasmni qayta ishlab bolmadi. Qayta urinib koring.",
    "photo.choose": "Bu rasm bilan nima qilay?",
    "photo.btn_describe": "🔎 Tavsiflash",
    "photo.btn_edit": "🎨 Izoh boyicha ozgartirish",
    "photo.edit_working": "🎨 Rasm tahrirlanmoqda…",
    "photo.edit_done": "✅ Tayyor!",
    "photo.edit_unavailable": "🛠 Rasmni tahrirlash tez orada ishga tushadi.",
    "photo.edit_failed": "Rasmni tahrirlab bolmadi. Qayta urinib koring.",
    "photo.edit_no_caption": "Rasmga ozgartirishni tavsiflovchi izoh qoshing, men rasmni ozgartiraman.",
    "voice_in.coming_soon": "Ovozli kiritish tez orada ishga tushadi.",
    "voice_in.heard": "🎙 Tanildi: «{text}»",
    "voice_in.empty": "Nutqni aniqlab bo'lmadi. Qaytadan yozib ko'ring.",
    "voice_in.failed": "Ovozli xabarni qayta ishlab bo'lmadi. Qaytadan urinib ko'ring.",
    "gen.image_started": "Sorov qabul qilindi! Tayyor bolganda natijani yuboraman.",
    "pay.credits_added": "✨ {qty} kredit qoʻshildi! Mini-ilovada ishlating.",
    "img.more": "🔄 Yana",
    "img.upscale": "🔍 Kattalashtirish",
    "img.file": "📎 Toʻliq sifat",
    "img.no_prompt": "Avval xizmatni tanlang va prompt yuboring.",
    "promo.usage": "Foydalanish: /promo KOD",
    "promo.invalid": "❌ Promokod yaroqsiz yoki muddati tugagan.",
    "promo.already": "Siz bu promokodni allaqachon faollashtirgansiz.",
    "promo.ok": "✅ Promokod faollashtirildi: +{amount} {reward}.",
    "promo.not_eligible": "❌ Bu promokod faqat yangi foydalanuvchilar uchun.",
    # --- bot UI strings (handlers sweep) ---
    "fb.thanks": "Baho uchun rahmat!",
    "report.usage": "Foydalanish: <code>/report muammo tavsifi</code>",
    "report.thanks": "Rahmat! Shikoyatingiz qabul qilindi.",
    "roles.btn_off": "🚫 Rolni o'chirish",
    "roles.btn_custom": "✍️ O'z roli",
    "roles.unavailable": "Tayyor rollar hozircha mavjud emas.",
    "roles.choose": "🎭 Yordamchi uchun tayyor rolni tanlang.",
    "roles.choose_active": "\n\nHozir maxsus rol yoqilgan — yangisini tanlang yoki o'chiring.",
    "roles.not_found": "Rol topilmadi",
    "roles.enabled": "«{title}» roli yoqildi ✅",
    "roles.enabled_full": "Tayyor — yordamchi endi «{title}» sifatida ishlaydi. O'chirish uchun /roles → «Rolni o'chirish» yuboring.",
    "roles.disabled": "Rol o'chirildi",
    "roles.disabled_full": "Yordamchi roli o'chirildi — oddiy rejim.",
    "contest.none": "Hozir faol konkurslar yo'q. Keyinroq qarab turing!",
    "contest.entrants": "Ishtirokchilar: {count}",
    "contest.btn_enter": "Ishtirok etish",
    "contest.ended": "Bu konkurs allaqachon yakunlangan.",
    "contest.entered": "Siz konkursda ishtirok etyapsiz! Omad! 🍀",
    "contest.already": "Siz bu konkursda allaqachon ishtirok etyapsiz.",
    "gift.btn_premium": "🎁 Premium · 1 oy",
    "gift.btn_pack": "🎁 Rasm to'plami · 50",
    "gift.btn_sub": "🎁 Obuna sovgʻa qilish",
    "gift.btn_pack_menu": "📦 Paket sovgʻa qilish",
    "gift.pack_none": "Paketlar hozircha mavjud emas.",
    "gift.choose": "🎁 Do'stingizga obuna yoki to'plam sovg'a qiling.\nNimani sovg'a qilishni tanlang:",
    "gift.invoice_title_sub": "🎁 {product} · {value} oy",
    "gift.invoice_desc": "Sovg'a: {title}",
    "gift.paid": "🎁 Sovg'a to'landi!\n\nKod: <code>{code}</code>\n\nDo'stingizga <code>/redeem {code}</code> buyrug'ini yoki ushbu havolani yuboring:\n{link}",
    "redeem.usage": "Foydalanish: <code>/redeem KOD</code>",
    "inline.hint_title": "Savol kiriting…",
    "inline.hint_text": "AI javobini olish uchun bot nomidan keyin savol yozing.",
    "inline.error_title": "Xato",
    "inline.error_text": "Javob olib bo'lmadi. Keyinroq urinib ko'ring.",
    "inline.throttle_title": "Juda tez-tez",
    "inline.throttle_text": "Ketma-ket juda ko'p so'rov. Biroz kuting va qaytadan urinib ko'ring.",
    "support.usage": "Foydalanish: <code>/support savolingiz</code>\nMuammoni tasvirlang — xabaringiz qo'llab-quvvatlashga yetib boradi.",
    "support.sent": "Xabar qo'llab-quvvatlashga yuborildi, tez orada javob beramiz.",
    "pay.precheckout_unavailable": "To'lov mavjud emas",
    "pay.activate_failed": "⚠️ Xaridni faollashtirib bo'lmadi. To'lovingiz (⭐) qaytarildi. Qaytadan urinib ko'ring yoki qo'llab-quvvatlashga yozing.",
    "invite.summary": "🔗 Sizning referal havolangiz:\n{link}\n\n👥 Taklif qilingan foydalanuvchilar: {count}\n✨ Har bir taklif uchun mukofot: {reward}\n💰 Jami ishlab topilgan: ✨ {earned}",
    "links.none": "Hali havolalar sozlanmagan.",
    "links.title": "Foydali havolalar:",
    "avatar.invoice_desc": "100 ta AI-avatar 1024×1440",
    "promo.reward.credits": "kredit",
    "promo.reward.image": "rasm",
    "promo.reward.video": "video",
    "promo.reward.music": "musiqa",
    "promo.reward.premium": "kun Premium",
    "pay.success": "✅ To'lov muvaffaqiyatli! Kirish faollashtirildi. Xaridingiz uchun rahmat 🚀",
    "gen.video_ready": "✅ Videongiz tayyor!",
    "gen.song_ready": "✅ Qoʻshigʻingiz tayyor!",
    "gen.photo_ready": "✅ Rasmingiz tayyor!",
    "gen.avatar_unavailable_refund": "⚠️ «Avatarlar» xizmati vaqtincha ishlamayapti. Toʻlovingiz (⭐) Telegram balansingizga toʻliq qaytarildi. Uzr soʻraymiz!",
    "spec.desc.gpt_image2": "Rasmlarni to'g'ridan-to'g'ri chatda yarating va tahrirlang.\n\nBoshlashga tayyormisiz?\nTahrirlamoqchi bo'lgan 1 dan 4 tagacha rasm yuboring yoki nima yaratmoqchi ekaningizni yozing.",
    "spec.desc.nano_banana": "Gemini Images — Yanada yorqin. Yanada aqlli!\n\nRasmlarni chatda yarating va tahrirlang. 1 dan 10 tagacha rasm yuboring yoki nima yaratmoqchi ekaningizni yozing.",
    "spec.desc.seedream": "Rasmlarni chatda yarating va tahrirlang. 1 dan 10 tagacha rasm yuboring yoki nima yaratmoqchi ekaningizni yozing.",
    "spec.desc.midjourney": "Qanday rasm yaratmoqchi ekaningizni yozing.\n\nBot Midjourney'ning barcha asosiy parametr va imkoniyatlarini qo'llab-quvvatlaydi.",
    "spec.desc.flux2": "Nisbat va Flux modelini tanlang. Flex va Max modellari 2 generatsiya sarflaydi.\n\nBoshlash uchun qanday rasm yaratmoqchi ekaningizni yozing 🐝",
    "spec.desc.recraft": "Recraft — vektor grafikasi va dizayn. Qanday rasm yaratmoqchi ekaningizni yozing.",
    "spec.desc.seedance": "Matn, rasm, video va audiodan video yaratish.\n\nParametrlarni sozlang va boshlash uchun prompt yuboring ⚡",
    "spec.desc.veo": "Veo 3.1 — Google'ning kinematografik videosi. Prompt yuboring ⚡",
    "spec.desc.grok": "Video yaratish va tahrirlash. Muharrir 2 generatsiya sarflaydi.\n18+, zo'ravonlik va deepfake taqiqlanadi. Prompt yuboring ⚡",
    "spec.desc.kling_ai": "Video yaratish va tahrirlash. Prompt yuboring ⚡",
    "spec.desc.hailuo": "Hailuo — tavsif va rasm asosida video. Prompt yuboring ⚡",
    "spec.desc.pika": "Pika Labs — tavsif va rasmlar asosida video. Prompt yuboring ⚡",
    "spec.desc.mj_video": "Midjourney Video — rasmlar animatsiyasi. Foto va/yoki prompt yuboring ⚡\nRasm to'plamidan yechiladi.",
    "spec.mode.create": "Yaratish",
    "spec.mode.edit": "Muharrir",
    "gen.ready_generic": "✅ Sizning generatsiyangiz ({service}) tayyor.",
    "refund.stars": "⚠️ Buyurtmani bajarib bo'lmadi. To'lov (⭐) Telegram balansingizga qaytarildi. Uzr so'raymiz!",
    "notify.premium_expiry": "⏳ Premium {days} kundan so'ng tugaydi. Yuqori limitlarni yo'qotmaslik uchun obunani yangilang.",
    "notify.low_balance": "✨ Balansingiz deyarli tugadi — {balance} ✨ qoldi. To'xtovsiz generatsiya qilish uchun to'ldiring.",
    "notify.winback": "👋 Ko'rinmay ketdingiz! Qaytib keling — yangi modellar va effektlar bor. So'rov yuboring, davom etamiz 🙌",
    "notify.bonus_available": "🎁 Kunlik bonusingiz tayyor! Seriyangizni saqlash va ko'proq ✨ olish uchun bugun oling.",
    "notify.btn.renew": "⭐ Premiumni yangilash",
    "notify.btn.topup": "✨ To'ldirish",
    "notify.btn.open": "🚀 Tariflarni ochish",
    "notify.btn.bonus": "🎁 Bonusni olish",
    "notify.abandoned_cart": "🛒 Xaridingizga bir qadam qoldi! Yakunlang — bir daqiqa vaqt oladi.",
    "notify.btn.cart": "🛒 Xaridni yakunlash",
    "ref.earned_register": "🎉 Sizning havolangiz orqali yangi foydalanuvchi ro'yxatdan o'tdi! Sizga ✨ {amount} hisoblandi.",
    "ref.welcome_bonus": "🎁 Referal havola orqali qo'shilganingiz uchun xush kelibsiz bonusi: +✨ {amount}!",
    "promo.welcome_bonus": "🎁 Yangi foydalanuvchi uchun xush kelibsiz bonusi: +✨ {amount}!",
    "promo.purchase_bonus": "🎁 Xarid uchun bonus: +✨ {amount}!",
    "promo.applied": "🏷 Promokod qo'llandi: keyingi xaridga −{percent}%!",
    "promo.applied_banner": "🏷 Promokod −{percent}% qo'llandi",
    "ad.remove_btn": "⭐ Reklamani olib tashlash",
    "ref.milestone": "🏆 Siz {count} ta foydalanuvchini taklif qildingiz! Bonus: +✨ {amount}.",
    "ref.earned_purchase": "🎉 Sizning havolangiz orqali xarid amalga oshirildi! Sizga ✨ {amount} hisoblandi.",
    "contest.won": "🎉 Tabriklaymiz! Siz konkursda yutdingiz!",
    "contest.won_credits": "🎉 Tabriklaymiz! Siz konkursda yutdingiz — sizga ✨ {amount} berildi!",
    "contest.won_pack": "🎉 Tabriklaymiz! Siz konkursda yutdingiz — sizga {amount} {unit} berildi!",
    "gift.not_found": "❌ Bunday kodli sovg'a topilmadi.",
    "gift.already_used": "❌ Bu sovg'a allaqachon faollashtirilgan.",
    "gift.own_gift": "🎁 O'z sovg'angizni faollashtira olmaysiz — uni do'stingizga ulashing.",
    "gift.redeemed_sub": "🎁 Sovg'a faollashtirildi: {product}, {months} oy.",
    "gift.redeemed_pack": "🎁 Sovg'a faollashtirildi: {product} to'plami (+{qty}).",
    "gift.redeemed_credits": "🎁 Sovg'a faollashtirildi: +{qty} ✨.",
    "gift.unknown_kind": "❌ Noma'lum sovg'a turi.",
}
