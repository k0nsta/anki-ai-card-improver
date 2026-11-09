# AI Card Improver

An Anki desktop add-on that proposes clearer card fields through an OpenAI-compatible chat completions API. Review each field-level suggestion before applying it.

## Install

- For development, link the add-on folder into an Anki profile: `make link ADDONS="/path/to/Anki2/<profile>/addons21"`.
- To install a package, run `make package`, then in Anki choose **Tools → Add-ons → Install from file** and select `dist/anki_ai_improver.ankiaddon`.

Restart Anki after installing. Open **Tools → AI Card Improver Settings…** to configure the provider.

## Configuration

In **General**, set the provider's base URL (the API root, such as `https://openrouter.ai/api/v1`), model name, and API key. The add-on appends `/chat/completions` to the base URL. The key is stored in the add-on's ignored `user_files/secret.json` file with owner-only file permissions; it is not part of `config.json` or the package.

In **Prompts**, create and edit instructions, and choose a default prompt. In **Decks**, optionally assign a prompt to a deck; the closest matching deck or parent-deck mapping is used, then the default. The keyboard shortcut defaults to `Ctrl+Alt+J` and can be changed in the add-on configuration.

Example prompt text:

```text
English: Correct factual and spelling errors. Make the card clear and concise. Preserve the meaning, field language, and HTML formatting.

Português: Corrija erros factuais e ortográficos. Deixe o cartão claro e conciso. Preserve o significado, o idioma de cada campo e a formatação HTML.
```

Use the language-specific prompt that fits your cards; prompts can be assigned to decks independently.

## Privacy

When you request an improvement, the note's field contents, note type, deck name, and tags are sent to the AI provider configured in settings. The provider processes that data under its own terms and privacy policy. Do not submit cards containing information you do not want that provider to receive.
