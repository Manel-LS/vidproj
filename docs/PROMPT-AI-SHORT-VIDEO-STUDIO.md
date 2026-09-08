# Prompt de travail — AI Short Video Studio

> Version réadaptée du cahier des charges « AI Short Video Studio » pour **ce dépôt**.
>
> Le cahier d'origine demandait Node / NestJS / Prisma / BullMQ / PostgreSQL. Ce projet
> tourne déjà, en production locale, sur **FastAPI / SQLAlchemy / MySQL / Alembic /
> FFmpeg** et **Next.js / React / TypeScript / Tailwind**, avec 182 tests au vert.
> Repartir sur Node jetterait un moteur de rendu FFmpeg fonctionnel, six abstractions
> de fournisseurs, la file de travaux, l'authentification et tout le rendu arabe RTL.
>
> Ce document remplace donc le prompt d'origine. Il garde **l'intention et toutes les
> règles dures**, et ne demande que ce qui manque réellement.

---

## 0. Rôle

Tu es ingénieur full-stack IA, ingénieur vidéo et concepteur produit.

Tu interviens sur une application **existante et fonctionnelle**. Ta tâche n'est pas de
la recréer : c'est de compléter la chaîne pour qu'elle produise le style de référence.

**Avant d'écrire une ligne, lis le dépôt.** `docs/ARCHITECTURE.md`, `docs/API.md`,
`backend/app/domain/plan.py` et `backend/app/infrastructure/` disent ce qui existe.

---

## 1. Le style de référence

Vidéo verticale TikTok / Reels / Shorts, **1080 × 1920, 9:16** :

- enfant / personnage IA réaliste et attachant, atmosphère tunisienne / nord-africaine,
  vêtements traditionnels ;
- éclairage chaud cinématographique, environnement réaliste, figurants en mouvement
  naturel à l'arrière-plan ;
- personnage face caméra qui **parle** : expressions, mouvements de tête et de mains ;
- voix IA, **synchronisation labiale**, musique de fond, sous-titres ;
- **MP4 final prêt à publier**.

Exemple d'entrée utilisateur :

> « Un petit bébé tunisien raconte une histoire drôle sur le mariage de son cousin. »

---

## 2. Ce qui existe déjà — NE PAS RECONSTRUIRE

Vérifié dans le dépôt. Chaque ligne renvoie au code réel.

| Brique | Où | État |
|---|---|---|
| Auth JWT, isolation par utilisateur, limites de débit | `app/api/v1/routes/auth.py`, `app/core/security.py` | ✅ |
| Projets, scènes, médias, pistes audio, voix, rendus, modèles | `app/models/entities.py` (8 tables) | ✅ |
| **Contrat de plan validé** (Pydantic strict) partagé UI ↔ API ↔ rendu | `app/domain/plan.py` | ✅ |
| **`LLMProvider`** — Anthropic, OpenAI, repli heuristique | `app/infrastructure/llm/` | ✅ |
| **`VoiceProvider`** — Edge (gratuit, 322 voix dont `ar-TN`), ElevenLabs, OpenAI | `app/infrastructure/tts/` | ✅ |
| **`ImageToVideoProvider`** — Runway, Luma, Kling | `app/infrastructure/i2v/` | ✅ |
| **`StorageProvider`** — local **et S3** | `app/infrastructure/storage/` | ✅ |
| **`JobQueue`** — fil in-process **et Celery/Redis** | `app/infrastructure/jobs/` | ✅ |
| **`RenderEngine`** — FFmpeg réel, 57 transitions, zoompan, mux audio | `app/infrastructure/render/` | ✅ |
| Sous-titres : rastérisation Pillow, **arabe RTL façonné**, polices par script | `app/infrastructure/imaging/` | ✅ |
| File de rendu non bloquante, progression, annulation, reprise après crash | `app/services/render_service.py` | ✅ |
| Matrice de capacités en direct (`GET /api/v1/capabilities`) | `app/api/v1/routes/capabilities.py` | ✅ |
| Tableau de bord, éditeur, timeline, aperçu | `frontend/src/app/` | ✅ |
| Modèles de vidéo | `app/services/template_service.py` | ✅ |
| Docker, README, `.env.example`, migrations Alembic, données de départ | racine | ✅ |
| **182 tests** (unitaires, API, rendu FFmpeg réel, RTL, AI Motion) | `backend/tests/` | ✅ |

