import threading
from datetime import datetime

from flask import Blueprint, request, jsonify, Response, copy_current_request_context
from flask_jwt_extended import jwt_required, get_jwt_identity
from framework.core_engine import core_engine
from framework.models.report import Report
from framework.models.user import db
from src.ai_culti_demo.report import generate_report, generate_pdf

report_bp = Blueprint('report', __name__)


def _async_generate_report(app, report_id, report_type, area_code):
    """后台线程：生成报告内容并更新数据库。"""
    with app.app_context():
        try:
            result = generate_report(report_type, area_code)
            report = db.session.get(Report, report_id)
            if report and result.get("status") == "ok":
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                report.title = f'{result["title"]}（{timestamp}）'
                report.content = result["content"]
                report.status = "completed"
            elif report:
                report.status = "failed"
            db.session.commit()
        except Exception as e:
            print(f"[Report] 后台生成失败 report_id={report_id}: {e}", flush=True)
            try:
                with app.app_context():
                    report = db.session.get(Report, report_id)
                    if report:
                        report.status = "failed"
                    db.session.commit()
            except Exception:
                pass

@report_bp.route('/summary', methods=['POST'])
@jwt_required()
def get_report_summary():
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "error": {"code": "MISSING_DIAGNOSIS", "message": "需要传入诊断结果或报告类型"}}), 400

    if data.get('status') != 'ok' and not data.get('report_type'):
        return jsonify({"status": "error", "error": {"code": "MISSING_DIAGNOSIS", "message": "需要传入成功的诊断结果或报告类型"}}), 400

    result = core_engine.build_report_summary(data)
    if result.get('status') == 'ok':
        return jsonify({"status": "ok", "data": result})
    return jsonify(result)


@report_bp.route('/generate', methods=['POST'])
@jwt_required()
def generate():
    user_id = get_jwt_identity()
    data = request.get_json()

    if not data:
        return jsonify({"status": "error", "error": {"code": "MISSING_PARAMS", "message": "缺少请求参数"}}), 400

    report_type = data.get('report_type')
    area_code = data.get('area_code')

    if not report_type or not area_code:
        return jsonify({"status": "error", "error": {"code": "MISSING_PARAMS", "message": "report_type 和 area_code 为必填参数"}}), 400

    # 先创建记录，status=processing，立即返回
    report = Report(
        title='报告生成中...',
        report_type=report_type,
        area_code=area_code,
        content='',
        status='processing',
        create_by=user_id
    )
    db.session.add(report)
    db.session.commit()
    report_id = report.id

    # 后台线程异步生成报告内容
    from flask import current_app
    app = current_app._get_current_object()
    thread = threading.Thread(
        target=_async_generate_report,
        args=(app, report_id, report_type, area_code),
        daemon=True
    )
    thread.start()

    return jsonify({"status": "ok", "data": report.to_dict()})


@report_bp.route('/list', methods=['GET'])
@jwt_required()
def report_list():
    user_id = get_jwt_identity()
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)

    pagination = Report.query.filter_by(create_by=user_id)\
        .order_by(Report.create_time.desc())\
        .paginate(page=page, per_page=page_size, error_out=False)

    items = []
    for r in pagination.items:
        d = r.to_dict()
        d.pop('content', None)
        items.append(d)

    return jsonify({
        "status": "ok",
        "data": {
            "list": items,
            "total": pagination.total
        }
    })


@report_bp.route('/<int:report_id>', methods=['GET'])
@jwt_required()
def report_detail(report_id):
    user_id = get_jwt_identity()
    report = Report.query.filter_by(id=report_id, create_by=user_id).first()

    if not report:
        return jsonify({"status": "error", "error": {"code": "NOT_FOUND", "message": "报告不存在"}}), 404

    return jsonify({"status": "ok", "data": report.to_dict()})


@report_bp.route('/<int:report_id>/download', methods=['GET'])
@jwt_required()
def report_download(report_id):
    user_id = get_jwt_identity()
    report = Report.query.filter_by(id=report_id, create_by=user_id).first()

    if not report:
        return jsonify({"status": "error", "error": {"code": "NOT_FOUND", "message": "报告不存在"}}), 404

    if report.status != 'completed':
        return jsonify({"status": "error", "error": {"code": "NOT_READY", "message": "报告尚未生成完成"}}), 400

    pdf_bytes = generate_pdf(report.content)
    print(f"[Download] report_id={report_id}, content_len={len(report.content or '')}, pdf_len={len(pdf_bytes)}, is_pdf={pdf_bytes[:5] == b'%PDF-'}", flush=True)

    return Response(
        pdf_bytes,
        mimetype='application/pdf',
        headers={
            'Content-Disposition': f'attachment; filename=report_{report_id}.pdf',
            'Content-Length': str(len(pdf_bytes))
        }
    )