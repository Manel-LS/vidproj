"""Placeholder on-screen copy, per language.

The built-in planner runs whenever no LLM is configured — which is the default
state, and the state most users are in. It used to write English regardless of
the project's language, so a French or derja project came back with "Built to
last" over its images. Structurally correct, unusable as it stood.

These lines are **placeholders the user is expected to edit**, not finished
copywriting. That is why the tables are grouped by tone rather than reproducing
every style in every language: inventing distinct marketing registers for ten
styles across four languages would be unmaintainable, and pretending to a
nuance I cannot verify in each language would be worse than an honest default.
An LLM, when configured, replaces all of this.
"""
from __future__ import annotations

from app.domain.enums import Language, VideoStyle

#: Styles collapse into these tones. Within a tone the copy is interchangeable.
_TONE_OF_STYLE: dict[VideoStyle, str] = {
    VideoStyle.PRODUCT_SHOWCASE: "promo",
    VideoStyle.MINIMAL: "promo",
    VideoStyle.LUXURY: "promo",
    VideoStyle.CUSTOM: "promo",
    VideoStyle.SALE: "sale",
    VideoStyle.TIKTOK_TREND: "trend",
    VideoStyle.STORYTELLING: "story",
    VideoStyle.REAL_ESTATE: "place",
    VideoStyle.FOOD: "food",
    VideoStyle.EDUCATIONAL: "teach",
}

#: language -> tone -> (hooks, beats, cta)
_COPY: dict[Language, dict[str, tuple[tuple[str, ...], tuple[str, ...], str]]] = {
    Language.FRENCH: {
        "promo": (
            ("Voici {subject}", "{subject}, de près", "Découvrez {subject}"),
            ("Fait pour durer", "Chaque détail compte", "Pensé pour tous les jours", "Avec soin"),
            "Découvrir la collection",
        ),
        "sale": (
            ("{subject} en promo", "À ne pas manquer", "Offre limitée : {subject}"),
            ("Stock limité", "Aujourd'hui seulement", "Tant qu'il y en a", "Meilleur prix"),
            "J'en profite",
        ),
        "trend": (
            ("Attends la fin...", "Il faut que tu voies {subject}", "POV : tu trouves {subject}"),
            ("Sérieux ?", "Regarde ça", "Et ça continue", "Et voilà"),
            "Suis-nous",
        ),
        "story": (
            ("Tout a commencé avec {subject}", "Une histoire : {subject}", "{subject}"),
            ("Puis il s'est passé ça", "Le tournant", "Et ensuite", "Enfin"),
            "La suite en commentaire",
        ),
        "place": (
            ("Entrez dans {subject}", "Bienvenue à {subject}", "{subject} — la visite"),
            ("Beaucoup de lumière", "Cuisine ouverte", "De l'espace", "Prêt à habiter"),
            "Réserver une visite",
        ),
        "food": (
            ("Ça donne faim ?", "{subject}, du jour", "Voici {subject}"),
            ("Frais chaque matin", "Préparé à la commande", "Tout juste sorti du four", "Ça se goûte"),
            "Commander",
        ),
        "teach": (
            ("{subject} : l'essentiel", "3 choses sur {subject}", "{subject}, expliqué"),
            ("1. On commence ici", "2. Ensuite ceci", "3. À retenir", "4. Et c'est tout"),
            "Enregistre pour plus tard",
        ),
    },
    Language.ARABIC: {
        "promo": (
            ("هذا هو {subject}", "{subject} عن قرب", "اكتشف {subject}"),
            ("صُنع ليدوم", "كل تفصيل مدروس", "للاستعمال اليومي", "بعناية"),
            "اكتشف المجموعة",
        ),
        "sale": (
            ("{subject} بسعر مخفّض", "لا تفوّت الفرصة", "عرض محدود: {subject}"),
            ("الكمية محدودة", "اليوم فقط", "ما دامت الكمية", "أفضل سعر"),
            "اطلب الآن",
        ),
        "trend": (
            ("انتظر النهاية...", "لازم تشوف {subject}", "تخيّل أنك لقيت {subject}"),
            ("مستحيل!", "شوف هذا", "وفي الأحسن", "وهكذا"),
            "تابعنا",
        ),
        "story": (
            ("بدأت القصة مع {subject}", "قصة قصيرة عن {subject}", "{subject}"),
            ("ثم حدث هذا", "نقطة التحوّل", "وبعدها", "وأخيرًا"),
            "التكملة في التعليقات",
        ),
        "place": (
            ("ادخل إلى {subject}", "أهلًا بك في {subject}", "{subject} — جولة"),
            ("إضاءة طبيعية", "مطبخ مفتوح", "مساحة واسعة", "جاهز للسكن"),
            "احجز زيارة",
        ),
        "food": (
            ("جعت؟", "{subject} طازج اليوم", "هذا هو {subject}"),
            ("طازج كل صباح", "يُحضّر عند الطلب", "من الفرن مباشرة", "الطعم يحكي"),
            "اطلب الآن",
        ),
        "teach": (
            ("{subject}: ما يجب معرفته", "٣ أشياء عن {subject}", "{subject} ببساطة"),
            ("١. ابدأ من هنا", "٢. ثم هذا", "٣. تذكّر هذا", "٤. وهذا كل شيء"),
            "احفظ المنشور",
        ),
    },
    Language.TUNISIAN: {
        "promo": (
            ("هاو {subject}", "{subject} من قريب", "شوف {subject}"),
            ("يدوم برشا", "كل تفصيلة محسوبة", "يخدم كل نهار", "بالعناية"),
            "شوف الكولكسيون",
        ),
        "sale": (
            ("{subject} بروموسيون", "ما تفوّتهاش", "عرض محدود: {subject}"),
            ("الكمية قليلة", "اليوم برك", "ما دام موجود", "أحسن ثمن"),
            "اطلب توّا",
        ),
        "trend": (
            ("استنّى الآخر...", "لازمك تشوف {subject}", "تصوّر لقيت {subject}"),
            ("ما يتصدّقش", "شوف هكّا", "وزيد", "وهاو"),
            "تبّعنا",
        ),
        "story": (
            ("بدات مع {subject}", "قصة صغيرة على {subject}", "{subject}"),
            ("وبعدها صار هكّا", "هوني تبدّل كل شي", "وبعد", "وفي الآخر"),
            "الكمالة في الكومنتار",
        ),
        "place": (
            ("أدخل لـ {subject}", "مرحبا بيك في {subject}", "{subject} — جولة"),
            ("ضوء برشا", "كوزينة مفتوحة", "بلاصة واسعة", "جاهز للسكنى"),
            "احجز زيارة",
        ),
        "food": (
            ("جعت؟", "{subject} طازج اليوم", "هاو {subject}"),
            ("طازج كل صباح", "يتحضّر ساعتها", "توّا خارج من الفرن", "الذوق يحكي"),
            "اطلب توّا",
        ),
        "teach": (
            ("{subject}: اللي لازم تعرفو", "٣ حاجات على {subject}", "{subject} بالساهل"),
            ("١. ابدا من هوني", "٢. وبعدها هكّا", "٣. اتفكّر هذا", "٤. وهذاكا الكل"),
            "سجّلها للبعد",
        ),
    },
}