**Conséquence :** les sections 11, 12, 13, 16, 17, 20, 21, 22, 23, 24, 26, 27 du cahier
d'origine sont déjà satisfaites. Ne les réécris pas. Étends-les.

---

## 3. Ce qui manque — le travail réel

Dans cet ordre. Chaque module se termine par des tests qui échouent sans lui.

### 3.1 ~~`ImageProvider` — texte → image~~ ✅ **livré**

`app/infrastructure/image/` : `ImageProvider` + `NullImageProvider`, adaptateurs
**OpenAI**, **Replicate** et **Google Imagen**, sélection par `IMAGE_PROVIDER`,
entrée `image` dans `GET /api/v1/capabilities`, route
`POST /api/v1/projects/{id}/scenes/{scene_id}/image` (asynchrone),
`app/services/image_worker.py`, colonne `scenes.image_prompt` (1 200 caractères) et sa
migration Alembic, `enqueue_image` sur les deux files. 10 tests.

Interface volontairement **synchrone** — une image prend des secondes là où une vidéo
prend des minutes ; les fournisseurs réellement asynchrones sondent en interne derrière
leur propre échéance. Ce qui est interdit, c'est de bloquer une requête HTTP : l'appel
part de la file, jamais d'une route.

L'image générée passe par le **même chemin qu'un téléversement** (`add_image`,
`source="ai_image"`) : optimisation, vignette, analyse, dimensions. Le planificateur et
le moteur de rendu lisent ces champs ; stocker les octets bruts aurait produit une scène
que le planificateur ne sait pas exploiter.

### 3.2 ~~Entité `Character`~~ ✅ **livré**

Table `characters` + `projects.character_id` (migration `c8d2f5a71b30`), service
`app/services/character_service.py`, CRUD `/api/v1/characters` isolé par utilisateur,
téléversement d'image de référence, `character_id` et `character_description` exposés
sur le projet. 13 tests.

La cohérence tient à **une seule règle** : `compose_description()` ne s'exécute qu'à la
création ou à l'édition d'un champ, et la phrase stockée est rejouée **mot pour mot** en
tête de chaque prompt image, précédée de « the same ». Recomposer à chaque génération —
même à partir des mêmes champs — dérive vers un autre enfant. Une description écrite à
la main l'emporte sur la phrase assemblée.

Le worker image préfère l'image de référence du personnage à toute autre : c'est la
seule qui traverse les projets. À défaut, il retombe sur la première image générée du
projet courant, ce qui garde au moins les scènes d'une même vidéo cohérentes entre elles.

Deux pièges rencontrés, tous deux corrigés et couverts : la description composée
commençait par un article, ce qui donnait « the same **an** adorable toddler » ; et les
trois tables forment un **cycle de clés étrangères** (characters → media → projects →
characters), qui laisse `create_all` sans ordre valide — déclaré par `use_alter=True`.

### 3.3 ~~`LipSyncProvider`~~ ✅ **livré**

`app/infrastructure/lipsync/` : `LipSyncProvider` + `NullLipSyncProvider`, adaptateurs
**Sync Labs**, **HeyGen** et **Replicate**, sélection par `LIPSYNC_PROVIDER`, entrée
`lipsync` dans les capacités, route
`POST /api/v1/projects/{id}/scenes/{scene_id}/lipsync`,
`app/services/lipsync_worker.py`, `enqueue_lipsync` sur les deux files, champs
`silent_media_id` / `lipsync_provider` / `lipsync_job_reference` sur `AiMotionSpec`.
13 tests.

**Le point qui fait la correction du module** : la voix est *un seul fichier pour toute
la vidéo*, chaque scène est un clip séparé. Transmettre la narration entière
synchroniserait chaque scène sur les mots de t=0 — six scènes fausses, et rien dans la
sortie ne le dirait. Le worker calcule donc la fenêtre de la scène depuis
`plan.scene_start_times()` et découpe l'audio avant l'envoi. La découpe **réencode** au
lieu de copier le flux : une copie coupe sur l'image-clé la plus proche, ce qui décale de
quelques dizaines de millisecondes — visible sur les lèvres.

