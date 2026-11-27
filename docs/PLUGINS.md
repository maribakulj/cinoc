# Writing a Cinoc module (third-party plugin)

Cinoc has **one extension point**: a **pipeline brick** (segmenter, OCR/HTR,
VLM, LLM post-corrector, ALTO assembler, reading order, NER…). Everything
else — metrics, corpus importers, report sections, statistical tests — stays
**internal** and cannot be extended. One socket, no more.

## Built-in and plugins: **the same contract**, only the delivery differs

A built-in engine (`tesseract`, `kraken`, `pero`, `calamari`, `google_vision`,
`azure_di`…) and a third-party module implement **exactly the same** `Module`
protocol. The only difference:

| | Built-in | Plugin |
|---|---|---|
| Delivery | in the package (`cinoc/adapters/`), registered by `register_default_modules` | a separate distribution, found through its entry point — or registered by your own script (below) |
| Heavy dependency | an optional extra (`cinoc[kraken]`…) | a dependency of the plugin |
| Public mode (an exposed Space) | runnable when listed in `PUBLIC_ENGINE_KINDS` (free built-ins) | **disabled (fail-closed)**: no third-party code in-process |

Putting a brick in the package or in a plugin is a **packaging** choice, not a
contract one.

## A complete module

A module has a `name` (`<kind>:<label>`, the `adapter_name` a spec gives it),
a `version` (recorded in the run manifest), the artifact types it consumes and
produces, and `execute`. This one reads an image and produces raw text; the
recognition itself is a stand-in to replace with your engine. Everything else
is what a real module writes — the output file in the step's workspace, and
the `Artifact` that points to it:

<!-- example: plugin-module -->
```python
# my_ocr.py
from collections.abc import Mapping
from pathlib import Path
from typing import ClassVar

from cinoc.adapters.extension import (
    AdapterStepError,
    Artifact,
    ArtifactType,
    DeadlineExceeded,
    Module,
    Param,
    ParamValue,
    RunContext,
    RunControl,
    StepOutput,
    compute_content_hash,
    workspace_artifact_path,
)


def recognise(image: Path, model: str) -> str:
    """Replace with your engine. This stand-in returns a fixed line."""
    return "Lorem ipsum dolor sit amet"


class MyOCR:
    PARAMS: ClassVar[tuple[Param, ...]] = (
        Param("label", "str", "Libellé", "Label", required=True),
        Param("model", "str", "Modèle", "Model", default="base"),
    )

    def __init__(self, *, label: str, model: str = "base") -> None:
        self._label = label
        self._model = model

    @property
    def name(self) -> str:
        return f"my_ocr:{self._label}"  # must equal the spec's adapter_name

    @property
    def version(self) -> str:
        return "1.0"  # bump it when the output can change: archives key on it

    @property
    def input_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.IMAGE})

    @property
    def output_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.RAW_TEXT})

    def execute(
        self,
        inputs: dict[ArtifactType, Artifact],
        params: dict[str, ParamValue],
        context: RunContext,
        control: RunControl,
    ) -> StepOutput:
        control.raise_if_cancelled()
        if context.deadline.is_expired():
            raise DeadlineExceeded(f"{self.name}: time limit reached")
        image = inputs[ArtifactType.IMAGE]
        if image.uri is None or context.workspace_uri is None:
            raise AdapterStepError(f"{self.name}: needs an image file and a workspace")
        payload = recognise(Path(image.uri), self._model).encode("utf-8")
        # <workspace>/<document>.<label>.txt — the document id made file-safe
        out = workspace_artifact_path(
            context.workspace_uri, context.document_id, self._label, "txt"
        )
        out.write_bytes(payload)
        artifact = Artifact(
            id=f"{context.document_id}:{self.name}:raw_text",
            document_id=context.document_id,
            type=ArtifactType.RAW_TEXT,
            uri=str(out),
            content_hash=compute_content_hash(payload),
        )
        return StepOutput(artifacts={ArtifactType.RAW_TEXT: artifact})


def build_my_ocr(kwargs: Mapping[str, ParamValue]) -> Module:
    """The builder: a spec's `adapter_kwargs` for this brick in, the module out."""
    return MyOCR(label=str(kwargs["label"]), model=str(kwargs.get("model", "base")))
```

