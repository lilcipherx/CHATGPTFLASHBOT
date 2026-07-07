import WebApp from "@twa-dev/sdk";

const SUPPORTED = ["ru", "en", "es", "fr", "pt", "uz", "ar", "zh"];

type Dict = Record<string, string>;

const M: Record<string, Dict> = {
  ru: {
    brand: "SUPER ИИ БОТ",
    tab_home: "Главная", tab_trends: "Тренды", tab_create: "Создать", tab_profile: "Профиль", tab_history: "История",
    create_style: "Стиль", create_pick_first: "Выберите стиль, чтобы начать", elements: "Элементы",
    templates: "Шаблоны", negative: "Негатив-промпт", negative_ph: "Чего избегать…", models_label: "Модели",
    banner_title: "GPT Image 2 — бесплатно", banner_sub: "Создавайте изображения каждую неделю без оплаты", banner_cta: "Создать",
    video_effects: "🎬 Видеоэффекты", photo_effects: "🎨 Фотоэффекты",
    loading: "Загрузка…", back: "← Назад", create_more: "✨ Создать ещё",
    quality: "Качество", aspect_ratio: "Соотношение сторон", auto: "Авто",
    upload_hint: "📸 Нажмите, чтобы загрузить фото", upload_size: "до 30 МБ",
    generate: "✨ Сгенерировать", uploading: "Загрузка…", generating: "Генерация…", queued: "В очереди…",
    err_limit: "Лимит исчерпан — пополните пакет ✨", failed: "Не удалось сгенерировать",
    err_server: "Ошибка сервера — попробуйте позже", err_auth: "Войдите через Telegram", err_rate: "Слишком много запросов — подождите", err_generic: "Что-то пошло не так",
    pay_cancelled: "Оплата отменена", pay_failed: "Платёж не прошёл", promo_banner: "Промоакция",
    cat_all: "Все", cat_female: "Женские", cat_male: "Мужские", cat_children: "Дети", cat_couple: "Парные",
    empty_cat: "В этой категории пока нет эффектов", section_off: "Этот раздел скоро будет доступен",
    free_plan: "Бесплатный тариф", premium_active: "Premium активен",
    connect_hint: "Подключите Премиум для большего",
    stat_photo: "Фотоэффекты", stat_credits: "Кредиты", balances: "Балансы пакетов",
    bal_image: "🌅 Изображения", bal_video: "🎬 Видео", bal_music: "🎸 Музыка",
    connect_premium: "🚀 Подключить Премиум", paid: "✅ Оплата прошла!", buy_credits: "✨ Купить кредиты",
    bonus_title: "🎁 Ежедневный бонус", bonus_claim: "Забрать {n} ✨", bonus_got: "✅ +{n} ✨ · серия {s}", bonus_already: "Уже забрано сегодня · серия {s}",
    ref_title: "👥 Пригласи друзей", ref_invited: "Приглашено: {n}", ref_earned: "Заработано: {n} ✨", ref_share: "📤 Пригласить друзей", ref_copied: "✅ Ссылка скопирована", language: "🌐 Язык",
    promo_title: "🎟 Промокод", promo_ph: "Введите код", promo_apply: "Применить", promo_ok: "✅ Начислено {n} ✨", promo_already: "Этот код уже использован", promo_invalid: "Неверный или истёкший код",
    pack_image: "🌅 Изображения", pack_video: "🎬 Видео", pack_music: "🎸 Музыка", pack_suffix: "пакет",
    generations: "генерации", history_empty: "Здесь появятся ваши генерации",
    profile_error: "Не удалось загрузить профиль. Откройте приложение из Telegram и попробуйте снова.", retry: "🔄 Повторить",
    app_crashed: "Что-то пошло не так. Перезагрузите приложение.",
    store: "🛒 Магазин и пополнение", store_title: "Магазин", settings: "Настройки",
    recreate: "Повторить", download: "⬇️ Скачать", share: "📤 Поделиться", choose_photo: "Выберите фото",
    seg_video: "Видео", seg_photo: "Фото",
    cat_dance: "Танцы", cat_emotion: "Эмоции", cat_effect: "Эффекты", cat_transform: "Превращение",
    your_photos: "Ваши фото", prompt: "Промпт", prompt_ph: "Опишите, что создать…",
    ai_model: "AI-модель", variant: "Вариант", resolution: "Разрешение", mode: "Режим", duration: "Длительность",
    cost: "Стоимость", balance: "баланс",
    err_too_big: "Файл больше 30 МБ", err_need_photo: "Добавьте хотя бы одно фото", err_need_prompt: "Введите промпт для этого эффекта",
    flag_audio: "Звук", tier_free: "Бесплатно", prev: "Назад", next: "Вперёд", dur_months: "{n} мес", flag_fourk: "4K", flag_seed: "Seed", by_author: "от {name}", flag_prompt_enhance: "Улучшение промпта",
    gate_title: "Откройте в Telegram", gate_sub: "Это приложение доступно только внутри Telegram.",  // FIX: B16
  },
  en: {
    brand: "SUPER AI BOT",
    tab_home: "Home", tab_trends: "Trends", tab_create: "Create", tab_profile: "Profile", tab_history: "History",
    create_style: "Style", create_pick_first: "Pick a style to begin", elements: "Elements",
    templates: "Templates", negative: "Negative prompt", negative_ph: "What to avoid…", models_label: "Models",
    banner_title: "GPT Image 2 — free", banner_sub: "Create images every week at no cost",
    video_effects: "🎬 Video effects", photo_effects: "🎨 Photo effects",
    loading: "Loading…", back: "← Back", create_more: "✨ Create more",
    quality: "Quality", aspect_ratio: "Aspect ratio", auto: "Auto",
    upload_hint: "📸 Tap to upload a photo", upload_size: "up to 30 MB",
    generate: "✨ Generate", uploading: "Uploading…", generating: "Generating…", queued: "Queued…",
    err_limit: "Limit reached — top up the pack ✨", failed: "Generation failed",
    err_server: "Server error — try again later", err_auth: "Sign in via Telegram", err_rate: "Too many requests — wait a moment", err_generic: "Something went wrong",
    pay_cancelled: "Payment cancelled", pay_failed: "Payment failed", promo_banner: "Promotion",
    cat_all: "All", cat_female: "Female", cat_male: "Male", cat_children: "Kids", cat_couple: "Couple",
    empty_cat: "No effects in this category yet", section_off: "This section will be available soon",
    free_plan: "Free plan", premium_active: "Premium active",
    connect_hint: "Get Premium for more",
    stat_photo: "Photo effects", stat_credits: "Credits", balances: "Pack balances",
    bal_image: "🌅 Images", bal_video: "🎬 Video", bal_music: "🎸 Music",
    connect_premium: "🚀 Get Premium", paid: "✅ Payment successful!", buy_credits: "✨ Buy credits",
    bonus_title: "🎁 Daily bonus", bonus_claim: "Claim {n} ✨", bonus_got: "✅ +{n} ✨ · streak {s}", bonus_already: "Already claimed today · streak {s}",
    ref_title: "👥 Invite friends", ref_invited: "Invited: {n}", ref_earned: "Earned: {n} ✨", ref_share: "📤 Invite friends", ref_copied: "✅ Link copied", language: "🌐 Language",
    promo_title: "🎟 Promo code", promo_ph: "Enter code", promo_apply: "Apply", promo_ok: "✅ +{n} ✨ added", promo_already: "Code already used", promo_invalid: "Invalid or expired code",
    pack_image: "🌅 Images", pack_video: "🎬 Video", pack_music: "🎸 Music", pack_suffix: "pack",
    generations: "generations", history_empty: "Your generations will appear here",
    profile_error: "Couldn't load your profile. Open the app from Telegram and try again.", retry: "🔄 Retry",
    app_crashed: "Something went wrong. Please reload the app.",
    store: "🛒 Store & top-up", store_title: "Store", settings: "Settings",
    recreate: "Redo", download: "⬇️ Download", share: "📤 Share", choose_photo: "Choose a photo",
    seg_video: "Video", seg_photo: "Photo",
    cat_dance: "Dance", cat_emotion: "Emotion", cat_effect: "Effects", cat_transform: "Transform",
    your_photos: "Your photos", prompt: "Prompt", prompt_ph: "Describe what to create…",
    ai_model: "AI model", variant: "Variant", resolution: "Resolution", mode: "Mode", duration: "Duration",
    cost: "Cost", balance: "balance",
    err_too_big: "File exceeds 30 MB", err_need_photo: "Add at least one photo", err_need_prompt: "Enter a prompt for this effect",
    flag_audio: "Sound", tier_free: "Free", prev: "Previous", next: "Next", dur_months: "{n} mo", banner_cta: "Create", flag_fourk: "4K", flag_seed: "Seed", by_author: "by {name}", flag_prompt_enhance: "Prompt boost",
    "gate_title": "Open in Telegram", "gate_sub": "This app is only available inside Telegram.",  // FIX: M15
  },
  es: {
    brand: "SUPER AI BOT",
    tab_home: "Inicio", tab_trends: "Tendencias", tab_create: "Crear", tab_profile: "Perfil", tab_history: "Historial",
    create_style: "Estilo", create_pick_first: "Elige un estilo para empezar", elements: "Elementos",
    templates: "Plantillas", negative: "Prompt negativo", negative_ph: "Qué evitar…", models_label: "Modelos",
    banner_title: "GPT Image 2 — gratis", banner_sub: "Crea imágenes cada semana sin costo",
    video_effects: "🎬 Efectos de vídeo", photo_effects: "🎨 Efectos de foto",
    loading: "Cargando…", back: "← Atrás", create_more: "✨ Crear otra",
    quality: "Calidad", aspect_ratio: "Relación de aspecto", auto: "Auto",
    upload_hint: "📸 Toca para subir una foto", upload_size: "hasta 30 MB",
    generate: "✨ Generar", uploading: "Subiendo…", generating: "Generando…", queued: "En cola…",
    err_limit: "Límite alcanzado — recarga el paquete ✨", failed: "Error al generar",
    err_server: "Error del servidor — inténtalo más tarde", err_auth: "Inicia sesión con Telegram", err_rate: "Demasiadas solicitudes — espera", err_generic: "Algo salió mal",
    pay_cancelled: "Pago cancelado", pay_failed: "Pago fallido", promo_banner: "Promoción",
    cat_all: "Todos", cat_female: "Mujer", cat_male: "Hombre", cat_children: "Niños", cat_couple: "Pareja",
    empty_cat: "Aún no hay efectos en esta categoría", section_off: "Esta sección estará disponible pronto",
    free_plan: "Plan gratuito", premium_active: "Premium activo",
    connect_hint: "Activa Premium para más",
    stat_photo: "Efectos de foto", stat_credits: "Créditos", balances: "Saldos de paquetes",
    bal_image: "🌅 Imágenes", bal_video: "🎬 Vídeo", bal_music: "🎸 Música",
    connect_premium: "🚀 Obtener Premium", paid: "✅ ¡Pago realizado!", buy_credits: "✨ Comprar créditos",
    bonus_title: "🎁 Bono diario", bonus_claim: "Reclamar {n} ✨", bonus_got: "✅ +{n} ✨ · racha {s}", bonus_already: "Ya reclamado hoy · racha {s}",
    ref_title: "👥 Invita amigos", ref_invited: "Invitados: {n}", ref_earned: "Ganado: {n} ✨", ref_share: "📤 Invitar amigos", ref_copied: "✅ Enlace copiado", language: "🌐 Idioma",
    promo_title: "🎟 Código promo", promo_ph: "Ingresa el código", promo_apply: "Aplicar", promo_ok: "✅ +{n} ✨ añadidos", promo_already: "Código ya usado", promo_invalid: "Código inválido o expirado",
    pack_image: "🌅 Imágenes", pack_video: "🎬 Vídeo", pack_music: "🎸 Música", pack_suffix: "paquete",
    generations: "generaciones", history_empty: "Aquí aparecerán tus generaciones",
    profile_error: "No se pudo cargar tu perfil. Abre la app desde Telegram e inténtalo de nuevo.", retry: "🔄 Reintentar",
    recreate: "Repetir", download: "⬇️ Descargar", share: "📤 Compartir", choose_photo: "Elige una foto",
    seg_video: "Vídeo", seg_photo: "Foto",
    cat_dance: "Baile", cat_emotion: "Emoción", cat_effect: "Efectos", cat_transform: "Transformar",
    your_photos: "Tus fotos", prompt: "Prompt", prompt_ph: "Describe qué crear…",
    ai_model: "Modelo IA", variant: "Variante", resolution: "Resolución", mode: "Modo", duration: "Duración",
    cost: "Costo", balance: "saldo",
    err_too_big: "El archivo supera 30 MB", err_need_photo: "Añade al menos una foto", err_need_prompt: "Escribe un prompt para este efecto",
    banner_cta: "Crear", app_crashed: "Algo salió mal. Reinicia la app.", store: "🛒 Tienda y recarga", store_title: "Tienda", settings: "Ajustes", flag_audio: "Audio", tier_free: "Gratis", prev: "Anterior", next: "Siguiente", dur_months: "{n} meses", by_author: "de {name}", flag_fourk: "4K", flag_seed: "Seed", flag_prompt_enhance: "Mejorar prompt",  // FIX: #9 - 14 missing keys for es
    "gate_title": "Abrir en Telegram", "gate_sub": "Esta aplicación solo está disponible dentro de Telegram.",  // FIX: B12
  },
  fr: {
    brand: "SUPER AI BOT",
    tab_home: "Accueil", tab_trends: "Tendances", tab_create: "Créer", tab_profile: "Profil", tab_history: "Historique",
    create_style: "Style", create_pick_first: "Choisissez un style pour commencer", elements: "Éléments",
    templates: "Modèles", negative: "Prompt négatif", negative_ph: "À éviter…", models_label: "Modèles",
    banner_title: "GPT Image 2 — gratuit", banner_sub: "Créez des images chaque semaine gratuitement",
    video_effects: "🎬 Effets vidéo", photo_effects: "🎨 Effets photo",
    loading: "Chargement…", back: "← Retour", create_more: "✨ Créer encore",
    quality: "Qualité", aspect_ratio: "Format", auto: "Auto",
    upload_hint: "📸 Touchez pour envoyer une photo", upload_size: "jusqu'à 10 Mo",
    generate: "✨ Générer", uploading: "Envoi…", generating: "Génération…", queued: "En file…",
    err_limit: "Limite atteinte — rechargez le pack ✨", failed: "Échec de génération",
    err_server: "Erreur serveur — réessayez plus tard", err_auth: "Connectez-vous via Telegram", err_rate: "Trop de requêtes — patientez", err_generic: "Une erreur est survenue",
    pay_cancelled: "Paiement annulé", pay_failed: "Paiement échoué", promo_banner: "Promotion",
    cat_all: "Tous", cat_female: "Femme", cat_male: "Homme", cat_children: "Enfants", cat_couple: "Couple",
    empty_cat: "Aucun effet dans cette catégorie", section_off: "Cette section sera bientôt disponible",
    free_plan: "Offre gratuite", premium_active: "Premium actif",
    connect_hint: "Passez à Premium pour plus",
    stat_photo: "Effets photo", stat_credits: "Crédits", balances: "Soldes des packs",
    bal_image: "🌅 Images", bal_video: "🎬 Vidéo", bal_music: "🎸 Musique",
    connect_premium: "🚀 Obtenir Premium", paid: "✅ Paiement réussi !", buy_credits: "✨ Acheter des crédits",
    bonus_title: "🎁 Bonus quotidien", bonus_claim: "Récupérer {n} ✨", bonus_got: "✅ +{n} ✨ · série {s}", bonus_already: "Déjà récupéré aujourd'hui · série {s}",
    ref_title: "👥 Invite des amis", ref_invited: "Invités : {n}", ref_earned: "Gagné : {n} ✨", ref_share: "📤 Inviter des amis", ref_copied: "✅ Lien copié", language: "🌐 Langue",
    promo_title: "🎟 Code promo", promo_ph: "Entrez le code", promo_apply: "Appliquer", promo_ok: "✅ +{n} ✨ ajoutés", promo_already: "Code déjà utilisé", promo_invalid: "Code invalide ou expiré",
    pack_image: "🌅 Images", pack_video: "🎬 Vidéo", pack_music: "🎸 Musique", pack_suffix: "pack",
    generations: "générations", history_empty: "Vos générations apparaîtront ici",
    profile_error: "Impossible de charger votre profil. Ouvrez l'app depuis Telegram et réessayez.", retry: "🔄 Réessayer",
    recreate: "Refaire", download: "⬇️ Télécharger", share: "📤 Partager", choose_photo: "Choisir une photo",
    seg_video: "Vidéo", seg_photo: "Photo",
    cat_dance: "Danse", cat_emotion: "Émotion", cat_effect: "Effets", cat_transform: "Transformer",
    your_photos: "Vos photos", prompt: "Prompt", prompt_ph: "Décrivez quoi créer…",
    ai_model: "Modèle IA", variant: "Variante", resolution: "Résolution", mode: "Mode", duration: "Durée",
    cost: "Coût", balance: "solde",
    err_too_big: "Fichier supérieur à 30 Mo", err_need_photo: "Ajoutez au moins une photo", err_need_prompt: "Saisissez un prompt pour cet effet",
    banner_cta: "Créer", app_crashed: "Une erreur est survenue. Redémarrez l'app.", store: "🛒 Boutique et recharge", store_title: "Boutique", settings: "Paramètres", flag_audio: "Audio", tier_free: "Gratuit", prev: "Précédent", next: "Suivant", dur_months: "{n} mois", by_author: "par {name}", flag_fourk: "4K", flag_seed: "Seed", flag_prompt_enhance: "Améliorer le prompt",  // FIX: #9 - 14 missing keys for fr
    "gate_title": "Ouvrir dans Telegram", "gate_sub": "Cette application est uniquement disponible dans Telegram.",  // FIX: B12
  },
  pt: {
    brand: "SUPER AI BOT",
    tab_home: "Início", tab_trends: "Tendências", tab_create: "Criar", tab_profile: "Perfil", tab_history: "Histórico",
    create_style: "Estilo", create_pick_first: "Escolha um estilo para começar", elements: "Elementos",
    templates: "Modelos", negative: "Prompt negativo", negative_ph: "O que evitar…", models_label: "Modelos",
    banner_title: "GPT Image 2 — grátis", banner_sub: "Crie imagens toda semana sem custo",
    video_effects: "🎬 Efeitos de vídeo", photo_effects: "🎨 Efeitos de foto",
    loading: "Carregando…", back: "← Voltar", create_more: "✨ Criar outra",
    quality: "Qualidade", aspect_ratio: "Proporção", auto: "Auto",
    upload_hint: "📸 Toque para enviar uma foto", upload_size: "até 10 MB",
    generate: "✨ Gerar", uploading: "Enviando…", generating: "Gerando…", queued: "Na fila…",
    err_limit: "Limite atingido — recarregue o pacote ✨", failed: "Falha na geração",
    err_server: "Erro do servidor — tente novamente", err_auth: "Entre via Telegram", err_rate: "Muitas solicitações — aguarde", err_generic: "Algo deu errado",
    pay_cancelled: "Pagamento cancelado", pay_failed: "Pagamento falhou", promo_banner: "Promoção",
    cat_all: "Todos", cat_female: "Feminino", cat_male: "Masculino", cat_children: "Crianças", cat_couple: "Casal",
    empty_cat: "Ainda não há efeitos nesta categoria", section_off: "Esta seção estará disponível em breve",
    free_plan: "Plano grátis", premium_active: "Premium ativo",
    connect_hint: "Ative o Premium para mais",
    stat_photo: "Efeitos de foto", stat_credits: "Créditos", balances: "Saldos dos pacotes",
    bal_image: "🌅 Imagens", bal_video: "🎬 Vídeo", bal_music: "🎸 Música",
    connect_premium: "🚀 Obter Premium", paid: "✅ Pagamento aprovado!", buy_credits: "✨ Comprar créditos",
    bonus_title: "🎁 Bônus diário", bonus_claim: "Resgatar {n} ✨", bonus_got: "✅ +{n} ✨ · sequência {s}", bonus_already: "Já resgatado hoje · sequência {s}",
    ref_title: "👥 Convide amigos", ref_invited: "Convidados: {n}", ref_earned: "Ganho: {n} ✨", ref_share: "📤 Convidar amigos", ref_copied: "✅ Link copiado", language: "🌐 Idioma",
    promo_title: "🎟 Código promo", promo_ph: "Digite o código", promo_apply: "Aplicar", promo_ok: "✅ +{n} ✨ adicionados", promo_already: "Código já usado", promo_invalid: "Código inválido ou expirado",
    pack_image: "🌅 Imagens", pack_video: "🎬 Vídeo", pack_music: "🎸 Música", pack_suffix: "pacote",
    generations: "gerações", history_empty: "Suas gerações aparecerão aqui",
    profile_error: "Não foi possível carregar seu perfil. Abra o app pelo Telegram e tente de novo.", retry: "🔄 Tentar de novo",
    recreate: "Repetir", download: "⬇️ Baixar", share: "📤 Compartilhar", choose_photo: "Escolha uma foto",
    seg_video: "Vídeo", seg_photo: "Foto",
    cat_dance: "Dança", cat_emotion: "Emoção", cat_effect: "Efeitos", cat_transform: "Transformar",
    your_photos: "Suas fotos", prompt: "Prompt", prompt_ph: "Descreva o que criar…",
    ai_model: "Modelo IA", variant: "Variante", resolution: "Resolução", mode: "Modo", duration: "Duração",
    cost: "Custo", balance: "saldo",
    err_too_big: "Arquivo acima de 30 MB", err_need_photo: "Adicione ao menos uma foto", err_need_prompt: "Digite um prompt para este efeito",
    banner_cta: "Criar", app_crashed: "Algo deu errado. Reinicie o app.", store: "🛒 Loja e recarga", store_title: "Loja", settings: "Configurações", flag_audio: "Áudio", tier_free: "Grátis", prev: "Anterior", next: "Próximo", dur_months: "{n} meses", by_author: "por {name}", flag_fourk: "4K", flag_seed: "Seed", flag_prompt_enhance: "Aprimorar prompt",  // FIX: #9 - 14 missing keys for pt
    "gate_title": "Abrir no Telegram", "gate_sub": "Este aplicativo está disponível apenas dentro do Telegram.",  // FIX: B12
  },
  uz: {
    brand: "SUPER AI BOT",
    tab_home: "Bosh", tab_trends: "Trend", tab_create: "Yaratish", tab_profile: "Profil", tab_history: "Tarix",
    create_style: "Uslub", create_pick_first: "Boshlash uchun uslub tanlang", elements: "Elementlar",
    templates: "Shablonlar", negative: "Salbiy prompt", negative_ph: "Nimadan qochish…", models_label: "Modellar",
    banner_title: "GPT Image 2 — bepul", banner_sub: "Har hafta bepul rasm yarating",
    video_effects: "🎬 Video effektlar", photo_effects: "🎨 Foto effektlar",
    loading: "Yuklanmoqda…", back: "← Orqaga", create_more: "✨ Yana yaratish",
    quality: "Sifat", aspect_ratio: "Nisbat", auto: "Avto",
    upload_hint: "📸 Rasm yuklash uchun bosing", upload_size: "10 MB gacha",
    generate: "✨ Yaratish", uploading: "Yuklanmoqda…", generating: "Yaratilmoqda…", queued: "Navbatda…",
    err_limit: "Limit tugadi — paketni toʻldiring ✨", failed: "Yaratib boʻlmadi",
    err_server: "Server xatosi — keyinroq urinib koʻring", err_auth: "Telegram orqali kiring", err_rate: "Soʻrovlar koʻp — kuting", err_generic: "Nimadir notoʻgʻri ketdi",
    pay_cancelled: "Toʻlov bekor qilindi", pay_failed: "Toʻlov amalga oshmadi", promo_banner: "Aksiya",
    cat_all: "Hammasi", cat_female: "Ayollar", cat_male: "Erkaklar", cat_children: "Bolalar", cat_couple: "Juftlik",
    empty_cat: "Bu turkumda hali effekt yoʻq", section_off: "Bu boʻlim tez orada ishga tushadi",
    free_plan: "Bepul tarif", premium_active: "Premium faol",
    connect_hint: "Koʻproq uchun Premium ulang",
    stat_photo: "Foto effektlar", stat_credits: "Kreditlar", balances: "Paket balanslari",
    bal_image: "🌅 Rasmlar", bal_video: "🎬 Video", bal_music: "🎸 Musiqa",
    connect_premium: "🚀 Premium ulash", paid: "✅ Toʻlov amalga oshdi!", buy_credits: "✨ Kredit sotib olish",
    bonus_title: "🎁 Kunlik bonus", bonus_claim: "{n} ✨ olish", bonus_got: "✅ +{n} ✨ · seriya {s}", bonus_already: "Bugun allaqachon olingan · seriya {s}",
    ref_title: "👥 Doʻstlarni taklif qiling", ref_invited: "Taklif qilindi: {n}", ref_earned: "Ishlandi: {n} ✨", ref_share: "📤 Doʻstlarni taklif qilish", ref_copied: "✅ Havola nusxalandi", language: "🌐 Til",
    promo_title: "🎟 Promokod", promo_ph: "Kodni kiriting", promo_apply: "Qoʻllash", promo_ok: "✅ +{n} ✨ qoʻshildi", promo_already: "Kod allaqachon ishlatilgan", promo_invalid: "Notoʻgʻri yoki muddati oʻtgan kod",
    pack_image: "🌅 Rasmlar", pack_video: "🎬 Video", pack_music: "🎸 Musiqa", pack_suffix: "paket",
    generations: "generatsiya", history_empty: "Generatsiyalaringiz shu yerda paydo boʻladi",
    profile_error: "Profil yuklanmadi. Ilovani Telegram orqali oching va qayta urinib koʻring.", retry: "🔄 Qayta urinish",
    recreate: "Takrorlash", download: "⬇️ Yuklab olish", share: "📤 Ulashish", choose_photo: "Rasm tanlang",
    seg_video: "Video", seg_photo: "Foto",
    cat_dance: "Raqs", cat_emotion: "Hissiyot", cat_effect: "Effektlar", cat_transform: "Aylantirish",
    your_photos: "Sizning rasmlar", prompt: "Prompt", prompt_ph: "Nima yaratishni yozing…",
    ai_model: "AI-model", variant: "Variant", resolution: "Aniqlik", mode: "Rejim", duration: "Davomiylik",
    cost: "Narx", balance: "balans",
    err_too_big: "Fayl 30 MB dan katta", err_need_photo: "Kamida bitta rasm qo'shing", err_need_prompt: "Bu effekt uchun prompt kiriting",
    banner_cta: "Yaratish", app_crashed: "Xatolik yuz berdi. Ilovani qayta ishga tushiring.", store: "🛒 Do'kon va to'ldirish", store_title: "Do'kon", settings: "Sozlamalar", flag_audio: "Audio", tier_free: "Bepul", prev: "Oldingi", next: "Keyingi", dur_months: "{n} oy", by_author: "{name} tomonidan", flag_fourk: "4K", flag_seed: "Seed", flag_prompt_enhance: "Promptni yaxshilash",  // FIX: #9 - 14 missing keys for uz
    "gate_title": "Telegramda oching", "gate_sub": "Bu ilova faqat Telegram ichida mavjud.",  // FIX: B12
  },
  ar: {
    brand: "SUPER AI BOT",
    tab_home: "الرئيسية", tab_trends: "الرائج", tab_create: "إنشاء", tab_profile: "الملف", tab_history: "السجل",
    create_style: "النمط", create_pick_first: "اختر نمطًا للبدء", elements: "عناصر",
    templates: "قوالب", negative: "موجه سلبي", negative_ph: "ما يجب تجنبه…", models_label: "نماذج",
    banner_title: "GPT Image 2 — مجانًا", banner_sub: "أنشئ صورًا كل أسبوع مجانًا",
    video_effects: "🎬 مؤثرات الفيديو", photo_effects: "🎨 مؤثرات الصور",
    loading: "جارٍ التحميل…", back: "← رجوع", create_more: "✨ إنشاء آخر",
    quality: "الجودة", aspect_ratio: "نسبة الأبعاد", auto: "تلقائي",
    upload_hint: "📸 اضغط لرفع صورة", upload_size: "حتى 30 ميغابايت",
    generate: "✨ إنشاء", uploading: "جارٍ الرفع…", generating: "جارٍ الإنشاء…", queued: "في الانتظار…",
    err_limit: "انتهى الحد — اشحن الباقة ✨", failed: "فشل الإنشاء",
    err_server: "خطأ في الخادم — حاول لاحقًا", err_auth: "سجّل عبر Telegram", err_rate: "طلبات كثيرة — انتظر", err_generic: "حدث خطأ ما",
    pay_cancelled: "تم إلغاء الدفع", pay_failed: "فشل الدفع", promo_banner: "عرض ترويجي",
    cat_all: "الكل", cat_female: "نساء", cat_male: "رجال", cat_children: "أطفال", cat_couple: "ثنائي",
    empty_cat: "لا توجد مؤثرات في هذه الفئة بعد", section_off: "سيتوفر هذا القسم قريبًا",
    free_plan: "الخطة المجانية", premium_active: "Premium نشط",
    connect_hint: "فعّل Premium للمزيد",
    stat_photo: "مؤثرات الصور", stat_credits: "أرصدة", balances: "أرصدة الباقات",
    bal_image: "🌅 الصور", bal_video: "🎬 الفيديو", bal_music: "🎸 الموسيقى",
    connect_premium: "🚀 تفعيل Premium", paid: "✅ تم الدفع!", buy_credits: "✨ شراء الأرصدة",
    bonus_title: "🎁 المكافأة اليومية", bonus_claim: "احصل على {n} ✨", bonus_got: "✅ +{n} ✨ · سلسلة {s}", bonus_already: "تم الاستلام اليوم · سلسلة {s}",
    ref_title: "👥 ادعُ أصدقاءك", ref_invited: "المدعوون: {n}", ref_earned: "المكتسب: {n} ✨", ref_share: "📤 دعوة الأصدقاء", ref_copied: "✅ تم نسخ الرابط", language: "🌐 اللغة",
    promo_title: "🎟 رمز ترويجي", promo_ph: "أدخل الرمز", promo_apply: "تطبيق", promo_ok: "✅ +{n} ✨ أُضيفت", promo_already: "الرمز مستخدم بالفعل", promo_invalid: "رمز غير صالح أو منتهٍ",
    pack_image: "🌅 الصور", pack_video: "🎬 الفيديو", pack_music: "🎸 الموسيقى", pack_suffix: "باقة",
    generations: "توليدات", history_empty: "ستظهر عمليات الإنشاء هنا",
    profile_error: "تعذّر تحميل ملفك الشخصي. افتح التطبيق من تيليجرام وحاول مجددًا.", retry: "🔄 إعادة المحاولة",
    recreate: "إعادة", download: "⬇️ تنزيل", share: "📤 مشاركة", choose_photo: "اختر صورة",
    seg_video: "فيديو", seg_photo: "صورة",
    cat_dance: "رقص", cat_emotion: "مشاعر", cat_effect: "مؤثرات", cat_transform: "تحويل",
    your_photos: "صورك", prompt: "الوصف", prompt_ph: "صف ما تريد إنشاءه…",
    ai_model: "نموذج الذكاء", variant: "نوع", resolution: "الدقة", mode: "الوضع", duration: "المدة",
    cost: "التكلفة", balance: "الرصيد",
    err_too_big: "الملف أكبر من 30 ميغابايت", err_need_photo: "أضف صورة واحدة على الأقل", err_need_prompt: "أدخل وصفًا لهذا المؤثر",
    banner_cta: "إنشاء", app_crashed: "حدث خطأ. أعد تشغيل التطبيق.", store: "🛒 المتجر وشحن", store_title: "المتجر", settings: "الإعدادات", flag_audio: "صوت", tier_free: "مجاني", prev: "السابق", next: "التالي", dur_months: "{n} شهر", by_author: "بواسطة {name}", flag_fourk: "4K", flag_seed: "Seed", flag_prompt_enhance: "تحسين الوصف",  // FIX: #9 - 14 missing keys for ar
    "gate_title": "افتح في تيليجرام", "gate_sub": "هذا التطبيق متاح فقط داخل تيليجرام.",  // FIX: B12
  },
  zh: {
    brand: "SUPER AI BOT",
    tab_home: "主页", tab_trends: "趋势", tab_create: "创建", tab_profile: "个人", tab_history: "历史",
    create_style: "风格", create_pick_first: "选择风格开始", elements: "元素",
    templates: "模板", negative: "负面提示", negative_ph: "要避免的内容…", models_label: "模型",
    banner_title: "GPT Image 2 — 免费", banner_sub: "每周免费创建图片",
    video_effects: "🎬 视频特效", photo_effects: "🎨 照片特效",
    loading: "加载中…", back: "← 返回", create_more: "✨ 再创建",
    quality: "质量", aspect_ratio: "宽高比", auto: "自动",
    upload_hint: "📸 点击上传照片", upload_size: "最大 30 MB",
    generate: "✨ 生成", uploading: "上传中…", generating: "生成中…", queued: "排队中…",
    err_limit: "额度用完 — 请充值 ✨", failed: "生成失败",
    err_server: "服务器错误 — 请稍后重试", err_auth: "请通过 Telegram 登录", err_rate: "请求过多 — 请稍候", err_generic: "出了点问题",
    pay_cancelled: "支付已取消", pay_failed: "支付失败", promo_banner: "促销活动",
    cat_all: "全部", cat_female: "女性", cat_male: "男性", cat_children: "儿童", cat_couple: "情侣",
    empty_cat: "该分类暂无特效", section_off: "该板块即将上线",
    free_plan: "免费套餐", premium_active: "会员已激活",
    connect_hint: "开通会员获得更多",
    stat_photo: "照片特效", stat_credits: "积分", balances: "套餐余额",
    bal_image: "🌅 图片", bal_video: "🎬 视频", bal_music: "🎸 音乐",
    connect_premium: "🚀 开通会员", paid: "✅ 支付成功！", buy_credits: "✨ 购买积分",
    bonus_title: "🎁 每日奖励", bonus_claim: "领取 {n} ✨", bonus_got: "✅ +{n} ✨ · 连续 {s}", bonus_already: "今日已领取 · 连续 {s}",
    ref_title: "👥 邀请好友", ref_invited: "已邀请：{n}", ref_earned: "已赚取：{n} ✨", ref_share: "📤 邀请好友", ref_copied: "✅ 链接已复制", language: "🌐 语言",
    promo_title: "🎟 优惠码", promo_ph: "输入优惠码", promo_apply: "应用", promo_ok: "✅ +{n} ✨ 已到账", promo_already: "优惠码已使用", promo_invalid: "无效或过期的优惠码",
    pack_image: "🌅 图片", pack_video: "🎬 视频", pack_music: "🎸 音乐", pack_suffix: "套餐",
    generations: "次生成", history_empty: "你的生成记录将显示在这里",
    profile_error: "无法加载你的资料。请从 Telegram 打开应用后重试。", retry: "🔄 重试",
    recreate: "重做", download: "⬇️ 下载", share: "📤 分享", choose_photo: "选择照片",
    seg_video: "视频", seg_photo: "照片",
    cat_dance: "舞蹈", cat_emotion: "情绪", cat_effect: "特效", cat_transform: "变换",
    your_photos: "你的照片", prompt: "提示词", prompt_ph: "描述要创建的内容…",
    ai_model: "AI 模型", variant: "变体", resolution: "分辨率", mode: "模式", duration: "时长",
    cost: "费用", balance: "余额",
    err_too_big: "文件超过 30 MB", err_need_photo: "请至少添加一张照片", err_need_prompt: "请为该特效输入提示词",
    banner_cta: "创建", app_crashed: "出了点问题。请重启应用。", store: "🛒 商店和充值", store_title: "商店", settings: "设置", flag_audio: "音频", tier_free: "免费", prev: "上一个", next: "下一个", dur_months: "{n} 个月", by_author: "作者：{name}", flag_fourk: "4K", flag_seed: "Seed", flag_prompt_enhance: "增强提示词",  // FIX: #9 - 14 missing keys for zh
    "gate_title": "在 Telegram 中打开", "gate_sub": "此应用仅在 Telegram 内可用。",  // FIX: B12
  },
};

