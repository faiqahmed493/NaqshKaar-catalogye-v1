-- =============================================================================
-- Reference data: supported categories and the 3D generation engine registry.
-- Safe to re-run (ON CONFLICT DO UPDATE / DO NOTHING).
-- =============================================================================

-- Top-level groups (proposal scope: furniture, lighting, planters, decor)
INSERT INTO category (code, name, product_group, parent_id, default_placement, sort_order) VALUES
  ('furniture', 'Furniture', 'furniture', NULL, 'floor',    10),
  ('lighting',  'Lighting',  'lighting',  NULL, NULL,       20),
  ('planter',   'Planters',  'planter',   NULL, 'floor',    30),
  ('decor',     'Decor',     'decor',     NULL, NULL,       40)
ON CONFLICT (code) DO NOTHING;

WITH g AS (SELECT id, code FROM category WHERE parent_id IS NULL)
INSERT INTO category (code, name, product_group, parent_id, default_placement, is_planar, sort_order)
SELECT v.code, v.name, v.grp::product_group, g.id, v.placement::placement_type, v.planar, v.ord
FROM (VALUES
  -- furniture
  ('bed',              'Bed',                    'furniture', 'floor',    false, 100),
  ('side_table',       'Bedside / side table',   'furniture', 'floor',    false, 101),
  ('wardrobe',         'Wardrobe',               'furniture', 'floor',    false, 102),
  ('chest_of_drawers', 'Chest of drawers',       'furniture', 'floor',    false, 103),
  ('dressing_table',   'Dressing table',         'furniture', 'floor',    false, 104),
  ('sofa',             'Sofa',                   'furniture', 'floor',    false, 110),
  ('armchair',         'Armchair',               'furniture', 'floor',    false, 111),
  ('coffee_table',     'Coffee / centre table',  'furniture', 'floor',    false, 112),
  ('tv_unit',          'TV unit',                'furniture', 'floor',    false, 113),
  ('console_table',    'Console table',          'furniture', 'floor',    false, 114),
  ('ottoman',          'Ottoman / pouffe',       'furniture', 'floor',    false, 115),
  ('floor_seating',    'Floor seating / gadda',  'furniture', 'floor',    false, 116),
  ('bookshelf',        'Bookshelf / cabinet',    'furniture', 'floor',    false, 117),
  ('wall_shelf',       'Wall shelf',             'furniture', 'wall',     false, 118),
  ('study_desk',       'Study desk',             'furniture', 'floor',    false, 120),
  ('study_chair',      'Study / office chair',   'furniture', 'floor',    false, 121),
  ('dining_table',     'Dining table',           'furniture', 'floor',    false, 130),
  ('dining_chair',     'Dining chair',           'furniture', 'floor',    false, 131),
  ('dining_set',       'Dining set',             'furniture', 'floor',    false, 132),
  ('sideboard',        'Sideboard / buffet',     'furniture', 'floor',    false, 133),
  ('bench',            'Bench',                  'furniture', 'floor',    false, 134),
  -- lighting
  ('floor_lamp',       'Floor lamp',             'lighting',  'floor',    false, 200),
  ('table_lamp',       'Table lamp',             'lighting',  'tabletop', false, 201),
  ('ceiling_light',    'Ceiling light',          'lighting',  'ceiling',  false, 202),
  ('chandelier',       'Chandelier',             'lighting',  'ceiling',  false, 203),
  ('wall_light',       'Wall light',             'lighting',  'wall',     false, 204),
  -- planters
  ('floor_planter',    'Floor planter',          'planter',   'floor',    false, 300),
  ('table_planter',    'Table planter',          'planter',   'tabletop', false, 301),
  ('wall_planter',     'Wall planter',           'planter',   'wall',     false, 302),
  -- decor
  ('rug',              'Rug / carpet',           'decor',     'floor',    true,  400),
  ('wall_art',         'Wall art / frame',       'decor',     'wall',     false, 401),
  ('mirror',           'Mirror',                 'decor',     'wall',     false, 402),
  ('wall_clock',       'Wall clock',             'decor',     'wall',     false, 403),
  ('vase',             'Vase / decor piece',     'decor',     'tabletop', false, 404),
  ('cushion',          'Cushion',                'decor',     'tabletop', false, 405)
) AS v(code, name, grp, placement, planar, ord)
JOIN g ON g.code = v.grp
ON CONFLICT (code) DO NOTHING;

-- Engine registry. VRAM figures are approximate starting points from each
-- project's documentation; benchmark on your own GPU before relying on them.
INSERT INTO generation_engine
  (code, display_name, kind, license, is_open_source, commercial_use_note, supports_multi_image,
   max_input_images, required_views, supports_texture, min_vram_gb, default_params, homepage_url, notes, sort_order)
