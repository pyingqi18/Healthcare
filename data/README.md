# Data Layers

```text
external   Frozen third-party source files such as NPPES
raw        Immutable API responses and review-level acquisitions
interim    Parsed, linked, and quality-checked intermediate data
processed  Frozen analysis datasets with documented schemas
```

Do not overwrite raw files. Every processed dataset should record its input versions and build timestamp.
