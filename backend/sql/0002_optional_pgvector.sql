-- =============================================================================
-- Optional: product embeddings for multimodal retrieval (proposal pipeline P1).
-- Runs only when the pgvector extension is installed on the server
-- (the docker-compose image pgvector/pgvector:pg16 has it). Otherwise it is a no-op,
-- and the rest of the system works unchanged.
-- =============================================================================
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'vector') THEN
    EXECUTE 'CREATE EXTENSION IF NOT EXISTS vector';
    EXECUTE $sql$
      CREATE TABLE IF NOT EXISTS variant_embedding (
        variant_id       uuid NOT NULL REFERENCES product_variant(id) ON DELETE CASCADE,
        model            text NOT NULL,                  -- e.g. open_clip/ViT-B-32/laion2b
        kind             text NOT NULL CHECK (kind IN ('image', 'text')),
        source_image_id  uuid REFERENCES product_image(id) ON DELETE SET NULL,
        embedding        vector(512) NOT NULL,
        created_at       timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (variant_id, model, kind)
      )
    $sql$;
    EXECUTE 'CREATE INDEX IF NOT EXISTS ix_variant_embedding_hnsw
             ON variant_embedding USING hnsw (embedding vector_cosine_ops)';
    RAISE NOTICE 'pgvector found: variant_embedding created';
  ELSE
    RAISE NOTICE 'pgvector not installed: skipping variant_embedding';
  END IF;
END $$;