VALUES
  ('trellis', 'TRELLIS (image-large)', 'local_gpu', 'MIT', true, NULL, true, 4, NULL, true, 16,
   '{"seed": 1, "ss_steps": 12, "ss_cfg": 7.5, "slat_steps": 12, "slat_cfg": 3.0, "simplify": 0.95, "texture_size": 1024, "multi_image_mode": "stochastic"}',
   'https://github.com/microsoft/TRELLIS',
   'Single or multi-image conditioning. Good default for furniture with textures.', 10),
  ('trellis_hf', 'TRELLIS via Hugging Face (no GPU)', 'external_api', 'MIT', true,
   'Images are uploaded to a public Hugging Face Space; free use is limited by its GPU quota.', false, 1, NULL, true, NULL,
   '{"seed": 1, "ss_steps": 12, "ss_cfg": 7.5, "slat_steps": 12, "slat_cfg": 3.0, "simplify": 0.95, "texture_size": 1024}',
   'https://huggingface.co/spaces/trellis-community/TRELLIS',
   'Runs TRELLIS on the Space''s GPU. Optional HF_TOKEN on the worker raises the free quota.', 15),
  ('trellis2', 'TRELLIS.2 (4B)', 'local_gpu', 'MIT', true, NULL, false, 1, NULL, true, 24,
   '{"seed": 1, "decimation_target": 500000, "texture_size": 2048, "pipeline_type": null}',
   'https://github.com/microsoft/TRELLIS.2',
   'Highest quality PBR output; needs a 24 GB GPU.', 20),
  ('triposr', 'TripoSR', 'local_gpu', 'MIT', true, NULL, false, 1, NULL, true, 6,
   '{"mc_resolution": 256, "foreground_ratio": 0.85, "chunk_size": 8192}',
   'https://github.com/VAST-AI-Research/TripoSR',
   'Fast and light; runs on a Colab T4. Output uses vertex colours (no UV texture).', 30),
  ('hunyuan3d2', 'Hunyuan3D-2 (shape + paint)', 'local_gpu', 'Tencent Hunyuan Community License', true,
   'Check the licence terms before commercial use.', false, 1, NULL, true, 16,
   '{"model": "tencent/Hunyuan3D-2", "subfolder": "hunyuan3d-dit-v2-0", "texture": true, "steps": 50, "octree_resolution": 380, "seed": 1234}',
   'https://github.com/Tencent-Hunyuan/Hunyuan3D-2',
   'Set texture=false for shape-only on ~6 GB. Use model tencent/Hunyuan3D-2mini for a lighter run.', 40),
  ('hunyuan3d2mv', 'Hunyuan3D-2mv (multi-view)', 'local_gpu', 'Tencent Hunyuan Community License', true,
   'Check the licence terms before commercial use.', true, 4, '{front}', false, 10,
   '{"model": "tencent/Hunyuan3D-2mv", "subfolder": "hunyuan3d-dit-v2-mv", "steps": 50, "octree_resolution": 380, "seed": 1234}',
   'https://github.com/Tencent-Hunyuan/Hunyuan3D-2',
   'Uses images tagged front / left / back / right. Front is required. Shape only.', 50),
  ('hunyuan3d21', 'Hunyuan3D-2.1 (PBR)', 'local_gpu', 'Tencent Hunyuan Non-Commercial License', true,
   'Non-commercial licence: fine for the FYP, not for a commercial product.', false, 1, NULL, true, 24,
   '{"texture": true, "max_num_view": 6, "paint_resolution": 512}',
   'https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1',
   'PBR textures; shape-only needs ~10 GB.', 60),
  ('sf3d', 'Stable Fast 3D', 'local_gpu', 'Stability AI Community License', true,
   'Free under the community licence threshold; model is gated on Hugging Face.', false, 1, NULL, true, 7,
   '{"texture_resolution": 1024, "remesh": "none", "vertex_count": -1, "foreground_ratio": 0.85}',
   'https://github.com/Stability-AI/stable-fast-3d',
   'Very fast UV-unwrapped output. Requires accepting the model terms on Hugging Face.', 70),
  ('instantmesh', 'InstantMesh', 'local_gpu', 'Apache-2.0', true,
   'Uses Zero123++ for view synthesis; check its licence too.', false, 1, NULL, true, 16,
   '{"config": "configs/instant-mesh-large.yaml", "export_texmap": true}',
   'https://github.com/TencentARC/InstantMesh',
   'Runs the repository CLI and converts its OBJ to GLB.', 80),
  ('command', 'Custom command (any model)', 'local_gpu', 'Depends on the model you plug in', true, NULL, true, 8, NULL, true, NULL,
   '{}', NULL,
   'Runs GENERATOR_COMMAND_TEMPLATE on the worker, so any open-source model with a CLI can be added without code.', 90),
  ('meshy', 'Meshy API (commercial)', 'external_api', 'Proprietary paid API', false,
   'Paid credits; images are sent to a third party.', true, 4, NULL, true, NULL,
   '{"ai_model": "latest", "should_texture": true, "target_polycount": 30000}',
   'https://docs.meshy.ai',
   'Optional. Needs MESHY_API_KEY on the worker. Not open source.', 100),
  ('mock', 'Mock engine (testing)', 'cpu', 'Internal', true, NULL, true, 8, NULL, true, NULL,
   '{"delay_seconds": 3}', NULL,
   'Builds a textured box from the first image. Use it to test the pipeline without a GPU.', 999)
ON CONFLICT (code) DO UPDATE SET
  display_name = EXCLUDED.display_name, kind = EXCLUDED.kind, license = EXCLUDED.license,
  is_open_source = EXCLUDED.is_open_source, commercial_use_note = EXCLUDED.commercial_use_note,
  supports_multi_image = EXCLUDED.supports_multi_image, max_input_images = EXCLUDED.max_input_images,
  required_views = EXCLUDED.required_views, supports_texture = EXCLUDED.supports_texture,
  min_vram_gb = EXCLUDED.min_vram_gb, default_params = EXCLUDED.default_params,
  homepage_url = EXCLUDED.homepage_url, notes = EXCLUDED.notes, sort_order = EXCLUDED.sort_order;
