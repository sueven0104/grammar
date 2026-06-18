import logging
import os
import sys

# 配置日志系统 - 必须在导入其他模块之前配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
    force=True,  # 强制重新配置，覆盖任何现有配置
)
logger = logging.getLogger(__name__)

# 确保 Flask 和 Werkzeug 的日志也输出
logging.getLogger('flask').setLevel(logging.INFO)
logging.getLogger('werkzeug').setLevel(logging.INFO)

from flask import Flask, jsonify, render_template, request

import llm_service
import question_bank

app = Flask(__name__)

# 启动时立即输出日志，验证日志系统工作
logger.info("="*80)
logger.info("【应用启动】Flask 应用正在初始化...")
logger.info("【应用启动】日志系统已配置，级别: INFO")
logger.info("【应用启动】日志输出目标: stdout (标准输出)")
logger.info("="*80)

# 子路径部署配置：Nginx 代理时剥离前缀，Flask 收到的是不带前缀的路径
# 设置 APPLICATION_ROOT 让 url_for() 生成带前缀的 URL
# 环境变量 APPLICATION_ROOT 例如：/englishtest
APPLICATION_ROOT = os.environ.get("APPLICATION_ROOT", "/englishtest")
if APPLICATION_ROOT:
    app.config["APPLICATION_ROOT"] = APPLICATION_ROOT

# 调试：打印请求信息
@app.before_request
def log_request_info():
    logger.info("Request: %s %s, SCRIPT_NAME: %s", request.method, request.path, request.environ.get('SCRIPT_NAME', ''))

VALID_GRADES = range(1, 6)
VALID_QUESTION_TYPES = {"choice", "fill", "judge", "correction"}
VALID_ZHONGKAO_SOURCE_TYPES = {"choice", "cloze"}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/grammar")
def grammar():
    return render_template("grammar.html")


@app.route("/quiz")
def quiz():
    grade = request.args.get("grade", type=int)
    question_type = request.args.get("type", "")
    knowledge_point = request.args.get("kp", "")

    if grade not in VALID_GRADES:
        return "年级参数错误", 400
    if question_type not in VALID_QUESTION_TYPES:
        return "题型参数错误", 400

    return render_template("quiz.html", grade=grade, question_type=question_type, knowledge_point=knowledge_point)


@app.route("/api/questions", methods=["POST"])
def get_questions():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "请求体不能为空"}), 400

    grade = data.get("grade")
    question_type = data.get("question_type")
    knowledge_point = data.get("knowledge_point")
    history = data.get("history", [])  # 新增：接收历史题目列表用于去重

    if grade not in VALID_GRADES:
        return jsonify({"success": False, "error": "年级必须是1-5的整数"}), 400

    if question_type not in VALID_QUESTION_TYPES:
        return jsonify({"success": False, "error": f"题型必须是以下之一: {', '.join(VALID_QUESTION_TYPES)}"}), 400

    # 支持自定义抽题数量，默认 1（单题模式），上限 10
    try:
        count = int(data.get("count", 1))
    except (TypeError, ValueError):
        count = 1
    count = max(1, min(count, 10))

    try:
        questions = llm_service.generate_questions(grade, question_type, count, knowledge_point=knowledge_point, history=history)
        return jsonify({
            "success": True,
            "questions": questions,
            "question_type": question_type,
        })
    except ValueError as e:
        logger.warning("生成题目参数错误: %s", str(e))
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error("生成题目失败: %s", str(e), exc_info=True)
        return jsonify({"success": False, "error": "生成题目失败，请稍后重试"}), 500


@app.route("/api/grade", methods=["POST"])
def grade():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "请求体不能为空"}), 400

    question = data.get("question")
    user_answer = data.get("user_answer")
    question_type = data.get("question_type")

    if not question:
        return jsonify({"success": False, "error": "缺少题目信息"}), 400

    if user_answer is None or user_answer == "":
        return jsonify({"success": False, "error": "缺少用户答案"}), 400

    if question_type not in VALID_QUESTION_TYPES:
        return jsonify({"success": False, "error": f"题型必须是以下之一: {', '.join(VALID_QUESTION_TYPES)}"}), 400

    try:
        result = llm_service.grade_answer(question, user_answer, question_type)
        response = {
            "success": True,
            "is_correct": result["is_correct"],
            "correct_answer": result["correct_answer"],
        }
        if "is_close" in result:
            response["is_close"] = result["is_close"]
        return jsonify(response)
    except ValueError as e:
        logger.warning("批改答案参数错误: %s", str(e))
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error("批改答案失败: %s", str(e), exc_info=True)
        return jsonify({"success": False, "error": "批改答案失败，请稍后重试"}), 500


