"""Arabic locale — user-facing screens; long legal/help fall back to RU."""

MESSAGES: dict[str, str] = {
    "start.welcome": (
        "مرحبًا! 👋\n\n"
        "أنا SUPER AI BOT، مساعدك بالذكاء الاصطناعي، أساعدك على إنشاء النصوص والصور والفيديو "
        "والموسيقى والكثير غير ذلك باستخدام أحدث الشبكات العصبية.\n\n"
        "🎁 مجانًا:\n100 طلب أسبوعيًا للنصوص والصور وأدوات الذكاء الاصطناعي الأخرى.\n\n"
        "⭐️ PREMIUM:\nوصول موسّع إلى أقوى الشبكات العصبية.\n\n"
        "كيفية استخدام البوت؟\n\n"
        "📝 النص\nاكتب سؤالك أو مهمتك في المحادثة — سأساعدك فورًا.\n\n"
        "🔎 البحث\nاستخدم /s لطرح سؤال مع البحث في الإنترنت.\n\n"
        "🌅 الصور\nاضغط /photo لإنشاء صورة أو تعديلها.\n\n"
        "🎬 الفيديو\nاضغط /video لإنشاء مقطع فيديو.\n\n"
        "🎸 الموسيقى\nاضغط /music لإنشاء أغنية.\n\n"
        "⚙️ النموذج\nالأمر /model يتيح اختيار الشبكة العصبية.\n\n"
        "💎 PREMIUM\nالأمر /premium يفتح الميزات المتقدمة.\n\n"
        "ابدأ الآن — فقط أرسل لي أي رسالة 🚀"
    ),
    "account": (
        "👤 حسابك\n\nالاشتراك: {sub}\nالنموذج المختار: {model_name} /model\n\n"
        "📊 إحصائيات الاستخدام\n\nالطلبات هذا الأسبوع: {used}/{limit}\n"
        "✨ طلبات إضافية: {credits} (من الإحالات والمكافأة اليومية؛ تُستخدم بعد انتهاء حد الأسبوع)\n\n"
        "المتاح في الخطة المجانية:\n└ GPT-5 mini\n└ DeepSeek V4\n└ Gemini 3.1 Flash\n"
        "└ Perplexity\n└ GPT Image 2\n└ Nano Banana 2\n\n"
        "تحتاج المزيد؟ فعّل /premium\n\n"
        "🚀 اشتراك Premium:\n└ 100–200 طلب يوميًا\n└ GPT-5.5\n└ Gemini 3.5\n"
        "└ DeepSeek\n└ Claude 4.8 Opus و Sonnet\n└ Nano Banana Pro\n└ التعامل مع المستندات\n\n"
        "🌅 باقة الصور: {image}\n🎬 باقة الفيديو: {video}\n🎸 باقة الموسيقى: {music}\n\n"
        "📞 الدعم: {support}"
    ),
    "account.sub_free": "مجاني ✔️",
    "account.role": "🎭 الدور: {title}",
    "account.role_custom": "✍️ دور خاص",
    "account.sub_premium": "Premium ✔️",
    "account.sub_premium_x2": "Premium X2 ✔️",
    "photo.menu": (
        "🌅 إنشاء وتعديل الصور\n\nاختر الخدمة المطلوبة 👇\n\n"
        "🔴 مؤثرات الصور\nقوالب جاهزة لصور رائجة وبورتريهات وصور رمزية وصور إبداعية.\n\n"
        "💬 GPT Image 2\nفوتوشوب بالذكاء الاصطناعي من OpenAI لإنشاء وتعديل الصور حسب وصفك.\n\n"
        "♊️ Nano Banana Pro\nفوتوشوب متقدم بالذكاء الاصطناعي من Google لتعديل دقيق واستبدال التفاصيل وتحسين الصور.\n\n"
        "🖼 Midjourney و Seedream و Recraft و FLUX\nمولّدات شهيرة للأعمال الفنية والصور الواقعية والتصميم والرسوم.\n\n"
        "📸 باقة الصور الرمزية\nأرسل صورة واحدة وسينشئ البوت 100 صورة رمزية بأنماط مختلفة.\n\n"
        "اختر خدمة بالأسفل وابدأ إنشاء صورتك ✨"
    ),
    "video.menu": (
        "🎬 إنشاء فيديو\n\nاختر خدمة توليد المقطع 👇\n\n"
        "🔴 مؤثرات الفيديو\nقوالب جاهزة لمقاطع رائجة وفيديوهات قصيرة ومؤثرات إبداعية.\n\n"
        "🌱 Seedance 2.0\nينشئ فيديو من النص والصور والفيديو والصوت.\n\n"
        "♊ Veo 3.1 و Pika و Hailuo\nتولّد فيديو من وصف أو صورة مرفوعة.\n\n"
        "❎ Grok Imagine و Kling\nتنشئ فيديو وتساعد أيضًا على تعديل المقاطع الجاهزة.\n\n"
        "👨 Kling Effects\nتُحيي صورك وتضيف إليها مؤثرات بصرية.\n\n"
        "🎥 Kling Motion\nتُحرّك الصورة مع تكرار الحركة من فيديو نموذجي.\n\n"
        "اختر الخدمة بالأسفل وابدأ إنشاء الفيديو ✨"
    ),
    "music.menu": (
        "🎸 إنشاء الموسيقى\n\nاختر خدمة توليد أغنية أو موسيقى 👇\n\n"
        "🎵 Suno V5.5\nينشئ أغاني كاملة حتى 8 دقائق: موسيقى وغناء وكلمات وتوزيع جاهز.\n\n"
        "♊ Lyria 3 Pro\nخدمة جديدة من Google لتوليد أغانٍ وموسيقى آلية حتى 3 دقائق.\n\n"
        "يمكنك استخدام كلماتك الخاصة أو طلب أن يبتكرها الذكاء الاصطناعي ✨"
    ),
    "search.intro": (
        "🔎 البحث في الإنترنت\n\n"
        "اختر نموذج البحث بالأسفل أو استخدم النموذج الافتراضي.\n\n"
        "ثم اكتب طلبك في المحادثة — سيجد البوت معلومات حديثة من الإنترنت ويجهّز الإجابة 👇"
    ),
    "model.selected": "✅ تم اختيار النموذج «{name}».",
    "model.premium_locked": "🔒 النموذج «{name}» متاح في /premium فقط.",
    "settings.lang.choose": "اختر لغة الواجهة:",
    "settings.lang.saved": "✅ تم تغيير اللغة.",
    "settings.context.on": "✅ تم تفعيل دعم السياق.",
    "settings.context.off": "❌ تم إيقاف دعم السياق.",
    "privacy.btn_terms": "📄 اتفاقية الاستخدام",
    "privacy.btn_policy": "📄 سياسة الخصوصية",
    "gate.premium": "🔒 هذه الميزة متاحة في /premium فقط.",
    "gate.pack_empty": "انتهت توليدات الباقة. اضغط «إعادة الشحن» 👇",
    "quota.exceeded.free": "لقد استنفدت طلباتك المجانية هذا الأسبوع ({used}/{limit}) و✨ أيضًا.\nادعُ أصدقاءك /invite أو خذ مكافأتك اليومية /bonus للحصول على ✨ أكثر، أو فعّل /premium 🚀",
    "quota.exceeded.premium": "بلغت الحد اليومي ({used}/{limit}) و✨ أيضًا نفدت. يتجدد غدًا، أو اشحن ✨ عبر /invite و/bonus.",
    "docs.prompt": (
        "📄 العمل مع المستندات\n\n"
        "أرسل ملفًا إلى البوت واطرح أسئلة عن محتواه.\n\n"
        "الصيغ المدعومة:\ndocx, pdf, xlsx, xls, csv, pptx, txt\n\n"
        "الحد الأقصى لحجم الملف: حتى 10 ميغابايت\n\n"
        "ما يمكنك فعله:\n"
        "└ الحصول على ملخص للمستند\n└ البحث عن معلومات محددة\n"
        "└ تحليل الجداول والنصوص\n└ طرح أسئلة عن الملف\n"
        "└ طلب الشرح أو الترجمة أو هيكلة البيانات\n\n"
        "💎 يتطلب العمل مع المستندات اشتراك /premium.\n\n"
        "⚠️ كل طلب على المستند يستهلك 3 توليدات."
    ),
    "ai.unavailable": "⚠️ خدمة الذكاء الاصطناعي غير متاحة مؤقتًا. حاول بعد قليل.",
    "ai.rate_limit": "✨ الذكاء الاصطناعي مشغول قليلاً — أرسل رسالتك مرة أخرى. لم يُخصم من حصتك.",
    "common.please_wait": "انتظر لحظة من فضلك •••",
    "common.cancelled": "تم الإلغاء.",  # FIX: AUDIT13-L11
    "gdpr.export_ready": "📦 بياناتك جاهزة — الملف مرفق.",  # FIX: AUDIT13-M22
    "common.coming_soon": "🛠 هذا القسم سيتوفر قريبًا.",
    "common.banned": "الوصول إلى البوت مقيّد.",
    "btn.model": "📝 اختيار النموذج",
    "btn.images": "🎨 إنشاء صورة",
    "btn.search": "🔎 بحث إنترنت",
    "btn.search_model": "🔎 نموذج البحث: {name}",
    "search.choose_model": "اختر نموذجًا للبحث في الإنترنت 👇",
    "search.model_set": "✅ نموذج البحث: {name}",
    "btn.video": "🎬 إنشاء فيديو",
    "btn.documents": "📄 مستند",
    "btn.music": "🎸 إنشاء أغنية",
    "btn.premium": "🚀 Premium",
    "btn.account": "👤 ملفي الشخصي",
    "btn.translate": "🌐 ترجمة",
    "btn.close": "إغلاق",
    "btn.back": "← رجوع",
    "btn.connect_premium": "🚀 تفعيل Premium",
    "btn.topup": "🎵 إعادة الشحن",
    "btn.set_model": "اختيار النموذج",
    "btn.set_role": "وصف الدور",
    "btn.set_context": "دعم السياق",
    "btn.set_voice": "الردود الصوتية",
    "btn.set_lang": "لغة الواجهة",
    "premium.choose_duration": "اختر مدة الاشتراك 👇",
    "premium.choose_gateway": "اختر طريقة الدفع 👇",
    "premium.upgrade_warning": "⚠️ لديك خطة {current} نشطة. سيستمر الوقت المتبقي وفق الخطة الجديدة {new}.",
    "premium.btn_premium": "⭐ Premium",
    "premium.btn_premium_x2": "🔥 Premium X2",
    "premium.btn_image": "🌅 باقة الصور",
    "premium.btn_video": "🎬 باقة الفيديو",
    "premium.btn_music": "🎸 باقة الموسيقى",
    "unit.generations": "توليدات",
    "unit.sec": "ث",
    "vcfg.with_sound": "مع الصوت",
    "vcfg.enhance": "تحسين الوصف",
    "vcfg.seed_add": "إضافة seed",
    "vcfg.seed_set": "seed: {v}",
    "btn.instruction": "❤️ الدليل",
    "btn.topup_pay": "💳 إعادة الشحن",
    "video.image_saved": "🖼 تمت إضافة الصورة. الآن أرسل وصف الفيديو ⚡",
    "video.effects_hint": "🎬 مؤثرات الفيديو متاحة في تطبيق Mini App. افتحه من قائمة المرفقات 📎",
    "photo.effects_hint": "🎨 مؤثرات الصور متاحة في تطبيق Mini App. افتحه من قائمة المرفقات 📎",  # FIX: AUDIT13-L13
    "tts.unavailable": "⚠️ النطق الصوتي غير متاح مؤقتًا.",
    "tts.failed": "⚠️ تعذّر نطق الرد.",
    "doc.unsupported": "المدعومة: pdf, docx, doc, xlsx, xls, csv, pptx, txt (حتى 10 ميغابايت).",
    "doc.too_large": "الملف كبير جدًا. الحد الأقصى 10 ميغابايت.",
    "doc.extract_failed": "تعذّر استخراج النص من الملف.",
    "doc.empty": "لم يُعثر على نص في الملف.",
    "doc.received": "📄 تم استلام الملف «{name}». اطرح أسئلتك — كل طلب يستهلك {cost} توليدات.",
    "btn.translate_hint": "🌐 اضغط 🌐 أسفل رد الذكاء الاصطناعي لترجمته.",
    "voice.selected": "الصوت: {voice}",
    "voice.sample": "مرحبًا! هكذا يبدو الصوت المختار.",
    "search.nothing": "لم يُعثر على شيء.",
    "btn.daily_bonus": "🎁 المكافأة اليومية",
    "bonus.claimed": "🎁 تم استلام المكافأة: +{amount} ✨ · السلسلة: {streak} 🔥",
    "bonus.already": "✅ تم الاستلام اليوم بالفعل. عُد غدًا! · السلسلة: {streak} 🔥",
    "notify.premium_granted": "🎁 تم منحك اشتراك Premium لمدة {months} شهر! استمتع 💎",
    "notify.premium_revoked": "ℹ️ تم إيقاف اشتراك Premium الخاص بك من قبل المسؤول.",
    "notify.banned": "🚫 تم حظر حسابك. إذا كان ذلك خطأً، تواصل مع الدعم.",
    "notify.unbanned": "✅ تم رفع الحظر عن حسابك. يمكنك استخدام البوت مجددًا.",
    "contact.saved": "✅ شكرًا! تم حفظ رقم هاتفك.",
    "btn.open_app": "🚀 فتح التطبيق",
    "voice.on": "🔊 الصوت: مفعّل",
    "voice.off": "🔇 الصوت: متوقف",
    "throttle.flood": "⏳ طلبات كثيرة. انتظر قليلًا.",
    "srv.photoeffects": "🎨 مؤثرات الصور",
    "srv.videoeffects": "🎬 مؤثرات الفيديو",
    "srv.avatar": "👤 باقة الصور الرمزية",
    "srv.faceswap": "🔄 تبديل الوجه",
    "srv.upscale": "📐 تكبير X2/X4",
    "pack.label.popular": "الأكثر شيوعًا",
    "pack.label.best": "أفضل اختيار",
    "product.premium": "Premium",
    "product.premium_x2": "Premium X2",
    "pack.name.image": "باقة الصور",
    "pack.name.video": "باقة الفيديو",
    "pack.name.music": "باقة الموسيقى",
    "duration.1": "شهر واحد",
    "duration.3": "3 أشهر",
    "duration.6": "6 أشهر",
    "duration.12": "سنة",
    "pack.choose": "اختر باقة «{name}» 👇",
    # ----- VIP / loyalty (ТЗ §4) -----
    "btn.vip": "🏅 مستويات VIP",
    "account.vip": "🏅 المستوى: {tier} · يتبقى {left} ⭐ حتى {next}",
    "account.vip_top": "🏅 المستوى: {tier} (الأعلى)",
    "account.vip_none": "🏅 يتبقى {left} ⭐ للمستوى {next}",
    "vip.title": "🏅 مستويات VIP\nإجمالي مشترياتك: {spent} ⭐\n",
    "vip.row": "{mark} {name} — من {min} ⭐ · +{daily}/يوم، +{weekly}/أسبوع",
    "vip.reached": "🎉 تهانينا! لقد وصلت إلى مستوى VIP {tier}.\nلديك الآن +{daily} توليد/يوم و +{weekly}/أسبوع.",
    # ----- global sale (ТЗ §4) -----
    "sale.banner": "🔥 تخفيض −{percent}%",
    "sale.ends_in": "⏳ ينتهي خلال: {time}",
    "sale.left_dh": "{d}ي {h}س",
    "sale.left_hm": "{h}س {m}د",
    "sale.left_m": "{m}د",
    "pay.sub_invoice_desc": "الاشتراك: {title}",
    "pay.pack_invoice_desc": "باقة التوليدات: {title}",
    "pay.sub_activated": "✅ تم تفعيل اشتراك «{title}»! شكرًا لشرائك 🚀",
    "pay.pack_added": "✅ تم شحن الباقة: +{qty} {unit} ({pack}). شكرًا لشرائك!",
    "pay.avatar_paid": "✅ تم الدفع! أرسل أفضل صورة سيلفي — سأنشئ 100 صورة رمزية (~15 دقيقة).",
    "pay.link": "افتح الرابط للدفع. يتم تفعيل الوصول تلقائيًا بعد الدفع الناجح 👇",
    "pay.link_btn": "💳 ادفع — {title}",
    "pay.unavailable": "طريقة الدفع هذه غير متاحة حاليًا.",
    "pay.failed": "تعذّر إنشاء الفاتورة. جرّب طريقة أخرى.",
    "gen.video_started": "🎬 بدأ توليد الفيديو! سيستغرق بضع دقائق — سأرسل النتيجة عند جاهزيتها.",
    "gen.music_started": "🎶 أُولّد أغنيتك — سأرسل الصوت عند جاهزيته!",
    "gen.photo_started": "🎨 يجري تطبيق «{name}» — سأرسل الفيديو عند جاهزيته!",
    "gen.unavailable": "⚠️ الخدمة غير متاحة مؤقتًا. حاول لاحقًا.",
    "gen.unavailable_refund": "⚠️ الخدمة غير متاحة مؤقتًا. تمت إعادة الأرصدة.",
    "gen.error_refund": "⚠️ خطأ في التوليد. تمت إعادة الأرصدة.",
    "mod.blocked": "🚫 الطلب يخالف قواعد الاستخدام.",
    "seed.ask": "أدخل seed للتوليد (قيمة رقمية):",
    "seed.saved": "✅ تم حفظ seed.",
    "avatar.info": (
        "👤 صور رمزية بالذكاء الاصطناعي\n\nأنشئ 100 صورة رمزية رائعة لوسائل التواصل بأنماط مختلفة.\n"
        "السعر: {price} ⭐ للباقة. الدقة 1024×1440، بدون علامات مائية.\n"
        "بعد الدفع، ارفع أفضل صورة سيلفي — التوليد ~15 دقيقة."
    ),
    "avatar.title": "باقة الصور الرمزية",
    "avatar.buy_btn": "اشترِ مقابل {price} ⭐",
    "avatar.started": (
        "🎨 بدأ توليد 100 صورة رمزية! سيستغرق ~15 دقيقة — يمكنك متابعة استخدام "
        "البوت، وسأرسل النتيجة عند جاهزيتها."
    ),
    "music.prompt": "🎵 {name}: أرسل وصفًا للأغنية (الأسلوب، المزاج، الكلمات).",
    "kling.effects_intro": (
        "🌊 Kling Effects\n\n1. اختر تأثيرًا من الخيارات أدناه.\n"
        "2. أرسل صورة إلى البوت لتطبيق التأثير المختار."
    ),
    "kling.effect_selected": "التأثير: {name}\n\nأرسل صورة وسيطبّق البوت التأثير المختار!",
    "kling.motion_intro": (
        "💃 Kling Motion\n\nستنبض صورتك بالحياة وتكرّر الحركة من فيديو نموذجي.\n"
        "اختر قالبًا 👇"
    ),
    "kling.motion_selected": "الحركة: 💃 {name}. أرسل صورة — سينقل Kling Motion الحركة إليها.",
    "btn.voice": "🔊",
    "btn.view": "🔥 عرض",
    "deletecontext.done": "تم مسح السياق. افتراضيًا يأخذ البوت سؤالك السابق وإجابته بعين الاعتبار.",
    "music.paywall": "🎵 لإنشاء الأغاني، اشترِ باقة موسيقى. اضغط «إعادة الشحن» 👇",
    "gate.subscription": "لمواصلة استخدام البوت مجانًا، اشترك في قناتنا 👇\nثم اضغط «اشتركت».",
    "gate.subscription.ok": "✅ شكرًا على اشتراكك! يمكنك المتابعة.",
    "gate.subscription.fail": "❌ يبدو أنك لم تشترك بعد.",
    "settings.role.prompt": "أرسل الدور (موجّه النظام) الذي يجب أن يتبعه الذكاء الاصطناعي.",
    "settings.role.current_none": "الدور الحالي: غير مُحدّد.",
    "settings.role.current": "الدور الحالي:\n{role}",
    "settings.role.saved": "✅ تم حفظ الدور.",
    "settings.role.cleared": "تم حذف الدور.",
    "settings.role.too_long": "❌ الدور طويل جدًا (الحد الأقصى {limit} حرفًا). يرجى اختصاره وإعادة الإرسال.",
    "settings.voice.intro": "اختر صوتًا للردود الصوتية (متاح في /premium):",
    "settings.voice.preview": "الاستماع إلى الصوت المختار",
    "settings.intro": (
        "⚙️ إعدادات البوت\n\nهنا يمكنك ضبط الذكاء الاصطناعي حسب رغبتك 👇\n\n"
        "1️⃣ اختيار النموذج — الشبكة التي تجيب على طلباتك.\n\n"
        "2️⃣ تحديد الدور — مثل: مساعد، كاتب، مبرمج، معلم أو خبير.\n\n"
        "3️⃣ سياق الحوار — فعّله أو أوقفه. عند التفعيل يأخذ البوت إجابته السابقة بعين الاعتبار.\n\n"
        "4️⃣ الردود الصوتية — اضبط النطق واختر الصوت. متاح في /premium.\n\n"
        "5️⃣ لغة الواجهة — اختر لغة مريحة.\n\n"
        "اختر عنصرًا بالأسفل 👇"
    ),
    "model.intro": (
        "🤖 اختيار نموذج الذكاء الاصطناعي\n\nنماذج رائدة للنصوص والبرمجة والتحليل والمهام المعقدة.\n\n"
        "اختر نموذجًا بالأسفل 👇\n\n"
        "💬 GPT-5.5 — نموذج OpenAI الأقوى. يستهلك 3 توليدات لكل طلب.\n\n"
        "💬 GPT-5.4 — نموذج متعدد الاستخدامات للبرمجة والنصوص.\n\n"
        "💬 GPT-5 mini — نموذج سريع للاستخدام اليومي. مجاني.\n\n"
        "🌥 Claude 4.8 Opus — نموذج Anthropic الأقوى. يستهلك 5 توليدات لكل طلب.\n\n"
        "🌥 Claude 4.6 Sonnet — قوي للنصوص والبرمجة والرياضيات.\n\n"
        "🐳 DeepSeek V4 — سريع وقوي. مجاني.\n\n"
        "🐳 DeepSeek V4 Pro — نسخة متقدمة من DeepSeek.\n\n"
        "♊️ Gemini 3.5 Flash — نموذج Google الأقوى.\n\n"
        "♊️ Gemini 3.1 Flash — نموذج Google سريع وذكي. مجاني.\n\n"
        "📌 المستندات: في Premium يمكنك إرسال ملفات حتى 10 ميغابايت. يستهلك 3 توليدات.\n\n"
        "🎁 مجانًا: GPT-5 mini، Gemini 3.1 Flash، DeepSeek V4\n💎 النماذج الأخرى في Premium: /premium\n\n"
        "اختر نموذجًا بالأسفل 👇"
    ),
    "help": (
        "📚 مساعدة البوت\n\nالأوامر والميزات الرئيسية.\n\n"
        "📝 توليد النصوص\nاكتب طلبك في المحادثة. يمكن لمستخدمي /premium إرسال رسائل صوتية أيضًا.\n\n"
        "الأوامر:\n└ /deletecontext — حوار جديد\n└ /s — بحث في الإنترنت\n"
        "└ /settings — النموذج والدور واللغة والسياق\n└ /model — اختيار النموذج\n\n"
        "💡 كلما زاد التفصيل، تحسّنت الإجابة.\n\n"
        "📄 المستندات (Premium)\nارفع ملفًا حتى 10 ميغابايت واطرح أسئلة عنه.\nالصيغ: docx, pdf, xlsx, xls, csv, pptx, txt.\nكل طلب يستهلك 3 توليدات.\n\n"
        "🌅 الصور\n└ Nano Banana 2 / Pro\n└ GPT Image 2\n└ Midjourney\n└ Flux\n└ Seedream\n└ Recraft\nالأوامر: /photo، /midjourney\n\n"
        "🎬 الفيديو\n└ Kling\n└ Seedance 2.0\n└ Pika\n└ Veo 3.1\n└ Hailuo\n└ Grok Imagine\nالأمر: /video\n\n"
        "🎸 الموسيقى\n└ Suno V5.5\n└ Lyria 3 Pro\nالأوامر: /music، /suno\n\n"
        "⚙️ أخرى\n└ /start\n└ /account\n└ /premium\n└ /privacy\n\n"
        "💬 للأسئلة: {support}"
    ),
    "privacy": (
        "🔐 المستندات القانونية\n\nقبل استخدام البوت، اطّلع على القواعد وشروط معالجة البيانات:\n\n"
        "1️⃣ اتفاقية الاستخدام\n2️⃣ سياسة الخصوصية\n\n"
        "بمتابعة استخدام البوت فإنك تؤكد أنك اطّلعت عليها وتقبلها."
    ),
    "premium": (
        "🚀 الباقات والميزات\n\nيجمع البوت خدمات الذكاء الاصطناعي الشهيرة: النص، البحث، الصور، الفيديو، الموسيقى والملفات.\n\n"
        "🎁 مجانًا | كل أسبوع\n\n100 طلب:\n✅ GPT-5 mini\n✅ DeepSeek V4\n✅ Gemini 3.1 Flash\n✅ Perplexity\n✅ التعرّف على الصور\n\n"
        "25 توليد صور:\n♊️ Nano Banana 2\n✅ GPT Image 2\n\n"
        "💎 PREMIUM | شهر واحد\n\nالحد: 100 طلب/يوم\n\n✅ كل ميزات الخطة المجانية\n✅ GPT-5.5\n✅ Gemini 3.5 Flash\n✅ Claude 4.8 Opus و Sonnet\n✅ DeepSeek\n♊️ Nano Banana Pro\n✅ GPT Image 2\n✅ المستندات\n✅ الردود الصوتية\n✅ بدون إعلانات\n\nالسعر: {p_premium}⭐️\n\n"
        "💎 PREMIUM X2 | شهر واحد\n\nالحد: 200 طلب/يوم\n\n✅ كل ميزات Premium\n✅ حد يومي أعلى\n\nالسعر: {p_premium_x2}⭐️\n\n"
        "🌅 الصور | باقة\n\nمن 50 إلى 500 توليد حسب اختيارك\n\nالخدمات المتاحة:\n"
        "🌅 Midjourney\n🎬 Midjourney Video\n🌱 Seedream\n🎨 Recraft\n⚡ Flux\n✅ تبديل الوجه في الصور\n\nالسعر: من {p_image_from}⭐️\n\n"
        "🎬 الفيديو | باقة\n\nمن 2 إلى 50 توليد حسب اختيارك\n\nالخدمات المتاحة:\n"
        "📼 Kling\n🎥 Veo 3.1\n🚀 Seedance 2.0\n❎ Grok Imagine\n🎞 Hailuo\n✨ Pika\n\n"
        "إضافةً إلى:\n✅ تعديل الفيديو\n✅ مؤثرات فيديو إبداعية\n\nالسعر: من {p_video_from}⭐️\n\n"
        "🎸 الموسيقى | باقة\n\nمن 20 إلى 100 توليد حسب اختيارك\n\nالخدمات المتاحة:\n"
        "🎸 Suno V5.5\n🎼 Lyria 3 Pro\n\nالإمكانيات:\n✅ أغاني بكلماتك الخاصة\n✅ توليد كلمات الأغنية بالذكاء الاصطناعي\n\nالسعر: من {p_music_from}⭐️\n\n"
        "⭐️ جميع الأسعار بعملة Stars في تيليجرام.\n\n💬 للدفع والوصول:\n{support}"
    ),
    "gate.channel": "لمواصلة استخدام البوت مجانا، اشترك في القنوات ادناه.\n\nبفضل الاشتراكات تحصل على 100 طلب مجاني اسبوعيا الى ChatGPT و DeepSeek و Gemini و Perplexity ومولدات الصور وغيرها.\n\nتريد كل شيء بدون اعلانات؟ اضغط Premium.",
    "gate.btn_subscribe": "الاشتراك في {channel}",
    "gate.btn_check": "التحقق من الاشتراك",
    "gate.btn_premium": "Premium",
    "gate.ok": "شكرا لاشتراكك! يمكنك المتابعة.",
    "gate.not_subscribed": "لم تشترك بعد في جميع القنوات.",
    "gate.premium_voice": "لارسال الطلبات الصوتية، اشترك في /premium.",
    "faceswap.step1": "[الخطوة 1/2] ارسل الصورة التي سيتم تغيير الوجه فيها.",
    "faceswap.step2": "[الخطوة 2/2] الان ارسل صورة الوجه المصدر.",
    "upscale.intro": "تزيد هذه الاداة من دقة الصورة. اختر المعامل.",
    "upscale.x2": "تكبير X2",
    "upscale.x4": "تكبير X4",
    "upscale.send_image": "ارسل صورة (بحد اقصى 1024x1024). سيتم خصم {cost} عملية انشاء.",
    "vision.coming_soon": "التعرف على الصور سيتوفر قريبا.",
    "vision.failed": "تعذر معالجة الصورة. حاول مرة اخرى.",
    "photo.choose": "ماذا تريد ان افعل بهذه الصورة؟",
    "photo.btn_describe": "🔎 وصف",
    "photo.btn_edit": "🎨 تعديل حسب التعليق",
    "photo.edit_working": "🎨 جاري تعديل الصورة…",
    "photo.edit_done": "✅ تم!",
    "photo.edit_unavailable": "🛠 تحرير الصور قادم قريبا.",
    "photo.edit_failed": "تعذر تعديل الصورة. حاول مرة اخرى.",
    "photo.edit_no_caption": "اضف تعليقا يصف التعديل وساغير الصورة.",
    "voice_in.coming_soon": "الادخال الصوتي سيتوفر قريبا.",
    "voice_in.heard": "🎙 تم التعرف: «{text}»",
    "voice_in.empty": "تعذر التعرف على الكلام. حاول التسجيل مرة اخرى.",
    "voice_in.failed": "تعذرت معالجة الرسالة الصوتية. حاول مرة اخرى.",
    "gen.image_started": "تم استلام الطلب! ساارسل النتيجة عندما تكون جاهزة.",
    "pay.credits_added": "✨ تمت اضافة {qty} رصيد! استخدمها في التطبيق المصغر.",
    "img.more": "🔄 المزيد",
    "img.upscale": "🔍 تكبير",
    "img.file": "📎 الجودة الكاملة",
    "img.no_prompt": "اختر خدمة وأرسل وصفا اولا.",
    "promo.usage": "الاستخدام: /promo الرمز",
    "promo.invalid": "❌ الرمز الترويجي غير صالح أو منتهي الصلاحية.",
    "promo.already": "لقد قمت بتفعيل هذا الرمز الترويجي بالفعل.",
    "promo.ok": "✅ تم تفعيل الرمز الترويجي: +{amount} {reward}.",
    "promo.not_eligible": "❌ هذا الرمز الترويجي مخصص للمستخدمين الجدد فقط.",
    # --- bot UI strings (handlers sweep) ---
    "fb.thanks": "شكرًا على تقييمك!",
    "report.usage": "الاستخدام: <code>/report وصف المشكلة</code>",
    "report.thanks": "شكرًا! تم استلام بلاغك.",
    "roles.btn_off": "🚫 إيقاف الدور",
    "roles.btn_custom": "✍️ دور خاص",
    "roles.unavailable": "الأدوار الجاهزة غير متاحة حاليًا.",
    "roles.choose": "🎭 اختر دورًا جاهزًا للمساعد.",
    "roles.choose_active": "\n\nيوجد دور مخصص مفعّل — اختر دورًا جديدًا أو أوقفه.",
    "roles.not_found": "الدور غير موجود",
    "roles.enabled": "تم تفعيل الدور «{title}» ✅",
    "roles.enabled_full": "تم — يعمل المساعد الآن بصفة «{title}». لإيقافه، أرسل /roles ← «إيقاف الدور».",
    "roles.disabled": "تم إيقاف الدور",
    "roles.disabled_full": "تم إيقاف دور المساعد — الوضع العادي.",
    "contest.none": "لا توجد مسابقات نشطة الآن. تحقّق لاحقًا!",
    "contest.entrants": "المشاركون: {count}",
    "contest.btn_enter": "المشاركة",
    "contest.ended": "انتهت هذه المسابقة بالفعل.",
    "contest.entered": "أنت مشارك في المسابقة! حظًا موفقًا! 🍀",
    "contest.already": "أنت مشارك بالفعل في هذه المسابقة.",
    "gift.btn_premium": "🎁 Premium · شهر واحد",
    "gift.btn_pack": "🎁 حزمة صور · 50",
    "gift.btn_sub": "🎁 إهداء اشتراك",
    "gift.btn_pack_menu": "📦 إهداء باقة",
    "gift.pack_none": "الباقات غير متاحة حاليًا.",
    "gift.choose": "🎁 أهدِ صديقًا اشتراكًا أو حزمة.\nاختر ما تريد إهداءه:",
    "gift.invoice_title_sub": "🎁 {product} · {value} شهر",
    "gift.invoice_desc": "هدية: {title}",
    "gift.paid": "🎁 تم دفع الهدية!\n\nالرمز: <code>{code}</code>\n\nأرسل لصديقك الأمر <code>/redeem {code}</code> أو هذا الرابط:\n{link}",
    "redeem.usage": "الاستخدام: <code>/redeem الرمز</code>",
    "inline.hint_title": "أدخل سؤالًا…",
    "inline.hint_text": "اكتب سؤالًا بعد اسم البوت للحصول على إجابة الذكاء الاصطناعي.",
    "inline.error_title": "خطأ",
    "inline.error_text": "تعذّر الحصول على إجابة. حاول لاحقًا.",
    "inline.throttle_title": "متكرر جدًا",
    "inline.throttle_text": "طلبات كثيرة متتالية. انتظر قليلًا ثم أعد المحاولة.",
    "support.usage": "الاستخدام: <code>/support سؤالك</code>\nصف المشكلة — ستصل رسالتك إلى الدعم.",
    "support.sent": "تم إرسال الرسالة إلى الدعم، وسنرد قريبًا.",
    "pay.precheckout_unavailable": "الدفع غير متاح",
    "pay.activate_failed": "⚠️ تعذّر تفعيل الشراء. تم استرداد دفعتك (⭐). حاول مرة أخرى أو تواصل مع الدعم.",
    "invite.summary": "🔗 رابط الإحالة الخاص بك:\n{link}\n\n👥 المستخدمون المدعوون: {count}\n✨ المكافأة لكل دعوة: {reward}\n💰 إجمالي ما رُبح: ✨ {earned}",
    "links.none": "لا توجد روابط مُعدّة بعد.",
    "links.title": "روابط مفيدة:",
    "avatar.invoice_desc": "100 صورة رمزية بالذكاء الاصطناعي 1024×1440",
    "promo.reward.credits": "رصيد",
    "promo.reward.image": "صورة",
    "promo.reward.video": "فيديو",
    "promo.reward.music": "مقاطع موسيقية",
    "promo.reward.premium": "يوم Premium",
    "pay.success": "✅ تم الدفع بنجاح! تم تفعيل وصولك. شكرًا لشرائك 🚀",
    "gen.video_ready": "✅ الفيديو جاهز!",
    "gen.song_ready": "✅ أغنيتك جاهزة!",
    "gen.photo_ready": "✅ صورتك جاهزة!",
    "gen.avatar_unavailable_refund": "⚠️ خدمة «الصور الرمزية» غير متاحة مؤقتًا. تم استرداد دفعتك (⭐) بالكامل إلى رصيدك في تيليجرام. نعتذر!",
    "spec.desc.gpt_image2": "أنشئ الصور وعدّلها مباشرة في الدردشة.\n\nهل أنت مستعد للبدء؟\nأرسل من 1 إلى 4 صور تريد تعديلها، أو اكتب ما تريد إنشاءه.",
    "spec.desc.nano_banana": "Gemini Images — أكثر إشراقًا. أكثر ذكاءً!\n\nأنشئ الصور وعدّلها في الدردشة. أرسل من 1 إلى 10 صور أو اكتب ما تريد إنشاءه.",
    "spec.desc.seedream": "أنشئ الصور وعدّلها في الدردشة. أرسل من 1 إلى 10 صور أو اكتب ما تريد إنشاءه.",
    "spec.desc.midjourney": "اكتب الصورة التي تريد إنشاءها.\n\nيدعم البوت جميع معاملات وميزات Midjourney الرئيسية.",
    "spec.desc.flux2": "اختر نسبة الأبعاد وطراز Flux. طرازا Flex وMax يكلّفان توليدتين.\n\nللبدء، اكتب الصورة التي تريد إنشاءها 🐝",
    "spec.desc.recraft": "Recraft — رسومات متجهة وتصميم. اكتب الصورة التي تريد إنشاءها.",
    "spec.desc.seedance": "توليد فيديو من النص والصور والفيديو والصوت.\n\nاضبط الخيارات وأرسل وصفًا للبدء ⚡",
    "spec.desc.veo": "Veo 3.1 — فيديو سينمائي من Google. أرسل وصفًا ⚡",
    "spec.desc.grok": "إنشاء وتعديل الفيديو. المحرّر يكلّف توليدتين.\nيُمنع +18 والعنف والتزييف العميق. أرسل وصفًا ⚡",
    "spec.desc.kling_ai": "إنشاء وتعديل الفيديو. أرسل وصفًا ⚡",
    "spec.desc.hailuo": "Hailuo — فيديو من وصف وصورة. أرسل وصفًا ⚡",
    "spec.desc.pika": "Pika Labs — فيديو من وصف وصور. أرسل وصفًا ⚡",
    "spec.desc.mj_video": "Midjourney Video — تحريك الصور. أرسل صورة و/أو وصفًا ⚡\nيُخصم من حزمة الصور.",
    "spec.mode.create": "إنشاء",
    "spec.mode.edit": "محرّر",
    "gen.ready_generic": "✅ تم تجهيز ما طلبته ({service}).",
    "refund.stars": "⚠️ تعذّر تنفيذ الطلب. تمت إعادة الدفعة (⭐) إلى رصيدك في تيليجرام. نعتذر!",
    "notify.premium_expiry": "⏳ ينتهي اشتراك Premium خلال {days} يوم. جدّد اشتراكك حتى لا تفقد حدودك الموسّعة.",
    "notify.low_balance": "✨ رصيدك على وشك النفاد — تبقّى {balance} ✨. اشحن رصيدك لمواصلة الإنشاء دون توقّف.",
    "notify.winback": "👋 لم نرَك منذ مدة! عُد إلينا — لدينا نماذج وتأثيرات جديدة. أرسل طلبك ولنُكمل 🙌",
    "notify.bonus_available": "🎁 مكافأتك اليومية جاهزة! استلمها اليوم للحفاظ على سلسلتك وكسب المزيد ✨.",
    "notify.btn.renew": "⭐ تجديد Premium",
    "notify.btn.topup": "✨ شحن الرصيد",
    "notify.btn.open": "🚀 عرض الباقات",
    "notify.btn.bonus": "🎁 استلام المكافأة",
    "notify.abandoned_cart": "🛒 كنت على بُعد خطوة من إتمام عملية الشراء! أكملها — تستغرق دقيقة.",
    "notify.btn.cart": "🛒 إكمال الشراء",
    "ref.earned_register": "🎉 سجّل مستخدم جديد عبر رابط الإحالة الخاص بك! حصلت على ✨ {amount}.",
    "ref.welcome_bonus": "🎁 مكافأة ترحيبية للانضمام عبر رابط إحالة: +✨ {amount}!",
    "promo.welcome_bonus": "🎁 مكافأة ترحيبية للمستخدم الجديد: +✨ {amount}!",
    "promo.purchase_bonus": "🎁 مكافأة على الشراء: +✨ {amount}!",
    "promo.applied": "🏷 تم تطبيق رمز الخصم: −{percent}% على عملية الشراء التالية!",
    "promo.applied_banner": "🏷 تم تطبيق خصم −{percent}%",
    "ad.remove_btn": "⭐ إزالة الإعلانات",
    "ref.milestone": "🏆 لقد دعوت {count} مستخدمين! مكافأة: +✨ {amount}.",
    "ref.earned_purchase": "🎉 تمت عملية شراء عبر رابط الإحالة الخاص بك! حصلت على ✨ {amount}.",
    "contest.won": "🎉 تهانينا! لقد فزت في المسابقة!",
    "contest.won_credits": "🎉 تهانينا! لقد فزت في المسابقة — حصلت على ✨ {amount}!",
    "contest.won_pack": "🎉 تهانينا! لقد فزت في المسابقة — حصلت على {amount} {unit}!",
    "gift.not_found": "❌ لا توجد هدية بهذا الرمز.",
    "gift.already_used": "❌ تم تفعيل هذه الهدية بالفعل.",
    "gift.own_gift": "🎁 لا يمكنك تفعيل هديتك الخاصة — شاركها مع صديق.",
    "gift.redeemed_sub": "🎁 تم تفعيل الهدية: {product} لمدة {months} شهر.",
    "gift.redeemed_pack": "🎁 تم تفعيل الهدية: باقة {product} (+{qty}).",
    "gift.redeemed_credits": "🎁 تم تفعيل الهدية: +{qty} ✨.",
    "gift.unknown_kind": "❌ نوع هدية غير معروف.",
}