Everything a module needs is imported from `cinoc.adapters.extension`, the
public surface kept stable; what is not there is internal and may move. A
**segmenter** (`IMAGE → LAYOUT`) does not build its `CanonicalLayout` by hand:
it describes its detections (`LayoutDetection`, `DetectedRegion`) and returns
`layout_step_output(to_canonical_layout(detection, min_score=…), context,
self.name)` — that is what applies the score threshold, removes redundant
detections and sorts the regions into a deterministic reading order, the same
way as the built-in segmenters.

What the runner and the module promise each other: the runner provides every
`input_types` artifact, a `Deadline` and cooperative cancellation; the module
fills every one of its `output_types`, swallows no exception, raises
`DeadlineExceeded` when its time is up and an `AdapterStepError` (or a subclass)
when the page cannot be read — the unit then fails with that reason, the run
goes on. The `Artifact` id must be file-system safe (letters, digits and `_.-:/`), its
`content_hash` is the SHA-256 of what the file holds. Wrap
an external library to translate it into this protocol — **never** a second
internal contract.

## Using it without a package

`cinoc run` only sees modules that an **installed distribution** declares (the
entry point below). Without installing anything, a module is used from Python:
register its builder in a registry next to the built-ins, and run a spec with
that registry. This script is the whole of it — put it beside `my_ocr.py`:

<!-- example: plugin-script -->
```python
# run_my_ocr.py — python run_my_ocr.py run.yaml report.html
import sys
from pathlib import Path

from cinoc.app import load_run_spec, resolve_code_version, run
from cinoc.app.modules import ModuleRegistry, register_default_modules
from cinoc.reports import default_report_renderer

from my_ocr import build_my_ocr

registry = ModuleRegistry()
register_default_modules(registry)
registry.register_builder("my_ocr", build_my_ocr)

config, report = Path(sys.argv[1]), Path(sys.argv[2])
result = run(
    load_run_spec(config),
    registry=registry,
    code_version=resolve_code_version(),
    paths_root=config.parent,
)
report.write_text(default_report_renderer().render(result), encoding="utf-8")
for pipeline in result.pipelines:
    for score in pipeline.aggregate:
        print(pipeline.pipeline, pipeline.view, score.metric, score.value)
```

and give it a spec that names the brick (`adapter_name: "my_ocr:<label>"`):

<!-- example: plugin-spec -->
```yaml
# run.yaml — page_001.png and page_001.gt.txt beside it
corpus:
  name: my_pages
  documents:
    - id: page_001
      image_uri: page_001.png
      ground_truths:
        - {type: raw_text, uri: page_001.gt.txt}
pipelines:
  - name: my_ocr
    initial_inputs: [image]
    steps:
      - {id: ocr, kind: ocr, adapter_name: "my_ocr:base",
         input_types: [image], output_types: [raw_text]}
adapter_kwargs:
  "my_ocr:base": {label: base}
evaluation:
  views:
    - {name: texte, candidate_types: [raw_text], metric_names: [cer, wer]}
```

These three blocks are extracted from this page and run by Cinoc's test suite:
if they stop working, the suite fails.

## Packaging it: the entry point

To make the brick a `cinoc run` brick — and a web one on a private instance —
a distribution declares the builder in the `cinoc.modules` group:

```toml
# pyproject.toml of the plugin
[project]
name = "my-ocr"
version = "1.0"

[project.entry-points."cinoc.modules"]
my_ocr = "my_ocr:build_my_ocr"

[tool.setuptools]
py-modules = ["my_ocr"]
```

`pip install .` (or `pip install -e .` while you work on it — a local folder is
enough, nothing is published) and the kind `my_ocr` is registered **like a
built-in**, referable in any spec (`adapter_name: "my_ocr:base"`) and listed by
`cinoc list engines` — with the reason, when it fails to load.

## Declaring its settings (`PARAMS`) — optional, recommended