#: Hashtags per language. The subject's own words are prepended by the caller.
_HASHTAGS: dict[Language, dict[str, list[str]]] = {
    Language.FRENCH: {
        "promo": ["produit", "nouveaute", "boutique"],
        "sale": ["promo", "soldes", "bonplan"],
        "trend": ["pourtoi", "fyp", "viral"],
        "story": ["histoire", "coulisses", "marque"],
        "place": ["immobilier", "visite", "maison"],
        "food": ["food", "gourmand", "miam"],
        "teach": ["astuce", "conseil", "apprendre"],
    },
    Language.ARABIC: {
        "promo": ["منتج", "جديد", "متجر"],
        "sale": ["تخفيضات", "عرض", "خصم"],
        "trend": ["اكسبلور", "فوريو", "ترند"],
        "story": ["قصة", "كواليس", "حكاية"],
        "place": ["عقارات", "جولة", "منزل"],
        "food": ["طعام", "أكل", "لذيذ"],
        "teach": ["نصيحة", "معلومة", "تعلم"],
    },
    Language.TUNISIAN: {
        "promo": ["تونس", "جديد", "بوتيك"],
        "sale": ["بروموسيون", "تخفيضات", "عرض"],
        "trend": ["اكسبلور", "تونس", "ترند"],
        "story": ["حكاية", "قصة", "تونس"],
        "place": ["عقارات", "تونس", "دار"],
        "food": ["ماكلة", "تونس", "بنين"],
        "teach": ["نصيحة", "معلومة", "تونس"],
    },
}


def tone_of(style: VideoStyle) -> str:
    return _TONE_OF_STYLE.get(style, "promo")


def has_copy(language: Language | str) -> bool:
    """False for English, which keeps the richer per-style tables in `planner`."""
    try:
        return Language(language) in _COPY
    except ValueError:
        return False


def hooks(language: Language | str, style: VideoStyle) -> tuple[str, ...]:
    return _COPY[Language(language)][tone_of(style)][0]


def beats(language: Language | str, style: VideoStyle) -> tuple[str, ...]:
    return _COPY[Language(language)][tone_of(style)][1]


def cta(language: Language | str, style: VideoStyle) -> str:
    return _COPY[Language(language)][tone_of(style)][2]


def hashtags(language: Language | str, style: VideoStyle) -> list[str]:
    return list(_HASHTAGS[Language(language)][tone_of(style)])
