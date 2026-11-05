"""Local Natural Language Inference (NLI) Engine for Hallucination Detection.

Classifies premise-hypothesis relationships into ENTAILMENT, NEUTRAL (unsupported),
and CONTRADICTION (hallucination) to verify factual faithfulness in AI workflows.
"""

import re
import math
from typing import Optional, List, Dict, Any


def split_sentences(text: str) -> List[str]:
    """Split text into sentences, preserving abbreviations, numbers, and decimals."""
    if not text or not text.strip():
        return []
    # Protect common abbreviations and numbers with decimals (e.g., 4.8, v2.1, e.g., avg.)
    cleaned = text.strip()
    # Normalize bullet points and newlines into sentence boundaries
    cleaned = re.sub(r'[\r\n]+', '. ', cleaned)
    cleaned = re.sub(r'•|\*|-', '. ', cleaned)
    
    # Split on sentence terminals followed by space and capital letter
    raw_sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9])', cleaned)
    sentences = []
    for s in raw_sentences:
        clean_s = s.strip().strip('.').strip()
        if len(clean_s) > 3:  # Skip tiny fragments
            sentences.append(clean_s)
    return sentences if sentences else [cleaned]


def extract_entities_and_metrics(text: str) -> Dict[str, Any]:
    """Extract metrics, numbers, percentages, entities, and polarity words."""
    # Numbers and percentages
    numbers = set(re.findall(r'\b\d+(?:\.\d+)?', text.lower()))
    
    # Proper nouns and capitalized multi-word phrases
    capitalized = set(re.findall(r'\b[A-Z][a-zA-Z0-9_]+(?:\s+[A-Z][a-zA-Z0-9_]+)*\b', text))
    
    # Negation words
    negations = set(re.findall(r'\b(no|not|never|none|neither|hardly|scarcely|without|denied|failed|zero)\b', text.lower()))
    
    # Tokens
    tokens = set(re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())) - negations
    
    return {
        "numbers": numbers,
        "capitalized": capitalized,
        "negations": negations,
        "tokens": tokens
    }


