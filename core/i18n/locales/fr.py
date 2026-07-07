"""French locale — user-facing screens; long legal/help fall back to RU."""

MESSAGES: dict[str, str] = {
    "start.welcome": (
        "Salut ! 👋\n\n"
        "Je suis SUPER AI BOT, ton assistant IA qui t'aide à créer du texte, des images, des "
        "vidéos, de la musique et bien plus avec des réseaux neuronaux modernes.\n\n"
        "🎁 GRATUIT :\n100 requêtes par semaine pour le texte, les images et d'autres outils IA.\n\n"
        "⭐️ PREMIUM :\nAccès étendu aux réseaux neuronaux les plus puissants.\n\n"
        "Comment utiliser le bot ?\n\n"
        "📝 TEXTE\nÉcris ta question ou ta tâche dans le chat — je t'aide tout de suite.\n\n"
        "🔎 RECHERCHE\nUtilise /s pour poser une question avec recherche internet.\n\n"
        "🌅 IMAGES\nAppuie sur /photo pour créer ou modifier une image.\n\n"
        "🎬 VIDÉO\nAppuie sur /video pour créer une vidéo.\n\n"
        "🎸 MUSIQUE\nAppuie sur /music pour créer une chanson.\n\n"
        "⚙️ MODÈLE\n/model permet de choisir le réseau neuronal.\n\n"
        "💎 PREMIUM\n/premium débloque les fonctions avancées.\n\n"
        "Commence maintenant — envoie-moi un message 🚀"
    ),
    "account": (
        "👤 Votre compte\n\nAbonnement : {sub}\nModèle sélectionné : {model_name} /model\n\n"
        "📊 Statistiques d'utilisation\n\nRequêtes cette semaine : {used}/{limit}\n"
        "✨ Requêtes bonus : {credits} (parrainages et bonus quotidien ; utilisées une fois la limite hebdo atteinte)\n\n"
        "Inclus dans le plan gratuit :\n└ GPT-5 mini\n└ DeepSeek V4\n└ Gemini 3.1 Flash\n"
        "└ Perplexity\n└ GPT Image 2\n└ Nano Banana 2\n\n"
        "Besoin de plus ? Activez /premium\n\n"
        "🚀 Abonnement Premium :\n└ 100–200 requêtes/jour\n└ GPT-5.5\n└ Gemini 3.5\n"
        "└ DeepSeek\n└ Claude 4.8 Opus et Sonnet\n└ Nano Banana Pro\n└ Documents\n\n"
        "🌅 Pack images : {image}\n🎬 Pack vidéo : {video}\n🎸 Pack musique : {music}\n\n"
        "📞 Support : {support}"
    ),
    "account.sub_free": "Gratuit ✔️",
    "account.role": "🎭 Rôle : {title}",
    "account.role_custom": "✍️ rôle perso",
    "account.sub_premium": "Premium ✔️",
    "account.sub_premium_x2": "Premium X2 ✔️",
    "photo.menu": (
        "🌅 Création et édition d'images\n\nChoisissez le service souhaité 👇\n\n"
        "🔴 Effets photo\nModèles prêts à l'emploi pour des photos tendance, portraits, avatars et images créatives.\n\n"
        "💬 GPT Image 2\nPhotoshop IA d'OpenAI pour générer et modifier des images selon votre description.\n\n"
        "♊️ Nano Banana Pro\nPhotoshop IA avancé de Google pour une retouche précise, le remplacement de détails et l'amélioration des images.\n\n"
        "🖼 Midjourney, Seedream, Recraft et FLUX\nGénérateurs populaires pour l'art, les photos réalistes, le design et les illustrations.\n\n"
        "📸 Pack d'avatars\nEnvoyez une photo et le bot créera 100 avatars dans différents styles.\n\n"
        "Choisissez un service ci-dessous et commencez la création d'image ✨"
    ),
    "video.menu": (
        "🎬 Création de vidéo\n\nChoisissez le service pour générer le clip 👇\n\n"
        "🔴 Effets vidéo\nModèles prêts à l'emploi pour des clips tendance, vidéos courtes et effets créatifs.\n\n"
        "🌱 Seedance 2.0\nCrée une vidéo à partir de texte, d'images, de vidéo et d'audio.\n\n"
        "♊ Veo 3.1, Pika et Hailuo\nGénèrent une vidéo à partir d'une description ou d'une image envoyée.\n\n"
        "❎ Grok Imagine et Kling\nCréent des vidéos et aident aussi à modifier des clips existants.\n\n"
        "👨 Kling Effects\nDonne vie à vos photos et y ajoute des effets visuels.\n\n"
        "🎥 Kling Motion\nAnime une image en reproduisant les mouvements d'une vidéo d'exemple.\n\n"
        "Choisissez le service ci-dessous et commencez la création de vidéo ✨"
    ),
    "music.menu": (
        "🎸 Création de musique\n\nChoisissez le service pour générer une chanson ou de la musique 👇\n\n"
        "🎵 Suno V5.5\nCrée des chansons complètes jusqu'à 8 minutes : musique, voix, paroles et arrangement clé en main.\n\n"
        "♊ Lyria 3 Pro\nNouveau service de Google pour générer des chansons et de la musique instrumentale jusqu'à 3 minutes.\n\n"
        "Vous pouvez utiliser vos propres paroles ou demander à l'IA de les inventer ✨"
    ),
    "search.intro": (
        "🔎 Recherche internet\n\n"
        "Choisissez le modèle de recherche ci-dessous ou utilisez celui par défaut.\n\n"
        "Écrivez ensuite votre requête dans le chat — le bot trouvera des informations à jour et préparera une réponse 👇"
    ),
    "model.selected": "✅ Modèle « {name} » sélectionné.",
    "model.premium_locked": "🔒 Le modèle « {name} » est réservé à /premium.",
    "settings.lang.choose": "Choisissez la langue de l'interface :",
    "settings.lang.saved": "✅ Langue modifiée.",
    "settings.context.on": "✅ Contexte activé.",
    "settings.context.off": "❌ Contexte désactivé.",
    "privacy.btn_terms": "📄 Conditions d'utilisation",
    "privacy.btn_policy": "📄 Politique de confidentialité",
    "gate.premium": "🔒 Cette fonction est réservée à /premium.",
    "gate.pack_empty": "Vous n'avez plus de générations. Appuyez sur « Recharger » 👇",
    "quota.exceeded.free": "Vous avez utilisé vos requêtes gratuites cette semaine ({used}/{limit}) et vos ✨ aussi.\nInvitez des amis /invite ou prenez le bonus quotidien /bonus pour plus de ✨, ou activez /premium 🚀",
    "quota.exceeded.premium": "Limite quotidienne atteinte ({used}/{limit}) et ✨ épuisés. Réinitialisation demain, ou rechargez des ✨ via /invite et /bonus.",
    "docs.prompt": (
        "📄 Travail avec les documents\n\n"
        "Envoyez un fichier au bot et posez des questions sur son contenu.\n\n"
        "Formats pris en charge :\ndocx, pdf, xlsx, xls, csv, pptx, txt\n\n"
        "Taille maximale : jusqu'à 10 Mo\n\n"
        "Ce que vous pouvez faire :\n"
        "└ obtenir un résumé du document\n└ rechercher une information précise\n"
        "└ analyser tableaux et textes\n└ poser des questions sur le fichier\n"
        "└ demander d'expliquer, traduire ou structurer les données\n\n"
        "💎 Le travail avec les documents nécessite un abonnement /premium.\n\n"
        "⚠️ Chaque requête sur le document consomme 3 générations."
    ),
    "ai.unavailable": "⚠️ Le service d'IA est temporairement indisponible. Réessayez un peu plus tard.",
    "ai.rate_limit": "✨ L'IA est un peu occupée — renvoie simplement ton message. Ton quota n'a pas été utilisé.",
    "common.please_wait": "Veuillez patienter un instant •••",
    "common.cancelled": "Annulé.",  # FIX: AUDIT13-L11
    "gdpr.export_ready": "📦 Vos données sont prêtes — fichier ci-joint.",  # FIX: AUDIT13-M22
    "common.coming_soon": "🛠 Cette section arrive bientôt.",
    "common.banned": "L'accès au bot est restreint.",
    "btn.model": "📝 Choisir le modèle",
    "btn.images": "🎨 Créer une image",
    "btn.search": "🔎 Recherche web",
    "btn.search_model": "🔎 Modèle de recherche : {name}",
    "search.choose_model": "Choisissez un modèle pour la recherche internet 👇",
    "search.model_set": "✅ Modèle de recherche : {name}",
    "btn.video": "🎬 Créer une vidéo",
    "btn.documents": "📄 Document",
    "btn.music": "🎸 Créer une chanson",
    "btn.premium": "🚀 Premium",
    "btn.account": "👤 Mon profil",
    "btn.translate": "🌐 Traduire",
    "btn.close": "Fermer",
    "btn.back": "← Retour",
    "btn.connect_premium": "🚀 Obtenir Premium",
    "btn.topup": "🎵 Recharger",
    "btn.set_model": "Choisir le modèle",
    "btn.set_role": "Description du rôle",
    "btn.set_context": "Support du contexte",
    "btn.set_voice": "Réponses vocales",
    "btn.set_lang": "Langue de l'interface",
    "premium.choose_duration": "Choisissez la durée d'abonnement 👇",
    "premium.choose_gateway": "Choisissez le mode de paiement 👇",
    "premium.upgrade_warning": "⚠️ Vous avez un forfait {current} actif. Le temps restant continuera avec le nouveau forfait {new}.",
    "premium.btn_premium": "⭐ Premium",
    "premium.btn_premium_x2": "🔥 Premium X2",
    "premium.btn_image": "🌅 Pack images",
    "premium.btn_video": "🎬 Pack vidéo",
    "premium.btn_music": "🎸 Pack musique",
    "unit.generations": "générations",
    "unit.sec": "s",
    "vcfg.with_sound": "Avec le son",
    "vcfg.enhance": "Améliorer le prompt",
    "vcfg.seed_add": "Ajouter un seed",
    "vcfg.seed_set": "seed : {v}",
    "btn.instruction": "❤️ Guide",
    "btn.topup_pay": "💳 Recharger",
    "video.image_saved": "🖼 Image ajoutée. Envoyez maintenant une description de la vidéo ⚡",
    "video.effects_hint": "🎬 Les effets vidéo sont dans la Mini App. Ouvrez-la depuis le menu des pièces jointes 📎",
    "photo.effects_hint": "🎨 Les effets photo sont disponibles dans la Mini App. Ouvrez-la depuis le menu des pièces jointes 📎",  # FIX: AUDIT13-L13
    "tts.unavailable": "⚠️ La synthèse vocale est indisponible pour le moment.",
    "tts.failed": "⚠️ Impossible de vocaliser la réponse.",
    "doc.unsupported": "Pris en charge : pdf, docx, doc, xlsx, xls, csv, pptx, txt (jusqu'à 10 Mo).",
    "doc.too_large": "Fichier trop volumineux. Maximum 10 Mo.",
    "doc.extract_failed": "Impossible d'extraire le texte du fichier.",
    "doc.empty": "Aucun texte trouvé dans le fichier.",
    "doc.received": "📄 Fichier « {name} » reçu. Posez vos questions — chaque requête consomme {cost} générations.",
    "btn.translate_hint": "🌐 Appuyez sur 🌐 sous la réponse de l'IA pour la traduire.",
    "voice.selected": "Voix : {voice}",
    "voice.sample": "Bonjour ! Voici à quoi ressemble la voix sélectionnée.",
    "search.nothing": "Aucun résultat.",
    "btn.daily_bonus": "🎁 Bonus quotidien",
    "bonus.claimed": "🎁 Bonus reçu : +{amount} ✨ · Série : {streak} 🔥",
    "bonus.already": "✅ Déjà réclamé aujourd'hui. Revenez demain ! · Série : {streak} 🔥",
    "notify.premium_granted": "🎁 On vous a offert Premium pour {months} mois ! Profitez-en 💎",
    "notify.premium_revoked": "ℹ️ Votre abonnement Premium a été désactivé par un administrateur.",
    "notify.banned": "🚫 Votre compte a été bloqué. Si c'est une erreur, contactez le support.",
    "notify.unbanned": "✅ Votre compte a été débloqué. Vous pouvez réutiliser le bot.",
    "contact.saved": "✅ Merci ! Votre numéro de téléphone a été enregistré.",
    "btn.open_app": "🚀 Ouvrir l'app",
    "voice.on": "🔊 Voix : ON",
    "voice.off": "🔇 Voix : OFF",
    "throttle.flood": "⏳ Trop de requêtes. Patientez un instant.",
    "srv.photoeffects": "🎨 Effets photo",
    "srv.videoeffects": "🎬 Effets vidéo",
    "srv.avatar": "👤 Pack d'avatars",
    "srv.faceswap": "🔄 Échange de visage",
    "srv.upscale": "📐 Agrandir X2/X4",
    "pack.label.popular": "POPULAIRE",
    "pack.label.best": "MEILLEUR CHOIX",
    "product.premium": "Premium",
    "product.premium_x2": "Premium X2",
    "pack.name.image": "Pack images",
    "pack.name.video": "Pack vidéo",
    "pack.name.music": "Pack musique",
    "duration.1": "1 mois",
    "duration.3": "3 mois",
    "duration.6": "6 mois",
    "duration.12": "1 an",
    "pack.choose": "Choisissez le pack « {name} » 👇",
    # ----- VIP / loyalty (ТЗ §4) -----
    "btn.vip": "🏅 Niveaux VIP",
    "account.vip": "🏅 Niveau : {tier} · {left} ⭐ jusqu'à {next}",
    "account.vip_top": "🏅 Niveau : {tier} (max)",
    "account.vip_none": "🏅 {left} ⭐ jusqu'au niveau {next}",
    "vip.title": "🏅 Niveaux VIP\nVotre total d'achats : {spent} ⭐\n",
    "vip.row": "{mark} {name} — dès {min} ⭐ · +{daily}/jour, +{weekly}/sem",
    "vip.reached": "🎉 Félicitations ! Vous avez atteint le niveau VIP {tier}.\nVous avez maintenant +{daily} générations/jour et +{weekly}/semaine.",
    # ----- global sale (ТЗ §4) -----
    "sale.banner": "🔥 Promo −{percent}%",
    "sale.ends_in": "⏳ se termine dans : {time}",
    "sale.left_dh": "{d}j {h}h",
    "sale.left_hm": "{h}h {m}m",
    "sale.left_m": "{m}m",
    "pay.sub_invoice_desc": "Abonnement : {title}",
    "pay.pack_invoice_desc": "Pack de générations : {title}",
    "pay.sub_activated": "✅ Abonnement « {title} » activé ! Merci pour votre achat 🚀",
    "pay.pack_added": "✅ Pack rechargé : +{qty} {unit} ({pack}). Merci pour votre achat !",
    "pay.avatar_paid": "✅ Payé ! Envoyez votre meilleur selfie — je créerai 100 avatars (~15 min).",
    "pay.link": "Ouvrez le lien pour payer. L'accès s'active automatiquement après le paiement 👇",
    "pay.link_btn": "💳 Payer — {title}",
    "pay.unavailable": "Ce mode de paiement est indisponible pour le moment.",
    "pay.failed": "Impossible de créer la facture. Essayez un autre mode.",
    "gen.video_started": "🎬 Génération de vidéo lancée ! Cela prendra quelques minutes — j'enverrai le résultat dès qu'il sera prêt.",
    "gen.music_started": "🎶 Je génère votre chanson — j'enverrai l'audio dès qu'il sera prêt !",
    "gen.photo_started": "🎨 Application de « {name} » — j'enverrai la vidéo dès qu'elle sera prête !",
    "gen.unavailable": "⚠️ Service temporairement indisponible. Réessayez plus tard.",
    "gen.unavailable_refund": "⚠️ Service temporairement indisponible. Crédits remboursés.",
    "gen.error_refund": "⚠️ Erreur de génération. Crédits remboursés.",
    "mod.blocked": "🚫 La requête enfreint les règles d'utilisation.",
    "seed.ask": "Saisissez un seed pour la génération (valeur numérique) :",
    "seed.saved": "✅ Seed enregistré.",
    "avatar.info": (
        "👤 Avatars IA\n\nCréez 100 avatars stylés pour les réseaux sociaux dans différents styles.\n"
        "Prix : {price} ⭐ le pack. Résolution 1024×1440, sans filigrane.\n"
        "Après le paiement, envoyez votre meilleur selfie — génération ~15 minutes."
    ),
    "avatar.title": "Pack d'avatars",
    "avatar.buy_btn": "Acheter pour {price} ⭐",
    "avatar.started": (
        "🎨 Génération de 100 avatars lancée ! Cela prendra ~15 minutes — vous "
        "pouvez continuer à utiliser le bot, j'enverrai le résultat dès qu'il sera prêt."
    ),
    "music.prompt": "🎵 {name} : envoyez une description de la chanson (style, ambiance, paroles).",
    "kling.effects_intro": (
        "🌊 Kling Effects\n\n1. Choisissez un effet parmi les options ci-dessous.\n"
        "2. Envoyez une photo au bot pour appliquer l'effet choisi."
    ),
    "kling.effect_selected": "Effet : {name}\n\nEnvoyez une photo et le bot appliquera l'effet choisi !",
    "kling.motion_intro": (
        "💃 Kling Motion\n\nVotre photo prendra vie et reproduira le mouvement d'une vidéo d'exemple.\n"
        "Choisissez un modèle 👇"
    ),
    "kling.motion_selected": "Mouvement : 💃 {name}. Envoyez une photo — Kling Motion y transférera le mouvement.",
    "btn.voice": "🔊",
    "btn.view": "🔥 Voir",
    "deletecontext.done": "Contexte effacé. Par défaut, le bot tient compte de votre question précédente et de sa réponse.",
    "music.paywall": "🎵 Pour générer des chansons, achetez un pack musique. Appuyez sur « Recharger » 👇",
    "gate.subscription": "Pour continuer gratuitement, abonnez-vous à notre canal 👇\nPuis appuyez sur « Je suis abonné ».",
    "gate.subscription.ok": "✅ Merci de votre abonnement ! Vous pouvez continuer.",
    "gate.subscription.fail": "❌ Il semble que vous ne soyez pas encore abonné.",
    "settings.role.prompt": "Envoyez le rôle (prompt système) que l'IA doit suivre.",
    "settings.role.current_none": "Rôle actuel : non défini.",
    "settings.role.current": "Rôle actuel :\n{role}",
    "settings.role.saved": "✅ Rôle enregistré.",
    "settings.role.cleared": "Rôle supprimé.",
    "settings.role.too_long": "❌ Rôle trop long (max {limit} caractères). Raccourcissez-le et renvoyez-le.",
    "settings.voice.intro": "Choisissez une voix pour les réponses vocales (disponible en /premium) :",
    "settings.voice.preview": "Écouter la voix sélectionnée",
    "settings.intro": (
        "⚙️ Paramètres du bot\n\nIci, adaptez l'IA à vos besoins 👇\n\n"
        "1️⃣ Choisir le modèle — le réseau qui répond à vos requêtes.\n\n"
        "2️⃣ Définir le rôle — ex. assistant, rédacteur, programmeur, enseignant ou expert.\n\n"
        "3️⃣ Contexte du dialogue — activez/désactivez. Activé, le bot tient compte de sa réponse précédente.\n\n"
        "4️⃣ Réponses vocales — configurez la lecture et choisissez la voix. Disponible en /premium.\n\n"
        "5️⃣ Langue de l'interface — choisissez une langue confortable.\n\n"
        "Choisissez une option ci-dessous 👇"
    ),
    "model.intro": (
        "🤖 Choisir un modèle d'IA\n\nDes modèles de pointe pour le texte, le code, l'analyse et les tâches complexes.\n\n"
        "Choisissez un modèle ci-dessous 👇\n\n"
        "💬 GPT-5.5 — modèle phare d'OpenAI. Consomme 3 générations par requête.\n\n"
        "💬 GPT-5.4 — modèle polyvalent pour le code et les textes.\n\n"
        "💬 GPT-5 mini — modèle rapide pour le quotidien. Gratuit.\n\n"
        "🌥 Claude 4.8 Opus — modèle phare d'Anthropic. Consomme 5 générations par requête.\n\n"
        "🌥 Claude 4.6 Sonnet — fort pour textes, code et maths.\n\n"
        "🐳 DeepSeek V4 — rapide et puissant. Gratuit.\n\n"
        "🐳 DeepSeek V4 Pro — version avancée de DeepSeek.\n\n"
        "♊️ Gemini 3.5 Flash — modèle phare de Google.\n\n"
        "♊️ Gemini 3.1 Flash — modèle Google rapide et intelligent. Gratuit.\n\n"
        "📌 Documents : en Premium, envoyez des fichiers jusqu'à 10 Mo. Consomme 3 générations.\n\n"
        "🎁 Gratuit : GPT-5 mini, Gemini 3.1 Flash, DeepSeek V4\n💎 Autres modèles en Premium : /premium\n\n"
        "Choisissez un modèle ci-dessous 👇"
    ),
    "help": (
        "📚 Aide du bot\n\nCommandes et fonctions principales.\n\n"
        "📝 Génération de texte\nÉcrivez votre requête dans le chat. Les utilisateurs /premium peuvent aussi envoyer des messages vocaux.\n\n"
        "Commandes :\n└ /deletecontext — nouveau dialogue\n└ /s — recherche internet\n"
        "└ /settings — modèle, rôle, langue et contexte\n└ /model — choisir le modèle\n\n"
        "💡 Plus c'est détaillé, meilleure est la réponse.\n\n"
        "📄 Documents (Premium)\nEnvoyez un fichier jusqu'à 10 Mo et posez des questions.\nFormats : docx, pdf, xlsx, xls, csv, pptx, txt.\nChaque requête consomme 3 générations.\n\n"
        "🌅 Images\n└ Nano Banana 2 / Pro\n└ GPT Image 2\n└ Midjourney\n└ Flux\n└ Seedream\n└ Recraft\nCommandes : /photo, /midjourney\n\n"
        "🎬 Vidéo\n└ Kling\n└ Seedance 2.0\n└ Pika\n└ Veo 3.1\n└ Hailuo\n└ Grok Imagine\nCommande : /video\n\n"
        "🎸 Musique\n└ Suno V5.5\n└ Lyria 3 Pro\nCommandes : /music, /suno\n\n"
        "⚙️ Autres\n└ /start\n└ /account\n└ /premium\n└ /privacy\n\n"
        "💬 Questions : {support}"
    ),
    "privacy": (
        "🔐 Documents juridiques\n\nAvant d'utiliser le bot, lisez les règles et le traitement des données :\n\n"
        "1️⃣ Conditions d'utilisation\n2️⃣ Politique de confidentialité\n\n"
        "En continuant à utiliser le bot, vous confirmez les avoir lues et acceptées."
    ),
    "premium": (
        "🚀 Offres et fonctions\n\nLe bot réunit des services d'IA populaires : texte, recherche, images, vidéo, musique et fichiers.\n\n"
        "🎁 GRATUIT | chaque semaine\n\n100 requêtes :\n✅ GPT-5 mini\n✅ DeepSeek V4\n✅ Gemini 3.1 Flash\n✅ Perplexity\n✅ Reconnaissance d'images\n\n"
        "25 générations d'images :\n♊️ Nano Banana 2\n✅ GPT Image 2\n\n"
        "💎 PREMIUM | 1 mois\n\nLimite : 100 requêtes/jour\n\n✅ Tout le plan gratuit\n✅ GPT-5.5\n✅ Gemini 3.5 Flash\n✅ Claude 4.8 Opus et Sonnet\n✅ DeepSeek\n♊️ Nano Banana Pro\n✅ GPT Image 2\n✅ Documents\n✅ Réponses vocales\n✅ Sans pub\n\nPrix : {p_premium}⭐️\n\n"
        "💎 PREMIUM X2 | 1 mois\n\nLimite : 200 requêtes/jour\n\n✅ Tout Premium\n✅ Limite quotidienne plus élevée\n\nPrix : {p_premium_x2}⭐️\n\n"
        "🌅 IMAGES | pack\n\nDe 50 à 500 générations au choix\n\nServices disponibles :\n"
        "🌅 Midjourney\n🎬 Midjourney Video\n🌱 Seedream\n🎨 Recraft\n⚡ Flux\n✅ Échange de visage sur photo\n\nPrix : à partir de {p_image_from}⭐️\n\n"
        "🎬 VIDÉO | pack\n\nDe 2 à 50 générations au choix\n\nServices disponibles :\n"
        "📼 Kling\n🎥 Veo 3.1\n🚀 Seedance 2.0\n❎ Grok Imagine\n🎞 Hailuo\n✨ Pika\n\n"
        "En plus :\n✅ Édition de vidéo\n✅ Effets vidéo créatifs\n\nPrix : à partir de {p_video_from}⭐️\n\n"
        "🎸 MUSIQUE | pack\n\nDe 20 à 100 générations au choix\n\nServices disponibles :\n"
        "🎸 Suno V5.5\n🎼 Lyria 3 Pro\n\nPossibilités :\n✅ Chansons sur vos propres paroles\n✅ Génération des paroles par l'IA\n\nPrix : à partir de {p_music_from}⭐️\n\n"
        "⭐️ Tous les prix sont en Stars — la monnaie de Telegram.\n\n💬 Paiement et accès :\n{support}"
    ),
    "gate.channel": "Pour continuer a utiliser le bot gratuitement, abonnez-vous aux chaines ci-dessous.\n\nGrace aux abonnements, vous recevez 100 requetes gratuites par semaine vers ChatGPT, DeepSeek, Gemini, Perplexity, generateurs d'images et plus.\n\nVous voulez tout sans publicite ? Appuyez sur Premium.",
    "gate.btn_subscribe": "S'abonner a {channel}",
    "gate.btn_check": "Verifier l'abonnement",
    "gate.btn_premium": "Premium",
    "gate.ok": "Merci de votre abonnement ! Vous pouvez continuer.",
    "gate.not_subscribed": "Vous n'etes pas encore abonne a toutes les chaines.",
    "gate.premium_voice": "Pour envoyer des requetes vocales, souscrivez a /premium.",
    "faceswap.step1": "[Etape 1/2] Envoyez l'image ou le visage sera remplace.",
    "faceswap.step2": "[Etape 2/2] Envoyez maintenant la photo du visage source.",
    "upscale.intro": "Cet outil augmente la resolution de l'image. Choisissez un facteur.",
    "upscale.x2": "Agrandir X2",
    "upscale.x4": "Agrandir X4",
    "upscale.send_image": "Envoyez une image (max 1024x1024). {cost} generations seront debitees.",
    "vision.coming_soon": "La reconnaissance d'images sera bientot disponible.",
    "vision.failed": "Impossible de traiter l'image. Reessayez.",
    "photo.choose": "Que faire avec cette photo ?",
    "photo.btn_describe": "🔎 Decrire",
    "photo.btn_edit": "🎨 Modifier selon la legende",
    "photo.edit_working": "🎨 Modification de la photo…",
    "photo.edit_done": "✅ Termine !",
    "photo.edit_unavailable": "🛠 La retouche photo arrive bientot.",
    "photo.edit_failed": "Impossible de modifier la photo. Reessayez.",
    "photo.edit_no_caption": "Ajoutez une legende decrivant la modification et je changerai l'image.",
    "voice_in.coming_soon": "La saisie vocale sera bientot disponible.",
    "voice_in.heard": "🎙 Reconnu : «{text}»",
    "voice_in.empty": "Impossible de reconnaitre la voix. Reessayez d'enregistrer.",
    "voice_in.failed": "Impossible de traiter le message vocal. Reessayez.",
    "gen.image_started": "Requete recue ! J'enverrai le resultat des qu'il sera pret.",
    "pay.credits_added": "✨ {qty} crédits ajoutés ! Utilisez-les dans la Mini App.",
    "img.more": "🔄 Encore",
    "img.upscale": "🔍 Agrandir",
    "img.file": "📎 Qualité maximale",
    "img.no_prompt": "Choisissez d'abord un service et envoyez un prompt.",
    "promo.usage": "Utilisation : /promo CODE",
    "promo.invalid": "❌ Ce code promo est invalide ou expiré.",
    "promo.already": "Vous avez déjà utilisé ce code promo.",
    "promo.ok": "✅ Code promo activé : +{amount} {reward}.",
    "promo.not_eligible": "❌ Ce code promo est réservé aux nouveaux utilisateurs.",
    # --- bot UI strings (handlers sweep) ---
    "fb.thanks": "Merci pour votre retour !",
    "report.usage": "Utilisation : <code>/report description du problème</code>",
    "report.thanks": "Merci ! Votre signalement a été reçu.",
    "roles.btn_off": "🚫 Désactiver le rôle",
    "roles.btn_custom": "✍️ Rôle perso",
    "roles.unavailable": "Les rôles prédéfinis sont actuellement indisponibles.",
    "roles.choose": "🎭 Choisissez un rôle prédéfini pour l'assistant.",
    "roles.choose_active": "\n\nUn rôle personnalisé est actif — choisissez-en un autre ou désactivez-le.",
    "roles.not_found": "Rôle introuvable",
    "roles.enabled": "Rôle « {title} » activé ✅",
    "roles.enabled_full": "C'est fait — l'assistant agit désormais comme « {title} ». Pour le désactiver, envoyez /roles → « Désactiver le rôle ».",
    "roles.disabled": "Rôle désactivé",
    "roles.disabled_full": "Rôle de l'assistant désactivé — mode normal.",
    "contest.none": "Aucun concours actif pour le moment. Revenez plus tard !",
    "contest.entrants": "Participants : {count}",
    "contest.btn_enter": "Participer",
    "contest.ended": "Ce concours est déjà terminé.",
    "contest.entered": "Vous participez au concours ! Bonne chance ! 🍀",
    "contest.already": "Vous participez déjà à ce concours.",
    "gift.btn_premium": "🎁 Premium · 1 mois",
    "gift.btn_pack": "🎁 Pack d'images · 50",
    "gift.btn_sub": "🎁 Offrir un abonnement",
    "gift.btn_pack_menu": "📦 Offrir un pack",
    "gift.pack_none": "Les packs sont indisponibles pour l'instant.",
    "gift.choose": "🎁 Offrez un abonnement ou un pack à un ami.\nChoisissez quoi offrir :",
    "gift.invoice_title_sub": "🎁 {product} · {value} mois",
    "gift.invoice_desc": "Cadeau : {title}",
    "gift.paid": "🎁 Cadeau payé !\n\nCode : <code>{code}</code>\n\nEnvoyez à votre ami la commande <code>/redeem {code}</code> ou ce lien :\n{link}",
    "redeem.usage": "Utilisation : <code>/redeem CODE</code>",
    "inline.hint_title": "Saisissez une question…",
    "inline.hint_text": "Tapez une question après le nom du bot pour obtenir une réponse de l'IA.",
    "inline.error_title": "Erreur",
    "inline.error_text": "Impossible d'obtenir une réponse. Réessayez plus tard.",
    "inline.throttle_title": "Trop fréquent",
    "inline.throttle_text": "Trop de requêtes d'affilée. Patientez un instant et réessayez.",
    "support.usage": "Utilisation : <code>/support votre question</code>\nDécrivez le problème — votre message parviendra au support.",
    "support.sent": "Message envoyé au support, nous répondrons bientôt.",
    "pay.precheckout_unavailable": "Paiement indisponible",
    "pay.activate_failed": "⚠️ Impossible d'activer l'achat. Votre paiement (⭐) a été remboursé. Réessayez ou contactez le support.",
    "invite.summary": "🔗 Votre lien de parrainage :\n{link}\n\n👥 Utilisateurs invités : {count}\n✨ Récompense par invitation : {reward}\n💰 Total gagné : ✨ {earned}",
    "links.none": "Aucun lien configuré pour le moment.",
    "links.title": "Liens utiles :",
    "avatar.invoice_desc": "100 avatars IA 1024×1440",
    "promo.reward.credits": "crédits",
    "promo.reward.image": "images",
    "promo.reward.video": "vidéos",
    "promo.reward.music": "morceaux",
    "promo.reward.premium": "jours de Premium",
    "pay.success": "✅ Paiement réussi ! Votre accès est activé. Merci pour votre achat 🚀",
    "gen.video_ready": "✅ Votre vidéo est prête !",
    "gen.song_ready": "✅ Votre chanson est prête !",
    "gen.photo_ready": "✅ Votre photo est prête !",
    "gen.avatar_unavailable_refund": "⚠️ Le service « Avatars » est temporairement indisponible. Votre paiement (⭐) a été intégralement remboursé sur votre solde Telegram. Toutes nos excuses !",
    "spec.desc.gpt_image2": "Créez et modifiez des images directement dans le chat.\n\nPrêt à commencer ?\nEnvoyez de 1 à 4 images à modifier, ou écrivez ce que vous voulez créer.",
    "spec.desc.nano_banana": "Gemini Images — Plus éclatant. Plus intelligent !\n\nCréez et modifiez des images dans le chat. Envoyez de 1 à 10 images ou écrivez ce que vous voulez créer.",
    "spec.desc.seedream": "Créez et modifiez des images dans le chat. Envoyez de 1 à 10 images ou écrivez ce que vous voulez créer.",
    "spec.desc.midjourney": "Écrivez l'image que vous voulez créer.\n\nLe bot prend en charge tous les principaux paramètres et fonctions de Midjourney.",
    "spec.desc.flux2": "Choisissez le format et le modèle Flux. Les modèles Flex et Max coûtent 2 générations.\n\nPour lancer, écrivez l'image que vous voulez créer 🐝",
    "spec.desc.recraft": "Recraft — graphisme vectoriel et design. Écrivez l'image que vous voulez créer.",
    "spec.desc.seedance": "Génération de vidéo à partir de texte, d'images, de vidéo et d'audio.\n\nRéglez les options et envoyez un prompt pour lancer ⚡",
    "spec.desc.veo": "Veo 3.1 — vidéo cinématographique de Google. Envoyez un prompt ⚡",
    "spec.desc.grok": "Création et édition de vidéo. L'éditeur coûte 2 générations.\n+18, violence et deepfakes interdits. Envoyez un prompt ⚡",
    "spec.desc.kling_ai": "Création et édition de vidéo. Envoyez un prompt ⚡",
    "spec.desc.hailuo": "Hailuo — vidéo à partir d'une description et d'une image. Envoyez un prompt ⚡",
    "spec.desc.pika": "Pika Labs — vidéo à partir d'une description et d'images. Envoyez un prompt ⚡",
    "spec.desc.mj_video": "Midjourney Video — animation d'images. Envoyez une photo et/ou un prompt ⚡\nDébité du pack d'images.",
    "spec.mode.create": "Créer",
    "spec.mode.edit": "Éditeur",
    "gen.ready_generic": "✅ Votre génération ({service}) est prête.",
    "refund.stars": "⚠️ La commande n'a pas pu être réalisée. Le paiement (⭐) a été remboursé sur votre solde Telegram. Toutes nos excuses !",
    "notify.premium_expiry": "⏳ Votre Premium expire dans {days} jour(s). Renouvelez votre abonnement pour ne pas perdre vos limites augmentées.",
    "notify.low_balance": "✨ Votre solde est presque épuisé — il reste {balance} ✨. Rechargez pour continuer à générer sans pause.",
    "notify.winback": "👋 Ça fait longtemps ! Revenez — nous avons de nouveaux modèles et effets. Envoyez une requête et continuons 🙌",
    "notify.bonus_available": "🎁 Votre bonus quotidien est prêt ! Récupérez-le aujourd'hui pour garder votre série et gagner plus ✨.",
    "notify.btn.renew": "⭐ Renouveler Premium",
    "notify.btn.topup": "✨ Recharger",
    "notify.btn.open": "🚀 Voir les offres",
    "notify.btn.bonus": "🎁 Récupérer le bonus",
    "notify.abandoned_cart": "🛒 Vous étiez à un pas de votre achat ! Terminez-le — ça prend une minute.",
    "notify.btn.cart": "🛒 Finaliser l'achat",
    "ref.earned_register": "🎉 Un nouvel utilisateur s'est inscrit via votre lien de parrainage ! Vous avez gagné ✨ {amount}.",
    "ref.welcome_bonus": "🎁 Bonus de bienvenue pour votre inscription via un lien de parrainage : +✨ {amount} !",
    "promo.welcome_bonus": "🎁 Bonus de bienvenue pour un nouvel utilisateur : +✨ {amount} !",
    "promo.purchase_bonus": "🎁 Bonus d'achat : +✨ {amount} !",
    "promo.applied": "🏷 Code promo appliqué : −{percent}% sur votre prochain achat !",
    "promo.applied_banner": "🏷 Promo −{percent}% appliqué",
    "ad.remove_btn": "⭐ Supprimer les pubs",
    "ref.milestone": "🏆 Vous avez invité {count} utilisateurs ! Bonus : +✨ {amount}.",
    "ref.earned_purchase": "🎉 Un achat a été effectué via votre lien de parrainage ! Vous avez gagné ✨ {amount}.",
    "contest.won": "🎉 Félicitations ! Vous avez gagné le concours !",
    "contest.won_credits": "🎉 Félicitations ! Vous avez gagné le concours — vous avez reçu ✨ {amount} !",
    "contest.won_pack": "🎉 Félicitations ! Vous avez gagné le concours — vous avez reçu {amount} {unit} !",
    "gift.not_found": "❌ Aucun cadeau trouvé avec ce code.",
    "gift.already_used": "❌ Ce cadeau a déjà été activé.",
    "gift.own_gift": "🎁 Vous ne pouvez pas activer votre propre cadeau — partagez-le avec un ami.",
    "gift.redeemed_sub": "🎁 Cadeau activé : {product} pour {months} mois.",
    "gift.redeemed_pack": "🎁 Cadeau activé : pack {product} (+{qty}).",
    "gift.redeemed_credits": "🎁 Cadeau activé : +{qty} ✨.",
    "gift.unknown_kind": "❌ Type de cadeau inconnu.",
}
