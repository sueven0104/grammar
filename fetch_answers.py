"""批量获取题库答案并保存到 answers.json
通过创建多个 session，顺序答题收集答案
"""
import json
import time
import urllib.request
import urllib.error
import os

API_BASE = "https://defensive-upon-pursue-pan.trycloudflare.com/api/quiz"
OUTPUT_FILE = "answers.json"
TARGET_QUESTIONS = 584  # 目标收集的题目数量

def api_post(endpoint, data):
    """发送 POST 请求"""
    url = f"{API_BASE}/{endpoint}"
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))

def create_session():
    """创建新的测验 session"""
    result = api_post("start", {"mode": "random"})
    return result

def submit_answer(session_id, question_id, answer="test"):
    """提交答案"""
    result = api_post("submit", {
        "sessionId": session_id,
        "questionId": question_id,
        "userAnswer": answer
    })
    return result

def load_existing_answers():
    """加载已有的答案"""
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_answers(answers):
    """保存答案"""
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(answers, f, ensure_ascii=False, indent=2)

def main():
    answers = load_existing_answers()
    print(f"已有 {len(answers)} 道题的答案，目标 {TARGET_QUESTIONS} 道")

    session_count = 0
    total_answered = len(answers)

    while total_answered < TARGET_QUESTIONS:
        try:
            # 创建新 session
            session_data = create_session()
            session_id = session_data["sessionId"]
            session_count += 1

            current_q = session_data.get("currentQuestion")
            questions_in_session = 0

            while current_q and questions_in_session < 5:
                qid = current_q["id"]

                # 如果已经有答案，跳过
                if qid in answers:
                    # 提交一个答案以获取下一题
                    try:
                        result = submit_answer(session_id, qid, answers[qid]["correctAnswer"])
                        current_q = result.get("nextQuestion")
                        questions_in_session += 1
                    except:
                        break
                    continue

                # 提交答案获取正确答案
                try:
                    result = submit_answer(session_id, qid, "test_answer")
                    correct_answer = result.get("correctAnswer")
                    kp_id = result.get("question", {}).get("knowledgePointId")
                    kp_name = result.get("question", {}).get("knowledgePointName")

                    answers[qid] = {
                        "correctAnswer": correct_answer,
                        "knowledgePoint": kp_id,
                        "knowledgePointName": kp_name,
                    }
                    total_answered += 1
                    questions_in_session += 1

                    print(f"[{total_answered}/{TARGET_QUESTIONS}] {qid}: {correct_answer} (session {session_count})")

                    # 每 20 题保存一次
                    if total_answered % 20 == 0:
                        save_answers(answers)

                    current_q = result.get("nextQuestion")

                except Exception as e:
                    print(f"  提交失败 {qid}: {e}")
                    break

                time.sleep(0.2)

            # 达到目标
            if total_answered >= TARGET_QUESTIONS:
                break

        except Exception as e:
            print(f"Session 创建失败: {e}")
            time.sleep(1)
            continue

    # 最终保存
    save_answers(answers)
    print(f"\n完成！共收集 {len(answers)} 道题的答案")
    print(f"答案已保存到 {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
