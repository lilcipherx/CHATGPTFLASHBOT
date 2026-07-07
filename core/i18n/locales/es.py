"""Spanish locale — user-facing screens; long legal/help fall back to RU."""

MESSAGES: dict[str, str] = {
    "start.welcome": (
        "¡Hola! 👋\n\n"
        "Soy SUPER AI BOT, tu asistente de IA que te ayuda a crear texto, imágenes, vídeo, "
        "música y mucho más con redes neuronales modernas.\n\n"
        "🎁 GRATIS:\n100 solicitudes por semana para texto, imágenes y otras herramientas de IA.\n\n"
        "⭐️ PREMIUM:\nAcceso ampliado a las redes neuronales más potentes.\n\n"
        "¿Cómo usar el bot?\n\n"
        "📝 TEXTO\nEscribe tu pregunta o tarea en el chat — te ayudo enseguida.\n\n"
        "🔎 BÚSQUEDA\nUsa /s para preguntar con búsqueda en internet.\n\n"
        "🌅 IMÁGENES\nPulsa /photo para crear o editar una imagen.\n\n"
        "🎬 VÍDEO\nPulsa /video para crear un clip.\n\n"
        "🎸 MÚSICA\nPulsa /music para crear una canción.\n\n"
        "⚙️ MODELO\n/model permite elegir la red neuronal.\n\n"
        "💎 PREMIUM\n/premium desbloquea funciones avanzadas.\n\n"
        "Empieza ahora — envíame cualquier mensaje 🚀"
    ),
    "account": (
        "👤 Tu cuenta\n\nSuscripción: {sub}\nModelo seleccionado: {model_name} /model\n\n"
        "📊 Estadísticas de uso\n\nSolicitudes esta semana: {used}/{limit}\n"
        "✨ Solicitudes extra: {credits} (de referidos y bono diario; se gastan cuando se agota el límite semanal)\n\n"
        "Disponible en el plan gratuito:\n└ GPT-5 mini\n└ DeepSeek V4\n└ Gemini 3.1 Flash\n"
        "└ Perplexity\n└ GPT Image 2\n└ Nano Banana 2\n\n"
        "¿Necesitas más? Activa /premium\n\n"
        "🚀 Suscripción Premium:\n└ 100–200 solicitudes/día\n└ GPT-5.5\n└ Gemini 3.5\n"
        "└ DeepSeek\n└ Claude 4.8 Opus y Sonnet\n└ Nano Banana Pro\n└ Documentos\n\n"
        "🌅 Paquete de imágenes: {image}\n🎬 Paquete de vídeo: {video}\n🎸 Paquete de música: {music}\n\n"
        "📞 Soporte: {support}"
    ),
    "account.sub_free": "Gratis ✔️",
    "account.role": "🎭 Rol: {title}",
    "account.role_custom": "✍️ rol propio",
    "account.sub_premium": "Premium ✔️",
    "account.sub_premium_x2": "Premium X2 ✔️",
    "photo.menu": (
        "🌅 Creación y edición de imágenes\n\nElige el servicio que necesitas 👇\n\n"
        "🔴 Efectos de foto\nPlantillas listas para fotos de tendencia, retratos, avatares e imágenes creativas.\n\n"
        "💬 GPT Image 2\nPhotoshop con IA de OpenAI para generar y editar imágenes según tu descripción.\n\n"
        "♊️ Nano Banana Pro\nPhotoshop con IA avanzado de Google para edición precisa, reemplazo de detalles y mejora de imágenes.\n\n"
        "🖼 Midjourney, Seedream, Recraft y FLUX\nGeneradores populares para arte, fotos realistas, diseño e ilustraciones.\n\n"
        "📸 Paquete de avatares\nSube una foto y el bot creará 100 avatares en distintos estilos.\n\n"
        "Elige un servicio abajo y empieza a crear tu imagen ✨"
    ),
    "video.menu": (
        "🎬 Creación de vídeo\n\nElige el servicio para generar el clip 👇\n\n"
        "🔴 Efectos de vídeo\nPlantillas listas para clips de tendencia, vídeos cortos y efectos creativos.\n\n"
        "🌱 Seedance 2.0\nCrea vídeo a partir de texto, imágenes, vídeo y audio.\n\n"
        "♊ Veo 3.1, Pika y Hailuo\nGeneran vídeo a partir de una descripción o una imagen cargada.\n\n"
        "❎ Grok Imagine y Kling\nCrean vídeo y también ayudan a editar clips ya listos.\n\n"
        "👨 Kling Effects\nDa vida a tus fotos y les añade efectos visuales.\n\n"
        "🎥 Kling Motion\nAnima una imagen repitiendo los movimientos de un vídeo de ejemplo.\n\n"
        "Elige el servicio abajo y empieza a crear tu vídeo ✨"
    ),
    "music.menu": (
        "🎸 Creación de música\n\nElige el servicio para generar una canción o música 👇\n\n"
        "🎵 Suno V5.5\nCrea canciones completas de hasta 8 minutos: música, voz, letra y arreglo llave en mano.\n\n"
        "♊ Lyria 3 Pro\nNuevo servicio de Google para generar canciones y música instrumental de hasta 3 minutos.\n\n"
        "Puedes usar tu propia letra o pedirle a la IA que la invente por ti ✨"
    ),
    "search.intro": (
        "🔎 Búsqueda en internet\n\n"
        "Elige el modelo de búsqueda abajo o usa el predeterminado.\n\n"
        "Después escribe tu consulta en el chat — el bot encontrará información actual en internet y preparará una respuesta 👇"
    ),
    "model.selected": "✅ Modelo «{name}» seleccionado.",
    "model.premium_locked": "🔒 El modelo «{name}» solo está disponible en /premium.",
    "settings.lang.choose": "Elige el idioma de la interfaz:",
    "settings.lang.saved": "✅ Idioma cambiado.",
    "settings.context.on": "✅ Contexto activado.",
    "settings.context.off": "❌ Contexto desactivado.",
    "privacy.btn_terms": "📄 Términos de uso",
    "privacy.btn_policy": "📄 Política de privacidad",
    "gate.premium": "🔒 Esta función solo está disponible en /premium.",
    "gate.pack_empty": "Se acabaron las generaciones del paquete. Pulsa «Recargar» 👇",
    "quota.exceeded.free": "Has usado tus solicitudes gratis esta semana ({used}/{limit}) y tus ✨ también.\nInvita amigos /invite o reclama el bono diario /bonus para más ✨, o activa /premium 🚀",
    "quota.exceeded.premium": "Límite diario alcanzado ({used}/{limit}) y los ✨ se agotaron. Se renueva mañana, o recarga ✨ con /invite y /bonus.",
    "docs.prompt": (
        "📄 Trabajo con documentos\n\n"
        "Envía un archivo al bot y haz preguntas sobre su contenido.\n\n"
        "Formatos admitidos:\ndocx, pdf, xlsx, xls, csv, pptx, txt\n\n"
        "Tamaño máximo: hasta 10 MB\n\n"
        "Qué puedes hacer:\n"
        "└ obtener un resumen del documento\n└ buscar información concreta\n"
        "└ analizar tablas y textos\n└ hacer preguntas sobre el archivo\n"
        "└ pedir explicar, traducir o estructurar los datos\n\n"
        "💎 El trabajo con documentos requiere suscripción /premium.\n\n"
        "⚠️ Cada solicitud sobre el documento consume 3 generaciones."
    ),
    "ai.unavailable": "⚠️ El servicio de IA no está disponible por ahora. Inténtalo un poco más tarde.",
    "ai.rate_limit": "✨ La IA está un poco ocupada — envía tu mensaje de nuevo. No se gastó tu cuota.",
    "common.please_wait": "Espera un momento •••",
    "common.cancelled": "Cancelado.",  # FIX: AUDIT13-L11
    "gdpr.export_ready": "📦 Tus datos están listos — archivo adjunto.",  # FIX: AUDIT13-M22
    "common.coming_soon": "🛠 Esta sección estará disponible pronto.",
    "common.banned": "El acceso al bot está restringido.",
    "btn.model": "📝 Elegir modelo",
    "btn.images": "🎨 Crear imagen",
    "btn.search": "🔎 Búsqueda web",
    "btn.search_model": "🔎 Modelo de búsqueda: {name}",
    "search.choose_model": "Elige un modelo para la búsqueda en internet 👇",
    "search.model_set": "✅ Modelo de búsqueda: {name}",
    "btn.video": "🎬 Crear vídeo",
    "btn.documents": "📄 Documento",
    "btn.music": "🎸 Crear canción",
    "btn.premium": "🚀 Premium",
    "btn.account": "👤 Mi perfil",
    "btn.translate": "🌐 Traducir",
    "btn.close": "Cerrar",
    "btn.back": "← Atrás",
    "btn.connect_premium": "🚀 Obtener Premium",
    "btn.topup": "🎵 Recargar",
    "btn.set_model": "Elegir modelo",
    "btn.set_role": "Descripción del rol",
    "btn.set_context": "Soporte de contexto",
    "btn.set_voice": "Respuestas de voz",
    "btn.set_lang": "Idioma de interfaz",
    "premium.choose_duration": "Elige el período de suscripción 👇",
    "premium.choose_gateway": "Elige el método de pago 👇",
    "premium.upgrade_warning": "⚠️ Tienes un plan {current} activo. El tiempo restante continuará con el nuevo plan {new}.",
    "premium.btn_premium": "⭐ Premium",
    "premium.btn_premium_x2": "🔥 Premium X2",
    "premium.btn_image": "🌅 Paquete de imágenes",
    "premium.btn_video": "🎬 Paquete de vídeo",
    "premium.btn_music": "🎸 Paquete de música",
    "unit.generations": "generaciones",
    "unit.sec": "s",
    "vcfg.with_sound": "Con sonido",
    "vcfg.enhance": "Mejorar prompt",
    "vcfg.seed_add": "Añadir seed",
    "vcfg.seed_set": "seed: {v}",
    "btn.instruction": "❤️ Guía",
    "btn.topup_pay": "💳 Recargar",
    "video.image_saved": "🖼 Imagen añadida. Ahora envía una descripción del vídeo ⚡",
    "video.effects_hint": "🎬 Los efectos de vídeo están en la Mini App. Ábrela desde el menú de adjuntos 📎",
    "photo.effects_hint": "🎨 Los efectos de foto están disponibles en la Mini App. Ábrela desde el menú de adjuntos 📎",  # FIX: AUDIT13-L13
    "tts.unavailable": "⚠️ La voz no está disponible por ahora.",
    "tts.failed": "⚠️ No se pudo poner voz a la respuesta.",
    "doc.unsupported": "Admitidos: pdf, docx, doc, xlsx, xls, csv, pptx, txt (hasta 10 MB).",
    "doc.too_large": "Archivo demasiado grande. Máximo 10 MB.",
    "doc.extract_failed": "No se pudo extraer texto del archivo.",
    "doc.empty": "No se encontró texto en el archivo.",
    "doc.received": "📄 Archivo «{name}» recibido. Haz preguntas — cada solicitud consume {cost} generaciones.",
    "btn.translate_hint": "🌐 Pulsa 🌐 bajo la respuesta de la IA para traducirla.",
    "voice.selected": "Voz: {voice}",
    "voice.sample": "¡Hola! Así suena la voz seleccionada.",
    "search.nothing": "No se encontró nada.",
    "btn.daily_bonus": "🎁 Bono diario",
    "bonus.claimed": "🎁 Bono recibido: +{amount} ✨ · Racha: {streak} 🔥",
    "bonus.already": "✅ Ya reclamado hoy. ¡Vuelve mañana! · Racha: {streak} 🔥",
    "notify.premium_granted": "🎁 ¡Te han regalado Premium por {months} mes(es)! Disfruta 💎",
    "notify.premium_revoked": "ℹ️ Tu suscripción Premium fue desactivada por un administrador.",
    "notify.banned": "🚫 Tu cuenta ha sido bloqueada. Si es un error, contacta con soporte.",
    "notify.unbanned": "✅ Tu cuenta ha sido desbloqueada. Puedes usar el bot de nuevo.",
    "contact.saved": "✅ ¡Gracias! Tu número de teléfono fue guardado.",
    "btn.open_app": "🚀 Abrir la app",
    "voice.on": "🔊 Voz: ON",
    "voice.off": "🔇 Voz: OFF",
    "throttle.flood": "⏳ Demasiadas solicitudes. Espera un momento.",
    "srv.photoeffects": "🎨 Efectos de foto",
    "srv.videoeffects": "🎬 Efectos de vídeo",
    "srv.avatar": "👤 Paquete de avatares",
    "srv.faceswap": "🔄 Cambio de cara",
    "srv.upscale": "📐 Mejorar X2/X4",
    "pack.label.popular": "POPULAR",
    "pack.label.best": "MEJOR OPCIÓN",
    "product.premium": "Premium",
    "product.premium_x2": "Premium X2",
    "pack.name.image": "Paquete de imágenes",
    "pack.name.video": "Paquete de vídeo",
    "pack.name.music": "Paquete de música",
    "duration.1": "1 mes",
    "duration.3": "3 meses",
    "duration.6": "6 meses",
    "duration.12": "1 año",
    "pack.choose": "Elige el paquete «{name}» 👇",
    # ----- VIP / loyalty (ТЗ §4) -----
    "btn.vip": "🏅 Niveles VIP",
    "account.vip": "🏅 Nivel: {tier} · faltan {left} ⭐ para {next}",
    "account.vip_top": "🏅 Nivel: {tier} (máximo)",
    "account.vip_none": "🏅 Faltan {left} ⭐ para el nivel {next}",
    "vip.title": "🏅 Niveles VIP\nTu gasto total: {spent} ⭐\n",
    "vip.row": "{mark} {name} — desde {min} ⭐ · +{daily}/día, +{weekly}/sem",
    "vip.reached": "🎉 ¡Enhorabuena! Has alcanzado el nivel VIP {tier}.\nAhora tienes +{daily} generaciones/día y +{weekly}/semana.",
    # ----- global sale (ТЗ §4) -----
    "sale.banner": "🔥 Rebaja −{percent}%",
    "sale.ends_in": "⏳ termina en: {time}",
    "sale.left_dh": "{d}d {h}h",
    "sale.left_hm": "{h}h {m}m",
    "sale.left_m": "{m}m",
    "pay.sub_invoice_desc": "Suscripción: {title}",
    "pay.pack_invoice_desc": "Paquete de generaciones: {title}",
    "pay.sub_activated": "✅ ¡Suscripción «{title}» activada! Gracias por tu compra 🚀",
    "pay.pack_added": "✅ Paquete recargado: +{qty} {unit} ({pack}). ¡Gracias por tu compra!",
    "pay.avatar_paid": "✅ ¡Pagado! Envía tu mejor selfie — crearé 100 avatares (~15 min).",
    "pay.link": "Abre el enlace para pagar. El acceso se activa automáticamente tras el pago 👇",
    "pay.link_btn": "💳 Pagar — {title}",
    "pay.unavailable": "Este método de pago no está disponible ahora.",
    "pay.failed": "No se pudo crear la factura. Prueba otro método.",
    "gen.video_started": "🎬 ¡Generación de vídeo iniciada! Tardará unos minutos — te enviaré el resultado cuando esté listo.",
    "gen.music_started": "🎶 Generando tu canción — te enviaré el audio cuando esté listo.",
    "gen.photo_started": "🎨 Aplicando «{name}» — te enviaré el vídeo cuando esté listo.",
    "gen.unavailable": "⚠️ Servicio no disponible por ahora. Inténtalo más tarde.",
    "gen.unavailable_refund": "⚠️ Servicio no disponible. Créditos devueltos.",
    "gen.error_refund": "⚠️ Error de generación. Créditos devueltos.",
    "mod.blocked": "🚫 La solicitud infringe las reglas de uso.",
    "seed.ask": "Introduce un seed para la generación (valor numérico):",
    "seed.saved": "✅ Seed guardado.",
    "avatar.info": (
        "👤 Avatares con IA\n\nCrea 100 avatares geniales para redes sociales en distintos estilos.\n"
        "Precio: {price} ⭐ por paquete. Resolución 1024×1440, sin marcas de agua.\n"
        "Tras el pago, sube tu mejor selfie — generación ~15 minutos."
    ),
    "avatar.title": "Paquete de avatares",
    "avatar.buy_btn": "Comprar por {price} ⭐",
    "avatar.started": (
        "🎨 ¡Generación de 100 avatares iniciada! Tardará ~15 minutos — puedes "
        "seguir usando el bot, te enviaré el resultado cuando esté listo."
    ),
    "music.prompt": "🎵 {name}: envía una descripción de la canción (estilo, ánimo, letra).",
    "kling.effects_intro": (
        "🌊 Kling Effects\n\n1. Elige un efecto de las opciones de abajo.\n"
        "2. Envía una foto al bot para aplicar el efecto elegido."
    ),
    "kling.effect_selected": "Efecto: {name}\n\nEnvía una foto y el bot aplicará el efecto elegido.",
    "kling.motion_intro": (
        "💃 Kling Motion\n\nTu foto cobrará vida y repetirá el movimiento de un vídeo de ejemplo.\n"
        "Elige una plantilla 👇"
    ),
    "kling.motion_selected": "Movimiento: 💃 {name}. Envía una foto — Kling Motion le transferirá el movimiento.",
    "btn.voice": "🔊",
    "btn.view": "🔥 Ver",
    "deletecontext.done": "Contexto borrado. Por defecto el bot tiene en cuenta tu pregunta anterior y su respuesta.",
    "music.paywall": "🎵 Para generar canciones, compra un paquete de música. Pulsa «Recargar» 👇",
    "gate.subscription": "Para seguir usando el bot gratis, suscríbete a nuestro canal 👇\nLuego pulsa «Me suscribí».",
    "gate.subscription.ok": "✅ ¡Gracias por suscribirte! Puedes continuar.",
    "gate.subscription.fail": "❌ Parece que aún no te has suscrito.",
    "settings.role.prompt": "Envía el rol (prompt de sistema) que la IA debe seguir.",
    "settings.role.current_none": "Rol actual: no establecido.",
    "settings.role.current": "Rol actual:\n{role}",
    "settings.role.saved": "✅ Rol guardado.",
    "settings.role.cleared": "Rol eliminado.",
    "settings.role.too_long": "❌ Rol demasiado largo (máx. {limit} caracteres). Acórtalo y envíalo de nuevo.",
    "settings.voice.intro": "Elige una voz para las respuestas habladas (disponible en /premium):",
    "settings.voice.preview": "Escuchar la voz seleccionada",
    "settings.intro": (
        "⚙️ Ajustes del bot\n\nAquí puedes adaptar la IA a ti 👇\n\n"
        "1️⃣ Elegir modelo — la red que responde a tus solicitudes.\n\n"
        "2️⃣ Definir rol — p. ej. asistente, redactor, programador, profesor o experto.\n\n"
        "3️⃣ Contexto del diálogo — actívalo o desactívalo. Si está activo, el bot tiene en cuenta su respuesta anterior.\n\n"
        "4️⃣ Respuestas de voz — configura la locución y elige la voz. Disponible en /premium.\n\n"
        "5️⃣ Idioma de la interfaz — elige un idioma cómodo.\n\n"
        "Elige una opción abajo 👇"
    ),
    "model.intro": (
        "🤖 Elegir modelo de IA\n\nModelos líderes para texto, código, análisis y tareas complejas.\n\n"
        "Elige un modelo abajo 👇\n\n"
        "💬 GPT-5.5 — modelo tope de OpenAI. Consume 3 generaciones por solicitud.\n\n"
        "💬 GPT-5.4 — modelo versátil para código y textos.\n\n"
        "💬 GPT-5 mini — modelo rápido para el día a día. Gratis.\n\n"
        "🌥 Claude 4.8 Opus — modelo tope de Anthropic. Consume 5 generaciones por solicitud.\n\n"
        "🌥 Claude 4.6 Sonnet — fuerte en textos, código y matemáticas.\n\n"
        "🐳 DeepSeek V4 — rápido y potente. Gratis.\n\n"
        "🐳 DeepSeek V4 Pro — versión avanzada de DeepSeek.\n\n"
        "♊️ Gemini 3.5 Flash — modelo tope de Google.\n\n"
        "♊️ Gemini 3.1 Flash — modelo rápido e inteligente de Google. Gratis.\n\n"
        "📌 Documentos: en Premium puedes enviar archivos de hasta 10 MB. Consume 3 generaciones.\n\n"
        "🎁 Gratis: GPT-5 mini, Gemini 3.1 Flash, DeepSeek V4\n💎 Otros modelos en Premium: /premium\n\n"
        "Elige un modelo abajo 👇"
    ),
    "help": (
        "📚 Ayuda del bot\n\nComandos y funciones principales.\n\n"
        "📝 Generación de texto\nEscribe tu solicitud en el chat. Los usuarios /premium también pueden enviar mensajes de voz.\n\n"
        "Comandos:\n└ /deletecontext — nuevo diálogo\n└ /s — búsqueda en internet\n"
        "└ /settings — modelo, rol, idioma y contexto\n└ /model — elegir modelo\n\n"
        "💡 Cuanto más detalle, mejor la respuesta.\n\n"
        "📄 Documentos (Premium)\nSube un archivo de hasta 10 MB y pregunta sobre él.\nFormatos: docx, pdf, xlsx, xls, csv, pptx, txt.\nCada solicitud consume 3 generaciones.\n\n"
        "🌅 Imágenes\n└ Nano Banana 2 / Pro\n└ GPT Image 2\n└ Midjourney\n└ Flux\n└ Seedream\n└ Recraft\nComandos: /photo, /midjourney\n\n"
        "🎬 Vídeo\n└ Kling\n└ Seedance 2.0\n└ Pika\n└ Veo 3.1\n└ Hailuo\n└ Grok Imagine\nComando: /video\n\n"
        "🎸 Música\n└ Suno V5.5\n└ Lyria 3 Pro\nComandos: /music, /suno\n\n"
        "⚙️ Otros\n└ /start\n└ /account\n└ /premium\n└ /privacy\n\n"
        "💬 Consultas: {support}"
    ),
    "privacy": (
        "🔐 Documentos legales\n\nAntes de usar el bot, lee las reglas y el tratamiento de datos:\n\n"
        "1️⃣ Términos de uso\n2️⃣ Política de privacidad\n\n"
        "Al seguir usando el bot confirmas que los has leído y los aceptas."
    ),
    "premium": (
        "🚀 Planes y funciones\n\nEl bot reúne servicios de IA populares: texto, búsqueda, imágenes, vídeo, música y archivos.\n\n"
        "🎁 GRATIS | cada semana\n\n100 solicitudes:\n✅ GPT-5 mini\n✅ DeepSeek V4\n✅ Gemini 3.1 Flash\n✅ Perplexity\n✅ Reconocimiento de imágenes\n\n"
        "25 generaciones de imágenes:\n♊️ Nano Banana 2\n✅ GPT Image 2\n\n"
        "💎 PREMIUM | 1 mes\n\nLímite: 100 solicitudes/día\n\n✅ Todo lo del plan gratis\n✅ GPT-5.5\n✅ Gemini 3.5 Flash\n✅ Claude 4.8 Opus y Sonnet\n✅ DeepSeek\n♊️ Nano Banana Pro\n✅ GPT Image 2\n✅ Documentos\n✅ Respuestas de voz\n✅ Sin anuncios\n\nPrecio: {p_premium}⭐️\n\n"
        "💎 PREMIUM X2 | 1 mes\n\nLímite: 200 solicitudes/día\n\n✅ Todo lo de Premium\n✅ Límite diario mayor\n\nPrecio: {p_premium_x2}⭐️\n\n"
        "🌅 IMÁGENES | paquete\n\nDe 50 a 500 generaciones a elegir\n\nServicios disponibles:\n"
        "🌅 Midjourney\n🎬 Midjourney Video\n🌱 Seedream\n🎨 Recraft\n⚡ Flux\n✅ Cambio de cara en fotos\n\nPrecio: desde {p_image_from}⭐️\n\n"
        "🎬 VÍDEO | paquete\n\nDe 2 a 50 generaciones a elegir\n\nServicios disponibles:\n"
        "📼 Kling\n🎥 Veo 3.1\n🚀 Seedance 2.0\n❎ Grok Imagine\n🎞 Hailuo\n✨ Pika\n\n"
        "Además:\n✅ Edición de vídeo\n✅ Efectos de vídeo creativos\n\nPrecio: desde {p_video_from}⭐️\n\n"
        "🎸 MÚSICA | paquete\n\nDe 20 a 100 generaciones a elegir\n\nServicios disponibles:\n"
        "🎸 Suno V5.5\n🎼 Lyria 3 Pro\n\nPosibilidades:\n✅ Canciones con tu propia letra\n✅ Generación de la letra con IA\n\nPrecio: desde {p_music_from}⭐️\n\n"
        "⭐️ Todos los precios en Stars — la moneda de Telegram.\n\n💬 Pagos y acceso:\n{support}"
    ),
    "gate.channel": "Para seguir usando el bot gratis, suscribete a los canales de abajo.\n\nGracias a las suscripciones recibes 100 solicitudes gratis por semana a ChatGPT, DeepSeek, Gemini, Perplexity, generadores de imagenes y mas.\n\nQuieres todo sin anuncios? Pulsa Premium.",
    "gate.btn_subscribe": "Suscribirse a {channel}",
    "gate.btn_check": "Comprobar suscripcion",
    "gate.btn_premium": "Premium",
    "gate.ok": "Gracias por suscribirte! Puedes continuar.",
    "gate.not_subscribed": "Aun no estas suscrito a todos los canales.",
    "gate.premium_voice": "Para enviar solicitudes de voz, obten una suscripcion /premium.",
    "faceswap.step1": "[Paso 1/2] Envia la imagen donde se cambiara la cara.",
    "faceswap.step2": "[Paso 2/2] Ahora envia la foto con la cara donante.",
    "upscale.intro": "Esta herramienta aumenta la resolucion de la imagen. Elige un factor.",
    "upscale.x2": "Aumentar X2",
    "upscale.x4": "Aumentar X4",
    "upscale.send_image": "Envia una imagen (max 1024x1024). Se cobraran {cost} generaciones.",
    "vision.coming_soon": "El reconocimiento de imagenes estara disponible pronto.",
    "vision.failed": "No se pudo procesar la imagen. Intentalo de nuevo.",
    "photo.choose": "Que hago con esta foto?",
    "photo.btn_describe": "🔎 Describir",
    "photo.btn_edit": "🎨 Editar segun el texto",
    "photo.edit_working": "🎨 Editando la foto…",
    "photo.edit_done": "✅ Listo!",
    "photo.edit_unavailable": "🛠 La edicion de fotos estara disponible pronto.",
    "photo.edit_failed": "No se pudo editar la foto. Intentalo de nuevo.",
    "photo.edit_no_caption": "Anade un texto describiendo la edicion y cambiare la imagen.",
    "voice_in.coming_soon": "La entrada de voz estara disponible pronto.",
    "voice_in.heard": "🎙 Reconocido: «{text}»",
    "voice_in.empty": "No se pudo reconocer la voz. Intenta grabar de nuevo.",
    "voice_in.failed": "No se pudo procesar el mensaje de voz. Intentalo de nuevo.",
    "gen.image_started": "Solicitud recibida! Te enviare el resultado cuando este listo.",
    "pay.credits_added": "✨ ¡{qty} créditos añadidos! Úsalos en la Mini App.",
    "img.more": "🔄 Otra",
    "img.upscale": "🔍 Aumentar",
    "img.file": "📎 Calidad completa",
    "img.no_prompt": "Primero elige un servicio y envía un prompt.",
    "promo.usage": "Uso: /promo CÓDIGO",
    "promo.invalid": "❌ Este código promocional no es válido o ha caducado.",
    "promo.already": "Ya has canjeado este código promocional.",
    "promo.ok": "✅ Código promocional canjeado: +{amount} {reward}.",
    "promo.not_eligible": "❌ Este código promocional es solo para nuevos usuarios.",
    # --- bot UI strings (handlers sweep) ---
    "fb.thanks": "¡Gracias por tu valoración!",
    "report.usage": "Uso: <code>/report descripción del problema</code>",
    "report.thanks": "¡Gracias! Tu reporte ha sido recibido.",
    "roles.btn_off": "🚫 Desactivar rol",
    "roles.btn_custom": "✍️ Rol propio",
    "roles.unavailable": "Los roles predefinidos no están disponibles ahora.",
    "roles.choose": "🎭 Elige un rol predefinido para el asistente.",
    "roles.choose_active": "\n\nHay un rol personalizado activo — elige uno nuevo o desactívalo.",
    "roles.not_found": "Rol no encontrado",
    "roles.enabled": "Rol «{title}» activado ✅",
    "roles.enabled_full": "Listo — el asistente ahora actúa como «{title}». Para desactivarlo, envía /roles → «Desactivar rol».",
    "roles.disabled": "Rol desactivado",
    "roles.disabled_full": "Rol del asistente desactivado — modo normal.",
    "contest.none": "No hay concursos activos ahora. ¡Vuelve más tarde!",
    "contest.entrants": "Participantes: {count}",
    "contest.btn_enter": "Participar",
    "contest.ended": "Este concurso ya ha terminado.",
    "contest.entered": "¡Estás participando en el concurso! ¡Buena suerte! 🍀",
    "contest.already": "Ya estás participando en este concurso.",
    "gift.btn_premium": "🎁 Premium · 1 mes",
    "gift.btn_pack": "🎁 Paquete de imágenes · 50",
    "gift.btn_sub": "🎁 Regalar suscripción",
    "gift.btn_pack_menu": "📦 Regalar paquete",
    "gift.pack_none": "Los paquetes no están disponibles ahora.",
    "gift.choose": "🎁 Regala una suscripción o paquete a un amigo.\nElige qué regalar:",
    "gift.invoice_title_sub": "🎁 {product} · {value} mes(es)",
    "gift.invoice_desc": "Regalo: {title}",
    "gift.paid": "🎁 ¡Regalo pagado!\n\nCódigo: <code>{code}</code>\n\nEnvía a tu amigo el comando <code>/redeem {code}</code> o este enlace:\n{link}",
    "redeem.usage": "Uso: <code>/redeem CÓDIGO</code>",
    "inline.hint_title": "Escribe una pregunta…",
    "inline.hint_text": "Escribe una pregunta después del nombre del bot para obtener una respuesta de IA.",
    "inline.error_title": "Error",
    "inline.error_text": "No se pudo obtener una respuesta. Inténtalo más tarde.",
    "inline.throttle_title": "Demasiado seguido",
    "inline.throttle_text": "Demasiadas solicitudes seguidas. Espera un momento e inténtalo de nuevo.",
    "support.usage": "Uso: <code>/support tu pregunta</code>\nDescribe el problema — tu mensaje llegará a soporte.",
    "support.sent": "Mensaje enviado a soporte, responderemos pronto.",
    "pay.precheckout_unavailable": "Pago no disponible",
    "pay.activate_failed": "⚠️ No se pudo activar la compra. Tu pago (⭐) fue reembolsado. Inténtalo de nuevo o contacta con soporte.",
    "invite.summary": "🔗 Tu enlace de referido:\n{link}\n\n👥 Usuarios invitados: {count}\n✨ Recompensa por cada invitado: {reward}\n💰 Total ganado: ✨ {earned}",
    "links.none": "Aún no hay enlaces configurados.",
    "links.title": "Enlaces útiles:",
    "avatar.invoice_desc": "100 avatares IA 1024×1440",
    "promo.reward.credits": "créditos",
    "promo.reward.image": "imágenes",
    "promo.reward.video": "vídeos",
    "promo.reward.music": "pistas de música",
    "promo.reward.premium": "días de Premium",
    "pay.success": "✅ ¡Pago realizado! Tu acceso está activado. Gracias por tu compra 🚀",
    "gen.video_ready": "✅ ¡Tu vídeo está listo!",
    "gen.song_ready": "✅ ¡Tu canción está lista!",
    "gen.photo_ready": "✅ ¡Tu foto está lista!",
    "gen.avatar_unavailable_refund": "⚠️ El servicio «Avatares» no está disponible temporalmente. Tu pago (⭐) fue reembolsado por completo a tu saldo de Telegram. ¡Disculpa!",
    "spec.desc.gpt_image2": "Crea y edita imágenes directamente en el chat.\n\n¿Listo para empezar?\nEnvía de 1 a 4 imágenes que quieras editar, o escribe qué quieres crear.",
    "spec.desc.nano_banana": "Gemini Images — ¡Más vivo. Más inteligente!\n\nCrea y edita imágenes en el chat. Envía de 1 a 10 imágenes o escribe qué quieres crear.",
    "spec.desc.seedream": "Crea y edita imágenes en el chat. Envía de 1 a 10 imágenes o escribe qué quieres crear.",
    "spec.desc.midjourney": "Escribe qué imagen quieres crear.\n\nEl bot admite todos los parámetros y funciones principales de Midjourney.",
    "spec.desc.flux2": "Elige la relación de aspecto y el modelo Flux. Los modelos Flex y Max cuestan 2 generaciones.\n\nPara empezar, escribe qué imagen quieres crear 🐝",
    "spec.desc.recraft": "Recraft — gráficos vectoriales y diseño. Escribe qué imagen quieres crear.",
    "spec.desc.seedance": "Genera vídeo a partir de texto, imágenes, vídeo y audio.\n\nAjusta las opciones y envía un prompt para empezar ⚡",
    "spec.desc.veo": "Veo 3.1 — vídeo cinematográfico de Google. Envía un prompt ⚡",
    "spec.desc.grok": "Crea y edita vídeo. El editor cuesta 2 generaciones.\nProhibido +18, violencia y deepfakes. Envía un prompt ⚡",
    "spec.desc.kling_ai": "Crea y edita vídeo. Envía un prompt ⚡",
    "spec.desc.hailuo": "Hailuo — vídeo a partir de una descripción y una imagen. Envía un prompt ⚡",
    "spec.desc.pika": "Pika Labs — vídeo a partir de una descripción e imágenes. Envía un prompt ⚡",
    "spec.desc.mj_video": "Midjourney Video — animación de imágenes. Envía una foto y/o un prompt ⚡\nSe cobra del paquete de imágenes.",
    "spec.mode.create": "Crear",
    "spec.mode.edit": "Editor",
    "gen.ready_generic": "✅ Tu generación ({service}) está lista.",
    "refund.stars": "⚠️ No se pudo completar el pedido. El pago (⭐) fue devuelto a tu saldo de Telegram. ¡Lo sentimos!",
    "notify.premium_expiry": "⏳ Tu Premium vence en {days} día(s). Renueva tu suscripción para no perder tus límites ampliados.",
    "notify.low_balance": "✨ Tu saldo está casi vacío — quedan {balance} ✨. Recarga para seguir generando sin pausas.",
    "notify.winback": "👋 ¡Hace tiempo que no te vemos! Vuelve — tenemos nuevos modelos y efectos. Envía una solicitud y continuamos 🙌",
    "notify.bonus_available": "🎁 ¡Tu bono diario está listo! Recógelo hoy para mantener tu racha y ganar más ✨.",
    "notify.btn.renew": "⭐ Renovar Premium",
    "notify.btn.topup": "✨ Recargar",
    "notify.btn.open": "🚀 Ver planes",
    "notify.btn.bonus": "🎁 Recoger bono",
    "notify.abandoned_cart": "🛒 ¡Estabas a un paso de tu compra! Termínala — toma un minuto.",
    "notify.btn.cart": "🛒 Completar compra",
    "ref.earned_register": "🎉 ¡Un nuevo usuario se registró con tu enlace de referido! Ganaste ✨ {amount}.",
    "ref.welcome_bonus": "🎁 Bono de bienvenida por unirte con un enlace de referido: +✨ {amount}!",
    "promo.welcome_bonus": "🎁 Bono de bienvenida para nuevo usuario: +✨ {amount}!",
    "promo.purchase_bonus": "🎁 Bono por compra: +✨ {amount}!",
    "promo.applied": "🏷 Promocódigo aplicado: −{percent}% en tu próxima compra!",
    "promo.applied_banner": "🏷 Promo −{percent}% aplicado",
    "ad.remove_btn": "⭐ Quitar anuncios",
    "ref.milestone": "🏆 ¡Has invitado a {count} usuarios! Bono: +✨ {amount}.",
    "ref.earned_purchase": "🎉 ¡Se realizó una compra con tu enlace de referido! Ganaste ✨ {amount}.",
    "contest.won": "🎉 ¡Felicidades! ¡Ganaste el sorteo!",
    "contest.won_credits": "🎉 ¡Felicidades! Ganaste el sorteo — recibiste ✨ {amount}!",
    "contest.won_pack": "🎉 ¡Felicidades! Ganaste el sorteo — recibiste {amount} {unit}!",
    "gift.not_found": "❌ No se encontró ningún regalo con ese código.",
    "gift.already_used": "❌ Este regalo ya fue activado.",
    "gift.own_gift": "🎁 No puedes activar tu propio regalo — compártelo con un amigo.",
    "gift.redeemed_sub": "🎁 Regalo activado: {product} por {months} mes(es).",
    "gift.redeemed_pack": "🎁 Regalo activado: paquete {product} (+{qty}).",
    "gift.redeemed_credits": "🎁 Regalo activado: +{qty} ✨.",
    "gift.unknown_kind": "❌ Tipo de regalo desconocido.",
}
