# Story Parser Framework

This folder contains the web/story parser framework for rebuilding
`Castorice.md` from primary story pages.

The target pages are messy: copied BWiki/MediaWiki pages often contain icon
filenames, collapsed blocks, repeated character names, flattened choices, and
branch dialogue without a clear tree. The framework is therefore staged instead
of being one monolithic script.

## Pipeline

1. `mirror.py`
   Downloads static HTML pages once. It can discover BWiki detailed dialogue
   links and next-story links from the downloaded HTML, then writes a manifest.

2. `extractors.py`
   Extracts visible text from HTML. It uses BeautifulSoup when available and
   falls back to the Python standard library.

3. `normalize.py`
   Removes web-copy noise, normalizes choice lines, repairs simple
   speaker/text line pairs, and converts text into typed lines.

4. `segment.py`
   Splits normalized lines into story sections and extracts dialogue records by
   speaker.

5. `writers.py`
   Writes cleaned Markdown and optional dialogue-only Markdown or JSONL.

6. `cli.py`
   Command-line entry point.

## Example

Mirror static pages first:

```powershell
python scripts/mirror_story_pages.py `
  --urls-file sources/story_urls.txt `
  --follow-links `
  --follow-types next_task `
  --min-version 3.0 `
  --max-version 4.0 `
  --output-dir sources/static_pages `
  --delay 2
```

`--follow-types next_task` means "follow 后续任务 only". Other relation links are
still written to `task_graph.json`, but they are not fetched automatically.
Pages outside the version range are kept as graph/manifest boundary nodes and
their HTML is not stored.

Later, parse locally as often as needed:

```powershell
python scripts/fetch_story_pages.py `
  --mirror-manifest sources/static_pages/manifest.json `
  --output sources/parsed_story.md `
  --dialogue-output sources/castorice_dialogue.md `
  --jsonl-output sources/castorice_dialogue.jsonl `
  --character 遐蝶
```

Generate a reviewable story Markdown preview from one mirrored HTML page:

```powershell
python scripts/parse_story_markdown.py `
  --html sources/static_pages/001_银辇啊_迅赴那黑色大地.html `
  --output sources/extracted/story_preview_001.md
```

Or parse pages from a manifest:

```powershell
python scripts/parse_story_markdown.py `
  --manifest sources/static_pages/manifest.json `
  --limit 1 `
  --output sources/extracted/story_preview.md
```

Verify a generated Markdown preview against its source HTML:

```powershell
python scripts/verify_story_markdown.py `
  --html sources/static_pages/001_银辇啊_迅赴那黑色大地.html `
  --markdown sources/extracted/story_preview_001.md `
  --output sources/extracted/coverage_report_001.md `
  --json-output sources/extracted/coverage_report_001.json
```

Batch parse and verify every mirrored page that has local HTML:

```powershell
python scripts/batch_story_markdown.py `
  --manifest sources/static_pages/manifest.json `
  --output-dir sources/extracted
```

This writes per-page Markdown to `sources/extracted/story_pages/`, per-page
coverage reports to `sources/extracted/coverage/`, and aggregate summaries to
`sources/extracted/coverage_summary.md` and `.json`.

When parsing from the mirror, omit `--url` if you do not want to refresh the
entry page. Keep `--url` only for a one-off live parse.

`sources/story_urls.txt` stores the current primary BWiki entry point.

## Evidence Caution

Parser output is still intermediate evidence. Review branch choices and
collapsed dialogue before using any line in `Castorice.md`.
