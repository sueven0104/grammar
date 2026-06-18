import json
import logging
import time

from openai import OpenAI

from config import LLM_API_BASE_URL, LLM_API_KEY, LLM_MODEL_NAME

logger = logging.getLogger(__name__)

client = OpenAI(
    api_key=LLM_API_KEY,
    base_url=LLM_API_BASE_URL,
)


def _log_llm_call(func_name, response, elapsed_time):
    """记录LLM调用的详细信息，包括时间消耗和token消耗。"""
    usage = response.usage
    logger.info(
        "【LLM调用统计】%s | 模型: %s | 耗时: %.2f秒 | "
        "输入tokens: %d | 输出tokens: %d | 总tokens: %d",
        func_name,
        LLM_MODEL_NAME,
        elapsed_time,
        usage.prompt_tokens,
        usage.completion_tokens,
        usage.total_tokens,
    )


def _log_llm_request(func_name, context_info):
    """记录LLM调用前的上下文信息。"""
    logger.info("【LLM调用请求】%s | %s", func_name, context_info)


def _log_llm_response(func_name, raw_content, max_length=5000):
    """记录LLM调用后的原始响应内容。"""
    display_content = raw_content[:max_length] if len(raw_content) > max_length else raw_content
    logger.info("【LLM调用响应】%s | 响应长度: %d | 内容: %s", func_name, len(raw_content), display_content)

GRADE_LABELS = {
    1: "一年级",
    2: "二年级",
    3: "三年级",
    4: "四年级",
    5: "五年级",
}

QUESTION_TYPE_LABELS = {
    "choice": "选择题",
    "fill": "填空题",
    "judge": "判断题",
    "correction": "改错题",
}

GRADE_SYLLABUS = {
    1: ["be动词(am/is/are)", "简单陈述句", "简单疑问句(What/Who)", "名词单数", "指示代词(this/that)", "人称代词主格(I/you/he/she/it/we/they)"],
    2: ["一般现在时(简单动词)", "名词复数", "there is/are", "祈使句", "形容词基础", "简单介词(in/on/under)"],
    3: ["一般现在时(第三人称单数)", "现在进行时", "can/can't", "冠词(a/an/the)", "物主代词", "比较级基础"],
    4: ["一般过去时", "一般将来时(will)", "连词(and/but/or)", "情态动词基础(should/must)", "简单条件句(if)", "简单宾语从句"],
    5: ["现在完成时(基础)", "最高级", "情态动词深化(should/must/could/might)", "定语从句(基础)", "被动语态(基础)", "时态综合运用"],
}

# JSON 格式示例（使用缩写字段名以减少 token 消耗）
# 字段说明：q=题目, opts=选项, ans=答案, kp=知识点（简洁描述）, cs=正确句子
QUESTION_JSON_FORMATS = {
    "choice": (
        '[{"q": "题目内容", "opts": ["选项1", "选项2", "选项3", "选项4"], '
        '"ans": "A", "kp": "知识点"}]'
    ),
    "fill": (
        '[{"q": "He ___ (go) to school every day.", '
        '"ans": "goes", "kp": "一般现在时"}]'
    ),
    "judge": (
        '[{"q": "They is playing football now.", '
        '"ans": false, "cs": "They are playing football now.", '
        '"kp": "主谓一致"}]'
    ),
    "correction": (
        '[{"q": "She don\'t like apples.", '
        '"ans": "She doesn\'t like apples.", "kp": "否定形式"}]'
    ),
}


