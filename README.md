# Claude Language Learning Skills

A [Claude Code](https://claude.com/claude-code) skill that turns a plain text list of foreign expressions into an Anki-importable CSV.

Cards are **monolingual**: every field is written in the target language, with no English. The goal is to stop translating in your head and start defining in the language you are learning.

For each expression, `anki-phrases` writes an explanation covering meaning, register, frequency, regional specificity, and connotation, plus five natural example sentences. Dictionaries rarely tell you that a phrase is common in São Paulo but confusing in Lisbon, which is exactly why this exists.

No scrapers, no backend, no API keys. One markdown file.

## Install

Copy the skill into a project, or into `~/.claude/skills/` to make it available everywhere:

```bash
git clone https://github.com/TBarmak/claude-language-learning-skills.git
cp -r claude-language-learning-skills/.claude/skills/* ~/.claude/skills/
```

## Use

```
/anki-phrases my_expressions.txt
```

Input is a plain text file, one expression per line. Blank lines and lines starting with `#` are ignored:

```
fazer vista grossa
dar uma mãozinha
# ainda não tenho certeza desta
chutar o balde
```

The language is detected from the list itself and printed back so you can confirm it. Output lands in `output/`.

## Output

Pipe-separated, no header row. Import into Anki with the field separator set to Pipe and "Allow HTML in fields" turned on.

```
fazer vista grossa|Fingir não ver algo, geralmente uma situação inconveniente ou ilegal. Registro informal. Expressão muito comum no Brasil, usada em todo o país.|O chefe fez vista grossa quando viu o funcionário chegar atrasado.<br>Ela fez vista grossa para os erros do irmão.<br>Às vezes é melhor fazer vista grossa do que criar confusão.
```

Columns: expression, explanation, examples. Example sentences are joined with `<br>` so they land in one field and render on one card.

## Design notes

A few things this skill does that are worth stealing for other generation skills:

- **Confidence gating.** The model assesses whether it actually knows an expression before writing about it. Low confidence triggers a web search in the target language first.
- **Fail loudly.** If an expression cannot be verified even after searching, the card is still written, carrying a visible warning instead of being silently dropped. A missing card you do not know about is worse than a card that admits it is unsure.
- **Self-validating output.** The format is fragile (a stray `|` shifts every column), so the skill checks its own rows against an explicit invariant before writing: exactly two pipes and four `<br>` per row.
- **Incremental visibility.** Expressions are processed one at a time with progress printed as it goes, so a long run can be watched and interrupted rather than blocking silently.
- **Nothing to approve.** The whole allowlist is three rules: `Bash(date:*)`, `WebSearch`, and `Write(output/**)`. Writing goes through the Write tool rather than shell redirection specifically so a long run does not stop to ask permission on every expression.

## Related

[Anki Lingo](https://github.com/TBarmak/anki-lingo) is the web app version of the same idea: React and Flask, with real scrapers instead of a model. Live at [anki.taylorbarmak.com](https://anki.taylorbarmak.com).
