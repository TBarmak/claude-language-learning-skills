---
name: anki-phrases
description: This skill should be used when the user asks to "generate Anki phrase cards", "create phrase flashcards", "build an Anki phrases CSV", "explain foreign expressions", or provides a file of foreign language expressions to study. Produces a CSV with monolingual explanations, example sentences, and a pronunciation audio file per phrase (Forvo human recording, falling back to neural TTS).
argument-hint: <expression-list-file>
---

# Anki Phrases Generator

Generate an Anki-importable CSV from a file of foreign language expressions. For each expression, produce a monolingual explanation (meaning, register, frequency, regional usage) and 5 example sentences. All content is strictly in the target language — no English or other languages.

## Inputs

Argument is provided as `$ARGUMENTS` in the form `<expression-list-file>`.

- `expression-list-file`: path to a plain text file with one expression or phrase per line

Language is auto-detected from the expressions in the file.

## Step 1 — Parse input

Read the expression list file. Ignore blank lines and lines starting with `#`. If the file does not exist or is empty, stop and report the error.

Collect all expressions into an ordered list.

## Step 2 — Detect language

Inspect the first 10–20 expressions and use AI to identify the target language (e.g. "Brazilian Portuguese", "Mexican Spanish", "French", "Japanese").

If the language is ambiguous or mixed, ask the user to clarify before continuing.

Print: `Idioma detectado: {language}` (or equivalent in the detected language) so the user can confirm.

## Step 3 — Set up output path

Determine a timestamp string (format: `YYYYMMDD_HHMMSS`) using the Bash tool — run as its own separate call:

```bash
date +%Y%m%d_%H%M%S
```

Output CSV path: `output/{language_lowercase}_phrases_{timestamp}.csv`

where `language_lowercase` is the detected language in lowercase with spaces replaced by underscores (e.g. `brazilian_portuguese`, `french`).

Print the output path so the user can see where the file will be written.

## Step 4 — Process each expression

Process expressions **one at a time**. For each expression, before generating content, print a progress header to text output so the user can monitor and interrupt if needed:

```
─────────────────────────────────────────
[N/total] {expression}
─────────────────────────────────────────
```

Then immediately generate the explanation and examples (see 4a–4d below). Print the completed content for that expression in your text output before moving to the next one. This gives the user full visibility at each step.

Do any required web searches (Step 4b) before generating the explanation.

### 4a — Assess confidence

Determine whether you are confident about the expression's meaning and usage:

- **High confidence**: common word, well-known idiom, standard phrase you know well
- **Low confidence**: obscure slang, unusual regional expression, compound phrase with ambiguous meaning, or anything you are not certain about

### 4b — Web search (low confidence only)

If confidence is low, use WebSearch to look up the expression. Suggested query format:
- Portuguese: `"{expression}" português significado uso`
- Spanish: `"{expression}" español significado uso`
- French: `"{expression}" français signification usage`
- Other languages: search in the target language for meaning and usage

Use the search results to inform your explanation and examples.

If web search also returns no useful results, mark the expression as **not found** (see 4c below) — do NOT skip it.

### 4c — Generate explanation

**If the expression was found (high confidence or web search succeeded):**

Write the explanation entirely in the target language. Include all of the following:

1. **Meaning**: what the expression means
2. **Register**: formal / informal / colloquial / vulgar / literary / etc.
3. **Frequency**: how commonly the expression is used (e.g. muito comum, pouco usado, expressão rara, caiu em desuso)
4. **Regional specificity**: which country or region uses it — be specific. Examples:
   - "Usado principalmente no Brasil, especialmente no Sudeste"
   - "Comum em Portugal, menos frequente no Brasil"
   - "Expressão tipicamente mexicana, pouco usada em outros países hispanófonos"
   - "Usada em toda a América Latina e Espanha"
   - If used broadly across all regions, say so explicitly
5. **Connotation**: any nuance, tone, or cultural note worth knowing

Do not use any English or other languages. Write as if explaining to a native-language learner who reads only the target language.

**If the expression was NOT found (low confidence AND web search failed):**

Write a short note in the target language indicating the expression is unknown or unverified. Example (Portuguese): `⚠️ Expressão não encontrada. O significado desta expressão não foi identificado com confiança, nem nas fontes consultadas. Verifique o significado antes de estudar este cartão.`

Adapt the note to the target language of the list.

### 4d — Generate 5 example sentences

**If the expression was found:** Write 5 natural sentences that use the expression in context. Each sentence should:
- Feel authentic, not textbook-stiff
- Show the expression used in a realistic situation
- Vary in context (different speakers, settings, or tones) where possible

All sentences in target language only.

**If the expression was NOT found:** Leave the examples column empty (the field will be blank in the CSV).

## Step 5 — Build all CSV rows in memory

After processing all expressions, assemble every row using this pipe-separated format (no header row):

