"""baseline: full base schema (explicit, immutable snapshot)

Static DDL for every base table EXCEPT ai_accounts / ai_models (added by
0001_ai_routing). This was generated once from the SQLAlchemy models via Alembic
autogenerate and then FROZEN: unlike the previous ``metadata.create_all`` form, it
no longer re-reads the live models, so a later model change can never silently
rewrite this historical revision — schema changes get their own migration instead.

Two portability notes baked in (so the same migration runs on Postgres prod AND
the zero-infra SQLite dev/test DB):
* JSON columns use ``core.models.types.JSONType`` (JSONB on Postgres, JSON on
  SQLite) rather than a Postgres-only JSONB.
* Timestamp server defaults use ``sa.func.now()`` (compiles to CURRENT_TIMESTAMP
  on SQLite, now() on Postgres), not a raw ``text('now()')``.

Revision ID: 0000_baseline
Revises:
Create Date: 2026-06-18
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from core.models.types import JSONType

revision = "0000_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('admin_audit_log',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('admin_id', sa.BigInteger(), nullable=False),
    sa.Column('action', sa.String(length=60), nullable=False),
    sa.Column('target_type', sa.String(length=40), nullable=True),
    sa.Column('target_id', sa.String(length=60), nullable=True),
    sa.Column('before', JSONType, nullable=True),
    sa.Column('after', JSONType, nullable=True),
    sa.Column('ip', sa.String(length=45), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('admin_users',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('totp_secret', sa.String(length=64), nullable=True),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
    sa.Column('token_version', sa.Integer(), server_default='0', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    op.create_table('broadcasts',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('admin_id', sa.BigInteger(), nullable=False),
    sa.Column('segment', JSONType, nullable=False),
    sa.Column('content', JSONType, nullable=False),
    sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('sent', sa.Integer(), nullable=False),
    sa.Column('failed', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('channel_gates',
    sa.Column('channel', sa.String(length=50), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('channel')
    )
    op.create_table('generation_jobs',
    sa.Column('job_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('service', sa.String(length=50), nullable=False),
    sa.Column('model_variant', sa.String(length=50), nullable=True),
    sa.Column('params', JSONType, nullable=False),
    sa.Column('cost_credits', sa.Integer(), nullable=False),
    sa.Column('pack_type', sa.String(length=10), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('result_file_id', sa.String(length=200), nullable=True),
    sa.Column('result_url', sa.String(length=500), nullable=True),
    sa.Column('provider_job_id', sa.String(length=120), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('job_id')
    )
    op.create_table('kling_effects_templates',
    sa.Column('template_id', sa.Integer(), nullable=False),
    sa.Column('page', sa.Integer(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('name_ru', sa.String(length=100), nullable=False),
    sa.Column('name_i18n', JSONType, nullable=False),
    sa.Column('is_new', sa.Boolean(), nullable=False),
    sa.Column('preview_url', sa.String(length=500), nullable=True),
    sa.PrimaryKeyConstraint('template_id')
    )
    op.create_table('kling_motion_templates',
    sa.Column('template_id', sa.Integer(), nullable=False),
    sa.Column('page', sa.Integer(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('name_ru', sa.String(length=100), nullable=False),
    sa.Column('name_i18n', JSONType, nullable=False),
    sa.Column('preview_url', sa.String(length=500), nullable=True),
    sa.PrimaryKeyConstraint('template_id')
    )
    op.create_table('mini_app_photo_effects',
    sa.Column('effect_id', sa.Integer(), nullable=False),
    sa.Column('category', sa.String(length=20), nullable=False),
    sa.Column('name_ru', sa.String(length=100), nullable=False),
    sa.Column('name_i18n', JSONType, nullable=False),
    sa.Column('thumbnail_url', sa.String(length=500), nullable=True),
    sa.Column('badge', sa.String(length=10), nullable=True),
    sa.Column('gen_count', sa.Integer(), nullable=False),
    sa.Column('is_ad', sa.Boolean(), nullable=False),
    sa.Column('recommended_model', sa.String(length=40), nullable=True),
    sa.Column('compatible_models', JSONType, nullable=False),
    sa.Column('prompt_template', sa.Text(), nullable=True),
    sa.Column('default_params', JSONType, nullable=False),
    sa.Column('max_photos', sa.Integer(), nullable=False),
    sa.Column('preview_url', sa.String(length=500), nullable=True),
    sa.Column('is_trending', sa.Boolean(), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('author', sa.String(length=40), nullable=True),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('effect_id')
    )
    op.create_table('mini_app_video_effects',
    sa.Column('effect_id', sa.Integer(), nullable=False),
    sa.Column('category', sa.String(length=20), nullable=False),
    sa.Column('name_ru', sa.String(length=100), nullable=False),
    sa.Column('name_i18n', JSONType, nullable=False),
    sa.Column('provider', sa.String(length=20), nullable=False),
    sa.Column('thumbnail_url', sa.String(length=500), nullable=True),
    sa.Column('gen_count', sa.Integer(), nullable=False),
    sa.Column('recommended_model', sa.String(length=40), nullable=True),
    sa.Column('compatible_models', JSONType, nullable=False),
    sa.Column('prompt_template', sa.Text(), nullable=True),
    sa.Column('default_params', JSONType, nullable=False),
    sa.Column('max_photos', sa.Integer(), nullable=False),
    sa.Column('preview_url', sa.String(length=500), nullable=True),
    sa.Column('is_trending', sa.Boolean(), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('author', sa.String(length=40), nullable=True),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('effect_id')
    )
    op.create_table('pricing',
    sa.Column('key', sa.String(length=50), nullable=False),
    sa.Column('value', JSONType, nullable=False),
    sa.PrimaryKeyConstraint('key')
    )
    op.create_table('promo_codes',
    sa.Column('code', sa.String(length=40), nullable=False),
    sa.Column('reward_type', sa.String(length=20), nullable=False),
    sa.Column('reward_amount', sa.Integer(), nullable=False),
    sa.Column('max_uses', sa.Integer(), nullable=False),
    sa.Column('used', sa.Integer(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('code')
    )
    op.create_table('referrals',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('referrer_id', sa.BigInteger(), nullable=False),
    sa.Column('referred_id', sa.BigInteger(), nullable=False),
    sa.Column('reward_type', sa.String(length=20), nullable=True),
    sa.Column('reward_amount', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('rewarded_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('referred_id')
    )
    op.create_table('transactions',
    sa.Column('tx_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('product', sa.String(length=30), nullable=False),
    sa.Column('duration_months', sa.Integer(), nullable=True),
    sa.Column('qty', sa.Integer(), nullable=True),
    sa.Column('amount', sa.Integer(), nullable=False),
    sa.Column('currency', sa.String(length=10), nullable=False),
    sa.Column('gateway', sa.String(length=20), nullable=False),
    sa.Column('gateway_tx_id', sa.String(length=120), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('credits_added', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('tx_id'),
    sa.UniqueConstraint('gateway_tx_id')
    )
    op.create_table('usage_log',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('action', sa.String(length=50), nullable=False),
    sa.Column('meta', JSONType, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('users',
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('username', sa.String(length=64), nullable=True),
    sa.Column('language_code', sa.String(length=5), nullable=False),
    sa.Column('selected_model', sa.String(length=50), nullable=False),
    sa.Column('custom_role', sa.Text(), nullable=True),
    sa.Column('role_enabled', sa.Boolean(), nullable=False),
    sa.Column('context_enabled', sa.Boolean(), nullable=False),
    sa.Column('voice_name', sa.String(length=20), nullable=False),
    sa.Column('voice_enabled', sa.Boolean(), nullable=False),
    sa.Column('sub_tier', sa.String(length=20), nullable=True),
    sa.Column('sub_expires', sa.DateTime(timezone=True), nullable=True),
    sa.Column('text_req_week', sa.Integer(), nullable=False),
    sa.Column('week_start', sa.DateTime(timezone=True), nullable=True),
    sa.Column('text_req_day', sa.Integer(), nullable=False),
    sa.Column('day_start', sa.DateTime(timezone=True), nullable=True),
    sa.Column('mini_app_effects_week', sa.Integer(), nullable=False),
    sa.Column('mini_app_week_start', sa.DateTime(timezone=True), nullable=True),
    sa.Column('diamonds', sa.Integer(), nullable=False),
    sa.Column('is_channel_subscribed', sa.Boolean(), nullable=False),
    sa.Column('referred_by', sa.BigInteger(), nullable=True),
    sa.Column('is_banned', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.PrimaryKeyConstraint('user_id')
    )
    op.create_table('pack_balances',
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('image_credits', sa.Integer(), nullable=False),
    sa.Column('video_credits', sa.Integer(), nullable=False),
    sa.Column('music_credits', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id')
    )
    op.create_index(op.f('ix_admin_audit_log_admin_id'), 'admin_audit_log', ['admin_id'], unique=False)
    op.create_index(op.f('ix_generation_jobs_status'), 'generation_jobs', ['status'], unique=False)
    op.create_index(op.f('ix_generation_jobs_user_id'), 'generation_jobs', ['user_id'], unique=False)
    op.create_index(op.f('ix_referrals_referrer_id'), 'referrals', ['referrer_id'], unique=False)
    op.create_index(op.f('ix_transactions_gateway'), 'transactions', ['gateway'], unique=False)
    op.create_index(op.f('ix_transactions_status'), 'transactions', ['status'], unique=False)
    op.create_index(op.f('ix_transactions_user_id'), 'transactions', ['user_id'], unique=False)
    op.create_index(op.f('ix_usage_log_user_id'), 'usage_log', ['user_id'], unique=False)
    op.create_index(op.f('ix_users_sub_expires'), 'users', ['sub_expires'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_admin_audit_log_admin_id'), table_name='admin_audit_log')
    op.drop_index(op.f('ix_generation_jobs_status'), table_name='generation_jobs')
    op.drop_index(op.f('ix_generation_jobs_user_id'), table_name='generation_jobs')
    op.drop_index(op.f('ix_referrals_referrer_id'), table_name='referrals')
    op.drop_index(op.f('ix_transactions_gateway'), table_name='transactions')
    op.drop_index(op.f('ix_transactions_status'), table_name='transactions')
    op.drop_index(op.f('ix_transactions_user_id'), table_name='transactions')
    op.drop_index(op.f('ix_usage_log_user_id'), table_name='usage_log')
    op.drop_index(op.f('ix_users_sub_expires'), table_name='users')
    op.drop_table('pack_balances')
    op.drop_table('users')
    op.drop_table('usage_log')
    op.drop_table('transactions')
    op.drop_table('referrals')
    op.drop_table('promo_codes')
    op.drop_table('pricing')
    op.drop_table('mini_app_video_effects')
    op.drop_table('mini_app_photo_effects')
    op.drop_table('kling_motion_templates')
    op.drop_table('kling_effects_templates')
    op.drop_table('generation_jobs')
    op.drop_table('channel_gates')
    op.drop_table('broadcasts')
    op.drop_table('admin_users')
    op.drop_table('admin_audit_log')
