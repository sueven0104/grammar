import json
import logging
import os
import random

logger = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

_choice_questions = []
_cloze_questions = []
_answers = {}


def _load_json(filename):
    filepath = os.path.join(_BASE_DIR, filename)
    with open(filepath, encoding="utf-8") as f:
        return json.load(f)


def _ensure_loaded():
    """惰性加载题库数据，仅在首次调用时加载。"""
    global _choice_questions, _cloze_questions, _answers
    if not _answers:
        _choice_questions = _load_json("choice.json")
        _cloze_questions = _load_json("cloze.json")
        _answers = _load_json("answers.json")
        logger.info(
            "题库加载完成: 选择题 %d 道, 填空题 %d 道, 答案 %d 条",
            len(_choice_questions),
            len(_cloze_questions),
            len(_answers),
        )


def _get_pool(source_type):
    """根据题型返回对应的题目列表。"""
    if source_type == "choice":
        return _choice_questions
    if source_type == "cloze":
        return _cloze_questions
    raise ValueError(f"不支持的题型: {source_type}，仅支持 'choice' 或 'cloze'")


def _enrich_with_answer(question):
    """为单道题目附加标准答案信息，返回新字典。"""
    qid = question.get("id")
    answer_info = _answers.get(qid, {})
    return {
        "id": qid,
        "stem": question.get("stem", ""),
        "options": question.get("options"),
        "wordBox": question.get("wordBox"),  # 填空题的单词选项框
        "sourceType": question.get("sourceType", ""),
        "examSource": question.get("examSource", ""),
        "knowledgePointId": question.get("knowledgePointId", ""),
        "correctAnswer": answer_info.get("correctAnswer", ""),
        "knowledgePointName": answer_info.get("knowledgePointName", ""),
    }


def get_random_questions(source_type, count=5):
    """从指定题库随机抽取题目并附带标准答案。

    Args:
        source_type: "choice" 或 "cloze"
        count: 抽取数量，默认 5

    Returns:
        题目列表，每道题包含 stem, options, correctAnswer 等字段
    """
    _ensure_loaded()
    pool = _get_pool(source_type)

    actual_count = min(count, len(pool))
    if actual_count == 0:
        logger.warning("题库 %s 为空，无法抽题", source_type)
        return []

    sampled = random.sample(pool, actual_count)
    return [_enrich_with_answer(q) for q in sampled]


def get_question_by_id(question_id):
    """根据 ID 查找单道题目并附带标准答案。

    Args:
        question_id: 题目 ID

    Returns:
        题目对象，或在未找到时返回 None
    """
    _ensure_loaded()

    for q in _choice_questions + _cloze_questions:
        if q.get("id") == question_id:
            return _enrich_with_answer(q)

    logger.warning("未找到题目: %s", question_id)
    return None
