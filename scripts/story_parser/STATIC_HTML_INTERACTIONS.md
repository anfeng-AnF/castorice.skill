# Static HTML Interaction Notes

## Conclusion

The downloaded BWiki story HTML does not preserve the page's clickable UI
behavior, but it can still preserve the underlying branch data.

For the checked page, the choice UI is already embedded in the static HTML. The
browser interaction mainly switches which pre-existing block is visible; it does
not appear to request the branch text from the server at click time.

## Mental Model

Treat a BWiki choice block like a small UI data structure:

```text
plotFrame
  plotOptions[0..n]  -> player choice labels
  content[0..n]      -> response blocks matched by index
  plotActive/contentA -> initially visible item
```

In C++ terms, it is closer to:

```cpp
struct ChoiceBlock {
    std::vector<std::string> options;
    std::vector<std::string> responses;
    int activeIndex;
};
```

The web page changes `activeIndex` when the user clicks. A parser does not need
to simulate those clicks if all `options` and `content` nodes are present in the
HTML.

## Observed Example

Local file:

```text
sources/static_pages/001_银辇啊_迅赴那黑色大地.html
```

Around the checked block, the HTML contains:

- one `plotFrame`
- three `plotOptions`
- three sibling `content` blocks
- the first option marked with `plotActive`
- the first response marked with `contentA`

The visible page only shows one branch at a time, but the downloaded HTML
contains the sibling branches as hidden/inactive content.

## Parser Requirement

When parsing static HTML, do not flatten this block into unrelated lines.
Instead:

1. Locate each `plotFrame`.
2. Read all direct `plotOptions` in order.
3. Read all matching `content` blocks in order.
4. Pair them by index.
5. Mark the active/default branch separately.

Expected intermediate output shape:

```json
{
  "type": "choice_block",
  "active_index": 0,
  "branches": [
    {"choice": "...", "response": "...", "active": true},
    {"choice": "...", "response": "...", "active": false}
  ]
}
```

## When Browser Automation Is Needed

Static HTML is not enough only if the branch text is absent from the downloaded
file and appears only after a click triggers an additional network request.

Signs that browser automation may be required:

- the HTML has choice labels but no corresponding `content` blocks
- click handlers reference an API endpoint for dialogue content
- the page fills dialogue nodes after load using fetched JSON

For the checked BWiki block, this was not the case.