@app.route("/api/explain", methods=["POST"])
def explain():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "请求体不能为空"}), 400

    question = data.get("question")
    user_answer = data.get("user_answer")
    correct_answer = data.get("correct_answer", "")
    is_correct = data.get("is_correct")
    question_type = data.get("question_type")
    knowledge = data.get("knowledge", "")

    if not question:
        return jsonify({"success": False, "error": "缺少题目信息"}), 400

    if is_correct is None:
        return jsonify({"success": False, "error": "缺少是否正确标记"}), 400

    if question_type not in VALID_QUESTION_TYPES:
        return jsonify({"success": False, "error": f"题型必须是以下之一: {', '.join(VALID_QUESTION_TYPES)}"}), 400

    # 组装题目数据字典
    question_data = {
        "question": question,
        "answer": correct_answer,
        "knowledge": knowledge
    }

    try:
        explanation = llm_service.explain_answer(question_data, user_answer, is_correct, question_type)
        return jsonify({
            "success": True,
            "explanation": explanation,
        })
    except Exception as e:
        logger.error("生成讲解失败: %s", str(e), exc_info=True)
        return jsonify({"success": False, "error": "生成讲解失败，请稍后重试"}), 500


# ---------------------------------------------------------------------------
# 中考题练习模块
# ---------------------------------------------------------------------------

def _strip_correct_answer(question):
    """返回去除 correctAnswer 字段的题目副本（答案不暴露给前端）。"""
    return {
        "id": question.get("id", ""),
        "stem": question.get("stem", ""),
        "options": question.get("options"),
        "wordBox": question.get("wordBox"),  # 填空题的单词选项框
        "sourceType": question.get("sourceType", ""),
        "examSource": question.get("examSource", ""),
        "knowledgePointId": question.get("knowledgePointId", ""),
        "knowledgePointName": question.get("knowledgePointName", ""),
    }


def _lookup_question(question_id, source_type):
    """根据 ID 和题型查找题目，返回 (question, error_response, status_code)。"""
    question = question_bank.get_question_by_id(question_id)
    if not question:
        return None, {"success": False, "error": "未找到该题目"}, 404
    if question.get("sourceType") != source_type:
        return None, {"success": False, "error": "题目类型不匹配"}, 400
    return question, None, None


@app.route("/zhongkao")
def zhongkao():
    return render_template("zhongkao.html")


@app.route("/zhongkao/quiz")
def zhongkao_quiz():
    source_type = request.args.get("source_type", "")
    if source_type not in VALID_ZHONGKAO_SOURCE_TYPES:
        return "题型参数错误，必须是 choice 或 cloze", 400
    return render_template("zhongkao_quiz.html", source_type=source_type)


@app.route("/api/zhongkao/questions", methods=["POST"])
def zhongkao_questions():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "请求体不能为空"}), 400

    source_type = data.get("source_type")
    if source_type not in VALID_ZHONGKAO_SOURCE_TYPES:
        return jsonify({"success": False, "error": "题型必须是 choice 或 cloze"}), 400

    # 支持自定义抽题数量，默认 1（单题模式），上限 10
    try:
        count = int(data.get("count", 1))
    except (TypeError, ValueError):
        count = 1
    count = max(1, min(count, 10))

    try:
        questions = question_bank.get_random_questions(source_type, count)
        # 去除正确答案，不暴露给前端
        safe_questions = [_strip_correct_answer(q) for q in questions]
        return jsonify({
            "success": True,
            "questions": safe_questions,
            "source_type": source_type,
        })
    except Exception as e:
        logger.error("获取中考题失败: %s", str(e), exc_info=True)
        return jsonify({"success": False, "error": "获取题目失败，请稍后重试"}), 500


@app.route("/api/zhongkao/grade", methods=["POST"])
def zhongkao_grade():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "请求体不能为空"}), 400

    question_id = data.get("question_id")
    user_answer = data.get("user_answer")
    source_type = data.get("source_type")

    if not question_id:
        return jsonify({"success": False, "error": "缺少题目ID"}), 400
    if user_answer is None or user_answer == "":
        return jsonify({"success": False, "error": "缺少用户答案"}), 400
    if source_type not in VALID_ZHONGKAO_SOURCE_TYPES:
        return jsonify({"success": False, "error": "题型必须是 choice 或 cloze"}), 400

    question, err_resp, err_code = _lookup_question(question_id, source_type)
    if err_resp:
        return jsonify(err_resp), err_code

    correct_answer = question.get("correctAnswer", "")

    # 本地批改：选择题忽略大小写，填空题支持多答案格式（如 "if/whether"）
    is_correct = False
    if source_type == "choice":
        is_correct = str(user_answer).strip().upper() == str(correct_answer).strip().upper()
    elif source_type == "cloze":
        user_clean = str(user_answer).strip().lower()
        # 支持 "answer1/answer2" 多答案格式
        accepted_answers = [a.strip().lower() for a in correct_answer.split("/")]
        is_correct = user_clean in accepted_answers

    return jsonify({
        "success": True,
        "is_correct": is_correct,
        "correct_answer": correct_answer,
    })