What a spec puts in `adapter_kwargs.<brick>` reaches the builder. Without a
declaration, nothing says which settings the brick reads: a typo (`modle`,
`min_scroe`) enters the spec, is read by nobody, and the run goes without it.
A brick therefore **declares** its settings, as a `ClassVar` on its class — the
same form as the built-in bricks:

```python
from typing import ClassVar
from cinoc.adapters.extension import Param


class MyOCR:
    PARAMS: ClassVar[tuple[Param, ...]] = (
        Param("label", "str", "Libellé", "Label", required=True),
        Param("model", "str", "Modèle", "Model", required=True),
        Param("min_score", "float", "Score minimal", "Minimum score",
              default=0.5, minimum=0.0, maximum=1.0),
        Param("token", "str", "Jeton", "Token", secret=True),
        Param("timeout", "float", "Délai (s)", "Time limit (s)",
              default=60.0, affects_output=False),
    )
```

| Field | Effect |
|---|---|
| `name`, `type` (`str`/`int`/`float`/`bool`) | a setting outside the list, or of another type, is **refused by name** — at `cinoc run --check`, at run time, when a spec is submitted on the web —, with the closest declared name (“did you mean `min_score`?”) |
| `label_fr`, `label_en` | the labels of `cinoc list engines my_ocr` and of the web settings fold |
| `default`, `required`, `choices`, `minimum`/`maximum` | default shown; a missing required setting, a value outside the choices or the bounds, refused |
| `secret=True` | never written: in the manifest, the report and the fingerprint, only the **fact** that it was given (`<secret>`); redacted from failure messages |
| `affects_output=False` | an **operational** setting: written to the manifest, but **outside** the step's fingerprint — changing it re-runs no archived unit (a time limit, the name of a key variable) |

The declaration is **read on the class** of the built module: it applies to a
third-party module without changing the builder. It is **optional** — this is
a public API, and a module written before it must keep running: without
`PARAMS` (or with `PARAMS = None`), settings stay free and nothing is checked;
a `token`, an `api_key`, a `password` are still masked by their name.
`PARAMS = ()` states “no setting”: any setting given is then refused. A
malformed declaration (a repeated name, a default of another type) is refused,
not ignored.

## Three obligations

1. **Public API** = a stability commitment: hence a single extension point
   (the pipeline brick).
2. **In-process execution**: in public mode, discovery is **disabled** (the
   safety of an exposed server).
3. **A declared version**: it goes to the manifest's `module_versions` and
   into the archive key (reproducibility).

## In the package, or a plugin?

- **In the package** (like `kraken`/`pero`/`calamari`): an established engine
  worth maintaining with the core; its heavy dependency as an extra; possibly
  runnable on a **private** Space.
- **A plugin**: an experimental or third-party module, or one you do not want
  in the core; installed separately, **disabled** on the public Space.

Both go through the **same** `Module` protocol.

---

## A third way: **no code at all** (`cli_layout`)

Before writing a module, ask: **does the tool already write PAGE-XML or
ALTO?** If so, there is nothing to write.

A segmenter's interface is not the tool, it is the **format**. Heritage work
has standardised on these two; a brick that reads *the format* plugs a whole
family of tools, where an adapter per *tool* plugs one.

```yaml
steps:
  - id: seg
    kind: segmentation
    adapter_name: cli_layout:eynollah
    input_types: [image]
    output_types: [layout]

adapter_kwargs:
  cli_layout:eynollah:
    label: eynollah
    command: "eynollah -i {image} -o {out} -m ~/models/eynollah"
```

`{image}` is the page, `{out}` an **empty** folder Cinoc allocates and cleans.
The tool writes **one** `.xml` file there; the dialect is recognised from its
content, not its extension.

#### Writing paths: **forward slashes, on all three systems**

The command is split by POSIX rules **everywhere**, Windows included. This is
deliberate: a spec is *reproducible data*, it must read the same on every
machine. Splitting by host rules would make the same spec two different
commands.

So the backslash is an **escape** character, never a path separator.

