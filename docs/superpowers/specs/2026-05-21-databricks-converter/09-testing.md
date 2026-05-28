# 09 — Testing

[← Index](./README.md)

## Pyramid

```
                  ┌─────────────────────────────┐
                  │  Integration (~10 tests)    │  Real LLM, gated by env var
                  │  - end-to-end per format    │  CI: skipped, local: opt-in
                  └─────────────────────────────┘
              ┌──────────────────────────────────┐
              │  Agent (~15 tests)               │  Mocked LLM via FakeChatModel
              │  - tool dispatch, FS state       │  Deterministic, fast
              │  - subagent invocation paths     │
              └──────────────────────────────────┘
       ┌────────────────────────────────────────────┐
       │  Extractor unit (~40 tests)                │  No LLM, no network
       │  - IR shape per fixture file               │  Fast (< 5s total)
       │  - edge cases per format                   │  Most of the suite
       └────────────────────────────────────────────┘
```

## Extractor unit tests — golden IR snapshots

```python
# tests/unit/test_extractors_pptx.py
import json, pytest
from any2md.extractors.pptx import PptxExtractor

FIXTURES = "tests/fixtures"

def test_simple_pptx_ir_shape():
    result = PptxExtractor().extract(f"{FIXTURES}/simple.pptx")
    assert result.ir["format"] == "pptx"
    assert result.ir["slide_count"] == 3
    slide_1 = result.ir["slides"][0]
    assert slide_1["title"] == "Introduction"
    assert len(slide_1["shapes"]) == 4
    assert [s["order"] for s in slide_1["shapes"]] == [0, 1, 2, 3]

def test_pptx_with_chart():
    result = PptxExtractor().extract(f"{FIXTURES}/with_chart.pptx")
    chart_shape = find_shape(result.ir, type="chart", slide=2)
    assert chart_shape["chart_type"] == "bar"
    assert chart_shape["categories"] == ["Q1", "Q2", "Q3", "Q4"]

def test_pptx_with_smartart_hierarchy():
    result = PptxExtractor().extract(f"{FIXTURES}/smartart_hierarchy.pptx")
    sa = find_shape(result.ir, type="smartart", slide=1)
    assert sa["layout_kind"] == "hierarchy"
    assert sa["nodes"][0]["text"] == "CEO"

def test_pptx_image_position_context():
    result = PptxExtractor().extract(f"{FIXTURES}/with_images.pptx")
    img_shape = find_shape(result.ir, type="image", slide=2)
    assert img_shape["image"]["container"]["kind"] == "pptx_slide"
    assert img_shape["image"]["container"]["index"] == 2
    assert img_shape["image"]["neighbors"]["before_kind"] == "heading_h2"

def test_pptx_grouped_shapes_with_connectors():
    result = PptxExtractor().extract(f"{FIXTURES}/flowchart_grouped.pptx")
    group = find_shape(result.ir, type="group", slide=1)
    assert group["diagram_hint"] == "flowchart"
    connectors = [c for c in group["children"] if c["type"] == "connector"]
    assert len(connectors) >= 2

def test_encrypted_pptx_raises():
    with pytest.raises(EncryptedFileError):
        PptxExtractor().extract(f"{FIXTURES}/encrypted.pptx")
```

**Golden snapshot pattern** for complex IRs using `syrupy`:

```python
def test_complex_docx_matches_golden(snapshot):
    result = DocxExtractor().extract(f"{FIXTURES}/complex.docx")
    snapshot.assert_match(json.dumps(result.ir, indent=2, ensure_ascii=False))
```

Update goldens after intentional extractor changes: `pytest --snapshot-update`.

## Agent unit tests — mocked LLM

```python
# tests/unit/test_agent_tools.py
from langchain_core.language_models.fake_chat_models import FakeListChatModel

def test_caption_image_tool_lookups_from_captions_json():
    options = ConvertOptions(text_model=ModelConfig(instance=FakeListChatModel(
        responses=['{"tool": "caption_image", "args": {"image_id": "img_1"}}', ...]
    )))
    agent = build_deep_agent(options)
    state = {
        "files": {
            "/ir.json": json.dumps({"format": "pptx", "slides": [...]}),
            "/captions.json": json.dumps({"img_1": "Doanh thu Q1"}),
        }
    }
    # invoke and assert the tool returned the cached caption

def test_main_agent_writes_markdown_then_finalizes(): ...
def test_quality_reviewer_fills_missing_block(): ...
def test_oversized_chunk_warning_propagates(): ...
```

## Integration tests — real LLM, opt-in

```python
# tests/integration/test_convert_end_to_end.py
pytestmark = pytest.mark.skipif(
    not os.getenv("CONVERTER_INTEGRATION_TESTS"),
    reason="Set CONVERTER_INTEGRATION_TESTS=1 to run (uses real LLM tokens)",
)

@pytest.mark.parametrize("fixture", [
    "simple.pptx", "with_chart.pptx", "flowchart_grouped.pptx",
    "simple.docx", "complex.docx",
    "simple.xlsx",
    "text.pdf", "scanned.pdf", "mixed.pdf",
    "simple.html",
    "simple.md", "multi_lang.md",
])
def test_end_to_end(fixture):
    result = convert(f"tests/fixtures/{fixture}")
    assert result.markdown
    assert result.format == fixture.split(".")[-1].replace("md", "markdown")
    assert "[Image: caption unavailable]" not in result.markdown
    if "chart" in fixture:
        assert "| Q1 |" in result.markdown
    if "flowchart" in fixture:
        assert "```mermaid" in result.markdown
    if fixture == "scanned.pdf":
        assert len(result.markdown) > 500
```

Gated by env var so CI does not consume tokens. Local dev: `CONVERTER_INTEGRATION_TESTS=1 pytest tests/integration/`.

## Fixtures

Committed in `tests/fixtures/`, regenerated by `build_fixtures.py`. Target each file under 50KB.

| File | Purpose |
|---|---|
| `simple.{xlsx,docx,pptx,pdf,html,md}` | Baseline per format |
| `with_chart.pptx` | Chart extraction |
| `smartart_hierarchy.pptx` | SmartArt parsing |
| `flowchart_grouped.pptx` | Connector-grouped flowchart |
| `encrypted.pptx` | Error path |
| `complex.docx` | Multi-column, textboxes, equations |
| `merged_cells.xlsx` | Merged cells, hidden sheet, formulas |
| `text.pdf`, `scanned.pdf`, `mixed.pdf` | PDF variants |
| `multi_lang.pptx`, `multi_lang.md` | vi + en mixed text |
| `multi_lang_image.pdf` | Vietnamese context + English screenshots |

## CI

```yaml
# .github/workflows/test.yml (sketch)
jobs:
  unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -e ".[dev]"     # no provider extras — core must work alone
      - run: ruff check src tests
      - run: mypy src
      - run: pytest tests/unit -v
```

Integration tests NOT in default CI — manual `workflow_dispatch` only.

## Quality benchmark (manual, periodic)

Reference set of ~10 human-curated golden markdown files; track BLEU / ROUGE drift on prompt or model changes. Not pass/fail — drift tracking only. Results logged to `benchmarks/<date>-<model>-<commit>.json`.
