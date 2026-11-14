from __future__ import annotations

from datetime import datetime, timezone


def build_report(title: str, methods: str, results: str, limitations: str) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"""# {title.strip() or 'GeneAI Research analysis report'}

**Generated:** {now}  
**Platform:** GeneAI Research

## Project information

Add project identifiers and dataset provenance here.

## Methods

{methods.strip() or 'Not provided.'}

## Results

{results.strip() or 'Not provided.'}

## Scientific interpretation

Interpretation requires review by a qualified researcher. This report does not provide clinical diagnosis or treatment guidance.

## Limitations

{limitations.strip() or 'Not provided.'}

## References

Add verified source references used in the analysis. No citations are generated automatically.

## Conclusion

Summarize conclusions only after checking the methods, data quality, and evidence.
"""