def _build_generate_prompt(grade, question_type, count, knowledge_point=None, history=None):
    """构建生成题目的 prompt。

    Args:
        grade: 年级（1-6）
        question_type: 题型（choice/fill/judge/correction）
        count: 题目数量
        knowledge_point: 可选，指定知识点
        history: 可选，历史题目列表，用于避免重复

    Returns:
        构建好的 prompt 字符串
    """
    grade_label = GRADE_LABELS.get(grade, f"{grade}年级")
    type_label = QUESTION_TYPE_LABELS.get(question_type, question_type)
    json_format = QUESTION_JSON_FORMATS.get(question_type)
    if json_format is None:
        raise ValueError(f"不支持的题型: {question_type}")

    syllabus = GRADE_SYLLABUS.get(grade, [])
    syllabus_text = "\n".join(f"- {kp}" for kp in syllabus)

    knowledge_constraint = ""
    if knowledge_point:
        knowledge_constraint = f"\n**本次只考查以下知识点：{knowledge_point}**\n"
    else:
        knowledge_constraint = (
            f"\n{grade_label}的核心语法知识点如下（只能从这些知识点中出题）：\n"
            f"{syllabus_text}\n"
            f"题目必须考查上述知识点之一，不得超出范围。\n"
        )

    # 历史题目约束：只传最近 50 条，避免 prompt 过长
    history_constraint = ""
    if history:
        recent_history = history[-50:]
        history_text = "\n".join(f"- {q}" for q in recent_history)
        history_constraint = f"\n**以下题目已出过，请勿重复或生成高度相似的题目：**\n{history_text}\n"

    return (
        f"你是一位专业的小学英语教师。请为小学{grade_label}的学生出{count}道英语语法{type_label}。\n"
        f"{knowledge_constraint}"
        f"{history_constraint}"
        f"要求：\n"
        f"1. 题目难度适合小学{grade_label}学生,稍微高于教材基础难度,考查学生对知识点的深入理解和灵活运用\n"
        f"2. 每道题必须有明确的知识点（kp字段用简洁的中文描述，如'be动词'、'一般现在时'）\n"
        f"3. **选择题（choice）格式要求**：\n"
        f"   - opts字段必须包含4个选项（纯文本，不带A/B/C/D前缀）\n"
        f"   - ans字段必须是字母A/B/C/D之一\n"
        f"   - 不要包含cs字段\n"
        f"4. **判断题（judge）格式要求**：\n"
        f"   - opts字段必须为空或不包含\n"
        f"   - ans字段必须是布尔值（true/false）\n"
        f"   - cs字段必须包含正确的句子\n"
        f"5. **填空题（fill）和改错题（correction）格式要求**：\n"
        f"   - opts字段必须为空或不包含\n"
        f"   - ans字段必须是文本答案\n"
        f"   - 不要包含cs字段\n"
        f"6. **重要：严格按照题型要求生成，不要混淆不同题型的格式**\n"
        f"7. **重要：每道题目必须不同，不要生成重复或相似的题目**\n"
        f"8. **重要：每道题的知识点必须不同，涵盖不同的语法知识点**\n"
        f"9. 题目内容要多样化，涵盖不同的语法知识点和场景\n\n"
        f"请严格按照以下JSON格式返回，不要包含任何其他文字、解释或markdown标记：\n{json_format}"
    )


def _map_question_fields(question_data):
    """将缩写字段名映射为完整字段名。
    
    支持向后兼容：如果输入已经是完整字段名，则直接返回。
    
    字段映射：
    - q -> question
    - ans -> answer
    - kp -> knowledge
    - opts -> options (添加 A/B/C/D 前缀)
    - cs -> correct_sentence
    
    Args:
        question_data: 包含题目数据的字典（可能是缩写格式或完整格式）
    
    Returns:
        包含完整字段名的字典
    
    Raises:
        TypeError: 如果 question_data 不是字典类型
    """
    # 输入验证
    if not isinstance(question_data, dict):
        raise TypeError("question_data 必须是字典类型")
    
    # 检测是否为缩写格式
    if "q" in question_data:
        mapped = {
            "question": question_data.get("q", ""),
            "answer": question_data.get("ans", ""),
            "knowledge": question_data.get("kp", ""),
        }
        # 选择题：添加选项，并添加前缀
        if "opts" in question_data:
            opts = question_data.get("opts", [])
            # 限制选项数量为最多4个
            if len(opts) > 4:
                logger.warning("选项数量超过4个，将只取前4个")
                opts = opts[:4]
            # 为每个选项添加A/B/C/D前缀
            mapped["options"] = [f"{chr(65+i)}. {opt}" for i, opt in enumerate(opts)]
        # 判断题：添加正确句子
        if "cs" in question_data:
            mapped["correct_sentence"] = question_data.get("cs", "")
        return mapped
    else:
        # 已经是完整格式，直接返回
        return question_data


