"""Simplified Chinese locale — user-facing screens; long legal/help fall back to RU."""

MESSAGES: dict[str, str] = {
    "start.welcome": (
        "你好！👋\n\n"
        "我是 SUPER AI BOT，你的 AI 助手，用现代神经网络帮你创作文本、图片、视频、音乐等等。\n\n"
        "🎁 免费：\n每周 100 次请求，用于文本、图片和其他 AI 工具。\n\n"
        "⭐️ PREMIUM：\n扩展访问最强大的神经网络。\n\n"
        "如何使用机器人？\n\n"
        "📝 文本\n在聊天中写下你的问题或任务 — 我立即帮你。\n\n"
        "🔎 搜索\n使用 /s 进行联网搜索提问。\n\n"
        "🌅 图片\n点击 /photo 创建或编辑图片。\n\n"
        "🎬 视频\n点击 /video 创建视频。\n\n"
        "🎸 音乐\n点击 /music 创建歌曲。\n\n"
        "⚙️ 模型\n/model 可以选择神经网络。\n\n"
        "💎 PREMIUM\n/premium 解锁高级功能。\n\n"
        "现在就开始 — 给我发任意消息吧 🚀"
    ),
    "account": (
        "👤 你的账户\n\n订阅：{sub}\n已选模型：{model_name} /model\n\n"
        "📊 使用统计\n\n本周请求：{used}/{limit}\n"
        "✨ 额外请求：{credits}（来自邀请和每日奖励；周限额用完后消耗）\n\n"
        "免费套餐包含：\n└ GPT-5 mini\n└ DeepSeek V4\n└ Gemini 3.1 Flash\n"
        "└ Perplexity\n└ GPT Image 2\n└ Nano Banana 2\n\n"
        "需要更多？开通 /premium\n\n"
        "🚀 Premium 订阅：\n└ 每天 100–200 次请求\n└ GPT-5.5\n└ Gemini 3.5\n"
        "└ DeepSeek\n└ Claude 4.8 Opus 和 Sonnet\n└ Nano Banana Pro\n└ 文档处理\n\n"
        "🌅 图片包：{image}\n🎬 视频包：{video}\n🎸 音乐包：{music}\n\n"
        "📞 客服：{support}"
    ),
    "account.sub_free": "免费 ✔️",
    "account.role": "🎭 角色：{title}",
    "account.role_custom": "✍️ 自定义角色",
    "account.sub_premium": "Premium ✔️",
    "account.sub_premium_x2": "Premium X2 ✔️",
    "photo.menu": (
        "🌅 创建和编辑图片\n\n请选择所需服务 👇\n\n"
        "🔴 照片特效\n用于潮流照片、肖像、头像和创意图片的现成模板。\n\n"
        "💬 GPT Image 2\nOpenAI 的 AI 修图，根据你的描述生成和编辑图片。\n\n"
        "♊️ Nano Banana Pro\nGoogle 的进阶 AI 修图，精准处理照片、替换细节并提升画质。\n\n"
        "🖼 Midjourney、Seedream、Recraft 和 FLUX\n用于艺术作品、写实照片、设计和插画的热门生成器。\n\n"
        "📸 头像套装\n上传一张照片，机器人会生成 100 个不同风格的头像。\n\n"
        "请在下方选择服务并开始创建图片 ✨"
    ),
    "video.menu": (
        "🎬 创建视频\n\n请选择生成视频的服务 👇\n\n"
        "🔴 视频特效\n用于潮流短片、短视频和创意特效的现成模板。\n\n"
        "🌱 Seedance 2.0\n根据文本、图片、视频和音频生成视频。\n\n"
        "♊ Veo 3.1、Pika 和 Hailuo\n根据描述或上传的图片生成视频。\n\n"
        "❎ Grok Imagine 和 Kling\n创建视频，也可编辑已有视频。\n\n"
        "👨 Kling Effects\n让你的照片动起来并添加视觉特效。\n\n"
        "🎥 Kling Motion\n根据示例视频中的动作让图片动起来。\n\n"
        "请在下方选择所需服务并开始创建视频 ✨"
    ),
    "music.menu": (
        "🎸 创建音乐\n\n请选择生成歌曲或音乐的服务 👇\n\n"
        "🎵 Suno V5.5\n生成长达 8 分钟的完整歌曲：音乐、人声、歌词与编曲一站式完成。\n\n"
        "♊ Lyria 3 Pro\nGoogle 新服务，生成长达 3 分钟的歌曲和器乐。\n\n"
        "你可以使用自己的歌词，或让 AI 为你创作 ✨"
    ),
    "search.intro": (
        "🔎 联网搜索\n\n"
        "在下方选择搜索模型，或使用默认模型。\n\n"
        "然后在聊天中写下你的查询 — 机器人会在网上查找最新信息并准备答案 👇"
    ),
    "model.selected": "✅ 已选择模型「{name}」。",
    "model.premium_locked": "🔒 模型「{name}」仅在 /premium 中可用。",
    "settings.lang.choose": "选择界面语言：",
    "settings.lang.saved": "✅ 语言已更改。",
    "settings.context.on": "✅ 已启用上下文。",
    "settings.context.off": "❌ 已关闭上下文。",
    "privacy.btn_terms": "📄 用户协议",
    "privacy.btn_policy": "📄 隐私政策",
    "gate.premium": "🔒 此功能仅在 /premium 中可用。",
    "gate.pack_empty": "套餐次数已用完。点击「充值」继续 👇",
    "quota.exceeded.free": "本周免费请求和 ✨ 都已用完（{used}/{limit}）。\n邀请好友 /invite 或领取每日奖励 /bonus 获取更多 ✨，或开通 /premium 🚀",
    "quota.exceeded.premium": "已达每日上限（{used}/{limit}），✨ 也已用完。明天重置，或用 /invite 和 /bonus 补充 ✨。",
    "docs.prompt": (
        "📄 文档处理\n\n"
        "向机器人发送文件并就其内容提问。\n\n"
        "支持的格式：\ndocx、pdf、xlsx、xls、csv、pptx、txt\n\n"
        "文件大小上限：最大 10 MB\n\n"
        "你可以：\n"
        "└ 获取文档摘要\n└ 查找所需信息\n"
        "└ 分析表格与文本\n└ 就文件提问\n"
        "└ 请求解释、翻译或结构化数据\n\n"
        "💎 文档处理需要 /premium 订阅。\n\n"
        "⚠️ 每次文档请求消耗 3 次生成。"
    ),
    "ai.unavailable": "⚠️ AI 服务暂时不可用，请稍后再试。",
    "ai.rate_limit": "✨ AI 有点繁忙，再发送一次即可。未消耗你的额度。",
    "common.please_wait": "请稍候 •••",
    "common.cancelled": "已取消。",  # FIX: AUDIT13-L11
    "gdpr.export_ready": "📦 您的数据已准备好——请查看附件。",  # FIX: AUDIT13-M22
    "common.coming_soon": "🛠 此板块即将上线。",
    "common.banned": "机器人访问受限。",
    "btn.model": "📝 选择模型",
    "btn.images": "🎨 创建图片",
    "btn.search": "🔎 联网搜索",
    "btn.video": "🎬 创建视频",
    "btn.documents": "📄 文档",
    "btn.music": "🎸 创建歌曲",
    "btn.premium": "🚀 Premium",
    "btn.account": "👤 我的资料",
    "btn.translate": "🌐 翻译",
    "btn.close": "关闭",
    "btn.back": "← 返回",
    "btn.connect_premium": "🚀 开通 Premium",
    "btn.topup": "🎵 充值",
    "btn.set_model": "选择模型",
    "btn.set_role": "角色描述",
    "btn.set_context": "上下文支持",
    "btn.set_voice": "语音回复",
    "btn.set_lang": "界面语言",
    "premium.choose_duration": "选择订阅时长 👇",
    "premium.choose_gateway": "选择支付方式 👇",
    "premium.upgrade_warning": "⚠️ 你有一个生效中的 {current} 套餐。剩余时间将按新的 {new} 套餐继续。",
    "premium.btn_premium": "⭐ Premium",
    "premium.btn_premium_x2": "🔥 Premium X2",
    "premium.btn_image": "🌅 图片套餐",
    "premium.btn_video": "🎬 视频套餐",
    "premium.btn_music": "🎸 音乐套餐",
    "unit.generations": "次生成",
    "unit.sec": "秒",
    "vcfg.with_sound": "带声音",
    "vcfg.enhance": "优化提示词",
    "vcfg.seed_add": "添加 seed",
    "vcfg.seed_set": "seed：{v}",
    "btn.instruction": "❤️ 指南",
    "btn.topup_pay": "💳 充值",
    "video.image_saved": "🖼 已添加图片。现在请发送视频描述 ⚡",
    "video.effects_hint": "🎬 视频特效在 Mini App 中。请从附件菜单打开 📎",
    "photo.effects_hint": "🎨 照片特效可在 Mini App 中使用。请从附件菜单打开 📎",  # FIX: AUDIT13-L13
    "tts.unavailable": "⚠️ 语音播报暂时不可用。",
    "tts.failed": "⚠️ 无法朗读回复。",
    "doc.unsupported": "支持：pdf、docx、doc、xlsx、xls、csv、pptx、txt（最大 10 MB）。",
    "doc.too_large": "文件过大，最大 10 MB。",
    "doc.extract_failed": "无法从文件中提取文本。",
    "doc.empty": "文件中未找到文本。",
    "doc.received": "📄 已收到文件「{name}」。就其内容提问吧 — 每次请求消耗 {cost} 次生成。",
    "btn.translate_hint": "🌐 点击 AI 回复下方的 🌐 进行翻译。",
    "voice.selected": "声音：{voice}",
    "voice.sample": "你好！所选声音听起来是这样的。",
    "search.nothing": "未找到任何内容。",
    "btn.daily_bonus": "🎁 每日奖励",
    "bonus.claimed": "🎁 已领取奖励：+{amount} ✨ · 连续：{streak} 🔥",
    "bonus.already": "✅ 今天已领取，明天再来！· 连续：{streak} 🔥",
    "notify.premium_granted": "🎁 您获赠了 {months} 个月的 Premium！尽情享受吧 💎",
    "notify.premium_revoked": "ℹ️ 您的 Premium 订阅已被管理员关闭。",
    "notify.banned": "🚫 您的账号已被封禁。如有误封，请联系客服。",
    "notify.unbanned": "✅ 您的账号已解封，可以继续使用机器人了。",
    "contact.saved": "✅ 谢谢！您的电话号码已保存。",
    "btn.open_app": "🚀 打开应用",
    "voice.on": "🔊 语音：开",
    "voice.off": "🔇 语音：关",
    "throttle.flood": "⏳ 请求过多，请稍候。",
    "srv.photoeffects": "🎨 照片特效",
    "srv.videoeffects": "🎬 视频特效",
    "srv.avatar": "👤 头像套装",
    "srv.faceswap": "🔄 换脸",
    "srv.upscale": "📐 放大 X2/X4",
    "pack.label.popular": "热门",
    "pack.label.best": "最佳选择",
    "product.premium": "Premium",
    "product.premium_x2": "Premium X2",
    "pack.name.image": "图片套餐",
    "pack.name.video": "视频套餐",
    "pack.name.music": "音乐套餐",
    "duration.1": "1 个月",
    "duration.3": "3 个月",
    "duration.6": "6 个月",
    "duration.12": "1 年",
    "pack.choose": "请选择「{name}」套餐 👇",
    # ----- VIP / loyalty (ТЗ §4) -----
    "btn.vip": "🏅 VIP 等级",
    "account.vip": "🏅 等级：{tier} · 距 {next} 还差 {left} ⭐",
    "account.vip_top": "🏅 等级：{tier}（最高）",
    "account.vip_none": "🏅 距 {next} 等级还差 {left} ⭐",
    "vip.title": "🏅 VIP 等级\n您的累计消费：{spent} ⭐\n",
    "vip.row": "{mark} {name} — {min} ⭐ 起 · +{daily}/天，+{weekly}/周",
    "vip.reached": "🎉 恭喜！您已达到 VIP 等级 {tier}。\n现在您每天 +{daily} 次生成，每周 +{weekly} 次。",
    # ----- global sale (ТЗ §4) -----
    "sale.banner": "🔥 促销 −{percent}%",
    "sale.ends_in": "⏳ 剩余：{time}",
    "sale.left_dh": "{d}天 {h}小时",
    "sale.left_hm": "{h}小时 {m}分",
    "sale.left_m": "{m}分",
    "pay.sub_invoice_desc": "订阅：{title}",
    "pay.pack_invoice_desc": "生成套餐：{title}",
    "pay.sub_activated": "✅ 订阅「{title}」已开通！感谢购买 🚀",
    "pay.pack_added": "✅ 套餐已充值：+{qty} {unit}（{pack}）。感谢购买！",
    "pay.avatar_paid": "✅ 已支付！发送你最好的自拍 — 我将生成 100 个头像（约 15 分钟）。",
    "pay.link": "打开链接付款。支付成功后将自动开通 👇",
    "pay.link_btn": "💳 支付 — {title}",
    "pay.unavailable": "该支付方式当前不可用。",
    "pay.failed": "无法创建账单，请尝试其他方式。",
    "gen.video_started": "🎬 视频生成已开始！需要几分钟 — 完成后我会发给你。",
    "gen.music_started": "🎶 正在生成你的歌曲 — 完成后我会发送音频！",
    "gen.photo_started": "🎨 正在应用「{name}」— 完成后我会发送视频！",
    "gen.unavailable": "⚠️ 服务暂时不可用，请稍后再试。",
    "gen.unavailable_refund": "⚠️ 服务暂时不可用。积分已退回。",
    "gen.error_refund": "⚠️ 生成出错。积分已退回。",
    "mod.blocked": "🚫 该请求违反使用规则。",
    "seed.ask": "请输入用于生成的 seed（数值）：",
    "seed.saved": "✅ Seed 已保存。",
    "avatar.info": (
        "👤 AI 头像\n\n为社交平台创建 100 个不同风格的酷头像。\n"
        "价格：每套 {price} ⭐。分辨率 1024×1440，无水印。\n"
        "支付后上传你最好的自拍 — 生成约 15 分钟。"
    ),
    "avatar.title": "头像套装",
    "avatar.buy_btn": "{price} ⭐ 购买",
    "avatar.started": (
        "🎨 已开始生成 100 个头像！约需 15 分钟 — 你可以继续使用机器人，完成后我会发给你。"
    ),
    "music.prompt": "🎵 {name}：发送歌曲描述（风格、情绪、歌词）。",
    "kling.effects_intro": (
        "🌊 Kling Effects\n\n1. 从下方选项中选择一个特效。\n"
        "2. 向机器人发送一张照片以应用所选特效。"
    ),
    "kling.effect_selected": "特效：{name}\n\n发送一张照片，机器人会应用你选择的特效！",
    "kling.motion_intro": (
        "💃 Kling Motion\n\n你的照片会动起来，重现示例视频中的动作。\n"
        "请选择一个模板 👇"
    ),
    "kling.motion_selected": "动作：💃 {name}。发送一张照片 — Kling Motion 会把动作迁移到照片上。",
    "btn.voice": "🔊",
    "btn.view": "🔥 查看",
    "deletecontext.done": "上下文已清除。默认情况下机器人会参考你上一个问题及其回答。",
    "music.paywall": "🎵 要生成歌曲，请购买音乐包。点击下方「充值」👇",
    "gate.subscription": "要继续免费使用机器人，请订阅我们的频道 👇\n然后点击「我已订阅」。",
    "gate.subscription.ok": "✅ 感谢订阅！可以继续了。",
    "gate.subscription.fail": "❌ 看起来你还没有订阅。",
    "settings.role.prompt": "发送 AI 应遵循的角色（系统提示）。",
    "settings.role.current_none": "当前角色：未设置。",
    "settings.role.current": "当前角色：\n{role}",
    "settings.role.saved": "✅ 角色已保存。",
    "settings.role.cleared": "角色已删除。",
    "settings.role.too_long": "❌ 角色过长（最多 {limit} 个字符）。请缩短后重新发送。",
    "settings.voice.intro": "为语音回复选择一个声音（/premium 可用）：",
    "settings.voice.preview": "试听所选声音",
    "settings.intro": (
        "⚙️ 机器人设置\n\n在这里你可以按需调整 AI 👇\n\n"
        "1️⃣ 选择模型 — 回答你请求的网络。\n\n"
        "2️⃣ 设置角色 — 例如助手、文案、程序员、老师或专家。\n\n"
        "3️⃣ 对话上下文 — 开启或关闭。开启时机器人会参考上一条回答。\n\n"
        "4️⃣ 语音回复 — 设置朗读并选择声音。/premium 可用。\n\n"
        "5️⃣ 界面语言 — 选择顺手的语言。\n\n"
        "请在下方选择 👇"
    ),
    "model.intro": (
        "🤖 选择 AI 模型\n\n机器人提供用于文本、代码、分析和复杂任务的领先模型。\n\n"
        "请在下方选择模型 👇\n\n"
        "💬 GPT-5.5 — OpenAI 顶级模型。每次请求消耗 3 次生成。\n\n"
        "💬 GPT-5.4 — 适合编程与文本的通用模型。\n\n"
        "💬 GPT-5 mini — 适合日常的快速模型。免费。\n\n"
        "🌥 Claude 4.8 Opus — Anthropic 顶级模型。每次请求消耗 5 次生成。\n\n"
        "🌥 Claude 4.6 Sonnet — 擅长文本、编程与数学。\n\n"
        "🐳 DeepSeek V4 — 快速强大。免费。\n\n"
        "🐳 DeepSeek V4 Pro — DeepSeek 进阶版。\n\n"
        "♊️ Gemini 3.5 Flash — Google 顶级模型。\n\n"
        "♊️ Gemini 3.1 Flash — 快速智能的 Google 模型。免费。\n\n"
        "📌 文档：Premium 可发送最大 10 MB 的文件并提问，消耗 3 次生成。\n\n"
        "🎁 免费：GPT-5 mini、Gemini 3.1 Flash、DeepSeek V4\n💎 其他模型在 Premium：/premium\n\n"
        "请在下方选择模型 👇"
    ),
    "help": (
        "📚 机器人帮助\n\n主要命令与功能。\n\n"
        "📝 文本生成\n直接在聊天中写下请求。/premium 用户还可发送语音消息。\n\n"
        "命令：\n└ /deletecontext — 开始新对话\n└ /s — 联网搜索\n"
        "└ /settings — 模型、角色、语言与上下文\n└ /model — 选择模型\n\n"
        "💡 描述越详细，回答越准确。\n\n"
        "📄 文档（Premium）\n上传最大 10 MB 的文件并提问。\n格式：docx、pdf、xlsx、xls、csv、pptx、txt。\n每次请求消耗 3 次生成。\n\n"
        "🌅 图片\n└ Nano Banana 2 / Pro\n└ GPT Image 2\n└ Midjourney\n└ Flux\n└ Seedream\n└ Recraft\n命令：/photo、/midjourney\n\n"
        "🎬 视频\n└ Kling\n└ Seedance 2.0\n└ Pika\n└ Veo 3.1\n└ Hailuo\n└ Grok Imagine\n命令：/video\n\n"
        "🎸 音乐\n└ Suno V5.5\n└ Lyria 3 Pro\n命令：/music、/suno\n\n"
        "⚙️ 其他\n└ /start\n└ /account\n└ /premium\n└ /privacy\n\n"
        "💬 有问题请联系：{support}"
    ),
    "privacy": (
        "🔐 法律文件\n\n使用机器人前，请阅读服务规则与数据处理条款：\n\n"
        "1️⃣ 用户协议\n2️⃣ 隐私政策\n\n"
        "继续使用机器人即表示你已阅读并接受这些条款。"
    ),
    "premium": (
        "🚀 套餐与功能\n\n机器人将热门 AI 服务集于一处：文本、搜索、图片、视频、音乐和文件。\n\n"
        "🎁 免费 | 每周\n\n100 次任意请求：\n✅ GPT-5 mini\n✅ DeepSeek V4\n✅ Gemini 3.1 Flash\n✅ Perplexity\n✅ 图像识别\n\n"
        "25 次图片生成：\n♊️ Nano Banana 2\n✅ GPT Image 2\n\n"
        "💎 PREMIUM | 1 个月\n\n上限：每天 100 次\n\n✅ 免费套餐全部功能\n✅ GPT-5.5\n✅ Gemini 3.5 Flash\n✅ Claude 4.8 Opus 和 Sonnet\n✅ DeepSeek\n♊️ Nano Banana Pro\n✅ GPT Image 2\n✅ 文档处理\n✅ 语音回复\n✅ 无广告\n\n价格：{p_premium}⭐️\n\n"
        "💎 PREMIUM X2 | 1 个月\n\n上限：每天 200 次\n\n✅ Premium 全部功能\n✅ 更高的每日上限\n\n价格：{p_premium_x2}⭐️\n\n"
        "🌅 图片 | 套餐包\n\n可选 50 至 500 次生成\n\n可用服务：\n"
        "🌅 Midjourney\n🎬 Midjourney Video\n🌱 Seedream\n🎨 Recraft\n⚡ Flux\n✅ 照片换脸\n\n价格：{p_image_from}⭐️ 起\n\n"
        "🎬 视频 | 套餐包\n\n可选 2 至 50 次生成\n\n可用服务：\n"
        "📼 Kling\n🎥 Veo 3.1\n🚀 Seedance 2.0\n❎ Grok Imagine\n🎞 Hailuo\n✨ Pika\n\n"
        "另外：\n✅ 视频编辑\n✅ 创意视频特效\n\n价格：{p_video_from}⭐️ 起\n\n"
        "🎸 音乐 | 套餐包\n\n可选 20 至 100 次生成\n\n可用服务：\n"
        "🎸 Suno V5.5\n🎼 Lyria 3 Pro\n\n功能：\n✅ 用你自己的歌词创作\n✅ 用 AI 生成歌词\n\n价格：{p_music_from}⭐️ 起\n\n"
        "⭐️ 所有价格以 Stars（Telegram 货币）计。\n\n💬 支付与开通：\n{support}"
    ),
    "gate.channel": "要继续免费使用机器人，请订阅下方频道。\n\n通过订阅，您每周可获得 100 次对 ChatGPT、DeepSeek、Gemini、Perplexity、图像生成器等的免费请求。\n\n想要无广告的全部功能？点击 Premium。",
    "gate.btn_subscribe": "订阅 {channel}",
    "gate.btn_check": "检查订阅",
    "gate.btn_premium": "会员",
    "gate.ok": "感谢订阅！您可以继续了。",
    "gate.not_subscribed": "您尚未订阅所有频道。",
    "gate.premium_voice": "要发送语音请求，请订阅 /premium。",
    "faceswap.step1": "[第1/2步] 发送需要替换人脸的图片。",
    "faceswap.step2": "[第2/2步] 现在发送提供人脸的照片。",
    "upscale.intro": "该工具可提高图片分辨率。请选择倍数。",
    "upscale.x2": "放大 X2",
    "upscale.x4": "放大 X4",
    "upscale.send_image": "发送图片（最大 1024x1024）。将扣除 {cost} 次生成。",
    "vision.coming_soon": "图像识别即将上线。",
    "vision.failed": "无法处理图片，请重试。",
    "photo.choose": "要对这张照片做什么？",
    "photo.btn_describe": "🔎 描述",
    "photo.btn_edit": "🎨 按说明编辑",
    "photo.edit_working": "🎨 正在编辑照片…",
    "photo.edit_done": "✅ 完成！",
    "photo.edit_unavailable": "🛠 照片编辑功能即将推出。",
    "photo.edit_failed": "无法编辑照片，请重试。",
    "photo.edit_no_caption": "请为照片添加描述编辑内容的说明，我会修改图片。",
    "voice_in.coming_soon": "语音输入即将上线。",
    "voice_in.heard": "🎙 已识别：«{text}»",
    "voice_in.empty": "未能识别语音，请重新录制。",
    "voice_in.failed": "无法处理语音消息，请重试。",
    "gen.image_started": "已收到请求！准备就绪后我会发送结果。",
    "pay.credits_added": "✨ 已添加 {qty} 积分！可在小程序中使用。",
    "img.more": "🔄 再来一张",
    "img.upscale": "🔍 放大",
    "img.file": "📎 原画质",
    "img.no_prompt": "请先选择服务并发送提示词。",
    "promo.usage": "用法：/promo 兑换码",
    "promo.invalid": "❌ 该兑换码无效或已过期。",
    "promo.already": "您已经兑换过此兑换码。",
    "promo.ok": "✅ 兑换码已激活：+{amount}（{reward}）。",
    "promo.not_eligible": "❌ 此兑换码仅限新用户使用。",
    # --- bot UI strings (handlers sweep) ---
    "fb.thanks": "感谢你的反馈！",
    "report.usage": "用法：<code>/report 问题描述</code>",
    "report.thanks": "谢谢！您的反馈已收到。",
    "roles.btn_off": "🚫 关闭角色",
    "roles.btn_custom": "✍️ 自定义角色",
    "roles.unavailable": "预设角色暂时不可用。",
    "roles.choose": "🎭 为助手选择一个预设角色。",
    "roles.choose_active": "\n\n当前已启用自定义角色——请选择新角色或将其关闭。",
    "roles.not_found": "未找到角色",
    "roles.enabled": "已启用角色“{title}” ✅",
    "roles.enabled_full": "完成——助手现在以“{title}”的身份工作。要关闭，请发送 /roles → “关闭角色”。",
    "roles.disabled": "角色已关闭",
    "roles.disabled_full": "助手角色已关闭——普通模式。",
    "contest.none": "目前没有进行中的活动。请稍后再来！",
    "contest.entrants": "参与人数：{count}",
    "contest.btn_enter": "参与",
    "contest.ended": "该活动已经结束。",
    "contest.entered": "你已参加活动！祝你好运！🍀",
    "contest.already": "你已经参加了该活动。",
    "gift.btn_premium": "🎁 Premium · 1 个月",
    "gift.btn_pack": "🎁 图片包 · 50",
    "gift.btn_sub": "🎁 赠送订阅",
    "gift.btn_pack_menu": "📦 赠送套餐",
    "gift.pack_none": "套餐暂时不可用。",
    "gift.choose": "🎁 给朋友赠送订阅或套餐。\n请选择要赠送的内容：",
    "gift.invoice_title_sub": "🎁 {product} · {value} 个月",
    "gift.invoice_desc": "礼物：{title}",
    "gift.paid": "🎁 礼物已支付！\n\n兑换码：<code>{code}</code>\n\n把命令 <code>/redeem {code}</code> 或此链接发给好友：\n{link}",
    "redeem.usage": "用法：<code>/redeem 兑换码</code>",
    "inline.hint_title": "输入问题…",
    "inline.hint_text": "在机器人名称后输入问题即可获得 AI 回答。",
    "inline.error_title": "错误",
    "inline.error_text": "无法获取回答。请稍后再试。",
    "inline.throttle_title": "操作过于频繁",
    "inline.throttle_text": "连续请求过多。请稍候片刻再试。",
    "support.usage": "用法：<code>/support 你的问题</code>\n请描述问题——你的消息会发送给客服。",
    "support.sent": "消息已发送给客服，我们会尽快回复。",
    "pay.precheckout_unavailable": "支付不可用",
    "pay.activate_failed": "⚠️ 无法激活购买。您的支付（⭐）已退款。请重试或联系客服。",
    "invite.summary": "🔗 你的邀请链接：\n{link}\n\n👥 已邀请用户：{count}\n✨ 每位邀请奖励：{reward}\n💰 累计获得：✨ {earned}",
    "links.none": "暂未配置链接。",
    "links.title": "实用链接：",
    "avatar.invoice_desc": "100 个 AI 头像 1024×1440",
    "promo.reward.credits": "积分",
    "promo.reward.image": "张图片",
    "promo.reward.video": "个视频",
    "promo.reward.music": "首音乐",
    "promo.reward.premium": "天 Premium",
    "pay.success": "✅ 支付成功！您的权限已激活。感谢购买 🚀",
    "gen.video_ready": "✅ 你的视频已生成！",
    "gen.song_ready": "✅ 你的歌曲已生成！",
    "gen.photo_ready": "✅ 你的照片已生成！",
    "gen.avatar_unavailable_refund": "⚠️ “头像”服务暂时不可用。您的支付（⭐）已全额退回到您的 Telegram 余额。抱歉！",
    "spec.desc.gpt_image2": "直接在聊天中创建和编辑图片。\n\n准备好了吗？\n发送 1 到 4 张要编辑的图片，或输入你想创建的内容。",
    "spec.desc.nano_banana": "Gemini Images — 更鲜艳，更智能！\n\n在聊天中创建和编辑图片。发送 1 到 10 张图片，或输入你想创建的内容。",
    "spec.desc.seedream": "在聊天中创建和编辑图片。发送 1 到 10 张图片，或输入你想创建的内容。",
    "spec.desc.midjourney": "输入你想创建的图片。\n\n机器人支持 Midjourney 的所有主要参数和功能。",
    "spec.desc.flux2": "选择宽高比和 Flux 模型。Flex 和 Max 模型消耗 2 次生成。\n\n开始前，请输入你想创建的图片 🐝",
    "spec.desc.recraft": "Recraft — 矢量图形与设计。输入你想创建的图片。",
    "spec.desc.seedance": "根据文本、图片、视频和音频生成视频。\n\n设置选项并发送提示词以开始 ⚡",
    "spec.desc.veo": "Veo 3.1 — 谷歌出品的电影级视频。发送提示词 ⚡",
    "spec.desc.grok": "创建和编辑视频。编辑器消耗 2 次生成。\n禁止 18+、暴力和深度伪造。发送提示词 ⚡",
    "spec.desc.kling_ai": "创建和编辑视频。发送提示词 ⚡",
    "spec.desc.hailuo": "Hailuo — 根据描述和图片生成视频。发送提示词 ⚡",
    "spec.desc.pika": "Pika Labs — 根据描述和图片生成视频。发送提示词 ⚡",
    "spec.desc.mj_video": "Midjourney Video — 图片动画。发送照片和/或提示词 ⚡\n从图片包扣除。",
    "spec.mode.create": "创建",
    "spec.mode.edit": "编辑器",
    "gen.ready_generic": "✅ 你的生成（{service}）已完成。",
    "refund.stars": "⚠️ 订单未能完成。款项（⭐）已退回到你的 Telegram 余额。我们深表歉意！",
    "notify.premium_expiry": "⏳ 你的 Premium 将在 {days} 天后到期。续订以免失去更高的额度。",
    "notify.low_balance": "✨ 余额快用完了 — 还剩 {balance} ✨。充值即可不间断地继续生成。",
    "notify.winback": "👋 好久不见！回来看看吧 — 我们上线了新模型和新效果。发送请求，我们继续 🙌",
    "notify.bonus_available": "🎁 你的每日奖励已就绪！今天领取以保持连续记录并获得更多 ✨。",
    "notify.btn.renew": "⭐ 续订 Premium",
    "notify.btn.topup": "✨ 充值",
    "notify.btn.open": "🚀 查看套餐",
    "notify.btn.bonus": "🎁 领取奖励",
    "notify.abandoned_cart": "🛒 你离完成购买只差一步！现在完成，只需一分钟。",
    "notify.btn.cart": "🛒 完成购买",
    "ref.earned_register": "🎉 有新用户通过你的推荐链接注册了！你获得了 ✨ {amount}。",
    "ref.welcome_bonus": "🎁 通过推荐链接加入的欢迎奖励：+✨ {amount}！",
    "promo.welcome_bonus": "🎁 新用户欢迎奖励：+✨ {amount}！",
    "promo.purchase_bonus": "🎁 购买奖励：+✨ {amount}！",
    "promo.applied": "🏷 优惠码已应用：下次购买 −{percent}%！",
    "promo.applied_banner": "🏷 已应用优惠码 −{percent}%",
    "ad.remove_btn": "⭐ 去除广告",
    "ref.milestone": "🏆 你已邀请 {count} 位用户！奖励：+✨ {amount}。",
    "ref.earned_purchase": "🎉 有人通过你的推荐链接完成了购买！你获得了 ✨ {amount}。",
    "contest.won": "🎉 恭喜！你在抽奖中获奖了！",
    "contest.won_credits": "🎉 恭喜！你在抽奖中获奖了 — 获得了 ✨ {amount}！",
    "contest.won_pack": "🎉 恭喜！你在抽奖中获奖了 — 获得了 {amount} {unit}！",
    "gift.not_found": "❌ 未找到该兑换码对应的礼物。",
    "gift.already_used": "❌ 该礼物已被激活。",
    "gift.own_gift": "🎁 不能激活自己的礼物 — 把它分享给朋友吧。",
    "gift.redeemed_sub": "🎁 礼物已激活：{product}，{months} 个月。",
    "gift.redeemed_pack": "🎁 礼物已激活：{product} 套餐（+{qty}）。",
    "gift.redeemed_credits": "🎁 礼物已激活：+{qty} ✨。",
    "gift.unknown_kind": "❌ 未知的礼物类型。",
}
