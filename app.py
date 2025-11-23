from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import threading
import uuid
import time
import logging

from backend import parse_resume, score_candidate, schedule_interview, update_ats, notify_hr, process_workflow, send_decision_email
from backend import generate_ai_response

logger = logging.getLogger("hireflow.app")
if not logger.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(h)
logger.setLevel(logging.INFO)

app = Flask(__name__, static_folder='.')
CORS(app)

# Simple job store for demo
JOBS = {}


@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


@app.route('/api/parse', methods=['POST'])
def api_parse():
    try:
        data = request.get_json() or {}
        resume_text = data.get('resume_text', '')
        parsed = parse_resume(resume_text)
        return jsonify({'ok': True, 'parsed': parsed})
    except Exception as e:
        logger.exception('Parse failed')
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/score', methods=['POST'])
def api_score():
    try:
        data = request.get_json() or {}
        parsed = data.get('parsed_resume') or {
            'skills': data.get('skills', []),
            'experience_years': float(data.get('experience_years', 0)),
            'education': data.get('education', '')
        }
        job_requirements = data.get('job_requirements', {})
        result = score_candidate(parsed, job_requirements)
        return jsonify({'ok': True, 'score': result})
    except Exception as e:
        logger.exception('Score failed')
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/schedule', methods=['POST'])
def api_schedule():
    try:
        data = request.get_json() or {}
        name = data.get('candidate_name', '')
        email = data.get('candidate_email', '')
        date = data.get('preferred_date', '')
        info = schedule_interview(name, email, date)
        return jsonify({'ok': True, 'schedule': info})
    except Exception as e:
        logger.exception('Schedule failed')
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/ats', methods=['POST'])
def api_ats():
    try:
        data = request.get_json() or {}
        candidate_data = data.get('candidate_data', {})
        res = update_ats(candidate_data)
        return jsonify({'ok': True, 'ats': res})
    except Exception as e:
        logger.exception('ATS update failed')
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/notify', methods=['POST'])
def api_notify():
    try:
        data = request.get_json() or {}
        message = data.get('message', '')
        res = notify_hr(message)
        return jsonify({'ok': True, 'notify': res})
    except Exception as e:
        logger.exception('Notify failed')
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/decision', methods=['POST'])
def api_decision():
    try:
        data = request.get_json() or {}
        candidate_email = data.get('candidate_email', '')
        candidate_name = data.get('candidate_name', '')
        decision = data.get('decision', '')
        role = data.get('role', '')
        custom_message = data.get('message', '')
        res = send_decision_email(candidate_email, candidate_name, decision, role, custom_message)
        ok = res.get('status') in ('sent', 'success')
        return jsonify({'ok': ok, 'result': res})
    except Exception as e:
        logger.exception('Decision failed')
        return jsonify({'ok': False, 'error': str(e)}), 500


def _run_workflow_job(job_id: str, resume_text: str, job_requirements: dict, preferred_date: str):
    logger.info('Starting workflow job %s', job_id)
    try:
        result = process_workflow(resume_text, job_requirements, preferred_date)
        JOBS[job_id]['status'] = 'done'
        JOBS[job_id]['result'] = result
    except Exception as e:
        logger.exception('Workflow job failed')
        JOBS[job_id]['status'] = 'error'
        JOBS[job_id]['error'] = str(e)


@app.route('/api/workflow', methods=['POST'])
def api_workflow():
    try:
        data = request.get_json() or {}
        resume_text = data.get('resume_text', '')
        job_requirements = data.get('job_requirements', {})
        preferred_date = data.get('preferred_date', '')
        job_id = uuid.uuid4().hex
        JOBS[job_id] = {'status': 'running', 'created_at': time.time()}
        t = threading.Thread(target=_run_workflow_job, args=(job_id, resume_text, job_requirements, preferred_date), daemon=True)
        t.start()
        return jsonify({'ok': True, 'job_id': job_id})
    except Exception as e:
        logger.exception('Start workflow failed')
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/workflow/<job_id>', methods=['GET'])
def api_workflow_status(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        return jsonify({'ok': False, 'error': 'job not found'}), 404
    return jsonify({'ok': True, 'job': job})


@app.route('/api/chat', methods=['POST'])
def api_chat():
    try:
        data = request.get_json() or {}
        message = data.get('message', '')
        context = data.get('context', {})
        res = generate_ai_response(message, context)
        return jsonify({'ok': True, 'reply': res})
    except Exception as e:
        logger.exception('Chat failed')
        return jsonify({'ok': False, 'error': str(e)}), 500


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

