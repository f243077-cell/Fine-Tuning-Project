---
title: RU-Guard
emoji: 🛡️
colorFrom: green
colorTo: red
sdk: docker
app_port: 7860
license: apache-2.0
short_description: Prompt-injection guard for Roman Urdu, English and mixed text
---

Public demo of [RU-Guard](https://github.com/f243077-cell/Roman-Urdu-Guard-Model): a small Qwen2.5 model fine-tuned to detect prompt injection in Roman Urdu. It runs on a free CPU, so a scan takes about a second and a chat answer 30 to 90 seconds.

Nothing you type is stored: the service keeps only a keyed hash and the length of each text, and the app's history lives in your browser tab. Each visitor is limited to 30 scans and 6 chat questions a minute.