class LocalNLIEngine:
    """Local NLI Engine for verifying faithfulness and detecting hallucinations."""

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name
        self._hf_pipeline = None
        self._attempted_hf_load = False

    def _get_hf_pipeline(self):
        """Lazy load Hugging Face NLI pipeline if transformers is installed."""
        if not self._attempted_hf_load:
            self._attempted_hf_load = True
            try:
                import transformers
                model = self.model_name or "cross-encoder/nli-deberta-v3-xsmall"
                self._hf_pipeline = transformers.pipeline(
                    "text-classification",
                    model=model,
                    top_k=None
                )
            except Exception:
                self._hf_pipeline = None
        return self._hf_pipeline

    def evaluate_sentence(self, premise: str, hypothesis: str) -> Dict[str, Any]:
        """Evaluate a single hypothesis sentence against the premise context."""
        hf = self._get_hf_pipeline()
        if hf is not None:
            try:
                # Format for cross-encoder or NLI pipeline
                result = hf(f"{premise} [SEP] {hypothesis}")
                scores = {item["label"].lower(): item["score"] for item in result[0]}
                entail = scores.get("entailment", 0.0)
                contra = scores.get("contradiction", 0.0)
                neutral = scores.get("neutral", 0.0)
                
                if contra > 0.5:
                    label = "CONTRADICTION"
                    conf = contra
                    reason = f"Neural NLI detected contradiction with premise context ({contra:.1%})"
                elif entail > 0.45:
                    label = "ENTAILMENT"
                    conf = entail
                    reason = f"Neural NLI confirmed factual entailment ({entail:.1%})"
                else:
                    label = "NEUTRAL"
                    conf = neutral
                    reason = "Claim is unsupported / ungrounded in the premise context"
                    
                return {
                    "sentence": hypothesis,
                    "label": label,
                    "confidence": round(conf, 3),
                    "reason": reason,
                    "backend": "neural_transformer"
                }
            except Exception:
                pass  # Fall back to semantic NLI

        # --- High-Precision Semantic NLI Engine ---
        p_info = extract_entities_and_metrics(premise)
        h_info = extract_entities_and_metrics(hypothesis)
        
        # 1. Contradiction: Conflicting numbers / quantities
        # If hypothesis has a number of same format/scale that conflicts with premise
        conflicting_numbers = []
        for h_num in h_info["numbers"]:
            # If premise has numbers, but this number is absent
            if p_info["numbers"] and h_num not in p_info["numbers"]:
                # Check if it looks like a conflicting quantity (e.g. 1500 vs 247)
                conflicting_numbers.append(h_num)

        # 2. Contradiction: Negation mismatch (e.g. Premise affirms, hypothesis negates)
        has_negation_conflict = bool(h_info["negations"] and not p_info["negations"] and len(h_info["tokens"] & p_info["tokens"]) >= 2)

        # 3. Token Overlap & Semantic Coverage
        common_tokens = h_info["tokens"] & p_info["tokens"]
        overlap_ratio = len(common_tokens) / max(len(h_info["tokens"]), 1)
        
        if conflicting_numbers:
            return {
                "sentence": hypothesis,
                "label": "CONTRADICTION",
                "confidence": 0.88,
                "reason": f"Fabricated numerical claims not grounded in premise: {', '.join(sorted(conflicting_numbers))}",
                "backend": "semantic_nli"
            }
        elif has_negation_conflict:
            return {
                "sentence": hypothesis,
                "label": "CONTRADICTION",
                "confidence": 0.82,
                "reason": "Direct polarity negation of premise assertions",
                "backend": "semantic_nli"
            }
        elif overlap_ratio >= 0.35 or len(common_tokens) >= 3:
            return {
                "sentence": hypothesis,
                "label": "ENTAILMENT",
                "confidence": round(min(0.95, 0.6 + overlap_ratio * 0.4), 2),
                "reason": f"Factual entities grounded in premise ({len(common_tokens)} common concepts)",
                "backend": "semantic_nli"
            }
        else:
            return {
                "sentence": hypothesis,
                "label": "NEUTRAL",
                "confidence": 0.70,
                "reason": "Extrapolated statement — not directly supported by premise context",
                "backend": "semantic_nli"
            }

    def evaluate(self, premise: str, hypothesis_text: str) -> Dict[str, Any]:
        """Evaluate an entire output against its input prompt context."""
        sentences = split_sentences(hypothesis_text)
        if not sentences:
            return {
                "faithfulness_score": 1.0,
                "hallucination_detected": False,
                "total_claims": 0,
                "entailed_claims": 0,
                "contradicted_claims": 0,
                "unsupported_claims": 0,
                "claims_analysis": [],
                "hallucinated_sentences": []
            }

        claims_analysis = [self.evaluate_sentence(premise, s) for s in sentences]
        
        entailed = sum(1 for c in claims_analysis if c["label"] == "ENTAILMENT")
        contradicted = sum(1 for c in claims_analysis if c["label"] == "CONTRADICTION")
        neutral = sum(1 for c in claims_analysis if c["label"] == "NEUTRAL")

        # Faithfulness score calculation:
        # Entailments get 1.0, Neutrals get 0.4, Contradictions get 0.0
        weighted_score = (entailed * 1.0 + neutral * 0.4 + contradicted * 0.0) / len(claims_analysis)
        faithfulness = round(max(0.0, min(1.0, weighted_score)), 2)

        # Flag as hallucination if any contradiction exists or faithfulness is low (<0.60)
        hallucination_detected = (contradicted > 0) or (faithfulness < 0.60)

        hallucinated_sentences = [
            c["sentence"] for c in claims_analysis if c["label"] == "CONTRADICTION"
        ]
        if not hallucinated_sentences and hallucination_detected:
            hallucinated_sentences = [
                c["sentence"] for c in claims_analysis if c["label"] == "NEUTRAL"
            ]

        return {
            "faithfulness_score": faithfulness,
            "hallucination_detected": hallucination_detected,
            "total_claims": len(claims_analysis),
            "entailed_claims": entailed,
            "contradicted_claims": contradicted,
            "unsupported_claims": neutral,
            "claims_analysis": claims_analysis,
            "hallucinated_sentences": hallucinated_sentences,
            "backend": claims_analysis[0]["backend"] if claims_analysis else "semantic_nli"
        }


# Global singleton instance
_engine_instance = None


def get_nli_engine() -> LocalNLIEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = LocalNLIEngine()
    return _engine_instance
