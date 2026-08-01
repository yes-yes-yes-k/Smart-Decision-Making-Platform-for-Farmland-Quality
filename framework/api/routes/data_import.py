"""数据导入 API 路由：POST /api/v1/data/import

编排校验 → 部署 → 触发 → 审计日志的完整流程，支持 CSV / shapefile / 耕地质量评价 CSV 三类数据。
仅 admin 角色可调用。触发失败时自动从备份回滚。
"""
import os
import tempfile

from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity

from framework.config import Config
from framework.models.user import User
from framework.auth.decorators import admin_required
from framework.upload.data_validator import (
    validate_csv,
    validate_shapefile_zip,
    validate_dat,
)
from framework.upload.data_deployer import (
    backup_existing,
    deploy_csv,
    deploy_shapefile,
    deploy_dat,
    cleanup_backups,
    restore_from_backup,
)
from framework.upload.data_trigger import (
    trigger_csv_evaluate,
    trigger_shapefile_precompute,
    trigger_dat_check,
)
from framework.upload.audit_logger import log_data_import

data_import_bp = Blueprint('data_import', __name__)

_VALID_TYPES = ('csv', 'shapefile', 'dat')


@data_import_bp.route('/import', methods=['POST'])
@admin_required
def import_data():
    """数据导入端点：上传 → 校验 → 部署 → 触发 → 审计。"""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    username = user.username if user else 'unknown'

    # 1. 解析请求
    data_type = request.form.get('data_type')
    if not data_type:
        return jsonify({"status": "error", "message": "缺少 data_type 字段"}), 400
    if data_type not in _VALID_TYPES:
        return jsonify({"status": "error", "message": f"不支持的 data_type: {data_type}"}), 400

    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "缺少 file 字段"}), 400
    file = request.files['file']
    if not file.filename:
        return jsonify({"status": "error", "message": "未选择文件"}), 400

    # 2. 大小校验（Content-Length 头，早拒）
    max_size = Config.MAX_DATA_IMPORT_SIZE
    if request.content_length is not None and request.content_length > max_size:
        return jsonify({"status": "error", "message": f"文件大小超过 {max_size // (1024 * 1024)}MB 限制"}), 413

    # 3. 保存到临时文件
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp_path = tmp.name
    tmp.close()  # Windows 上必须先 close 再让 file.save 写入
    try:
        file.save(tmp_path)

        # 实际大小校验（防 Content-Length spoof）
        actual_size = os.path.getsize(tmp_path)
        if actual_size > max_size:
            return jsonify({"status": "error", "message": f"文件大小超过 {max_size // (1024 * 1024)}MB 限制"}), 413

        # 4. 校验
        manifest = {}
        if data_type == 'csv':
            ok, err = validate_csv(tmp_path)
        elif data_type == 'shapefile':
            ok, err, manifest = validate_shapefile_zip(tmp_path)
        else:
            ok, err = validate_dat(tmp_path)

        if not ok:
            log_data_import(username, data_type, file.filename, '', {}, False, f"校验失败: {err}")
            return jsonify({"status": "error", "message": err}), 400

        # 5. 部署 + 触发
        target_dir = Config.DATA_IMPORT_TARGETS[data_type]
        backup_path = backup_existing(target_dir)

        try:
            if data_type == 'csv':
                deployed_path = deploy_csv(tmp_path, target_dir)
                trigger_result = trigger_csv_evaluate(deployed_path)
            elif data_type == 'shapefile':
                deploy_shapefile(tmp_path, target_dir, manifest)
                deployed_path = target_dir
                trigger_result = trigger_shapefile_precompute(target_dir, manifest)
            else:
                deployed_path = deploy_dat(tmp_path, target_dir)
                trigger_result = trigger_dat_check(target_dir)
        except TimeoutError as e:
            restored = restore_from_backup(target_dir)
            log_data_import(
                username, data_type, file.filename, '', {}, False,
                f"触发超时: {e}", restored_from_backup=restored,
            )
            return jsonify({"status": "error", "message": f"触发超时: {e}"}), 504
        except Exception as e:
            restored = restore_from_backup(target_dir)
            log_data_import(
                username, data_type, file.filename, '', {}, False,
                f"触发异常: {e}", restored_from_backup=restored,
            )
            return jsonify({"status": "error", "message": f"触发失败: {e}"}), 500

        # 6. 检查触发结果是否为错误字典
        if data_type == 'dat':
            trigger_failed = not trigger_result.get('deployment_ok', False)
        else:
            trigger_failed = trigger_result.get('status') == 'error'

        if trigger_failed:
            restored = restore_from_backup(target_dir)
            log_data_import(
                username, data_type, file.filename, '', trigger_result, False,
                "触发返回错误", restored_from_backup=restored,
            )
            return jsonify({
                "status": "error",
                "message": "触发失败",
                "trigger_result": trigger_result,
            }), 500

        # 7. 成功：清理旧备份 + 审计
        cleanup_backups(target_dir)
        log_data_import(username, data_type, file.filename, deployed_path, trigger_result, True)

        return jsonify({
            "status": "ok",
            "data": {
                "data_type": data_type,
                "deployed_path": deployed_path,
                "backup_path": backup_path,
                "trigger_result": trigger_result,
            }
        })
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