```yaml
command: "C:/Tools/eynollah.exe -i {image} -o {out}"    # ✅ Windows accepts it
command: "'C:/Program Files/x/seg.exe' -i {image}"     # ✅ a space → quotes
command: "C:\Tools\eynollah.exe -i {image}"             # ❌ refused at planning
```

The last form is **refused when the spec is built**, not quietly fixed:
without that refusal it silently became `C:Toolseynollah.exe`, and the user
read “command not found” without ever learning why.

The tools in view — eynollah, `kraken segment -bl`, the OCR-D processors,
dhSegment — all write PAGE-XML, and that is what makes them pluggable.
**tesseract, kraken, eynollah and an OCR-D processor have been plugged in for
real**, and that first contact found two defects that reading the code had
not.

The test suite, on the other hand, runs **none** of these tools, on purpose:
it checks the contract — splitting, reading both dialects, refusals —
against a fake tool, to stay fast and depend on no installation. What each
segmenter is *worth*, on a ground-truth corpus, remains to be measured.

### What the brick refuses, and why

| Refusal | Reason |
|---|---|
| **No shell.** The command is split (`shlex`) *before* substitution | A path containing `; rm -rf` stays **one argument**. Substituting first would let a second command be built. |
| **Zero or several `.xml`** produced | Picking one would make the result depend on file-system order — the determinism invariant falls. |
| **An XML without any region** | Well-formed but empty, it would give a blank page: a CER of 1.0 **without a message**. The worst failure mode of a benchmark. |
| **A backslash in the command** | Splitting is POSIX everywhere (a spec reads the same on every machine), so the backslash escapes: a Windows path pasted as is would be eaten **silently**. Refused at planning, with the form to write. |
| **Any call from the web** | See below. |

### Why the web always refuses it

`cli_layout` runs a command **written in the spec**. That is its purpose
locally, and over HTTP it would be a shell on offer.

The refusal (`cinoc.app.engines.CLI_ONLY_KINDS`) is therefore
**unconditional**: it does not depend on public mode. Public mode bounds an
*exposure*; this lock bounds a *capability*. “Private instance” means “people I
know”, not “people I hand a shell to”.

## OCR-D: a brick of its own, and why

OCR-D does not fit `cli_layout`, and that is instructive. Its processors do
**not** see an image: their unit is a *METS workspace*; they read one file
group and write another. Plugging them through `cli_layout` would take three
chained commands — a shell script, outside the repository, without tests or
refusals. It works, and it is tinkering.

The `ocrd` brick translates that contract:

```yaml
adapter_name: ocrd:segment
adapter_kwargs:
  ocrd:segment:
    label: segment
    processor: ocrd-tesserocr-segment
    bin_dir: ~/tools/ocrd-env/bin   # optional: otherwise the PATH
```

(A spec's settings are **flat** — string, number, boolean: a processor's own
parameters, an object, cannot be written there yet. The constructor accepts
them from Python; the spec does not.)

The gain is the same as with `cli_layout` — *one brick, one family*: the
hundred or so OCR-D processors (binarisation, deskewing, segmentation,
recognition) become a setting.

Scope, stated: **`IMAGE → LAYOUT`**. OCR-D also chains PAGE → PAGE; feeding a
layout back into a workspace is other work, which nothing asks for today.

> `ocrd-tesserocr-*` needs `TESSDATA_PREFIX` in the environment
> (`/opt/homebrew/share/tessdata` on macOS Homebrew). That is an installation
> matter, not a spec one: the brick does not build an environment.

### The general rule

Does the tool **already** speak PAGE or ALTO, in one command on one image?
→ `cli_layout`, one line of YAML.
Is its contract **something else** (a workspace, a library, its own format)?
→ an adapter, which translates that contract — and lives in the repository,
with its tests and its refusals.

### When to write an adapter anyway

- the tool is a **Python library**, not a command (no subprocess to start, no
  file to read back);
- it returns a format **of its own** (custom JSON, masks, tensors);
- it must be loaded **once** for a thousand pages — `cli_layout` restarts the
  command for every page, which rules it out for a heavy model.

Outside these three cases, one line of YAML is enough.