def generate_questions(grade, question_type, count=5, knowledge_point=None, history=None):
    """生成指定年级和题型的英语语法题。

    Args:
        grade: 年级（1-6）
        question_type: 题型（choice/fill/judge/correction）
        count: 题目数量，默认5
        knowledge_point: 可选，指定知识点
        history: 可选，历史题目列表，用于避免重复

    Returns:
        list: 题目列表，每个题目为字典格式

    Raises:
        ValueError: JSON解析失败或返回格式不正确
    """
    grade_label = GRADE_LABELS.get(grade, f"{grade}年级")
    type_label = QUESTION_TYPE_LABELS.get(question_type, question_type)
    context_info = f"年级: {grade_label} | 题型: {type_label} | 数量: {count}"
    if knowledge_point:
        context_info += f" | 知识点: {knowledge_point}"
    if history:
        context_info += f" | 历史题目数: {len(history)}"
    _log_llm_request("generate_questions", context_info)

    prompt = _build_generate_prompt(grade, question_type, count, knowledge_point, history)

    try:
        start_time = time.time()
        response = client.chat.completions.create(
            model=LLM_MODEL_NAME,
            messages=[
                {"role": "system", "content": "你是一位专业的小学英语教师，擅长出题和语法讲解。请只返回JSON格式的内容。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            extra_body={"thinking": {"type": "disabled"}},
            response_format={'type': 'json_object'}
        )
        elapsed_time = time.time() - start_time
        _log_llm_call("generate_questions", response, elapsed_time)

        raw_content = response.choices[0].message.content.strip()
        _log_llm_response("generate_questions", raw_content)

        # 尝试提取 JSON 部分（兼容 markdown 代码块包裹的情况）
        if raw_content.startswith("```"):
            lines = raw_content.split("\n")
            # 去掉首行 ```json 和末行 ```
            start = 1
            end = len(lines)
            for i in range(len(lines) - 1, 0, -1):
                if lines[i].strip() == "```":
                    end = i
                    break
            raw_content = "\n".join(lines[start:end])

        questions = json.loads(raw_content)

        if not isinstance(questions, list):
            raise ValueError("返回的JSON不是列表格式")

        # 字段名映射：将缩写格式转换为完整格式
        mapped_questions = [_map_question_fields(q) for q in questions]

        # 知识点去重检查（使用映射后的数据）
        unique_questions = []
        seen_knowledge = set()
        for q in mapped_questions:
            knowledge = q.get("knowledge", "")
            if knowledge and knowledge not in seen_knowledge:
                seen_knowledge.add(knowledge)
                unique_questions.append(q)
            elif not knowledge:
                # 如果没有知识点字段，也保留
                unique_questions.append(q)
        
        # 如果去重后题目数量不足，补充提示
        if len(unique_questions) < count:
            logger.warning(
                "知识点去重后题目数量不足: 原始%d道, 去重后%d道, 需要%d道",
                len(questions), len(unique_questions), count
            )
        
        return unique_questions

    except json.JSONDecodeError as e:
        logger.error("JSON解析失败: %s, 原始内容: %s", str(e), raw_content[:500])
        raise ValueError(f"大模型返回的内容无法解析为JSON: {str(e)}")
    except Exception as e:
        logger.error("生成题目失败: %s", str(e))
        raise


def fuzzy_grade_fill(question_data, user_answer):
    """当填空题严格匹配失败时，调用LLM做模糊批改。

    Returns:
        dict with is_correct, correct_answer, is_close
    """
    context_info = f"题目: {question_data['question'][:50]} | 正确答案: {question_data['answer']} | 学生答案: {user_answer}"
    _log_llm_request("fuzzy_grade_fill", context_info)

    prompt = (
        f"判断学生的填空题答案是否正确或接近正确。\n\n"
        f"题目：{question_data['question']}\n"
        f"正确答案：{question_data['answer']}\n"
        f"学生答案：{user_answer}\n\n"
        f"判断规则：\n"
        f"- 如果学生答案和正确答案意思一致（即使有轻微拼写错误），返回 is_correct: true\n"
        f"- 如果学生答案和正确答案很接近但有明显拼写错误（如少了一个字母），返回 is_close: true, is_correct: false\n"
        f"- 如果学生答案完全错误，返回 is_correct: false, is_close: false\n\n"
        f'请严格以JSON格式返回：{{"is_correct": true/false, "correct_answer": "正确答案", "is_close": true/false}}\n'
        f"不要包含任何其他文字。"
    )

    try:
        start_time = time.time()
        response = client.chat.completions.create(
            model=LLM_MODEL_NAME,
            messages=[
                {"role": "system", "content": "你是一位专业的小学英语教师，负责批改填空题。只返回JSON格式。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            response_format={'type': 'json_object'}
        )
        elapsed_time = time.time() - start_time
        _log_llm_call("fuzzy_grade_fill", response, elapsed_time)

        raw_content = response.choices[0].message.content.strip()
        _log_llm_response("fuzzy_grade_fill", raw_content)

        if raw_content.startswith("```"):
            lines = raw_content.split("\n")
            start = 1
            end = len(lines)
            for i in range(len(lines) - 1, 0, -1):
                if lines[i].strip() == "```":
                    end = i
                    break
            raw_content = "\n".join(lines[start:end])

        result = json.loads(raw_content)
        logger.info("【模糊批改结果】是否正确: %s | 是否接近: %s | 正确答案: %s", 
                    result.get("is_correct"), result.get("is_close"), result.get("correct_answer"))
        return {
            "is_correct": bool(result.get("is_correct", False)),
            "correct_answer": result.get("correct_answer", question_data["answer"]),
            "is_close": bool(result.get("is_close", False)),
        }
    except (json.JSONDecodeError, Exception) as e:
        logger.error("【模糊批改失败】错误: %s | 原始响应: %s", str(e), raw_content[:200] if 'raw_content' in locals() else 'N/A')
        return {
            "is_correct": False,
            "correct_answer": question_data["answer"],
            "is_close": False,
        }


def grade_answer(question_data, user_answer, question_type):
    """批改用户答案，返回是否正确和正确答案。"""
    if question_type == "choice":
        is_correct = str(user_answer).strip().upper() == str(question_data["answer"]).strip().upper()
        return {
            "is_correct": is_correct,
            "correct_answer": question_data["answer"],
        }

    if question_type == "fill":
        user_clean = str(user_answer).strip().lower()
        answer_clean = str(question_data["answer"]).strip().lower()
        is_correct = user_clean == answer_clean
        if is_correct:
            return {
                "is_correct": True,
                "correct_answer": question_data["answer"],
            }
        # 严格匹配失败，尝试模糊批改
        fuzzy = fuzzy_grade_fill(question_data, user_answer)
        return {
            "is_correct": fuzzy["is_correct"],
            "correct_answer": fuzzy["correct_answer"],
            "is_close": fuzzy.get("is_close", False),
        }

    if question_type == "judge":
        if isinstance(user_answer, str):
            user_bool = user_answer.strip().lower() in ("true", "对", "正确", "1", "yes")
        else:
            user_bool = bool(user_answer)
        is_correct = user_bool == question_data["answer"]
        correct_answer = "正确" if question_data["answer"] else "错误"
        return {
            "is_correct": is_correct,
            "correct_answer": correct_answer,
        }

    if question_type == "correction":
        context_info = f"原句: {question_data['question'][:50]} | 学生答案: {user_answer[:50]}"
        _log_llm_request("grade_answer(correction)", context_info)
        
        try:
            start_time = time.time()
            response = client.chat.completions.create(
                model=LLM_MODEL_NAME,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一位专业的小学英语教师。请判断学生修改后的句子是否正确。只返回JSON格式。",
                    },
                    {
                        "role": "user",
                        "content": (
                            f"原句：{question_data['question']}\n"
                            f"正确答案：{question_data['answer']}\n"
                            f"学生修改后的句子：{user_answer}\n\n"
                            f"请判断学生的答案是否正确（语法和意思都要正确）。\n"
                            f'请严格以JSON格式返回：{{"is_correct": true或false, "correct_answer": "正确答案"}}\n'
                            f"不要包含任何其他文字。"
                        ),
                    },
                ],
                temperature=0.1,
            )
            elapsed_time = time.time() - start_time
            _log_llm_call("grade_answer(correction)", response, elapsed_time)

            raw_content = response.choices[0].message.content.strip()
            _log_llm_response("grade_answer(correction)", raw_content)

            if raw_content.startswith("```"):
                lines = raw_content.split("\n")
                start = 1
                end = len(lines)
                for i in range(len(lines) - 1, 0, -1):
                    if lines[i].strip() == "```":
                        end = i
                        break
                raw_content = "\n".join(lines[start:end])

            result = json.loads(raw_content)
            logger.info("【改错题批改结果】是否正确: %s | 正确答案: %s", 
                        result.get("is_correct"), result.get("correct_answer"))
            return {
                "is_correct": bool(result.get("is_correct", False)),
                "correct_answer": result.get("correct_answer", question_data["answer"]),
            }

        except (json.JSONDecodeError, KeyError) as e:
            logger.error("【改错题批改失败】错误: %s | 原始响应: %s", str(e), raw_content[:200] if 'raw_content' in locals() else 'N/A')
            return {
                "is_correct": False,
                "correct_answer": question_data["answer"],
            }

    raise ValueError(f"不支持的题型: {question_type}")


def explain_answer(question_data, user_answer, is_correct, question_type):
    """生成答案讲解，适合小学生理解。"""
    context_info = f"题型: {question_type} | 是否正确: {is_correct} | 知识点: {question_data.get('knowledge', 'N/A')}"
    _log_llm_request("explain_answer", context_info)

    if is_correct:
        prompt = (
            f"学生回答正确！请给予鼓励并讲解这道题涉及的语法知识点。\n\n"
            f"题目：{question_data['question']}\n"
            f"正确答案：{question_data.get('answer', '')}\n"
            f"知识点：{question_data.get('knowledge', '')}\n\n"
            f"要求：\n"
            f"1. 先表扬学生\n"
            f"2. 用简单易懂的中文讲解知识点\n"
            f"3. 可以举1-2个例子帮助理解\n"
            f"4. 语言要适合小学生"
        )
    else:
        prompt = (
            f"学生回答错误。请讲解正确答案和错误原因。\n\n"
            f"题目：{question_data['question']}\n"
            f"学生的答案：{user_answer}\n"
            f"正确答案：{question_data.get('answer', '')}\n"
        )
        if question_data.get("correct_sentence"):
            prompt += f"正确句子：{question_data['correct_sentence']}\n"
        prompt += (
            f"知识点：{question_data.get('knowledge', '')}\n\n"
            f"要求：\n"
            f"1. 告诉学生正确答案是什么\n"
            f"2. 解释为什么学生的答案是错的\n"
            f"3. 用简单易懂的中文讲解正确的用法\n"
            f"4. 举1-2个例子帮助理解\n"
            f"5. 语言要适合小学生，多鼓励"
        )

    try:
        start_time = time.time()
        response = client.chat.completions.create(
            model=LLM_MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": "你是一位亲切友善的小学英语教师，擅长用简单易懂的方式讲解语法知识。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7
        )
        elapsed_time = time.time() - start_time
        _log_llm_call("explain_answer", response, elapsed_time)

        explanation = response.choices[0].message.content.strip()
        _log_llm_response("explain_answer", explanation, max_length=300)
        return explanation

    except Exception as e:
        logger.error("【生成讲解失败】错误: %s", str(e))
        raise


# ---------------------------------------------------------------------------
# 中考题练习模块
# ---------------------------------------------------------------------------

def explain_zhongkao_question(question, user_answer, is_correct, correct_answer):
    """为中考题生成详细解析，适合中学生理解。

    Args:
        question: 题目对象（含 stem, options, knowledgePointName 等）
        user_answer: 用户提交的答案
        is_correct: 是否正确
        correct_answer: 正确答案

    Returns:
        解析文本（中文）
    """
    stem = question.get("stem", "")
    options = question.get("options")
    kp_name = question.get("knowledgePointName", "")
    
    context_info = f"题目: {stem[:50]} | 是否正确: {is_correct} | 知识点: {kp_name}"
    _log_llm_request("explain_zhongkao_question", context_info)

    if is_correct:
        prompt = (
            f"学生回答正确！请给予肯定并讲解这道中考英语题涉及的知识点。\n\n"
            f"题目：{stem}\n"
        )
        if options:
            prompt += f"选项：{options}\n"
        prompt += (
            f"正确答案：{correct_answer}\n"
            f"知识点：{kp_name}\n\n"
            f"要求：\n"
            f"1. 先表扬学生\n"
            f"2. 用简洁易懂的中文讲解该知识点\n"
            f"3. 可以举1-2个例子帮助理解\n"
            f"4. 语言适合中学生"
        )
    else:
        prompt = (
            f"学生回答错误。请讲解正确答案和错误原因。\n\n"
            f"题目：{stem}\n"
        )
        if options:
            prompt += f"选项：{options}\n"
        prompt += (
            f"学生的答案：{user_answer}\n"
            f"正确答案：{correct_answer}\n"
            f"知识点：{kp_name}\n\n"
            f"要求：\n"
            f"1. 告诉学生正确答案是什么\n"
            f"2. 解释为什么学生的答案是错的\n"
            f"3. 用简洁易懂的中文讲解正确的用法\n"
            f"4. 举1-2个例子帮助理解\n"
            f"5. 语言适合中学生，多鼓励"
        )

    try:
        start_time = time.time()
        response = client.chat.completions.create(
            model=LLM_MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": "你是一位经验丰富的初中英语教师，擅长用简洁清晰的方式讲解中考英语知识点。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7
        )
        elapsed_time = time.time() - start_time
        _log_llm_call("explain_zhongkao_question", response, elapsed_time)

        explanation = response.choices[0].message.content.strip()
        _log_llm_response("explain_zhongkao_question", explanation, max_length=300)
        return explanation

    except Exception as e:
        logger.error("【生成中考题解析失败】错误: %s", str(e))
        raise


def _normalize_choice_options(result):
    """规范化选择题的 options 与 correctAnswer。

    问题背景：大模型生成相似题时，options 可能：
    1. 已带 "A. xxx" / "B. xxx" 等前缀（前端会再加一次前缀，导致 "A. A. xxx"）；
    2. 字母前缀出现重复（例如同时返回两个 "A. xxx"）；
    3. 选项文本之间出现重复。

    规范化策略：
    - 剥离每个选项首部的 "X."/"X、"/"X)"/"X：" 等字母前缀，仅保留纯选项文本；
    - 同时保留原始字母前缀到纯文本的映射，用于 correctAnswer 重映射；
    - 去除完全重复的纯文本选项；
    - 根据原始字母与去重后位置的映射，更新 correctAnswer 为新的字母（A/B/C/D）。
    """
    import re

    options = result.get("options")
    if not isinstance(options, list) or not options:
        return result

    prefix_pattern = re.compile(r"^\s*([A-Da-d])\s*[\.\)、:：]\s*")

    cleaned_in_order = []
    seen_texts = set()
    for idx, opt in enumerate(options):
        if not isinstance(opt, str):
            opt = str(opt)
        stripped = opt.strip()
        match = prefix_pattern.match(stripped)
        if match:
            original_letter = match.group(1).upper()
            text = prefix_pattern.sub("", stripped, count=1).strip()
        else:
            # 未带前缀，则按原始位置字母推断
            original_letter = chr(ord("A") + idx) if idx < 4 else None
            text = stripped

        if not text or text in seen_texts:
            continue
        seen_texts.add(text)
        cleaned_in_order.append((original_letter, text))

    if not cleaned_in_order:
        return result

    # 截断到最多 4 个；不足时不强行补全，由前端正常渲染
    cleaned_in_order = cleaned_in_order[:4]

    letter_map = {}
    new_options = []
    for new_idx, (original_letter, text) in enumerate(cleaned_in_order):
        new_letter = chr(ord("A") + new_idx)
        new_options.append(text)
        if original_letter:
            letter_map.setdefault(original_letter, new_letter)

    result["options"] = new_options

    # 重映射 correctAnswer
    correct = result.get("correctAnswer")
    if isinstance(correct, str):
        correct_stripped = correct.strip()
        match = re.match(r"^([A-Da-d])\b", correct_stripped)
        if match:
            original_letter = match.group(1).upper()
            mapped = letter_map.get(original_letter)
            if mapped:
                result["correctAnswer"] = mapped

    return result


def generate_similar_question(question, knowledge_point_id, knowledge_point_name):
    """根据错题的考点生成一道相似的中考题。

    Args:
        question: 原始题目对象
        knowledge_point_id: 考点 ID
        knowledge_point_name: 考点名称

    Returns:
        包含 stem, options, sourceType, correctAnswer, explanation 的字典
    """
    source_type = question.get("sourceType", "choice")
    original_stem = question.get("stem", "")
    options = question.get("options")
    
    context_info = f"原题: {original_stem[:50]} | 考点: {knowledge_point_name} | 题型: {source_type}"
    _log_llm_request("generate_similar_question", context_info)

    if source_type == "choice":
        format_instruction = (
            "请严格按照以下JSON格式返回，不要包含任何其他文字、解释或markdown标记：\n"
            '{"stem": "新题目内容", "options": ["选项1原文", "选项2原文", "选项3原文", "选项4原文"], '
            '"sourceType": "choice", "correctAnswer": "A/B/C/D", "explanation": "解析"}\n'
            "注意：options 数组中的每个元素必须是纯选项文本，不要带 \"A.\"/\"B.\"/\"C.\"/\"D.\" 等字母编号前缀；"
            "四个选项内容必须互不相同，不能出现重复选项；correctAnswer 仅填写字母 A/B/C/D，"
            "对应 options 数组下标 0/1/2/3。"
        )
    else:
        format_instruction = (
            "请严格按照以下JSON格式返回，不要包含任何其他文字、解释或markdown标记：\n"
            '{"stem": "新题目内容", "sourceType": "cloze", '
            '"correctAnswer": "答案", "explanation": "解析"}'
        )

    prompt = (
        f"请根据以下中考英语错题的考点，生成一道新的相似题目。\n\n"
        f"原题：{original_stem}\n"
    )
    if options:
        prompt += f"原选项：{options}\n"
    prompt += (
        f"考点ID：{knowledge_point_id}\n"
        f"考点名称：{knowledge_point_name}\n\n"
        f"要求：\n"
        f"1. 新题目必须考查相同的考点：{knowledge_point_name}\n"
        f"2. 难度与中考相当\n"
        f"3. 题目内容不能与原题相同\n"
        f"4. 必须包含正确答案和简要解析\n"
        f"5. {format_instruction}"
    )

    try:
        start_time = time.time()
        response = client.chat.completions.create(
            model=LLM_MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": "你是一位专业的中考英语命题教师，擅长根据考点出题。请只返回JSON格式的内容。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.8,
            response_format={'type': 'json_object'}
        )
        elapsed_time = time.time() - start_time
        _log_llm_call("generate_similar_question", response, elapsed_time)

        raw_content = response.choices[0].message.content.strip()
        _log_llm_response("generate_similar_question", raw_content)

        # 兼容 markdown 代码块包裹
        if raw_content.startswith("```"):
            lines = raw_content.split("\n")
            start = 1
            end = len(lines)
            for i in range(len(lines) - 1, 0, -1):
                if lines[i].strip() == "```":
                    end = i
                    break
            raw_content = "\n".join(lines[start:end])

        result = json.loads(raw_content)

        if not isinstance(result, dict):
            raise ValueError("返回的JSON不是对象格式")

        # 确保 sourceType 一致
        result.setdefault("sourceType", source_type)

        # 规范化选择题选项：去除大模型可能附带的 "A./B." 前缀，并按位置重新映射 correctAnswer
        if result.get("sourceType") == "choice":
            result = _normalize_choice_options(result)

        logger.info("【生成相似题结果】新题: %s | 正确答案: %s", 
                    result.get("stem", "")[:50], result.get("correctAnswer"))
        return result

    except json.JSONDecodeError as e:
        logger.error("【生成相似题失败】JSON解析错误: %s | 原始内容: %s", str(e), raw_content[:500] if 'raw_content' in locals() else 'N/A')
        raise ValueError(f"大模型返回的内容无法解析为JSON: {str(e)}")
    except Exception as e:
        logger.error("【生成相似题失败】错误: %s", str(e))
        raise