```
{expression}|{explanation}|{sentence1}<br>{sentence2}<br>{sentence3}<br>{sentence4}<br>{sentence5}
```

Rules:
- **Exactly 2 pipes (`|`) per row** — one after the expression, one after the explanation. The pipe is a COLUMN separator, not a sentence separator.
- **Separate the 5 example sentences with `<br>`, NEVER with `|`.** Do not put a pipe between sentences. The entire block of 5 sentences is a single field.
- Preserve the expression exactly as it appeared in the input file
- Do not quote fields
- Do not include newlines within fields (use `<br>` only)
- If a pipe character appears in any field content, replace it with `&#124;`

Self-check before writing: every row must contain exactly 2 `|` and (for found expressions) exactly 4 `<br>`. If a row has more than 2 pipes, you used `|` where a `<br>` belongs — fix it.

Example row (Brazilian Portuguese):
```
fazer vista grossa|Fingir não ver algo, geralmente uma situação inconveniente ou ilegal. Registro informal. Expressão muito comum no Brasil, usada em todo o país. Não carrega conotação fortemente negativa — às vezes é visto como compreensão ou diplomacia.|O chefe fez vista grossa quando viu o funcionário chegar atrasado.<br>Ela fez vista grossa para os erros do irmão.<br>Às vezes é melhor fazer vista grossa do que criar confusão.<br>O policial fez vista grossa para o vendedor ambulante.<br>Não consigo fazer vista grossa diante de uma injustiça tão clara.
```

## Step 6 — Write CSV file

Use the Write tool to write the complete CSV file in a single operation. All rows joined by newlines, no trailing newline required.

Do not use Bash for this step. The Write tool handles the file directly with no permission prompts.

## Step 7 — Generate pronunciation audio

Add one pronunciation audio file per phrase. The helper script `gen_audio.py`
(in this skill's directory) tries sources in order per phrase and stops at the
first that works: **Forvo** (real human recording) → **Piper** (neural TTS) →
macOS **`say`**. Every clip is normalized to mp3.

**7a — Map the detected language to a code.** The script takes a `--lang` code,
not the display name. Pick from:

| Detected language                     | `--lang` |
|---------------------------------------|----------|
| Spanish (any region)                  | `es`     |
| French                                | `fr`     |
| Italian                               | `it`     |
| German                                | `de`     |
| Brazilian Portuguese                  | `pt-br`  |
| European Portuguese                   | `pt-pt`  |
| English                               | `en`     |
| Japanese                              | `ja`     |
| Mandarin Chinese                      | `zh`     |

Forvo covers all of these. Piper neural voices exist only for es/fr/it/de/pt-br/en;
other languages fall back to macOS `say` when Forvo has no recording.

**7b — Ensure the audio venv (idempotent).** Forvo scraping needs `curl_cffi` +
`beautifulsoup4` in a skill-local venv. Run once (safe to re-run):

```bash
VENV=.claude/skills/anki-phrases/.venv
[ -d "$VENV" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --disable-pip-version-check curl_cffi beautifulsoup4
```

**7c — Run the generator** on the CSV from Step 6. It appends a 4th column
`[sound:...]` to every row and writes the mp3s into `output/{csv_stem}/`:

```bash
.claude/skills/anki-phrases/.venv/bin/python \
  .claude/skills/anki-phrases/gen_audio.py \
  --csv output/{language_lowercase}_phrases_{timestamp}.csv \
  --lang {code}
```

The script prints per-phrase progress (`✓ forvo` / `✓ piper` / `✓ say` / `✗ no
audio`) and a summary of how many came from each source. It is idempotent:
existing mp3s are reused, and re-running never duplicates the audio column.

Piper (the AI fallback) is reused from the local `ai-language-tutor` checkout at
`/Users/taylor/Development/ai-language-tutor`. If that path moves, point the
`PIPER_PYTHON` and `PIPER_VOICES` env vars at the new location. If Piper is
unavailable, the script still falls back to macOS `say`. Pass `--no-forvo` to
skip Forvo and go straight to TTS (useful for testing or offline).

The final CSV has 4 columns: `expression | explanation | examples | audio`.

## Step 8 — Report results

Print a summary:

```
✓ Arquivo gerado: output/{language_lowercase}_phrases_{timestamp}.csv
  Áudio: output/{csv_stem}/  ({forvo_count} Forvo, {tts_count} TTS, {audio_failed} sem áudio)
  Expressões processadas: {total}
  Buscas web realizadas: {web_search_count}
  Não encontradas: {not_found_count}
```

Tell the user how to import: open Anki, drag every mp3 from `output/{csv_stem}/`
into the collection's media folder (or import the CSV with Anki's media handling),
then import the CSV. The `[sound:...]` field plays the audio on the card.

(Print the summary in the detected language or in English if the detected language is not easily writable in the terminal.)

List any expressions marked as not found, so the user knows to review them.
