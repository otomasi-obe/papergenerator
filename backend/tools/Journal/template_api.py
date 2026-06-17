"""
Template API - Endpoints for template selection and metadata
"""
from typing import List, Optional

from flask import Blueprint, jsonify, request

from .template_registry import (
    get_template,
    get_template_info,
    get_all_templates_info,
    list_templates,
    validate_paper_for_template,
    TemplateField,
    TemplateType,
    CitationStyle,
)

template_bp = Blueprint("template", __name__, url_prefix="/api/templates")


@template_bp.route("/", methods=["GET"])
def get_templates():
    """Get all available templates with metadata"""
    field = request.args.get("field")
    template_type = request.args.get("type")
    citation_style = request.args.get("citation_style")
    
    field_enum = None
    if field:
        try:
            field_enum = TemplateField(field)
        except ValueError:
            pass
    
    type_enum = None
    if template_type:
        try:
            type_enum = TemplateType(template_type)
        except ValueError:
            pass
    
    style_enum = None
    if citation_style:
        try:
            style_enum = CitationStyle(citation_style)
        except ValueError:
            pass
    
    templates = list_templates(
        field=field_enum,
        template_type=type_enum,
        citation_style=style_enum,
    )
    
    return jsonify({
        "templates": [get_template_info(t.code) for t in templates],
        "count": len(templates),
    })


@template_bp.route("/<template_code>", methods=["GET"])
def get_template_detail(template_code: str):
    """Get detailed information about a specific template"""
    info = get_template_info(template_code)
    if not info:
        return jsonify({"error": "Template not found"}), 404
    
    return jsonify(info)


@template_bp.route("/<template_code>/validate", methods=["POST"])
def validate_paper(template_code: str):
    """Validate paper data against template requirements"""
    paper_data = request.get_json(silent=True)
    if not paper_data:
        return jsonify({"error": "No paper data provided"}), 400
    
    errors = validate_paper_for_template(paper_data, template_code)
    
    return jsonify({
        "valid": len(errors) == 0,
        "errors": errors,
        "template": template_code,
    })


@template_bp.route("/fields", methods=["GET"])
def get_fields():
    """Get all available template fields"""
    return jsonify({
        "fields": [{"value": f.value, "name": f.name} for f in TemplateField]
    })


@template_bp.route("/citation-styles", methods=["GET"])
def get_citation_styles():
    """Get all available citation styles"""
    return jsonify({
        "styles": [{"value": s.value, "name": s.name} for s in CitationStyle]
    })


@template_bp.route("/types", methods=["GET"])
def get_template_types():
    """Get all available template types"""
    return jsonify({
        "types": [{"value": t.value, "name": t.name} for t in TemplateType]
    })


@template_bp.route("/search", methods=["GET"])
def search_templates():
    """Search templates by name or field"""
    query = request.args.get("q", "").lower()
    if not query:
        return jsonify({"templates": [], "count": 0})
    
    all_templates = get_all_templates_info()
    
    results = [
        t for t in all_templates
        if query in t["name"].lower()
        or query in t["full_name"].lower()
        or any(query in f.lower() for f in t["fields"])
    ]
    
    return jsonify({
        "templates": results,
        "count": len(results),
        "query": query,
    })


@template_bp.route("/recommend", methods=["POST"])
def recommend_template():
    """Recommend templates based on paper metadata"""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    field = data.get("field")
    paper_type = data.get("type")
    
    field_enum = None
    if field:
        try:
            field_enum = TemplateField(field)
        except ValueError:
            pass
    
    type_enum = None
    if paper_type:
        try:
            type_enum = TemplateType(paper_type)
        except ValueError:
            pass
    
    templates = list_templates(field=field_enum, template_type=type_enum)
    
    recommendations = [get_template_info(t.code) for t in templates[:5]]
    
    return jsonify({
        "recommendations": recommendations,
        "count": len(recommendations),
    })