@app.route("/api/zhongkao/explain", methods=["POST"])
def zhongkao_explain():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "请求体不能为空"}), 400

    question_id = data.get("question_id")
    user_answer = data.get("user_answer")
    is_correct = data.get("is_correct")
    source_type = data.get("source_type")

    if not question_id:
        return jsonify({"success": False, "error": "缺少题目ID"}), 400
    if is_correct is None:
        return jsonify({"success": False, "error": "缺少是否正确标记"}), 400
    if source_type not in VALID_ZHONGKAO_SOURCE_TYPES:
        return jsonify({"success": False, "error": "题型必须是 choice 或 cloze"}), 400

    question, err_resp, err_code = _lookup_question(question_id, source_type)
    if err_resp:
        return jsonify(err_resp), err_code

    correct_answer = question.get("correctAnswer", "")

    try:
        explanation = llm_service.explain_zhongkao_question(
            question, user_answer or "", bool(is_correct), correct_answer
        )
        return jsonify({"success": True, "explanation": explanation})
    except Exception as e:
        logger.error("生成中考题解析失败: %s", str(e), exc_info=True)
        return jsonify({"success": False, "error": "生成解析失败，请稍后重试"}), 500


@app.route("/api/zhongkao/similar", methods=["POST"])
def zhongkao_similar():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "请求体不能为空"}), 400

    question = data.get("question")
    knowledge_point_id = data.get("knowledge_point_id")
    knowledge_point_name = data.get("knowledge_point_name")
    source_type = data.get("source_type")

    if not question:
        return jsonify({"success": False, "error": "缺少题目信息"}), 400
    if not knowledge_point_id:
        return jsonify({"success": False, "error": "缺少知识点ID"}), 400
    if not knowledge_point_name:
        return jsonify({"success": False, "error": "缺少知识点名称"}), 400
    if source_type not in VALID_ZHONGKAO_SOURCE_TYPES:
        return jsonify({"success": False, "error": "题型必须是 choice 或 cloze"}), 400

    try:
        new_question = llm_service.generate_similar_question(
            question, knowledge_point_id, knowledge_point_name
        )
        # 相似题由 LLM 实时生成，保留 correctAnswer 供前端展示参考答案
        safe_question = {
            "stem": new_question.get("stem", ""),
            "options": new_question.get("options"),
            "sourceType": new_question.get("sourceType", source_type),
            "correctAnswer": new_question.get("correctAnswer", ""),
            "explanation": new_question.get("explanation", ""),
        }
        return jsonify({
            "success": True,
            "question": safe_question,
        })
    except Exception as e:
        logger.error("生成相似题失败: %s", str(e), exc_info=True)
        return jsonify({"success": False, "error": "生成相似题失败，请稍后重试"}), 500


@app.route("/wrong-questions")
def wrong_questions():
    return render_template("wrong_questions.html")


@app.route("/stats")
def stats():
    return render_template("stats.html")


if __name__ == "__main__":
    logger.info("="*80)
    logger.info("【应用启动】准备启动 Flask 服务器...")
    logger.info("【应用启动】监听地址: http://0.0.0.0:5000")
    
    # 检查环境变量决定是否启用 debug 模式
    # debug=True 时 Werkzeug 会覆盖日志配置，导致看不到日志
    # 生产环境建议设置 FLASK_DEBUG=0 或不设置
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    
    if debug_mode:
        logger.info("【应用启动】调试模式: 开启（注意：可能影响日志输出）")
        logger.warning("【应用启动】建议使用 FLASK_DEBUG=0 以确保日志正常输出")
    else:
        logger.info("【应用启动】调试模式: 关闭（日志输出正常）")
    
    logger.info("="*80)
    
    # 使用 use_reloader=False 避免 Werkzeug 的日志处理器覆盖
    app.run(debug=debug_mode, host="0.0.0.0", port=5000, use_reloader=False)
