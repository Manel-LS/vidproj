-- Reelcraft -- schema MySQL / MariaDB
-- Genere depuis les modeles SQLAlchemy (backend/app/models/entities.py)
-- via SQLAlchemy + Alembic (historique complet dans backend/alembic/versions/).
--
-- Utilisation (XAMPP / WAMP / phpMyAdmin) :
--   1. Executer ce fichier tel quel (il cree la base 'reelcraft').
--   2. Renseigner DATABASE_URL dans .env, ex :
--      DATABASE_URL=mysql+pymysql://root@127.0.0.1:3306/reelcraft
--   3. Marquer la base a jour cote Alembic (ne pas rejouer les migrations) :
--      alembic stamp head

CREATE DATABASE IF NOT EXISTS reelcraft
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE reelcraft;

SET FOREIGN_KEY_CHECKS=0;

-- users
CREATE TABLE users (
	email VARCHAR(320) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	full_name VARCHAR(120) NOT NULL, 
	is_active BOOL NOT NULL, 
	is_admin BOOL NOT NULL, 
	id VARCHAR(32) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	CONSTRAINT pk_users PRIMARY KEY (id)
);

-- brand_kits
CREATE TABLE brand_kits (
	user_id VARCHAR(32) NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	brand_name VARCHAR(120) NOT NULL, 
	slogan VARCHAR(200) NOT NULL, 
	primary_color VARCHAR(9) NOT NULL, 
	accent_color VARCHAR(9) NOT NULL, 
	background_color VARCHAR(9) NOT NULL, 
	font_family VARCHAR(16) NOT NULL, 
	logo_media_id VARCHAR(32), 
	logo_position VARCHAR(16) NOT NULL, 
	logo_scale FLOAT NOT NULL, 
	logo_opacity FLOAT NOT NULL, 
	id VARCHAR(32) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	CONSTRAINT pk_brand_kits PRIMARY KEY (id), 
	CONSTRAINT fk_brand_kits_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

-- characters
CREATE TABLE characters (
	user_id VARCHAR(32) NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	kind VARCHAR(16) NOT NULL, 
	age VARCHAR(60) NOT NULL, 
	gender VARCHAR(40) NOT NULL, 
	skin_tone VARCHAR(60) NOT NULL, 
	hair VARCHAR(120) NOT NULL, 
	clothes VARCHAR(300) NOT NULL, 
	headwear VARCHAR(160) NOT NULL, 
	expression VARCHAR(120) NOT NULL, 
	personality VARCHAR(200) NOT NULL, 
	environment VARCHAR(300) NOT NULL, 
	description VARCHAR(1200) NOT NULL, 
	reference_media_id VARCHAR(32), 
	id VARCHAR(32) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	CONSTRAINT pk_characters PRIMARY KEY (id), 
	CONSTRAINT fk_characters_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

-- templates
CREATE TABLE templates (
	`key` VARCHAR(64) NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	description TEXT NOT NULL, 
	category VARCHAR(64) NOT NULL, 
	style VARCHAR(32) NOT NULL, 
	format VARCHAR(16) NOT NULL, 
	recommended_duration FLOAT NOT NULL, 
	min_images INTEGER NOT NULL, 
	max_images INTEGER NOT NULL, 
	is_builtin BOOL NOT NULL, 
	user_id VARCHAR(32), 
	definition JSON NOT NULL, 
	id VARCHAR(32) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	CONSTRAINT pk_templates PRIMARY KEY (id), 
	CONSTRAINT uq_template_key_user UNIQUE (`key`, user_id), 
	CONSTRAINT fk_templates_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

-- projects
CREATE TABLE projects (
	user_id VARCHAR(32) NOT NULL, 
	name VARCHAR(160) NOT NULL, 
	description TEXT NOT NULL, 
	topic VARCHAR(300) NOT NULL, 
	platform VARCHAR(32) NOT NULL, 
	format VARCHAR(16) NOT NULL, 
	style VARCHAR(32) NOT NULL, 
	language VARCHAR(8) NOT NULL, 
	mode VARCHAR(16) NOT NULL, 
	fps INTEGER NOT NULL, 
	template_key VARCHAR(64), 
	subtitle_style VARCHAR(16) NOT NULL DEFAULT 'none', 
	character_id VARCHAR(32), 
	brand_kit_id VARCHAR(32), 
	target_duration FLOAT, 
	hook VARCHAR(300) NOT NULL, 
	cta VARCHAR(300) NOT NULL, 
	caption TEXT NOT NULL, 
	hashtags JSON NOT NULL, 
	plan_generated_by VARCHAR(32) NOT NULL, 
	plan_notes TEXT NOT NULL, 
	duration_seconds FLOAT NOT NULL, 
	thumbnail_media_id VARCHAR(32), 
	last_render_id VARCHAR(32), 
	id VARCHAR(32) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	CONSTRAINT pk_projects PRIMARY KEY (id), 
	CONSTRAINT fk_projects_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	CONSTRAINT fk_projects_character_id_characters FOREIGN KEY(character_id) REFERENCES characters (id) ON DELETE SET NULL
);

-- generation_jobs
CREATE TABLE generation_jobs (
	project_id VARCHAR(32) NOT NULL, 
	user_id VARCHAR(32) NOT NULL, 
	scene_id VARCHAR(32), 
	type VARCHAR(16) NOT NULL, 
	provider VARCHAR(32) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	progress INTEGER NOT NULL, 
	stage VARCHAR(80) NOT NULL, 
	error TEXT NOT NULL, 
	external_job_id VARCHAR(120) NOT NULL, 
	result_media_id VARCHAR(32), 
	started_at DATETIME, 
	completed_at DATETIME, 
	id VARCHAR(32) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	CONSTRAINT pk_generation_jobs PRIMARY KEY (id), 
	CONSTRAINT fk_generation_jobs_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE, 
	CONSTRAINT fk_generation_jobs_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

-- media
CREATE TABLE media (
	user_id VARCHAR(32) NOT NULL, 
	project_id VARCHAR(32), 
	kind VARCHAR(16) NOT NULL, 
	source VARCHAR(24) NOT NULL, 
	storage_key VARCHAR(512) NOT NULL, 
	thumbnail_key VARCHAR(512), 
	original_filename VARCHAR(255) NOT NULL, 
	content_type VARCHAR(120) NOT NULL, 
	size_bytes INTEGER NOT NULL, 
	width INTEGER, 
	height INTEGER, 
	duration_seconds FLOAT, 
	position INTEGER NOT NULL, 
	analysis JSON NOT NULL, 
	id VARCHAR(32) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	CONSTRAINT pk_media PRIMARY KEY (id), 
	CONSTRAINT fk_media_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	CONSTRAINT fk_media_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE
);

-- audio_tracks
CREATE TABLE audio_tracks (
	project_id VARCHAR(32) NOT NULL, 
	media_id VARCHAR(32), 
	volume FLOAT NOT NULL, 
	fade_in FLOAT NOT NULL, 
	fade_out FLOAT NOT NULL, 
	start_offset FLOAT NOT NULL, 
	`loop` BOOL NOT NULL, 
	library_track_key VARCHAR(64), 
	id VARCHAR(32) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	CONSTRAINT pk_audio_tracks PRIMARY KEY (id), 
	CONSTRAINT uq_audio_tracks_project_id UNIQUE (project_id), 
	CONSTRAINT fk_audio_tracks_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE, 
	CONSTRAINT fk_audio_tracks_media_id_media FOREIGN KEY(media_id) REFERENCES media (id) ON DELETE SET NULL
);

-- render_jobs
CREATE TABLE render_jobs (
	project_id VARCHAR(32) NOT NULL, 
	user_id VARCHAR(32) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	progress INTEGER NOT NULL, 
	stage VARCHAR(80) NOT NULL, 
	error TEXT NOT NULL, 
	cancel_requested BOOL NOT NULL, 
	plan JSON NOT NULL, 
	output_media_id VARCHAR(32), 
	started_at DATETIME, 
	finished_at DATETIME, 
	id VARCHAR(32) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	CONSTRAINT pk_render_jobs PRIMARY KEY (id), 
	CONSTRAINT fk_render_jobs_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE, 
	CONSTRAINT fk_render_jobs_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	CONSTRAINT fk_render_jobs_output_media_id_media FOREIGN KEY(output_media_id) REFERENCES media (id) ON DELETE SET NULL
);

-- scenes
CREATE TABLE scenes (
	project_id VARCHAR(32) NOT NULL, 
	order_index INTEGER NOT NULL, 
	media_id VARCHAR(32), 
	duration FLOAT NOT NULL, 
	animation VARCHAR(32) NOT NULL, 
	animation_intensity FLOAT NOT NULL, 
	focus_x FLOAT NOT NULL, 
	focus_y FLOAT NOT NULL, 
	transition VARCHAR(32) NOT NULL, 
	transition_duration FLOAT NOT NULL, 
	background_color VARCHAR(9) NOT NULL, 
	note VARCHAR(400) NOT NULL, 
	image_prompt VARCHAR(1200) NOT NULL, 
	texts JSON NOT NULL, 
	ai_motion JSON, 
	id VARCHAR(32) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	CONSTRAINT pk_scenes PRIMARY KEY (id), 
	CONSTRAINT uq_scene_order UNIQUE (project_id, order_index), 
	CONSTRAINT ck_scenes_duration_positive CHECK (duration > 0), 
	CONSTRAINT fk_scenes_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE, 
	CONSTRAINT fk_scenes_media_id_media FOREIGN KEY(media_id) REFERENCES media (id) ON DELETE SET NULL
);

-- voice_overs
CREATE TABLE voice_overs (
	project_id VARCHAR(32) NOT NULL, 
	media_id VARCHAR(32), 
	enabled BOOL NOT NULL, 
	script TEXT NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	provider VARCHAR(32), 
	voice_id VARCHAR(120), 
	volume FLOAT NOT NULL, 
	duck_music_to FLOAT NOT NULL, 
	error TEXT NOT NULL, 
	word_timings JSON NOT NULL DEFAULT '[]', 
	id VARCHAR(32) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	CONSTRAINT pk_voice_overs PRIMARY KEY (id), 
	CONSTRAINT uq_voice_overs_project_id UNIQUE (project_id), 
	CONSTRAINT fk_voice_overs_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE, 
	CONSTRAINT fk_voice_overs_media_id_media FOREIGN KEY(media_id) REFERENCES media (id) ON DELETE SET NULL
);

-- Contraintes ajoutees apres coup : les tables suivantes forment un cycle
-- (characters/brand_kits -> media -> projects -> characters/brand_kits),
-- donc ces FK ne peuvent pas toutes exister au moment du CREATE TABLE.
ALTER TABLE brand_kits ADD CONSTRAINT fk_brand_kits_logo_media FOREIGN KEY(logo_media_id) REFERENCES media (id) ON DELETE SET NULL;
ALTER TABLE characters ADD CONSTRAINT fk_characters_reference_media FOREIGN KEY(reference_media_id) REFERENCES media (id) ON DELETE SET NULL;
ALTER TABLE projects ADD CONSTRAINT fk_projects_brand_kit FOREIGN KEY(brand_kit_id) REFERENCES brand_kits (id) ON DELETE SET NULL;

SET FOREIGN_KEY_CHECKS=1;

