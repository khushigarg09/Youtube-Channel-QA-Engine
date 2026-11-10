"""initial schema with pgvector

Revision ID: 001
Revises: 
Create Date: 2026-11-09

"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name

    # 1. Enable pgvector extension on PostgreSQL
    if dialect_name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # 2. Create channels table
    op.create_table(
        'channels',
        sa.Column('channel_id', sa.String(), primary_key=True, nullable=False),
        sa.Column('channel_name', sa.String(), nullable=False),
        sa.Column('custom_url', sa.String(), nullable=True),
        sa.Column('thumbnail_url', sa.String(), nullable=True),
        sa.Column('indexed_at', sa.DateTime(), nullable=True),
        sa.Column('indexing_status', sa.String(), nullable=False, server_default='idle'),
    )
    op.create_index('ix_channels_channel_id', 'channels', ['channel_id'])

    # 3. Create videos table
    op.create_table(
        'videos',
        sa.Column('video_id', sa.String(), primary_key=True, nullable=False),
        sa.Column('channel_id', sa.String(), sa.ForeignKey('channels.channel_id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('upload_date', sa.DateTime(), nullable=True),
        sa.Column('thumbnail_url', sa.String(), nullable=True),
        sa.Column('duration_seconds', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('error_message', sa.Text(), nullable=True),
    )
    op.create_index('ix_videos_video_id', 'videos', ['video_id'])
    op.create_index('ix_videos_channel_id', 'videos', ['channel_id'])
    op.create_index('ix_videos_upload_date', 'videos', ['upload_date'])

    # 4. Create transcript_chunks table with vector(384)
    chunk_columns = [
        sa.Column('chunk_id', sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column('video_id', sa.String(), sa.ForeignKey('videos.video_id', ondelete='CASCADE'), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('start_time', sa.Float(), nullable=False),
        sa.Column('duration', sa.Float(), nullable=False),
        sa.Column('chroma_id', sa.String(), nullable=True),
    ]
    if dialect_name == "postgresql":
        chunk_columns.append(sa.Column('embedding', Vector(384), nullable=True))
    else:
        chunk_columns.append(sa.Column('embedding', sa.JSON(), nullable=True))

    op.create_table('transcript_chunks', *chunk_columns)
    op.create_index('ix_transcript_chunks_video_id', 'transcript_chunks', ['video_id'])
    op.create_index('ix_transcript_chunks_chroma_id', 'transcript_chunks', ['chroma_id'])

    if dialect_name == "postgresql":
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_transcript_chunks_embedding "
            "ON transcript_chunks USING hnsw (embedding vector_cosine_ops);"
        )

    # 5. Create topics table
    op.create_table(
        'topics',
        sa.Column('topic_id', sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('video_id', sa.String(), sa.ForeignKey('videos.video_id', ondelete='CASCADE'), nullable=False),
        sa.Column('timestamp', sa.Float(), nullable=False),
    )
    op.create_index('ix_topics_name', 'topics', ['name'])
    op.create_index('ix_topics_video_id', 'topics', ['video_id'])


def downgrade() -> None:
    op.drop_table('topics')
    op.drop_table('transcript_chunks')
    op.drop_table('videos')
    op.drop_table('channels')