// Exposed for the key-parity test: every locale must define the same keys as ru,
// else a missing key silently falls back to Russian for that user.
export const MESSAGES = M;

// Native language label for the picker (own-language names so anyone recognises it).
export const LANG_LABELS: Record<string, string> = {
  ru: "🇷🇺 Русский", en: "🇬🇧 English", es: "🇪🇸 Español", fr: "🇫🇷 Français",
  pt: "🇧🇷 Português", uz: "🇺🇿 Oʻzbekcha", ar: "🇸🇦 العربية", zh: "🇨🇳 简体中文",
};
export const LANGS = SUPPORTED;

function pickLang(): string {
  // FIX: AUDIT12-F8 - no more localStorage override. The bot is the single source
  // of truth for the user's language; the Mini App reads it from /api/profile and
  // calls syncLang(). On first paint we fall back to Telegram's initDataUnsafe.
  let code = "ru";
  try {
    code = WebApp.initDataUnsafe?.user?.language_code ?? "ru";
  } catch {
    /* ignore */
  }
  code = code.slice(0, 2).toLowerCase();
  return SUPPORTED.includes(code) ? code : "ru";
}

// Current active language (mutable). Components read this via `getLang()` so they
// always see the latest value after a `syncLang()` call.
let _lang: string = pickLang();
export const LANG: string = _lang;  // back-compat: static initial value
export function getLang(): string { return _lang; }

