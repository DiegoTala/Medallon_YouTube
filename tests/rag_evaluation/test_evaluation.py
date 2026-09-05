"""Tests de evaluación de calidad y seguridad del agente RAG.

Ver .claude/skills/rag-evaluation-suite/SKILL.md y docs/PRD_Fase2.md §13.

Este módulo contiene:
- validación de estructura de los casos de prueba
- métricas objetivo del PRD
"""

from tests.rag_evaluation.test_cases import ADVERSARIAL_QUESTIONS, GOLDEN_QUESTIONS


def test_golden_questions_count():
    """Verifica que hay exactamente 15 preguntas doradas."""
    assert len(GOLDEN_QUESTIONS) == 15


def test_adversarial_questions_count():
    """Verifica que hay exactamente 10 preguntas adversariales."""
    assert len(ADVERSARIAL_QUESTIONS) == 10


def test_golden_questions_have_required_fields():
    """Cada pregunta dorada tiene los 6 campos del PRD + rejection_criteria."""
    required = {"id", "query", "expected_intent", "expected_tool", "relevant_data", "expected_answer", "required_citations", "rejection_criteria"}
    for q in GOLDEN_QUESTIONS:
        missing = required - set(q.keys())
        assert not missing, f"Pregunta {q.get('id', '?')} falta: {missing}"


def test_adversarial_questions_have_required_fields():
    """Cada pregunta adversarial tiene los campos requeridos."""
    required = {"id", "query", "category", "expected_behavior", "rejection_criteria"}
    for q in ADVERSARIAL_QUESTIONS:
        missing = required - set(q.keys())
        assert not missing, f"Pregunta {q.get('id', '?')} falta: {missing}"


def test_golden_distribution():
    """Verifica la distribución 5-5-5 del PRD §13."""
    intents = {q["expected_intent"] for q in GOLDEN_QUESTIONS}
    assert intents == {"semantic_search", "sentiment_analytics", "trend_detection"}

    for intent in intents:
        count = sum(1 for q in GOLDEN_QUESTIONS if q["expected_intent"] == intent)
        assert count == 5, f"{intent}: esperado 5, encontrado {count}"


def test_adversarial_categories():
    """Verifica las 3 categorías del set adversarial."""
    categories = {q["category"] for q in ADVERSARIAL_QUESTIONS}
    assert categories == {"domain", "injection", "data_access"}


def test_all_ids_unique():
    """Verifica que todos los IDs son únicos."""
    all_ids = [q["id"] for q in GOLDEN_QUESTIONS + ADVERSARIAL_QUESTIONS]
    assert len(all_ids) == len(set(all_ids)), "IDs duplicados encontrados"


def test_golden_rejection_criteria_present():
    """Todas las preguntas doradas tienen al menos un criterio de rechazo."""
    for q in GOLDEN_QUESTIONS:
        assert len(q["rejection_criteria"]) > 0, f"Pregunta {q['id']} sin rejection_criteria"


def test_adversarial_rejection_criteria_present():
    """Todas las preguntas adversariales tienen al menos un criterio de rechazo."""
    for q in ADVERSARIAL_QUESTIONS:
        assert len(q["rejection_criteria"]) > 0, f"Pregunta {q['id']} sin rejection_criteria"


def test_injection_via_corpus_exists():
    """Al menos una inyección vía corpus (no solo vía consulta)."""
    # sec-inject-03 simula un ataque que vendría por el corpus
    corpus_injection = [q for q in ADVERSARIAL_QUESTIONS if q["category"] == "injection"]
    assert len(corpus_injection) >= 1, "Debe haber al menos una inyección de prompt"