Le clip muet n'est jamais détruit : `generated_media_id` passe au clip parlant,
`silent_media_id` garde l'original. Relancer repart donc du muet, sinon la deuxième passe
synchroniserait une bouche qui bouge déjà sur ces mots-là.

Sync Labs et HeyGen **téléchargent les médias eux-mêmes** : ils exigent `STORAGE_PROVIDER=s3`.
Le worker le dit explicitement au lieu d'échouer obscurément. Replicate accepte les envois
directs et fonctionne en stockage local.

### 3.4 ~~Champ `language`~~ ✅ **livré**

`Project.language` (`tn` | `ar` | `fr` | `en`, migration `d3f9a1c60e57`),
`app/domain/language.py` avec un profil par langue, `rtl` exposé sur le projet.

La langue se propage aux **trois** endroits où elle change quelque chose :
l'instruction du planificateur, le choix de la voix par défaut, et la direction des
sous-titres. La consigne est une **directive**, pas un nom de langue : à qui on donne
seulement « Tunisian Arabic », le modèle rédige en anglais puis traduit — et ça s'entend.

La derja n'est **pas** confondue avec l'arabe standard : registre différent, étiquettes
de voix différentes (`ar-TN` contre `ar-SA`), et un script en MSA lu par une voix MSA
sonne comme un journal télévisé — l'inverse de ce format.

`capabilities` dit la vérité **langue par langue** : `supported`, `exact`, la voix
retenue et une note quand seul un accent approchant existe. Substituer un accent du Golfe
à de la derja sans le dire est un défaut que l'utilisateur entend immédiatement.

### 3.5 ~~`PromptEngine`~~ ✅ **livré**

`app/services/prompt_engine.py` : `story_prompt`, `image_prompt`, `video_prompt`,
`voice_prompt`, plus `ShotBrief` et `MotionBrief`. 23 tests, aucun réseau.

**Déterministe** — mêmes entrées, même chaîne octet pour octet : c'est ce qui fait qu'une
scène régénérée reproduit le même plan au lieu d'en inventer un autre.

**Ordonné** — sujet, cadrage, environnement, lumière, caméra, puis les clauses
techniques. Les modèles d'image pondèrent davantage les premiers tokens.

Trois détails qui portent le résultat : la durée du script est exprimée en **mots
prononcés** (≈ 2,3 mots/seconde) parce qu'un modèle à qui l'on dit « 30 secondes » ne sait
pas les compter et dépasse de moitié ; « no morphing » est systématique, sans quoi les
modèles image→vidéo font fondre les visages entre images-clés ; et le mouvement est
énuméré **partie par partie** — un « bouge naturellement » donne une image figée ou un
visage qui dérive.

### 3.6 ~~Registre de travaux unifié~~ ✅ **livré**

Table `generation_jobs` (migration `e5b7c9d34f82`), `app/services/generation_job_service.py`,
routes `GET /projects/{id}/jobs`, `GET /jobs`, `GET /jobs/{id}`. Les **cinq** workers y
écrivent : image, vidéo, voix, lip-sync et rendu. 9 tests.

Le service **enregistre**, il ne pilote pas : chaque worker reste la source de vérité de
sa propre sortie. Et chaque fonction avale ses propres erreurs — un registre capable de
casser le travail qu'il décrit serait pire que pas de registre : perdre une ligne de
progression est une ligne manquante dans une liste, perdre une génération coûte de
l'argent. Un test le vérifie.

Le rendu est **reflété** plutôt que branché en dur : `_finish` est atteint depuis cinq
chemins, et une édition qui en oublie un laisse un travail bloqué à « processing » pour
toujours dans le tableau de bord.

Au démarrage, les lignes restées en `processing` après un crash sont passées en échec —
sinon l'éditeur les interrogerait indéfiniment.

**Test de bout en bout par l'API** : `scripts/smoke_api.py` pilote toute la chaîne en HTTP
(connexion, capacités, personnage, projet, images, plan, prompts, voix, motion, lip-sync,
rendu, registre) et distingue *échec* de *non configuré*. Dernier passage : 13 OK,
3 sautés faute de clé, 0 échec.

### 3.7 Sous-titres : surlignage mot à mot

Le système de calques existe et l'arabe est correctement façonné. Manque le style
« TikTok » : le mot en cours surligné. Nécessite un horodatage par mot — enveloppe
d'amplitude ou horodatages du fournisseur TTS quand il en fournit.