// Pub/sub so React components can re-render when the language changes.
type Listener = (lang: string) => void;
const _listeners = new Set<Listener>();
export function onLangChange(fn: Listener): () => void {
  _listeners.add(fn);
  return () => { _listeners.delete(fn); };
}

/**
 * Switch the Mini App's active language WITHOUT a page reload. Called from
 * Profile.tsx after /api/profile returns the user's bot-side language_code.
 * Updates document.lang + dir for accessibility, fires haptic, and notifies
 * subscribers so React re-renders with the new translations.
 */
export function syncLang(code: string): void {
  const c = (code || "").slice(0, 2).toLowerCase();
  if (!SUPPORTED.includes(c) || c === _lang) return;
  _lang = c;
  // FIX: AUDIT-FINAL-8 - removed dead localStorage.setItem. pickLang() never
  // reads from localStorage (the bot is the single source of truth via
  // /api/profile.language_code), so writing here was a dead store that
  // contradicted the AUDIT12-F8 comment above.
  try { WebApp.HapticFeedback?.impactOccurred?.("light"); } catch { /* ignore */ }
  document.documentElement.lang = c;
  document.documentElement.dir = c === "ar" ? "rtl" : "ltr";
  for (const fn of _listeners) { try { fn(c); } catch { /* ignore */ } }
}

