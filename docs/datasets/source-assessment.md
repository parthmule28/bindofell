# Public Dataset Source Assessment

**Audit date:** 2026-10-17
**Purpose:** Select reproducible public or synthetic metadata for Bindofell v0.1. This document assesses source suitability; it does not turn source SQL into binding labels or establish rights beyond terms stated by the source.

## Decisions at a glance

| Source | Observed version or revision | Decision | Proposed role |
|---|---|---|---|
| [OMOP Common Data Model](https://github.com/OHDSI/CommonDataModel) | CDM v5.5.0, tag at commit `ba3dc1b` | **CONDITIONAL** | Primary metadata estate; package declares Apache 2.0; check component notices and redistribution obligations before bundling |
| [BIRD Mini-Dev](https://github.com/bird-bench/mini_dev) | GitHub README describes V2; Hugging Face snapshot `f65faf4` still displays 500 cases | **CONDITIONAL** | Manually re-annotated complementary cases after reconciling snapshot and database rights |
| [Spider 1.0](https://yale-lily.github.io/spider) | Official corrected release; latest correction noted 2020-08-03; archive digest not yet recorded | **CONDITIONAL** | Cross-domain schema-linking comparator; curate binding labels independently |
| [Jaffle Shop DuckDB](https://github.com/dbt-labs/jaffle_shop_duckdb) | `duckdb` branch at `36bde6c` (2026-03-02) | **DEFER** | Future derived-binding and lineage experiments |
| [DuckDB TPC-DS extension](https://duckdb.org/docs/stable/core_extensions/tpcds) | DuckDB / in-tree extension v1.5.6 is the latest release listed on 2026-10-17 | **CONDITIONAL** | Optional schema-only structural stress suite after terms and binary digest are recorded |
| [WDC SMB: SOTAB-SM](https://webdatacommons.org/structureddata/smb/) | Initial public release 2023-11-29; `SOTAB_SM_V500.zip` | **DEFER** | Separate schema-matching comparison only |
| [WDC SMB: T2D-SM](https://webdatacommons.org/structureddata/smb/) | Initial public release 2023-11-29; `T2D_SM_WH.zip` and `T2D_SM_NH.zip` | **DEFER** | Separate schema-matching comparison only |

**Primary recommendation:** use OMOP CDM v5.5.0 as the first metadata adapter candidate, with a fetch-and-hash script and local source files by default. Its versioned `DESCRIPTION` declares Apache License 2.0; this is positive package-license evidence, subject to the component and notice checks below before bundling upstream material. It offers the richest versioned table and field descriptions among the assessed sources. It has no natural-language business-to-field gold labels, so cases need separate human curation. A solo curator may produce the explicitly provisional pilot defined in the [benchmark specification](../design/0002-benchmark-v0.1.md); independently validated gold requires the full independent review process.

**Complementary suites:** use a manually curated subset of BIRD Mini-Dev and Spider only after selecting exact archives and separately annotating field targets. Use TPC-DS only for deterministic candidate-universe size/structure checks, never as labeled business-binding evidence. Keep WDC SOTAB-SM and T2D-SM as schema-matching comparators, not as substitutes for Tasks A–C. Reserve Jaffle Shop DuckDB for a later derived-binding track.

## Assessment method and rights handling

The source pages linked below were checked for release information, file formats, schema fields, task labels and license statements. A source page being public or downloadable does not by itself establish redistribution rights. Where the source does not state applicable terms clearly, the implementation should fetch it locally, record the exact source revision and a SHA-256 digest, and avoid committing the downloaded files until terms are resolved. The data lock manifest should identify the source URL, version or commit, retrieval date, archive/file digests, and the adapter version.

Counts below are reported only where the source exposes them. “Not verified” means do not infer the count from a preview's physical line count or from benchmark tables with different scopes. A deterministic import should emit the actual table and field counts for the pinned files and save them in the run manifest.

## OMOP Common Data Model

- **Canonical source and owner:** [OHDSI CommonDataModel repository](https://github.com/OHDSI/CommonDataModel), with the versioned specification at [OHDSI Common Data Model documentation](https://ohdsi.github.io/CommonDataModel/).
- **Version/revision:** use release tag `v5.5.0`, resolved to full commit `ba3dc1b651cc243279052bca3d051485c3ec1136`, for the initial adapter. The [GitHub release](https://github.com/OHDSI/CommonDataModel/releases) marks v5.5 as the current released version; the [versioned field CSV](https://github.com/OHDSI/CommonDataModel/blob/v5.5.0/inst/csv/OMOP_CDMv5.5_Field_Level.csv) and [table CSV](https://github.com/OHDSI/CommonDataModel/blob/v5.5.0/inst/csv/OMOP_CDMv5.5_Table_Level.csv) are the intended inputs. Record both source-file hashes at acquisition.
- **Format and metadata:** `OMOP_CDMv5.5_Field_Level.csv` includes table and field names, requiredness, datatype, user guidance, ETL conventions, primary/foreign-key flags, referenced table/field, foreign-key domain and class. `OMOP_CDMv5.5_Table_Level.csv` includes table name, schema, requiredness, validation fields, table description, user guidance and ETL conventions. Version-specific DDL and constraint files are also available. The source maintainer states that the CSV files are the source of truth for model structure and documentation.
- **Tables and fields:** 42 tables are listed in the official v5.5 specification, counting its six table groups. The CSV preview reports 610 lines / 592 code lines, which is not a verified field-row count; the field count must be computed from the pinned CSV by the adapter and recorded in its manifest.
- **Existing natural-language labels and ground truth:** no natural-language business requirements or binding annotations. Field/table guidance is source metadata, not a benchmark query. No mapping from a business term to a field is provided.
- **Relationships and keys:** field-level primary/foreign-key flags and target metadata are present; versioned DDL/constraint scripts provide additional relationship definitions. OMOP also has semantic conventions and concept identifiers, but no patient rows are needed for this metadata-only estate.
- **Access:** public GitHub source; no account is required for the repository files. Pin the tag, resolve the full commit and hash the two CSVs. Do not use a moving `main` URL for a benchmark run.
- **License and redistribution:** the [release-pinned `DESCRIPTION`](https://github.com/OHDSI/CommonDataModel/blob/ba3dc1b651cc243279052bca3d051485c3ec1136/DESCRIPTION) declares `License: Apache License 2.0`. This corrects the earlier omission: package-level license evidence exists. The release-tree filename check found no separate `LICENSE`, `NOTICE`, `COPYING`, or similarly named component file; it does not establish that every embedded or externally acquired component has identical terms. Before redistributing the CSVs or copied descriptions, check the selected files for component-specific notices and comply with [Apache 2.0 section 4](https://www.apache.org/licenses/LICENSE-2.0): include the license, retain applicable source notices and NOTICE content, and mark modifications. External vocabularies or other separately acquired assets need their own terms check. Public availability alone grants no additional rights. B00 includes no upstream copies; local fetch-and-hash remains the default while these packaging checks are completed.
- **Reproducibility:** strong for the schema snapshot when the release tag, full commit SHA, CSV digests and parser version are locked. Record the source-reported version separately from the Bindofell snapshot ID.
- **Suitability:** high for direct field retrieval after independent query authoring; moderate for ambiguity cases because concepts, identifiers and temporal fields recur across tables; feasible for bounded no-match cases if annotators explicitly scope “no match” to this exact estate. Some derived concepts have standardized fields/tables, but there is no complete formula or lineage gold set, so derived-KPI evaluation remains future work.
- **Risks and limits:** the domain is observational health data, its terms are precise and specialized, and many fields differ by event type, time role or concept domain. It is a standard data dictionary, not an enterprise KPI catalog. Do not claim clinical expert validation without qualified, documented annotators.
- **Decision:** **CONDITIONAL**, recommended primary source for the first adapter. Apache 2.0 is the declared package license; the remaining redistribution gate is checking the selected components and satisfying notice obligations, rather than locating a missing package license.

## BIRD Mini-Dev

- **Canonical source and owner:** [BIRD Mini-Dev repository](https://github.com/bird-bench/mini_dev) and the project-designated [Hugging Face dataset](https://huggingface.co/datasets/birdsql/bird_mini_dev), maintained by the BIRD team.
- **Version/revision:** the GitHub README announces Mini-Dev V2 on 2025-07-22 and describes 780 text-to-SQL instances, including 500 selected original cases plus 270 new cases. Those component counts sum to 770, not 780. The Hugging Face viewer still presents 500 rows per engine split across 11 database IDs at snapshot abbreviation `f65faf4`. This is a source/version discrepancy; do not silently treat the two views as one release. Pin one immutable Hugging Face revision and the exact complete database package before admitting any subset.
- **Format and metadata:** questions and SQL/evidence are JSON records; each database package includes SQLite files and `database_description` CSVs that describe schema and values. The Hugging Face splits also provide engine-specific SQL representations. The repository says questions were crowdsourced, evidence was expert-annotated, and SQL was crowdsourced with reference to descriptions and database contents.
- **Tables and fields:** the currently indexed 500-case HF view exposes 11 database IDs. The count of tables and fields in each database is not given in the indexed dataset page; compute and manifest it from the selected complete package. Do not treat the stated 18 “new databases” in the V2 note as the total Mini-Dev database count.
- **Existing natural-language labels and ground truth:** natural-language questions, evidence and reference SQL exist. SQL is ground truth for text-to-SQL execution, not a complete or independently reviewed business-to-field mapping. A field mentioned in SQL can be a filter, join key, grouping key, projection, or intermediate and is not automatically a correct binding label.
- **Relationships and keys:** actual SQLite schemas expose table columns and database constraints when available; descriptions CSVs provide column descriptions/examples. Inspect the pinned package rather than assume every database records all constraints.
- **Access:** public Hugging Face rows; the repository README points to a complete database package through Hugging Face and external Google Drive/Alibaba links. Record the resolved revision and archive digest for the selected engine/package. Do not rely on the mutable `main` alias.
- **License and redistribution:** the Hugging Face dataset card declares CC BY-SA 4.0. This assessment did not verify separate terms for every underlying database or external package. Preserve attribution and share-alike requirements; do not redistribute a database package until its component terms are checked.
- **Reproducibility:** good after selecting a specific HF revision, engine and database archive, but current V2/readme/viewer inconsistency blocks an unambiguous initial lock.
- **Suitability:** useful for complementary business-like questions, synonym/abbreviation cases and manual field-target annotation. SQL and evidence can help curators locate candidate fields but cannot be used as gold without independent review. Derived formulas may be studied later only with a separate annotation. No-match and clarification labels must be curated against the chosen local schema snapshot.
- **Risks and limits:** SQL contains more than the intended semantic target; natural-language questions may require values or joins; database descriptions include data examples; database package rights vary; the V2 row totals conflict.
- **Decision:** **CONDITIONAL** for a manually annotated complementary subset after the V2/HF version is reconciled and database rights are reviewed.

## Spider 1.0

- **Canonical source and owner:** [Yale Spider task site](https://yale-lily.github.io/spider/) and [taoyds/spider code repository](https://github.com/taoyds/spider), created by the Spider research team.
- **Version/revision:** Spider 1.0. The official code README notes annotation updates on 2020-06-07 and corrected table/column-name mismatches in two schemas on 2020-08-03; obtain the corrected archive from the official task site and record its digest. The code repository's Apache license applies to the code; the task site states the dataset is CC BY-SA 4.0.
- **Format and metadata:** split JSON files contain questions and SQL annotations; `tables.json` has original and normalized table/column names, broad column types, primary-key column indices, and foreign-key column-index pairs. SQLite databases hold table contents.
- **Counts:** the task site reports 10,181 questions, 5,693 unique complex SQL queries, 200 databases and 138 domains. It does not expose a single aggregate field count in the reviewed page; count tables/fields from the pinned schemas on ingestion.
- **Existing natural-language labels and ground truth:** natural-language questions and reference SQL; the direct benchmark target is semantic parsing / text-to-SQL. SQL references do not by themselves establish business-binding gold labels.
- **Relationships and keys:** primary and foreign keys are encoded in `tables.json`, and database files are available. Descriptive table/column documentation is limited compared with OMOP.
- **Access:** public archive linked from the task site; no credentials are described. Pin the downloaded archive and separate it from the Apache-licensed baseline code.
- **License and redistribution:** the official task site states CC BY-SA 4.0 for the dataset. Preserve required attribution/share-alike terms. Do not include a dataset copy in Bindofell until the selected archive and its component contents are checked.
- **Reproducibility:** schema and split format are stable, but there is no release commit for the downloadable archive; record the archive SHA-256 and official correction date.
- **Suitability:** useful as a cross-domain schema-linking source and as a manually annotated complementary suite. It is not a governed KPI benchmark. Curators must independently choose valid direct bindings, no-match and clarification cases from the provided schema.
- **Risks and limits:** sparse schema descriptions make “business meaning” annotation less grounded; generated SQL may touch several fields for different semantic roles; benchmark train/test distinctions should not be reused as Bindofell gold labels.
- **Decision:** **CONDITIONAL** for a small, manually re-annotated schema-linking comparison; not the primary estate.

## Jaffle Shop DuckDB

- **Canonical source and owner:** [dbt-labs/jaffle_shop_duckdb](https://github.com/dbt-labs/jaffle_shop_duckdb), maintained by dbt Labs.
- **Version/revision:** `duckdb` branch, tip `36bde6c` dated 2026-03-02 on the repository's commit history. Pin that commit rather than the branch. The repository describes itself as a self-contained dbt playground with five models.
- **Format and metadata:** dbt project, SQL models, YAML documentation/tests, fictional customer/order/payment seeds, and an ER diagram. `ref()` relationships can be read from the project graph. A local build can materialize models and generate dbt documentation.
- **Tables and fields:** the source describes three raw seed entities and five models; exact materialized table/field counts must come from a pinned local `dbt build` manifest because configuration and adapter versions determine outputs.
- **Existing natural-language labels and ground truth:** no business requirement query set or binding gold set. Model docs and SQL are transformation metadata, not human binding labels.
- **Relationships and keys:** dbt `ref` dependencies express model-level lineage; model SQL exposes column-level derivation. Inspect generated manifest/catalog for exact column lineage rather than assume every SQL expression resolves to complete lineage.
- **Access:** public GitHub repository; local setup and DuckDB build instructions are provided.
- **License and redistribution:** GitHub identifies the repository as Apache-2.0. The data is described as fake and fictional. Keep license and attribution notices if distributing copied files.
- **Reproducibility:** reasonable when commit, `uv.lock`, dbt, adapter and DuckDB versions are pinned; run `dbt seed`, `dbt build` and capture the output catalog/manifest.
- **Suitability:** poor as a first direct-binding gold source because there are no NL prompts; valuable future fixture for source-to-derived bindings, transformation evidence and lineage checks. No-match/ambiguity examples would be authored artificially and should be labeled accordingly.
- **Risks and limits:** deliberately small demonstration project and not a realistic enterprise estate or standards benchmark; adds a dbt runtime stack not needed for the initial retrieval baseline.
- **Decision:** **DEFER** to a derived-binding/lineage track.

## TPC-DS through DuckDB

- **Canonical source and owner:** TPC-DS benchmark schema generated by DuckDB's official [`tpcds` core extension](https://duckdb.org/docs/stable/core_extensions/tpcds).
- **Version/revision:** at the 2026-10-17 audit date, DuckDB's release calendar lists v1.5.6 (2026-09-28) as the latest release; pin DuckDB v1.5.6 and its matching in-tree `tpcds` extension binary. The extension is tied to the DuckDB version/platform. Record its downloaded binary digest and platform. The docs warn that the generator changes in DuckDB 2.0 for TPC-DS version 4; do not cross that boundary without a new snapshot.
- **Format and metadata:** `CALL dsdgen(sf = 0)` produces schema without rows. The `keys` parameter controls whether primary/foreign keys are generated. The extension also exposes 99 reference queries; they are not labels for business-to-field mapping.
- **Tables and fields:** the docs do not provide a versioned generated-catalog count. Record exact table, field and key counts from the v1.5.6 generated catalog; no count is asserted here.
- **Existing natural-language labels and ground truth:** none. Reference SQL queries are workload examples, not gold mappings.
- **Relationships and keys:** can generate primary/foreign keys by setting `keys = true`.
- **Access:** DuckDB extension installation is public and requires network access on first install unless the matching extension binary is cached locally.
- **License and redistribution:** DuckDB docs explain extension distribution but do not settle TPC-DS benchmark terms or redistribution rights for all generated assets. Treat these rights as unresolved; do not redistribute queries or generated data. Schema-only local use also requires terms review before public packaging.
- **Reproducibility:** strong after pinning DuckDB, platform-specific extension binary digest, generator invocation/options and resulting catalog manifest. Avoid the moving `stable` docs as the only lock.
- **Suitability:** good for schema-size, key-density and candidate-universe stress tests; poor for semantic labels, no-match/clarification gold, or direct/derived semantic-binding accuracy.
- **Risks and limits:** generator version changes alter schema; SQL query workload is not binding ground truth; extension requires a compatible binary and its license terms are separate from the docs.
- **Decision:** **CONDITIONAL** for optional structural stress tests after licensing and binary pinning; exclude from the primary benchmark.

## WDC Schema Matching Benchmark — SOTAB-SM

- **Canonical source and owner:** WDC SMB by Reng Chiz Der and Christian Bizer, hosted by [Web Data Commons](https://webdatacommons.org/structureddata/smb/).
- **Version/revision:** initial public release announced 2023-11-29; select the hosted `SOTAB_SM_V500.zip` variant and record its digest, since the web page does not supply a Git commit or numbered archive release.
- **Format and metadata:** compressed JSON-lines tables; column headers are replaced by column indices. Correspondence CSVs label pairs as matching/non-matching. Tables contain schema.org structured data harvested from the September 2020 Common Crawl version.
- **Counts:** the 500-table variant spans 16 topical domains, 3–29 columns per table, 4,228 positive and 24,787 negative correspondences (29,015 combined). The page separately describes a 20-table test set with 1,522 positive and negative correspondences. Treat those as different stated scopes and preserve both figures.
- **Existing natural-language labels and ground truth:** no NL business requirements. Gold is pairwise schema-column correspondence derived from CPA/property labels and sampled positive/negative correspondences.
- **Relationships and keys:** no relational PK/FK graph is described; table-pair correspondence files are the relevant structure.
- **Access:** public zip download from the WDC SMB page; pin local bytes by digest.
- **License and redistribution:** no explicit dataset license was located on the benchmark page during this audit. Rights are unresolved; local-only acquisition and no redistribution pending clarification.
- **Reproducibility:** fixed published splits and hosted files help; archive digest and exact variant are still required.
- **Suitability:** use only as a separate schema-matching comparator. Pairwise column correspondences are not natural-language-to-field bindings; negative correspondences do not mean a business query has no representation, and the labels do not express clarification needs.
- **Risks and limits:** web-table data and headers are source-derived; task differs materially from governed metadata retrieval; stated test-set and full-corpus counts should not be conflated.
- **Decision:** **DEFER** from v0.1 binding evaluation; revisit only for a clearly separated schema-matching comparison after rights review.

## WDC Schema Matching Benchmark — T2D-SM

- **Canonical source and owner:** WDC SMB by Reng Chiz Der and Christian Bizer, hosted by [Web Data Commons](https://webdatacommons.org/structureddata/smb/).
- **Version/revision:** initial public release announced 2023-11-29. The two official files are `T2D_SM_WH.zip` (with headers) and `T2D_SM_NH.zip` (without headers); record a digest for the chosen variant.
- **Format and metadata:** CSV tables for web and DBpedia-derived tables plus correspondence CSVs. WH retains column headers; NH removes them. The source describes filtering DBpedia properties and manually reviewing candidate column pairs.
- **Counts and source discrepancy:** the introduction reports 178 web-table/DBpedia-table pairs over 28 DBpedia classes and 421 correspondences. The profile table reports 356 tables, 445 positive and 2,197 negative correspondences. Preserve both reported figures and their scopes as unresolved source discrepancy; do not rewrite one to match the other.
- **Existing natural-language labels and ground truth:** no NL business requirements. Gold is binary, pairwise column correspondence; it is not no-match or clarification gold.
- **Relationships and keys:** table pairs and semantic correspondences are provided; no standard physical PK/FK constraints are described as labels.
- **Access:** public zip downloads from WDC SMB; pin chosen archive by digest.
- **License and redistribution:** no explicit dataset license was located on the benchmark page during this audit. Rights are unresolved; local-only acquisition and no redistribution pending clarification.
- **Reproducibility:** fixed train/validation/test splits, strict table split and downloadable files; capture archive digest and variant.
- **Suitability:** appropriate only for a separate column schema-matching comparison, especially header/no-header behavior. It cannot stand in for natural-language direct binding, no-match or clarification evaluation.
- **Risks and limits:** correspondence statistics conflict between the intro and profile sections; DBpedia versioning and archive licensing need separate review; its task uses instance/header signals unlike Bindofell's metadata-only v0.1 input.
- **Decision:** **DEFER** from v0.1 binding evaluation; revisit only for a clearly separated schema-matching comparison after rights review.

## Dataset selection outcome

1. Carry OMOP v5.5.0 forward as the primary **candidate** estate. The first adapter should use only versioned field/table metadata, not patient data. Record the Apache 2.0 declaration, complete component/notice checks before bundling, and prefer source/version/checksum reconstruction logic over upstream copies.
2. Start with a 15–20 case OMOP pilot, explicitly graded provisional curator-grade when independent reviewers are unavailable. Expansion toward 100 cases depends on source evidence and label feasibility; an independently validated gold release additionally requires two independent annotations and adjudicator sign-off.
3. Treat BIRD and Spider SQL as curator navigation evidence only. Human curators must inspect the snapshot without evaluated retrieval rankings; label the annotation grade honestly and require independent review before calling a release independently validated gold.
4. Keep Jaffle Shop for a future derived-binding track; use TPC-DS only for schema-only structural tests after term/version locks; keep both WDC tasks in their own task category.
5. Re-open the conditional decisions when source snapshots, component terms, or source counts change. A changed upstream source creates a new Bindofell estate snapshot and requires explicit benchmark migration review.
