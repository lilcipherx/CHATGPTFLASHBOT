"""Portuguese (Brazil) locale — user-facing screens; long legal/help fall back to RU."""

MESSAGES: dict[str, str] = {
    "start.welcome": (
        "Olá! 👋\n\n"
        "Sou o SUPER AI BOT, seu assistente de IA que ajuda a criar texto, imagens, vídeo, "
        "música e muito mais com redes neurais modernas.\n\n"
        "🎁 GRÁTIS:\n100 solicitações por semana para texto, imagens e outras ferramentas de IA.\n\n"
        "⭐️ PREMIUM:\nAcesso ampliado às redes neurais mais poderosas.\n\n"
        "Como usar o bot?\n\n"
        "📝 TEXTO\nEscreva sua pergunta ou tarefa no chat — ajudo na hora.\n\n"
        "🔎 BUSCA\nUse /s para perguntar com busca na internet.\n\n"
        "🌅 IMAGENS\nToque em /photo para criar ou editar uma imagem.\n\n"
        "🎬 VÍDEO\nToque em /video para criar um vídeo.\n\n"
        "🎸 MÚSICA\nToque em /music para criar uma música.\n\n"
        "⚙️ MODELO\n/model permite escolher a rede neural.\n\n"
        "💎 PREMIUM\n/premium libera recursos avançados.\n\n"
        "Comece agora — é só me enviar qualquer mensagem 🚀"
    ),
    "account": (
        "👤 Sua conta\n\nAssinatura: {sub}\nModelo selecionado: {model_name} /model\n\n"
        "📊 Estatísticas de uso\n\nSolicitações nesta semana: {used}/{limit}\n"
        "✨ Solicitações extras: {credits} (de indicações e do bônus diário; gastas quando o limite semanal acabar)\n\n"
        "Incluído no plano gratuito:\n└ GPT-5 mini\n└ DeepSeek V4\n└ Gemini 3.1 Flash\n"
        "└ Perplexity\n└ GPT Image 2\n└ Nano Banana 2\n\n"
        "Precisa de mais? Ative o /premium\n\n"
        "🚀 Assinatura Premium:\n└ 100–200 solicitações/dia\n└ GPT-5.5\n└ Gemini 3.5\n"
        "└ DeepSeek\n└ Claude 4.8 Opus e Sonnet\n└ Nano Banana Pro\n└ Documentos\n\n"
        "🌅 Pacote de imagens: {image}\n🎬 Pacote de vídeo: {video}\n🎸 Pacote de música: {music}\n\n"
        "📞 Suporte: {support}"
    ),
    "account.sub_free": "Grátis ✔️",
    "account.role": "🎭 Papel: {title}",
    "account.role_custom": "✍️ papel próprio",
    "account.sub_premium": "Premium ✔️",
    "account.sub_premium_x2": "Premium X2 ✔️",
    "photo.menu": (
        "🌅 Criação e edição de imagens\n\nEscolha o serviço desejado 👇\n\n"
        "🔴 Efeitos de foto\nModelos prontos para fotos de tendência, retratos, avatares e imagens criativas.\n\n"
        "💬 GPT Image 2\nPhotoshop com IA da OpenAI para gerar e editar imagens conforme sua descrição.\n\n"
        "♊️ Nano Banana Pro\nPhotoshop com IA avançado do Google para edição precisa, troca de detalhes e melhoria de imagens.\n\n"
        "🖼 Midjourney, Seedream, Recraft e FLUX\nGeradores populares para artes, fotos realistas, design e ilustrações.\n\n"
        "📸 Pacote de avatares\nEnvie uma foto e o bot criará 100 avatares em estilos diferentes.\n\n"
        "Escolha um serviço abaixo e comece a criar sua imagem ✨"
    ),
    "video.menu": (
        "🎬 Criação de vídeo\n\nEscolha o serviço para gerar o vídeo 👇\n\n"
        "🔴 Efeitos de vídeo\nModelos prontos para vídeos de tendência, vídeos curtos e efeitos criativos.\n\n"
        "🌱 Seedance 2.0\nCria vídeo a partir de texto, imagens, vídeo e áudio.\n\n"
        "♊ Veo 3.1, Pika e Hailuo\nGeram vídeo a partir de uma descrição ou imagem enviada.\n\n"
        "❎ Grok Imagine e Kling\nCriam vídeos e também ajudam a editar vídeos prontos.\n\n"
        "👨 Kling Effects\nDá vida às suas fotos e adiciona efeitos visuais.\n\n"
        "🎥 Kling Motion\nAnima uma imagem repetindo os movimentos de um vídeo de exemplo.\n\n"
        "Escolha o serviço abaixo e comece a criar seu vídeo ✨"
    ),
    "music.menu": (
        "🎸 Criação de música\n\nEscolha o serviço para gerar uma canção ou música 👇\n\n"
        "🎵 Suno V5.5\nCria canções completas de até 8 minutos: música, vocais, letra e arranjo prontos.\n\n"
        "♊ Lyria 3 Pro\nNovo serviço do Google para gerar canções e música instrumental de até 3 minutos.\n\n"
        "Você pode usar sua própria letra ou pedir à IA para criá-la ✨"
    ),
    "search.intro": (
        "🔎 Busca na internet\n\n"
        "Escolha o modelo de busca abaixo ou use o padrão.\n\n"
        "Depois escreva sua consulta no chat — o bot encontrará informações atuais na internet e preparará uma resposta 👇"
    ),
    "model.selected": "✅ Modelo «{name}» selecionado.",
    "model.premium_locked": "🔒 O modelo «{name}» está disponível apenas no /premium.",
    "settings.lang.choose": "Escolha o idioma da interface:",
    "settings.lang.saved": "✅ Idioma alterado.",
    "settings.context.on": "✅ Contexto ativado.",
    "settings.context.off": "❌ Contexto desativado.",
    "privacy.btn_terms": "📄 Termos de uso",
    "privacy.btn_policy": "📄 Política de privacidade",
    "gate.premium": "🔒 Este recurso está disponível apenas no /premium.",
    "gate.pack_empty": "Suas gerações acabaram. Toque em «Recarregar» 👇",
    "quota.exceeded.free": "Você usou as solicitações grátis desta semana ({used}/{limit}) e os ✨ também.\nConvide amigos /invite ou pegue o bônus diário /bonus para mais ✨, ou ative /premium 🚀",
    "quota.exceeded.premium": "Limite diário atingido ({used}/{limit}) e os ✨ acabaram. Renova amanhã, ou recarregue ✨ por /invite e /bonus.",
    "docs.prompt": (
        "📄 Trabalho com documentos\n\n"
        "Envie um arquivo ao bot e faça perguntas sobre o conteúdo.\n\n"
        "Formatos suportados:\ndocx, pdf, xlsx, xls, csv, pptx, txt\n\n"
        "Tamanho máximo: até 10 MB\n\n"
        "O que você pode fazer:\n"
        "└ obter um resumo do documento\n└ buscar informações específicas\n"
        "└ analisar tabelas e textos\n└ fazer perguntas sobre o arquivo\n"
        "└ pedir para explicar, traduzir ou estruturar os dados\n\n"
        "💎 O trabalho com documentos requer assinatura /premium.\n\n"
        "⚠️ Cada solicitação sobre o documento consome 3 gerações."
    ),
    "ai.unavailable": "⚠️ O serviço de IA está temporariamente indisponível. Tente novamente em breve.",
    "ai.rate_limit": "✨ A IA está um pouco ocupada — basta enviar sua mensagem de novo. Sua cota não foi usada.",
    "common.please_wait": "Aguarde um momento •••",
    "common.cancelled": "Cancelado.",  # FIX: AUDIT13-L11
    "gdpr.export_ready": "📦 Seus dados estão prontos — arquivo em anexo.",  # FIX: AUDIT13-M22
    "common.coming_soon": "🛠 Esta seção estará disponível em breve.",
    "common.banned": "O acesso ao bot está restrito.",
    "btn.model": "📝 Escolher modelo",
    "btn.images": "🎨 Criar imagem",
    "btn.search": "🔎 Busca na web",
    "btn.video": "🎬 Criar vídeo",
    "btn.documents": "📄 Documento",
    "btn.music": "🎸 Criar música",
    "btn.premium": "🚀 Premium",
    "btn.account": "👤 Meu perfil",
    "btn.translate": "🌐 Traduzir",
    "btn.close": "Fechar",
    "btn.back": "← Voltar",
    "btn.connect_premium": "🚀 Obter Premium",
    "btn.topup": "🎵 Recarregar",
    "btn.set_model": "Escolher modelo",
    "btn.set_role": "Descrição do papel",
    "btn.set_context": "Suporte de contexto",
    "btn.set_voice": "Respostas em voz",
    "btn.set_lang": "Idioma da interface",
    "premium.choose_duration": "Escolha o período da assinatura 👇",
    "premium.choose_gateway": "Escolha a forma de pagamento 👇",
    "premium.upgrade_warning": "⚠️ Você tem um plano {current} ativo. O tempo restante continuará no novo plano {new}.",
    "premium.btn_premium": "⭐ Premium",
    "premium.btn_premium_x2": "🔥 Premium X2",
    "premium.btn_image": "🌅 Pacote de imagens",
    "premium.btn_video": "🎬 Pacote de vídeo",
    "premium.btn_music": "🎸 Pacote de música",
    "unit.generations": "gerações",
    "unit.sec": "s",
    "vcfg.with_sound": "Com som",
    "vcfg.enhance": "Melhorar prompt",
    "vcfg.seed_add": "Adicionar seed",
    "vcfg.seed_set": "seed: {v}",
    "btn.instruction": "❤️ Guia",
    "btn.topup_pay": "💳 Recarregar",
    "video.image_saved": "🖼 Imagem adicionada. Agora envie uma descrição do vídeo ⚡",
    "video.effects_hint": "🎬 Os efeitos de vídeo estão no Mini App. Abra-o pelo menu de anexos 📎",
    "photo.effects_hint": "🎨 Os efeitos de foto estão disponíveis no Mini App. Abra-o pelo menu de anexos 📎",  # FIX: AUDIT13-L13
    "tts.unavailable": "⚠️ A locução está indisponível no momento.",
    "tts.failed": "⚠️ Não foi possível narrar a resposta.",
    "doc.unsupported": "Suportados: pdf, docx, doc, xlsx, xls, csv, pptx, txt (até 10 MB).",
    "doc.too_large": "Arquivo muito grande. Máximo 10 MB.",
    "doc.extract_failed": "Não foi possível extrair texto do arquivo.",
    "doc.empty": "Nenhum texto encontrado no arquivo.",
    "doc.received": "📄 Arquivo «{name}» recebido. Faça perguntas — cada solicitação consome {cost} gerações.",
    "btn.translate_hint": "🌐 Toque em 🌐 abaixo da resposta da IA para traduzi-la.",
    "voice.selected": "Voz: {voice}",
    "voice.sample": "Olá! É assim que soa a voz selecionada.",
    "search.nothing": "Nada encontrado.",
    "btn.daily_bonus": "🎁 Bônus diário",
    "bonus.claimed": "🎁 Bônus recebido: +{amount} ✨ · Sequência: {streak} 🔥",
    "bonus.already": "✅ Já resgatado hoje. Volte amanhã! · Sequência: {streak} 🔥",
    "notify.premium_granted": "🎁 Você ganhou Premium por {months} mês(es)! Aproveite 💎",
    "notify.premium_revoked": "ℹ️ Sua assinatura Premium foi desativada por um administrador.",
    "notify.banned": "🚫 Sua conta foi bloqueada. Se for um engano, contate o suporte.",
    "notify.unbanned": "✅ Sua conta foi desbloqueada. Você pode usar o bot novamente.",
    "contact.saved": "✅ Obrigado! Seu número de telefone foi salvo.",
    "btn.open_app": "🚀 Abrir o app",
    "voice.on": "🔊 Voz: ON",
    "voice.off": "🔇 Voz: OFF",
    "throttle.flood": "⏳ Muitas solicitações. Aguarde um momento.",
    "srv.photoeffects": "🎨 Efeitos de foto",
    "srv.videoeffects": "🎬 Efeitos de vídeo",
    "srv.avatar": "👤 Pacote de avatares",
    "srv.faceswap": "🔄 Troca de rosto",
    "srv.upscale": "📐 Ampliar X2/X4",
    "pack.label.popular": "POPULAR",
    "pack.label.best": "MELHOR ESCOLHA",
    "product.premium": "Premium",
    "product.premium_x2": "Premium X2",
    "pack.name.image": "Pacote de imagens",
    "pack.name.video": "Pacote de vídeo",
    "pack.name.music": "Pacote de música",
    "duration.1": "1 mês",
    "duration.3": "3 meses",
    "duration.6": "6 meses",
    "duration.12": "1 ano",
    "pack.choose": "Escolha o pacote «{name}» 👇",
    # ----- VIP / loyalty (ТЗ §4) -----
    "btn.vip": "🏅 Níveis VIP",
    "account.vip": "🏅 Nível: {tier} · faltam {left} ⭐ para {next}",
    "account.vip_top": "🏅 Nível: {tier} (máximo)",
    "account.vip_none": "🏅 Faltam {left} ⭐ para o nível {next}",
    "vip.title": "🏅 Níveis VIP\nSeu total de compras: {spent} ⭐\n",
    "vip.row": "{mark} {name} — a partir de {min} ⭐ · +{daily}/dia, +{weekly}/sem",
    "vip.reached": "🎉 Parabéns! Você alcançou o nível VIP {tier}.\nAgora você tem +{daily} gerações/dia e +{weekly}/semana.",
    # ----- global sale (ТЗ §4) -----
    "sale.banner": "🔥 Promoção −{percent}%",
    "sale.ends_in": "⏳ termina em: {time}",
    "sale.left_dh": "{d}d {h}h",
    "sale.left_hm": "{h}h {m}m",
    "sale.left_m": "{m}m",
    "pay.sub_invoice_desc": "Assinatura: {title}",
    "pay.pack_invoice_desc": "Pacote de gerações: {title}",
    "pay.sub_activated": "✅ Assinatura «{title}» ativada! Obrigado pela compra 🚀",
    "pay.pack_added": "✅ Pacote recarregado: +{qty} {unit} ({pack}). Obrigado pela compra!",
    "pay.avatar_paid": "✅ Pago! Envie sua melhor selfie — vou criar 100 avatares (~15 min).",
    "pay.link": "Abra o link para pagar. O acesso é ativado automaticamente após o pagamento 👇",
    "pay.link_btn": "💳 Pagar — {title}",
    "pay.unavailable": "Esta forma de pagamento está indisponível agora.",
    "pay.failed": "Não foi possível criar a fatura. Tente outra forma.",
    "gen.video_started": "🎬 Geração de vídeo iniciada! Vai levar alguns minutos — enviarei o resultado quando estiver pronto.",
    "gen.music_started": "🎶 Gerando sua música — enviarei o áudio quando estiver pronto!",
    "gen.photo_started": "🎨 Aplicando «{name}» — enviarei o vídeo quando estiver pronto!",
    "gen.unavailable": "⚠️ Serviço temporariamente indisponível. Tente mais tarde.",
    "gen.unavailable_refund": "⚠️ Serviço temporariamente indisponível. Créditos devolvidos.",
    "gen.error_refund": "⚠️ Erro de geração. Créditos devolvidos.",
    "mod.blocked": "🚫 A solicitação viola as regras de uso.",
    "seed.ask": "Insira um seed para a geração (valor numérico):",
    "seed.saved": "✅ Seed salvo.",
    "avatar.info": (
        "👤 Avatares com IA\n\nCrie 100 avatares legais para redes sociais em estilos diferentes.\n"
        "Preço: {price} ⭐ por pacote. Resolução 1024×1440, sem marca d'água.\n"
        "Após o pagamento, envie sua melhor selfie — geração ~15 minutos."
    ),
    "avatar.title": "Pacote de avatares",
    "avatar.buy_btn": "Comprar por {price} ⭐",
    "avatar.started": (
        "🎨 Geração de 100 avatares iniciada! Vai levar ~15 minutos — você pode "
        "continuar usando o bot, enviarei o resultado quando estiver pronto."
    ),
    "music.prompt": "🎵 {name}: envie uma descrição da música (estilo, clima, letra).",
    "kling.effects_intro": (
        "🌊 Kling Effects\n\n1. Escolha um efeito entre as opções abaixo.\n"
        "2. Envie uma foto ao bot para aplicar o efeito escolhido."
    ),
    "kling.effect_selected": "Efeito: {name}\n\nEnvie uma foto e o bot aplicará o efeito escolhido!",
    "kling.motion_intro": (
        "💃 Kling Motion\n\nSua foto ganhará vida e repetirá o movimento de um vídeo de exemplo.\n"
        "Escolha um modelo 👇"
    ),
    "kling.motion_selected": "Movimento: 💃 {name}. Envie uma foto — o Kling Motion transferirá o movimento para ela.",
    "btn.voice": "🔊",
    "btn.view": "🔥 Ver",
    "deletecontext.done": "Contexto apagado. Por padrão o bot considera sua pergunta anterior e a resposta dela.",
    "music.paywall": "🎵 Para gerar músicas, compre um pacote de música. Toque em «Recarregar» 👇",
    "gate.subscription": "Para continuar usando o bot de graça, inscreva-se no nosso canal 👇\nDepois toque em «Eu me inscrevi».",
    "gate.subscription.ok": "✅ Obrigado por se inscrever! Pode continuar.",
    "gate.subscription.fail": "❌ Parece que você ainda não se inscreveu.",
    "settings.role.prompt": "Envie o papel (prompt de sistema) que a IA deve seguir.",
    "settings.role.current_none": "Papel atual: não definido.",
    "settings.role.current": "Papel atual:\n{role}",
    "settings.role.saved": "✅ Papel salvo.",
    "settings.role.cleared": "Papel removido.",
    "settings.role.too_long": "❌ Papel muito longo (máx. {limit} caracteres). Encurte e envie novamente.",
    "settings.voice.intro": "Escolha uma voz para respostas faladas (disponível no /premium):",
    "settings.voice.preview": "Ouvir a voz selecionada",
    "settings.intro": (
        "⚙️ Configurações do bot\n\nAqui você ajusta a IA para você 👇\n\n"
        "1️⃣ Escolher modelo — a rede que responde às suas solicitações.\n\n"
        "2️⃣ Definir papel — ex.: assistente, redator, programador, professor ou especialista.\n\n"
        "3️⃣ Contexto do diálogo — ative/desative. Ativo, o bot considera a resposta anterior.\n\n"
        "4️⃣ Respostas em voz — configure a narração e escolha a voz. Disponível no /premium.\n\n"
        "5️⃣ Idioma da interface — escolha um idioma confortável.\n\n"
        "Escolha uma opção abaixo 👇"
    ),
    "model.intro": (
        "🤖 Escolher modelo de IA\n\nModelos líderes para texto, código, análise e tarefas complexas.\n\n"
        "Escolha um modelo abaixo 👇\n\n"
        "💬 GPT-5.5 — modelo top da OpenAI. Consome 3 gerações por solicitação.\n\n"
        "💬 GPT-5.4 — modelo versátil para código e textos.\n\n"
        "💬 GPT-5 mini — modelo rápido para o dia a dia. Grátis.\n\n"
        "🌥 Claude 4.8 Opus — modelo top da Anthropic. Consome 5 gerações por solicitação.\n\n"
        "🌥 Claude 4.6 Sonnet — forte em textos, código e matemática.\n\n"
        "🐳 DeepSeek V4 — rápido e potente. Grátis.\n\n"
        "🐳 DeepSeek V4 Pro — versão avançada do DeepSeek.\n\n"
        "♊️ Gemini 3.5 Flash — modelo top do Google.\n\n"
        "♊️ Gemini 3.1 Flash — modelo rápido e inteligente do Google. Grátis.\n\n"
        "📌 Documentos: no Premium você envia arquivos até 10 MB. Consome 3 gerações.\n\n"
        "🎁 Grátis: GPT-5 mini, Gemini 3.1 Flash, DeepSeek V4\n💎 Outros modelos no Premium: /premium\n\n"
        "Escolha um modelo abaixo 👇"
    ),
    "help": (
        "📚 Ajuda do bot\n\nComandos e recursos principais.\n\n"
        "📝 Geração de texto\nEscreva sua solicitação no chat. Usuários /premium também podem enviar mensagens de voz.\n\n"
        "Comandos:\n└ /deletecontext — novo diálogo\n└ /s — busca na internet\n"
        "└ /settings — modelo, papel, idioma e contexto\n└ /model — escolher modelo\n\n"
        "💡 Quanto mais detalhes, melhor a resposta.\n\n"
        "📄 Documentos (Premium)\nEnvie um arquivo até 10 MB e pergunte sobre ele.\nFormatos: docx, pdf, xlsx, xls, csv, pptx, txt.\nCada solicitação consome 3 gerações.\n\n"
        "🌅 Imagens\n└ Nano Banana 2 / Pro\n└ GPT Image 2\n└ Midjourney\n└ Flux\n└ Seedream\n└ Recraft\nComandos: /photo, /midjourney\n\n"
        "🎬 Vídeo\n└ Kling\n└ Seedance 2.0\n└ Pika\n└ Veo 3.1\n└ Hailuo\n└ Grok Imagine\nComando: /video\n\n"
        "🎸 Música\n└ Suno V5.5\n└ Lyria 3 Pro\nComandos: /music, /suno\n\n"
        "⚙️ Outros\n└ /start\n└ /account\n└ /premium\n└ /privacy\n\n"
        "💬 Dúvidas: {support}"
    ),
    "privacy": (
        "🔐 Documentos legais\n\nAntes de usar o bot, leia as regras e o tratamento de dados:\n\n"
        "1️⃣ Termos de uso\n2️⃣ Política de privacidade\n\n"
        "Ao continuar usando o bot, você confirma que os leu e aceita."
    ),
    "premium": (
        "🚀 Planos e recursos\n\nO bot reúne serviços de IA populares: texto, busca, imagens, vídeo, música e arquivos.\n\n"
        "🎁 GRÁTIS | toda semana\n\n100 solicitações:\n✅ GPT-5 mini\n✅ DeepSeek V4\n✅ Gemini 3.1 Flash\n✅ Perplexity\n✅ Reconhecimento de imagens\n\n"
        "25 gerações de imagens:\n♊️ Nano Banana 2\n✅ GPT Image 2\n\n"
        "💎 PREMIUM | 1 mês\n\nLimite: 100 solicitações/dia\n\n✅ Tudo do plano grátis\n✅ GPT-5.5\n✅ Gemini 3.5 Flash\n✅ Claude 4.8 Opus e Sonnet\n✅ DeepSeek\n♊️ Nano Banana Pro\n✅ GPT Image 2\n✅ Documentos\n✅ Respostas em voz\n✅ Sem anúncios\n\nPreço: {p_premium}⭐️\n\n"
        "💎 PREMIUM X2 | 1 mês\n\nLimite: 200 solicitações/dia\n\n✅ Tudo do Premium\n✅ Limite diário maior\n\nPreço: {p_premium_x2}⭐️\n\n"
        "🌅 IMAGENS | pacote\n\nDe 50 a 500 gerações à escolha\n\nServiços disponíveis:\n"
        "🌅 Midjourney\n🎬 Midjourney Video\n🌱 Seedream\n🎨 Recraft\n⚡ Flux\n✅ Troca de rosto em fotos\n\nPreço: a partir de {p_image_from}⭐️\n\n"
        "🎬 VÍDEO | pacote\n\nDe 2 a 50 gerações à escolha\n\nServiços disponíveis:\n"
        "📼 Kling\n🎥 Veo 3.1\n🚀 Seedance 2.0\n❎ Grok Imagine\n🎞 Hailuo\n✨ Pika\n\n"
        "Além disso:\n✅ Edição de vídeo\n✅ Efeitos de vídeo criativos\n\nPreço: a partir de {p_video_from}⭐️\n\n"
        "🎸 MÚSICA | pacote\n\nDe 20 a 100 gerações à escolha\n\nServiços disponíveis:\n"
        "🎸 Suno V5.5\n🎼 Lyria 3 Pro\n\nPossibilidades:\n✅ Canções com sua própria letra\n✅ Geração da letra com IA\n\nPreço: a partir de {p_music_from}⭐️\n\n"
        "⭐️ Todos os preços em Stars — a moeda do Telegram.\n\n💬 Pagamentos e acesso:\n{support}"
    ),
    "gate.channel": "Para continuar usando o bot gratuitamente, inscreva-se nos canais abaixo.\n\nGracas as inscricoes voce recebe 100 solicitacoes gratis por semana para ChatGPT, DeepSeek, Gemini, Perplexity, geradores de imagens e mais.\n\nQuer tudo sem anuncios? Toque em Premium.",
    "gate.btn_subscribe": "Inscrever-se em {channel}",
    "gate.btn_check": "Verificar inscricao",
    "gate.btn_premium": "Premium",
    "gate.ok": "Obrigado por se inscrever! Voce pode continuar.",
    "gate.not_subscribed": "Voce ainda nao esta inscrito em todos os canais.",
    "gate.premium_voice": "Para enviar solicitacoes de voz, obtenha uma assinatura /premium.",
    "faceswap.step1": "[Passo 1/2] Envie a imagem onde o rosto sera alterado.",
    "faceswap.step2": "[Passo 2/2] Agora envie a foto com o rosto doador.",
    "upscale.intro": "Esta ferramenta aumenta a resolucao da imagem. Escolha um fator.",
    "upscale.x2": "Aumentar X2",
    "upscale.x4": "Aumentar X4",
    "upscale.send_image": "Envie uma imagem (max 1024x1024). Serao cobradas {cost} geracoes.",
    "vision.coming_soon": "O reconhecimento de imagens estara disponivel em breve.",
    "vision.failed": "Nao foi possivel processar a imagem. Tente novamente.",
    "photo.choose": "O que fazer com esta foto?",
    "photo.btn_describe": "🔎 Descrever",
    "photo.btn_edit": "🎨 Editar pela legenda",
    "photo.edit_working": "🎨 Editando a foto…",
    "photo.edit_done": "✅ Pronto!",
    "photo.edit_unavailable": "🛠 A edicao de fotos chega em breve.",
    "photo.edit_failed": "Nao foi possivel editar a foto. Tente novamente.",
    "photo.edit_no_caption": "Adicione uma legenda descrevendo a edicao e eu mudarei a imagem.",
    "voice_in.coming_soon": "A entrada de voz estara disponivel em breve.",
    "voice_in.heard": "🎙 Reconhecido: «{text}»",
    "voice_in.empty": "Nao foi possivel reconhecer a fala. Tente gravar novamente.",
    "voice_in.failed": "Nao foi possivel processar a mensagem de voz. Tente novamente.",
    "gen.image_started": "Solicitacao recebida! Enviarei o resultado quando estiver pronto.",
    "pay.credits_added": "✨ {qty} créditos adicionados! Use-os no Mini App.",
    "img.more": "🔄 Outra",
    "img.upscale": "🔍 Aumentar",
    "img.file": "📎 Qualidade total",
    "img.no_prompt": "Primeiro escolha um servico e envie um prompt.",
    "promo.usage": "Uso: /promo CÓDIGO",
    "promo.invalid": "❌ Este código promocional é inválido ou expirou.",
    "promo.already": "Você já resgatou este código promocional.",
    "promo.ok": "✅ Código promocional resgatado: +{amount} {reward}.",
    "promo.not_eligible": "❌ Este código promocional é apenas para novos usuários.",
    # --- bot UI strings (handlers sweep) ---
    "fb.thanks": "Obrigado pela avaliação!",
    "report.usage": "Uso: <code>/report descrição do problema</code>",
    "report.thanks": "Obrigado! Sua denúncia foi recebida.",
    "roles.btn_off": "🚫 Desativar papel",
    "roles.btn_custom": "✍️ Papel próprio",
    "roles.unavailable": "Os papéis predefinidos estão indisponíveis no momento.",
    "roles.choose": "🎭 Escolha um papel predefinido para o assistente.",
    "roles.choose_active": "\n\nUm papel personalizado está ativo — escolha outro ou desative.",
    "roles.not_found": "Papel não encontrado",
    "roles.enabled": "Papel «{title}» ativado ✅",
    "roles.enabled_full": "Pronto — o assistente agora atua como «{title}». Para desativar, envie /roles → «Desativar papel».",
    "roles.disabled": "Papel desativado",
    "roles.disabled_full": "Papel do assistente desativado — modo normal.",
    "contest.none": "Nenhum concurso ativo no momento. Volte mais tarde!",
    "contest.entrants": "Participantes: {count}",
    "contest.btn_enter": "Participar",
    "contest.ended": "Este concurso já terminou.",
    "contest.entered": "Você está participando do concurso! Boa sorte! 🍀",
    "contest.already": "Você já está participando deste concurso.",
    "gift.btn_premium": "🎁 Premium · 1 mês",
    "gift.btn_pack": "🎁 Pacote de imagens · 50",
    "gift.btn_sub": "🎁 Presentear assinatura",
    "gift.btn_pack_menu": "📦 Presentear pacote",
    "gift.pack_none": "Pacotes indisponíveis no momento.",
    "gift.choose": "🎁 Presenteie um amigo com uma assinatura ou pacote.\nEscolha o que presentear:",
    "gift.invoice_title_sub": "🎁 {product} · {value} mês(es)",
    "gift.invoice_desc": "Presente: {title}",
    "gift.paid": "🎁 Presente pago!\n\nCódigo: <code>{code}</code>\n\nEnvie ao seu amigo o comando <code>/redeem {code}</code> ou este link:\n{link}",
    "redeem.usage": "Uso: <code>/redeem CÓDIGO</code>",
    "inline.hint_title": "Digite uma pergunta…",
    "inline.hint_text": "Digite uma pergunta após o nome do bot para obter uma resposta da IA.",
    "inline.error_title": "Erro",
    "inline.error_text": "Não foi possível obter uma resposta. Tente novamente mais tarde.",
    "inline.throttle_title": "Muito frequente",
    "inline.throttle_text": "Muitas solicitações seguidas. Aguarde um momento e tente novamente.",
    "support.usage": "Uso: <code>/support sua pergunta</code>\nDescreva o problema — sua mensagem chegará ao suporte.",
    "support.sent": "Mensagem enviada ao suporte, responderemos em breve.",
    "pay.precheckout_unavailable": "Pagamento indisponível",
    "pay.activate_failed": "⚠️ Não foi possível ativar a compra. Seu pagamento (⭐) foi reembolsado. Tente novamente ou contate o suporte.",
    "invite.summary": "🔗 Seu link de indicação:\n{link}\n\n👥 Usuários convidados: {count}\n✨ Recompensa por indicação: {reward}\n💰 Total ganho: ✨ {earned}",
    "links.none": "Nenhum link configurado ainda.",
    "links.title": "Links úteis:",
    "avatar.invoice_desc": "100 avatares de IA 1024×1440",
    "promo.reward.credits": "créditos",
    "promo.reward.image": "imagens",
    "promo.reward.video": "vídeos",
    "promo.reward.music": "faixas",
    "promo.reward.premium": "dias de Premium",
    "pay.success": "✅ Pagamento aprovado! Seu acesso foi ativado. Obrigado pela compra 🚀",
    "gen.video_ready": "✅ Seu vídeo está pronto!",
    "gen.song_ready": "✅ Sua música está pronta!",
    "gen.photo_ready": "✅ Sua foto está pronta!",
    "gen.avatar_unavailable_refund": "⚠️ O serviço «Avatares» está temporariamente indisponível. Seu pagamento (⭐) foi totalmente reembolsado ao seu saldo do Telegram. Desculpe!",
    "spec.desc.gpt_image2": "Crie e edite imagens direto no chat.\n\nPronto para começar?\nEnvie de 1 a 4 imagens que deseja editar, ou escreva o que quer criar.",
    "spec.desc.nano_banana": "Gemini Images — Mais vivo. Mais inteligente!\n\nCrie e edite imagens no chat. Envie de 1 a 10 imagens ou escreva o que quer criar.",
    "spec.desc.seedream": "Crie e edite imagens no chat. Envie de 1 a 10 imagens ou escreva o que quer criar.",
    "spec.desc.midjourney": "Escreva qual imagem você quer criar.\n\nO bot suporta todos os principais parâmetros e recursos do Midjourney.",
    "spec.desc.flux2": "Escolha a proporção e o modelo Flux. Os modelos Flex e Max custam 2 gerações.\n\nPara iniciar, escreva qual imagem você quer criar 🐝",
    "spec.desc.recraft": "Recraft — gráficos vetoriais e design. Escreva qual imagem você quer criar.",
    "spec.desc.seedance": "Geração de vídeo a partir de texto, imagens, vídeo e áudio.\n\nAjuste as opções e envie um prompt para iniciar ⚡",
    "spec.desc.veo": "Veo 3.1 — vídeo cinematográfico do Google. Envie um prompt ⚡",
    "spec.desc.grok": "Criação e edição de vídeo. O editor custa 2 gerações.\n+18, violência e deepfakes são proibidos. Envie um prompt ⚡",
    "spec.desc.kling_ai": "Criação e edição de vídeo. Envie um prompt ⚡",
    "spec.desc.hailuo": "Hailuo — vídeo a partir de uma descrição e uma imagem. Envie um prompt ⚡",
    "spec.desc.pika": "Pika Labs — vídeo a partir de uma descrição e imagens. Envie um prompt ⚡",
    "spec.desc.mj_video": "Midjourney Video — animação de imagens. Envie uma foto e/ou um prompt ⚡\nDebitado do pacote de imagens.",
    "spec.mode.create": "Criar",
    "spec.mode.edit": "Editor",
    "gen.ready_generic": "✅ Sua geração ({service}) está pronta.",
    "refund.stars": "⚠️ Não foi possível concluir o pedido. O pagamento (⭐) foi devolvido ao seu saldo do Telegram. Pedimos desculpas!",
    "notify.premium_expiry": "⏳ Seu Premium expira em {days} dia(s). Renove sua assinatura para não perder seus limites ampliados.",
    "notify.low_balance": "✨ Seu saldo está quase no fim — restam {balance} ✨. Recarregue para continuar gerando sem pausas.",
    "notify.winback": "👋 Faz tempo que não aparece! Volte — temos novos modelos e efeitos. Envie um pedido e vamos continuar 🙌",
    "notify.bonus_available": "🎁 Seu bônus diário está pronto! Resgate-o hoje para manter sua sequência e ganhar mais ✨.",
    "notify.btn.renew": "⭐ Renovar Premium",
    "notify.btn.topup": "✨ Recarregar",
    "notify.btn.open": "🚀 Ver planos",
    "notify.btn.bonus": "🎁 Resgatar bônus",
    "notify.abandoned_cart": "🛒 Você estava a um passo da sua compra! Conclua — leva um minuto.",
    "notify.btn.cart": "🛒 Concluir compra",
    "ref.earned_register": "🎉 Um novo usuário se cadastrou pelo seu link de indicação! Você ganhou ✨ {amount}.",
    "ref.welcome_bonus": "🎁 Bônus de boas-vindas por entrar via link de indicação: +✨ {amount}!",
    "promo.welcome_bonus": "🎁 Bônus de boas-vindas para novo usuário: +✨ {amount}!",
    "promo.purchase_bonus": "🎁 Bônus por compra: +✨ {amount}!",
    "promo.applied": "🏷 Cupom aplicado: −{percent}% na sua próxima compra!",
    "promo.applied_banner": "🏷 Promo −{percent}% aplicado",
    "ad.remove_btn": "⭐ Remover anúncios",
    "ref.milestone": "🏆 Você convidou {count} usuários! Bônus: +✨ {amount}.",
    "ref.earned_purchase": "🎉 Uma compra foi feita pelo seu link de indicação! Você ganhou ✨ {amount}.",
    "contest.won": "🎉 Parabéns! Você ganhou o sorteio!",
    "contest.won_credits": "🎉 Parabéns! Você ganhou o sorteio — recebeu ✨ {amount}!",
    "contest.won_pack": "🎉 Parabéns! Você ganhou o sorteio — recebeu {amount} {unit}!",
    "gift.not_found": "❌ Nenhum presente encontrado com esse código.",
    "gift.already_used": "❌ Este presente já foi ativado.",
    "gift.own_gift": "🎁 Você não pode ativar seu próprio presente — compartilhe com um amigo.",
    "gift.redeemed_sub": "🎁 Presente ativado: {product} por {months} mês(es).",
    "gift.redeemed_pack": "🎁 Presente ativado: pacote {product} (+{qty}).",
    "gift.redeemed_credits": "🎁 Presente ativado: +{qty} ✨.",
    "gift.unknown_kind": "❌ Tipo de presente desconhecido.",
}
