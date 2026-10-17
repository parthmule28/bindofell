# Synthetic benchmark fixtures

These files are authored solely for offline engineering tests, not copied from
OMOP or any real benchmark. `toy_estate.json` has two fictional tables and eight
fields. `toy_cases.jsonl` has one example of each A/B/C label. Every committed
case is `provisional_curator`; the named "curator" and provenance are explicitly
synthetic placeholders, not real people or verified source observations. The
all-`a` source digest is a fictional test token, not a computed upstream hash.

`toy_rankings.jsonl` is deliberately constructed: A returns an accepted field,
B is empty and C has tied plausible fields. It is not output from retrieval or
classification. Candidate evidence references the same synthetic metadata.
Independent-role records created in unit tests exercise validation only and
are never released as independently validated gold.

Case/gold corpus revision 2 corrects the initial generic source excerpts to the
actual synthetic descriptions in the unchanged toy snapshot. Candidate excerpts
were corrected likewise. No original source evidence records are attached to
this generic snapshot; contextual validation checks its actual metadata content.
Unit tests attach explicit originals to exercise locator/attribute/ID integrity.
