# Publish the model file as a GitHub Release (owner, Phase 8)

CI downloads the guard model from a GitHub Release. Until it exists, the PR smoke eval is skipped with a warning
and the nightly workflow fails at "Fetch GGUF". Release assets can be up to 2 GiB each; this file is 0.99 GB.
Keep the repository public, so that standard GitHub-hosted runners stay free.

## Steps (web browser, about 5 minutes plus upload time)

1. Check the file first. In Git Bash in the repo folder:

   ```bash
   sha256sum models/ru-guard-1.5b-v2-Q4_K_M.gguf
   ```

   It must print `52b5472abc1419f8c43645a733dd4dd9ee9e6e8b1be7de974d61dd988f8022e7`.

2. Open https://github.com/f243077-cell/Roman-Urdu-Guard-Model/releases/new
3. **Choose a tag:** type `model-v1` and click "Create new tag: model-v1 on publish". Target: `main`.
4. **Release title:** `ru-guard-1.5b-v2 (Q4_K_M) model file`
5. **Description:** paste this:

   ```
   Deployed RU-Guard model (D49): ru-guard-1.5b-v2, GGUF Q4_K_M, 986,048,224 bytes.
   SHA-256: 52b5472abc1419f8c43645a733dd4dd9ee9e6e8b1be7de974d61dd988f8022e7
   Register: bash scripts/register_model.sh ru-guard-1.5b-v2  (file in models/)
   Base model: Qwen2.5-1.5B-Instruct (check its licence before reuse). See MODEL_CARD.md.
   ```

6. Drag `models/ru-guard-1.5b-v2-Q4_K_M.gguf` into "Attach binaries". Keep the file name exactly as it is.
   On a slow connection this upload can take more than an hour. Leave the tab open until the file shows a size.
7. Leave "Set as a pre-release" unticked, then click **Publish release**.

## Check

Open https://github.com/f243077-cell/Roman-Urdu-Guard-Model/releases/download/model-v1/ru-guard-1.5b-v2-Q4_K_M.gguf.
The download must start. Then, on the Actions tab, run the "ci" workflow ("Run workflow"). The "Smoke eval
(100 rows) and gate" job should run the eval and print `gate: PASS`.

The tag name and file name are set in `.github/workflows/ci.yml` and `nightly.yml` (`MODEL_TAG`, `GGUF_NAME`).
If you change either, change it there too.
