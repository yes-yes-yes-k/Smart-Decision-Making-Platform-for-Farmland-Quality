from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from framework.domain.data.soil_data_loader import load_soil_data
from framework.domain.assessment.acidification import assess_acidification
from framework.domain.calculation.lime_calculator import calculate_lime_demand

county_bp = Blueprint('county', __name__)

@county_bp.route('/overview', methods=['GET'])
@jwt_required()
def get_overview():
    area_code = request.args.get('area_code', 'lechang')
    soil_data = load_soil_data(area_code)
    assessment = assess_acidification(soil_data)
    return jsonify({"status": "ok", "data": {"area": area_code, "assessment": assessment}})

@county_bp.route('/diagnose', methods=['POST'])
@jwt_required()
def diagnose():
    data = request.get_json()
    area_code = data.get('area_code', 'lechang')
    target_ph = data.get('target_ph', 6.0)

    soil_data = load_soil_data(area_code)
    assessment = assess_acidification(soil_data)
    calculation = calculate_lime_demand(assessment, target_ph=target_ph)

    return jsonify({"status": "ok", "data": {"area": area_code, "assessment": assessment, "calculation": calculation}})