Styles à livrer : `clean`, `tiktok`, `bold`, `cinematic`, `minimal`.

### 3.8 `MusicProvider`

`GET /audio/library` renvoie volontairement une liste vide : **le produit ne distribue
aucune musique non licenciée**. Cette règle ne change pas. Branche soit un catalogue
sous licence, soit un générateur de musique — et laisse le téléversement utilisateur.

---

## 4. Règles dures — non négociables

1. **Ne jamais simuler une génération réussie.** Clé absente → état « Provider not
   configured », message clair, instructions de configuration. Jamais de faux résultat.
2. **Aucune clé d'API dans le frontend.** Tout appel fournisseur part du serveur.
3. **Aucun couplage à un fournisseur unique.** Interface d'abord, adaptateur ensuite,
   choix par variable d'environnement.
4. **Pas de logique métier dans les composants React. Pas de commandes FFmpeg dans les
   routes API.** Couches : UI → API → Services → Domaine → Infrastructure.
5. **Ne jamais bloquer une requête HTTP** sur une génération. Travail asynchrone,
   statut par sondage.
6. **Aucune musique sous droits embarquée.**
7. **Sécurité des contenus.** Les personnages enfants restent dans des contextes
   ordinaires et sûrs : famille, fêtes, histoires, humour, éducation. Rejeter tout prompt
   sexualisé ou d'exploitation, à la saisie **et** avant l'envoi au fournisseur.
8. **Ne pas committer de secrets.**
9. **Le personnage doit rester visuellement cohérent** d'une vidéo à l'autre.

---

## 5. Variables d'environnement

Existantes (voir `.env.example`) : `DATABASE_URL`, `REDIS_URL`, `JOB_QUEUE`,
`STORAGE_PROVIDER`, `S3_*`, `SECRET_KEY`, `LLM_PROVIDER`, `ANTHROPIC_API_KEY`,
`OPENAI_API_KEY`, `TTS_PROVIDER`, `EDGE_TTS_VOICE`, `ELEVENLABS_API_KEY`,
`I2V_PROVIDER`, `RUNWAY_API_KEY`, `KLING_ACCESS_KEY`, `KLING_SECRET_KEY`,
`LUMA_API_KEY`, `FFMPEG_BINARY`, `RENDER_*`.

À ajouter :

```
IMAGE_PROVIDER=none        # none | openai | replicate | google
OPENAI_IMAGE_MODEL=gpt-image-1
REPLICATE_API_TOKEN=
GOOGLE_API_KEY=

LIPSYNC_PROVIDER=none      # none | synclabs | heygen | replicate
SYNCLABS_API_KEY=
HEYGEN_API_KEY=

MUSIC_PROVIDER=none
```

Mets `.env.example` à jour dans le même commit que le code qui lit la variable.

---

## 6. Ordre de travail

1. `ImageProvider` + adaptateur OpenAI + `NullImageProvider` + capacités + tests
2. `Character` + CRUD + cohérence par description figée + tests
3. `PromptEngine` + tests déterministes
4. `Project.language` + propagation + migration Alembic
5. `LipSyncProvider` + insertion dans la chaîne + tests
6. `generation_jobs` + files + reprise + tests
7. Sous-titres mot à mot + les 5 styles
8. `MusicProvider`
9. Frontend : Character Studio, sélecteur de langue, styles de sous-titres, progression
   par étape

**Après chaque module : lance les tests, et regarde une image du résultat.** Sur ce
projet, les codes HTTP 200 ont menti trois fois — hydratation muette, arabe en tofu,
clip AI Motion silencieusement ignoré. Seul un contrôle visuel les a révélés.

---

## 7. Critères d'acceptation

Un utilisateur saisit :

> « Un bébé tunisien raconte pourquoi il ne veut pas aller au mariage. »

choisit derja / 30 s / réaliste, clique **Générer**, et obtient sans autre intervention :

- un script en derja qu'il peut modifier ;
- 6 images cohérentes du **même** personnage ;
- 6 clips animés ;
- une voix `ar-TN` synchronisée sur les lèvres ;
- des sous-titres arabes RTL ;
- un **MP4 1080 × 1920, H.264 / AAC**, téléchargeable.

Et si une clé manque : il voit **quel** fournisseur manque et **comment** le configurer —
jamais une fausse vidéo.
