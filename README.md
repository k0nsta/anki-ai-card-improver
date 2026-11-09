# AI Card Improver

An Anki desktop add-on that proposes clearer card fields through an OpenAI-compatible chat completions API. Review each field-level suggestion before applying it.

## Install

- For development, link the add-on folder into an Anki profile: `make link ADDONS="/path/to/Anki2/<profile>/addons21"`.
- To install a package, run `make package`, then in Anki choose **Tools → Add-ons → Install from file** and select `dist/anki_ai_improver.ankiaddon`.

Restart Anki after installing. Open **Tools → AI Card Improver Settings…** to configure the provider.

## Configuration

In **General**, set the provider's base URL (the API root, such as `https://openrouter.ai/api/v1`), model name, and API key. The add-on appends `/chat/completions` to the base URL. The key is stored in the add-on's ignored `user_files/secret.json` file with owner-only file permissions; it is not part of `config.json` or the package. The keyboard shortcut defaults to `Ctrl+Alt+J` and can be changed in the add-on configuration.

## Prompts

The default prompt works for any deck. Per-deck prompts should control the card's content only; the add-on supplies deck-agnostic output and formatting rules. See the [generic](docs/prompts/generic.md), [English](docs/prompts/english.md), and [European Portuguese](docs/prompts/portuguese.md) examples. Add or edit prompts in **Prompts**, then use the **Decks** tab to map a deck to a prompt; the closest deck or parent-deck mapping wins, and unmapped decks use the default.

## Quality gate

The optional quality gate asks an OpenRouter decisions model to check correctness, including facts, language, translations, code, and formulas. A low score triggers one repair request; it is off by default and only available with an OpenRouter base URL. The judge adds about $0.00002 and 0.3 s per check.

| Improvement model | Approximate cost | Typical latency |
| --- | ---: | ---: |
| `openai/gpt-6-luna` | ~$0.0005/card | ~8 s |
| `claude-haiku-5.5` | ~$0.001/card | — |

## Privacy

When you request an improvement, the note's field contents, note type, deck name, and tags are sent to the AI provider configured in settings. The provider processes that data under its own terms and privacy policy. Do not submit cards containing information you do not want that provider to receive.
