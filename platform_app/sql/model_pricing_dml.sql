-- Initial LiteLLM standard-text USD rates, copied from the existing attributed snapshot.
-- INSERT OR IGNORE preserves local edits when initialization is repeated.
INSERT OR IGNORE INTO model_pricing_provenance(key, value) VALUES ('source', 'https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json');
INSERT OR IGNORE INTO model_pricing_provenance(key, value) VALUES ('documentation', 'https://docs.litellm.ai/docs/proxy/model_cost_map');
INSERT OR IGNORE INTO model_pricing_provenance(key, value) VALUES ('retrieved_at', '2026-11-09T11:58:01.778819+00:00');
INSERT OR IGNORE INTO model_pricing_provenance(key, value) VALUES ('source_sha256', 'faa400408127c27aa323d29544389f85a06ab77660aa910b6d6e30dc46f33aa2');
INSERT OR IGNORE INTO model_pricing_provenance(key, value) VALUES ('description', 'Verbatim subset of standard text-token USD rates; no live refresh or gateway traffic.');
INSERT OR IGNORE INTO model_pricing(model, input_cost_per_token, output_cost_per_token, cache_read_input_token_cost, input_cost_per_token_above_200k_tokens, output_cost_per_token_above_200k_tokens, cache_read_input_token_cost_above_200k_tokens)
VALUES ('gemini/gemini-2.5-flash-lite', 1e-07, 4e-07, 1e-08, NULL, NULL, NULL);
INSERT OR IGNORE INTO model_pricing(model, input_cost_per_token, output_cost_per_token, cache_read_input_token_cost, input_cost_per_token_above_200k_tokens, output_cost_per_token_above_200k_tokens, cache_read_input_token_cost_above_200k_tokens)
VALUES ('gemini/gemini-2.5-flash', 3e-07, 2.5e-06, 3e-08, NULL, NULL, NULL);
INSERT OR IGNORE INTO model_pricing(model, input_cost_per_token, output_cost_per_token, cache_read_input_token_cost, input_cost_per_token_above_200k_tokens, output_cost_per_token_above_200k_tokens, cache_read_input_token_cost_above_200k_tokens)
VALUES ('gemini/gemini-2.5-pro', 1.25e-06, 1e-05, 1.25e-07, 2.5e-06, 1.5e-05, 2.5e-07);
INSERT OR IGNORE INTO model_pricing(model, input_cost_per_token, output_cost_per_token, cache_read_input_token_cost, input_cost_per_token_above_200k_tokens, output_cost_per_token_above_200k_tokens, cache_read_input_token_cost_above_200k_tokens)
VALUES ('gemini-2.5-flash-lite', 1e-07, 4e-07, 1e-08, NULL, NULL, NULL);
INSERT OR IGNORE INTO model_pricing(model, input_cost_per_token, output_cost_per_token, cache_read_input_token_cost, input_cost_per_token_above_200k_tokens, output_cost_per_token_above_200k_tokens, cache_read_input_token_cost_above_200k_tokens)
VALUES ('gemini-2.5-flash', 3e-07, 2.5e-06, 3e-08, NULL, NULL, NULL);
INSERT OR IGNORE INTO model_pricing(model, input_cost_per_token, output_cost_per_token, cache_read_input_token_cost, input_cost_per_token_above_200k_tokens, output_cost_per_token_above_200k_tokens, cache_read_input_token_cost_above_200k_tokens)
VALUES ('gemini-2.5-pro', 1.25e-06, 1e-05, 1.25e-07, 2.5e-06, 1.5e-05, 2.5e-07);
INSERT OR IGNORE INTO model_pricing(model, input_cost_per_token, output_cost_per_token, cache_read_input_token_cost, input_cost_per_token_above_200k_tokens, output_cost_per_token_above_200k_tokens, cache_read_input_token_cost_above_200k_tokens)
VALUES ('gpt-4.1-mini', 4e-07, 1.6e-06, 1e-07, NULL, NULL, NULL);
INSERT OR IGNORE INTO model_pricing(model, input_cost_per_token, output_cost_per_token, cache_read_input_token_cost, input_cost_per_token_above_200k_tokens, output_cost_per_token_above_200k_tokens, cache_read_input_token_cost_above_200k_tokens)
VALUES ('gpt-4o-mini', 1.5e-07, 6e-07, 7.5e-08, NULL, NULL, NULL);