/**
 * Back-compat shim: old callers used setLang(code) to switch + reload. We keep
 * the export name but route it to syncLang (no reload — the whole point of
 * AUDIT12-F8 is to stop reloading the Mini App on language change).
 */
export const setLang = syncLang;

export function t(key: string, params?: Record<string, string | number>): string {
  let s = M[_lang]?.[key] ?? M.ru[key] ?? key;
  if (params) {
    // FIX: AUDIT13-M21 - in RTL (Arabic) wrap interpolated LTR values (numbers,
    // @handles, model names) in a First-Strong Isolate (U+2068 … U+2069) so their
    // internal order and neighbouring punctuation render correctly. No-op visual effect
    // in LTR, so it is safe to always apply when the active locale is RTL.
    const rtl = _lang === "ar";
    for (const [k, v] of Object.entries(params)) {
      let val = String(v).replaceAll("$", "$$$$");  // FIX: AUDIT-3 - escape $ for replaceAll
      if (rtl) val = `⁨${val}⁩`;
      s = s.replaceAll(`{${k}}`, val);
    }
  }
  return s;
}

export function applyRtl(): void {
  // FIX: AUDIT-3 - always set document lang for screen readers
  document.documentElement.lang = _lang;
  if (_lang === "ar") document.documentElement.dir = "rtl";
}
